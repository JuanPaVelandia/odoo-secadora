# -*- coding: utf-8 -*-
"""
Servicio de Cálculo de Días Trabajados
======================================

Calcula las líneas de días trabajados (worked_days_line_ids) para la nómina.
Incluye:
- Días totales del período
- Días de ausencia (desde hr.leave.line)
- Días fuera de contrato
- Días para auxilio de transporte
- Día 31
"""

from datetime import timedelta
from decimal import Decimal
import logging

from odoo.addons.lavish_hr_employee.models.payroll.hr_payslip_constants import (
    days360,
    DAYS_MONTH,
    HOURS_PER_DAY,
)

_logger = logging.getLogger(__name__)


class WorkedDaysCalculationService:
    """
    Servicio para calcular líneas de días trabajados.
    Extrae la lógica de get_worked_day_lines de hr.payslip.
    """

    def __init__(self, payslip):
        """
        Args:
            payslip: hr.payslip record
        """
        self.payslip = payslip
        self.env = payslip.env
        self.contract = payslip.contract_id
        self.date_from = payslip.date_from
        self.date_to = payslip.date_to

    def _format_number(self, number):
        """Convierte un número a formato decimal y devuelve como float."""
        return float(Decimal(number))

    def _get_entry_types(self):
        """Obtiene los tipos de entrada de trabajo necesarios."""
        return self.payslip._get_entry_types()

    def _days_between(self, date_from, date_to):
        """
        Calcula días entre fechas usando método comercial colombiano 360.
        Usa la función estándar days360 de hr_payslip_constants.
        """
        return days360(date_from, date_to)

    def calculate(self):
        """
        Calcula y genera las líneas de días trabajados para la nómina.

        Returns:
            list: Lista de diccionarios con la información de cada línea
        """
        res = []
        rec = self.payslip
        contract = self.contract
        date_from = self.date_from
        date_to = self.date_to

        # Cambios de salario ordenados
        wage_changes_sorted = sorted(contract.change_wage_ids, key=lambda x: x.date_start)
        last_wage_change = max(
            (change for change in wage_changes_sorted if change.date_start < date_from),
            default=None
        )
        current_wage_day = last_wage_change.wage / DAYS_MONTH if last_wage_change else contract.wage / DAYS_MONTH

        # Variables de acumulación
        leaves_worked_lines = {}
        worked_days = 0
        worked_aux_days = 0
        aux_transport_days = 0
        worked30 = 0

        # Tipo de estructura
        hp_type = rec.struct_process

        # Parámetros anuales
        company_id = rec.company_id.id if rec.company_id else None
        annual_parameters = self.env['hr.annual.parameters'].get_for_year(
            date_to.year, company_id=company_id, raise_if_not_found=False
        )
        w_hours_base = annual_parameters.hours_daily if annual_parameters else HOURS_PER_DAY

        # Ajustar horas para contratos de tiempo parcial
        partial_factor = contract.factor if contract.parcial and contract.factor else 1.0
        w_hours = w_hours_base * partial_factor

        # Tipos de entrada
        types = self._get_entry_types()
        days31 = types['days31']
        outdays = types['outdays']
        wdays = types['wdays']
        wdayst = types['wdayst']
        prevdays = types['prevdays']

        # Tipos de proceso que calculan días trabajados
        ps_types = ['nomina', 'contrato']
        if not rec.company_id.fragment_vac:
            ps_types.append('Vacaciones')

        adjustments = []

        if hp_type in ps_types:
            lab_days = self._days_between(date_from, date_to)

            # Línea de total días del período
            res.append({
                'work_entry_type_id': wdayst.id,
                'name': 'Total días del período',
                'sequence': 1,
                'code': 'TOTAL_DIAS',
                'symbol': '',
                'number_of_days': self._format_number(lab_days),
                'number_of_hours': self._format_number(w_hours * lab_days),
                'contract_id': contract.id
            })

            # Consultar días previos de otras nóminas
            wd_other = self._get_previous_worked_days(date_from, date_to, contract.id, rec.id)
            if wd_other > 0:
                adjustments.append(f"(-{wd_other} D previos)")

            # Inicializar con días totales del período (sistema 360)
            worked_days = lab_days
            worked_aux_days = lab_days

            # Procesar día a día
            date_tmp = date_from
            out_of_contract_days = 0

            while date_tmp <= date_to:
                # Verificar si es día de ausencia
                is_absence_day = any(
                    leave.date_from.date() <= date_tmp <= leave.date_to.date() and
                    leave.holiday_status_id.novelty not in ['vco', 'p'] and
                    leave.holiday_status_id.sub_wd
                    for leave in rec.leave_ids.leave_id
                )

                is_within_contract = contract.date_start <= date_tmp <= (contract.date_end or date_tmp)

                # Verificar cambio de salario
                wage_change_today = next(
                    (change for change in wage_changes_sorted if change.date_start == date_tmp),
                    None
                )
                if wage_change_today:
                    current_wage_day = wage_change_today.wage / DAYS_MONTH

                if is_within_contract:
                    if is_absence_day:
                        # Procesar día de ausencia
                        absence_data = self._process_absence_day(
                            date_tmp, rec, leaves_worked_lines, contract,
                            current_wage_day, w_hours
                        )
                        if absence_data:
                            leaves_worked_lines = absence_data['leaves_worked_lines']
                            worked_days -= absence_data['days_to_subtract']

                            if absence_data['pay_transport_allowance']:
                                aux_transport_days += absence_data['days_to_subtract']
                            else:
                                worked_aux_days -= absence_data['days_to_subtract']
                    else:
                        # Día normal - verificar día 31
                        if date_tmp.day == 31:
                            worked_days -= 0
                            worked_aux_days -= 0
                            worked30 = 0
                else:
                    # Fuera de contrato - NO contar día 31
                    if date_tmp.day != 31:
                        out_of_contract_days += 1

                date_tmp += timedelta(days=1)

            # Línea de días fuera de contrato
            if out_of_contract_days > 0:
                description = 'Deducción por inicio de contrato' if date_from < contract.date_start else 'Deducción por fin de contrato'
                res.append({
                    'work_entry_type_id': outdays.id,
                    'name': description,
                    'sequence': 2,
                    'code': 'OUT',
                    'symbol': '-',
                    'number_of_days': self._format_number(out_of_contract_days),
                    'number_of_hours': self._format_number(w_hours * out_of_contract_days),
                    'contract_id': contract.id,
                })
                adjustments.append(f"(-{out_of_contract_days} D fuera contrato)")
                worked_days -= out_of_contract_days
                worked_aux_days -= out_of_contract_days
                worked_days = max(0, worked_days)
                worked_aux_days = max(0, worked_aux_days)

            # Agregar líneas de ausencias
            for key, line_data in leaves_worked_lines.items():
                line_data['number_of_days'] = self._format_number(line_data['number_of_days'])
                line_data['number_of_hours'] = self._format_number(line_data['number_of_hours'])
                res.append(line_data)

            # Calcular días sin auxilio de transporte
            days_without_aux_transport = self._calculate_days_without_aux_transport(rec, date_from, date_to)

            worked_aux_days = worked_days + aux_transport_days - days_without_aux_transport

            # Línea WORK100 - Días trabajados
            worked_days_name = 'Días Trabajados'
            if adjustments:
                worked_days_name += " " + " ".join(adjustments)

            res.append({
                'work_entry_type_id': wdays.id,
                'name': worked_days_name,
                'sequence': 6,
                'code': 'WORK100',
                'symbol': '+',
                'amount': current_wage_day * worked_days,
                'number_of_days': self._format_number(worked_days),
                'number_of_hours': self._format_number(worked_days * w_hours),
                'number_of_days_aux': self._format_number(worked_aux_days),
                'number_of_hours_aux': self._format_number(worked_aux_days * w_hours),
                'contract_id': contract.id
            })

            # Línea WORK131 - Día 31
            if rec.struct_id.regular_31:
                res.append({
                    'work_entry_type_id': days31.id,
                    'name': 'Día 31',
                    'sequence': 6,
                    'code': 'WORK131',
                    'symbol': '+',
                    'amount': current_wage_day * worked30,
                    'number_of_days': self._format_number(worked30),
                    'number_of_hours': self._format_number(worked30 * w_hours),
                    'number_of_days_aux': self._format_number(worked30),
                    'number_of_hours_aux': self._format_number(worked30 * w_hours),
                    'contract_id': contract.id
                })

            # Línea de días previos
            if wd_other:
                res.append({
                    'work_entry_type_id': prevdays.id,
                    'name': 'Días Previos',
                    'sequence': 7,
                    'code': 'PREV_PAYS',
                    'symbol': '-',
                    'number_of_days': self._format_number(wd_other),
                    'number_of_hours': self._format_number(wd_other * w_hours),
                    'contract_id': contract.id
                })

        return res

    def _get_previous_worked_days(self, date_from, date_to, contract_id, payslip_id):
        """
        Consulta días previos de otras nóminas en el período usando read_group.

        Returns:
            float: Días a restar por nóminas previas
        """
        WorkedDays = self.env['hr.payslip.worked_days']

        # Dominio para filtrar worked_days de otras nóminas en el período
        domain = [
            ('payslip_id.date_from', '>=', date_from),
            ('payslip_id.date_to', '<=', date_to),
            ('payslip_id.contract_id', '=', contract_id),
            ('payslip_id', '!=', payslip_id),
            ('work_entry_type_id.code', 'not in', ['WORK_D', 'LICENCIA_REMUNERADA']),
            ('payslip_id.struct_process', 'in', ['vacaciones', 'nomina', 'contrato']),
            ('payslip_id.state', 'in', ['done', 'paid']),
        ]

        # Agrupar por symbol y código del work_entry_type
        grouped_data = WorkedDays._read_group(
            domain=domain,
            groupby=['symbol', 'work_entry_type_id'],
            aggregates=['number_of_days:sum'],
        )

        wd_prev = 0
        wd_minus = 0

        for symbol, work_entry_rec, number_of_days in grouped_data:
            number_of_days = number_of_days or 0
            symbol = symbol or ''

            # Obtener código del work_entry_type
            code = work_entry_rec.code if work_entry_rec else ''

            if code == 'WORK_D':
                continue

            if code in ('PREV_AUS', 'PREV_PAYS'):
                wd_prev += number_of_days
            elif symbol in ('-', '') and code not in ('OUT', 'VAC', 'VACDISFRUTADAS'):
                wd_minus += number_of_days

        return wd_minus - wd_prev

    def _process_absence_day(self, date_tmp, rec, leaves_worked_lines, contract, current_wage_day, w_hours):
        """
        Procesa un día de ausencia.

        Returns:
            dict con datos de ausencia o None si no hay ausencia
        """
        # Buscar la ausencia que cubre este día
        leave = next(
            (lv for lv in rec.leave_ids.leave_id
             if lv.date_from.date() <= date_tmp <= lv.date_to.date()
             and lv.holiday_status_id.novelty not in ['vco', 'p']
             and lv.holiday_status_id.sub_wd),
            None
        )

        if not leave:
            return None

        key = (leave.holiday_status_id.id, '-')
        absence_line = next((line for line in leave.line_ids if line.date == date_tmp), None)

        # Obtener valores de la línea o usar defaults
        if absence_line:
            days_to_subtract = absence_line.days_payslip
            hour_to_subtract = absence_line.hours
            amount = absence_line.amount
        else:
            days_to_subtract = 1.0
            hour_to_subtract = w_hours
            amount = current_wage_day

        if days_to_subtract <= 0:
            return None

        # Crear o actualizar línea de ausencia
        if key not in leaves_worked_lines:
            leaves_worked_lines[key] = {
                'work_entry_type_id': leave.holiday_status_id.work_entry_type_id.id if leave.holiday_status_id.work_entry_type_id else False,
                'name': f"Días {leave.holiday_status_id.name.capitalize()}",
                'sequence': 5,
                'code': leave.holiday_status_id.code or 'nocode',
                'symbol': '-',
                'amount': amount,
                'number_of_days': days_to_subtract,
                'number_of_hours': hour_to_subtract,
                'contract_id': contract.id,
            }
        else:
            leaves_worked_lines[key]['number_of_days'] += days_to_subtract
            leaves_worked_lines[key]['number_of_hours'] += hour_to_subtract
            leaves_worked_lines[key]['amount'] += amount

        return {
            'leaves_worked_lines': leaves_worked_lines,
            'days_to_subtract': days_to_subtract,
            'pay_transport_allowance': leave.holiday_status_id.pay_transport_allowance,
        }

    def _calculate_days_without_aux_transport(self, rec, date_from, date_to):
        """
        Calcula días de ausencias que NO pagan auxilio de transporte.
        (ej: VACDISFRUTADAS con sub_wd=False, pay_transport_allowance=False)
        Según Decreto 1250/2017: No se paga auxilio durante vacaciones.

        Returns:
            float: Días sin auxilio de transporte
        """
        days_without_aux_transport = 0

        for leave in rec.leave_ids.leave_id:
            status = leave.holiday_status_id

            # Solo ausencias que NO restan días (sub_wd=False) y NO pagan auxilio
            if status.sub_wd:
                continue  # Ya procesado en el loop principal
            if status.pay_transport_allowance:
                continue  # Paga auxilio, no restar
            if status.novelty in ['vco', 'p']:
                continue  # Vacaciones compensadas o permisos especiales

            # Calcular días de esta ausencia dentro del período
            overlap_start = max(leave.date_from.date(), date_from)
            overlap_end = min(leave.date_to.date(), date_to)

            if overlap_start <= overlap_end:
                days_without_aux = self._days_between(overlap_start, overlap_end)
                days_without_aux_transport += days_without_aux

        return days_without_aux_transport
