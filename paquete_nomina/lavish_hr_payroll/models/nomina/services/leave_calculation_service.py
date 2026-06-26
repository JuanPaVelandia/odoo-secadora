# -*- coding: utf-8 -*-
"""
Servicio de Cálculo de Ausencias
================================

Calcula y procesa las ausencias (leaves) para la nómina.
Incluye:
- Validación de tipos de ausencia
- Cálculo de días de ausencia (compute_sheet_leave)
- Cálculo de días trabajados detallados (compute_worked_days)
"""

from datetime import datetime, timedelta
import calendar
import logging

from odoo.exceptions import UserError
from odoo import _

from odoo.addons.lavish_hr_employee.models.payroll.hr_payslip_constants import (
    DAYS_MONTH,
    DATETIME_MIN,
    DATETIME_MAX,
    VALID_NOVELTY_TYPES,
)

_logger = logging.getLogger(__name__)


class LeaveCalculationService:
    """
    Servicio para calcular y procesar ausencias en nómina.
    Extrae la lógica de compute_sheet_leave y compute_worked_days de hr.payslip.
    """

    def __init__(self, payslip):
        """
        Args:
            payslip: hr.payslip record
        """
        self.payslip = payslip
        self.env = payslip.env
        self.contract = payslip.contract_id
        self.employee = payslip.employee_id
        self.date_from = payslip.date_from
        self.date_to = payslip.date_to

    def _get_entry_types(self):
        """Obtiene los tipos de entrada de trabajo necesarios."""
        return self.payslip._get_entry_types()

    def validate_leave_types(self):
        """
        Valida que los tipos de ausencia estén correctamente configurados.

        Esta función verifica que los tipos de ausencia utilizados en las nóminas
        tengan correctamente configurados los campos que determinan su comportamiento
        en el cálculo de días trabajados.

        Returns:
            bool: True si todos los tipos están correctamente configurados

        Raises:
            UserError: Si algún tipo de ausencia no está correctamente configurado
        """
        rec = self.payslip
        if not rec.leave_ids:
            return True

        leave_status_list = rec.leave_ids.leave_id.mapped('holiday_status_id')
        missing_config = []

        for leave_status in leave_status_list:
            if not leave_status.novelty:
                missing_config.append(f"{leave_status.name}: Sin tipo PILA configurado")
            elif leave_status.novelty not in VALID_NOVELTY_TYPES:
                missing_config.append(f"{leave_status.name}: Tipo PILA '{leave_status.novelty}' no válido")

            if leave_status.novelty in ['vco', 'p'] and leave_status.sub_wd:
                missing_config.append(f"{leave_status.name}: Tipo '{leave_status.novelty}' no debe restar días trabajados (sub_wd)")

            if not leave_status.work_entry_type_id:
                missing_config.append(f"{leave_status.name}: Falta tipo de entrada de trabajo (work_entry_type_id)")

        if missing_config:
            raise UserError(_(f"Configuración incorrecta en tipos de ausencia:\n{chr(10).join(missing_config)}"))

        return True

    def compute_sheet_leave(self):
        """
        Calcula y asigna las ausencias para la nómina con detalle mejorado
        de días usados y no utilizados, respetando la estructura de campos existente.

        OPTIMIZACIÓN: Si existe payroll_batch_context, usa leaves pre-cargados.

        Returns:
            bool: True si se procesó correctamente
        """
        rec = self.payslip
        rec.leave_ids.unlink()
        rec.payslip_day_ids.unlink()

        date_from = datetime.combine(rec.date_from, DATETIME_MIN)
        date_to = datetime.combine(rec.date_to, DATETIME_MAX)
        employee_id = rec.employee_id.id

        # OPTIMIZACIÓN: Usar batch context si está disponible
        batch_ctx = self.env.context.get('payroll_batch_context')
        if batch_ctx:
            # Filtrar las leaves pre-cargadas por fechas
            all_leaves = batch_ctx.get_employee_leaves(employee_id)
            leaves = all_leaves.filtered(
                lambda l: l.date_to >= date_from and l.date_from <= date_to
            )
        else:
            leaves = self.env['hr.leave'].search([
                ('state', '=', 'validate'),
                ('date_to', '>=', date_from),
                ('date_from', '<=', date_to),
                ('employee_id', '=', employee_id),
            ])

        self.validate_leave_types()

        if not leaves:
            self.compute_worked_days()
            return True

        absence_records = []

        for leave in leaves:
            leave_start = max(leave.date_from.date(), rec.date_from)
            leave_end = min(leave.date_to.date(), rec.date_to)
            days_in_payslip = (leave_end - leave_start).days + 1
            days_in_other_payslips = sum(
                line.days_payslip
                for line in leave.line_ids
                if line.payslip_id and line.payslip_id.id != rec.id
            )
            affects_payroll = leave.holiday_status_id.novelty not in ['vco', 'p'] and leave.holiday_status_id.sub_wd
            days_to_use = days_in_payslip if affects_payroll else 0
            days_not_used = leave.number_of_days_in_payslip - days_to_use - days_in_other_payslips
            absence_data = {
                'leave_id': leave.id,
                'leave_type': leave.holiday_status_id.name,
                'employee_id': employee_id,
                'payroll_id': rec.id,
                'total_days': leave.number_of_days_in_payslip,
                'days_used': days_to_use,
                'days': days_in_other_payslips,
                'days_unused': days_not_used,
                'total': leave.number_of_days_in_payslip - days_in_other_payslips,
                'is_interrupted': False,
            }

            absence_records.append(absence_data)

        if absence_records:
            leave_records = self.env['hr.absence.days'].create(absence_records)
            all_lines = leave_records.mapped('leave_id.line_ids').filtered(
                lambda l: l.state == 'validated'
            )
            if rec.struct_id.process == 'vacaciones' or rec.pay_vacations_in_payroll:
                vacation_lines = all_lines.filtered(lambda l: l.leave_id.holiday_status_id.is_vacation)
                if vacation_lines:
                    money_lines = vacation_lines.filtered(
                        lambda l: l.leave_id.holiday_status_id.is_vacation_money
                    )
                    time_lines = vacation_lines - money_lines

                    relevant_lines = money_lines
                    if rec.company_id.fragment_vac:
                        relevant_lines |= time_lines.filtered(
                            lambda l: rec.date_from <= l.date <= rec.date_to
                        )
                    else:
                        relevant_lines |= time_lines

                    relevant_lines.write({
                        'payslip_id': rec.id,
                    })

                other_lines = all_lines - vacation_lines
                if other_lines:
                    other_lines.filtered(
                        lambda l: rec.date_from <= l.date <= rec.date_to
                    ).write({
                        'payslip_id': rec.id
                    })

            else:
                relevant_lines = all_lines.filtered(
                    lambda l: (
                        rec.date_from <= l.date <= rec.date_to and
                        not l.leave_id.holiday_status_id.is_vacation and
                        not l.leave_id.holiday_status_id.is_vacation_money
                    )
                )
                if relevant_lines:
                    relevant_lines.write({
                        'payslip_id': rec.id
                    })

        self.compute_worked_days()
        return True

    def compute_worked_days(self):
        """
        Calcula los días trabajados para la nómina.
        Incluye manejo especial para febrero, día 31, días de descanso, sábados y feriados.

        Returns:
            bool: True si se procesó correctamente
        """
        rec = self.payslip
        payslip_day_ids = []

        self.validate_leave_types()

        wage_changes_sorted = sorted(rec.contract_id.change_wage_ids, key=lambda x: x.date_start)
        last_wage_change_before_payslip = max(
            (change for change in wage_changes_sorted if change.date_start < rec.date_from),
            default=None
        )
        current_wage_day = last_wage_change_before_payslip.wage / DAYS_MONTH if last_wage_change_before_payslip else rec.contract_id.wage / DAYS_MONTH

        has_day_31 = False
        holiday_service = self.env['lavish.holidays']
        date_tmp = rec.date_from

        while date_tmp <= rec.date_to:
            absence_line = None
            permission_line = None

            # Buscar permisos
            permission_leaves = [
                leave for leave in rec.leave_ids.leave_id.line_ids
                if leave.date <= date_tmp <= leave.date and
                leave.leave_id.holiday_status_id.novelty == 'p'
            ]
            is_permission_day = bool(permission_leaves)

            if is_permission_day:
                permission_leave = permission_leaves[0]
                permission_line = next(
                    (line for line in permission_leave
                    if line.date == date_tmp and line.state in ['paid','validated']),
                    None
                )

            # Buscar ausencias
            absence_leaves = [
                leave for leave in rec.leave_ids.leave_id.line_ids
                if leave.date <= date_tmp <= leave.date and
                leave.leave_id.holiday_status_id.novelty not in ['vco', 'p'] and
                leave.leave_id.holiday_status_id.sub_wd
            ]

            is_absence_day = bool(absence_leaves)

            if is_absence_day:
                absence_leave = absence_leaves[0]
                absence_line = next(
                    (line for line in absence_leaves
                    if line.date == date_tmp and line.state in ['paid','validated']),
                    None
                )

            is_within_contract = rec.contract_id.date_start <= date_tmp <= (rec.contract_id.date_end or date_tmp)
            is_holiday = holiday_service.ensure_holidays(date_tmp)
            is_sunday = date_tmp.weekday() == 6
            is_saturday = date_tmp.weekday() == 5 and not rec.employee_id.sabado
            is_day_31 = date_tmp.day == 31

            wage_change_today = next(
                (change for change in wage_changes_sorted if change.date_start == date_tmp),
                None
            )
            if wage_change_today:
                current_wage_day = wage_change_today.wage / DAYS_MONTH

            if is_within_contract:
                if is_absence_day:
                    day_type = 'A'  # Ausencia
                elif is_permission_day:
                    day_type = 'P'  # Permiso (informativo, no resta días)
                elif is_holiday:
                    day_type = 'H'  # Feriado
                elif is_sunday:
                    day_type = 'D'  # Día de descanso (domingo)
                elif is_saturday:
                    day_type = 'S'  # Sábado
                else:
                    day_type = 'W'  # Trabajado

                payslip_day_data = {
                    'payslip_id': rec.id,
                    'day': date_tmp.day,
                    'day_type': day_type,
                    'is_holiday': is_holiday,
                    'is_sunday': is_sunday,
                    'is_saturday': is_saturday,
                    'is_permission': is_permission_day,
                    'is_absence': is_absence_day
                }

                if absence_line:
                    payslip_day_data['leave_line_id'] = absence_line.id
                elif permission_line:
                    payslip_day_data['leave_line_id'] = permission_line.id

                if is_day_31:
                    has_day_31 = True
                    apply_day_31 = any(
                        leave.date_from.date() <= date_tmp <= leave.date_to.date() and
                        leave.apply_day_31
                        for leave in rec.leave_ids.leave_id
                    )

                    if not apply_day_31:
                        payslip_day_data['is_day_31'] = True

                if date_tmp.month == 2:
                    last_day_of_february = calendar.monthrange(date_tmp.year, 2)[1]
                    if date_tmp.day == last_day_of_february:
                        payslip_day_data['is_feb_last'] = True

                        if date_tmp.day == 28:
                            payslip_day_data['feb_adjust'] = 2
                        else:  # día 29
                            payslip_day_data['feb_adjust'] = 1

                if day_type not in ['A', 'X']:
                    payslip_day_data['subtotal'] = current_wage_day

                payslip_day_ids.append(payslip_day_data)
            else:
                # NO agregar día 31 como fuera de contrato (mes comercial = 30 días)
                if date_tmp.day != 31:
                    payslip_day_ids.append({
                        'payslip_id': rec.id,
                        'day': date_tmp.day,
                        'day_type': 'X',
                        'is_holiday': is_holiday,
                        'is_sunday': is_sunday,
                        'is_saturday': is_saturday
                    })

            date_tmp += timedelta(days=1)

        if rec.period_id.type_period == "monthly" and not has_day_31:
            last_day = calendar.monthrange(rec.date_to.year, rec.date_to.month)[1]
            if last_day < 31:
                payslip_day_ids.append({
                    'payslip_id': rec.id,
                    'day': 31,
                    'day_type': 'V',
                    'is_virtual': True,
                    'is_day_31': True
                })

        rec.payslip_day_ids.create(payslip_day_ids)
        return True
