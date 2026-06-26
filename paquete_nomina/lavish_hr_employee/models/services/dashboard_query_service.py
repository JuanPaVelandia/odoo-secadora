# -*- coding: utf-8 -*-
"""
Servicio de Consultas Optimizadas para Dashboard
================================================

Este servicio centraliza todas las consultas del dashboard de nómina
usando SQL optimizado en lugar de ORM para mejor rendimiento.

Uso:
    service = self.env['dashboard.query.service']
    data = service.get_payslip_totals(date_from, date_to, company_id, department_id)
"""

from odoo import models, api
from datetime import date
from typing import Dict, Any, Optional, List

from .service_sql import (
    DashboardKPIsQueryBuilder,
    DashboardOvertimeQueryBuilder,
    DashboardAbsencesQueryBuilder,
    DashboardTrendQueryBuilder,
    DashboardEmployeesQueryBuilder,
    DashboardPendingLeavesQueryBuilder,
    DashboardPayrollSummaryQueryBuilder,
    DashboardAccidentsChartQueryBuilder,
    DashboardIncomeDeductionsQueryBuilder,
    DashboardDisabilityQueryBuilder,
    DashboardPayrollSummaryDetailQueryBuilder,
)


class DashboardQueryService(models.AbstractModel):
    """
    Servicio centralizado para consultas optimizadas del dashboard.

    Usa SQL builders para consultas de alto rendimiento.
    """
    _name = 'dashboard.query.service'
    _description = 'Servicio de consultas optimizadas para dashboard'

    # =========================================================================
    # CÓDIGOS DE CONFIGURACIÓN
    # =========================================================================

    RETENTION_CODES = (
        'RTEFTE001', 'RTEFTE002', 'RTEFTE_PROC1', 'RTEFTE_PROC2',
        'RETENCION_FUENTE', 'RET_FUENTE',
    )

    DEVENGADO_CATEGORIES = ('DEV_SALARIAL', 'DEV', 'DEVENGOS')
    DEDUCCION_CATEGORIES = ('DED', 'DEDUCCIONES', 'RTEFTE')

    # =========================================================================
    # CONSULTAS DE KPIs
    # =========================================================================

    def get_kpis_all(
        self,
        date_from: date,
        date_to: date,
        company_id: int,
        department_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Obtiene todos los KPIs básicos en consultas SQL optimizadas.

        Returns:
            Dict con todos los KPIs: empleados, nóminas, accidentes, ausencias, etc.
        """
        builder = DashboardKPIsQueryBuilder()
        builder.for_company(company_id)
        builder.for_department(department_id)
        builder.in_period(date_from, date_to)

        result = {}

        # 1. Empleados activos
        query, params = builder.build_active_employees_count()
        self._cr.execute(query, params)
        row = self._cr.dictfetchone()
        result['total_employees'] = row['total_employees'] if row else 0

        # 2. Resumen de nóminas
        query, params = builder.build_payslip_summary()
        self._cr.execute(query, params)
        row = self._cr.dictfetchone()
        result['payslip_count'] = row['payslip_count'] if row else 0
        result['payslip_employee_count'] = row['employee_count'] if row else 0
        result['payslip_net_total'] = row['net_total'] or 0 if row else 0

        # 3. Accidentes laborales
        query, params = builder.build_accidents_count()
        self._cr.execute(query, params)
        row = self._cr.dictfetchone()
        result['accidents_count'] = row['accidents_count'] if row else 0

        # 4. Resumen de ausencias
        query, params = builder.build_leaves_summary()
        self._cr.execute(query, params)
        row = self._cr.dictfetchone()
        result['total_leaves'] = row['total_leaves'] if row else 0
        result['total_leave_days'] = row['total_days'] or 0 if row else 0

        # 5. Solicitudes pendientes
        query, params = builder.build_pending_requests_count()
        self._cr.execute(query, params)
        row = self._cr.dictfetchone()
        result['pending_requests'] = row['pending_count'] if row else 0

        # 6. Nuevos empleados
        query, params = builder.build_new_employees_count()
        self._cr.execute(query, params)
        row = self._cr.dictfetchone()
        result['new_employees'] = row['new_employees'] if row else 0

        # 7. Resumen horas extras (desde líneas de nómina HEYREC*)
        query, params = builder.build_overtime_summary()
        self._cr.execute(query, params)
        row = self._cr.dictfetchone()
        result['total_overtime_hours'] = row['total_hours'] or 0 if row else 0
        result['overtime_count'] = row['overtime_count'] if row else 0
        result['overtime_employee_count'] = row['employee_count'] if row else 0
        result['avg_overtime_rate'] = row['avg_rate'] or 0 if row else 0

        # Calcular promedio de horas extras por empleado
        # Usar employee_count de overtime si hay horas, sino total_employees
        divisor = result['overtime_employee_count'] if result['overtime_employee_count'] > 0 else result['total_employees']
        if divisor > 0:
            result['avg_overtime_hours'] = result['total_overtime_hours'] / divisor
        else:
            result['avg_overtime_hours'] = 0

        return result

    def get_payslip_totals_by_category(
        self,
        date_from: date,
        date_to: date,
        company_id: int,
        department_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Obtiene totales de nómina agrupados por categoría padre.

        Args:
            date_from: Fecha inicio
            date_to: Fecha fin
            company_id: ID de la compañía
            department_id: ID del departamento (opcional)

        Returns:
            Dict con totales por categoría y estadísticas generales
        """
        builder = DashboardKPIsQueryBuilder()
        builder.for_company(company_id)
        builder.for_department(department_id)
        builder.in_period(date_from, date_to)

        query, params = builder.build_payslip_totals()
        self._cr.execute(query, params)
        rows = self._cr.dictfetchall()

        # Procesar resultados
        totals_by_category = {}
        total_devengado = 0.0
        total_deducciones = 0.0
        total_payslips = 0
        total_employees = set()

        for row in rows:
            cat_code = row['category_code']
            totals_by_category[cat_code] = {
                'name': row['category_name'],
                'total': row['total'],
                'payslip_count': row['payslip_count'],
                'employee_count': row['employee_count'],
            }

            # Acumular totales
            if cat_code in self.DEVENGADO_CATEGORIES or cat_code.startswith('DEV'):
                total_devengado += row['total']
            elif cat_code in self.DEDUCCION_CATEGORIES or cat_code.startswith('DED'):
                total_deducciones += abs(row['total'])

            total_payslips = max(total_payslips, row['payslip_count'])

        return {
            'by_category': totals_by_category,
            'total_devengado': total_devengado,
            'total_deducciones': total_deducciones,
            'total_payslips': total_payslips,
        }

    def get_retention_totals(
        self,
        date_from: date,
        date_to: date,
        company_id: int,
        department_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Obtiene totales de retención en la fuente.

        Returns:
            Dict con base de retención, total retenido, y estadísticas
        """
        builder = DashboardKPIsQueryBuilder()
        builder.for_company(company_id)
        builder.for_department(department_id)
        builder.in_period(date_from, date_to)

        query, params = builder.build_retention_totals(self.RETENTION_CODES)
        self._cr.execute(query, params)
        row = self._cr.dictfetchone()

        if not row:
            return {
                'base_retencion': 0.0,
                'total_retenido': 0.0,
                'payslip_count': 0,
                'employee_count': 0,
            }

        return {
            'base_retencion': row['base_retencion'] or 0.0,
            'total_retenido': row['total_retenido'] or 0.0,
            'payslip_count': row['payslip_count'] or 0,
            'employee_count': row['employee_count'] or 0,
        }

    # =========================================================================
    # CONSULTAS DE HORAS EXTRAS
    # =========================================================================

    def get_overtime_by_department(
        self,
        date_from: date,
        date_to: date,
        company_id: int,
    ) -> List[Dict[str, Any]]:
        """
        Obtiene horas extras agrupadas por departamento.

        Returns:
            Lista de dicts con departamento, horas, conteo
        """
        builder = DashboardOvertimeQueryBuilder()
        builder.for_company(company_id)
        builder.in_period(date_from, date_to)

        query, params = builder.build_by_department()
        self._cr.execute(query, params)

        return self._cr.dictfetchall()

    def get_overtime_by_type(
        self,
        date_from: date,
        date_to: date,
        company_id: int,
    ) -> List[Dict[str, Any]]:
        """
        Obtiene horas extras agrupadas por tipo.

        Returns:
            Lista de dicts con tipo, horas, conteo
        """
        builder = DashboardOvertimeQueryBuilder()
        builder.for_company(company_id)
        builder.in_period(date_from, date_to)

        query, params = builder.build_by_type()
        self._cr.execute(query, params)

        return self._cr.dictfetchall()

    # =========================================================================
    # CONSULTAS DE AUSENCIAS
    # =========================================================================

    def get_absences_by_type(
        self,
        date_from: date,
        date_to: date,
        company_id: int,
        department_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Obtiene ausencias agrupadas por tipo.

        Returns:
            Lista de dicts con tipo, días, conteo
        """
        builder = DashboardAbsencesQueryBuilder()
        builder.for_company(company_id)
        builder.for_department(department_id)
        builder.in_period(date_from, date_to)

        query, params = builder.build_by_type()
        self._cr.execute(query, params)

        return self._cr.dictfetchall()

    def get_accidents(
        self,
        date_from: date,
        date_to: date,
        company_id: int,
        department_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Obtiene accidentes laborales (novelty = 'irl').

        Returns:
            Lista de accidentes con detalle de empleado
        """
        builder = DashboardAbsencesQueryBuilder()
        builder.for_company(company_id)
        builder.for_department(department_id)
        builder.in_period(date_from, date_to)

        query, params = builder.build_accidents()
        self._cr.execute(query, params)

        return self._cr.dictfetchall()

    # =========================================================================
    # CONSULTAS DE TENDENCIAS
    # =========================================================================

    def get_payroll_trend(
        self,
        date_to: date,
        company_id: int,
        department_id: Optional[int] = None,
        months_back: int = 6,
    ) -> List[Dict[str, Any]]:
        """
        Obtiene tendencia de nómina por mes.

        Args:
            date_to: Fecha hasta (último mes)
            company_id: ID de la compañía
            department_id: ID del departamento (opcional)
            months_back: Cantidad de meses hacia atrás

        Returns:
            Lista de dicts con período, totales
        """
        builder = DashboardTrendQueryBuilder()
        builder.for_company(company_id)
        builder.for_department(department_id)
        builder.months_back(months_back)

        query, params = builder.build_payroll_trend(date_to)
        self._cr.execute(query, params)

        return self._cr.dictfetchall()

    def get_devengos_deducciones_trend(
        self,
        date_to: date,
        company_id: int,
        department_id: Optional[int] = None,
        months_back: int = 6,
    ) -> List[Dict[str, Any]]:
        """
        Obtiene tendencia de devengos vs deducciones por mes.

        Returns:
            Lista de dicts con período, devengos, deducciones
        """
        builder = DashboardTrendQueryBuilder()
        builder.for_company(company_id)
        builder.for_department(department_id)
        builder.months_back(months_back)

        query, params = builder.build_devengos_deducciones_trend(date_to)
        self._cr.execute(query, params)

        return self._cr.dictfetchall()

    # =========================================================================
    # CONSULTAS DE EMPLEADOS
    # =========================================================================

    def get_employees_by_city(
        self,
        date_to: date,
        company_id: int,
        department_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Obtiene empleados agrupados por ciudad.

        Returns:
            Lista de dicts con ciudad, conteo
        """
        builder = DashboardEmployeesQueryBuilder()
        builder.for_company(company_id)
        builder.for_department(department_id)
        builder.in_period(date_to, date_to)  # Solo usa date_to para filtrar activos

        query, params = builder.build_by_city()
        self._cr.execute(query, params)

        return self._cr.dictfetchall()

    def get_new_employees(
        self,
        date_from: date,
        date_to: date,
        company_id: int,
        department_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Obtiene nuevos empleados en el período.

        Returns:
            Lista de nuevos empleados con detalles
        """
        builder = DashboardEmployeesQueryBuilder()
        builder.for_company(company_id)
        builder.for_department(department_id)
        builder.in_period(date_from, date_to)

        query, params = builder.build_new_employees()
        self._cr.execute(query, params)

        return self._cr.dictfetchall()

    def get_expiring_contracts(
        self,
        company_id: int,
        department_id: Optional[int] = None,
        days_ahead: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Obtiene contratos próximos a vencer.

        Args:
            company_id: ID de la compañía
            department_id: ID del departamento (opcional)
            days_ahead: Días hacia adelante para buscar vencimientos

        Returns:
            Lista de contratos con detalles
        """
        builder = DashboardEmployeesQueryBuilder()
        builder.for_company(company_id)
        builder.for_department(department_id)

        query, params = builder.build_expiring_contracts(days_ahead)
        self._cr.execute(query, params)

        return self._cr.dictfetchall()

    # =========================================================================
    # CONSULTAS DE AUSENCIAS PENDIENTES
    # =========================================================================

    def get_pending_leaves(
        self,
        company_id: int,
        department_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Obtiene ausencias pendientes de aprobación.

        Returns:
            Lista de ausencias pendientes con detalles
        """
        builder = DashboardPendingLeavesQueryBuilder()
        builder.for_company(company_id)
        builder.for_department(department_id)

        query, params = builder.build_pending_leaves()
        self._cr.execute(query, params)

        return self._cr.dictfetchall()

    # =========================================================================
    # CONSULTAS DE RESUMEN DE NÓMINA
    # =========================================================================

    def get_payroll_summary_by_category(
        self,
        date_from: date,
        date_to: date,
        company_id: int,
        category_codes: tuple,
        department_id: Optional[int] = None,
        batch_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Obtiene resumen de nómina agrupado por categoría.

        Args:
            category_codes: Tupla de códigos de categoría a buscar

        Returns:
            Lista de totales por categoría
        """
        builder = DashboardPayrollSummaryQueryBuilder()
        builder.for_company(company_id)
        builder.for_department(department_id)
        builder.in_period(date_from, date_to)
        builder.for_batch(batch_id)

        query, params = builder.build_summary_by_category(category_codes)
        self._cr.execute(query, params)

        return self._cr.dictfetchall()

    def get_payroll_summary_by_rule(
        self,
        date_from: date,
        date_to: date,
        company_id: int,
        rule_codes: tuple,
        department_id: Optional[int] = None,
        batch_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Obtiene resumen de nómina agrupado por código de regla.

        Args:
            rule_codes: Tupla de códigos de regla a buscar

        Returns:
            Lista de totales por regla
        """
        builder = DashboardPayrollSummaryQueryBuilder()
        builder.for_company(company_id)
        builder.for_department(department_id)
        builder.in_period(date_from, date_to)
        builder.for_batch(batch_id)

        query, params = builder.build_summary_by_rule_code(rule_codes)
        self._cr.execute(query, params)

        return self._cr.dictfetchall()

    # =========================================================================
    # CONSULTAS DE GRÁFICOS ADICIONALES
    # =========================================================================

    def get_accidents_by_month(
        self,
        date_from: date,
        company_id: int,
        months_back: int = 6,
    ) -> List[Dict[str, Any]]:
        """
        Obtiene accidentes agrupados por mes para el gráfico.

        Args:
            date_from: Fecha de referencia
            company_id: ID de la compañía
            months_back: Meses hacia atrás

        Returns:
            Lista con datos por mes (month_label, accidents_count, incidents_count)
        """
        builder = DashboardAccidentsChartQueryBuilder()
        builder.for_company(company_id)
        builder.for_date(date_from)

        query, params = builder.build_accidents_by_month(months_back)
        self._cr.execute(query, params)

        return self._cr.dictfetchall()

    def get_income_deductions_by_category(
        self,
        date_from: date,
        date_to: date,
        company_id: int,
        department_id: Optional[int] = None,
        detailed: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Obtiene ingresos y deducciones agrupados por categoría.

        Args:
            date_from: Fecha inicio
            date_to: Fecha fin
            company_id: ID de la compañía
            department_id: ID del departamento (opcional)
            detailed: Si True, incluye detalle por regla

        Returns:
            Lista de categorías con totales
        """
        builder = DashboardIncomeDeductionsQueryBuilder()
        builder.for_company(company_id)
        builder.for_department(department_id)
        builder.in_period(date_from, date_to)

        if detailed:
            query, params = builder.build_totals_by_category()
        else:
            query, params = builder.build_category_totals()

        self._cr.execute(query, params)
        return self._cr.dictfetchall()

    def get_disability_by_type(
        self,
        date_from: date,
        date_to: date,
        company_id: int,
        department_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Obtiene incapacidades agrupadas por tipo de novedad.

        Returns:
            Lista con novelty_code, leave_type_name, cases, total_days
        """
        builder = DashboardDisabilityQueryBuilder()
        builder.for_company(company_id)
        builder.for_department(department_id)
        builder.in_period(date_from, date_to)

        query, params = builder.build_disability_by_type()
        self._cr.execute(query, params)

        return self._cr.dictfetchall()

    def get_disability_comparison(
        self,
        date_from: date,
        date_to: date,
        company_id: int,
        department_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Obtiene comparación de incapacidades período actual vs anterior.

        Returns:
            Lista con current_days, current_cases, prev_days, prev_cases por tipo
        """
        builder = DashboardDisabilityQueryBuilder()
        builder.for_company(company_id)
        builder.for_department(department_id)
        builder.in_period(date_from, date_to)

        query, params = builder.build_disability_comparison()
        self._cr.execute(query, params)

        return self._cr.dictfetchall()

    def get_payroll_summary_by_categories_config(
        self,
        date_from: date,
        date_to: date,
        company_id: int,
        categories_config: Dict[str, list],
        department_id: Optional[int] = None,
        batch_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Obtiene resumen de nómina por configuración de categorías.

        Args:
            categories_config: Dict con {'key': ['CAT1', 'CAT2', ...]}

        Returns:
            Dict con totales por cada key
        """
        builder = DashboardPayrollSummaryDetailQueryBuilder()
        builder.for_company(company_id)
        builder.for_department(department_id)
        builder.in_period(date_from, date_to)
        builder.for_batch(batch_id)

        query, params = builder.build_summary_by_categories(categories_config)
        self._cr.execute(query, params)

        return self._cr.dictfetchone() or {}

