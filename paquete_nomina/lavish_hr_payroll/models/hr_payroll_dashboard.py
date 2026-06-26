# -*- coding: utf-8 -*-
"""
Dashboard de Nómina - Lavish HR Payroll
Contiene toda la lógica para el dashboard web de nómina
"""

from odoo import models, fields, api
from dateutil.relativedelta import relativedelta
from collections import defaultdict
from .hr_slip_constante import CATEGORY_MAPPINGS


class HrPayslipDashboard(models.Model):
    """
    Modelo para la lógica del Dashboard de Nómina.

    Este modelo contiene todos los métodos para generar los datos
    que se muestran en el dashboard web de nómina, incluyendo:
    - KPIs principales
    - Datos de seguridad social
    - Lotes y nóminas del período
    - Gráficos de horas extras, accidentes y ausencias
    """
    _inherit = 'hr.payslip'

    @api.model
    def get_hr_dashboard_data(self, period_id=None, date_from=None, date_to=None, department_id=None, **kwargs):
        """
        Método principal para obtener todos los datos del dashboard HR.

        Args:
            period_id (int): ID del período seleccionado
            date_from (date): Fecha inicio (si no se usa período)
            date_to (date): Fecha fin (si no se usa período)
            department_id (int): ID del departamento para filtrar (opcional)
            **kwargs: Parámetros adicionales opcionales

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
            # Convertir strings a fechas si es necesario
            if date_from and isinstance(date_from, str):
                date_from = fields.Date.from_string(date_from)
            if date_to and isinstance(date_to, str):
                date_to = fields.Date.from_string(date_to)

            # Usar mes actual si no se especifica
            today = fields.Date.today()
            date_from = date_from or today.replace(day=1)
            date_to = date_to or (date_from + relativedelta(months=1, days=-1))
            period_name = date_from.strftime('%B %Y')
            period_month = date_from.month
            period_year = date_from.year

        # Obtener períodos disponibles (últimos 12 meses)
        periods = self.env['hr.period'].search([
            ('date_start', '>=', fields.Date.today() - relativedelta(months=12))
        ], order='date_start desc', limit=48)

        # Obtener departamentos activos
        departments = self.env['hr.department'].search([
            ('active', '=', True)
        ], order='name')

        result = {
            'company': self._get_dashboard_company_data(),
            'period': {
                'id': period_id,
                'name': period_name,
                'date_from': fields.Date.to_string(date_from),
                'date_to': fields.Date.to_string(date_to),
                'month': period_month,
                'year': period_year,
                'is_prima_month': period_month in [6, 12],  # Junio o Diciembre
            },
            'periods': [{'id': p.id, 'name': p.name} for p in periods],
            'departments': [{'id': d.id, 'name': d.name} for d in departments],
            'kpis': self._get_dashboard_kpis(date_from, date_to, department_id),
            'social_security': self._get_dashboard_social_security_real(period_year, period_month, department_id),
            'batches': self._get_dashboard_batches(date_from, date_to, department_id),
            'payslips': self._get_dashboard_payslips(date_from, date_to, department_id),
            'expiring_contracts': self._get_dashboard_expiring_contracts(date_from, 30, department_id),
            'payment_schedule': self._get_dashboard_payment_schedule(date_from, date_to, department_id),
            'new_employees': self._get_dashboard_new_employees(date_from, date_to, department_id),
            'pending_leaves': self._get_dashboard_pending_leaves(department_id),
            'payroll_summary': self._get_dashboard_payroll_summary(date_from, date_to, department_id),
            'charts': {
                'overtime_by_department': self._get_dashboard_overtime_by_department(date_from, date_to),
                'accidents_chart': self._get_dashboard_accidents_chart(date_from),
                'absences_by_type': self._get_dashboard_absences_by_type(date_from, date_to),
                'income_deductions': self._get_dashboard_income_deductions_chart(date_from, date_to, department_id),
                'disability_by_type': self._get_dashboard_disability_chart(date_from, date_to, department_id),
                'employees_by_city': self._get_dashboard_employees_by_city(date_from, date_to, department_id),
                'payroll_trend': self._get_dashboard_payroll_trend(date_from, date_to, department_id),
            }
        }

        return result

    @api.model
    def _get_dashboard_kpis(self, date_from, date_to, department_id=None):
        """Obtiene los KPIs principales del dashboard"""

        # Obtener la empresa actual del usuario
        company_id = self.env.company.id

        # Construir dominio base para filtros
        employee_domain = [
            ('active', '=', True),
            ('company_id', '=', company_id)
        ]
        if department_id:
            employee_domain.append(('department_id', '=', department_id))

        # Total Empleados Activos
        employee_domain.extend([
            '|',
            ('departure_date', '=', False),
            ('departure_date', '>', date_to)
        ])
        total_employees = self.env['hr.employee'].search_count(employee_domain)

        # Total Devengado en el Período
        payslip_domain = [
            ('date_from', '>=', date_from),
            ('date_to', '<=', date_to),
            ('state', 'in', ['done', 'paid']),
            ('company_id', '=', company_id)
        ]
        if department_id:
            payslip_domain.append(('employee_id.department_id', '=', department_id))

        payslips = self.search(payslip_domain)

        # Sumar líneas de categoría DEV_SALARIAL (devengos)
        total_devengado = sum(payslips.mapped('line_ids').filtered(
            lambda l: l.category_id.code == 'DEV_SALARIAL' or l.category_id.parent_id.code == 'DEV_SALARIAL'
        ).mapped('total'))

        # Total Nóminas del Mes
        total_payslips = len(payslips)
        total_payslip_amount = sum(payslips.mapped('net_amount'))

        # Accidentes Laborales en el Período
        # Usar hr.leave con novelty = 'irl' (Incapacidad por accidente de trabajo)
        accident_domain = [
            '|',
            '&', ('date_from', '>=', date_from), ('date_from', '<=', date_to),
            '&', ('date_to', '>=', date_from), ('date_to', '<=', date_to),
            ('state', '=', 'validate'),
            ('holiday_status_id.novelty', '=', 'irl'),
            ('employee_id.company_id', '=', company_id),
        ]
        if department_id:
            accident_domain.append(('employee_id.department_id', '=', department_id))
        accident_leaves = self.env['hr.leave'].search(accident_domain)
        accidents_count = len(accident_leaves)

        # Ausencias en el Período (hr.leave)
        leave_domain = [
            '|',
            '&', ('date_from', '>=', date_from), ('date_from', '<=', date_to),
            '&', ('date_to', '>=', date_from), ('date_to', '<=', date_to),
            ('state', '=', 'validate'),
            ('employee_id.company_id', '=', company_id),
        ]
        if department_id:
            leave_domain.append(('employee_id.department_id', '=', department_id))
        leaves = self.env['hr.leave'].search(leave_domain)
        total_leaves = len(leaves)
        total_leave_days = sum(leaves.mapped('number_of_days'))

        # Solicitudes Pendientes de Vacaciones
        pending_domain = [
            ('state', '=', 'confirm'),
            ('employee_id.company_id', '=', company_id),
        ]
        if department_id:
            pending_domain.append(('employee_id.department_id', '=', department_id))
        pending_requests = self.env['hr.leave'].search_count(pending_domain)

        # Nuevos Empleados en el Período
        new_emp_domain = [
            ('first_contract_date', '>=', date_from),
            ('first_contract_date', '<=', date_to),
            ('company_id', '=', company_id),
        ]
        if department_id:
            new_emp_domain.append(('department_id', '=', department_id))
        new_employees = self.env['hr.employee'].search_count(new_emp_domain)

        # Promedio de Horas Extras
        # Usar modelo hr.overtime con campo total_hours
        overtime_domain = [
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('state', '=', 'procesado'),  # Solo horas extras procesadas
            ('employee_id.company_id', '=', company_id),
        ]
        if department_id:
            overtime_domain.append(('employee_id.department_id', '=', department_id))
        overtimes = self.env['hr.overtime'].search(overtime_domain)
        total_overtime_hours = sum(overtimes.mapped('total_hours'))
        avg_overtime_hours = total_overtime_hours / total_employees if total_employees > 0 else 0

        # Retenciones en la Fuente (Período Actual)
        # Buscar líneas con categoría RTEFTE o reglas específicas de retención
        retention_rule_codes = ['RT_MET_01', 'RET_PRIMA', 'RTF_INDEM', 'RETFTE001', 'RETFTE_PRIMA001']
        retention_lines = payslips.mapped('line_ids').filtered(
            lambda l: l.category_id.code == 'RTEFTE' or
                      l.category_id.parent_id.code == 'RTEFTE' or
                      l.salary_rule_id.code in retention_rule_codes
        )
        total_retention_base = sum(retention_lines.mapped('amount'))  # Base de retención
        total_retention = abs(sum(retention_lines.mapped('total')))   # Monto retenido (valor absoluto)

        # Retenciones en la Fuente (Período Anterior) para comparación
        from dateutil.relativedelta import relativedelta
        prev_date_from = date_from - relativedelta(months=1)
        prev_date_to = date_to - relativedelta(months=1)

        prev_payslip_domain = [
            ('date_from', '>=', prev_date_from),
            ('date_to', '<=', prev_date_to),
            ('state', 'in', ['done', 'paid']),
            ('company_id', '=', company_id),
        ]
        if department_id:
            prev_payslip_domain.append(('employee_id.department_id', '=', department_id))

        prev_payslips = self.search(prev_payslip_domain)
        prev_retention_lines = prev_payslips.mapped('line_ids').filtered(
            lambda l: l.category_id.code == 'RTEFTE' or
                      l.category_id.parent_id.code == 'RTEFTE' or
                      l.salary_rule_id.code in retention_rule_codes
        )
        prev_total_retention_base = sum(prev_retention_lines.mapped('amount'))
        prev_total_retention = abs(sum(prev_retention_lines.mapped('total')))

        # Calcular cambio porcentual
        retention_base_change = 0
        retention_change = 0
        if prev_total_retention_base > 0:
            retention_base_change = ((total_retention_base - prev_total_retention_base) / prev_total_retention_base) * 100
        if prev_total_retention > 0:
            retention_change = ((total_retention - prev_total_retention) / prev_total_retention) * 100

        def _employee_summary(records):
            result = []
            for employee in records:
                result.append({
                    'id': employee.id,
                    'name': employee.name,
                    'identification': employee.identification_id,
                    'department': employee.department_id.name if employee.department_id else 'Sin Departamento',
                    'job_title': employee.job_id.name if employee.job_id else 'Sin Cargo',
                })
            return result

        # KPI: Empleados sin Seguridad Social
        # Buscar registro de seguridad social del período
        period_month = date_from.month
        period_year = date_from.year
        ss_record = self.env['hr.payroll.social.security'].search([
            ('year', '=', period_year),
            ('month', '=', str(period_month)),
            ('company_id', '=', self.env.company.id)
        ], limit=1)

        employees_without_ss = 0
        employees_without_ss_list = []
        if ss_record:
            # Empleados en seguridad social
            ss_employee_ids = ss_record.executing_social_security_ids.mapped('employee_id').ids
            # Empleados activos del dominio base que NO están en SS
            all_active_employees = self.env['hr.employee'].search(employee_domain)
            employees_without_ss_records = all_active_employees.filtered(lambda e: e.id not in ss_employee_ids)
            employees_without_ss = len(employees_without_ss_records)
            employees_without_ss_list = employees_without_ss_records.ids
        else:
            # Si no hay registro de SS, todos los activos están sin SS
            all_active_employees = self.env['hr.employee'].search(employee_domain)
            employees_without_ss = len(all_active_employees)
            employees_without_ss_list = all_active_employees.ids
            employees_without_ss_records = all_active_employees

        # KPI: Empleados sin Nómina en el Período
        # Empleados activos que NO tienen nómina en el período
        payslip_employee_ids = payslips.mapped('employee_id').ids
        all_active_employees = self.env['hr.employee'].search(employee_domain)
        employees_without_payslip = all_active_employees.filtered(lambda e: e.id not in payslip_employee_ids)
        employees_without_payslip_count = len(employees_without_payslip)
        employees_without_payslip_list = employees_without_payslip.ids

        # KPI: Empleados sin Liquidación (contrato terminado sin liquidar)
        # Buscar empleados con departure_date <= date_to y sin liquidación
        terminated_domain = [
            ('departure_date', '!=', False),
            ('departure_date', '<=', date_to),
            ('active', 'in', [True, False]),  # Incluir inactivos también
            ('company_id', '=', company_id),
        ]
        if department_id:
            terminated_domain.append(('department_id', '=', department_id))

        terminated_employees = self.env['hr.employee'].search(terminated_domain)

        # Verificar cuáles tienen liquidación
        # Una liquidación es una nómina con estructura tipo "Liquidación"
        employees_without_settlement = []
        for employee in terminated_employees:
            # Buscar nóminas de liquidación para este empleado
            settlement_payslips = self.env['hr.payslip'].search([
                ('employee_id', '=', employee.id),
                ('struct_id.name', 'ilike', 'liquidación'),  # Estructura con "liquidación" en el nombre
                ('state', 'in', ['done', 'paid']),
                ('company_id', '=', company_id),
            ], limit=1)

            if not settlement_payslips:
                employees_without_settlement.append(employee.id)

        employees_without_settlement_count = len(employees_without_settlement)
        employees_without_settlement_records = self.env['hr.employee'].browse(employees_without_settlement)

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
                'change': 0,  # TODO: calcular cambio vs período anterior
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
            },
            'retention_base': {
                'value': total_retention_base,
                'formatted': self._format_currency(total_retention_base),
                'prev_value': prev_total_retention_base,
                'prev_formatted': self._format_currency(prev_total_retention_base),
                'change': round(retention_base_change, 1),
            },
            'retention_total': {
                'value': total_retention,
                'formatted': self._format_currency(total_retention),
                'prev_value': prev_total_retention,
                'prev_formatted': self._format_currency(prev_total_retention),
                'change': round(retention_change, 1),
            },
            'employees_without_ss': {
                'value': employees_without_ss,
                'employee_ids': employees_without_ss_list,
                'employees': _employee_summary(employees_without_ss_records),
                'severity': 'danger' if employees_without_ss > 0 else 'success',
            },
            'employees_without_payslip': {
                'value': employees_without_payslip_count,
                'employee_ids': employees_without_payslip_list,
                'employees': _employee_summary(employees_without_payslip),
                'severity': 'warning' if employees_without_payslip_count > 0 else 'success',
            },
            'employees_without_settlement': {
                'value': employees_without_settlement_count,
                'employee_ids': employees_without_settlement,
                'employees': _employee_summary(employees_without_settlement_records),
                'severity': 'danger' if employees_without_settlement_count > 0 else 'success',
            }
        }

    @api.model
    def _get_dashboard_social_security_real(self, year, month, department_id=None):
        """
        Obtiene datos REALES de seguridad social desde el modelo hr.payroll.social.security.

        Esta es la implementación correcta que usa los datos del módulo lavish_hr_social_security
        en lugar de intentar calcularlos desde las líneas de nómina.

        Args:
            year (int): Año del período
            month (int): Mes del período (1-12)
            department_id (int): ID del departamento para filtrar (opcional)

        Returns:
            dict: Datos de seguridad social por tipo y entidad
        """
        # Buscar registro de seguridad social para este período
        company_id = self.env.company.id
        ss_record = self.env['hr.payroll.social.security'].search([
            ('year', '=', year),
            ('month', '=', str(month)),
            ('company_id', '=', company_id)
        ], limit=1)

        if not ss_record:
            # No hay datos de seguridad social para este período
            return {
                'exists': False,
                'period': f"{month}/{year}",
                'state': 'no_data',
                'chart_data': {
                    'labels': ['EPS', 'AFP', 'ARL', 'CCF'],
                    'values': [0, 0, 0, 0],
                    'percentages': [0, 0, 0, 0],
                },
                'totals': {
                    'eps': {'value': 0, 'formatted': '$0'},
                    'afp': {'value': 0, 'formatted': '$0'},
                    'arl': {'value': 0, 'formatted': '$0'},
                    'ccf': {'value': 0, 'formatted': '$0'},
                    'total': {'value': 0, 'formatted': '$0'},
                },
                'detail_by_entity': [],
            }

        # Obtener líneas filtradas si hay departamento
        lines_to_process = ss_record.executing_social_security_ids
        if department_id:
            lines_to_process = lines_to_process.filtered(lambda l: l.employee_id.department_id.id == department_id)

        # Calcular totales basándose en las líneas (filtradas o no)
        if department_id and lines_to_process:
            # Recalcular totales para el departamento
            eps_total = sum(lines_to_process.mapped('nValorSaludTotal'))
            afp_total = sum(lines_to_process.mapped('nValorPensionTotal'))
            arl_total = sum(lines_to_process.mapped('nValorARP'))
            ccf_total = sum(lines_to_process.mapped('nValorCajaCom'))
        else:
            # Usar totales del registro principal
            eps_total = ss_record.total_health or 0
            afp_total = ss_record.total_pension or 0
            arl_total = ss_record.total_arl or 0
            ccf_total = ss_record.total_parafiscal or 0  # Incluye CCF + SENA + ICBF

        grand_total = eps_total + afp_total + arl_total + ccf_total

        # Calcular porcentajes
        eps_pct = round((eps_total / grand_total) * 100, 1) if grand_total > 0 else 0
        afp_pct = round((afp_total / grand_total) * 100, 1) if grand_total > 0 else 0
        arl_pct = round((arl_total / grand_total) * 100, 1) if grand_total > 0 else 0
        ccf_pct = round((ccf_total / grand_total) * 100, 1) if grand_total > 0 else 0

        # Obtener detalle por entidad desde las líneas
        detail_by_entity = []

        # Agrupar por entidad EPS
        eps_by_entity = {}
        afp_by_entity = {}
        arl_by_entity = {}
        ccf_by_entity = {}

        # Usar las líneas ya filtradas
        for line in lines_to_process:
            # EPS
            eps_entity = line.TerceroEPS.name if line.TerceroEPS else 'Sin EPS'
            if eps_entity not in eps_by_entity:
                eps_by_entity[eps_entity] = {
                    'entity_name': eps_entity,
                    'type': 'EPS',
                    'value': 0,
                    'employees': 0,
                }
            eps_by_entity[eps_entity]['value'] += line.nValorSaludTotal or 0
            eps_by_entity[eps_entity]['employees'] += 1

            # AFP
            afp_entity = line.TerceroPension.name if line.TerceroPension else 'Sin AFP'
            if afp_entity not in afp_by_entity:
                afp_by_entity[afp_entity] = {
                    'entity_name': afp_entity,
                    'type': 'AFP',
                    'value': 0,
                    'employees': 0,
                }
            afp_by_entity[afp_entity]['value'] += line.nValorPensionTotal or 0
            afp_by_entity[afp_entity]['employees'] += 1

            # ARL
            arl_entity = line.TerceroARP.name if line.TerceroARP else 'Sin ARL'
            if arl_entity not in arl_by_entity:
                arl_by_entity[arl_entity] = {
                    'entity_name': arl_entity,
                    'type': 'ARL',
                    'value': 0,
                    'employees': 0,
                }
            arl_by_entity[arl_entity]['value'] += line.nValorARP or 0
            arl_by_entity[arl_entity]['employees'] += 1

            # CCF (Caja de Compensación)
            ccf_entity = line.TerceroCajaCom.name if line.TerceroCajaCom else 'Sin CCF'
            if ccf_entity not in ccf_by_entity:
                ccf_by_entity[ccf_entity] = {
                    'entity_name': ccf_entity,
                    'type': 'CCF',
                    'value': 0,
                    'employees': 0,
                }
            ccf_by_entity[ccf_entity]['value'] += line.nValorCajaCom or 0
            ccf_by_entity[ccf_entity]['employees'] += 1

        # Consolidar todas las entidades
        for entity_data in eps_by_entity.values():
            detail_by_entity.append({
                'entity_name': entity_data['entity_name'],
                'type': 'EPS',
                'value': entity_data['value'],
                'formatted_value': self._format_currency(entity_data['value']),
                'employees': entity_data['employees'],
            })

        for entity_data in afp_by_entity.values():
            detail_by_entity.append({
                'entity_name': entity_data['entity_name'],
                'type': 'AFP',
                'value': entity_data['value'],
                'formatted_value': self._format_currency(entity_data['value']),
                'employees': entity_data['employees'],
            })

        for entity_data in arl_by_entity.values():
            detail_by_entity.append({
                'entity_name': entity_data['entity_name'],
                'type': 'ARL',
                'value': entity_data['value'],
                'formatted_value': self._format_currency(entity_data['value']),
                'employees': entity_data['employees'],
            })

        for entity_data in ccf_by_entity.values():
            detail_by_entity.append({
                'entity_name': entity_data['entity_name'],
                'type': 'CCF',
                'value': entity_data['value'],
                'formatted_value': self._format_currency(entity_data['value']),
                'employees': entity_data['employees'],
            })

        # Mapeo de estados
        state_labels = {
            'draft': 'Borrador',
            'done': 'Realizado',
            'accounting': 'Contabilizado',
        }

        # Obtener datos del mes anterior para comparación
        from dateutil.relativedelta import relativedelta
        from datetime import date as dt_date
        prev_date = dt_date(year, month, 1) - relativedelta(months=1)
        prev_year = prev_date.year
        prev_month = prev_date.month

        prev_ss_record = self.env['hr.payroll.social.security'].search([
            ('year', '=', prev_year),
            ('month', '=', str(prev_month)),
            ('company_id', '=', company_id)
        ], limit=1)

        # Calcular totales del mes anterior
        prev_eps_total = 0
        prev_afp_total = 0
        prev_arl_total = 0
        prev_ccf_total = 0
        prev_grand_total = 0

        if prev_ss_record:
            prev_lines_to_process = prev_ss_record.executing_social_security_ids
            if department_id:
                prev_lines_to_process = prev_lines_to_process.filtered(lambda l: l.employee_id.department_id.id == department_id)

            if department_id and prev_lines_to_process:
                prev_eps_total = sum(prev_lines_to_process.mapped('nValorSaludTotal'))
                prev_afp_total = sum(prev_lines_to_process.mapped('nValorPensionTotal'))
                prev_arl_total = sum(prev_lines_to_process.mapped('nValorARP'))
                prev_ccf_total = sum(prev_lines_to_process.mapped('nValorCajaCom'))
            else:
                prev_eps_total = prev_ss_record.total_health or 0
                prev_afp_total = prev_ss_record.total_pension or 0
                prev_arl_total = prev_ss_record.total_arl or 0
                prev_ccf_total = prev_ss_record.total_parafiscal or 0

            prev_grand_total = prev_eps_total + prev_afp_total + prev_arl_total + prev_ccf_total

        # Calcular cambios porcentuales
        eps_change = ((eps_total - prev_eps_total) / prev_eps_total * 100) if prev_eps_total > 0 else 0
        afp_change = ((afp_total - prev_afp_total) / prev_afp_total * 100) if prev_afp_total > 0 else 0
        arl_change = ((arl_total - prev_arl_total) / prev_arl_total * 100) if prev_arl_total > 0 else 0
        ccf_change = ((ccf_total - prev_ccf_total) / prev_ccf_total * 100) if prev_ccf_total > 0 else 0
        total_change = ((grand_total - prev_grand_total) / prev_grand_total * 100) if prev_grand_total > 0 else 0

        return {
            'exists': True,
            'period': f"{month}/{year}",
            'prev_period': f"{prev_month}/{prev_year}",
            'state': ss_record.state,
            'state_label': state_labels.get(ss_record.state, ss_record.state),
            'chart_data': {
                'labels': ['EPS', 'AFP', 'ARL', 'CCF'],
                'values': [eps_total, afp_total, arl_total, ccf_total],
                'percentages': [eps_pct, afp_pct, arl_pct, ccf_pct],
            },
            'totals': {
                'eps': {
                    'value': eps_total,
                    'formatted': self._format_currency(eps_total),
                    'prev_value': prev_eps_total,
                    'prev_formatted': self._format_currency(prev_eps_total),
                    'change': round(eps_change, 1),
                },
                'afp': {
                    'value': afp_total,
                    'formatted': self._format_currency(afp_total),
                    'prev_value': prev_afp_total,
                    'prev_formatted': self._format_currency(prev_afp_total),
                    'change': round(afp_change, 1),
                },
                'arl': {
                    'value': arl_total,
                    'formatted': self._format_currency(arl_total),
                    'prev_value': prev_arl_total,
                    'prev_formatted': self._format_currency(prev_arl_total),
                    'change': round(arl_change, 1),
                },
                'ccf': {
                    'value': ccf_total,
                    'formatted': self._format_currency(ccf_total),
                    'prev_value': prev_ccf_total,
                    'prev_formatted': self._format_currency(prev_ccf_total),
                    'change': round(ccf_change, 1),
                },
                'total': {
                    'value': grand_total,
                    'formatted': self._format_currency(grand_total),
                    'prev_value': prev_grand_total,
                    'prev_formatted': self._format_currency(prev_grand_total),
                    'change': round(total_change, 1),
                },
            },
            'detail_by_entity': detail_by_entity,
        }

    @api.model
    def _get_dashboard_batches(self, date_from, date_to, department_id=None):
        """Obtiene lotes del período"""

        batch_domain = [
            '|',
            '&', ('date_start', '>=', date_from), ('date_start', '<=', date_to),
            '&', ('date_end', '>=', date_from), ('date_end', '<=', date_to),
            ('company_id', '=', self.env.company.id),
        ]

        batches = self.env['hr.payslip.run'].search(batch_domain, order='date_start desc')

        # Si hay filtro de departamento, filtrar batches que tengan nóminas de ese departamento
        if department_id:
            batches = batches.filtered(
                lambda b: any(p.employee_id.department_id.id == department_id for p in b.slip_ids)
            )

        # Mapeo de estados de lotes (Odoo nativo)
        batch_state_labels = {
            'draft': 'Borrador',
            'verify': 'Verificar',
            'close': 'Cerrado',
            'paid': 'Pagado',
        }

        result = []
        for batch in batches:
            total_amount = sum(batch.slip_ids.mapped('net_wage'))
            result.append({
                'id': batch.id,
                'name': batch.name,
                'number': batch.number or f"LOT-{batch.id}",
                'date_start': fields.Date.to_string(batch.date_start) if batch.date_start else False,
                'date_end': fields.Date.to_string(batch.date_end) if batch.date_end else False,
                'employee_count': len(batch.slip_ids.mapped('employee_id')),
                'payslip_count': len(batch.slip_ids),
                'total_amount': total_amount,
                'formatted_amount': self._format_currency(total_amount),
                'state': batch.state,
                'state_label': batch_state_labels.get(batch.state, batch.state),
            })

        return result

    @api.model
    def _get_dashboard_payslips(self, date_from, date_to, department_id=None):
        """Obtiene nóminas del período"""

        payslip_domain = [
            ('date_from', '>=', date_from),
            ('date_to', '<=', date_to),
            ('company_id', '=', self.env.company.id),
        ]
        if department_id:
            payslip_domain.append(('employee_id.department_id', '=', department_id))

        payslips = self.search(payslip_domain, order='date_from desc', limit=100)

        # Mapeo de estados de nóminas (Odoo nativo)
        payslip_state_labels = {
            'draft': 'Borrador',
            'verify': 'En Espera',
            'done': 'Hecho',
            'paid': 'Pagado',
            'cancel': 'Cancelado',
        }

        result = []
        for payslip in payslips:
            # Obtener valores específicos de las líneas de nómina
            salud = 0
            pension = 0
            auxilio = 0
            sueldo = 0
            retencion = 0
            prestamos = 0
            otras_deducciones = 0

            for line in payslip.line_ids:
                code = (line.code or '').upper()
                category_code = (line.category_id.code or '').upper()
                rule_code = (line.salary_rule_id.code or '').upper()

                # Salud - SSOCIAL001
                if code == 'SSOCIAL001' or rule_code == 'SSOCIAL001':
                    salud += abs(line.total)

                # Pensión - SSOCIAL002
                elif code == 'SSOCIAL002' or rule_code == 'SSOCIAL002':
                    pension += abs(line.total)

                # Retención en la fuente - RT_MET_01, RET_PRIMA, RTF_INDEM
                elif code in ['RT_MET_01', 'RET_PRIMA', 'RTF_INDEM'] or rule_code in ['RT_MET_01', 'RET_PRIMA', 'RTF_INDEM']:
                    retencion += abs(line.total)

                # Préstamos
                elif 'PRESTAMO' in code or 'LOAN' in code or 'PRESTAMO' in category_code:
                    prestamos += abs(line.total)

                # Auxilio de transporte - AUX000
                elif code == 'AUX000' or rule_code == 'AUX000':
                    auxilio += line.total

                # Sueldo básico - BASIC, BASIC002, BASIC003
                elif code in ['BASIC', 'BASIC002', 'BASIC003'] or rule_code in ['BASIC', 'BASIC002', 'BASIC003']:
                    sueldo += line.total

                # Otras deducciones (incluye FONDO SOLIDARIDAD y FONDO SUBSISTENCIA)
                elif (('DED' in category_code or 'DEDU' in category_code or
                       code in ['SSOCIAL003', 'SSOCIAL004'] or
                       rule_code in ['SSOCIAL003', 'SSOCIAL004']) and line.total < 0):
                    otras_deducciones += abs(line.total)

            # Calcular días trabajados
            dias_trabajados = sum(payslip.worked_days_line_ids.mapped('number_of_days'))

            # Obtener imagen del empleado en base64
            employee_image = False
            if payslip.employee_id.image_128:
                employee_image = payslip.employee_id.image_128.decode('utf-8') if isinstance(payslip.employee_id.image_128, bytes) else payslip.employee_id.image_128

            result.append({
                'id': payslip.id,
                'number': payslip.number,
                'name': payslip.name,
                'employee_id': payslip.employee_id.id,
                'employee_name': payslip.employee_id.name,
                'employee_image': employee_image,
                'struct_name': payslip.struct_id.name,
                'date_from': fields.Date.to_string(payslip.date_from) if payslip.date_from else False,
                'date_to': fields.Date.to_string(payslip.date_to) if payslip.date_to else False,
                'total': payslip.net_wage,
                'formatted_total': self._format_currency(payslip.net_wage),
                'state': payslip.state,
                'state_label': payslip_state_labels.get(payslip.state, payslip.state),
                # Nuevos campos
                'salud': salud,
                'formatted_salud': self._format_currency(salud),
                'pension': pension,
                'formatted_pension': self._format_currency(pension),
                'auxilio': auxilio,
                'formatted_auxilio': self._format_currency(auxilio),
                'sueldo': sueldo,
                'formatted_sueldo': self._format_currency(sueldo),
                'retencion': retencion,
                'formatted_retencion': self._format_currency(retencion),
                'prestamos': prestamos,
                'formatted_prestamos': self._format_currency(prestamos),
                'otras_deducciones': otras_deducciones,
                'formatted_otras_deducciones': self._format_currency(otras_deducciones),
                'dias_trabajados': dias_trabajados,
                'neto': payslip.net_wage,
                'formatted_neto': self._format_currency(payslip.net_wage),
            })

        return result

    @api.model
    def _get_dashboard_overtime_by_department(self, date_from, date_to):
        """Obtiene horas extras agrupadas por departamento"""

        payslips = self.search([
            ('date_from', '>=', date_from),
            ('date_to', '<=', date_to),
            ('state', 'in', ['done', 'paid']),
            ('company_id', '=', self.env.company.id),
        ])

        # Agrupar horas extras por departamento
        dept_overtime = {}
        for payslip in payslips:
            dept_name = payslip.employee_id.department_id.name or 'Sin Departamento'

            # Obtener horas extras de las líneas trabajadas
            overtime_lines = payslip.worked_days_line_ids.filtered(
                lambda l: 'EXTRA' in (l.code or '').upper() or 'HE' in (l.code or '').upper()
            )
            hours = sum(overtime_lines.mapped('number_of_hours'))

            if dept_name not in dept_overtime:
                dept_overtime[dept_name] = 0
            dept_overtime[dept_name] += hours

        # Convertir a formato de gráfico
        labels = list(dept_overtime.keys())
        data = list(dept_overtime.values())

        return {
            'labels': labels,
            'datasets': [{
                'label': 'Horas Extras',
                'data': data,
            }]
        }

    @api.model
    def _get_dashboard_accidents_chart(self, date_from):
        """Obtiene datos de accidentes e incidentes de los últimos 6 meses"""

        # Calcular fechas de los últimos 6 meses
        months = []
        accidents_data = []
        incidents_data = []

        for i in range(5, -1, -1):
            month_date = date_from - relativedelta(months=i)
            month_start = month_date.replace(day=1)
            month_end = month_start + relativedelta(months=1, days=-1)
            month_label = month_date.strftime('%b')

            months.append(month_label)

            # Contar accidentes si el modelo existe
            accidents_count = 0
            incidents_count = 0

            if self.env['ir.model'].search([('model', '=', 'sst.accident')], limit=1):
                # Accidentes
                accidents = self.env['sst.accident'].search([
                    ('date_accident', '>=', month_start),
                    ('date_accident', '<=', month_end),
                    ('severity_general', 'in', ['disability', 'permanent_disability', 'death']),  # Solo graves
                ])
                accidents_count = len(accidents)

                # Incidentes (menos graves)
                incidents = self.env['sst.accident'].search([
                    ('date_accident', '>=', month_start),
                    ('date_accident', '<=', month_end),
                    ('severity_general', 'in', ['minor', 'medical']),  # Leves
                ])
                incidents_count = len(incidents)

            accidents_data.append(accidents_count)
            incidents_data.append(incidents_count)

        return {
            'labels': months,
            'datasets': [
                {
                    'label': 'Accidentes',
                    'data': accidents_data,
                },
                {
                    'label': 'Incidentes',
                    'data': incidents_data,
                }
            ]
        }

    @api.model
    def _get_dashboard_absences_by_type(self, date_from, date_to):
        """Obtiene ausencias agrupadas por tipo"""

        leaves = self.env['hr.leave'].search([
            '|',
            '&', ('date_from', '>=', date_from), ('date_from', '<=', date_to),
            '&', ('date_to', '>=', date_from), ('date_to', '<=', date_to),
            ('state', '=', 'validate'),
            ('employee_id.company_id', '=', self.env.company.id),
        ])

        # Agrupar por tipo
        type_days = {}
        for leave in leaves:
            leave_type = leave.holiday_status_id.name or 'Otro'
            days = leave.number_of_days

            if leave_type not in type_days:
                type_days[leave_type] = 0
            type_days[leave_type] += days

        # Convertir a formato de gráfico
        labels = list(type_days.keys())
        data = list(type_days.values())

        return {
            'labels': labels,
            'datasets': [{
                'data': data,
            }]
        }

    @api.model
    def _get_dashboard_company_data(self):
        """Retorna datos basicos de la compania para el dashboard"""

        company = self.env.company
        logo_url = f"/web/image/res.company/{company.id}/logo"

        return {
            'id': company.id,
            'name': company.name,
            'logo_url': logo_url,
            'currency_symbol': company.currency_id.symbol if company.currency_id else '',
            'currency_position': company.currency_id.position if company.currency_id else 'after',
        }

    @api.model
    def _get_dashboard_payroll_trend(self, date_from, date_to, department_id=None):
        """Obtiene tendencia de nomina neta para los ultimos 6 meses"""

        company_id = self.env.company.id
        labels = []
        totals = []

        for i in range(5, -1, -1):
            month_date = date_from - relativedelta(months=i)
            month_start = month_date.replace(day=1)
            month_end = month_start + relativedelta(months=1, days=-1)

            payslip_domain = [
                ('date_from', '>=', month_start),
                ('date_to', '<=', month_end),
                ('state', 'in', ['done', 'paid']),
                ('company_id', '=', company_id),
            ]
            if department_id:
                payslip_domain.append(('employee_id.department_id', '=', department_id))

            payslips = self.search(payslip_domain)
            total = sum(payslips.mapped('net_amount'))

            labels.append(month_date.strftime('%b'))
            totals.append(total)

        current_total = totals[-1] if totals else 0
        prev_total = totals[-2] if len(totals) > 1 else 0

        change = 0
        if prev_total:
            change = ((current_total - prev_total) / prev_total) * 100

        return {
            'labels': labels,
            'datasets': [{
                'label': 'Nomina neta',
                'data': totals,
            }],
            'current_total': current_total,
            'prev_total': prev_total,
            'formatted_current': self._format_currency(current_total),
            'formatted_prev': self._format_currency(prev_total),
            'change': round(change, 1),
        }

    @api.model
    def _get_dashboard_employees_by_city(self, date_from, date_to, department_id=None):
        """Obtiene empleados agrupados por ciudad"""

        payslip_domain = [
            ('date_from', '>=', date_from),
            ('date_to', '<=', date_to),
            ('state', 'in', ['done', 'paid']),
            ('company_id', '=', self.env.company.id),
        ]
        if department_id:
            payslip_domain.append(('employee_id.department_id', '=', department_id))

        payslips = self.search(payslip_domain)
        employees = payslips.mapped('employee_id')

        city_counts = defaultdict(int)
        for employee in employees:
            city_name = (
                employee.private_city_id.name
                if employee.private_city_id
                else (employee.private_city or 'Sin ciudad')
            )
            city_counts[city_name] += 1

        total = sum(city_counts.values())
        cities = sorted(
            [{'name': name, 'count': count} for name, count in city_counts.items()],
            key=lambda item: (-item['count'], item['name'])
        )

        for city in cities:
            city['percent'] = round((city['count'] / total) * 100, 1) if total else 0

        return {
            'total': total,
            'cities': cities,
        }

    @api.model
    def _get_dashboard_income_deductions_chart(self, date_from, date_to, department_id=None):
        """Obtiene gráfico de ingresos (devengos) vs deducciones"""

        payslip_domain = [
            ('date_from', '>=', date_from),
            ('date_to', '<=', date_to),
            ('state', 'in', ['done', 'paid'])
        ]
        if department_id:
            payslip_domain.append(('employee_id.department_id', '=', department_id))

        payslips = self.search(payslip_domain)

        # Debug: verificar cuántos payslips se encontraron
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info(f"Dashboard: Encontrados {len(payslips)} payslips entre {date_from} y {date_to}")

        # Agrupar por CATEGORÍA primero, luego por REGLA
        # {category_code: {'name': name, 'total': value, 'rules': {rule_code: {...}}}}
        categories_grouped = {}

        for payslip in payslips:
            # Filtrar líneas: buscar líneas de DETALLE (no totales)
            for line in payslip.line_ids:
                # Verificar que tenga regla y categoría
                if not line.salary_rule_id or not line.category_id:
                    continue

                # Verificar que la secuencia sea menor a 300 (líneas de detalle)
                if line.salary_rule_id.sequence >= 300:
                    continue

                # Verificar que sea imprimible
                if not line.salary_rule_id.appears_on_payslip:
                    continue

                # EXCLUIR totales (queremos ver el detalle)
                if line.category_id.code in ['TOTALDEV', 'TOTALDED', 'NETO']:
                    continue

                # Obtener información de la línea
                rule_code = line.salary_rule_id.code
                rule_name = line.salary_rule_id.name
                category_code = line.category_id.code
                category_name = line.category_id.name

                # Inicializar categoría si no existe
                if category_code not in categories_grouped:
                    categories_grouped[category_code] = {
                        'name': category_name,
                        'code': category_code,
                        'total': 0,
                        'rules': {}
                    }

                # Inicializar regla dentro de la categoría si no existe
                if rule_code not in categories_grouped[category_code]['rules']:
                    categories_grouped[category_code]['rules'][rule_code] = {
                        'name': rule_name,
                        'code': rule_code,
                        'total': 0,
                        'employees': {}
                    }

                # Obtener valor (las deducciones pueden ser negativas)
                value = abs(line.total)

                # Sumar al total de la regla
                categories_grouped[category_code]['rules'][rule_code]['total'] += value

                # Sumar al total de la categoría
                categories_grouped[category_code]['total'] += value

                # Agregar detalle por empleado
                employee = payslip.employee_id
                rule_ref = categories_grouped[category_code]['rules'][rule_code]

                if employee.id not in rule_ref['employees']:
                    rule_ref['employees'][employee.id] = {
                        'id': employee.id,
                        'name': employee.name,
                        'total': 0,
                        'lines': []
                    }

                rule_ref['employees'][employee.id]['total'] += value
                rule_ref['employees'][employee.id]['lines'].append({
                    'id': line.id,
                    'name': line.name,
                    'code': line.code,
                    'value': value,
                    'formatted': self._format_currency(value)
                })

        # Debug: verificar categorías y reglas encontradas
        _logger.info(f"Dashboard: Categorías encontradas: {list(categories_grouped.keys())}")
        for cat_code, cat_data in categories_grouped.items():
            _logger.info(f"  {cat_code} ({cat_data['name']}): {cat_data['total']} - {len(cat_data['rules'])} reglas")
            for rule_code, rule_data in cat_data['rules'].items():
                _logger.info(f"    → {rule_code}: {rule_data['total']} ({len(rule_data['employees'])} empleados)")

        # Preparar datos para gráfico separando devengos y deducciones
        income_categories_list = []  # Lista de categorías de devengos
        deduction_categories_list = []  # Lista de categorías de deducciones

        # Usar constantes del sistema para clasificación
        earnings_categories = CATEGORY_MAPPINGS.get('EARNINGS', [])
        deduction_categories = CATEGORY_MAPPINGS.get('DEDUCTIONS', [])

        # Procesar todas las categorías encontradas
        for category_code, category_data in sorted(categories_grouped.items(), key=lambda x: x[1]['total'], reverse=True):
            # Preparar lista de reglas dentro de esta categoría
            rules_list = []

            for rule_code, rule_data in sorted(category_data['rules'].items(), key=lambda x: x[1]['total'], reverse=True):
                # Preparar lista de empleados con porcentajes
                employees_list = []
                for emp_id, emp_data in rule_data['employees'].items():
                    percentage = (emp_data['total'] / rule_data['total'] * 100) if rule_data['total'] > 0 else 0
                    employees_list.append({
                        'id': emp_data['id'],
                        'name': emp_data['name'],
                        'value': emp_data['total'],
                        'formatted': self._format_currency(emp_data['total']),
                        'percentage': round(percentage, 1),
                        'lines': emp_data['lines']
                    })

                # Agregar regla a la lista
                rules_list.append({
                    'name': rule_data['name'],
                    'code': rule_code,
                    'value': rule_data['total'],
                    'formatted': self._format_currency(rule_data['total']),
                    'employees': employees_list,
                })

            # Crear objeto de categoría con sus reglas
            category_item = {
                'name': category_data['name'],
                'code': category_code,
                'value': category_data['total'],
                'formatted': self._format_currency(category_data['total']),
                'rules': rules_list,
            }

            # Clasificar según si es devengo o deducción
            is_income = category_code in earnings_categories

            if is_income:
                income_categories_list.append(category_item)
            else:  # Es deducción
                deduction_categories_list.append(category_item)

        # Calcular totales
        total_income = sum(cat['value'] for cat in income_categories_list)
        total_deductions = sum(cat['value'] for cat in deduction_categories_list)

        return {
            'income': {
                'categories': income_categories_list,  # Lista de categorías, cada una con sus reglas
                'total': total_income,
                'formatted_total': self._format_currency(total_income),
            },
            'deductions': {
                'categories': deduction_categories_list,  # Lista de categorías, cada una con sus reglas
                'total': total_deductions,
                'formatted_total': self._format_currency(total_deductions),
            },
            'net': {
                'value': total_income - total_deductions,
                'formatted': self._format_currency(total_income - total_deductions),
            }
        }

    @api.model
    def _get_dashboard_expiring_contracts(self, date_from=None, days_threshold=30, department_id=None):
        """
        Obtiene contratos próximos a vencer

        Args:
            date_from: Fecha de referencia (por defecto hoy)
            days_threshold: Días de anticipación para alertar (por defecto 30)
            department_id: Filtrar por departamento
        """
        if not date_from:
            date_from = fields.Date.today()

        date_limit = date_from + relativedelta(days=days_threshold)

        contract_domain = [
            ('state', '=', 'open'),  # Solo contratos activos
            ('date_end', '!=', False),  # Que tengan fecha fin
            ('date_end', '>=', date_from),  # Que no hayan vencido
            ('date_end', '<=', date_limit),  # Que venzan en el período
            ('company_id', '=', self.env.company.id),
        ]

        if department_id:
            contract_domain.append(('employee_id.department_id', '=', department_id))

        contracts = self.env['hr.contract'].search(contract_domain, order='date_end asc')

        result = []
        for contract in contracts:
            days_remaining = (contract.date_end - date_from).days

            # Nivel de urgencia
            if days_remaining <= 7:
                urgency = 'critical'
                urgency_label = 'Crítico'
            elif days_remaining <= 15:
                urgency = 'high'
                urgency_label = 'Alto'
            elif days_remaining <= 30:
                urgency = 'medium'
                urgency_label = 'Medio'
            else:
                urgency = 'low'
                urgency_label = 'Bajo'

            result.append({
                'id': contract.id,
                'employee_id': contract.employee_id.id,
                'employee_name': contract.employee_id.name,
                'employee_identification': contract.employee_id.identification_id,
                'department': contract.employee_id.department_id.name if contract.employee_id.department_id else 'Sin Departamento',
                'contract_type': contract.contract_type_id.name if contract.contract_type_id else 'Sin Tipo',
                'date_start': fields.Date.to_string(contract.date_start),
                'date_end': fields.Date.to_string(contract.date_end),
                'days_remaining': days_remaining,
                'urgency': urgency,
                'urgency_label': urgency_label,
                'wage': contract.wage,
                'formatted_wage': self._format_currency(contract.wage),
            })

        return {
            'total': len(result),
            'critical': len([c for c in result if c['urgency'] == 'critical']),
            'high': len([c for c in result if c['urgency'] == 'high']),
            'medium': len([c for c in result if c['urgency'] == 'medium']),
            'contracts': result,
        }

    @api.model
    def _get_dashboard_payment_schedule(self, date_from, date_to, department_id=None):
        """
        Obtiene la programación de pagos del período

        Retorna lotes de nómina agrupados por fecha de pago programada
        """
        batch_domain = [
            '|',
            '&', ('date_start', '>=', date_from), ('date_start', '<=', date_to),
            '&', ('date_end', '>=', date_from), ('date_end', '<=', date_to),
            ('company_id', '=', self.env.company.id),
        ]

        batches = self.env['hr.payslip.run'].search(batch_domain, order='date_end asc')

        if department_id:
            batches = batches.filtered(
                lambda b: any(p.employee_id.department_id.id == department_id for p in b.slip_ids)
            )

        # Agrupar por fecha de pago (usar date_end como fecha de pago)
        schedule_by_date = {}
        total_scheduled = 0

        for batch in batches:
            if batch.state in ['draft', 'close']:  # Solo lotes no pagados
                payment_date = batch.date_end
                if payment_date:
                    date_key = fields.Date.to_string(payment_date)

                    if date_key not in schedule_by_date:
                        schedule_by_date[date_key] = {
                            'date': date_key,
                            'date_formatted': payment_date.strftime('%d/%m/%Y'),
                            'batches': [],
                            'total_amount': 0,
                            'total_employees': 0,
                        }

                    batch_amount = sum(batch.slip_ids.mapped('net_wage'))
                    schedule_by_date[date_key]['batches'].append({
                        'id': batch.id,
                        'name': batch.name,
                        'state': batch.state,
                        'amount': batch_amount,
                        'formatted_amount': self._format_currency(batch_amount),
                        'employee_count': len(batch.slip_ids.mapped('employee_id')),
                    })
                    schedule_by_date[date_key]['total_amount'] += batch_amount
                    schedule_by_date[date_key]['total_employees'] += len(batch.slip_ids.mapped('employee_id'))
                    total_scheduled += batch_amount

        # Formatear totales
        for date_data in schedule_by_date.values():
            date_data['formatted_total'] = self._format_currency(date_data['total_amount'])

        # Convertir a lista ordenada por fecha
        schedule_list = sorted(schedule_by_date.values(), key=lambda x: x['date'])

        return {
            'total_scheduled': total_scheduled,
            'formatted_total': self._format_currency(total_scheduled),
            'payment_dates_count': len(schedule_list),
            'schedule': schedule_list,
        }

    @api.model
    def _get_dashboard_disability_chart(self, date_from, date_to, department_id=None):
        """
        Obtiene gráfico de incapacidades por tipo y días del período

        Agrupa las incapacidades (hr.leave) por tipo de novedad:
        - IGE: Incapacidad por Enfermedad General
        - IRL: Incapacidad por Accidente Laboral (Riesgo Laboral)
        - LMA: Licencia de Maternidad
        - LPA: Licencia de Paternidad
        etc.
        """
        # Buscar ausencias validadas en el período que sean incapacidades
        leave_domain = [
            '|',
            '&', ('date_from', '>=', date_from), ('date_from', '<=', date_to),
            '&', ('date_to', '>=', date_from), ('date_to', '<=', date_to),
            ('state', '=', 'validate'),
            ('holiday_status_id.novelty', '!=', False),  # Solo con novedad (incapacidades)
            ('employee_id.company_id', '=', self.env.company.id),
        ]
        if department_id:
            leave_domain.append(('employee_id.department_id', '=', department_id))

        leaves = self.env['hr.leave'].search(leave_domain)

        # Agrupar por tipo de incapacidad
        disability_by_type = {}
        disability_count_by_type = {}

        for leave in leaves:
            novelty_code = leave.holiday_status_id.novelty
            leave_type_name = leave.holiday_status_id.name
            days = leave.number_of_days

            # Mapeo de códigos de novedad a nombres descriptivos
            novelty_labels = {
                'ige': 'Inc. Enfermedad General',
                'irl': 'Inc. Accidente Laboral',
                'lma': 'Lic. Maternidad',
                'lpa': 'Lic. Paternidad',
                'vac': 'Vacaciones',
                'vr': 'Vacaciones Remuneradas',
                'lic': 'Licencia',
            }

            # Usar nombre descriptivo si existe, si no usar el nombre del tipo
            display_name = novelty_labels.get(novelty_code.lower() if novelty_code else '', leave_type_name)

            if display_name not in disability_by_type:
                disability_by_type[display_name] = 0
                disability_count_by_type[display_name] = 0

            disability_by_type[display_name] += days
            disability_count_by_type[display_name] += 1

        # Ordenar por días (mayor a menor)
        sorted_items = sorted(disability_by_type.items(), key=lambda x: x[1], reverse=True)

        labels = [item[0] for item in sorted_items]
        days_data = [item[1] for item in sorted_items]
        count_data = [disability_count_by_type[label] for label in labels]

        # Calcular totales
        total_days = sum(days_data)
        total_cases = sum(count_data)

        # Obtener datos del período anterior para calcular tendencia
        from datetime import date as dt_date
        prev_date_from = date_from - relativedelta(months=1)
        prev_date_to = date_to - relativedelta(months=1)

        prev_leave_domain = [
            '|',
            '&', ('date_from', '>=', prev_date_from), ('date_from', '<=', prev_date_to),
            '&', ('date_to', '>=', prev_date_from), ('date_to', '<=', prev_date_to),
            ('state', '=', 'validate'),
            ('holiday_status_id.novelty', '!=', False),
            ('employee_id.company_id', '=', self.env.company.id),
        ]
        if department_id:
            prev_leave_domain.append(('employee_id.department_id', '=', department_id))

        prev_leaves = self.env['hr.leave'].search(prev_leave_domain)

        # Agrupar datos del período anterior por tipo
        prev_disability_by_type = {}
        for leave in prev_leaves:
            novelty_code = leave.holiday_status_id.novelty
            leave_type_name = leave.holiday_status_id.name
            days = leave.number_of_days

            novelty_labels = {
                'ige': 'Inc. Enfermedad General',
                'irl': 'Inc. Accidente Laboral',
                'lma': 'Lic. Maternidad',
                'lpa': 'Lic. Paternidad',
                'vac': 'Vacaciones',
                'vr': 'Vacaciones Remuneradas',
                'lic': 'Licencia',
            }

            display_name = novelty_labels.get(novelty_code.lower() if novelty_code else '', leave_type_name)

            if display_name not in prev_disability_by_type:
                prev_disability_by_type[display_name] = 0

            prev_disability_by_type[display_name] += days

        # Preparar detalle por tipo
        detail = []
        types_found = []  # Lista de códigos de tipos encontrados

        # Mapeo inverso para obtener el código del nombre
        name_to_code = {
            'Inc. Enfermedad General': 'IGE',
            'Inc. Accidente Laboral': 'IRL',
            'Lic. Maternidad': 'LMA',
            'Lic. Paternidad': 'LPA',
            'Vacaciones': 'VAC',
            'Vacaciones Remuneradas': 'VR',
            'Licencia': 'LIC',
        }

        # Mapeo de códigos de novedad a códigos de reglas salariales
        novelty_to_rule_codes = {
            'IGE': ['IGE', 'IGE001', 'IGE002', 'IGE_RECOBRO'],
            'IRL': ['IRL', 'IRL001', 'IRL002', 'IRL_RECOBRO'],
            'LMA': ['LMA', 'LMA001', 'LMA002'],
            'LPA': ['LPA', 'LPA001', 'LPA002'],
            'VAC': ['VAC', 'VAC001', 'VACATION'],
            'VR': ['VAC', 'VAC001', 'VACATION'],
            'LIC': ['LIC', 'LIC001', 'LICENSE'],
        }

        # Íconos Font Awesome por tipo
        type_icons = {
            'IGE': 'fa-medkit',
            'IRL': 'fa-ambulance',
            'LMA': 'fa-female',
            'LPA': 'fa-child',
            'VAC': 'fa-plane',
            'VR': 'fa-plane',
            'LIC': 'fa-file-alt',
        }

        # Colores por tipo
        type_colors = {
            'IGE': 'text-info',      # Azul
            'IRL': 'text-danger',    # Rojo
            'LMA': 'text-purple',    # Morado
            'LPA': 'text-primary',   # Azul primario
            'VAC': 'text-success',   # Verde
            'VR': 'text-success',    # Verde
            'LIC': 'text-warning',   # Amarillo
        }

        for i, label in enumerate(labels):
            code = name_to_code.get(label, '')
            icon = type_icons.get(code, 'fa-file-o')
            color = type_colors.get(code, 'text-muted')

            # Calcular tendencia comparando con período anterior
            current_days = days_data[i]
            prev_days = prev_disability_by_type.get(label, 0)
            trend = 0
            if prev_days > 0:
                trend = round(((current_days - prev_days) / prev_days) * 100, 1)

            # Buscar reglas de nómina relacionadas con este tipo de incapacidad
            rule_codes_to_search = novelty_to_rule_codes.get(code, [])
            related_rules = []

            if rule_codes_to_search:
                # Buscar líneas de nómina del período con estos códigos
                payslip_lines = self.env['hr.payslip.line'].search([
                    ('date_from', '>=', date_from),
                    ('date_from', '<=', date_to),
                    ('slip_id.state', 'in', ['done', 'paid']),
                    ('salary_rule_id.code', 'in', rule_codes_to_search),
                    ('slip_id.company_id', '=', self.env.company.id),
                ])

                # Agrupar por regla
                rules_by_code = {}
                for line in payslip_lines:
                    rule_code = line.salary_rule_id.code
                    if rule_code not in rules_by_code:
                        rules_by_code[rule_code] = {
                            'code': rule_code,
                            'name': line.salary_rule_id.name,
                            'amount': 0,
                            'cases': 0,
                        }
                    rules_by_code[rule_code]['amount'] += line.total
                    rules_by_code[rule_code]['cases'] += 1

                # Convertir a lista
                for rule_data in rules_by_code.values():
                    related_rules.append({
                        'code': rule_data['code'],
                        'name': rule_data['name'],
                        'amount': self._format_currency(rule_data['amount']),
                        'cases': rule_data['cases'],
                    })

            detail.append({
                'name': label,  # Nombre descriptivo del tipo
                'code': code,
                'icon': icon,
                'color': color,
                'days': days_data[i],
                'cases': count_data[i],
                'percentage': round((days_data[i] / total_days * 100), 1) if total_days > 0 else 0,
                'trend': trend,  # Tendencia vs período anterior
                'prev_days': prev_days,  # Días del período anterior
                'rules': related_rules,  # Reglas de nómina relacionadas
            })

            if code:
                types_found.append(code)

        # Metadata de tipos para el frontend
        type_metadata = {
            'IGE': {'label': 'Inc. Enfermedad General', 'icon': 'fa-medkit', 'color': 'text-info'},
            'IRL': {'label': 'Inc. Accidente Laboral', 'icon': 'fa-ambulance', 'color': 'text-danger'},
            'LMA': {'label': 'Lic. Maternidad', 'icon': 'fa-female', 'color': 'text-purple'},
            'LPA': {'label': 'Lic. Paternidad', 'icon': 'fa-child', 'color': 'text-primary'},
            'VAC': {'label': 'Vacaciones', 'icon': 'fa-plane', 'color': 'text-success'},
            'LIC': {'label': 'Licencia', 'icon': 'fa-file-alt', 'color': 'text-warning'},
        }

        return {
            'labels': labels,
            'datasets': [
                {
                    'label': 'Días de Incapacidad',
                    'data': days_data,
                },
                {
                    'label': 'Número de Casos',
                    'data': count_data,
                }
            ],
            'total_days': total_days,
            'total_cases': total_cases,
            'detail': detail,
            'types_found': types_found,  # Códigos de tipos encontrados ['IGE', 'IRL', ...]
            'type_metadata': type_metadata,  # Metadata completa de cada tipo
            'has_ige': 'IGE' in types_found,
            'has_irl': 'IRL' in types_found,
            'has_lma': 'LMA' in types_found,
            'has_lpa': 'LPA' in types_found,
            'has_vac': 'VAC' in types_found or 'VR' in types_found,
            'has_lic': 'LIC' in types_found,
        }

    @api.model
    def _get_dashboard_new_employees(self, date_from, date_to, department_id=None):
        """
        Obtiene lista detallada de empleados nuevos en el período

        Args:
            date_from: Fecha inicio del período
            date_to: Fecha fin del período
            department_id: Filtrar por departamento
        """
        employee_domain = [
            ('first_contract_date', '>=', date_from),
            ('first_contract_date', '<=', date_to),
            ('company_id', '=', self.env.company.id),
        ]
        if department_id:
            employee_domain.append(('department_id', '=', department_id))

        new_employees = self.env['hr.employee'].search(employee_domain, order='first_contract_date desc')

        result = []
        for employee in new_employees:
            # Obtener contrato actual
            current_contract = employee.contract_id

            result.append({
                'id': employee.id,
                'name': employee.name,
                'identification_id': employee.identification_id,
                'department': employee.department_id.name if employee.department_id else 'Sin Departamento',
                'job_title': employee.job_id.name if employee.job_id else 'Sin Cargo',
                'first_contract_date': fields.Date.to_string(employee.first_contract_date) if employee.first_contract_date else False,
                'first_contract_date_formatted': employee.first_contract_date.strftime('%d/%m/%Y') if employee.first_contract_date else '',
                'contract_type': current_contract.contract_type_id.name if current_contract and current_contract.contract_type_id else 'Sin Tipo',
                'wage': current_contract.wage if current_contract else 0,
                'formatted_wage': self._format_currency(current_contract.wage) if current_contract else '$0',
                'work_email': employee.work_email or '',
                'mobile_phone': employee.mobile_phone or '',
            })

        return {
            'total': len(result),
            'employees': result,
        }

    @api.model
    def _get_dashboard_pending_leaves(self, department_id=None):
        """
        Obtiene licencias/ausencias pendientes de aprobar (sin conciliar)

        Retorna todas las solicitudes en estado 'confirm' (pendiente de aprobación)
        """
        leave_domain = [
            ('state', '=', 'confirm'),  # Pendientes de aprobar
            ('employee_id.company_id', '=', self.env.company.id),
        ]
        if department_id:
            leave_domain.append(('employee_id.department_id', '=', department_id))

        pending_leaves = self.env['hr.leave'].search(leave_domain, order='date_from desc')

        result = []
        for leave in pending_leaves:
            # Calcular días de antigüedad de la solicitud (request_date_from es tipo date)
            request_age_days = (fields.Date.today() - leave.request_date_from).days if leave.request_date_from else 0

            # Nivel de urgencia basado en antigüedad
            if request_age_days > 7:
                urgency = 'high'
                urgency_label = 'Alta'
            elif request_age_days > 3:
                urgency = 'medium'
                urgency_label = 'Media'
            else:
                urgency = 'low'
                urgency_label = 'Baja'

            result.append({
                'id': leave.id,
                'employee_id': leave.employee_id.id,
                'employee_name': leave.employee_id.name,
                'employee_identification': leave.employee_id.identification_id,
                'department': leave.employee_id.department_id.name if leave.employee_id.department_id else 'Sin Departamento',
                'leave_type': leave.holiday_status_id.name,
                'leave_type_code': leave.holiday_status_id.code if leave.holiday_status_id.code else '',
                'date_from': fields.Date.to_string(leave.date_from) if leave.date_from else False,
                'date_to': fields.Date.to_string(leave.date_to) if leave.date_to else False,
                'date_from_formatted': leave.date_from.strftime('%d/%m/%Y') if leave.date_from else '',
                'date_to_formatted': leave.date_to.strftime('%d/%m/%Y') if leave.date_to else '',
                'number_of_days': leave.number_of_days,
                'request_date': fields.Date.to_string(leave.request_date_from) if leave.request_date_from else False,
                'request_date_formatted': leave.request_date_from.strftime('%d/%m/%Y') if leave.request_date_from else '',
                'request_age_days': request_age_days,
                'urgency': urgency,
                'urgency_label': urgency_label,
                'notes': leave.name or '',
            })

        # Agrupar por tipo de licencia para estadísticas
        by_type = {}
        for leave in result:
            leave_type = leave['leave_type']
            if leave_type not in by_type:
                by_type[leave_type] = {
                    'type': leave_type,
                    'count': 0,
                    'total_days': 0,
                }
            by_type[leave_type]['count'] += 1
            by_type[leave_type]['total_days'] += leave['number_of_days']

        return {
            'total': len(result),
            'high_urgency': len([l for l in result if l['urgency'] == 'high']),
            'medium_urgency': len([l for l in result if l['urgency'] == 'medium']),
            'low_urgency': len([l for l in result if l['urgency'] == 'low']),
            'by_type': list(by_type.values()),
            'leaves': result,
        }

    @api.model
    def get_dashboard_action(self, action_name, **kwargs):
        """
        Retorna una acción de Odoo para abrir vistas desde el dashboard

        Args:
            action_name: Nombre de la acción a ejecutar
            **kwargs: Parámetros adicionales (filtros, contexto, etc.)
        """
        if action_name == 'view_employees':
            # Si se pasa employee_id, abrir el formulario del empleado
            employee_id = kwargs.get('employee_id')
            if employee_id:
                return {
                    'type': 'ir.actions.act_window',
                    'name': 'Empleado',
                    'res_model': 'hr.employee',
                    'res_id': employee_id,
                    'view_mode': 'form',
                    'views': [(False, 'form')],
                    'target': 'current',
                }

            # Si no, abrir la lista con el dominio
            return {
                'type': 'ir.actions.act_window',
                'name': 'Empleados',
                'res_model': 'hr.employee',
                'view_mode': 'kanban,list,form',
                'views': [(False, 'kanban'), (False, 'list'), (False, 'form')],
                'domain': kwargs.get('domain', []),
                'context': kwargs.get('context', {}),
                'target': 'current',
            }

        elif action_name == 'view_contracts':
            # Si se pasa contract_id, abrir el formulario del contrato
            contract_id = kwargs.get('contract_id')
            if contract_id:
                return {
                    'type': 'ir.actions.act_window',
                    'name': 'Contrato',
                    'res_model': 'hr.contract',
                    'res_id': contract_id,
                    'view_mode': 'form',
                    'views': [(False, 'form')],
                    'target': 'current',
                }

            # Si no, abrir la lista con el dominio
            return {
                'type': 'ir.actions.act_window',
                'name': 'Contratos',
                'res_model': 'hr.contract',
                'view_mode': 'list,form',
                'views': [(False, 'list'), (False, 'form')],
                'domain': kwargs.get('domain', []),
                'context': kwargs.get('context', {}),
                'target': 'current',
            }

        elif action_name == 'view_expiring_contracts':
            date_from = fields.Date.today()
            date_limit = date_from + relativedelta(days=30)
            department_id = kwargs.get('department_id')

            domain = [
                ('state', '=', 'open'),
                ('date_end', '!=', False),
                ('date_end', '>=', date_from),
                ('date_end', '<=', date_limit),
                ('company_id', '=', self.env.company.id),
            ]

            if department_id:
                domain.append(('employee_id.department_id', '=', department_id))

            return {
                'type': 'ir.actions.act_window',
                'name': 'Contratos por Vencer',
                'res_model': 'hr.contract',
                'view_mode': 'list,form',
                'views': [(False, 'list'), (False, 'form')],
                'domain': domain,
                'context': {'search_default_group_by_date_end': 1},
                'target': 'current',
            }

        elif action_name == 'view_payslips':
            return {
                'type': 'ir.actions.act_window',
                'name': 'Nóminas',
                'res_model': 'hr.payslip',
                'view_mode': 'list,form',
                'views': [(False, 'list'), (False, 'form')],
                'domain': kwargs.get('domain', []),
                'context': kwargs.get('context', {}),
                'target': 'current',
            }

        elif action_name == 'view_batches':
            # Si se pasa batch_id, abrir el formulario del lote
            batch_id = kwargs.get('batch_id')
            if batch_id:
                return {
                    'type': 'ir.actions.act_window',
                    'name': 'Lote de Nómina',
                    'res_model': 'hr.payslip.run',
                    'res_id': batch_id,
                    'view_mode': 'form',
                    'views': [(False, 'form')],
                    'target': 'current',
                }

            # Si no, abrir la lista con el dominio
            return {
                'type': 'ir.actions.act_window',
                'name': 'Lotes de Nómina',
                'res_model': 'hr.payslip.run',
                'view_mode': 'list,form',
                'views': [(False, 'list'), (False, 'form')],
                'domain': kwargs.get('domain', []),
                'context': kwargs.get('context', {}),
                'target': 'current',
            }

        elif action_name == 'view_pending_leaves':
            department_id = kwargs.get('department_id')

            domain = [
                ('state', '=', 'confirm'),
                ('employee_id.company_id', '=', self.env.company.id),
            ]

            if department_id:
                domain.append(('employee_id.department_id', '=', department_id))

            return {
                'type': 'ir.actions.act_window',
                'name': 'Licencias Pendientes',
                'res_model': 'hr.leave',
                'view_mode': 'list,form',
                'views': [(False, 'list'), (False, 'form')],
                'domain': domain,
                'context': {'search_default_group_by_type': 1},
                'target': 'current',
            }

        elif action_name == 'view_new_employees':
            date_from = kwargs.get('date_from')
            date_to = kwargs.get('date_to')
            department_id = kwargs.get('department_id')

            if not date_from or not date_to:
                today = fields.Date.today()
                date_from = today.replace(day=1)
                date_to = date_from + relativedelta(months=1, days=-1)

            # Convertir strings a fechas si es necesario
            if date_from and isinstance(date_from, str):
                date_from = fields.Date.from_string(date_from)
            if date_to and isinstance(date_to, str):
                date_to = fields.Date.from_string(date_to)

            domain = [
                ('first_contract_date', '>=', date_from),
                ('first_contract_date', '<=', date_to),
                ('company_id', '=', self.env.company.id),
            ]

            if department_id:
                domain.append(('department_id', '=', department_id))

            return {
                'type': 'ir.actions.act_window',
                'name': 'Empleados Nuevos',
                'res_model': 'hr.employee',
                'view_mode': 'list,form',
                'views': [(False, 'list'), (False, 'form')],
                'domain': domain,
                'context': {},
                'target': 'current',
            }

        elif action_name == 'view_social_security':
            year = kwargs.get('year')
            month = kwargs.get('month')
            domain = [('company_id', '=', self.env.company.id)]
            if year:
                domain.append(('year', '=', year))
            if month:
                domain.append(('month', '=', str(month)))

            return {
                'type': 'ir.actions.act_window',
                'name': 'Seguridad Social',
                'res_model': 'hr.payroll.social.security',
                'view_mode': 'list,form',
                'views': [(False, 'list'), (False, 'form')],
                'domain': domain,
                'context': {},
                'target': 'current',
            }

        elif action_name == 'view_disabilities':
            period_id = kwargs.get('period_id')
            date_from = kwargs.get('date_from')
            date_to = kwargs.get('date_to')
            disability_type = kwargs.get('disability_type')  # IGE, IRL, etc.

            # Convertir strings a fechas si es necesario
            if date_from and isinstance(date_from, str):
                date_from = fields.Date.from_string(date_from)
            if date_to and isinstance(date_to, str):
                date_to = fields.Date.from_string(date_to)

            # Obtener fechas del período si se proporciona period_id y no hay fechas
            if period_id and not date_from:
                period = self.env['hr.period'].browse(period_id)
                if period.exists():
                    date_from = period.date_start
                    date_to = period.date_end

            domain = [
                ('state', '=', 'validate'),
                ('holiday_status_id.novelty', '!=', False),
                ('employee_id.company_id', '=', self.env.company.id),
            ]

            if date_from and date_to:
                domain.extend([
                    '|',
                    '&', ('date_from', '>=', fields.Date.to_string(date_from)), ('date_from', '<=', fields.Date.to_string(date_to)),
                    '&', ('date_to', '>=', fields.Date.to_string(date_from)), ('date_to', '<=', fields.Date.to_string(date_to)),
                ])

            if disability_type:
                domain.append(('holiday_status_id.novelty', '=', disability_type.lower()))

            return {
                'type': 'ir.actions.act_window',
                'name': f'Incapacidades {disability_type}' if disability_type else 'Incapacidades',
                'res_model': 'hr.leave',
                'view_mode': 'list,form',
                'views': [(False, 'list'), (False, 'form')],
                'domain': domain,
                'context': {},
                'target': 'current',
            }

        elif action_name == 'view_payment_schedule':
            return {
                'type': 'ir.actions.act_window',
                'name': 'Programación de Pagos',
                'res_model': 'hr.payslip.run',
                'view_mode': 'list,form',
                'views': [(False, 'list'), (False, 'form')],
                'domain': [
                    ('state', 'in', ['draft', 'close']),
                    ('company_id', '=', self.env.company.id),
                ],
                'context': {'search_default_group_by_date_end': 1},
                'target': 'current',
            }

        elif action_name == 'view_payslip_lines_by_category':
            # Ver lineas de nomina filtradas por categoria
            category_code = kwargs.get('category_code')
            period_id = kwargs.get('period_id')
            date_from = kwargs.get('date_from')
            date_to = kwargs.get('date_to')

            # Mapeo de claves del resumen a reglas y categorias
            SUMMARY_RULES_MAP = {
                'salud': {'rules': ['SSOCIAL001'], 'name': 'Salud'},
                'pension': {'rules': ['SSOCIAL002'], 'name': 'Pension'},
                'fondos': {'rules': ['SSOCIAL003', 'SSOCIAL004'], 'name': 'Fondos Solidaridad'},
                'retencion': {'rules': ['RT_MET_01', 'RET_PRIMA', 'RTF_INDEM'], 'name': 'Retencion Fuente'},
                'sueldo': {'categories': ['BASIC'], 'name': 'Sueldo Basico'},
                'auxilio': {'categories': ['AUX'], 'name': 'Auxilio Transporte'},
                'horas_extras': {'categories': ['HEYREC'], 'name': 'Horas Extras'},
                'prestamos': {'rules': ['P01', 'PRESTAMO'], 'name': 'Prestamos'},
                'libranzas': {'rules': ['LIBRANZA'], 'name': 'Libranzas'},
                'vacaciones': {'categories': ['VACACIONES'], 'name': 'Vacaciones'},
                'incapacidades': {'categories': ['INCAPACIDAD', 'ACCIDENTE_TRABAJO'], 'name': 'Incapacidades'},
                'licencias': {'categories': ['LICENCIA_MATERNIDAD', 'LICENCIA_REMUNERADA'], 'name': 'Licencias'},
                'prestaciones': {'categories': ['PRESTACIONES_SOCIALES'], 'name': 'Prestaciones Sociales'},
                'devengos_salariales': {'categories': ['DEV_SALARIAL'], 'name': 'Devengos Salariales'},
                'devengos_no_salariales': {'categories': ['DEV_NO_SALARIAL'], 'name': 'Devengos No Salariales'},
                'deducciones': {'categories': ['DEDUCCIONES'], 'rules': ['EMBARGO007', 'EMBARGO009', 'EMBARGO002', 'MEDPRE', 'ERROR', 'HORAS', 'ANTICIPO', 'AVP', 'DESCUENTO', 'AFC'], 'name': 'Otras Deducciones'},
            }

            # Convertir strings a fechas si es necesario
            if date_from and isinstance(date_from, str):
                date_from = fields.Date.from_string(date_from)
            if date_to and isinstance(date_to, str):
                date_to = fields.Date.from_string(date_to)

            # Obtener fechas del periodo si se proporciona period_id
            if period_id and not date_from:
                period = self.env['hr.period'].browse(period_id)
                if period.exists():
                    date_from = period.date_start
                    date_to = period.date_end

            # Si aun no hay fechas, usar mes actual
            if not date_from or not date_to:
                today = fields.Date.today()
                date_from = today.replace(day=1)
                date_to = date_from + relativedelta(months=1, days=-1)

            domain = [
                ('date_from', '>=', date_from),
                ('date_from', '<=', date_to),
                ('slip_id.state', 'in', ['done', 'paid']),
                ('slip_id.company_id', '=', self.env.company.id),
            ]

            action_name_display = 'Todas'

            if category_code and category_code in SUMMARY_RULES_MAP:
                # Usar el mapeo de claves del resumen
                rule_config = SUMMARY_RULES_MAP[category_code]
                action_name_display = rule_config.get('name', category_code)
                rules = rule_config.get('rules', [])
                categories = rule_config.get('categories', [])

                filter_conditions = []
                if rules:
                    filter_conditions.append(('salary_rule_id.code', 'in', rules))
                if categories:
                    filter_conditions.append(('category_id.code', 'in', categories))

                if len(filter_conditions) == 1:
                    domain.append(filter_conditions[0])
                elif len(filter_conditions) > 1:
                    domain.append('|')
                    domain.extend(filter_conditions)

            elif category_code:
                # Buscar por codigo de categoria o codigo de padre (comportamiento legacy)
                action_name_display = category_code
                domain.append('|')
                domain.append(('category_id.code', '=', category_code))
                domain.append(('category_id.parent_id.code', '=', category_code))

            return {
                'type': 'ir.actions.act_window',
                'name': f'Lineas de Nomina - {action_name_display}',
                'res_model': 'hr.payslip.line',
                'view_mode': 'list,form',
                'views': [(False, 'list'), (False, 'form')],
                'domain': domain,
                'context': {},
                'target': 'current',
            }

        elif action_name == 'view_employees_without_ss':
            # Ver empleados sin seguridad social
            employee_ids = kwargs.get('employee_ids', [])
            return {
                'type': 'ir.actions.act_window',
                'name': 'Empleados sin Seguridad Social',
                'res_model': 'hr.employee',
                'view_mode': 'kanban,list,form',
                'views': [(False, 'kanban'), (False, 'list'), (False, 'form')],
                'domain': [('id', 'in', employee_ids)] if employee_ids else [],
                'context': {},
                'target': 'current',
            }

        elif action_name == 'view_employees_without_payslip':
            # Ver empleados sin nómina en el período
            employee_ids = kwargs.get('employee_ids', [])
            return {
                'type': 'ir.actions.act_window',
                'name': 'Empleados sin Nómina en el Período',
                'res_model': 'hr.employee',
                'view_mode': 'kanban,list,form',
                'views': [(False, 'kanban'), (False, 'list'), (False, 'form')],
                'domain': [('id', 'in', employee_ids)] if employee_ids else [],
                'context': {},
                'target': 'current',
            }

        elif action_name == 'view_employees_without_settlement':
            # Ver empleados terminados sin liquidación
            employee_ids = kwargs.get('employee_ids', [])
            return {
                'type': 'ir.actions.act_window',
                'name': 'Empleados sin Liquidación',
                'res_model': 'hr.employee',
                'view_mode': 'kanban,list,form',
                'views': [(False, 'kanban'), (False, 'list'), (False, 'form')],
                'domain': [('id', 'in', employee_ids)] if employee_ids else [],
                'context': {'active_test': False},  # Mostrar inactivos también
                'target': 'current',
            }

        else:
            return {
                'type': 'ir.actions.act_window',
                'name': 'Error',
                'res_model': 'hr.payslip',
                'view_mode': 'list',
                'views': [(False, 'list')],
                'target': 'current',
            }

    @api.model
    def _get_dashboard_payroll_summary(self, date_from, date_to, department_id=None, batch_id=None):
        """Obtiene resumen de totales de nomina por categoria de regla salarial"""
        import logging
        _logger = logging.getLogger(__name__)

        # Construir dominio base
        payslip_domain = [
            ('date_from', '>=', date_from),
            ('date_to', '<=', date_to),
            ('state', 'in', ['done', 'paid'])
        ]
        if department_id:
            payslip_domain.append(('employee_id.department_id', '=', department_id))
        if batch_id:
            payslip_domain.append(('payslip_run_id', '=', batch_id))

        payslips = self.search(payslip_domain)
        _logger.info(f"Payroll Summary: {len(payslips)} payslips entre {date_from} y {date_to}")

        # Definir categorias especificas a sumarizar
        # Usar tanto categorias como reglas especificas para mayor precision
        SUMMARY_RULES = {
            'sueldo': {
                'name': 'Sueldo Basico',
                'icon': 'fa-money',
                'color': 'success',
                'categories': ['BASIC', 'BASICD'],
                'show_if_zero': True,
                'type': 'earning'
            },
            'auxilio': {
                'name': 'Auxilio Transporte',
                'icon': 'fa-bus',
                'color': 'info',
                'categories': ['AUX', 'AUS', 'ALW'],
                'show_if_zero': False,
                'type': 'earning'
            },
            'horas_extras': {
                'name': 'Horas Extras y Recargos',
                'icon': 'fa-clock',
                'color': 'warning',
                'categories': ['HEYREC', 'HED', 'HEN', 'HEDDF', 'HENDF'],
                'show_if_zero': False,
                'type': 'earning'
            },
            'comisiones': {
                'name': 'Comisiones',
                'icon': 'fa-percent',
                'color': 'success',
                'categories': ['COMISIONES'],
                'show_if_zero': False,
                'type': 'earning'
            },
            'vacaciones': {
                'name': 'Vacaciones',
                'icon': 'fa-plane',
                'color': 'success',
                'categories': ['VACACIONES'],
                'show_if_zero': False,
                'type': 'earning'
            },
            'incapacidades': {
                'name': 'Incapacidades',
                'icon': 'fa-medkit',
                'color': 'info',
                'categories': ['INCAPACIDAD', 'ACCIDENTE_TRABAJO'],
                'show_if_zero': False,
                'type': 'earning'
            },
            'licencias': {
                'name': 'Licencias',
                'icon': 'fa-calendar-times',
                'color': 'secondary',
                'categories': ['LICENCIA_MATERNIDAD', 'LICENCIA_REMUNERADA'],
                'show_if_zero': False,
                'type': 'earning'
            },
            'prestaciones': {
                'name': 'Prestaciones Sociales',
                'icon': 'fa-gift',
                'color': 'primary',
                'categories': ['PRESTACIONES_SOCIALES', 'PRIMA'],
                'show_if_zero': False,
                'type': 'earning'
            },
            'devengos_salariales': {
                'name': 'Otros Devengos Salariales',
                'icon': 'fa-plus-circle',
                'color': 'success',
                'categories': ['DEV_SALARIAL'],
                'show_if_zero': False,
                'type': 'earning'
            },
            'devengos_no_salariales': {
                'name': 'Devengos No Salariales',
                'icon': 'fa-plus',
                'color': 'info',
                'categories': ['DEV_NO_SALARIAL', 'COMPLEMENTARIOS'],
                'show_if_zero': False,
                'type': 'earning'
            },
            'seguridad_social': {
                'name': 'Seguridad Social',
                'icon': 'fa-shield',
                'color': 'danger',
                'categories': ['SSOCIAL', 'SS_EMP'],
                'show_if_zero': False,
                'type': 'deduction'
            },
            'retencion': {
                'name': 'Retencion Fuente',
                'icon': 'fa-percent',
                'color': 'warning',
                'categories': ['RTEFTE'],
                'rules': ['RT_MET_01', 'RET_PRIMA', 'RTF_INDEM', 'RETFTE001', 'RETFTE_PRIMA001'],
                'show_if_zero': False,
                'type': 'deduction'
            },
            'deducciones': {
                'name': 'Deducciones',
                'icon': 'fa-minus-circle',
                'color': 'danger',
                'categories': ['DED', 'DEDUCCIONES', 'DEDUCCION', 'SANCIONES', 'DESCUENTO_AFC'],
                'show_if_zero': False,
                'type': 'deduction'
            },
        }

        # Inicializar totales
        totals = {key: {'total': 0, 'count': 0, 'employees': set(), **config}
                  for key, config in SUMMARY_RULES.items()}

        # Calcular totales por linea de nomina
        for payslip in payslips:
            for line in payslip.line_ids:
                if not line.salary_rule_id or not line.category_id:
                    continue
                if not line.salary_rule_id.appears_on_payslip:
                    continue

                rule_code = line.salary_rule_id.code
                category_code = line.category_id.code
                value = abs(line.total)

                # Buscar en que categoria cae esta linea
                for key, config in SUMMARY_RULES.items():
                    matched = False

                    # Primero buscar por regla especifica
                    if 'rules' in config and rule_code in config['rules']:
                        matched = True
                    # Luego buscar por categoria
                    elif 'categories' in config and category_code in config['categories']:
                        # Verificar que no sea una regla que ya esta en otra categoria
                        already_in_rules = False
                        for other_key, other_config in SUMMARY_RULES.items():
                            if other_key != key and 'rules' in other_config and rule_code in other_config['rules']:
                                already_in_rules = True
                                break
                        if not already_in_rules:
                            matched = True

                    if matched:
                        totals[key]['total'] += value
                        totals[key]['count'] += 1
                        totals[key]['employees'].add(payslip.employee_id.id)
                        break

        # Formatear resultado
        summary_items = []
        for key, data in totals.items():
            if data['total'] > 0 or data.get('show_if_zero', False):
                summary_items.append({
                    'key': key,
                    'name': data['name'],
                    'icon': data['icon'],
                    'color': data['color'],
                    'type': data.get('type', 'earning'),
                    'total': data['total'],
                    'formatted': self._format_currency(data['total']),
                    'count': data['count'],
                    'employees_count': len(data['employees']),
                })

        # Calcular totales generales usando el campo type
        total_devengos = sum(t['total'] for k, t in totals.items()
                            if t.get('type') == 'earning')
        total_deducciones = sum(t['total'] for k, t in totals.items()
                               if t.get('type') == 'deduction')

        return {
            'items': summary_items,
            'total_devengos': total_devengos,
            'total_deducciones': total_deducciones,
            'neto': total_devengos - total_deducciones,
            'formatted_devengos': self._format_currency(total_devengos),
            'formatted_deducciones': self._format_currency(total_deducciones),
            'formatted_neto': self._format_currency(total_devengos - total_deducciones),
            'payslips_count': len(payslips),
            'employees_count': len(set(p.employee_id.id for p in payslips)),
        }

    @api.model
    def _format_currency(self, amount):
        """Formatea un monto como moneda"""
        if not amount:
            return '$0'

        # Formatear con separadores de miles y sin decimales (estilo colombiano)
        return '${:,.0f}'.format(abs(amount)).replace(',', '.')
