# -*- coding: utf-8 -*-

"""
PRESTACIONES SOCIALES - PAGOS
==============================
Prima, cesantías, intereses y retroactivos anuales.
"""

from odoo import models
from .config_reglas import DAYS_YEAR


class HrSalaryRulePrestacionesPagos(models.AbstractModel):
    _inherit = 'hr.salary.rule.prestaciones'

    def _prima(self, localdict):
        """
        PRIMA adaptada de 
        Calcula prima de servicios con lógica de promedio simplificada
        """
        slip = localdict['slip']
        contract = localdict['contract']

        # Usar método centralizado para calcular período
        date_from, date_to = self._get_periodo_prestacion(slip, contract, 'prima')

        resultado = self._compute_social_benefits(
            localdict, date_from, date_to, 'prima', self.descontar_suspensiones
        )

        # Crear/actualizar historial si es liquidacion de contrato
        if isinstance(resultado, tuple):
            base_diaria, days_worked, rate, nombre, vacio, datos = resultado

            # Si rate es 0 (ej: salario integral), no calcular historial
            if rate == 0:
                return resultado

            valor_prima = base_diaria * days_worked / rate
            
            # Obtener valor anterior de prima para comparación
            valores_anteriores_prima = self._get_prestacion_previous_values(contract, 'PRIMA', date_from, date_to)
            diferencia_prima = valor_prima - valores_anteriores_prima['valor_anterior'] if valores_anteriores_prima['valor_anterior'] > 0 else valor_prima
            
            # Agregar información de diferencia a datos
            if datos and 'trazabilidad' in datos:
                datos['trazabilidad']['diferencia_prima'] = diferencia_prima
                datos['trazabilidad']['valor_anterior_prima'] = valores_anteriores_prima['valor_anterior']
                datos['trazabilidad']['valor_actual_prima'] = valor_prima

            # Determinar tipo: settlement (liquidación), normal (primera vez), adjustment (ajuste)
            is_settlement = slip.struct_process == 'contrato' and slip.date_liquidacion

            # Buscar si ya existe un registro previo para este período
            existing_prima = self.env['hr.history.prima'].search([
                ('employee_id', '=', contract.employee_id.id),
                ('contract_id', '=', contract.id),
                ('initial_accrual_date', '=', date_from),
                ('final_accrual_date', '=', date_to),
                ('payslip', '!=', slip.id),  # Diferente nómina
            ], limit=1)

            # Definir tipo
            if is_settlement:
                tipo_prima = 'settlement'
            elif existing_prima:
                tipo_prima = 'adjustment'  # Ya existe, es un ajuste
            else:
                tipo_prima = 'normal'

            # Identificador: Usar fechas + tipo para distinguir
            self._create_update_history(
                slip, contract,
                'hr.history.prima',
                {
                    'bonus_value': valor_prima,  # Campo correcto: bonus_value
                    'note': nombre,
                    'type': tipo_prima,
                },
                date_from, date_to,
                search_fields={
                    'initial_accrual_date': date_from,
                    'final_accrual_date': date_to,
                }
            )

        return resultado



    def _cesantias(self, localdict):
        """
        CESANTÍAS adaptadas de 
        Calcula cesantías con lógica de promedio simplificada
        """
        slip = localdict['slip']
        contract = localdict['contract']

        # Usar método centralizado para calcular período
        date_from, date_to = self._get_periodo_prestacion(slip, contract, 'cesantias')

        resultado = self._compute_social_benefits(
            localdict, date_from, date_to, 'cesantias', self.descontar_suspensiones
        )

        # Crear/actualizar historial si es liquidacion de contrato
        if isinstance(resultado, tuple):
            base_diaria, days_worked, rate, nombre, vacio, datos = resultado

            # Si rate es 0 (ej: salario integral), no calcular historial
            if rate == 0:
                return resultado

            valor_cesantias = base_diaria * days_worked / rate

            # Obtener valor anterior de cesantias para comparacion
            valores_anteriores_cesantias = self._get_prestacion_previous_values(contract, 'CESANTIAS', date_from, date_to)
            diferencia_cesantias = valor_cesantias - valores_anteriores_cesantias['valor_anterior'] if valores_anteriores_cesantias['valor_anterior'] > 0 else valor_cesantias
            
            # Agregar información de diferencia a datos
            if datos and 'trazabilidad' in datos:
                datos['trazabilidad']['diferencia_cesantias'] = diferencia_cesantias
                datos['trazabilidad']['valor_anterior_cesantias'] = valores_anteriores_cesantias['valor_anterior']
                datos['trazabilidad']['valor_actual_cesantias'] = valor_cesantias

            # Determinar tipo
            is_settlement = slip.struct_process == 'contrato' and slip.date_liquidacion

            # Buscar registro previo
            existing_cesantias = self.env['hr.history.cesantias'].search([
                ('employee_id', '=', contract.employee_id.id),
                ('contract_id', '=', contract.id),
                ('initial_accrual_date', '=', date_from),
                ('final_accrual_date', '=', date_to),
                ('payslip', '!=', slip.id),
            ], limit=1)

            # Definir tipo
            if is_settlement:
                tipo_cesantias = 'settlement'
            elif existing_cesantias:
                tipo_cesantias = 'adjustment'
            else:
                tipo_cesantias = 'normal'

            # Crear/actualizar historial
            self._create_update_history(
                slip, contract,
                'hr.history.cesantias',
                {
                    'severance_value': valor_cesantias,  # Campo correcto: severance_value
                    'type_history': 'cesantias',  # Tipo de historial: cesantías
                    'note': nombre,
                    'type': tipo_cesantias,
                },
                date_from, date_to,
                search_fields={
                    'initial_accrual_date': date_from,
                    'final_accrual_date': date_to,
                }
            )

        return resultado



    def _intcesantias(self, localdict):
        """
        INTERESES DE CESANTÍAS adaptados de 
        Calcula intereses (12% anual) sobre cesantías
        """
        slip = localdict['slip']
        contract = localdict['contract']

        # Usar método centralizado para calcular período
        date_from, date_to = self._get_periodo_prestacion(slip, contract, 'intereses')

        resultado = self._compute_social_benefits(
            localdict, date_from, date_to, 'intereses', self.descontar_suspensiones
        )

        # Crear/actualizar historial si es liquidacion de contrato
        if isinstance(resultado, tuple):
            base_diaria, days_worked, rate, nombre, vacio, datos = resultado

            # Si rate es 0 (ej: salario integral), no calcular historial
            if rate == 0:
                return resultado

            # Calcular intereses usando cesantías ya calculadas en la liquidación
            # Fórmula esperada: cesantias * 12% * (dias / 360)
            rules = localdict.get('rules', {})
            ces_rule = rules.get('CESANTIAS') if rules else None
            cesantias_total = abs(ces_rule.total) if ces_rule else 0
            if not cesantias_total:
                # Fallback: usar base calculada si no hay línea de cesantías
                base_mensual = base_diaria * 30
                cesantias_total = base_mensual * days_worked / 360

            factor_dias = (days_worked / 360.0) if days_worked else 0
            valor_intereses = cesantias_total * 0.12 * factor_dias
            amount = (cesantias_total * 0.12 / 360.0) if days_worked else 0

            # Determinar tipo
            is_settlement = slip.struct_process == 'contrato' and slip.date_liquidacion

            # Buscar registro previo (usa el mismo modelo que cesantías)
            existing_intereses = self.env['hr.history.cesantias'].search([
                ('employee_id', '=', contract.employee_id.id),
                ('contract_id', '=', contract.id),
                ('initial_accrual_date', '=', date_from),
                ('final_accrual_date', '=', date_to),
                ('type_history', '=', 'intcesantias'),  # Filtrar por tipo de historial
                ('payslip', '!=', slip.id),
            ], limit=1)

            # Definir tipo
            if is_settlement:
                tipo_intereses = 'settlement'
            elif existing_intereses:
                tipo_intereses = 'adjustment'
            else:
                tipo_intereses = 'normal'

            # Crear/actualizar historial (usa el mismo modelo que cesantías)
            self._create_update_history(
                slip, contract,
                'hr.history.cesantias',  # Usa el mismo modelo que cesantías
                {
                    'severance_interest_value': valor_intereses,  # Campo correcto: severance_interest_value
                    'type_history': 'intcesantias',  # Tipo de historial: intereses de cesantías
                    'note': nombre,
                    'type': tipo_intereses,
                },
                date_from, date_to,
                search_fields={
                    'initial_accrual_date': date_from,
                    'final_accrual_date': date_to,
                    'type_history': 'intcesantias',  # Agregar al search para distinguir de cesantías
                }
            )

            # Ajustar datos visibles para reflejar nueva fórmula
            if datos and isinstance(datos, dict):
                data_kpi = datos.get('data_kpi', {})
                data_kpi.update({
                    'cesantias_proporcionales': cesantias_total,
                    'tasa_interes': 12.0,
                    'formula': f'Cesantias x dias/360 x 12% = {cesantias_total:,.2f} x {days_worked}/360 x 0.12 = {valor_intereses:,.2f}',
                })
                datos['data_kpi'] = data_kpi
                datos['monto_total'] = float(valor_intereses)
                if 'formula_final' in datos:
                    datos['formula_final'] = f'Cesantias {cesantias_total:,.0f} x {days_worked}/360 x 12% = {valor_intereses:,.0f}'

            return amount, days_worked, 100, nombre, "", datos

        return resultado



    def _intces_year(self, data_payslip):
        """
        Calcula intereses de cesantías del año anterior.
        PRIMERA OPCION: Buscar en consolidado (hr_executing_provisions_details)
        FALLBACK: Calcular manualmente si no existe consolidado.
        """
        employee = data_payslip['employee']
        contract = data_payslip['contract']
        payslip = data_payslip['slip']

        # Validaciones de exclusión
        skip = employee.tipo_coti_id.code in ['12', '19']
        skip |= contract.modality_salary == 'integral'
        skip |= contract.date_start.year == payslip.date_to.year

        if skip:
            return 0, 0, 0, 0, "", {}

        should_pay_in_payroll = payslip.pay_cesantias_in_payroll

        if not should_pay_in_payroll:
            return 0, 0, 0, 0, "", {}

        # Año anterior
        previous_year = payslip.date_to.year - 1
        nombre = f"INT. CESANTIAS DEL PERIODO ANTERIOR {previous_year}"

        # =====================================================================
        # PRIMERA OPCION: Buscar en consolidado del año anterior
        # =====================================================================
        consolidado = self._get_consolidado_ano_anterior(
            employee, contract, previous_year, 'intcesantias'
        )

        if consolidado:
            # Usar valor del consolidado (current_payable_value = neto a pagar)
            total_intereses = consolidado.get('current_payable_value', 0)
            if total_intereses > 0:
                data_kpi = {
                    'fuente': 'consolidado',
                    'provision_id': consolidado.get('provision_id'),
                    'year': previous_year,
                    'month': consolidado.get('month', 12),
                    'value_base': consolidado.get('value_base', 0),
                    'amount': consolidado.get('amount', 0),
                    'value_payments': consolidado.get('value_payments', 0),
                    'current_payable_value': total_intereses,
                    'total_intereses': total_intereses,
                    'formula': f"Consolidado {previous_year}-{consolidado.get('month', 12):02d}: {total_intereses:,.0f}"
                }
                return total_intereses, 1, 100, nombre, '', {
                    'data_kpi': data_kpi,
                    'monto_total': total_intereses
                }

        # =====================================================================
        # FALLBACK: Calcular manualmente si no hay consolidado
        # =====================================================================
        date_ref = payslip.date_to.replace(year=previous_year)
        date_from = date_ref.replace(month=1, day=1)
        date_to = date_ref.replace(month=12, day=31)

        if date_from < contract.date_start:
            date_from = contract.date_start

        # Usar método adaptado para calcular base
        base_diaria, _, _, _, _, datos = self._compute_social_benefits(
            data_payslip,
            date_from,
            date_to,
            'intereses',
            descontar_suspensiones=True
        )

        # Extraer días del resultado
        dias_trabajados = datos.get('data_kpi', {}).get('days_worked', 0)

        # Calcular valor total de intereses correctamente
        # Cesantías proporcionales = (base_mensual * días_trabajados) / 360
        # Intereses = cesantías * 12%
        base_mensual = base_diaria * 30
        cesantias_proporcionales = (base_mensual * dias_trabajados) / 360
        total_intereses = cesantias_proporcionales * 0.12
        tasa_aplicada = (dias_trabajados / DAYS_YEAR) * 12  # Solo para info

        data_kpi = {
            'fuente': 'calculo',
            'base_diaria': base_diaria,
            'base_mensual': base_mensual,
            'days_worked': dias_trabajados,
            'cesantias_proporcionales': cesantias_proporcionales,
            'tasa_interes': 12,
            'tasa_aplicada': tasa_aplicada,
            'total_intereses': total_intereses,
            'period': f"{date_from.year}",
            'formula': f"(({base_mensual:,.0f} x {dias_trabajados}) / 360) x 12% = {total_intereses:,.0f}"
        }

        # Retornar total con quantity=1 y monto_total para que hr_slip.py lo use
        return total_intereses, 1, 100, nombre, '', {
            'data_kpi': data_kpi,
            'monto_total': total_intereses
        }



    def _ces_year(self, data_payslip):
        """
        Calcula cesantías del año anterior.
        PRIMERA OPCION: Buscar en consolidado (hr_executing_provisions_details)
        FALLBACK: Calcular manualmente si no existe consolidado.
        """
        employee = data_payslip['employee']
        contract = data_payslip['contract']
        payslip = data_payslip['slip']

        # Validaciones de exclusión
        skip = employee.tipo_coti_id.code in ['12', '19']
        skip |= contract.modality_salary == 'integral'
        skip |= contract.date_start.year == payslip.date_to.year

        if skip:
            return 0, 0, 0, 0, "", {}

        # Verificar si hay pagos de cesantías previos (reversiones)
        for payments in payslip.severance_payments_reverse:
            if payments.type_history in ('cesantias', 'all'):
                tot_rule = payments.severance_value
                return tot_rule, 1, 100, f"{self.name} {payments.final_accrual_date.year}", "", {
                    'monto_total': tot_rule
                }

        # CES_YEAR SOLO se computa en liquidaciones
        is_liquidation = payslip.struct_process == 'contrato' and payslip.date_liquidacion

        if not is_liquidation:
            return 0, 0, 0, 0, "", {}

        # Verificar si aplica el pago de cesantías del año anterior
        # (solo en enero/febrero cuando no se han consignado al fondo)
        is_jan_feb = payslip.date_to.month in [1, 2]
        try:
            has_previous_year_option = payslip.pagar_cesantias_ano_anterior
        except (AttributeError, KeyError):
            has_previous_year_option = False

        if not (is_jan_feb and has_previous_year_option):
            return 0, 0, 0, 0, "", {}

        # Año anterior
        previous_year = payslip.date_to.year - 1
        nombre = f"CESANTIAS DEL PERIODO ANTERIOR {previous_year}"

        # =====================================================================
        # PRIMERA OPCION: Buscar en consolidado del año anterior
        # =====================================================================
        consolidado = self._get_consolidado_ano_anterior(
            employee, contract, previous_year, 'cesantias'
        )

        if consolidado:
            # Usar valor del consolidado (current_payable_value = neto a pagar)
            total_cesantias = consolidado.get('current_payable_value', 0)
            if total_cesantias > 0:
                data_kpi = {
                    'fuente': 'consolidado',
                    'provision_id': consolidado.get('provision_id'),
                    'year': previous_year,
                    'month': consolidado.get('month', 12),
                    'value_wage': consolidado.get('value_wage', 0),
                    'value_base': consolidado.get('value_base', 0),
                    'amount': consolidado.get('amount', 0),
                    'value_payments': consolidado.get('value_payments', 0),
                    'current_payable_value': total_cesantias,
                    'total_cesantias': total_cesantias,
                    'formula': f"Consolidado {previous_year}-{consolidado.get('month', 12):02d}: {total_cesantias:,.0f}"
                }
                return total_cesantias, 1, 100, nombre, '', {
                    'data_kpi': data_kpi,
                    'monto_total': total_cesantias
                }

        # =====================================================================
        # FALLBACK: Calcular manualmente si no hay consolidado
        # =====================================================================
        date_ref = payslip.date_to.replace(year=previous_year)
        date_from = date_ref.replace(month=1, day=1)
        date_to = date_ref.replace(month=12, day=31)

        if date_from < contract.date_start:
            date_from = contract.date_start

        # Usar método adaptado para calcular base
        base_diaria, _, _, _, _, datos = self._compute_social_benefits(
            data_payslip,
            date_from,
            date_to,
            'cesantias',
            descontar_suspensiones=True
        )

        # Extraer días del resultado
        dias_trabajados = datos.get('data_kpi', {}).get('days_worked', 0)

        # Calcular valor total de cesantías
        # Fórmula: (salario_mensual * días_trabajados) / 360
        base_mensual = base_diaria * 30
        total_cesantias = (base_mensual * dias_trabajados) / 360

        data_kpi = {
            'fuente': 'calculo',
            'base_diaria': base_diaria,
            'base_mensual': base_mensual,
            'days_worked': dias_trabajados,
            'total_cesantias': total_cesantias,
            'period': f"{date_from.year}",
            'formula': f"({base_mensual:,.0f} x {dias_trabajados}) / 360 = {total_cesantias:,.0f}"
        }

        # Retornar total con quantity=1 y monto_total para que hr_slip.py lo use
        return total_cesantias, 1, 100, nombre, '', {
            'data_kpi': data_kpi,
            'monto_total': total_cesantias
        }

