# -*- coding: utf-8 -*-
"""
Modelo hr.contract.deductions.rtf - Deducciones para retencion en la fuente.
"""
from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError

from .hr_contractual_modifications import TOPES_DEDUCCIONES_RTF

class HrContractDeductionsRtf(models.Model):
    _name = 'hr.contract.deductions.rtf'
    _description = 'Deducciones para Retención en la Fuente'

    input_id = fields.Many2one('hr.salary.rule', 'Regla', required=True,
                               help='Regla salarial', domain="[('type_concepts','=','tributaria')]")
    date_start = fields.Date('Fecha Inicial')
    date_end = fields.Date('Fecha Final')
    number_months = fields.Integer('N° Meses')
    value_total = fields.Float('Valor Total Certificado')
    value_monthly = fields.Float('Valor Mensualizado')
    contract_id = fields.Many2one('hr.contract', 'Contrato', required=True,
                                  ondelete='cascade', index=True)

    # ─────────────────────────────────────────────────────────────────────────
    # CAMPOS NORMATIVOS - Límites según Estatuto Tributario
    # ─────────────────────────────────────────────────────────────────────────
    limite_uvt_mensual = fields.Float('Limite UVT Mensual', compute='_compute_limites_normativos', store=True)
    limite_uvt_anual = fields.Float('Limite UVT Anual', compute='_compute_limites_normativos', store=True)
    limite_pesos_mensual = fields.Float('Limite $ Mensual', compute='_compute_limite_pesos')
    limite_pesos_anual = fields.Float('Limite $ Anual', compute='_compute_limite_pesos')
    base_legal = fields.Char('Base Legal', compute='_compute_limites_normativos', store=True)
    valor_acumulado_anio = fields.Float('Valor Acumulado Anio', compute='_compute_valor_acumulado')
    porcentaje_usado = fields.Float('% Usado del Limite', compute='_compute_valor_acumulado')

    # ─────────────────────────────────────────────────────────────────────────
    # RELACION CON NOMINAS
    # ─────────────────────────────────────────────────────────────────────────
    payslip_line_ids = fields.Many2many(
        'hr.payslip.line',
        string='Lineas de Nomina',
        compute='_compute_payslip_lines',
        help='Lineas de nomina donde se ha aplicado esta deduccion'
    )
    payslip_count = fields.Integer(
        'Aplicaciones',
        compute='_compute_payslip_lines',
        help='Numero de veces que se ha aplicado en nominas'
    )
    last_payslip_date = fields.Date(
        'Ultima Aplicacion',
        compute='_compute_payslip_lines',
        help='Fecha de la ultima nomina donde se aplico'
    )

    def _compute_payslip_lines(self):
        """Obtiene las lineas de nomina relacionadas con esta deduccion."""
        PayslipLine = self.env['hr.payslip.line']
        for record in self:
            if not record.contract_id or not record.input_id:
                record.payslip_line_ids = False
                record.payslip_count = 0
                record.last_payslip_date = False
                continue

            lines = PayslipLine.search([
                ('slip_id.contract_id', '=', record.contract_id.id),
                ('salary_rule_id', '=', record.input_id.id),
                ('slip_id.state', 'in', ['done', 'paid'])
            ], order='slip_id desc')

            record.payslip_line_ids = lines
            record.payslip_count = len(lines)
            if lines:
                record.last_payslip_date = lines[0].slip_id.date_to
            else:
                record.last_payslip_date = False

    def action_view_payslip_lines(self):
        """Abre vista de lineas de nomina relacionadas."""
        self.ensure_one()
        return {
            'name': _('Aplicaciones en Nomina'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payslip.line',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.payslip_line_ids.ids)],
            'context': {'create': False},
        }

    @api.depends('input_id', 'input_id.code')
    def _compute_limites_normativos(self):
        """Calcula los límites normativos según el tipo de deducción."""
        for record in self:
            codigo = record.input_id.code if record.input_id else False
            if codigo and codigo in TOPES_DEDUCCIONES_RTF:
                topes = TOPES_DEDUCCIONES_RTF[codigo]
                record.limite_uvt_mensual = topes.get('uvt_mensual', 0)
                record.limite_uvt_anual = topes.get('uvt_anual', 0)
                record.base_legal = topes.get('base_legal', '')
            else:
                record.limite_uvt_mensual = 0
                record.limite_uvt_anual = 0
                record.base_legal = ''

    @api.depends('limite_uvt_mensual', 'limite_uvt_anual')
    def _compute_limite_pesos(self):
        """Convierte los límites UVT a pesos según el valor del UVT vigente."""
        for record in self:
            # Obtener UVT del año actual
            year = fields.Date.today().year
            company_id = (
                record.contract_id.company_id.id
                if record.contract_id and record.contract_id.company_id
                else self.env.company.id
            )
            annual_params = self.env['hr.annual.parameters'].get_for_year(
                year,
                company_id=company_id,
                raise_if_not_found=False,
            )
            uvt = annual_params.value_uvt if annual_params else 0

            record.limite_pesos_mensual = record.limite_uvt_mensual * uvt
            record.limite_pesos_anual = record.limite_uvt_anual * uvt

    @api.depends('contract_id', 'input_id', 'value_monthly')
    def _compute_valor_acumulado(self):
        """Calcula el valor acumulado de la deducción en el año fiscal actual."""
        for record in self:
            if not record.contract_id or not record.input_id:
                record.valor_acumulado_anio = 0
                record.porcentaje_usado = 0
                continue

            year = fields.Date.today().year
            # Buscar nóminas del año actual para este contrato
            payslips = self.env['hr.payslip'].search([
                ('contract_id', '=', record.contract_id.id),
                ('date_from', '>=', f'{year}-01-01'),
                ('date_to', '<=', f'{year}-12-31'),
                ('state', 'in', ['done', 'paid'])
            ])

            if payslips:
                grouped = self.env['hr.payslip.line']._read_group(
                    [
                        ('slip_id', 'in', payslips.ids),
                        ('code', '=', record.input_id.code)
                    ],
                    groupby=[],
                    aggregates=['total:sum'],
                )
                total_sum = grouped[0][0] or 0.0 if grouped else 0.0
                record.valor_acumulado_anio = abs(float(total_sum))
            else:
                # Si no hay nóminas, calcular basado en valor mensual × meses transcurridos
                mes_actual = fields.Date.today().month
                record.valor_acumulado_anio = record.value_monthly * mes_actual

            # Calcular porcentaje usado del límite anual
            if record.limite_pesos_anual > 0:
                record.porcentaje_usado = (record.valor_acumulado_anio / record.limite_pesos_anual) * 100
            else:
                record.porcentaje_usado = 0

    # ─────────────────────────────────────────────────────────────────────────
    # VALIDACIONES
    # ─────────────────────────────────────────────────────────────────────────
    @api.onchange('value_total')
    def _onchange_value_total(self):
        for record in self:
            if record.value_total > 0:
                if not record.date_start:
                    raise UserError(_('No se ha especificado la fecha inicial.'))
                if not record.date_end:
                    raise UserError(_('No se ha especificado la fecha final'))

                nSecondDif = (record.date_end - record.date_start).total_seconds()
                nMinutesDif = round(nSecondDif/60,0)
                nHoursDif = round(nMinutesDif/60,0)
                nDaysDif = round(nHoursDif/24,0)
                nMonthsDif = round(nDaysDif/30,0)

                if nMonthsDif != 0:
                    if record.number_months > 0:
                        self.value_monthly = record.value_total / record.number_months
                    else:
                        self.value_monthly = record.value_total / 12
                else:
                    raise UserError(_('La fecha inicial es mayor que la fecha final, por favor verificar.'))

    @api.onchange('value_monthly')
    def _onchange_value_monthly(self):
        for record in self:
            if record.value_monthly > 0:
                if not record.date_start:
                    raise UserError(_('No se ha especificado la fecha inicial.'))
                if not record.date_end:
                    raise UserError(_('No se ha especificado la fecha final'))

                nSecondDif = (record.date_end - record.date_start).total_seconds()
                nMinutesDif = round(nSecondDif/60,0)
                nHoursDif = round(nMinutesDif/60,0)
                nDaysDif = round(nHoursDif/24,0)
                nMonthsDif = round(nDaysDif/30,0)

                if nMonthsDif != 0:
                    if record.number_months > 0:
                        self.value_total = record.value_monthly * record.number_months
                    else:
                        self.value_total = record.value_monthly * 12
                else:
                    raise UserError(_('La fecha inicial es mayor que la fecha final, por favor verificar.'))

    @api.onchange('value_monthly', 'limite_pesos_mensual')
    def _onchange_validar_limite(self):
        """Valida que el valor mensual no exceda el límite normativo."""
        for record in self:
            if record.value_monthly > 0 and record.limite_pesos_mensual > 0:
                if record.value_monthly > record.limite_pesos_mensual:
                    return {
                        'warning': {
                            'title': 'Advertencia - Límite Excedido',
                            'message': f'El valor mensual (${record.value_monthly:,.0f}) excede el límite '
                                      f'normativo de {record.limite_uvt_mensual} UVT (${record.limite_pesos_mensual:,.0f}). '
                                      f'Base Legal: {record.base_legal}'
                        }
                    }

    _change_deductionsrtf_uniq = models.Constraint('unique(input_id, contract_id)',
                                                   'Ya existe esta deducción para este contrato, por favor verificar.')

    # ─────────────────────────────────────────────────────────────────────────
    # SINCRONIZACION CON REPORTE DE RETENCION
    # ─────────────────────────────────────────────────────────────────────────
    retencion_reporte_count = fields.Integer(
        'Reportes Retencion',
        default=0,
        help='Cantidad de reportes de retencion relacionados'
    )
    valor_promedio_aplicado = fields.Float(
        'Valor Promedio Aplicado',
        default=0,
        help='Valor promedio aplicado en los ultimos 3 meses segun reporte de retencion'
    )
    diferencia_configurado_aplicado = fields.Float(
        'Diferencia Config vs Aplicado',
        default=0,
        help='Diferencia entre el valor mensualizado configurado y el valor promedio aplicado'
    )
    ultima_sincronizacion = fields.Datetime(
        'Ultima Sincronizacion',
        help='Fecha de la ultima sincronizacion con reportes de retencion'
    )

    # Mapeo de codigos de regla a campos en lavish.retencion.reporte
    # Incluye codigos exactos y prefijos para mayor flexibilidad
    CAMPO_RETENCION_MAP = {
        # Vivienda - codigo exacto y variantes
        'INTVIV': 'ded_vivienda',
        'VIVIENDA': 'ded_vivienda',
        'DED_VIV': 'ded_vivienda',
        'INT_VIV': 'ded_vivienda',
        # Dependientes
        'DEPENDIENTES': 'ded_dependientes',
        'DED_DEP': 'ded_dependientes',
        # Medicina prepagada - codigo exacto y variantes
        'MEDPRE': 'ded_salud',
        'SALUD_PREP': 'ded_salud',
        'DED_SALUD': 'ded_salud',
        'MED_PREP': 'ded_salud',
        # AVP/AFC
        'AVP': 'valor_avp_afc',
        'AFC': 'valor_avp_afc',
        'AVP_AFC': 'valor_avp_afc',
    }

    def action_actualizar_desde_reportes(self):
        """Actualiza los campos desde los reportes de retencion."""
        RetencionReporte = self.env['lavish.retencion.reporte']

        for record in self:
            if not record.contract_id or not record.input_id:
                continue

            employee = record.contract_id.employee_id
            if not employee:
                continue

            # Buscar reportes de retencion del empleado (ultimos 6 meses)
            fecha_limite = fields.Date.today() - relativedelta(months=6)
            reportes = RetencionReporte.search([
                ('employee_id', '=', employee.id),
                ('date', '>=', fecha_limite)
            ], order='date desc', limit=12)

            # Calcular valor promedio aplicado basado en el tipo de deduccion
            codigo = (record.input_id.code or '').upper()
            campo_retencion = None

            for prefijo, campo in self.CAMPO_RETENCION_MAP.items():
                if prefijo in codigo:
                    campo_retencion = campo
                    break

            promedio = 0
            if campo_retencion and reportes:
                # Tomar los ultimos 3 registros para calcular promedio
                ultimos_3 = reportes[:3]
                valores = [getattr(r, campo_retencion, 0) or 0 for r in ultimos_3]
                promedio = sum(valores) / len(valores) if valores else 0

            record.write({
                'retencion_reporte_count': len(reportes),
                'valor_promedio_aplicado': promedio,
                'diferencia_configurado_aplicado': record.value_monthly - promedio,
                'ultima_sincronizacion': fields.Datetime.now(),
            })

        return True

    @api.model
    def actualizar_todos_desde_reportes(self):
        """Actualiza todos los registros desde reportes de retencion. Para cron."""
        deducciones = self.search([])
        deducciones.action_actualizar_desde_reportes()
        return {
            'registros_actualizados': len(deducciones)
        }

    def action_view_retencion_reportes(self):
        """Abre vista de reportes de retencion relacionados."""
        self.ensure_one()
        employee = self.contract_id.employee_id
        if not employee:
            raise UserError(_('El contrato no tiene empleado asignado.'))

        return {
            'name': _('Reportes de Retencion'),
            'type': 'ir.actions.act_window',
            'res_model': 'lavish.retencion.reporte',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', employee.id)],
            'context': {'create': False},
        }

    def action_sync_from_retencion_reporte(self):
        """Sincroniza el valor mensualizado desde el reporte de retencion."""
        # Primero actualizar desde reportes
        self.action_actualizar_desde_reportes()

        actualizados = 0
        for record in self:
            if record.valor_promedio_aplicado > 0:
                record.value_monthly = record.valor_promedio_aplicado
                record.diferencia_configurado_aplicado = 0  # Ya estan sincronizados
                # Recalcular valor total si hay meses definidos
                if record.number_months > 0:
                    record.value_total = record.value_monthly * record.number_months
                actualizados += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Sincronizacion Completada'),
                'message': _('Se actualizaron %(count)s deducciones desde el reporte de retencion.') % {
                    'count': actualizados
                },
                'type': 'success',
                'sticky': False,
            }
        }

    @api.model
    def sync_all_from_retencion_reporte(self, contract_ids=None):
        """
        Sincroniza todas las deducciones RTF desde los reportes de retencion.
        Puede ejecutarse como cron o manualmente.

        Args:
            contract_ids: Lista de IDs de contratos a sincronizar. Si es None, sincroniza todos.
        """
        domain = []
        if contract_ids:
            domain.append(('contract_id', 'in', contract_ids))

        deducciones = self.search(domain)

        # Primero actualizar campos desde reportes
        deducciones.action_actualizar_desde_reportes()

        actualizadas = 0
        for deduccion in deducciones:
            if deduccion.valor_promedio_aplicado > 0:
                diferencia = abs(deduccion.diferencia_configurado_aplicado)
                # Solo actualizar si hay diferencia significativa (> 1%)
                if diferencia > (deduccion.value_monthly * 0.01) or deduccion.value_monthly == 0:
                    deduccion.value_monthly = deduccion.valor_promedio_aplicado
                    deduccion.diferencia_configurado_aplicado = 0
                    if deduccion.number_months > 0:
                        deduccion.value_total = deduccion.value_monthly * deduccion.number_months
                    actualizadas += 1

        return {
            'deducciones_procesadas': len(deducciones),
            'deducciones_actualizadas': actualizadas
        }

    @api.model
    def sync_from_payslip_lines(self, payslip_ids=None, meses_atras=3):
        """
        Sincroniza deducciones RTF desde lineas de nomina.
        Busca lineas con codigos de deduccion y actualiza valores en RTF.

        Args:
            payslip_ids: Lista de IDs de nominas. Si es None, busca en ultimos N meses.
            meses_atras: Meses hacia atras para buscar nominas (default 3).
        """
        PayslipLine = self.env['hr.payslip.line']

        # Codigos de deduccion a buscar
        codigos_deduccion = list(self.CAMPO_RETENCION_MAP.keys())

        # Dominio para buscar lineas
        domain = [
            ('code', 'in', codigos_deduccion),
            ('total', '!=', 0)
        ]

        if payslip_ids:
            domain.append(('slip_id', 'in', payslip_ids))
        else:
            fecha_limite = fields.Date.today() - relativedelta(months=meses_atras)
            domain.append(('slip_id.date_to', '>=', fecha_limite))
            domain.append(('slip_id.state', '=', 'done'))

        lineas = PayslipLine.search(domain)

        # Agrupar por contrato y codigo
        valores_por_contrato = {}
        for linea in lineas:
            contract = linea.slip_id.contract_id
            if not contract:
                continue

            key = (contract.id, linea.code)
            if key not in valores_por_contrato:
                valores_por_contrato[key] = {
                    'contract_id': contract.id,
                    'code': linea.code,
                    'valores': [],
                }
            valores_por_contrato[key]['valores'].append(abs(linea.total))

        # Actualizar deducciones RTF
        actualizadas = 0
        for key, data in valores_por_contrato.items():
            contract_id, code = key
            valores = data['valores']

            if not valores:
                continue

            # Calcular promedio
            promedio = sum(valores) / len(valores)

            # Buscar deduccion RTF existente
            deduccion = self.search([
                ('contract_id', '=', contract_id),
                ('input_id.code', '=', code)
            ], limit=1)

            if deduccion:
                # Solo actualizar si hay diferencia significativa
                if deduccion.value_monthly == 0 or abs(deduccion.value_monthly - promedio) > (promedio * 0.01):
                    deduccion.value_monthly = promedio
                    if deduccion.number_months > 0:
                        deduccion.value_total = promedio * deduccion.number_months
                    actualizadas += 1

        return {
            'lineas_encontradas': len(lineas),
            'contratos_procesados': len(valores_por_contrato),
            'deducciones_actualizadas': actualizadas
        }

    def action_sync_from_payslip(self):
        """Accion para sincronizar desde nominas del contrato."""
        self.ensure_one()
        if not self.contract_id:
            raise UserError(_('No hay contrato asociado.'))

        # Buscar nominas del contrato
        payslips = self.env['hr.payslip'].search([
            ('contract_id', '=', self.contract_id.id),
            ('state', '=', 'done')
        ], limit=6, order='date_to desc')

        if not payslips:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sin Datos'),
                    'message': _('No hay nominas confirmadas para este contrato.'),
                    'type': 'warning',
                    'sticky': False,
                }
            }

        result = self.sync_from_payslip_lines(payslip_ids=payslips.ids)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Sincronizacion Completada'),
                'message': _('Lineas: %(lineas)s, Actualizadas: %(actualizadas)s') % {
                    'lineas': result['lineas_encontradas'],
                    'actualizadas': result['deducciones_actualizadas'],
                },
                'type': 'success',
                'sticky': False,
            }
        }

    @api.model
    def set_deduction_value(self, contract_id, code, value_monthly, value_total=0):
        """
        Establece el valor de una deduccion RTF.
        Util para cargar valores desde scripts o integraciones.

        Args:
            contract_id: ID del contrato
            code: Codigo de la regla salarial (INTVIV, MEDPRE, etc.)
            value_monthly: Valor mensual
            value_total: Valor total anual (opcional)

        Returns:
            dict con resultado de la operacion
        """
        # Buscar regla salarial por codigo
        rule = self.env['hr.salary.rule'].search([('code', '=', code)], limit=1)
        if not rule:
            return {'success': False, 'error': f'Regla salarial con codigo {code} no encontrada'}

        # Buscar deduccion existente
        deduccion = self.search([
            ('contract_id', '=', contract_id),
            ('input_id', '=', rule.id)
        ], limit=1)

        if deduccion:
            # Actualizar existente
            deduccion.write({
                'value_monthly': value_monthly,
                'value_total': value_total or (value_monthly * 12),
            })
            return {'success': True, 'action': 'updated', 'id': deduccion.id}
        else:
            # Crear nueva
            nueva = self.create({
                'contract_id': contract_id,
                'input_id': rule.id,
                'value_monthly': value_monthly,
                'value_total': value_total or (value_monthly * 12),
                'number_months': 12,
            })
            return {'success': True, 'action': 'created', 'id': nueva.id}

    @api.model
    def bulk_set_deduction_values(self, values_list):
        """
        Establece valores de deducciones en lote.

        Args:
            values_list: Lista de diccionarios con:
                - contract_id: ID del contrato
                - code: Codigo de regla (INTVIV, MEDPRE)
                - value_monthly: Valor mensual

        Returns:
            dict con resumen de la operacion
        """
        resultados = {
            'total': len(values_list),
            'created': 0,
            'updated': 0,
            'errors': []
        }

        for item in values_list:
            contract_id = item.get('contract_id')
            code = item.get('code')
            value_monthly = item.get('value_monthly', 0)
            value_total = item.get('value_total', 0)

            if not contract_id or not code:
                resultados['errors'].append(f'Datos incompletos: {item}')
                continue

            result = self.set_deduction_value(contract_id, code, value_monthly, value_total)

            if result.get('success'):
                if result.get('action') == 'created':
                    resultados['created'] += 1
                else:
                    resultados['updated'] += 1
            else:
                resultados['errors'].append(result.get('error', 'Error desconocido'))

        return resultados
