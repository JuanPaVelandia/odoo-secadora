# -*- coding: utf-8 -*-
from odoo import models, api, fields, _
from odoo.exceptions import UserError
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
import json
import logging

_logger = logging.getLogger(__name__)


class HrPayslipLine(models.Model):
    _inherit = 'hr.payslip.line'

    # ======================================================================
    # CAMPOS ADICIONALES PARA NOMINA COLOMBIANA
    # ======================================================================

    # Campos de clasificacion
    object_type = fields.Selection([
        ('regular', 'Concepto Regular'),
        ('novelty', 'Novedad'),
        ('absence', 'Ausencia'),
        ('vacation', 'Vacaciones'),
        ('loan', 'Prestamo'),
        ('prima', 'Prima'),
        ('cesantias', 'Cesantias'),
        ('int_cesantias', 'Intereses Cesantias'),
        ('provision', 'Provision'),
        ('liquidation', 'Liquidacion')
    ], string='Tipo de Objeto', default='regular', index=True)

    technical_key = fields.Char('Clave Tecnica', index=True)
    ytd = fields.Monetary(string='YTD')

    # Relaciones adicionales
    entity_id = fields.Many2one('hr.employee.entities', string="Entidad", index=True)
    concept_id = fields.Many2one('hr.contract.concepts', string='Concepto Relacionado', ondelete='set null')
    leave_id = fields.Many2one('hr.leave', string='Ausencia')
    vacation_leave_id = fields.Many2one('hr.leave', 'Ausencia de vacaciones')
    loan_id = fields.Many2one('hr.loan', 'Prestamo', readonly=True)
    loan_installment_id = fields.Many2one('hr.loan.installment', 'Cuota de Prestamo', readonly=True)
    skip_id = fields.Many2one('hr.contract.concept.skip', string='Salto Aplicado')
    run_id = fields.Many2one('hr.payslip.run', 'Lote de Nomina', index=True)

    # Fechas de ausencia (desde leave_id)
    leave_date_from = fields.Datetime(related='leave_id.date_from', string='Inicio Ausencia', store=True)
    leave_date_to = fields.Datetime(related='leave_id.date_to', string='Fin Ausencia', store=True)
    leave_number_of_days = fields.Float(related='leave_id.number_of_days', string='Dias Ausencia', store=True)

    # Campos relacionados (stored para reportes y busquedas)
    identification_id = fields.Char(related='employee_id.identification_id', string='Identificacion', store=True, index=True)
    department_id = fields.Many2one(related='employee_id.department_id', string='Departamento', store=True)
    job_id = fields.Many2one(related='employee_id.job_id', string='Puesto de Trabajo', store=True)
    date_from = fields.Date(related="slip_id.date_from", store=True, index=True)
    date_to = fields.Date(related="slip_id.date_to", store=True, index=True)
    category_code = fields.Char(related='salary_rule_id.category_id.code', string='Codigo Categoria', store=True, index=True)
    category_type = fields.Selection(related='category_id.category_type', store=True, string='Tipo de Categoria')
    struct_slip_id = fields.Many2one(related='slip_id.struct_id', string='Estructura', store=True)
    struct_process = fields.Selection(related='slip_id.struct_process', string='Proceso', store=True, index=True)
    process = fields.Selection(related='salary_rule_id.process', string='Proceso de Regla', store=True)
    slip_number = fields.Char(related='slip_id.number', string='N Nomina', store=True, index=True)
    run_name = fields.Char(related='run_id.name', string='Lote', store=True)
    period_id = fields.Many2one(related="slip_id.period_id", string='Periodo', store=True, index=True)
    company_id = fields.Many2one(related='slip_id.company_id', store=True, index=True)
    state_slip = fields.Selection(related='slip_id.state', string='Estado Nomina', store=True, index=True)
    analytic_account_slip_id = fields.Many2one(related='slip_id.analytic_account_id', string='Cuenta Analitica', store=True)

    # Campos de regla salarial (stored para reportes)
    dev_or_ded = fields.Selection(related='salary_rule_id.dev_or_ded', string='Naturaleza', store=True)
    afecta_totales = fields.Selection(related='salary_rule_id.afecta_totales', string='Afecta Totales', store=True)
    type_concepts = fields.Selection(related='salary_rule_id.type_concepts', string='Tipo de Concepto', store=True)
    is_leave = fields.Boolean(related='salary_rule_id.is_leave', string='Es Ausencia', store=True)
    is_recargo = fields.Boolean(related='salary_rule_id.is_recargo', string='Es Recargo', store=True)
    display_days_worked = fields.Boolean(related='salary_rule_id.display_days_worked', store=True)
    appears_on_payslip = fields.Boolean(related='salary_rule_id.appears_on_payslip', readonly=True)
    liquidar_con_base = fields.Boolean(related='salary_rule_id.liquidar_con_base', string='Liquidar con IBC mes anterior', store=True)

    # Bases para prestaciones sociales
    base_prima = fields.Boolean(related='salary_rule_id.base_prima', store=True)
    base_cesantias = fields.Boolean(related='salary_rule_id.base_cesantias', store=True)
    base_vacaciones = fields.Boolean(related='salary_rule_id.base_vacaciones', store=True)
    base_vacaciones_dinero = fields.Boolean(related='salary_rule_id.base_vacaciones_dinero', store=True)
    base_intereses_cesantias = fields.Boolean(related='salary_rule_id.base_intereses_cesantias', store=True)
    base_seguridad_social = fields.Boolean(related='salary_rule_id.base_seguridad_social', store=True)
    base_parafiscales = fields.Boolean(related='salary_rule_id.base_parafiscales', store=True)
    base_compensation = fields.Boolean(related='salary_rule_id.base_compensation', store=True)
    base_auxtransporte_tope = fields.Boolean(related='salary_rule_id.base_auxtransporte_tope', store=True)

    # Campos de calculo
    subtotal = fields.Monetary('Subtotal')
    amount_base = fields.Float('Base', digits=(18, 2))

    # Fechas especificas
    date_out = fields.Date('Fecha Salida')
    date_in = fields.Date('Fecha Entrada')
    vacation_departure_date = fields.Date('Fecha Salida Vacaciones')
    vacation_return_date = fields.Date('Fecha Regreso Vacaciones')
    initial_accrual_date = fields.Date('Causacion Inicio')
    final_accrual_date = fields.Date('Causacion Fin')
    period_start = fields.Date(string='Periodo Inicio Calculo')
    period_end = fields.Date(string='Periodo Fin Calculo')

    # Unidades de tiempo
    business_units = fields.Float('Unidades Habiles', digits=(16, 2))
    business_31_units = fields.Float('Unidades Habiles - Dias 31', digits=(16, 2))
    holiday_units = fields.Float('Unidades Festivos', digits=(16, 2))
    holiday_31_units = fields.Float('Unidades Festivos - Dias 31', digits=(16, 2))
    days_unpaid_absences = fields.Integer(string='Dias Ausencias No Pagadas')
    days_count = fields.Float(string='Dias Contados')

    # Visualizacion
    display_type = fields.Selection([
        ('normal', 'Normal'),
        ('days', 'Dias Trabajados'),
        ('totals', 'Totales'),
        ('line_section', 'Seccion'),
        ('line_note', 'Nota')
    ], string='Tipo de Visualizacion', default='normal')

    # Indicadores
    is_previous_period = fields.Boolean('Novedad Saltada')

    # Clasificación efectiva para totales
    afecta_totales_effective = fields.Selection(
        [('devengo', 'Devengo'), ('deduccion', 'Deducción'), ('ninguno', 'Ninguno')],
        string='Afecta Totales (Efectivo)',
        compute='_compute_afecta_totales_effective',
        store=False
    )
    ex_rent = fields.Boolean('Aporte Voluntario/Ingreso Exento de Renta')
    afc = fields.Boolean('AFC')
    fortnight_indicator = fields.Char(string='Quincena')
    is_history_reverse = fields.Boolean(string='Es Historico para Reversar')
    is_deduction = fields.Boolean(string='Es Deduccion')
    pending_review = fields.Boolean(string='Pendiente de Revision')
    reviewed = fields.Boolean(string='Revisado')
    double_payment = fields.Boolean(string='Pago Doble')
    discount_suspensions = fields.Boolean(string='Desconto Suspensiones')

    # Ajustes manuales
    manual_adjustment = fields.Boolean(string='Ajuste Manual')
    original_amount = fields.Float(string='Monto Original')
    adjustment_reason = fields.Text(string='Razon del Ajuste')
    adjusted_by = fields.Many2one('res.users', string='Ajustado por')
    adjustment_date = fields.Datetime(string='Fecha de Ajuste')

    # Datos de computacion
    formula_used = fields.Text(string='Formula Utilizada')
    computation = fields.Text('Datos de Computacion')
    log_compute = fields.Html('Log de Computacion')
    calculation_method = fields.Char(string='Metodo de Calculo')

    # Relaciones Many2many para trazabilidad
    accounting_line_ids = fields.Many2many(
        'account.move.line',
        'hr_payslip_line_accounting_rel',
        'payslip_line_id',
        'accounting_line_id',
        string='Lineas Contables Relacionadas'
    )
    accumulated_line_ids = fields.Many2many(
        'hr.payslip.line',
        'hr_payslip_line_accumulated_rel',
        'current_line_id',
        'accumulated_line_id',
        string='Lineas de Nomina Acumuladas'
    )
    accumulated_payroll_ids = fields.One2many(
        'hr.accumulated.payroll',
        'origin_payslip_line_id',
        string='Acumulados Generados'
    )
    accumulated_payroll_consulted_ids = fields.Many2many(
        'hr.accumulated.payroll',
        'hr_payslip_line_accumulated_payroll_rel',
        'payslip_line_id',
        'accumulated_payroll_id',
        string='Acumulados Consultados'
    )
    source_rule_ids = fields.Many2many(
        'hr.salary.rule',
        'hr_payslip_line_source_rule_rel',
        'payslip_line_id',
        'source_rule_id',
        string='Reglas de Origen del Calculo'
    )

    # ======================================================================
    # CAMPOS DE IBC - Ingreso Base de Cotizacion
    # ======================================================================

    ibc_daily = fields.Float(string='IBC Diario', digits=(18, 2))
    ibc_base = fields.Float(string='Base IBC Mensual', digits=(18, 2))
    ibc_previous_month = fields.Float(string='IBC Mes Anterior', digits=(18, 2))
    ibc_original = fields.Float(string='IBC Original Mes Anterior', digits=(18, 2))
    valor_pagado_diario = fields.Float(string='Valor Pagado Diario', digits=(18, 2))
    valor_pagado_mensual = fields.Float(string='Valor Pagado Mensual', digits=(18, 2))

    base_type = fields.Selection([
        ('ibc', 'IBC Mes Anterior'),
        ('valor_pagado', 'Valor Pagado Mes Anterior'),
        ('wage', 'Sueldo Actual'),
        ('smmlv', 'SMMLV'),
        ('year', 'Promedio Ano'),
        ('forced', 'Forzado'),
    ], string='Tipo Base')

    show_both_values = fields.Boolean(
        string='Mostrar Ambos Valores',
        compute='_compute_show_both_values',
        store=True
    )
    limite_minimo_aplicado = fields.Boolean(string='Limite Minimo Aplicado')
    valor_minimo_legal = fields.Float(string='Valor Minimo Legal', digits=(18, 2))

    # ======================================================================
    # CAMPOS COMPUTADOS
    # ======================================================================

    total_devengo = fields.Monetary(
        string='TV',
        compute='_compute_amounts_by_type',
        store=True,
        aggregator='sum'
    )
    total_deduccion = fields.Monetary(
        string='TD',
        compute='_compute_amounts_by_type',
        store=True,
        aggregator='sum'
    )
    net_amount = fields.Monetary(
        string='NET',
        compute='_compute_amounts_by_type',
        store=True,
        aggregator='sum'
    )
    html_display = fields.Html(
        string='Detalle Visual',
        compute='_compute_html_display',
        store=False
    )

    # ======================================================================
    # METODOS COMPUTE
    # ======================================================================

    @api.depends('ibc_base', 'valor_pagado_mensual', 'ibc_previous_month')
    def _compute_show_both_values(self):
        for record in self:
            if record.ibc_previous_month and record.valor_pagado_mensual:
                diferencia = abs(record.ibc_previous_month - record.valor_pagado_mensual)
                porcentaje = (diferencia / record.ibc_previous_month * 100) if record.ibc_previous_month > 0 else 0
                record.show_both_values = porcentaje > 1.0
            else:
                record.show_both_values = False

    @api.depends('total', 'dev_or_ded', 'afecta_totales_effective')
    def _compute_amounts_by_type(self):
        for record in self:
            afecta = record.afecta_totales_effective or record.dev_or_ded
            if afecta == 'devengo':
                record.total_devengo = record.total
                record.total_deduccion = 0
            elif afecta == 'deduccion':
                record.total_devengo = 0
                record.total_deduccion = abs(record.total)
            else:
                record.total_devengo = 0
                record.total_deduccion = 0
            record.net_amount = record.total_devengo - record.total_deduccion

    @api.depends('salary_rule_id', 'salary_rule_id.afecta_totales', 'salary_rule_id.category_id', 'salary_rule_id.category_id.parent_id')
    def _compute_afecta_totales_effective(self):
        for record in self:
            rule = record.salary_rule_id
            if not rule:
                record.afecta_totales_effective = 'ninguno'
                continue
            record.afecta_totales_effective = rule._get_afecta_totales_effective()

    def _compute_html_display(self):
        for record in self:
            record.html_display = '<span>%s: $%s</span>' % (record.name, '{:,.0f}'.format(record.total or 0))

    @api.depends('quantity', 'amount', 'rate', 'subtotal')
    def _compute_total(self):
        for line in self:
            if line.subtotal != 0.0:
                line.total = line.subtotal
            else:
                line.total = float(line.quantity) * line.amount * line.rate / 100

    # ======================================================================
    # METODOS CREATE
    # ======================================================================

    @api.model_create_multi
    def create(self, vals_list):
        has_contract_field = 'contract_id' in self._fields
        for values in vals_list:
            needs_employee = 'employee_id' not in values or not values.get('employee_id')
            needs_contract = has_contract_field and ('contract_id' not in values or not values.get('contract_id'))
            if needs_employee or needs_contract:
                payslip = self.env['hr.payslip'].browse(values.get('slip_id'))
                values['employee_id'] = values.get('employee_id') or payslip.employee_id.id
                if has_contract_field:
                    values['contract_id'] = values.get('contract_id') or (
                        payslip.contract_id and payslip.contract_id.id
                    )
                if has_contract_field and not values['contract_id']:
                    raise UserError(_('Debe establecer un contrato para crear una linea de nomina.'))

            contract_id = values.get('contract_id')
            if not contract_id and values.get('slip_id'):
                payslip = self.env['hr.payslip'].browse(values.get('slip_id'))
                contract_id = payslip.contract_id.id if payslip.contract_id else False

            if 'technical_key' not in values and values.get('code') and contract_id:
                values['technical_key'] = "%s-%s-%s" % (
                    values.get('code'),
                    contract_id,
                    values.get('slip_id')
                )

            if 'object_type' not in values:
                if values.get('leave_id'):
                    if values.get('vacation_leave_id') or (values.get('code') and 'VAC' in values.get('code')):
                        values['object_type'] = 'vacation'
                    else:
                        values['object_type'] = 'absence'
                elif values.get('loan_id'):
                    values['object_type'] = 'loan'
                elif values.get('concept_id'):
                    values['object_type'] = 'novelty'
                elif values.get('code'):
                    code = values.get('code')
                    if 'PRIMA' in code:
                        values['object_type'] = 'prima'
                    elif 'CES' in code:
                        values['object_type'] = 'cesantias'
                    elif 'INTCES' in code:
                        values['object_type'] = 'int_cesantias'
                    elif 'PROV' in code:
                        values['object_type'] = 'provision'
                    else:
                        values['object_type'] = 'regular'

            if 'total' not in values and all(k in values for k in ('amount', 'quantity', 'rate')):
                values['total'] = values['amount'] * values['quantity'] * values['rate'] / 100.0

            if 'subtotal' not in values and 'total' in values:
                values['subtotal'] = values['total']

            if 'display_type' not in values:
                values['display_type'] = 'normal'

        lines = super().create(vals_list)

        for line in lines:
            if line.leave_id and line.salary_rule_id:
                leave_line = self.env['hr.leave.line'].search([
                    ('leave_id', '=', line.leave_id.id),
                    ('payslip_id', '=', line.slip_id.id),
                    ('rule_id', '=', line.salary_rule_id.id)
                ], limit=1)
                try:
                    line._calcular_valores_base_ausencia(leave_line=leave_line)
                except Exception as e:
                    _logger.warning("Error calculando valores base para linea %s: %s", line.id, str(e))

        return lines

    # ======================================================================
    # METODOS DE AUSENCIAS E IBC
    # ======================================================================

    def _get_leave_line(self):
        """Obtiene la linea de ausencia relacionada."""
        if not self.leave_id or not self.salary_rule_id:
            return False
        return self.env['hr.leave.line'].search([
            ('leave_id', '=', self.leave_id.id),
            ('payslip_id', '=', self.slip_id.id),
            ('rule_id', '=', self.salary_rule_id.id)
        ], limit=1)

    def _get_previous_month_ibd_total(self, ref_date):
        """Retorna la suma de IBD del mes anterior para el contrato de la línea."""
        if not self.contract_id or not ref_date:
            return 0.0

        month_start = ref_date.replace(day=1)
        prev_month_start = month_start - relativedelta(months=1)
        prev_month_end = month_start - timedelta(days=1)

        ibd_lines = self.env['hr.payslip.line'].search([
            ('slip_id.contract_id', '=', self.contract_id.id),
            ('slip_id.state', 'in', ['done', 'paid']),
            ('slip_id.date_from', '>=', prev_month_start),
            ('slip_id.date_to', '<=', prev_month_end),
            ('code', '=', 'IBD'),
        ])
        return sum(ibd_lines.mapped('total'))

    def _calcular_valores_base_ausencia(self, leave_line=None):
        """Calcula valores de IBC para linea de ausencia."""
        if not self.contract_id or not self.salary_rule_id:
            return

        if not leave_line:
            leave_line = self._get_leave_line()

        contract = self.contract_id
        rule = self.salary_rule_id
        ref_date = self.date_from or date.today()

        annual_params = self.env['hr.annual.parameters'].get_for_year(
            ref_date.year,
            company_id=(contract.company_id.id if contract.company_id else self.env.company.id),
            raise_if_not_found=False,
        )

        smmlv_monthly = annual_params.smmlv_monthly if annual_params else 0
        valor_minimo_diario = smmlv_monthly / 30.0 if smmlv_monthly > 0 else 0

        if rule.liquidar_con_base:
            ibc_previous_month = self._get_previous_month_ibd_total(ref_date)
            if ibc_previous_month > 0:
                self.ibc_previous_month = ibc_previous_month
                self.ibc_original = ibc_previous_month
                self.ibc_base = ibc_previous_month
                self.ibc_daily = ibc_previous_month / 30.0
                self.base_type = 'ibc_previous_month'
                self.valor_pagado_diario = contract.wage / 30.0 if contract else 0.0
                self.valor_pagado_mensual = self.valor_pagado_diario * 30.0
                self.limite_minimo_aplicado = self.ibc_daily >= valor_minimo_diario
                self.valor_minimo_legal = valor_minimo_diario
                return

        if leave_line and leave_line.ibc_day:
            self.ibc_daily = leave_line.ibc_day or 0.0
            self.ibc_base = leave_line.ibc_base or 0.0
            self.ibc_previous_month = leave_line.ibc_original or 0.0
            self.ibc_original = leave_line.ibc_original or 0.0
            self.base_type = leave_line.base_type or 'wage'

            if not self.valor_pagado_diario:
                self.valor_pagado_diario = contract.wage / 30.0 if contract else 0.0
                self.valor_pagado_mensual = self.valor_pagado_diario * 30.0
        else:
            base_daily = contract.wage / 30.0 if contract else 0.0

            if rule.liquidar_con_base:
                self.ibc_daily = base_daily
                self.ibc_base = base_daily * 30.0
                self.ibc_previous_month = base_daily * 30.0
                self.ibc_original = base_daily * 30.0
                self.valor_pagado_diario = base_daily
                self.valor_pagado_mensual = base_daily * 30.0
                self.base_type = 'ibc'
                self.limite_minimo_aplicado = base_daily >= valor_minimo_diario
                self.valor_minimo_legal = valor_minimo_diario
            else:
                self.ibc_daily = base_daily
                self.ibc_base = contract.wage
                self.ibc_previous_month = 0.0
                self.ibc_original = 0.0
                self.valor_pagado_diario = base_daily
                self.valor_pagado_mensual = contract.wage
                self.base_type = 'wage'
                self.limite_minimo_aplicado = False
                self.valor_minimo_legal = valor_minimo_diario

    # ======================================================================
    # METODOS UTILITARIOS
    # ======================================================================

    def get_payslip_styling_dict(self):
        """Define estilos para lineas especificas en reportes."""
        return {
            'NET': {'line_style': 'color:#875A7B;', 'line_class': 'o_total o_border_bottom fw-bold'},
            'GROSS': {'line_style': 'color:#00A09D;', 'line_class': 'o_subtotal o_border_bottom'},
            'BASIC': {'line_style': 'color:#00A09D;', 'line_class': 'o_subtotal o_border_bottom'},
            'TOTAL': {'line_style': 'color:#875A7B;', 'line_class': 'o_total o_border_bottom fw-bold'},
            'TOTDED': {'line_style': 'color:#FF0000;', 'line_class': 'o_subtotal o_border_bottom'},
        }

    def count_category_ids(self):
        """Cuenta lineas con misma categoria en la nomina."""
        return self.env['hr.payslip.line'].search_count([
            ('slip_id', '=', self.slip_id.id),
            ('category_id', '=', self.category_id.id)
        ])

    def get_computation_data(self):
        """Recupera JSON de computation como diccionario."""
        if self.computation:
            try:
                return json.loads(self.computation)
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}

    def action_open_payslip(self):
        """Abre la nomina relacionada."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Nomina'),
            'res_model': 'hr.payslip',
            'res_id': self.slip_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_visual_widget(self):
        """Abre la vista de widget visual interactivo."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Detalle Visual - %s' % self.name,
            'res_model': 'hr.payslip.line',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref('lavish_hr_payroll.view_hr_payslip_line_form_widget').id,
            'target': 'new',
            'context': {'form_view_initial_mode': 'readonly'},
        }

    # ======================================================================
    # API PARA WIDGET DE FORMULA - CRITERIOS IBC
    # ======================================================================

    @api.model
    def get_ibc_criteria_data(self, line_id):
        """Retorna criterios de IBC para widget JS."""
        line = self.browse(line_id)
        if not line.exists():
            return {'error': 'Linea no encontrada'}

        rule = line.salary_rule_id
        slip = line.slip_id

        novelty = None
        novelty_name = None
        if line.leave_id and line.leave_id.holiday_status_id:
            novelty = line.leave_id.holiday_status_id.novelty
            novelty_name = dict(line.leave_id.holiday_status_id._fields['novelty'].selection).get(novelty, novelty)

        ibc_criteria = self._get_line_ibc_criteria(line, rule, novelty, novelty_name)
        bases_aplicables = self._get_bases_aplicables(rule)
        kpis = self._get_line_kpis(line, slip)
        related_lines = self._get_related_ibc_lines(slip)

        return {
            'line_info': {
                'id': line.id,
                'code': line.code,
                'name': line.name,
                'total': line.total,
                'quantity': line.quantity,
                'amount': line.amount,
                'category_code': line.category_code,
                'dev_or_ded': line.dev_or_ded,
                'object_type': line.object_type,
            },
            'ibc_criteria': ibc_criteria,
            'bases_aplicables': bases_aplicables,
            'kpis': kpis,
            'related_lines': related_lines,
            'novelty_info': {
                'has_novelty': bool(novelty),
                'novelty_code': novelty,
                'novelty_name': novelty_name,
                'leave_id': line.leave_id.id if line.leave_id else None,
                'leave_name': line.leave_id.display_name if line.leave_id else None,
            } if novelty else None,
        }

    def _get_line_ibc_criteria(self, line, rule, novelty, novelty_name):
        """Determina criterio IBC para una linea."""
        cat_code = line.category_code or ''
        parent_cat_code = rule.category_id.parent_id.code if rule.category_id and rule.category_id.parent_id else ''
        novelty_excluidos_40 = ['sln', 'ige', 'irl', 'lma', 'lpa', 'vco', 'vdi', 'vre']

        company = line.company_id or self.env.company
        include_absences_1393 = getattr(company, 'include_absences_1393', False)

        result = {
            'aplica_ibc': False,
            'criterio': 'Sin determinar',
            'referencia_legal': '',
            'color': 'gray',
            'explicacion': '',
            'tipo_base': 'N/A',
        }

        if novelty:
            if novelty in novelty_excluidos_40:
                criteria_map = {
                    'ige': ('Incapacidad EPS', 'Art. 3.2.1.10 Decreto 780/2016', 'blue', 'Las incapacidades por enfermedad general suman directo al IBC'),
                    'irl': ('Accidente de Trabajo', 'Art. 3.2.1.10 Decreto 780/2016', 'orange', 'Los accidentes de trabajo suman directo al IBC'),
                    'lma': ('Licencia Maternidad', 'Art. 236 CST', 'pink', 'La licencia de maternidad suma directo al IBC'),
                    'sln': ('Licencia No Remunerada', 'Concepto UGPP', 'gray', 'Las licencias no remuneradas NO suman al IBC'),
                }
                if novelty in criteria_map:
                    c = criteria_map[novelty]
                    result.update({
                        'aplica_ibc': novelty != 'sln',
                        'criterio': c[0],
                        'referencia_legal': c[1],
                        'color': c[2],
                        'explicacion': c[3],
                        'tipo_base': 'NO_APLICA' if novelty == 'sln' else 'DIRECTO',
                    })
                elif novelty in ('vco', 'vdi', 'vre'):
                    result.update({
                        'aplica_ibc': True,
                        'criterio': 'Vacaciones',
                        'referencia_legal': 'Art. 3.2.1.10 Decreto 780/2016',
                        'color': 'cyan',
                        'explicacion': 'Las vacaciones suman directo al IBC',
                        'tipo_base': 'DIRECTO',
                    })
            else:
                if include_absences_1393:
                    result.update({
                        'aplica_ibc': True,
                        'criterio': novelty_name or novelty,
                        'referencia_legal': 'Ley 1393/2010 Art. 30',
                        'color': 'yellow',
                        'explicacion': 'Esta ausencia participa en el calculo del limite 40%',
                        'tipo_base': 'LIMITE_40',
                    })
                else:
                    result.update({
                        'aplica_ibc': True,
                        'criterio': novelty_name or novelty,
                        'referencia_legal': 'Concepto UGPP 2018',
                        'color': 'blue',
                        'explicacion': 'Segun UGPP, esta ausencia suma directo al IBC',
                        'tipo_base': 'DIRECTO',
                    })

        elif cat_code in ('DEV_SALARIAL', 'BASIC', 'HEYREC', 'COMISIONES') or parent_cat_code == 'DEV_SALARIAL':
            base_ss = getattr(rule, 'base_seguridad_social', False)
            if base_ss:
                result.update({
                    'aplica_ibc': True,
                    'criterio': 'Devengo Salarial',
                    'referencia_legal': 'Art. 127 CST',
                    'color': 'green',
                    'explicacion': 'Los devengos salariales marcados como Base SS suman al IBC',
                    'tipo_base': 'SALARIAL',
                })
            else:
                result.update({
                    'aplica_ibc': False,
                    'criterio': 'Devengo NO marcado Base SS',
                    'referencia_legal': 'Config. Regla Salarial',
                    'color': 'red',
                    'explicacion': 'Este devengo NO esta marcado como Base de Seguridad Social',
                    'tipo_base': 'NO_APLICA',
                })

        elif cat_code == 'DEV_NO_SALARIAL' or parent_cat_code == 'DEV_NO_SALARIAL':
            result.update({
                'aplica_ibc': True,
                'criterio': 'Devengo No Salarial',
                'referencia_legal': 'Ley 1393/2010 Art. 30',
                'color': 'yellow',
                'explicacion': 'Los devengos no salariales estan sujetos al limite del 40%',
                'tipo_base': 'LIMITE_40',
            })

        elif cat_code == 'VACACIONES':
            result.update({
                'aplica_ibc': True,
                'criterio': 'Vacaciones',
                'referencia_legal': 'Art. 3.2.1.10 Decreto 780/2016',
                'color': 'cyan',
                'explicacion': 'Las vacaciones suman directo al IBC',
                'tipo_base': 'DIRECTO',
            })

        elif line.dev_or_ded == 'deduccion':
            result.update({
                'aplica_ibc': False,
                'criterio': 'Deduccion',
                'referencia_legal': 'N/A',
                'color': 'gray',
                'explicacion': 'Las deducciones no afectan el calculo del IBC',
                'tipo_base': 'NO_APLICA',
            })

        else:
            base_ss = getattr(rule, 'base_seguridad_social', False)
            if base_ss:
                result.update({
                    'aplica_ibc': True,
                    'criterio': 'Marcado Base SS',
                    'referencia_legal': 'Config. Regla Salarial',
                    'color': 'green',
                    'explicacion': 'Este concepto esta marcado como Base de Seguridad Social',
                    'tipo_base': 'SALARIAL',
                })
            else:
                result.update({
                    'aplica_ibc': False,
                    'criterio': 'NO marcado Base SS',
                    'referencia_legal': 'Config. Regla Salarial',
                    'color': 'gray',
                    'explicacion': 'Este concepto NO esta marcado como Base de Seguridad Social',
                    'tipo_base': 'NO_APLICA',
                })

        return result

    def _get_bases_aplicables(self, rule):
        """Retorna bases aplicables para la regla."""
        bases_config = [
            ('SS', 'Seguridad Social', 'base_seguridad_social', 'green'),
            ('PARA', 'Parafiscales', 'base_parafiscales', 'green'),
            ('PRIMA', 'Prima', 'base_prima', 'blue'),
            ('CES', 'Cesantias', 'base_cesantias', 'blue'),
            ('VAC', 'Vacaciones', 'base_vacaciones', 'cyan'),
            ('INT', 'Int. Cesantias', 'base_intereses_cesantias', 'blue'),
        ]
        return [
            {
                'code': code,
                'name': name,
                'aplica': getattr(rule, attr, False),
                'color': color if getattr(rule, attr, False) else 'gray'
            }
            for code, name, attr, color in bases_config
        ]

    def _get_line_kpis(self, line, slip):
        """Retorna KPIs para la linea."""
        kpis = [{
            'id': 'total',
            'label': 'Total',
            'value': line.total,
            'format': 'currency',
            'color': 'primary',
            'icon': 'fa-dollar-sign',
        }]

        if line.quantity and line.quantity != 1:
            kpis.append({
                'id': 'quantity',
                'label': 'Dias' if line.object_type == 'absence' else 'Cantidad',
                'value': line.quantity,
                'format': 'number',
                'color': 'info',
                'icon': 'fa-calendar-day' if line.object_type == 'absence' else 'fa-hashtag',
            })

        if slip and slip.line_ids:
            total_devengos = sum(
                l.total for l in slip.line_ids
                if l.afecta_totales_effective == 'devengo' and l.total > 0
            )
            if total_devengos > 0 and line.total > 0:
                kpis.append({
                    'id': 'percentage',
                    'label': '% Nomina',
                    'value': round((line.total / total_devengos) * 100, 1),
                    'format': 'percent',
                    'color': 'secondary',
                    'icon': 'fa-percent',
                })

        if line.ibc_daily and line.ibc_daily > 0:
            kpis.append({
                'id': 'ibc_daily',
                'label': 'IBC Diario',
                'value': line.ibc_daily,
                'format': 'currency',
                'color': 'success',
                'icon': 'fa-calendar-check',
            })

        return kpis

    def _get_related_ibc_lines(self, slip):
        """Retorna lineas relacionadas que afectan el IBC."""
        if not slip:
            return []

        related = []
        for ibd in slip.line_ids.filtered(lambda l: l.code in ('IBD', 'IBC_R')):
            related.append({
                'id': ibd.id,
                'code': ibd.code,
                'name': ibd.name,
                'total': ibd.total,
                'tipo': 'IBC',
                'color': 'primary',
            })

        for ss in slip.line_ids.filtered(lambda l: l.code and l.code.startswith('SSOCIAL'))[:5]:
            related.append({
                'id': ss.id,
                'code': ss.code,
                'name': ss.name,
                'total': ss.total,
                'tipo': 'SS',
                'color': 'info',
            })

        return related

    # ======================================================================
    # API PARA WIDGET - INFORMACION CONTEXTUAL
    # ======================================================================

    @api.model
    def get_contextual_info(self, line_id):
        """
        Retorna informacion contextual para el widget segun el tipo de linea.
        - Prestamos: pagado, pendiente, cuotas, fecha fin
        - Novedades contrato: tipo, saltos, pago doble
        - Ausencias: fechas, dias, regreso
        - Vacaciones: salida, regreso
        - Otros: KPI basico segun categoria
        """
        line = self.browse(line_id)
        if not line.exists():
            return {'error': 'Linea no encontrada', 'tipo': None}

        result = {
            'tipo': line.object_type,
            'code': line.code,
            'category_code': line.category_code,
            'total': line.total,
            'quantity': line.quantity,
            'dev_or_ded': line.dev_or_ded,
            'liquidar_con_base': line.liquidar_con_base,
            'base_seguridad_social': line.base_seguridad_social,
            'base_prima': line.base_prima,
            'base_cesantias': line.base_cesantias,
            'base_vacaciones': line.base_vacaciones,
            'has_relation': False,
            'relation_type': None,
            'relation_data': {},
            'acciones': [],
            'kpis': [],
            'notas': [],
        }

        # === PRESTAMOS ===
        if line.loan_id:
            result['has_relation'] = True
            result['relation_type'] = 'loan'
            loan = line.loan_id
            installment = line.loan_installment_id

            # Calcular cuota actual
            cuota_actual = 0
            total_cuotas = len(loan.installment_ids)
            if installment:
                cuotas_pagadas = loan.installment_ids.filtered(lambda i: i.state == 'paid')
                cuota_actual = len(cuotas_pagadas) + 1

            result['relation_data'] = {
                'id': loan.id,
                'name': loan.name,
                'loan_type': loan.loan_type,
                'loan_type_label': dict(loan._fields['loan_type'].selection).get(loan.loan_type, loan.loan_type),
                'original_amount': loan.original_amount,
                'total_paid': loan.total_paid,
                'remaining_amount': loan.remaining_amount,
                'pending_installments': loan.pending_installments,
                'total_installments': total_cuotas,
                'cuota_actual': cuota_actual,
                'payment_start_date': loan.payment_start_date.isoformat() if loan.payment_start_date else None,
                'payment_end_date': loan.payment_end_date.isoformat() if loan.payment_end_date else None,
                'apply_interest': loan.apply_interest,
                'interest_rate': loan.interest_rate if loan.apply_interest else 0,
                'deduct_on_settlement': loan.deduct_on_settlement,
                'porcentaje_pagado': round((loan.total_paid / loan.original_amount * 100), 1) if loan.original_amount > 0 else 0,
            }

            # KPIs para prestamo
            result['kpis'] = [
                {'label': 'Cuota', 'value': f"{cuota_actual}/{total_cuotas}", 'icon': 'fa-hashtag', 'color': 'info'},
                {'label': 'Pagado', 'value': loan.total_paid, 'format': 'currency', 'icon': 'fa-check', 'color': 'success'},
                {'label': 'Pendiente', 'value': loan.remaining_amount, 'format': 'currency', 'icon': 'fa-clock-o', 'color': 'warning'},
            ]

            # Notas
            if loan.deduct_on_settlement:
                result['notas'].append({'texto': 'Se deduce saldo en liquidacion', 'icon': 'fa-info-circle', 'color': 'info'})
            if loan.apply_interest:
                result['notas'].append({'texto': f'Tasa interes: {loan.interest_rate}%', 'icon': 'fa-percent', 'color': 'warning'})

        # === NOVEDADES DE CONTRATO ===
        elif line.concept_id:
            result['has_relation'] = True
            result['relation_type'] = 'concept'
            concept = line.concept_id

            # Tipo de deduccion
            type_labels = {
                'P': 'Prestamo Empresa',
                'A': 'Ahorro',
                'S': 'Seguro',
                'L': 'Libranza',
                'E': 'Embargo',
                'R': 'Retencion',
                'O': 'Otros'
            }
            type_emb_labels = {
                'ECA': 'Cuotas Alimentarias',
                'EDJ': 'Deposito Judicial',
                'EI': 'ICETEX',
                'EJ': 'Ejecutivo',
                'O': 'Otros'
            }
            aplicar_labels = {
                '15': '1ra Quincena',
                '30': '2da Quincena',
                '0': 'Ambas Quincenas'
            }

            # Verificar saltos
            skip_info = None
            if line.skip_id:
                skip_info = {
                    'id': line.skip_id.id,
                    'period_skip': line.skip_id.period_skip.isoformat() if line.skip_id.period_skip else None,
                    'period_double': line.skip_id.period_double,
                }

            # Etiquetas de modalidad
            modality_labels = {
                'fijo': 'Valor Fijo',
                'diario': 'Valor Diario',
                'diario_efectivo': 'Diario Efectivo'
            }
            behavior_labels = {
                'equal': 'Mismo valor ambas quincenas',
                'proportional': 'Proporcional a dias',
                'divided': 'Dividido entre quincenas'
            }

            result['relation_data'] = {
                'id': concept.id,
                'name': concept.name,
                'type_deduction': concept.type_deduction,
                'type_deduction_label': type_labels.get(concept.type_deduction, concept.type_deduction or 'N/A'),
                'type_emb': concept.type_emb,
                'type_emb_label': type_emb_labels.get(concept.type_emb, ''),
                'monthly_behavior': concept.monthly_behavior,
                'monthly_behavior_label': behavior_labels.get(concept.monthly_behavior, ''),
                'modality_value': concept.modality_value,
                'modality_label': modality_labels.get(concept.modality_value, ''),
                'aplicar': concept.aplicar,
                'aplicar_label': aplicar_labels.get(concept.aplicar, concept.aplicar),
                'amount': concept.amount,
                'amount_select': concept.amount_select,
                'period': concept.period,
                # Saldos y estadisticas
                'balance': concept.balance,
                'total_paid': concept.total_paid,
                'remaining_installments': concept.remaining_installments,
                'accumulated_amount': concept.accumulated_amount,
                # Fechas
                'date_start': concept.date_start.isoformat() if concept.date_start else None,
                'date_end': concept.date_end.isoformat() if concept.date_end else None,
                # Proyecciones
                'proyectar_nomina': concept.proyectar_nomina,
                'proyectar_seguridad_social': concept.proyectar_seguridad_social,
                'proyectar_retencion': concept.proyectar_retencion,
                'proyectar_prestaciones': concept.proyectar_prestaciones,
                # Control
                'skip_info': skip_info,
                'double_payment': line.double_payment,
                'is_previous_period': line.is_previous_period,
                'force_double_payment': concept.force_double_payment,
            }

            # KPIs segun tipo
            kpis = [{'label': 'Tipo', 'value': type_labels.get(concept.type_deduction, 'Concepto'), 'icon': 'fa-tag', 'color': 'primary'}]

            if concept.type_deduction == 'E' and concept.type_emb:
                kpis.append({'label': 'Embargo', 'value': type_emb_labels.get(concept.type_emb, 'Otro'), 'icon': 'fa-gavel', 'color': 'danger'})

            kpis.append({'label': 'Aplica', 'value': aplicar_labels.get(concept.aplicar, ''), 'icon': 'fa-calendar', 'color': 'info'})

            # KPI de saldo si tiene periodo limitado
            if concept.period == 'limited' and concept.balance:
                kpis.append({'label': 'Saldo', 'value': concept.balance, 'format': 'currency', 'icon': 'fa-balance-scale', 'color': 'warning'})
            if concept.remaining_installments and concept.remaining_installments > 0:
                kpis.append({'label': 'Restantes', 'value': f'{concept.remaining_installments} cuotas', 'icon': 'fa-list-ol', 'color': 'info'})

            result['kpis'] = kpis

            # Acciones y notas
            if line.double_payment:
                result['acciones'].append({'accion': 'PAGO_DOBLE', 'label': 'Pago Doble', 'icon': 'fa-clone', 'color': 'warning', 'descripcion': 'Recuperando cuota saltada anterior'})
            if line.is_previous_period:
                result['notas'].append({'texto': 'Novedad de periodo anterior', 'icon': 'fa-history', 'color': 'info'})
            if skip_info and skip_info.get('period_double'):
                result['notas'].append({'texto': 'Salto con recuperacion doble pendiente', 'icon': 'fa-forward', 'color': 'warning'})
            if concept.modality_value != 'fijo':
                result['notas'].append({'texto': f'Modalidad: {modality_labels.get(concept.modality_value, "")}', 'icon': 'fa-calculator', 'color': 'info'})
            if concept.proyectar_seguridad_social:
                result['notas'].append({'texto': 'Proyecta en Seguridad Social', 'icon': 'fa-shield', 'color': 'success'})

        # === AUSENCIAS ===
        elif line.leave_id and not line.vacation_leave_id:
            result['has_relation'] = True
            result['relation_type'] = 'leave'
            leave = line.leave_id

            # Fecha de regreso (dia siguiente al fin de ausencia)
            fecha_regreso = None
            if leave.date_to:
                fecha_regreso = (leave.date_to + timedelta(days=1)).date() if isinstance(leave.date_to, datetime) else leave.date_to + timedelta(days=1)

            result['relation_data'] = {
                'id': leave.id,
                'name': leave.display_name,
                'leave_type': leave.holiday_status_id.name if leave.holiday_status_id else 'Ausencia',
                'leave_type_code': leave.holiday_status_id.code if leave.holiday_status_id else None,
                'date_from': leave.date_from.isoformat() if leave.date_from else None,
                'date_to': leave.date_to.isoformat() if leave.date_to else None,
                'number_of_days': leave.number_of_days,
                'fecha_regreso': fecha_regreso.isoformat() if fecha_regreso else None,
                'state': leave.state,
                'entity': leave.entity.name if hasattr(leave, 'entity') and leave.entity else None,
            }

            # KPIs
            result['kpis'] = [
                {'label': 'Dias', 'value': leave.number_of_days, 'icon': 'fa-calendar-times-o', 'color': 'warning'},
                {'label': 'Tipo', 'value': leave.holiday_status_id.name if leave.holiday_status_id else 'Ausencia', 'icon': 'fa-medkit', 'color': 'danger'},
            ]

            if fecha_regreso:
                result['notas'].append({'texto': f'Regreso: {fecha_regreso.strftime("%d/%m/%Y") if hasattr(fecha_regreso, "strftime") else fecha_regreso}', 'icon': 'fa-calendar-check-o', 'color': 'success'})

        # === VACACIONES ===
        elif line.vacation_leave_id or line.object_type == 'vacation':
            result['has_relation'] = True
            result['relation_type'] = 'vacation'
            leave = line.vacation_leave_id or line.leave_id

            fecha_salida = line.vacation_departure_date
            fecha_regreso = line.vacation_return_date

            result['relation_data'] = {
                'id': leave.id if leave else None,
                'name': leave.display_name if leave else 'Vacaciones',
                'date_from': leave.date_from.isoformat() if leave and leave.date_from else None,
                'date_to': leave.date_to.isoformat() if leave and leave.date_to else None,
                'number_of_days': leave.number_of_days if leave else line.quantity,
                'vacation_departure_date': fecha_salida.isoformat() if fecha_salida else None,
                'vacation_return_date': fecha_regreso.isoformat() if fecha_regreso else None,
            }

            # KPIs
            result['kpis'] = [
                {'label': 'Dias', 'value': leave.number_of_days if leave else line.quantity, 'icon': 'fa-sun-o', 'color': 'info'},
            ]

            if fecha_salida:
                result['notas'].append({'texto': f'Salida: {fecha_salida.strftime("%d/%m/%Y")}', 'icon': 'fa-sign-out', 'color': 'info'})
            if fecha_regreso:
                result['notas'].append({'texto': f'Regreso: {fecha_regreso.strftime("%d/%m/%Y")}', 'icon': 'fa-sign-in', 'color': 'success'})

        # === LINEAS SIN RELACION - KPIs BASICOS ===
        else:
            result['has_relation'] = False

            # KPIs basicos segun categoria
            cat_code = line.category_code or ''
            cat_type = line.category_type

            if cat_code in ('BASIC', 'BASIC001', 'BASIC002'):
                result['kpis'] = [
                    {'label': 'Salario', 'value': line.total, 'format': 'currency', 'icon': 'fa-money', 'color': 'success'},
                    {'label': 'Dias', 'value': line.quantity, 'icon': 'fa-calendar', 'color': 'info'},
                ]
            elif cat_code in ('HEYREC',) or 'HE_' in (line.code or ''):
                result['kpis'] = [
                    {'label': 'Valor HE', 'value': line.total, 'format': 'currency', 'icon': 'fa-clock-o', 'color': 'primary'},
                    {'label': 'Horas', 'value': line.quantity, 'icon': 'fa-hourglass', 'color': 'info'},
                ]
            elif 'PROV' in (line.code or '') or 'PRV' in (line.code or ''):
                result['kpis'] = [
                    {'label': 'Provision', 'value': line.total, 'format': 'currency', 'icon': 'fa-database', 'color': 'purple'},
                ]
            elif line.dev_or_ded == 'deduccion':
                result['kpis'] = [
                    {'label': 'Deduccion', 'value': abs(line.total), 'format': 'currency', 'icon': 'fa-minus-circle', 'color': 'danger'},
                ]
            else:
                result['kpis'] = [
                    {'label': 'Total', 'value': line.total, 'format': 'currency', 'icon': 'fa-dollar', 'color': 'primary'},
                ]

            # Nota basica
            if line.salary_rule_id and line.salary_rule_id.note:
                result['notas'].append({'texto': line.salary_rule_id.note, 'icon': 'fa-info-circle', 'color': 'muted'})

        return result
