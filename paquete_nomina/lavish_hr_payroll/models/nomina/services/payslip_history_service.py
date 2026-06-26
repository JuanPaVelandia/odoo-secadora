# -*- coding: utf-8 -*-
"""
Servicio de Historial de Nómina
===============================

Gestiona la creación y actualización de registros históricos de prestaciones sociales.
Incluye:
- Historial de vacaciones (hr.vacation)
- Historial de cesantías (hr.history.cesantias)
- Historial de prima (hr.history.prima)
"""

import logging
from datetime import timedelta

_logger = logging.getLogger(__name__)


class PayslipHistoryService:
    """
    Servicio para gestionar registros históricos de prestaciones sociales.
    Extrae la lógica de historial de hr.payslip.
    """

    # Campos clave para cada modelo de historial
    HISTORY_KEY_FIELDS = {
        'hr.vacation': ['employee_id', 'contract_id', 'initial_accrual_date', 'final_accrual_date', 'leave_id'],
        'hr.history.cesantias': ['employee_id', 'contract_id', 'initial_accrual_date', 'final_accrual_date'],
        'hr.history.prima': ['employee_id', 'contract_id', 'initial_accrual_date', 'final_accrual_date'],
    }

    # Configuración de valores de vacaciones por código
    VACATION_CONFIGS = {
        'VACDISFRUTADAS': lambda record, line: {
            'departure_date': line.vacation_departure_date or record.date_from,
            'return_date': line.vacation_return_date or record.date_to,
            'business_units': line.business_units + line.business_31_units,
            'value_business_days': line.business_units * line.amount,
            'holiday_units': line.holiday_units + line.holiday_31_units,
            'holiday_value': round(line.holiday_units * line.amount),
            'base_value': line.amount_base,
            'total': round((line.business_units * line.amount) + (line.holiday_units * line.amount)),
            'leave_id': line.vacation_leave_id.id if line.vacation_leave_id else False,
        },
        'VACREMUNERADAS': lambda record, line: {
            'departure_date': record.date_from,
            'return_date': record.date_to,
            'units_of_money': line.quantity,
            'money_value': line.total,
            'base_value_money': line.amount_base,
            'total': line.total,
        },
        'VACATIONS_MONEY': lambda record, line: {
            'departure_date': record.date_from,
            'return_date': record.date_to,
            'units_of_money': line.quantity,
            'business_units': line.quantity,
            'money_value': line.total,
            'base_value_money': line.amount_base,
            'total': line.total,
            'leave_id': line.vacation_leave_id.id if line.vacation_leave_id else False,
        },
        'VACCONTRATO': lambda record, line: {
            'departure_date': record.date_liquidacion,
            'return_date': record.date_liquidacion,
            'units_of_money': line.quantity,
            'business_units': line.business_units or 0,
            'holiday_units': line.holiday_units or 0,
            'money_value': line.total,
            'base_value_money': line.amount,
            'total': line.total,
            'type': 'settlement',
        },
        'VAC_LIQ': lambda record, line: {
            'departure_date': record.date_liquidacion,
            'return_date': record.date_liquidacion,
            'units_of_money': line.quantity,
            'business_units': line.business_units or 0,
            'holiday_units': line.holiday_units or 0,
            'money_value': line.total,
            'base_value_money': line.amount,
            'total': line.total,
            'type': 'settlement',
        },
    }

    def __init__(self, payslip):
        """
        Args:
            payslip: hr.payslip record
        """
        self.payslip = payslip
        self.env = payslip.env
        self.employee_id = payslip.employee_id.id
        self.contract_id = payslip.contract_id.id

    def get_history_key_fields(self, model_name):
        """
        Obtiene los campos clave para un modelo de historial.

        Args:
            model_name: Nombre del modelo (hr.vacation, hr.history.cesantias, hr.history.prima)

        Returns:
            list: Lista de nombres de campos clave
        """
        return self.HISTORY_KEY_FIELDS.get(model_name, [])

    def create_or_update_history(self, model_name, values):
        """
        Crea o actualiza un registro de historial basado en campos clave.

        Args:
            model_name: Nombre del modelo de historial
            values: Diccionario con los valores a crear/actualizar

        Returns:
            record: Registro creado o actualizado
        """
        Model = self.env[model_name]
        key_fields = self.get_history_key_fields(model_name)

        domain = [
            (field, '=', values.get(field))
            for field in key_fields
            if values.get(field) is not False
        ]

        if domain:
            existing = Model.search(domain, limit=1)
            if existing:
                existing.write(values)
                return existing

        return Model.create(values)

    def get_vacation_values(self, line):
        """
        Obtiene valores de vacaciones según el código de línea.

        Args:
            line: hr.payslip.line record

        Returns:
            dict: Valores para crear/actualizar hr.vacation o None
        """
        record = self.payslip

        base_values = {
            'employee_id': self.employee_id,
            'contract_id': self.contract_id,
            'initial_accrual_date': line.initial_accrual_date,
            'final_accrual_date': line.final_accrual_date,
            'payslip': record.id,
        }

        config_func = self.VACATION_CONFIGS.get(line.code)
        if config_func:
            base_values.update(config_func(record, line))
            return base_values

        return None

    def get_severance_values(self, line_cesantias=None, line_interes=None):
        """
        Obtiene valores consolidados de cesantías e intereses.

        Args:
            line_cesantias: hr.payslip.line de cesantías (opcional)
            line_interes: hr.payslip.line de intereses (opcional)

        Returns:
            dict: Valores para crear/actualizar hr.history.cesantias
        """
        record = self.payslip
        values = {}

        if record.struct_id.process == 'contrato':
            date_from = record.date_cesantias
            date_to = record.date_liquidacion
        else:
            date_from = record.date_cesantias
            date_to = record.date_to

        if line_cesantias and not line_cesantias.is_history_reverse:
            values.update({
                'employee_id': self.employee_id,
                'contract_id': self.contract_id,
                'type_history': 'cesantias',
                'initial_accrual_date': date_from,
                'final_accrual_date': date_to,
                'settlement_date': date_to,
                'time': line_cesantias.quantity,
                'base_value': line_cesantias.amount_base,
                'severance_value': line_cesantias.total,
                'payslip': record.id,
            })

        if line_interes and not line_interes.is_history_reverse:
            if record.struct_id.process in ('cesantias', 'intereses_cesantias'):
                values.update({
                    'type_history': 'intcesantias',
                    'severance_interest_value': line_interes.total,
                })
            else:
                values.update({'severance_interest_value': line_interes.total})

        return values

    def process_history_lines(self):
        """
        Procesa todas las líneas de historial de la nómina.

        Incluye:
        - Vacaciones (nómina regular y liquidaciones)
        - Cesantías e intereses
        - Prima
        """
        record = self.payslip
        process_type = record.struct_id.process
        is_liquidacion = process_type == 'contrato' and record.date_liquidacion

        lines_by_code = {line.code: line for line in record.line_ids}

        # VACACIONES: Para nómina regular
        self._process_regular_vacations(record, lines_by_code)

        # VACACIONES LIQUIDACIÓN: Para liquidaciones de contrato
        if is_liquidacion:
            self._process_liquidation_vacations(record, lines_by_code)

        # CESANTÍAS E INTERESES: Solo para provisiones/procesos específicos
        if process_type in ('cesantias', 'intereses_cesantias', 'nomina'):
            self._process_severance(record, lines_by_code)

        # PRIMA: Solo para provisiones/procesos específicos
        if process_type in ('prima', 'nomina'):
            self._process_prima(record, lines_by_code)

    def _process_regular_vacations(self, record, lines_by_code):
        """Procesa vacaciones para nómina regular."""
        vacation_codes = ['VACDISFRUTADAS', 'VACREMUNERADAS', 'VACATIONS_MONEY']

        for code in vacation_codes:
            line = lines_by_code.get(code)
            if line and line.initial_accrual_date:
                values = self.get_vacation_values(line)
                if values:
                    values['type'] = 'normal'

                    if record.pay_vacations_in_payroll:
                        self.create_or_update_history('hr.vacation', values)
                    else:
                        self.env['hr.vacation'].create(values)

    def _process_liquidation_vacations(self, record, lines_by_code):
        """Procesa vacaciones para liquidaciones de contrato."""
        vacation_liq_codes = ['VAC_LIQ', 'VACCONTRATO']

        for code in vacation_liq_codes:
            line = lines_by_code.get(code)
            if line and line.total > 0:
                values = self.get_vacation_values(line)
                if values:
                    # Asegurar fechas de causación
                    if not values.get('initial_accrual_date'):
                        values['initial_accrual_date'] = record.date_vacaciones or record.contract_id.date_start
                    if not values.get('final_accrual_date'):
                        values['final_accrual_date'] = record.date_liquidacion

                    self.env['hr.vacation'].create(values)

    def _process_severance(self, record, lines_by_code):
        """Procesa cesantías e intereses."""
        ces_line = lines_by_code.get('CESANTIAS')
        int_line = lines_by_code.get('INTCESANTIAS')

        if ces_line or int_line:
            values = self.get_severance_values(ces_line, int_line)
            if values:
                values['type'] = 'normal'
                self.create_or_update_history('hr.history.cesantias', values)

    def _process_prima(self, record, lines_by_code):
        """Procesa prima de servicios."""
        prima_line = lines_by_code.get('PRIMA')

        if prima_line:
            date_from = record.date_prima
            date_to = record.date_to
            settlement_date = record.date_liquidacion if record.date_liquidacion else None

            values = {
                'employee_id': self.employee_id,
                'contract_id': self.contract_id,
                'initial_accrual_date': date_from,
                'final_accrual_date': date_to,
                'settlement_date': settlement_date,
                'time': prima_line.quantity,
                'base_value': prima_line.amount_base,
                'bonus_value': prima_line.total,
                'payslip': record.id,
                'type': 'normal',
            }
            self.create_or_update_history('hr.history.prima', values)

    def update_prima_cesantias_dates(self, slip_data):
        """
        Actualiza las fechas de prima y cesantías en la nómina.

        Args:
            slip_data: Diccionario con datos de la nómina
        """
        slip = self.payslip

        # Actualizar fecha de prima
        if slip_data['struct_process'] in ['prima', 'contrato'] or slip_data.get('pay_primas_in_payroll'):
            from_month = 1 if slip_data['date_from'].month <= 6 else 7
            date_from = slip_data['date_from'].replace(month=from_month, day=1)
            if date_from < slip.contract_id.date_start:
                date_from = slip.contract_id.date_start
            slip.date_prima = date_from

        # Actualizar fecha de cesantías
        if slip_data['struct_process'] in ['cesantias', 'contrato'] or slip_data.get('pay_cesantias_in_payroll'):
            date_ref = slip_data['date_to']
            date_from = date_ref.replace(month=1, day=1)
            if date_from < slip.contract_id.date_start:
                date_from = slip.contract_id.date_start
            slip.date_cesantias = date_from

    # =========================================================================
    # CONSULTA DE FECHAS DESDE HISTORIAL
    # =========================================================================

    def get_last_prima_date(self):
        """
        Obtiene la última fecha de causación de prima desde hr.history.prima.

        Returns:
            date: Última fecha de causación + 1 día, o fecha inicio contrato
        """
        contract_start = self.payslip.contract_id.date_start
        date_prima = contract_start

        historiales = self.env['hr.history.prima'].search([
            ('employee_id', '=', self.employee_id),
            ('contract_id', '=', self.contract_id),
        ], order='final_accrual_date asc')

        for history in historiales:
            if history.final_accrual_date and history.final_accrual_date > date_prima:
                date_prima = history.final_accrual_date + timedelta(days=1)

        return date_prima

    def get_last_vacation_date(self):
        """
        Obtiene la última fecha de causación de vacaciones desde hr.vacation.
        Solo considera vacaciones que no sean ausencias no remuneradas.

        Delega al método get_last_accrual_date del modelo hr.vacation.

        Returns:
            date: Última fecha de causación + 1 día, o fecha inicio contrato
        """
        # Usar método del modelo hr.vacation para obtener última fecha
        last_accrual_date = self.env['hr.vacation'].get_last_accrual_date(
            employee_id=self.employee_id,
            contract_id=self.contract_id,
            exclude_payslip_id=self.payslip.id
        )

        # Si hay fecha desde históricos, usarla; sino, fecha inicio de contrato
        if last_accrual_date:
            return last_accrual_date
        else:
            return self.payslip.contract_id.date_start

    def get_last_severance_date(self):
        """
        Obtiene la última fecha de causación de cesantías desde hr.history.cesantias.

        Returns:
            date: Última fecha de causación + 1 día, o fecha inicio contrato
        """
        contract_start = self.payslip.contract_id.date_start
        date_cesantias = contract_start

        historiales = self.env['hr.history.cesantias'].search([
            ('employee_id', '=', self.employee_id),
            ('contract_id', '=', self.contract_id),
        ], order='final_accrual_date asc')

        for history in historiales:
            if history.final_accrual_date and history.final_accrual_date > date_cesantias:
                date_cesantias = history.final_accrual_date + timedelta(days=1)

        return date_cesantias

    def load_liquidation_dates(self):
        """
        Carga las fechas para liquidación de contrato desde históricos.

        Solo se calculan las fechas que estén vacías (no sobrescribe valores manuales).
        Se usa en onchange del payslip cuando struct_id.process == 'contrato'.

        Returns:
            dict: Fechas calculadas {
                'date_liquidacion': date,
                'date_prima': date or None,
                'date_vacaciones': date or None,
                'date_cesantias': date or None,
            }
        """
        slip = self.payslip
        contract_start = slip.contract_id.date_start if slip.contract_id else False

        result = {
            'date_liquidacion': slip.date_to,
            'date_prima': None,
            'date_vacaciones': None,
            'date_cesantias': None,
        }

        # PRIMA: Solo calcular si NO tiene fecha previa
        if not slip.date_prima:
            try:
                result['date_prima'] = self.get_last_prima_date()
            except Exception:  # noqa: BLE001 – fallback a fecha inicio contrato
                _logger.warning("Error calculando fecha de prima en historial, usando inicio de contrato", exc_info=True)
                result['date_prima'] = contract_start

        # VACACIONES: Solo calcular si NO tiene fecha previa
        if not slip.date_vacaciones:
            try:
                result['date_vacaciones'] = self.get_last_vacation_date()
            except Exception:  # noqa: BLE001 – fallback a fecha inicio contrato
                _logger.warning("Error calculando fecha de vacaciones en historial, usando inicio de contrato", exc_info=True)
                result['date_vacaciones'] = contract_start

        # CESANTÍAS: Solo calcular si NO tiene fecha previa
        if not slip.date_cesantias:
            try:
                result['date_cesantias'] = self.get_last_severance_date()
            except Exception:  # noqa: BLE001 – fallback a fecha inicio contrato
                _logger.warning("Error calculando fecha de cesantías en historial, usando inicio de contrato", exc_info=True)
                result['date_cesantias'] = contract_start

        return result

    def apply_liquidation_dates(self):
        """
        Aplica las fechas de liquidación al payslip.
        Wrapper que llama a load_liquidation_dates y asigna los valores.
        """
        slip = self.payslip

        if not slip.struct_id or slip.struct_id.process != 'contrato':
            return

        try:
            dates = self.load_liquidation_dates()

            slip.date_liquidacion = dates['date_liquidacion']

            if dates['date_prima']:
                slip.date_prima = dates['date_prima']

            if dates['date_vacaciones']:
                slip.date_vacaciones = dates['date_vacaciones']

            if dates['date_cesantias']:
                slip.date_cesantias = dates['date_cesantias']

        except Exception:  # noqa: BLE001 – fallback seguro para fechas de liquidación
            _logger.warning("Error en apply_liquidation_dates para nómina %s, aplicando fallback con inicio de contrato", getattr(slip, 'name', '?'), exc_info=True)
            # Fallback: usar fecha inicio de contrato
            contract_start = slip.contract_id.date_start if slip.contract_id else False
            slip.date_liquidacion = slip.date_to

            if not slip.date_prima:
                slip.date_prima = contract_start
            if not slip.date_vacaciones:
                slip.date_vacaciones = contract_start
            if not slip.date_cesantias:
                slip.date_cesantias = contract_start

    # =========================================================================
    # ACTUALIZACIÓN DE VACACIONES EN NÓMINAS CONFIRMADAS
    # =========================================================================

    def update_vacation_data(self):
        """
        Actualiza los datos de vacaciones de una nómina ya confirmada,
        diferenciando entre vacaciones disfrutadas y vacaciones en dinero.

        Returns:
            dict: Resultado de la acción (notificación)
        """
        from datetime import timedelta
        from decimal import Decimal, ROUND_HALF_UP
        from odoo.exceptions import UserError
        from odoo import _

        slip = self.payslip

        if slip.state not in ('done', 'paid'):
            raise UserError(_("Solo se pueden actualizar datos de vacaciones en nóminas confirmadas."))

        vacation_lines = slip.line_ids.filtered(lambda line:
            line.code in ['VACATIONS_MONEY', 'VACDISFRUTADAS'] or
            (line.leave_id and (line.leave_id.holiday_status_id.is_vacation or
                                line.leave_id.holiday_status_id.is_vacation_money))
        )

        if not vacation_lines:
            raise UserError(_("No se encontraron líneas de vacaciones para actualizar."))

        leave_periods = [(line.leave_id.date_from, line.leave_id.date_to, line.leave_id.name)
                         for line in vacation_lines if line.leave_id]
        leave_periods.sort()

        for i in range(1, len(leave_periods)):
            if leave_periods[i - 1][1] >= leave_periods[i][0]:
                raise UserError(_(
                    "Se detectó un solapamiento entre períodos de vacaciones: %s (%s - %s) y %s (%s - %s). "
                    "Por favor, corrija las fechas antes de actualizar."
                ) % (
                    leave_periods[i - 1][2], leave_periods[i - 1][0].strftime('%d/%m/%Y'),
                    leave_periods[i - 1][1].strftime('%d/%m/%Y'),
                    leave_periods[i][2], leave_periods[i][0].strftime('%d/%m/%Y'),
                    leave_periods[i][1].strftime('%d/%m/%Y')
                ))

        last_accrual_end = {}
        vacation_lines_sorted = sorted(
            [line for line in vacation_lines if line.leave_id],
            key=lambda line: line.leave_id.date_from
        )

        Vac = self.env['hr.vacation']

        for line in vacation_lines_sorted:
            employee = slip.employee_id
            contract = slip.contract_id
            leave = line.leave_id

            is_money_vacation = line.code == 'VACATIONS_MONEY' or (
                leave.holiday_status_id.is_vacation_money if leave else False
            )

            concept = {
                'leave_id': leave,
                'date_from': leave.date_from,
                'date_to': leave.date_to,
                'days_work': line.business_units,
                'days_holiday': line.holiday_units,
                'days_31': line.business_31_units,
                'days_holiday_31': line.holiday_31_units,
            }

            if employee.id in last_accrual_end:
                start = last_accrual_end[employee.id] + timedelta(days=1)
            else:
                last_vacation = Vac.search(
                    [
                        ('employee_id', '=', employee.id),
                        ('payslip', '!=', slip.id),
                    ],
                    order='final_accrual_date desc', limit=1
                )
                if last_vacation and last_vacation.final_accrual_date:
                    start = last_vacation.final_accrual_date + timedelta(days=1)
                    if start < contract.date_start:
                        start = contract.date_start
                else:
                    start = contract.date_start

            # Calcular ausencias no pagadas
            domain = [
                ('state', '=', 'validate'),
                ('employee_id', '=', employee.id),
                ('unpaid_absences', '=', True),
                ('date_from', '>=', start),
                ('date_to', '<=', slip.date_to),
            ]
            dias_aus = sum(l.number_of_days for l in self.env['hr.leave'].search(domain))
            dias_aus += sum(h.days for h in self.env['hr.absence.history'].search([
                ('employee_id', '=', employee.id),
                ('leave_type_id.unpaid_absences', '=', True),
                ('star_date', '>=', start),
                ('end_date', '<=', slip.date_to),
            ]))

            dias_hab = concept['days_work']
            dias_fest = concept['days_holiday']
            dias_31_hab = concept['days_31']
            dias_31_fest = concept['days_holiday_31']

            dias_equiv = ((Decimal(dias_hab) + Decimal(dias_31_hab)) * Decimal(365)) / Decimal(15)
            dias_equiv = int(dias_equiv.quantize(0, rounding=ROUND_HALF_UP))

            end = start + timedelta(days=(dias_equiv + dias_aus) - 1)
            last_accrual_end[employee.id] = end

            disp = slip.get_holiday_book(contract, start)['days_left']
            dias_rest = max(disp - dias_hab, 0)

            amount_per_day = line.amount if line.amount else 0
            total_amount = line.total if line.total else 0

            import json
            from odoo.addons.lavish_hr_employee.models.payroll.hr_payslip_constants import json_serial

            vacation_log_data = {
                'tipo_vacaciones': 'En Dinero' if is_money_vacation else 'Disfrute',
                'periodo_inicio': concept['date_from'].strftime("%d/%m/%Y"),
                'periodo_fin': concept['date_to'].strftime("%d/%m/%Y"),
                'inicio_causacion': start.strftime("%d/%m/%Y"),
                'fin_causacion': end.strftime("%d/%m/%Y"),
                'dias_habiles': dias_hab,
                'dias_festivos': dias_fest,
                'dias_31_habiles': dias_31_hab,
                'dias_31_festivos': dias_31_fest,
                'equivalente_calendario': dias_equiv,
                'ausencias_no_pagadas': dias_aus,
                'disponibles_antes': disp,
                'restantes': dias_rest,
                'base_diaria': amount_per_day,
                'valor_total': total_amount,
            }

            line.write({
                'initial_accrual_date': start,
                'final_accrual_date': end,
                'vacation_departure_date': concept['date_from'],
                'vacation_return_date': concept['date_to'],
                'log_compute': json.dumps(vacation_log_data, default=json_serial),
                'business_units': dias_hab,
                'holiday_units': dias_fest,
                'business_31_units': dias_31_hab,
                'holiday_31_units': dias_31_fest,
            })

            vacation_values = {
                'employee_id': employee.id,
                'employee_identification': employee.identification_id,
                'leave_id': leave.id,
                'payslip': slip.id,
                'initial_accrual_date': start,
                'final_accrual_date': end,
                'departure_date': concept['date_from'],
                'return_date': concept['date_to'],
                'business_units': dias_hab,
                'holiday_units': dias_fest,
                'days_returned': 0,
                'contract_id': contract.id,
                'ibc_pila': self.env['hr.payslip.line'].search([
                    ('slip_id', '=', slip.id),
                    ('code', '=', 'IBD')
                ], limit=1).total or 0,
            }

            if is_money_vacation:
                vacation_values.update({
                    'base_value_money': round(amount_per_day * 30),
                    'units_of_money': dias_hab + dias_fest,
                    'money_value': round(total_amount),
                    'total': round(total_amount),
                    'description': 'Vacaciones en Dinero'
                })
            else:
                vacation_values.update({
                    'base_value': round(amount_per_day * 30),
                    'value_business_days': round(amount_per_day * dias_hab),
                    'holiday_value': round(amount_per_day * dias_fest),
                    'total': round(total_amount),
                    'description': 'Vacaciones Disfrutadas'
                })

            vacation_records = Vac.search([
                ('employee_id', '=', employee.id),
                ('payslip', '=', slip.id)
            ])

            if vacation_records:
                for vac_record in vacation_records:
                    vac_record.write(vacation_values)
            else:
                Vac.create(vacation_values)

        slip.message_post(
            body=_("Se actualizaron los datos de %d períodos de vacaciones (%d disfrutadas, %d en dinero).") % (
                len(vacation_lines_sorted),
                len([l for l in vacation_lines_sorted if l.code == 'VACDISFRUTADAS' or
                     (l.leave_id and l.leave_id.holiday_status_id.is_vacation and not l.leave_id.holiday_status_id.is_vacation_money)]),
                len([l for l in vacation_lines_sorted if l.code == 'VACATIONS_MONEY' or
                     (l.leave_id and l.leave_id.holiday_status_id.is_vacation_money)])
            ),
            subject=_("Actualización de Datos de Vacaciones")
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Éxito'),
                'message': _('Datos de vacaciones actualizados correctamente.'),
                'sticky': False,
            }
        }
