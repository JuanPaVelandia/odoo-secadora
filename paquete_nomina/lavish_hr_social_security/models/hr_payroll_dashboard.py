# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
from collections import defaultdict
import logging

_logger = logging.getLogger(__name__)


class HrPayrollDashboard(models.Model):
    """
    Modelo centralizado para la lógica del Dashboard de Nómina y RH.
    Integra datos de nóminas, seguridad social, ausencias, accidentes y más.
    """
    _name = 'hr.payroll.dashboard'
    _description = 'Dashboard de Nómina y Recursos Humanos'

    @api.model
    def get_dashboard_data(self, period_id=None, date_from=None, date_to=None, department_id=None):
        """
        Método principal para obtener todos los datos del dashboard.

        Args:
            period_id (int): ID del período seleccionado
            date_from (date): Fecha inicio (si no se usa período)
            date_to (date): Fecha fin (si no se usa período)
            department_id (int): ID del departamento para filtrar

        Returns:
            dict: Diccionario con todos los datos del dashboard
        """
        # Determinar el período
        if period_id:
            period = self.env['hr.period'].browse(period_id)
            date_from = period.date_start
            date_to = period.date_end
            period_name = period.name
            period_month = date_from.month
            period_year = date_from.year
        else:
            # Usar mes actual si no se especifica
            today = fields.Date.today()
            date_from = date_from or fields.Date.to_date(today.replace(day=1))
            date_to = date_to or (date_from + relativedelta(months=1, days=-1))
            period_name = date_from.strftime('%B %Y')
            period_month = date_from.month
            period_year = date_from.year

        # Construir el resultado
        result = {
            'period': {
                'id': period_id,
                'name': period_name,
                'date_from': fields.Date.to_string(date_from),
                'date_to': fields.Date.to_string(date_to),
                'month': period_month,
                'year': period_year,
                'is_prima_month': period_month in [6, 12],  # Junio o Diciembre
            },
            'kpis': self._get_kpis(date_from, date_to, department_id),
            'social_security': self._get_social_security_data(period_year, period_month, department_id),
            'batches': self._get_batches(date_from, date_to, department_id),
            'payslips': self._get_payslips(date_from, date_to, department_id),
            'charts': {
                'overtime_by_department': self._get_overtime_by_department(date_from, date_to),
                'accidents_chart': self._get_accidents_chart(date_from),
                'absences_by_type': self._get_absences_by_type(date_from, date_to, department_id),
            },
            'departments': self._get_departments(),
            'periods': self._get_available_periods(),
        }

        return result

    @api.model
    def _get_kpis(self, date_from, date_to, department_id=None):
        """Obtiene los KPIs principales del dashboard"""

        # Dominio base para empleados
        employee_domain = [
            ('active', '=', True),
            '|',
            ('departure_date', '=', False),
            ('departure_date', '>', date_to)
        ]
        if department_id:
            employee_domain.append(('department_id', '=', department_id))

        total_employees = self.env['hr.employee'].search_count(employee_domain)

        # Dominio base para nóminas
        payslip_domain = [
            ('date_from', '>=', date_from),
            ('date_to', '<=', date_to),
            ('state', 'in', ['done', 'paid'])
        ]
        if department_id:
            payslip_domain.append(('employee_id.department_id', '=', department_id))

        payslips = self.env['hr.payslip'].search(payslip_domain)

        # Total Devengado en el Período
        total_devengado = sum(payslips.mapped('line_ids').filtered(
            lambda l: l.category_id.code == 'DEV_SALARIAL' or
                     (l.category_id.parent_id and l.category_id.parent_id.code == 'DEV_SALARIAL')
        ).mapped('total'))

        # Total Nóminas del Mes
        total_payslips = len(payslips)
        total_payslip_amount = sum(payslips.mapped('net_amount'))

        # Accidentes Laborales en el Período
        accidents_count = 0
        if self.env['ir.model'].search([('model', '=', 'sst.accident')], limit=1):
            accident_domain = [
                ('date', '>=', date_from),
                ('date', '<=', date_to),
            ]
            if department_id:
                accident_domain.append(('employee_id.department_id', '=', department_id))

            accidents = self.env['sst.accident'].search(accident_domain)
            accidents_count = len(accidents)

        # Ausencias en el Período (hr.leave)
        leave_domain = [
            '|',
            '&', ('date_from', '>=', date_from), ('date_from', '<=', date_to),
            '&', ('date_to', '>=', date_from), ('date_to', '<=', date_to),
            ('state', '=', 'validate'),
        ]
        if department_id:
            leave_domain.append(('employee_id.department_id', '=', department_id))

        leaves = self.env['hr.leave'].search(leave_domain)
        total_leaves = len(leaves)
        total_leave_days = sum(leaves.mapped('number_of_days'))

        # Solicitudes Pendientes de Vacaciones/Ausencias
        pending_domain = [('state', '=', 'confirm')]
        if department_id:
            pending_domain.append(('employee_id.department_id', '=', department_id))

        pending_requests = self.env['hr.leave'].search_count(pending_domain)

        # Nuevos Empleados en el Período
        new_employee_domain = [
            ('first_contract_date', '>=', date_from),
            ('first_contract_date', '<=', date_to),
        ]
        if department_id:
            new_employee_domain.append(('department_id', '=', department_id))

        new_employees = self.env['hr.employee'].search_count(new_employee_domain)

        # Promedio de Horas Extras
        overtime_lines = payslips.mapped('worked_days_line_ids').filtered(
            lambda l: 'EXTRA' in (l.code or '').upper() or 'HE' in (l.code or '').upper()
        )
        total_overtime_hours = sum(overtime_lines.mapped('number_of_hours'))
        avg_overtime_hours = total_overtime_hours / total_employees if total_employees > 0 else 0

        return {
            'total_employees': {
                'value': total_employees,
            },
            'total_devengado': {
                'value': total_devengado,
                'formatted': self._format_currency(total_devengado),
            },
            'payslips_month': {
                'count': total_payslips,
                'value': total_payslip_amount,
                'formatted': self._format_currency(total_payslip_amount),
            },
            'accidents': {
                'value': accidents_count,
            },
            'absences': {
                'value': total_leaves,
                'days': total_leave_days,
            },
            'pending_requests': {
                'value': pending_requests,
            },
            'new_employees': {
                'value': new_employees,
            },
            'avg_overtime_hours': {
                'value': round(avg_overtime_hours, 1),
            }
        }

    @api.model
    def _get_social_security_data(self, year, month, department_id=None):
        """
        Obtiene datos de seguridad social desde hr.payroll.social.security.

        Args:
            year (int): Año del período
            month (int): Mes del período (1-12)
            department_id (int): ID del departamento (opcional)

        Returns:
            dict: Datos de seguridad social agrupados por entidad
        """
        # Buscar el registro de seguridad social para el año/mes
        ss_record = self.env['hr.payroll.social.security'].search([
            ('year', '=', year),
            ('month', '=', str(month)),
        ], limit=1)

        if not ss_record:
            return {
                'totals': {
                    'total': {'value': 0, 'formatted': '$0'},
                    'eps': {'value': 0, 'formatted': '$0'},
                    'afp': {'value': 0, 'formatted': '$0'},
                    'arl': {'value': 0, 'formatted': '$0'},
                    'ccf': {'value': 0, 'formatted': '$0'},
                },
                'by_entity': [],
                'state_label': 'Sin datos',
            }

        # TODO: Implementar lógica para obtener datos por departamento si es necesario
        # Por ahora retornamos datos globales del registro

        return {
            'totals': {
                'total': {
                    'value': ss_record.total_seguridad_social if 'total_seguridad_social' in ss_record._fields else 0,
                    'formatted': self._format_currency(getattr(ss_record, 'total_seguridad_social', 0)),
                },
            },
            'by_entity': [],
            'state_label': ss_record.state if 'state' in ss_record._fields else 'draft',
        }

    @api.model
    def _get_batches(self, date_from, date_to, department_id=None):
        """Obtiene lotes del período"""
        domain = [
            ('date_start', '>=', date_from),
            ('date_end', '<=', date_to)
        ]

        batches = self.env['hr.payslip.run'].search(domain, order='date_start desc', limit=10)

        result = []
        for batch in batches:
            # Filtrar por departamento si es necesario
            payslip_count = len(batch.slip_ids)
            if department_id:
                payslip_count = len(batch.slip_ids.filtered(
                    lambda p: p.employee_id.department_id.id == department_id
                ))

            result.append({
                'id': batch.id,
                'name': batch.name,
                'date_start': fields.Date.to_string(batch.date_start) if batch.date_start else False,
                'date_end': fields.Date.to_string(batch.date_end) if batch.date_end else False,
                'payslip_count': payslip_count,
                'state': batch.state,
            })

        return result

    @api.model
    def _get_payslips(self, date_from, date_to, department_id=None):
        """Obtiene nóminas del período"""
        domain = [
            ('date_from', '>=', date_from),
            ('date_to', '<=', date_to)
        ]

        if department_id:
            domain.append(('employee_id.department_id', '=', department_id))

        payslips = self.env['hr.payslip'].search(domain, order='date_from desc', limit=100)

        result = []
        for payslip in payslips:
            result.append({
                'id': payslip.id,
                'number': payslip.number,
                'name': payslip.name,
                'employee_id': payslip.employee_id.id,
                'employee_name': payslip.employee_id.name,
                'struct_name': payslip.struct_id.name,
                'date_from': fields.Date.to_string(payslip.date_from) if payslip.date_from else False,
                'date_to': fields.Date.to_string(payslip.date_to) if payslip.date_to else False,
                'total': payslip.net_amount,
                'formatted_total': self._format_currency(payslip.net_amount),
                'state': payslip.state,
            })

        return result

    @api.model
    def _get_overtime_by_department(self, date_from, date_to):
        """Obtiene horas extras agrupadas por departamento"""
        payslips = self.env['hr.payslip'].search([
            ('date_from', '>=', date_from),
            ('date_to', '<=', date_to),
            ('state', 'in', ['done', 'paid'])
        ])

        dept_overtime = {}
        for payslip in payslips:
            dept_name = payslip.employee_id.department_id.name or 'Sin Departamento'

            overtime_lines = payslip.worked_days_line_ids.filtered(
                lambda l: 'EXTRA' in (l.code or '').upper() or 'HE' in (l.code or '').upper()
            )
            hours = sum(overtime_lines.mapped('number_of_hours'))

            if dept_name not in dept_overtime:
                dept_overtime[dept_name] = 0
            dept_overtime[dept_name] += hours

        return {
            'labels': list(dept_overtime.keys()),
            'datasets': [{
                'label': 'Horas Extras',
                'data': list(dept_overtime.values()),
            }]
        }

    @api.model
    def _get_accidents_chart(self, date_from):
        """Obtiene datos de accidentes e incidentes de los últimos 6 meses"""
        months = []
        accidents_data = []
        incidents_data = []

        for i in range(5, -1, -1):
            month_date = date_from - relativedelta(months=i)
            month_start = month_date.replace(day=1)
            month_end = month_start + relativedelta(months=1, days=-1)
            month_label = month_date.strftime('%b')

            months.append(month_label)

            accidents_count = 0
            incidents_count = 0

            if self.env['ir.model'].search([('model', '=', 'sst.accident')], limit=1):
                # Accidentes graves
                accidents = self.env['sst.accident'].search([
                    ('date', '>=', month_start),
                    ('date', '<=', month_end),
                    ('severity', 'in', ['high', 'critical']),
                ])
                accidents_count = len(accidents)

                # Incidentes leves
                incidents = self.env['sst.accident'].search([
                    ('date', '>=', month_start),
                    ('date', '<=', month_end),
                    ('severity', 'in', ['low', 'medium']),
                ])
                incidents_count = len(incidents)

            accidents_data.append(accidents_count)
            incidents_data.append(incidents_count)

        return {
            'labels': months,
            'datasets': [
                {'label': 'Accidentes', 'data': accidents_data},
                {'label': 'Incidentes', 'data': incidents_data}
            ]
        }

    @api.model
    def _get_absences_by_type(self, date_from, date_to, department_id=None):
        """Obtiene ausencias agrupadas por tipo"""
        domain = [
            '|',
            '&', ('date_from', '>=', date_from), ('date_from', '<=', date_to),
            '&', ('date_to', '>=', date_from), ('date_to', '<=', date_to),
            ('state', '=', 'validate'),
        ]

        if department_id:
            domain.append(('employee_id.department_id', '=', department_id))

        leaves = self.env['hr.leave'].search(domain)

        type_days = {}
        for leave in leaves:
            leave_type = leave.holiday_status_id.name or 'Otro'
            days = leave.number_of_days

            if leave_type not in type_days:
                type_days[leave_type] = 0
            type_days[leave_type] += days

        return {
            'labels': list(type_days.keys()),
            'datasets': [{'data': list(type_days.values())}]
        }

    @api.model
    def _get_departments(self):
        """Obtiene lista de departamentos para el filtro"""
        departments = self.env['hr.department'].search([('active', '=', True)], order='name')

        return [{
            'id': dept.id,
            'name': dept.name,
        } for dept in departments]

    @api.model
    def _get_available_periods(self):
        """Obtiene períodos disponibles para el selector"""
        periods = self.env['hr.period'].search([], order='date_start desc', limit=12)

        return [{
            'id': period.id,
            'name': period.name,
            'date_start': fields.Date.to_string(period.date_start),
            'date_end': fields.Date.to_string(period.date_end),
        } for period in periods]

    @api.model
    def _format_currency(self, amount):
        """Formatea un monto como moneda colombiana"""
        if not amount:
            return '$0'
        return '${:,.0f}'.format(abs(amount)).replace(',', '.')
