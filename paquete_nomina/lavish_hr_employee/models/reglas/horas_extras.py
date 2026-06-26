# -*- coding: utf-8 -*-

"""
REGLAS SALARIALES - HORAS EXTRAS Y RECARGOS
============================================

Métodos extraídos de hr_rule_adapted.py
Cálculo de horas extras, recargos nocturnos, festivos, etc.
"""

from odoo import models, api
from decimal import Decimal
from .config_reglas import (
    crear_log_data, crear_resultado_regla, crear_resultado_vacio,
    crear_computation_estandar, crear_indicador, crear_paso_calculo
)


class HrSalaryRuleHorasExtras(models.AbstractModel):
    """Mixin para reglas de horas extras"""

    _name = 'hr.salary.rule.horas.extras'
    _description = 'Métodos para Horas Extras y Recargos'


    def _get_hours_config_for_date(self, company_id, date_reference):
        """
        Busca la configuración de horas aplicable para una fecha específica
        """
        all_configs = self.env['hr.company.working.hours'].search([
            ('company_id', '=', company_id),
            ('effective_date', '<=', date_reference)
        ], order='effective_date desc')

        if all_configs:
            for config in all_configs:
                if config.effective_date <= date_reference:
                    next_config = self.env['hr.company.working.hours'].search([
                        ('company_id', '=', company_id),
                        ('effective_date', '>', config.effective_date)
                    ], order='effective_date asc', limit=1)

                    if not next_config or date_reference < next_config.effective_date:
                        return config.hours_to_pay or config.hours_per_month

        year, month, day = date_reference.year, date_reference.month, date_reference.day

        if year < 2024:
            return 240
        elif year == 2024:
            return 240 if month < 7 or (month == 7 and day < 15) else 230
        elif year == 2025:
            return 230 if month < 7 or (month == 7 and day < 15) else 220
        elif year == 2026:
            return 220 if month < 7 or (month == 7 and day < 15) else 210
        else:
            return 210

    def _get_overtime_work_time_rate(self, contract):
        """
        Retorna un factor de tiempo parcial compatible con Odoo 19.
        En este stack la frecuencia de pago vive en `version_id.schedule_pay`
        y la parcialidad puede venir desde `work_time_rate`, `factor` o flags
        heredados del contrato.
        """
        version = getattr(contract, 'version_id', False)
        work_time_rate = getattr(version, 'work_time_rate', False) or getattr(contract, 'factor', False)
        if work_time_rate:
            return work_time_rate
        if getattr(contract, 'parcial', False):
            return 0.5
        return 1.0


    def _compute_overtime_with_log(self, localdict, rule_code):
        """
        Calcula horas extras - solo construccion de datos.
        Los porcentajes se obtienen de hr.type.overtime segun la fecha de cada novedad.
        Soporta rangos de fechas para manejar gradualidad de Ley 2466/2025.

        Formula de calculo segun overtime_formula_type en parametros anuales:
        - 'classic': Salario / 240 (fijo)
        - 'legal': Salario / Horas mes (segun reduccion gradual de jornada)
        """
        contract = localdict.get('contract')
        employee = localdict.get('employee')
        payslip = localdict.get('payslip')
        inherit_contrato = localdict.get('inherit_contrato', 0)
        annual_parameters = localdict.get('annual_parameters')

        # Mapeo de campos type_overtime para cada regla
        OVERTIME_FIELD_MAP = {
            'HEYREC001': {'field': 'overtime_ext_d', 'name': 'Hora extra diurna'},
            'HEYREC002': {'field': 'overtime_eddf', 'name': 'Hora extra diurna dom/fest'},
            'HEYREC003': {'field': 'overtime_ext_n', 'name': 'Hora extra nocturna'},
            'HEYREC004': {'field': 'overtime_rdf', 'name': 'Recargo dom/fest'},
            'HEYREC005': {'field': 'overtime_rn', 'name': 'Recargo nocturno'},
            'HEYREC006': {'field': 'overtime_endf', 'name': 'Hora extra nocturna dom/fest'},
            'HEYREC007': {'field': 'overtime_dof', 'name': 'Dominical o festivo'},
            'HEYREC008': {'field': 'overtime_rndf', 'name': 'Recargo nocturno dom/fest'},
            'HEYREC009': {'field': 'overtime_rnf', 'name': 'Recargo nocturno festivo'},
        }

        field_config = OVERTIME_FIELD_MAP.get(rule_code, {})
        rule_name = field_config.get('name', rule_code)
        overtime_type_code = field_config.get('field', '')

        salary_rule = self.get_salary_rule(rule_code, employee.employee_type)
        if not salary_rule:
            return 0.0, 0.0, 0.0, False, '', False

        aplicar = int(salary_rule.aplicar_cobro or '0')
        day_from = payslip.date_from.day
        day_to = 30 if payslip.date_to.month == 2 and payslip.date_to.day in (28, 29) else payslip.date_to.day

        if not ((aplicar == 0) or (aplicar >= day_from and aplicar <= day_to)):
            return 0.0, 0.0, 0.0, False, '', False

        overtime_records = self.get_overtime(employee, payslip.date_from, payslip.date_to, inherit_contrato, aplicar)
        if not overtime_records:
            return 0.0, 0.0, 0, False, '', False

        TypeOvertime = self.env['hr.type.overtime']
        result_tota_rate = 0.0
        result_total = 0.0
        hours_total = 0.0
        details = []
        percentages_used = set()

        for record in overtime_records:
            hours = record[overtime_type_code] if overtime_type_code in record._fields else 0
            if hours <= 0:
                continue

            # Obtener porcentaje vigente para la fecha de la novedad
            # Usar date_only (Date) en lugar de date (Datetime) para busqueda
            reference_date = record.date_only or (record.date.date() if record.date else None)
            type_overtime = TypeOvertime.get_percentage_for_date(
                overtime_type_code,
                reference_date,
                contract.company_id.id
            ) if reference_date else None

            if not type_overtime:
                # Fallback: buscar por regla salarial (compatibilidad)
                type_overtime = TypeOvertime.search([
                    ('salary_rule', '=', salary_rule.id),
                    ('active', '=', True)
                ], limit=1)

            if not type_overtime:
                continue

            percentage = type_overtime.percentage or 100.0
            multiplier = percentage / 100.0
            percentages_used.add(percentage)

            # Determinar horas base segun formula seleccionada en parametros anuales
            if annual_parameters:
                try:
                    formula_type = annual_parameters.overtime_formula_type
                except (AttributeError, KeyError):
                    formula_type = 'legal'
            else:
                formula_type = 'legal'
            if formula_type == 'classic':
                # Formula clasica: siempre 240 horas (Salario / 240)
                base_hours = 240
            else:
                # Formula legal: usa horas segun reduccion gradual de jornada (Ley 2101)
                # Usar date_only para obtener configuracion de horas
                base_hours = self._get_hours_config_for_date(contract.company_id.id, reference_date)

            # NOTA: La division por 2 para subcontract_type 'obra_parcial' / 'obra_integral'
            # se removio porque inflaba el valor hora al doble (base_hours=110 en vez de 220),
            # generando el "Set B" de reglas duplicadas reportado. El divisor correcto es
            # la jornada legal vigente (Ley 2101) sin ajustes por subcontract_type.
            # El ajuste por tiempo parcial real se mantiene via work_time_rate.

            work_time_rate = self._get_overtime_work_time_rate(contract)
            if work_time_rate and work_time_rate > 0 and work_time_rate < 1:
                base_hours = base_hours * work_time_rate

            # Defensa: evitar division por cero si base_hours quedo en 0
            if not base_hours or base_hours <= 0:
                continue

            hourly_rate = contract.wage / base_hours
            rate_per_hour = round(float(hourly_rate * multiplier), 2)
            line_total = hourly_rate * hours

            details.append({
                'date': reference_date,  # Usar date_only para consistencia
                'datetime_start': record.date,  # Datetime completo de inicio
                'datetime_end': record.date_end,  # Datetime completo de fin
                'hours': hours,
                'base_hours': base_hours,
                'hourly_rate': hourly_rate,
                'percentage': percentage,
                'multiplier': multiplier,
                'rate_per_hour': rate_per_hour,
                'line_total': rate_per_hour * hours,
                'overtime_id': record.id,
                'legal_ref': type_overtime.legal_reference or ''
            })

            result_tota_rate += rate_per_hour * hours
            result_total += line_total
            hours_total += hours

        if hours_total <= 0:
            return 0.0, 0.0, 0, False, '', False

        avg_rate = result_tota_rate / hours_total
        avg_nom_rate = result_total / hours_total

        # Si hay multiples porcentajes usados, mostrarlos todos
        if len(percentages_used) > 1:
            pct_str = '/'.join([f'{p}%' for p in sorted(percentages_used)])
            name = f"{rule_name} ({pct_str}) - {hours_total}h a ${avg_rate:,.0f}"
        else:
            percentage = list(percentages_used)[0] if percentages_used else 0
            name = f"{rule_name} ({percentage}%) - {hours_total}h a ${avg_rate:,.0f}"

        # Usar el porcentaje promedio para el resumen
        avg_percentage = sum(percentages_used) / len(percentages_used) if percentages_used else 0
        avg_multiplier = avg_percentage / 100.0

        # Determinar formula usada para mostrar en detalles
        if annual_parameters:
            try:
                formula_type = annual_parameters.overtime_formula_type
            except (AttributeError, KeyError):
                formula_type = 'legal'
        else:
            formula_type = 'legal'
        base_hours_used = details[0]['base_hours'] if details else 240
        formula_desc = 'Salario / 240' if formula_type == 'classic' else f'Salario / {int(base_hours_used)}'

        data = {
            'rule_code': rule_code,
            'rule_name': rule_name,
            'percentage': avg_percentage,
            'percentages_used': list(percentages_used),
            'multiplier': avg_multiplier,
            'hours_total': hours_total,
            'result_total': result_tota_rate,
            'avg_rate': avg_rate,
            'avg_nom_rate': avg_nom_rate,
            'base_wage': contract.wage,
            'base_hours': base_hours_used,
            'formula_type': formula_type,
            'details': details
        }

        # Crear computation estandarizada para el widget
        indicadores = [
            crear_indicador('Horas', float(hours_total), 'info', 'number'),
            crear_indicador('Recargo', f'{avg_percentage}%', 'warning', 'text'),
            crear_indicador('Base', f'{int(base_hours_used)}h/mes', 'secondary', 'text'),
        ]

        if len(percentages_used) > 1:
            indicadores.append(
                crear_indicador('Rangos', f'{len(percentages_used)} periodos', 'secondary', 'text')
            )

        pasos = [
            crear_paso_calculo('Salario Base', float(contract.wage), 'currency'),
            crear_paso_calculo(f'Horas Mes ({formula_type})', float(base_hours_used), 'number'),
            crear_paso_calculo('Valor Hora Base', float(contract.wage / base_hours_used) if base_hours_used else 0, 'currency'),
            crear_paso_calculo('Multiplicador Prom.', float(avg_multiplier), 'number'),
            crear_paso_calculo('Valor Hora Extra', float(avg_rate), 'currency'),
            crear_paso_calculo('Horas Trabajadas', float(hours_total), 'number'),
            crear_paso_calculo('Total', float(result_tota_rate), 'currency', highlight=True),
        ]

        # Agregar detalle por fecha con porcentaje usado
        detalle_fechas = []
        for d in details:
            detalle_fechas.append({
                'fecha': str(d['date']),
                'horas': d['hours'],
                'porcentaje': d['percentage'],
                'valor': d['rate_per_hour'],
                'subtotal': d['line_total'],
                'base_legal': d.get('legal_ref', ''),
            })

        computation = crear_computation_estandar(
            'hora_extra',
            titulo=rule_name,
            formula=f'({formula_desc}) x {avg_percentage}% x Horas',
            indicadores=indicadores,
            pasos=pasos,
            base_legal='Art. 159-171 CST, Ley 2466/2025, Ley 2101/2021',
            elemento_ley='Trabajo suplementario o de horas extras',
            datos={**data, 'detalle_fechas': detalle_fechas},
        )

        return avg_nom_rate, hours_total, avg_percentage, name, '', computation


    def _compute_overtime_generic(self, localdict, rule_code, percentage, field_name):
        """
        Método genérico para cálculo de horas extras y recargos.
        Args:
            localdict: Diccionario de contexto de nómina
            rule_code: Código de la regla (HEYREC001, HEYREC002, etc.)
            percentage: Porcentaje de recargo (125.0, 200.0, 175.0, 110.0, 35.0)
            field_name: Campo en hr.overtime que contiene las horas
        Returns:
            Tuple: (rate, quantity, percentage, name, False, {})
        """
        contract = localdict['contract']
        employee = localdict['employee']
        slip = localdict['slip']
        annual_parameters = localdict.get('annual_parameters')

        if contract.not_pay_overtime:
            return 0, 0, 0, f'HE {rule_code}', False, {}

        # Usar date_only para busquedas ya que date ahora es Datetime
        overtime_records = self.env['hr.overtime'].search([
            ('employee_id', '=', employee.id),
            ('date_only', '>=', slip.date_from),
            ('date_only', '<=', slip.date_to)
        ])

        total_hours = 0
        total_value = 0

        if annual_parameters.hours_monthly > 0:
            base_hours = annual_parameters.hours_monthly
        else:
            base_hours = 240

        hourly_rate = Decimal(contract.wage) / Decimal(base_hours)

        for overtime in overtime_records:
            hours = overtime[field_name] if field_name in overtime._fields else 0

            if hours > 0:
                hours_decimal = Decimal(str(hours))
                percentage_decimal = Decimal(str(percentage)) / Decimal('100')
                value = hourly_rate * percentage_decimal * hours_decimal

                total_hours += float(hours)
                total_value += float(value)

        if total_hours == 0:
            return 0, 0, percentage, f'HE {rule_code}', False, {}

        rate = total_value / total_hours if total_hours > 0 else 0

        return rate, total_hours, percentage, f'HE {rule_code}', False, {}



    def _heyrec001(self, localdict):
        """Horas extra diurnas (125%)"""
        return self._compute_overtime_with_log(localdict, 'HEYREC001')

    def _heyrec002(self, localdict):
        """Horas extra diurnas dominical/festiva (200%)"""
        return self._compute_overtime_with_log(localdict, 'HEYREC002')

    def _heyrec003(self, localdict):
        """Horas extra nocturna (175%)"""
        return self._compute_overtime_with_log(localdict, 'HEYREC003')

    def _heyrec004(self, localdict):
        """Recargo festivo (110%)"""
        return self._compute_overtime_with_log(localdict, 'HEYREC004')

    def _heyrec005(self, localdict):
        """Recargo nocturno (35%)"""
        return self._compute_overtime_with_log(localdict, 'HEYREC005')

    def _heyrec006(self, localdict):
        """Horas extra nocturna dominical/festiva (250%)"""
        return self._compute_overtime_with_log(localdict, 'HEYREC006')

    def _heyrec007(self, localdict):
        """Horas Dominicales (175%)"""
        return self._compute_overtime_with_log(localdict, 'HEYREC007')

    def _heyrec008(self, localdict):
        """Recargos dominicales (75%)"""
        return self._compute_overtime_with_log(localdict, 'HEYREC008')

    def _heyrec009(self, localdict):
        """Recargo nocturno festivo (210%)"""
        return self._compute_overtime_with_log(localdict, 'HEYREC009')

    def get_overtime(self, employee_id, from_date, to_date, inherit_contrato=0, aplicar=0):
        """Busca registros de horas extras para el empleado en el período.

        Usa date_only y date_end_only para busquedas ya que date y date_end
        ahora son campos Datetime.
        """
        if inherit_contrato == 0 and aplicar != 0:
            from_month = from_date.month
            from_year = from_date.year
            date = str(from_year) + '-' + str(from_month) + '-01'
        else:
            date = from_date

        if employee_id.contract_id.not_pay_overtime:
            res = self.env['hr.overtime']
        else:
            # Usar date_only y date_end_only para busquedas por fecha
            res = self.env['hr.overtime'].search([
                ('employee_id', '=', employee_id.id),
                ('date_only', '>=', date),
                ('date_end_only', '<=', to_date)
            ])
        return res

    def get_salary_rule(self, salary_rule_code, employee_type=None):
        """
        Busca regla salarial por codigo y valida si aplica al tipo de empleado.

        Args:
            salary_rule_code: Codigo de la regla salarial
            employee_type: Tipo de empleado (string) - ej: 'employee', 'contractor'
                          Si es None, retorna la regla sin validar tipo

        Returns:
            hr.salary.rule: Regla encontrada que aplica al tipo de empleado
        """
        rules = self.env['hr.salary.rule'].search([('code', '=', salary_rule_code)])

        if not rules or not employee_type:
            return rules

        # Filtrar reglas que aplican al tipo de empleado
        for rule in rules:
            if rule.applies_to_employee_type(employee_type):
                return rule

        return self.env['hr.salary.rule']

    def get_type_overtime(self, salary_rule_id):
        """Busca tipo de hora extra asociado a una regla salarial"""
        res = self.env['hr.type.overtime'].search([('salary_rule', '=', salary_rule_id)])
        return res
