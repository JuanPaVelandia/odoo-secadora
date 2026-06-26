# -*- coding: utf-8 -*-

"""
PRESTACIONES SOCIALES - CONSOLIDACIÓN
======================================
Reglas de consolidación para ajuste contable exacto al momento de corte del lote.

Cada concepto consolidable (vacaciones, cesantías, intereses de cesantías) tiene
una regla de consolidación que calcula el ajuste contable exacto comparando:
- Saldo de cuenta de provisión (ej: 26XX obligaciones laborales)
- Saldo de cuenta de consolidación (ej: 25XX pasivos por pagar)
- Diferencia = Ajuste necesario

Las cuentas son configurables en Ajustes > Nómina > Consolidación de Prestaciones
"""

import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import date

_logger = logging.getLogger(__name__)


class HrSalaryRulePrestacionesConsolidacion(models.AbstractModel):
    """Reglas de consolidación para prestaciones sociales"""
    
    _name = 'hr.salary.rule.prestaciones.consolidacion'
    _inherit = 'hr.salary.rule.prestaciones'
    _description = 'Reglas de Consolidación de Prestaciones Sociales'

    # =========================================================================
    # CONFIGURACIÓN DE CONCEPTOS CONSOLIDABLES
    # =========================================================================
    
    CONCEPTOS_CONSOLIDABLES = {
        'cesantias': {
            'codigo_regla': 'CESANTIAS_CONS',
            'codigo_provision': 'PRVCESANTIAS',
            'param_provision': 'lavish_hr_payroll.cuenta_provision_cesantias_id',
            'param_consolidacion': 'lavish_hr_payroll.cuenta_consolidacion_cesantias_id',
            'nombre': 'Consolidación Cesantías',
            'tipo_prestacion': 'cesantias',
        },
        'intereses': {
            'codigo_regla': 'INTCESANTIAS_CONS',
            'codigo_provision': 'PRVINTCESANTIAS',
            'param_provision': 'lavish_hr_payroll.cuenta_provision_intereses_id',
            'param_consolidacion': 'lavish_hr_payroll.cuenta_consolidacion_intereses_id',
            'nombre': 'Consolidación Intereses de Cesantías',
            'tipo_prestacion': 'intereses_cesantias',
        },
        'vacaciones': {
            'codigo_regla': 'VACACIONES_CONS',
            'codigo_provision': 'PRVVACACIONES',
            'param_provision': 'lavish_hr_payroll.cuenta_provision_vacaciones_id',
            'param_consolidacion': 'lavish_hr_payroll.cuenta_consolidacion_vacaciones_id',
            'nombre': 'Consolidación Vacaciones',
            'tipo_prestacion': 'vacaciones',
        },
    }

    # =========================================================================
    # HOOKS - Métodos extensibles para personalizar comportamiento
    # =========================================================================

    def _hook_validar_concepto(self, localdict, concepto):
        """
        Hook para validar si un concepto debe procesarse.
        
        Override este método para agregar validaciones personalizadas.
        
        Args:
            localdict: Diccionario de contexto
            concepto: 'cesantias', 'intereses', 'vacaciones', 'gasto_festivo'
            
        Returns:
            tuple: (aplica: bool, motivo: str)
        """
        slip = localdict.get('slip')
        contract = localdict.get('contract')
        
        if not slip or not contract:
            return False, 'Sin slip o contrato'
        
        return True, ''

    def _hook_antes_calcular_ajuste(self, localdict, concepto, date_from, date_to):
        """
        Hook ejecutado ANTES de calcular el ajuste de consolidación.
        
        Override para modificar parámetros o agregar lógica previa.
        
        Args:
            localdict: Diccionario de contexto
            concepto: Tipo de concepto
            date_from: Fecha inicio período
            date_to: Fecha fin período
            
        Returns:
            dict: Datos adicionales para el cálculo
        """
        return {}

    def _hook_despues_calcular_ajuste(self, localdict, concepto, resultado):
        """
        Hook ejecutado DESPUÉS de calcular el ajuste.
        
        Override para modificar el resultado o agregar lógica posterior.
        
        Args:
            localdict: Diccionario de contexto
            concepto: Tipo de concepto
            resultado: Dict con resultado del cálculo
            
        Returns:
            dict: Resultado modificado
        """
        return resultado

    def _hook_calcular_diferencia_gasto(self, localdict, concepto, resultado):
        """
        Hook para calcular la diferencia como gasto.
        
        Se usa cuando hay diferencia entre provisión y obligación
        que debe ir a gasto del período.
        
        Args:
            localdict: Diccionario de contexto
            concepto: Tipo de concepto
            resultado: Dict con resultado del cálculo
            
        Returns:
            float: Valor del gasto a registrar
        """
        ajuste = resultado.get('ajuste', 0.0)
        
        # Si la provisión es mayor que la obligación, la diferencia va a gasto
        if ajuste > 0:
            return ajuste
        
        return 0.0

    def _hook_obtener_cuenta_gasto(self, concepto):
        """
        Hook para obtener la cuenta de gasto según el concepto.
        
        Override para personalizar las cuentas de gasto.
        
        Args:
            concepto: Tipo de concepto
            
        Returns:
            str: Código PUC de la cuenta de gasto
        """
        # Cuentas de gasto por defecto (PUC Colombia - Clase 5)
        cuentas_gasto = {
            'cesantias': '510568',       # Gasto cesantías
            'intereses': '510569',       # Gasto intereses cesantías
            'vacaciones': '510536',      # Gasto vacaciones
            'gasto_festivo': '510536',   # Gasto vacaciones (festivos)
        }
        return cuentas_gasto.get(concepto, '5105')

    # =========================================================================
    # HOOKS DE CONTABILIZACIÓN - Para ajustar cuentas contables dinámicamente
    # =========================================================================

    def _hook_get_cuentas_contabilizacion(self, concepto, slip=None):
        """
        Hook para obtener cuentas de contabilización según concepto.
        
        Permite personalizar las cuentas contables para cada concepto
        antes de generar el asiento contable.
        
        Args:
            concepto: 'cesantias', 'intereses', 'vacaciones', 'gasto_festivo'
            slip: hr.payslip opcional para contexto
            
        Returns:
            dict: {
                'cuenta_debito': account.account,
                'cuenta_credito': account.account,
                'tercero_debito': str,  # 'empleado', 'entidad', 'compania'
                'tercero_credito': str,
            }
        """
        config = self.CONCEPTOS_CONSOLIDABLES.get(concepto, {})
        
        # Obtener cuentas configuradas
        cuenta_provision = self._get_cuenta_config(config.get('param_provision', ''))
        cuenta_consolidacion = self._get_cuenta_config(config.get('param_consolidacion', ''))
        
        # Para consolidación: D:Obligación(25XX) C:Provisión(26XX)
        # Para gasto festivo: D:Provisión(26XX) C:Obligación(25XX)
        if concepto == 'gasto_festivo':
            return {
                'cuenta_debito': cuenta_provision,
                'cuenta_credito': cuenta_consolidacion,
                'tercero_debito': 'compania',
                'tercero_credito': 'compania',
            }
        else:
            return {
                'cuenta_debito': cuenta_consolidacion,
                'cuenta_credito': cuenta_provision,
                'tercero_debito': 'empleado',
                'tercero_credito': 'compania',
            }

    def _hook_validar_contabilizacion(self, concepto, slip, ajuste):
        """
        Hook para validar antes de contabilizar.
        
        Override para agregar validaciones personalizadas.
        
        Args:
            concepto: Tipo de concepto
            slip: hr.payslip
            ajuste: Valor del ajuste a contabilizar
            
        Returns:
            tuple: (valido: bool, mensaje: str)
        """
        if not ajuste or ajuste == 0:
            return False, 'Ajuste es cero, no hay que contabilizar'
        
        cuentas = self._hook_get_cuentas_contabilizacion(concepto, slip)
        
        if not cuentas.get('cuenta_debito'):
            return False, f'No hay cuenta de débito configurada para {concepto}'
        
        if not cuentas.get('cuenta_credito'):
            return False, f'No hay cuenta de crédito configurada para {concepto}'
        
        return True, ''

    def _hook_prepare_account_move_line(self, concepto, slip, ajuste, is_debit=True):
        """
        Hook para preparar línea de asiento contable.
        
        Retorna dict con valores para crear account.move.line.
        
        Args:
            concepto: Tipo de concepto
            slip: hr.payslip
            ajuste: Valor del ajuste
            is_debit: True para débito, False para crédito
            
        Returns:
            dict: Valores para account.move.line
        """
        cuentas = self._hook_get_cuentas_contabilizacion(concepto, slip)
        
        if is_debit:
            cuenta = cuentas.get('cuenta_debito')
            tercero_tipo = cuentas.get('tercero_debito', 'compania')
        else:
            cuenta = cuentas.get('cuenta_credito')
            tercero_tipo = cuentas.get('tercero_credito', 'compania')
        
        # Determinar partner
        partner_id = self._hook_get_partner_contabilizacion(slip, tercero_tipo)
        
        return {
            'account_id': cuenta.id if cuenta else False,
            'partner_id': partner_id,
            'name': self._hook_get_descripcion_linea(concepto, slip, is_debit),
            'debit': abs(ajuste) if is_debit and ajuste > 0 else 0,
            'credit': abs(ajuste) if not is_debit and ajuste > 0 else 0,
        }

    def _hook_get_partner_contabilizacion(self, slip, tercero_tipo):
        """
        Hook para obtener partner según tipo de tercero.
        
        Args:
            slip: hr.payslip
            tercero_tipo: 'empleado', 'entidad', 'compania'
            
        Returns:
            int: ID del partner
        """
        if tercero_tipo == 'empleado':
            return (slip.employee_id.work_contact_id or slip.employee_id.user_id.partner_id).id if (slip.employee_id.work_contact_id or slip.employee_id.user_id.partner_id) else False
        elif tercero_tipo == 'compania':
            return slip.company_id.partner_id.id if slip.company_id.partner_id else False
        return False

    def _hook_get_descripcion_linea(self, concepto, slip, is_debit):
        """
        Hook para obtener descripción de línea contable.
        
        Args:
            concepto: Tipo de concepto
            slip: hr.payslip
            is_debit: True para débito
            
        Returns:
            str: Descripción de la línea
        """
        nombres = {
            'cesantias': 'Consolidación Cesantías',
            'intereses': 'Consolidación Int. Cesantías',
            'vacaciones': 'Consolidación Vacaciones',
            'gasto_festivo': 'Ajuste Gasto Festivo Vacaciones',
        }
        
        nombre_concepto = nombres.get(concepto, concepto)
        tipo = 'Débito' if is_debit else 'Crédito'
        empleado = slip.employee_id.name if slip.employee_id else ''
        
        return f"{nombre_concepto} - {empleado}"

    def _hook_after_contabilizacion(self, concepto, slip, move_lines, resultado):
        """
        Hook ejecutado después de crear líneas contables.
        
        Override para agregar lógica post-contabilización.
        
        Args:
            concepto: Tipo de concepto
            slip: hr.payslip
            move_lines: Lista de account.move.line creadas
            resultado: Dict con resultado del cálculo
        """
        # Por defecto no hace nada, disponible para override
        pass

    def _hook_calcular_festivos(self, localdict, date_from, date_to, dias_vacaciones):
        """
        Hook para calcular días festivos en un período.
        
        Override para personalizar el cálculo de festivos.
        
        Args:
            localdict: Diccionario de contexto
            date_from: Fecha inicio
            date_to: Fecha fin
            dias_vacaciones: Días de vacaciones a considerar
            
        Returns:
            dict: {
                'dias_festivos': int,
                'festivos_360': float,
                'festivos_detalle': list,
            }
        """
        from datetime import timedelta
        
        contract = localdict.get('contract')
        trabaja_sabado = contract.employee_id.sabado if contract and contract.employee_id else False
        
        dias_festivos = 0
        festivos_detalle = []
        max_dias = min(int(dias_vacaciones * 2), 90)
        dias_contados = 0
        
        for i in range(max_dias):
            if dias_contados >= dias_vacaciones:
                break
            
            fecha_actual = date_to + timedelta(days=i)
            dia_semana = fecha_actual.weekday()
            
            # Domingo
            if dia_semana == 6:
                dias_festivos += 1
                festivos_detalle.append(f"{fecha_actual.strftime('%d/%m/%Y')} (Domingo)")
                continue
            
            # Sábado
            if dia_semana == 5 and not trabaja_sabado:
                dias_festivos += 1
                festivos_detalle.append(f"{fecha_actual.strftime('%d/%m/%Y')} (Sábado)")
                continue
            
            # Festivo calendario
            es_festivo = self.env['lavish.holidays'].ensure_holidays(fecha_actual)
            if es_festivo:
                festivo_obj = self.env['lavish.holidays'].search([
                    ('date', '=', fecha_actual)
                ], limit=1)
                nombre = festivo_obj.name if festivo_obj else 'Festivo'
                dias_festivos += 1
                festivos_detalle.append(f"{fecha_actual.strftime('%d/%m/%Y')} ({nombre})")
                continue
            
            dias_contados += 1
        
        festivos_360 = dias_festivos / 0.417 if dias_festivos > 0 else 0
        
        return {
            'dias_festivos': dias_festivos,
            'festivos_360': round(festivos_360, 2),
            'festivos_detalle': festivos_detalle,
            'trabaja_sabado': trabaja_sabado,
        }

    # =========================================================================
    # MÉTODO CENTRAL DE CONSOLIDACIÓN (usa hooks)
    # =========================================================================

    def _calcular_consolidacion_concepto(self, localdict, concepto):
        """
        Método central para calcular consolidación de cualquier concepto.
        
        Usa hooks para permitir personalización sin modificar lógica base.
        
        Args:
            localdict: Diccionario de contexto
            concepto: 'cesantias', 'intereses', 'vacaciones'
            
        Returns:
            float: Valor del ajuste
        """
        # 1. Validar si aplica
        aplica, motivo = self._hook_validar_concepto(localdict, concepto)
        if not aplica:
            localdict[f'{concepto.upper()}_CONS_INFO'] = {'aplica': False, 'motivo': motivo}
            return 0.0
        
        slip = localdict.get('slip')
        contract = localdict.get('contract')
        
        # 2. Obtener período
        date_from, date_to = self._get_periodo_prestacion(slip, contract, concepto)
        
        # 3. Hook antes de calcular
        datos_adicionales = self._hook_antes_calcular_ajuste(localdict, concepto, date_from, date_to)
        
        # 4. Calcular ajuste base
        resultado = self._calcular_ajuste_consolidacion(localdict, concepto, date_from, date_to)
        resultado.update(datos_adicionales)
        
        # 5. Hook después de calcular
        resultado = self._hook_despues_calcular_ajuste(localdict, concepto, resultado)
        
        # 6. Calcular diferencia a gasto si aplica
        gasto = self._hook_calcular_diferencia_gasto(localdict, concepto, resultado)
        resultado['gasto'] = gasto
        resultado['cuenta_gasto'] = self._hook_obtener_cuenta_gasto(concepto)
        
        # 7. Guardar info en localdict
        localdict[f'{concepto.upper()}_CONS_INFO'] = resultado
        
        return resultado['ajuste']

    # =========================================================================
    # MÉTODOS AUXILIARES
    # =========================================================================

    def _get_cuenta_config(self, param_key):
        """
        Obtiene una cuenta configurada desde res.config.settings.
        
        Args:
            param_key: Clave del parámetro (ej: 'lavish_hr_payroll.cuenta_provision_cesantias_id')
            
        Returns:
            account.account: Cuenta contable o False
        """
        get_param = self.env['ir.config_parameter'].sudo().get_param
        cuenta_id = get_param(param_key, False)
        if cuenta_id:
            try:
                cuenta_id = int(cuenta_id)
                return self.env['account.account'].browse(cuenta_id).exists()
            except (ValueError, TypeError):
                pass
        return False

    def _get_saldo_cuenta_like(self, prefijo_cuenta, date_to, company_id=None):
        """
        Obtiene el saldo de cuentas que coincidan con un prefijo (LIKE).
        
        Args:
            prefijo_cuenta: Prefijo de cuenta (ej: '2610', '2510', '261005')
            date_to: Fecha de corte
            company_id: ID de la compañía (opcional)
            
        Returns:
            float: Saldo de las cuentas (crédito - débito para pasivos)
        """
        company = company_id or self.env.company
        
        if not prefijo_cuenta:
            return 0.0
        
        # Buscar cuentas que empiecen con el prefijo (multi-empresa)
        AccountAccount = self.env['account.account']
        cuentas = AccountAccount.search([
            ('code', '=like', f'{prefijo_cuenta}%'),
            ('company_ids', 'in', [company.id]),
        ])
        
        if not cuentas:
            _logger.warning(
                "No se encontraron cuentas con prefijo %s para compañía %s",
                prefijo_cuenta, company.name
            )
            return 0.0
        
        # Obtener saldo de todas las cuentas hasta la fecha de corte
        self.env.cr.execute("""
            SELECT 
                COALESCE(SUM(aml.debit), 0) as total_debit,
                COALESCE(SUM(aml.credit), 0) as total_credit
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            WHERE aml.account_id IN %s
              AND aml.date <= %s
              AND am.state = 'posted'
        """, (tuple(cuentas.ids), date_to))
        
        result = self.env.cr.fetchone()
        if result:
            total_debit, total_credit = result
            # Para cuentas de pasivo, el saldo es crédito - débito
            saldo = total_credit - total_debit
            return saldo
        
        return 0.0

    def _get_saldo_cuenta_by_id(self, cuenta, date_to):
        """
        Obtiene el saldo de una cuenta específica por ID.
        
        Args:
            cuenta: Registro account.account
            date_to: Fecha de corte
            
        Returns:
            float: Saldo de la cuenta
        """
        if not cuenta:
            return 0.0
        
        self.env.cr.execute("""
            SELECT 
                COALESCE(SUM(aml.debit), 0) as total_debit,
                COALESCE(SUM(aml.credit), 0) as total_credit
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            WHERE aml.account_id = %s
              AND aml.date <= %s
              AND am.state = 'posted'
        """, (cuenta.id, date_to))
        
        result = self.env.cr.fetchone()
        if result:
            total_debit, total_credit = result
            # Para cuentas de pasivo, saldo = crédito - débito
            return total_credit - total_debit
        
        return 0.0

    def _calcular_ajuste_consolidacion(self, localdict, concepto, date_from, date_to):
        """
        Calcula el ajuste de consolidación para un concepto.
        
        El ajuste es la diferencia entre:
        - Saldo cuenta de PROVISIÓN (26XX - Pasivos estimados): Lo que se ha provisionado
        - Saldo cuenta de CONSOLIDACIÓN (25XX - Obligaciones laborales): Lo que realmente se debe
        
        Ajuste = Provisión (26XX) - Obligación (25XX)
        - Positivo: Hay más provisión de la necesaria (revertir exceso)
        - Negativo: Falta provisión (aumentar provisión)
        
        Args:
            localdict: Diccionario de contexto
            concepto: 'cesantias', 'intereses', 'vacaciones'
            date_from: Fecha inicio del período
            date_to: Fecha fin del período (fecha de corte)
            
        Returns:
            dict: Información del cálculo de consolidación
        """
        config = self.CONCEPTOS_CONSOLIDABLES.get(concepto)
        if not config:
            raise UserError(_("Concepto consolidable '%s' no reconocido") % concepto)
        
        slip = localdict.get('slip')
        company = slip.company_id if slip else self.env.company
        
        # =====================================================================
        # OBTENER CUENTAS CONFIGURADAS O BUSCAR POR PREFIJO
        # =====================================================================
        
        # Cuenta de PROVISIÓN (26XX - ej: 261005 Cesantías)
        cuenta_provision = self._get_cuenta_config(config['param_provision'])
        if cuenta_provision:
            saldo_provision = self._get_saldo_cuenta_by_id(cuenta_provision, date_to)
            codigo_provision = cuenta_provision.code
        else:
            # Fallback: buscar por prefijo PUC estándar
            prefijos_provision = {
                'cesantias': '261005',
                'intereses': '261010',
                'vacaciones': '261015',
            }
            prefijo = prefijos_provision.get(concepto, '2610')
            saldo_provision = self._get_saldo_cuenta_like(prefijo, date_to, company)
            codigo_provision = f'{prefijo}%'
        
        # Cuenta de CONSOLIDACIÓN (25XX - ej: 2510 Cesantías consolidadas)
        cuenta_consolidacion = self._get_cuenta_config(config['param_consolidacion'])
        if cuenta_consolidacion:
            saldo_consolidacion = self._get_saldo_cuenta_by_id(cuenta_consolidacion, date_to)
            codigo_consolidacion = cuenta_consolidacion.code
        else:
            # Fallback: buscar por prefijo PUC estándar
            prefijos_consolidacion = {
                'cesantias': '2510',
                'intereses': '2515',
                'vacaciones': '2525',
            }
            prefijo = prefijos_consolidacion.get(concepto, '25')
            saldo_consolidacion = self._get_saldo_cuenta_like(prefijo, date_to, company)
            codigo_consolidacion = f'{prefijo}%'
        
        # =====================================================================
        # CALCULAR AJUSTE
        # =====================================================================
        # Ajuste = Provisión - Obligación
        # Si Provisión > Obligación: Se provisionó de más (ajuste positivo = revertir)
        # Si Provisión < Obligación: Falta provisión (ajuste negativo = aumentar)
        ajuste = saldo_provision - saldo_consolidacion
        
        return {
            'ajuste': ajuste,
            'saldo_provision': saldo_provision,
            'saldo_consolidacion': saldo_consolidacion,
            'cuenta_provision': codigo_provision,
            'cuenta_consolidacion': codigo_consolidacion,
            'concepto': concepto,
            'config': config,
            'date_from': date_from,
            'date_to': date_to,
        }

    # =========================================================================
    # REGLAS DE CONSOLIDACIÓN POR CONCEPTO (métodos privados)
    # Código regla en mayúsculas, método en minúsculas con _
    # Usan el método central _calcular_consolidacion_concepto con hooks
    # =========================================================================

    def _cesantias_cons(self, localdict):
        """
        Regla de consolidación para Cesantías (código: CESANTIAS_CONS).
        
        Usa el método central con hooks para flexibilidad.
        """
        return self._calcular_consolidacion_concepto(localdict, 'cesantias')

    def _intcesantias_cons(self, localdict):
        """
        Regla de consolidación para Intereses de Cesantías (código: INTCESANTIAS_CONS).
        
        Usa el método central con hooks para flexibilidad.
        """
        return self._calcular_consolidacion_concepto(localdict, 'intereses')

    def _vacaciones_cons(self, localdict):
        """
        Regla de consolidación para Vacaciones (código: VACACIONES_CONS).
        
        Usa el método central con hooks para flexibilidad.
        """
        return self._calcular_consolidacion_concepto(localdict, 'vacaciones')

    def _gasto_festivo(self, localdict):
        """
        Regla de ajuste para Gasto Festivo en Vacaciones (código: GASTO_FESTIVO).
        
        Usa hooks para flexibilidad:
        - _hook_validar_concepto: valida si aplica
        - _hook_calcular_festivos: calcula días festivos
        - _hook_calcular_diferencia_gasto: calcula gasto
        """
        # 1. Validar si aplica usando hook
        aplica, motivo = self._hook_validar_gasto_festivo(localdict)
        if not aplica:
            localdict['GASTO_FESTIVO_INFO'] = {'aplica': False, 'motivo': motivo}
            return 0.0
        
        slip = localdict.get('slip')
        contract = localdict.get('contract')
        
        # 2. Obtener período
        date_from, date_to = self._get_periodo_prestacion(slip, contract, 'vacaciones')
        
        # 3. Obtener días de vacaciones
        dias_vacaciones = self._hook_obtener_dias_vacaciones(localdict, date_from, date_to)
        
        # 4. Calcular festivos usando hook
        festivos_info = self._hook_calcular_festivos(localdict, date_from, date_to, dias_vacaciones)
        
        # 5. Obtener base diaria
        base_diaria = self._hook_obtener_base_diaria_vacaciones(localdict, dias_vacaciones)
        
        # 6. Calcular valor del ajuste por festivos
        festivos_360 = festivos_info.get('festivos_360', 0)
        valor_festivos = base_diaria * festivos_360 / 24 if festivos_360 > 0 else 0
        
        # 7. Comparar con saldo de cuentas
        resultado = self._calcular_ajuste_consolidacion(localdict, 'vacaciones', date_from, date_to)
        
        # 8. Calcular ajuste final usando hook
        ajuste_final = self._hook_calcular_ajuste_festivo(resultado, valor_festivos)
        
        # 9. Guardar información en localdict
        localdict['GASTO_FESTIVO_INFO'] = {
            **resultado,
            **festivos_info,
            'dias_vacaciones': dias_vacaciones,
            'base_diaria': base_diaria,
            'valor_festivos': valor_festivos,
            'ajuste_aplicado': ajuste_final,
            'cuenta_gasto': self._hook_obtener_cuenta_gasto('gasto_festivo'),
        }
        
        return ajuste_final

    # =========================================================================
    # HOOKS ESPECÍFICOS PARA GASTO FESTIVO
    # =========================================================================

    def _hook_validar_gasto_festivo(self, localdict):
        """
        Hook para validar si aplica el cálculo de gasto festivo.
        
        Returns:
            tuple: (aplica: bool, motivo: str)
        """
        slip = localdict.get('slip')
        contract = localdict.get('contract')
        
        if not slip or not contract:
            return False, 'Sin slip o contrato'
        
        # Verificar si aplica: estructura de vacaciones o liquidación
        es_vacaciones = slip.struct_id.process in ('vacaciones', 'contrato')
        
        # Verificar configuración
        integrar_liquidacion = self.env['ir.config_parameter'].sudo().get_param(
            'lavish_hr_payroll.integrar_consolidacion_liquidacion', False
        )
        
        if not es_vacaciones and not integrar_liquidacion:
            return False, 'No es estructura de vacaciones ni integrar liquidación'
        
        return True, ''

    def _hook_obtener_dias_vacaciones(self, localdict, date_from, date_to):
        """
        Hook para obtener días de vacaciones a calcular.
        
        Returns:
            float: Días de vacaciones
        """
        rules = localdict.get('rules', {})
        vacaciones_rule = rules.get('VACCONTRATO') or rules.get('VACDISFRUTADAS')
        
        if vacaciones_rule and vacaciones_rule.quantity:
            return vacaciones_rule.quantity
        
        # Calcular desde período
        from odoo.addons.lavish_hr_employee.models.hr_slip_utils import days360
        dias_periodo = days360(date_from, date_to)
        return dias_periodo / 24

    def _hook_obtener_base_diaria_vacaciones(self, localdict, dias_vacaciones):
        """
        Hook para obtener base diaria de vacaciones.
        
        Returns:
            float: Base diaria
        """
        rules = localdict.get('rules', {})
        vacaciones_rule = rules.get('VACCONTRATO') or rules.get('VACDISFRUTADAS')
        
        if vacaciones_rule and vacaciones_rule.total and dias_vacaciones > 0:
            return vacaciones_rule.total / dias_vacaciones
        
        return 0.0

    def _hook_calcular_ajuste_festivo(self, resultado, valor_festivos):
        """
        Hook para calcular el ajuste final por festivos.
        
        Args:
            resultado: Dict con resultado de consolidación
            valor_festivos: Valor calculado de festivos
            
        Returns:
            float: Ajuste final
        """
        ajuste = resultado.get('ajuste', 0)
        
        # El ajuste es el menor entre la diferencia y el valor de festivos
        if ajuste < 0:
            return min(abs(ajuste), valor_festivos)
        elif ajuste > 0:
            return -min(ajuste, valor_festivos)
        
        return valor_festivos
