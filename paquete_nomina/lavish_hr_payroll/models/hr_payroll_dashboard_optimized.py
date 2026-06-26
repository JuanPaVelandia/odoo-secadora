# -*- coding: utf-8 -*-
"""
Dashboard Optimizado con SQL Service
====================================

Mixin que proporciona versiones optimizadas de los métodos del dashboard
usando consultas SQL directas en lugar de ORM.

Los métodos optimizados tienen el sufijo '_sql' y pueden usarse como
reemplazo drop-in de los métodos originales cuando se necesita
mejor rendimiento.

Uso:
    # En lugar de:
    data = self._get_dashboard_overtime_by_department(date_from, date_to)

    # Usar:
    data = self._get_dashboard_overtime_by_department_sql(date_from, date_to)
"""

from odoo import models, api, fields
from datetime import date as dt_date
from dateutil.relativedelta import relativedelta


class HrPayslipDashboardOptimized(models.Model):
    """
    Extensión del dashboard con métodos optimizados usando SQL service.
    """
    _inherit = 'hr.payslip'

    # =========================================================================
    # MÉTODOS OPTIMIZADOS - Usan SQL Service
    # =========================================================================

    @api.model
    def _get_dashboard_query_service(self):
        """Obtiene el servicio de consultas del dashboard."""
        return self.env['dashboard.query.service']

    @api.model
    def _get_dashboard_kpis_sql(self, date_from, date_to, department_id=None):
        """
        Versión optimizada de _get_dashboard_kpis.

        Usa SQL directo para las consultas principales de KPIs.
        Las consultas complejas (empleados sin SS, sin nómina, sin liquidación)
        se calculan con ORM debido a su lógica especializada.
        """
        service = self._get_dashboard_query_service()
        company_id = self.env.company.id

        # Obtener KPIs básicos con SQL
        kpis = service.get_kpis_all(
            date_from=date_from,
            date_to=date_to,
            company_id=company_id,
            department_id=department_id,
        )

        # Obtener totales por categoría con SQL
        totals_data = service.get_payslip_totals_by_category(
            date_from=date_from,
            date_to=date_to,
            company_id=company_id,
            department_id=department_id,
        )
        total_devengado = totals_data.get('total_devengado', 0)

        # Obtener retenciones con SQL
        retention_data = service.get_retention_totals(
            date_from=date_from,
            date_to=date_to,
            company_id=company_id,
            department_id=department_id,
        )

        # Obtener retenciones del período anterior
        prev_date_from = date_from - relativedelta(months=1)
        prev_date_to = date_to - relativedelta(months=1)

        prev_retention_data = service.get_retention_totals(
            date_from=prev_date_from,
            date_to=prev_date_to,
            company_id=company_id,
            department_id=department_id,
        )

        # Calcular cambios de retención
        retention_base_change = 0
        retention_change = 0
        if prev_retention_data['base_retencion'] > 0:
            retention_base_change = ((retention_data['base_retencion'] - prev_retention_data['base_retencion']) / prev_retention_data['base_retencion']) * 100
        if prev_retention_data['total_retenido'] > 0:
            retention_change = ((retention_data['total_retenido'] - prev_retention_data['total_retenido']) / prev_retention_data['total_retenido']) * 100

        # =====================================================================
        # KPIs que requieren lógica ORM compleja (calculados internamente)
        # =====================================================================

        def _employee_summary(records):
            """Helper para formatear lista de empleados."""
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

        # Dominio base para empleados
        employee_domain = [
            ('active', '=', True),
            ('company_id', '=', company_id),
            '|',
            ('departure_date', '=', False),
            ('departure_date', '>', date_to)
        ]
        if department_id:
            employee_domain.insert(0, ('department_id', '=', department_id))

        all_active_employees = self.env['hr.employee'].search(employee_domain)

        # KPI: Empleados sin Seguridad Social
        period_month = date_from.month
        period_year = date_from.year
        ss_record = self.env['hr.payroll.social.security'].search([
            ('year', '=', period_year),
            ('month', '=', str(period_month)),
            ('company_id', '=', company_id)
        ], limit=1)

        employees_without_ss = 0
        employees_without_ss_list = []
        employees_without_ss_records = self.env['hr.employee']

        if ss_record:
            ss_employee_ids = ss_record.executing_social_security_ids.mapped('employee_id').ids
            employees_without_ss_records = all_active_employees.filtered(lambda e: e.id not in ss_employee_ids)
            employees_without_ss = len(employees_without_ss_records)
            employees_without_ss_list = employees_without_ss_records.ids
        else:
            employees_without_ss = len(all_active_employees)
            employees_without_ss_list = all_active_employees.ids
            employees_without_ss_records = all_active_employees

        # KPI: Empleados sin Nómina en el Período
        payslip_domain = [
            ('date_from', '>=', date_from),
            ('date_to', '<=', date_to),
            ('state', 'in', ['validated', 'paid']),
            ('company_id', '=', company_id)
        ]
        if department_id:
            payslip_domain.append(('employee_id.department_id', '=', department_id))

        payslips = self.search(payslip_domain)
        payslip_employee_ids = payslips.mapped('employee_id').ids
        employees_without_payslip = all_active_employees.filtered(lambda e: e.id not in payslip_employee_ids)
        employees_without_payslip_count = len(employees_without_payslip)
        employees_without_payslip_list = employees_without_payslip.ids

        # KPI: Empleados sin Liquidación
        terminated_domain = [
            ('departure_date', '!=', False),
            ('departure_date', '<=', date_to),
            ('active', 'in', [True, False]),
            ('company_id', '=', company_id),
        ]
        if department_id:
            terminated_domain.append(('department_id', '=', department_id))

        terminated_employees = self.env['hr.employee'].search(terminated_domain)

        employees_without_settlement = []
        for employee in terminated_employees:
            settlement_payslips = self.env['hr.payslip'].search([
                ('employee_id', '=', employee.id),
                ('struct_id.name', 'ilike', 'liquidación'),
                ('state', 'in', ['validated', 'paid']),
                ('company_id', '=', company_id),
            ], limit=1)

            if not settlement_payslips:
                employees_without_settlement.append(employee.id)

        employees_without_settlement_count = len(employees_without_settlement)
        employees_without_settlement_records = self.env['hr.employee'].browse(employees_without_settlement)

        return {
            'total_employees': {
                'value': kpis['total_employees'],
            },
            'total_devengado': {
                'value': total_devengado,
                'formatted': self._format_currency(total_devengado),
            },
            'payslips_month': {
                'count': kpis['payslip_count'],
                'value': kpis['payslip_net_total'],
                'formatted': self._format_currency(kpis['payslip_net_total']),
            },
            'accidents': {
                'value': kpis['accidents_count'],
                'change': 0,
            },
            'absences': {
                'value': kpis['total_leaves'],
                'days': kpis['total_leave_days'],
            },
            'pending_requests': {
                'value': kpis['pending_requests'],
            },
            'new_employees': {
                'value': kpis['new_employees'],
            },
            'avg_overtime_hours': {
                'value': round(kpis['avg_overtime_hours'], 1),
                'total_hours': round(kpis.get('total_overtime_hours', 0), 1),
                'employee_count': kpis.get('overtime_employee_count', 0),
                'avg_rate': round(kpis.get('avg_overtime_rate', 0), 1),
            },
            'retention_base': {
                'value': retention_data['base_retencion'],
                'formatted': self._format_currency(retention_data['base_retencion']),
                'prev_value': prev_retention_data['base_retencion'],
                'prev_formatted': self._format_currency(prev_retention_data['base_retencion']),
                'change': round(retention_base_change, 1),
            },
            'retention_total': {
                'value': retention_data['total_retenido'],
                'formatted': self._format_currency(retention_data['total_retenido']),
                'prev_value': prev_retention_data['total_retenido'],
                'prev_formatted': self._format_currency(prev_retention_data['total_retenido']),
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
    def _get_dashboard_overtime_by_department_sql(self, date_from, date_to):
        """
        Versión optimizada de _get_dashboard_overtime_by_department.

        Usa SQL directo en lugar de ORM para mejor rendimiento.
        """
        service = self._get_dashboard_query_service()
        rows = service.get_overtime_by_department(
            date_from=date_from,
            date_to=date_to,
            company_id=self.env.company.id,
        )

        labels = [r['department_name'] for r in rows]
        data = [r['total_hours'] for r in rows]

        return {
            'labels': labels,
            'datasets': [{
                'label': 'Horas Extras',
                'data': data,
            }]
        }

    @api.model
    def _get_dashboard_absences_by_type_sql(self, date_from, date_to, department_id=None):
        """
        Versión optimizada de _get_dashboard_absences_by_type.

        Usa SQL directo en lugar de ORM para mejor rendimiento.
        """
        service = self._get_dashboard_query_service()
        rows = service.get_absences_by_type(
            date_from=date_from,
            date_to=date_to,
            company_id=self.env.company.id,
            department_id=department_id,
        )

        labels = [r['type_name'] for r in rows]
        data = [r['total_days'] for r in rows]

        return {
            'labels': labels,
            'datasets': [{
                'data': data,
            }]
        }

    @api.model
    def _get_dashboard_payroll_trend_sql(self, date_from, date_to, department_id=None):
        """
        Versión optimizada de _get_dashboard_payroll_trend.

        Usa SQL directo en lugar de ORM para mejor rendimiento.
        """
        service = self._get_dashboard_query_service()
        rows = service.get_payroll_trend(
            date_to=date_to,
            company_id=self.env.company.id,
            department_id=department_id,
            months_back=6,
        )

        labels = [r['period_label'] for r in rows]
        totals = [r['net_total'] for r in rows]

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
    def _get_dashboard_employees_by_city_sql(self, date_from, date_to, department_id=None):
        """
        Versión optimizada de _get_dashboard_employees_by_city.

        Usa SQL directo en lugar de ORM para mejor rendimiento.
        """
        service = self._get_dashboard_query_service()
        rows = service.get_employees_by_city(
            date_to=date_to,
            company_id=self.env.company.id,
            department_id=department_id,
        )

        total = sum(r['employee_count'] for r in rows)
        cities = sorted(
            [{'name': r['city_name'], 'count': r['employee_count']} for r in rows],
            key=lambda x: (-x['count'], x['name'])
        )

        for city in cities:
            city['percent'] = round((city['count'] / total) * 100, 1) if total else 0

        return {
            'total': total,
            'cities': cities,
        }

    @api.model
    def _get_dashboard_new_employees_sql(self, date_from, date_to, department_id=None):
        """
        Versión optimizada de _get_dashboard_new_employees.

        Usa SQL directo en lugar de ORM para mejor rendimiento.
        """
        service = self._get_dashboard_query_service()
        rows = service.get_new_employees(
            date_from=date_from,
            date_to=date_to,
            company_id=self.env.company.id,
            department_id=department_id,
        )

        return [{
            'id': r['id'],
            'name': r['name'],
            'identification': r.get('identification_id', ''),
            'department': r.get('department_name', 'Sin Departamento'),
            'job': r.get('job_name', 'Sin Cargo'),
            'start_date': fields.Date.to_string(r['first_contract_date']) if r.get('first_contract_date') else None,
        } for r in rows]

    @api.model
    def _get_dashboard_expiring_contracts_sql(self, date_from=None, days_threshold=30, department_id=None):
        """
        Versión optimizada de _get_dashboard_expiring_contracts.

        Usa SQL directo en lugar de ORM para mejor rendimiento.
        """
        service = self._get_dashboard_query_service()
        rows = service.get_expiring_contracts(
            company_id=self.env.company.id,
            department_id=department_id,
            days_ahead=days_threshold,
        )

        today = date_from or fields.Date.today()
        result = []

        for r in rows:
            days_remaining = r.get('days_remaining', 0)

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
                'id': r['contract_id'],  # Required for t-key in template
                'employee_id': r['employee_id'],
                'employee_name': r['employee_name'],
                'employee_identification': r.get('identification_id', ''),
                'department': r.get('department_name', 'Sin Departamento'),
                'job': r.get('job_name', ''),
                'date_end': fields.Date.to_string(r['contract_end_date']) if r.get('contract_end_date') else None,
                'days_remaining': days_remaining,
                'urgency': urgency,
                'urgency_label': urgency_label,
            })

        return {
            'total': len(result),
            'critical': len([c for c in result if c['urgency'] == 'critical']),
            'high': len([c for c in result if c['urgency'] == 'high']),
            'medium': len([c for c in result if c['urgency'] == 'medium']),
            'contracts': result,
        }

    @api.model
    def _get_dashboard_kpis_payslip_totals_sql(self, date_from, date_to, department_id=None):
        """
        Obtiene totales de nómina por categoría usando SQL optimizado.

        Este método complementa _get_dashboard_kpis proveyendo los totales
        de devengos y deducciones de manera más eficiente.
        """
        service = self._get_dashboard_query_service()
        data = service.get_payslip_totals_by_category(
            date_from=date_from,
            date_to=date_to,
            company_id=self.env.company.id,
            department_id=department_id,
        )

        return {
            'total_devengado': {
                'value': data['total_devengado'],
                'formatted': self._format_currency(data['total_devengado']),
            },
            'total_deducciones': {
                'value': data['total_deducciones'],
                'formatted': self._format_currency(data['total_deducciones']),
            },
            'payslips_count': data['total_payslips'],
            'by_category': data['by_category'],
        }

    @api.model
    def _get_dashboard_retention_totals_sql(self, date_from, date_to, department_id=None):
        """
        Obtiene totales de retención en la fuente usando SQL optimizado.

        Complementa _get_dashboard_kpis para las métricas de retención.
        """
        service = self._get_dashboard_query_service()
        data = service.get_retention_totals(
            date_from=date_from,
            date_to=date_to,
            company_id=self.env.company.id,
            department_id=department_id,
        )

        # Obtener datos del período anterior para comparación
        prev_date_from = date_from - relativedelta(months=1)
        prev_date_to = date_to - relativedelta(months=1)

        prev_data = service.get_retention_totals(
            date_from=prev_date_from,
            date_to=prev_date_to,
            company_id=self.env.company.id,
            department_id=department_id,
        )

        # Calcular cambio porcentual
        base_change = 0
        total_change = 0
        if prev_data['base_retencion'] > 0:
            base_change = ((data['base_retencion'] - prev_data['base_retencion']) / prev_data['base_retencion']) * 100
        if prev_data['total_retenido'] > 0:
            total_change = ((data['total_retenido'] - prev_data['total_retenido']) / prev_data['total_retenido']) * 100

        return {
            'retention_base': {
                'value': data['base_retencion'],
                'formatted': self._format_currency(data['base_retencion']),
                'prev_value': prev_data['base_retencion'],
                'prev_formatted': self._format_currency(prev_data['base_retencion']),
                'change': round(base_change, 1),
            },
            'retention_total': {
                'value': data['total_retenido'],
                'formatted': self._format_currency(data['total_retenido']),
                'prev_value': prev_data['total_retenido'],
                'prev_formatted': self._format_currency(prev_data['total_retenido']),
                'change': round(total_change, 1),
            },
        }

    @api.model
    def _get_dashboard_pending_leaves_sql(self, department_id=None):
        """
        Versión optimizada de _get_dashboard_pending_leaves.

        Usa SQL directo en lugar de ORM para mejor rendimiento.
        """
        service = self._get_dashboard_query_service()
        rows = service.get_pending_leaves(
            company_id=self.env.company.id,
            department_id=department_id,
        )

        result = []
        for r in rows:
            request_age_days = r.get('request_age_days', 0) or 0

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
                'id': r['id'],
                'employee_id': r['employee_id'],
                'employee_name': r['employee_name'],
                'department': r.get('department_name', 'Sin Departamento'),
                'leave_type': r.get('leave_type_name', 'Sin Tipo'),
                'date_from': fields.Date.to_string(r['request_date_from']) if r.get('request_date_from') else None,
                'date_to': fields.Date.to_string(r['request_date_to']) if r.get('request_date_to') else None,
                'days': r.get('number_of_days', 0),
                'request_age_days': request_age_days,
                'urgency': urgency,
                'urgency_label': urgency_label,
            })

        return {
            'total': len(result),
            'high': len([l for l in result if l['urgency'] == 'high']),
            'medium': len([l for l in result if l['urgency'] == 'medium']),
            'low': len([l for l in result if l['urgency'] == 'low']),
            'leaves': result,
        }

    @api.model
    def _get_dashboard_accidents_sql(self, date_from, date_to, department_id=None):
        """
        Obtiene lista de accidentes laborales usando SQL optimizado.
        """
        service = self._get_dashboard_query_service()
        rows = service.get_accidents(
            date_from=date_from,
            date_to=date_to,
            company_id=self.env.company.id,
            department_id=department_id,
        )

        return {
            'count': len(rows),
            'accidents': [{
                'id': r['id'],
                'employee_name': r['employee_name'],
                'employee_id': r['employee_id'],
                'department': r.get('department_name', 'Sin Departamento'),
                'date_from': fields.Date.to_string(r['date_from']) if r.get('date_from') else None,
                'date_to': fields.Date.to_string(r['date_to']) if r.get('date_to') else None,
                'days': r.get('days', 0),
                'description': r.get('description', ''),
            } for r in rows]
        }

    @api.model
    def _get_dashboard_devengos_deducciones_trend_sql(self, date_from, date_to, department_id=None):
        """
        Obtiene tendencia de devengos vs deducciones usando SQL optimizado.
        """
        service = self._get_dashboard_query_service()
        rows = service.get_devengos_deducciones_trend(
            date_to=date_to,
            company_id=self.env.company.id,
            department_id=department_id,
            months_back=6,
        )

        labels = [r['period_label'] for r in rows]
        devengos = [r['total_devengos'] for r in rows]
        deducciones = [r['total_deducciones'] for r in rows]

        return {
            'labels': labels,
            'datasets': [
                {
                    'label': 'Devengos',
                    'data': devengos,
                },
                {
                    'label': 'Deducciones',
                    'data': deducciones,
                }
            ]
        }

    # =========================================================================
    # MÉTODOS DE GRÁFICOS ADICIONALES (SQL)
    # =========================================================================

    @api.model
    def _get_dashboard_accidents_chart_sql(self, date_from):
        """
        Versión SQL de _get_dashboard_accidents_chart.
        Obtiene accidentes e incidentes de los últimos 6 meses.
        """
        service = self._get_dashboard_query_service()

        # Verificar si existe el modelo sst.accident
        if not self.env['ir.model'].search([('model', '=', 'sst.accident')], limit=1):
            # No existe el modelo, retornar datos vacíos
            months = []
            for i in range(5, -1, -1):
                month_date = date_from - relativedelta(months=i)
                months.append(month_date.strftime('%b'))
            return {
                'labels': months,
                'datasets': [
                    {'label': 'Accidentes', 'data': [0] * 6},
                    {'label': 'Incidentes', 'data': [0] * 6}
                ]
            }

        rows = service.get_accidents_by_month(
            date_from=date_from,
            company_id=self.env.company.id,
            months_back=6,
        )

        labels = [r['month_label'] for r in rows]
        accidents = [r['accidents_count'] for r in rows]
        incidents = [r['incidents_count'] for r in rows]

        return {
            'labels': labels,
            'datasets': [
                {'label': 'Accidentes', 'data': accidents},
                {'label': 'Incidentes', 'data': incidents}
            ]
        }

    @api.model
    def _get_dashboard_income_deductions_chart_sql(self, date_from, date_to, department_id=None):
        """
        Versión SQL de _get_dashboard_income_deductions_chart.
        Obtiene gráfico de ingresos vs deducciones.
        """
        from odoo.addons.lavish_hr_employee.models.payroll.hr_payslip_constants import CATEGORY_MAPPINGS

        service = self._get_dashboard_query_service()

        # Obtener datos agregados por categoría
        rows = service.get_income_deductions_by_category(
            date_from=date_from,
            date_to=date_to,
            company_id=self.env.company.id,
            department_id=department_id,
            detailed=False,
        )

        # Clasificar categorías
        earnings_categories = CATEGORY_MAPPINGS.get('EARNINGS', [])
        deduction_categories = CATEGORY_MAPPINGS.get('DEDUCTIONS', [])

        income_categories_list = []
        deduction_categories_list = []

        for row in rows:
            cat_code = row['category_code']
            cat_item = {
                'name': row['category_name'],
                'code': cat_code,
                'value': row['total'],
                'formatted': self._format_currency(row['total']),
                'rules': [],  # Sin detalle de reglas en versión simplificada
            }

            if cat_code in earnings_categories:
                income_categories_list.append(cat_item)
            else:
                deduction_categories_list.append(cat_item)

        total_income = sum(cat['value'] for cat in income_categories_list)
        total_deductions = sum(cat['value'] for cat in deduction_categories_list)

        return {
            'income': {
                'categories': income_categories_list,
                'total': total_income,
                'formatted_total': self._format_currency(total_income),
            },
            'deductions': {
                'categories': deduction_categories_list,
                'total': total_deductions,
                'formatted_total': self._format_currency(total_deductions),
            },
            'net': {
                'value': total_income - total_deductions,
                'formatted': self._format_currency(total_income - total_deductions),
            }
        }

    @api.model
    def _get_dashboard_disability_chart_sql(self, date_from, date_to, department_id=None):
        """
        Versión SQL de _get_dashboard_disability_chart.
        Obtiene gráfico de incapacidades por tipo.
        """
        service = self._get_dashboard_query_service()

        # Mapeo de códigos a nombres descriptivos
        novelty_labels = {
            'IGE': 'Inc. Enfermedad General',
            'IRL': 'Inc. Accidente Laboral',
            'LMA': 'Lic. Maternidad',
            'LPA': 'Lic. Paternidad',
            'VAC': 'Vacaciones',
            'VR': 'Vacaciones Remuneradas',
            'LIC': 'Licencia',
        }

        type_icons = {
            'IGE': 'fa-medkit', 'IRL': 'fa-ambulance', 'LMA': 'fa-female',
            'LPA': 'fa-child', 'VAC': 'fa-plane', 'VR': 'fa-plane', 'LIC': 'fa-file-alt',
        }

        type_colors = {
            'IGE': 'text-info', 'IRL': 'text-danger', 'LMA': 'text-purple',
            'LPA': 'text-primary', 'VAC': 'text-success', 'VR': 'text-success',
            'LIC': 'text-warning',
        }

        # Obtener comparación con período anterior
        rows = service.get_disability_comparison(
            date_from=date_from,
            date_to=date_to,
            company_id=self.env.company.id,
            department_id=department_id,
        )

        labels = []
        days_data = []
        count_data = []
        detail = []
        total_days = 0
        total_cases = 0

        for row in rows:
            code = row['novelty_code'] or ''
            display_name = novelty_labels.get(code, row['leave_type_name'])
            current_days = row['current_days'] or 0
            current_cases = row['current_cases'] or 0
            prev_days = row['prev_days'] or 0

            labels.append(display_name)
            days_data.append(current_days)
            count_data.append(current_cases)
            total_days += current_days
            total_cases += current_cases

            # Calcular tendencia
            trend = 0
            if prev_days > 0:
                trend = round(((current_days - prev_days) / prev_days) * 100, 1)

            detail.append({
                'name': display_name,
                'code': code,
                'icon': type_icons.get(code, 'fa-file-o'),
                'color': type_colors.get(code, 'text-muted'),
                'days': current_days,
                'cases': current_cases,
                'percentage': round((current_days / total_days * 100), 1) if total_days > 0 else 0,
                'trend': trend,
                'prev_days': prev_days,
                'rules': [],  # Sin detalle de reglas en versión SQL
            })

        return {
            'labels': labels,
            'datasets': [
                {'label': 'Días de Incapacidad', 'data': days_data},
                {'label': 'Número de Casos', 'data': count_data}
            ],
            'total_days': total_days,
            'total_cases': total_cases,
            'detail': detail,
            'types_found': [d['code'] for d in detail if d['code']],
        }

    @api.model
    def _get_dashboard_payroll_summary_sql(self, date_from, date_to, department_id=None, batch_id=None):
        """
        Versión SQL de _get_dashboard_payroll_summary.
        Obtiene resumen de totales de nómina por categoría.
        """
        service = self._get_dashboard_query_service()

        # Configuración de categorías (misma que el método original)
        SUMMARY_CONFIG = {
            'sueldo': {'categories': ['BASIC', 'BASICD'], 'name': 'Sueldo Básico', 'icon': 'fa-money', 'color': 'success', 'type': 'earning'},
            'auxilio': {'categories': ['AUX', 'AUS', 'ALW'], 'name': 'Auxilio Transporte', 'icon': 'fa-bus', 'color': 'info', 'type': 'earning'},
            'horas_extras': {'categories': ['HEYREC', 'HED', 'HEN', 'HEDDF', 'HENDF'], 'name': 'Horas Extras y Recargos', 'icon': 'fa-clock', 'color': 'warning', 'type': 'earning'},
            'comisiones': {'categories': ['COMISIONES'], 'name': 'Comisiones', 'icon': 'fa-percent', 'color': 'success', 'type': 'earning'},
            'vacaciones': {'categories': ['VACACIONES'], 'name': 'Vacaciones', 'icon': 'fa-plane', 'color': 'success', 'type': 'earning'},
            'incapacidades': {'categories': ['INCAPACIDAD', 'ACCIDENTE_TRABAJO'], 'name': 'Incapacidades', 'icon': 'fa-medkit', 'color': 'info', 'type': 'earning'},
            'licencias': {'categories': ['LICENCIA_MATERNIDAD', 'LICENCIA_REMUNERADA', 'LICENCIA_NO_REMUNERADA'], 'name': 'Licencias', 'icon': 'fa-calendar-times', 'color': 'secondary', 'type': 'earning'},
            'prestaciones': {'categories': ['PRESTACIONES_SOCIALES', 'PRIMA'], 'name': 'Prestaciones Sociales', 'icon': 'fa-gift', 'color': 'primary', 'type': 'earning'},
            'devengos_salariales': {'categories': ['DEV_SALARIAL'], 'name': 'Otros Devengos Salariales', 'icon': 'fa-plus-circle', 'color': 'success', 'type': 'earning'},
            'devengos_no_salariales': {'categories': ['DEV_NO_SALARIAL', 'COMPLEMENTARIOS'], 'name': 'Devengos No Salariales', 'icon': 'fa-plus', 'color': 'info', 'type': 'earning'},
            'seguridad_social': {'categories': ['SSOCIAL', 'SS_EMP'], 'name': 'Seguridad Social', 'icon': 'fa-shield', 'color': 'danger', 'type': 'deduction'},
            'retencion': {'categories': ['RTEFTE'], 'name': 'Retención Fuente', 'icon': 'fa-percent', 'color': 'warning', 'type': 'deduction'},
            'deducciones': {'categories': ['DED', 'DEDUCCIONES', 'DEDUCCION', 'SANCIONES', 'DESCUENTO_AFC'], 'name': 'Deducciones', 'icon': 'fa-minus-circle', 'color': 'danger', 'type': 'deduction'},
        }

        # Construir config para query
        categories_config = {k: v['categories'] for k, v in SUMMARY_CONFIG.items()}

        row = service.get_payroll_summary_by_categories_config(
            date_from=date_from,
            date_to=date_to,
            company_id=self.env.company.id,
            categories_config=categories_config,
            department_id=department_id,
            batch_id=batch_id,
        )

        # Formatear resultado
        summary_items = []
        total_earnings = 0
        total_deductions = 0

        for key, config in SUMMARY_CONFIG.items():
            total = row.get(f'{key}_total', 0) or 0
            employees = row.get(f'{key}_employees', 0) or 0

            if total > 0:
                item = {
                    'key': key,
                    'name': config['name'],
                    'icon': config['icon'],
                    'color': config['color'],
                    'type': config['type'],
                    'total': total,
                    'formatted': self._format_currency(total),
                    'count': 0,  # No disponible en versión SQL simplificada
                    'employees': employees,
                }
                summary_items.append(item)

                if config['type'] == 'earning':
                    total_earnings += total
                else:
                    total_deductions += total

        # Use Spanish keys to match JavaScript expectations
        return {
            'items': summary_items,
            'total_devengos': total_earnings,
            'total_deducciones': total_deductions,
            'neto': total_earnings - total_deductions,
            'formatted_devengos': self._format_currency(total_earnings),
            'formatted_deducciones': self._format_currency(total_deductions),
            'formatted_neto': self._format_currency(total_earnings - total_deductions),
            'payslips_count': row.get('payslips_count', 0) or 0,
            'employees_count': row.get('employees_count', 0) or 0,
        }

