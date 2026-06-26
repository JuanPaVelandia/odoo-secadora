# -*- coding: utf-8 -*-
"""
Dashboard Query Builders
========================

SQL builders especializados para consultas del dashboard de nómina.
Optimiza consultas que el dashboard hace frecuentemente usando SQL directo
en lugar de ORM.

Consultas soportadas:
- KPIs de empleados y nóminas
- Totales de devengos y deducciones por categoría
- Horas extras por departamento
- Ausencias por tipo
- Tendencias de nómina (múltiples períodos)
"""
from typing import List, Dict, Any, Optional, Tuple
from datetime import date
from .base_query_builder import SQLQueryBuilder, JoinDefinition


class DashboardKPIsQueryBuilder(SQLQueryBuilder):
    """
    Builder para consultas de KPIs del dashboard.

    Optimiza las consultas de:
    - Total devengado/deducciones por período
    - Conteo de nóminas
    - Estadísticas de retenciones
    - Empleados activos
    - Accidentes y ausencias
    - Horas extras
    """

    def __init__(self):
        super().__init__()
        self._company_id: Optional[int] = None
        self._department_id: Optional[int] = None
        self._date_from: Optional[date] = None
        self._date_to: Optional[date] = None

    def for_company(self, company_id: int) -> 'DashboardKPIsQueryBuilder':
        """Filtra por compañía."""
        self._company_id = company_id
        return self

    def for_department(self, department_id: Optional[int]) -> 'DashboardKPIsQueryBuilder':
        """Filtra por departamento (opcional)."""
        self._department_id = department_id
        return self

    def in_period(self, date_from: date, date_to: date) -> 'DashboardKPIsQueryBuilder':
        """Define el período de consulta."""
        self._date_from = date_from
        self._date_to = date_to
        return self

    def build_active_employees_count(self) -> Tuple[str, Dict[str, Any]]:
        """
        Construye query para contar empleados activos.
        """
        self.reset()

        self.select("COUNT(*) AS total_employees")
        self.from_table('hr_employee', 'emp')

        self.where("emp.active = TRUE")
        self.where("(emp.departure_date IS NULL OR emp.departure_date > %(date_to)s)", date_to=self._date_to)

        if self._company_id:
            self.where("emp.company_id = %(company_id)s", company_id=self._company_id)

        if self._department_id:
            self.where("emp.department_id = %(department_id)s", department_id=self._department_id)

        return self.build()

    def build_payslip_summary(self) -> Tuple[str, Dict[str, Any]]:
        """
        Construye query para resumen de nóminas (count, net total).
        """
        self.reset()

        self.select(
            "COUNT(DISTINCT hp.id) AS payslip_count",
            "COUNT(DISTINCT hp.employee_id) AS employee_count",
            "SUM(hp.net_wage) AS net_total",
        )

        self.from_table('hr_payslip', 'hp')

        self.where("hp.state IN %(states)s", states=('done', 'paid'))
        self.where("hp.date_from >= %(date_from)s", date_from=self._date_from)
        self.where("hp.date_to <= %(date_to)s", date_to=self._date_to)

        if self._company_id:
            self.where("hp.company_id = %(company_id)s", company_id=self._company_id)

        if self._department_id:
            self.join('hr_employee', 'emp', 'emp.id = hp.employee_id')
            self.where("emp.department_id = %(department_id)s", department_id=self._department_id)

        return self.build()

    def build_accidents_count(self) -> Tuple[str, Dict[str, Any]]:
        """
        Construye query para contar accidentes laborales (novelty = 'irl').
        """
        self.reset()

        self.select("COUNT(*) AS accidents_count")
        self.from_table('hr_leave', 'hl')
        self.join('hr_leave_type', 'hlt', 'hlt.id = hl.holiday_status_id')
        self.join('hr_employee', 'emp', 'emp.id = hl.employee_id')

        self.where("hl.state = %(state)s", state='validate')
        self.where("hlt.novelty = %(novelty)s", novelty='irl')
        self.where("""(
            (hl.request_date_from >= %(date_from)s AND hl.request_date_from <= %(date_to)s)
            OR (hl.request_date_to >= %(date_from)s AND hl.request_date_to <= %(date_to)s)
        )""", date_from=self._date_from, date_to=self._date_to)

        if self._company_id:
            self.where("emp.company_id = %(company_id)s", company_id=self._company_id)

        if self._department_id:
            self.where("emp.department_id = %(department_id)s", department_id=self._department_id)

        return self.build()

    def build_leaves_summary(self) -> Tuple[str, Dict[str, Any]]:
        """
        Construye query para resumen de ausencias (count, total days).
        """
        self.reset()

        self.select(
            "COUNT(*) AS total_leaves",
            "COALESCE(SUM(hl.number_of_days), 0) AS total_days",
        )
        self.from_table('hr_leave', 'hl')
        self.join('hr_employee', 'emp', 'emp.id = hl.employee_id')

        self.where("hl.state = %(state)s", state='validate')
        self.where("""(
            (hl.request_date_from >= %(date_from)s AND hl.request_date_from <= %(date_to)s)
            OR (hl.request_date_to >= %(date_from)s AND hl.request_date_to <= %(date_to)s)
        )""", date_from=self._date_from, date_to=self._date_to)

        if self._company_id:
            self.where("emp.company_id = %(company_id)s", company_id=self._company_id)

        if self._department_id:
            self.where("emp.department_id = %(department_id)s", department_id=self._department_id)

        return self.build()

    def build_pending_requests_count(self) -> Tuple[str, Dict[str, Any]]:
        """
        Construye query para contar solicitudes pendientes.
        """
        self.reset()

        self.select("COUNT(*) AS pending_count")
        self.from_table('hr_leave', 'hl')
        self.join('hr_employee', 'emp', 'emp.id = hl.employee_id')

        self.where("hl.state = %(state)s", state='confirm')

        if self._company_id:
            self.where("emp.company_id = %(company_id)s", company_id=self._company_id)

        if self._department_id:
            self.where("emp.department_id = %(department_id)s", department_id=self._department_id)

        return self.build()

    def build_new_employees_count(self) -> Tuple[str, Dict[str, Any]]:
        """
        Construye query para contar nuevos empleados en el período.
        """
        self.reset()

        self.select("COUNT(*) AS new_employees")
        self.from_table('hr_employee', 'emp')

        self.where("emp.first_contract_date >= %(date_from)s", date_from=self._date_from)
        self.where("emp.first_contract_date <= %(date_to)s", date_to=self._date_to)

        if self._company_id:
            self.where("emp.company_id = %(company_id)s", company_id=self._company_id)

        if self._department_id:
            self.where("emp.department_id = %(department_id)s", department_id=self._department_id)

        return self.build()

    def build_overtime_summary(self) -> Tuple[str, Dict[str, Any]]:
        """
        Construye query para resumen de horas extras usando líneas de nómina.

        Usa hr_payslip_line con reglas de horas extras (código HEYREC*)
        para obtener cantidad (horas) y porcentaje promedio (rate).
        """
        self.reset()

        # Usar líneas de nómina con reglas de horas extras (HEYREC*)
        # quantity = horas, rate = porcentaje (ej: 125, 175, 200)
        self.select(
            "COALESCE(SUM(hpl.quantity), 0) AS total_hours",
            "COUNT(DISTINCT hpl.id) AS overtime_count",
            "COUNT(DISTINCT hp.employee_id) AS employee_count",
            "COALESCE(AVG(hpl.rate), 0) AS avg_rate",
        )
        self.from_table('hr_payslip_line', 'hpl')
        self.join('hr_payslip', 'hp', 'hp.id = hpl.slip_id')
        self.join('hr_salary_rule', 'hsr', 'hsr.id = hpl.salary_rule_id')

        # Filtrar por reglas de horas extras (código empieza con HEYREC)
        self.where("hsr.code LIKE %(rule_code_pattern)s", rule_code_pattern='HEYREC%')
        self.where("hp.state IN %(payslip_states)s", payslip_states=('done', 'paid'))
        self.where("hp.date_from >= %(date_from)s", date_from=self._date_from)
        self.where("hp.date_to <= %(date_to)s", date_to=self._date_to)
        # Solo contar líneas con cantidad > 0
        self.where("COALESCE(hpl.quantity, 0) > 0")

        if self._company_id:
            self.where("hp.company_id = %(company_id)s", company_id=self._company_id)

        if self._department_id:
            self.join('hr_employee', 'emp', 'emp.id = hp.employee_id')
            self.where("emp.department_id = %(department_id)s", department_id=self._department_id)

        return self.build()

    def build_payslip_totals(self) -> Tuple[str, Dict[str, Any]]:
        """
        Construye query para totales de nóminas por categoría.

        Returns:
            Tupla (query, params) con totales por categoría padre.
        """
        self.reset()

        self.select(
            "COALESCE(cat_parent.code, cat.code) AS category_code",
            "COALESCE(cat_parent.name->>'es_CO', cat_parent.name->>'en_US', cat.name->>'es_CO', cat.name->>'en_US') AS category_name",
            "SUM(hpl.total) AS total",
            "COUNT(DISTINCT hp.id) AS payslip_count",
            "COUNT(DISTINCT hp.employee_id) AS employee_count",
        )

        self.from_table('hr_payslip_line', 'hpl')
        self.join('hr_payslip', 'hp', 'hp.id = hpl.slip_id')
        self.join('hr_salary_rule_category', 'cat', 'cat.id = hpl.category_id')
        self.left_join('hr_salary_rule_category', 'cat_parent', 'cat_parent.id = cat.parent_id')

        # Filtros base
        self.where("hp.state IN %(states)s", states=('done', 'paid'))
        self.where("hp.date_from >= %(date_from)s", date_from=self._date_from)
        self.where("hp.date_to <= %(date_to)s", date_to=self._date_to)

        if self._company_id:
            self.where("hp.company_id = %(company_id)s", company_id=self._company_id)

        if self._department_id:
            self.join('hr_employee', 'emp', 'emp.id = hp.employee_id')
            self.where("emp.department_id = %(department_id)s", department_id=self._department_id)

        self.group_by(
            "COALESCE(cat_parent.code, cat.code)",
            "COALESCE(cat_parent.name->>'es_CO', cat_parent.name->>'en_US', cat.name->>'es_CO', cat.name->>'en_US')"
        )
        self.order_by("total DESC")

        return self.build()

    def build_retention_totals(self, retention_codes: Tuple[str, ...]) -> Tuple[str, Dict[str, Any]]:
        """
        Construye query para totales de retención en la fuente.

        Args:
            retention_codes: Códigos de reglas de retención
        """
        self.reset()

        self.select(
            "SUM(hpl.amount) AS base_retencion",
            "SUM(ABS(hpl.total)) AS total_retenido",
            "COUNT(DISTINCT hp.id) AS payslip_count",
            "COUNT(DISTINCT hp.employee_id) AS employee_count",
        )

        self.from_table('hr_payslip_line', 'hpl')
        self.join('hr_payslip', 'hp', 'hp.id = hpl.slip_id')
        self.join('hr_salary_rule', 'rule', 'rule.id = hpl.salary_rule_id')
        self.join('hr_salary_rule_category', 'cat', 'cat.id = hpl.category_id')
        self.left_join('hr_salary_rule_category', 'cat_parent', 'cat_parent.id = cat.parent_id')

        # Filtros base
        self.where("hp.state IN %(states)s", states=('done', 'paid'))
        self.where("hp.date_from >= %(date_from)s", date_from=self._date_from)
        self.where("hp.date_to <= %(date_to)s", date_to=self._date_to)

        # Filtro de retención (por código de categoría o regla)
        self.where("""(
            cat.code = 'RTEFTE'
            OR cat_parent.code = 'RTEFTE'
            OR rule.code IN %(retention_codes)s
        )""", retention_codes=retention_codes)

        if self._company_id:
            self.where("hp.company_id = %(company_id)s", company_id=self._company_id)

        if self._department_id:
            self.join('hr_employee', 'emp', 'emp.id = hp.employee_id')
            self.where("emp.department_id = %(department_id)s", department_id=self._department_id)

        return self.build()


class DashboardOvertimeQueryBuilder(SQLQueryBuilder):
    """
    Builder para consultas de horas extras.

    Agrupa horas extras por departamento para gráficos del dashboard.
    """

    def __init__(self):
        super().__init__()
        self._company_id: Optional[int] = None
        self._date_from: Optional[date] = None
        self._date_to: Optional[date] = None

    def for_company(self, company_id: int) -> 'DashboardOvertimeQueryBuilder':
        self._company_id = company_id
        return self

    def in_period(self, date_from: date, date_to: date) -> 'DashboardOvertimeQueryBuilder':
        self._date_from = date_from
        self._date_to = date_to
        return self

    def build_by_department(self) -> Tuple[str, Dict[str, Any]]:
        """
        Construye query para horas extras agrupadas por departamento.

        Usa líneas de nómina con reglas HEYREC* para obtener horas y rate.
        """
        self.reset()

        self.select(
            "COALESCE(dep.name->>'es_CO', dep.name->>'en_US', 'Sin Departamento') AS department_name",
            "dep.id AS department_id",
            "COALESCE(SUM(hpl.quantity), 0) AS total_hours",
            "COUNT(DISTINCT hpl.id) AS overtime_count",
            "COUNT(DISTINCT hp.employee_id) AS employee_count",
            "COALESCE(AVG(hpl.rate), 0) AS avg_rate",
        )

        self.from_table('hr_payslip_line', 'hpl')
        self.join('hr_payslip', 'hp', 'hp.id = hpl.slip_id')
        self.join('hr_salary_rule', 'hsr', 'hsr.id = hpl.salary_rule_id')
        self.join('hr_employee', 'emp', 'emp.id = hp.employee_id')
        self.left_join('hr_department', 'dep', 'dep.id = emp.department_id')

        # Filtrar por reglas de horas extras y nóminas procesadas
        self.where("hsr.code LIKE %(rule_code_pattern)s", rule_code_pattern='HEYREC%')
        self.where("hp.state IN %(payslip_states)s", payslip_states=('done', 'paid'))
        self.where("hp.date_from >= %(date_from)s", date_from=self._date_from)
        self.where("hp.date_to <= %(date_to)s", date_to=self._date_to)
        self.where("COALESCE(hpl.quantity, 0) > 0")

        if self._company_id:
            self.where("hp.company_id = %(company_id)s", company_id=self._company_id)

        self.group_by("dep.id", "COALESCE(dep.name->>'es_CO', dep.name->>'en_US', 'Sin Departamento')")
        self.order_by("total_hours DESC")

        return self.build()

    def build_by_type(self) -> Tuple[str, Dict[str, Any]]:
        """
        Construye query para horas extras agrupadas por tipo de regla salarial.

        Usa líneas de nómina con reglas HEYREC* y agrupa por regla.
        """
        self.reset()

        self.select(
            "COALESCE(hsr.name->>'es_CO', hsr.name->>'en_US') AS type",
            "hsr.code AS type_code",
            "COALESCE(SUM(hpl.quantity), 0) AS total_hours",
            "COUNT(DISTINCT hpl.id) AS overtime_count",
            "COUNT(DISTINCT hp.employee_id) AS employee_count",
            "COALESCE(AVG(hpl.rate), 0) AS avg_rate",
        )

        self.from_table('hr_payslip_line', 'hpl')
        self.join('hr_payslip', 'hp', 'hp.id = hpl.slip_id')
        self.join('hr_salary_rule', 'hsr', 'hsr.id = hpl.salary_rule_id')

        # Filtrar por reglas de horas extras y nóminas procesadas
        self.where("hsr.code LIKE %(rule_code_pattern)s", rule_code_pattern='HEYREC%')
        self.where("hp.state IN %(payslip_states)s", payslip_states=('done', 'paid'))
        self.where("hp.date_from >= %(date_from)s", date_from=self._date_from)
        self.where("hp.date_to <= %(date_to)s", date_to=self._date_to)
        self.where("COALESCE(hpl.quantity, 0) > 0")

        if self._company_id:
            self.join('hr_employee', 'emp', 'emp.id = hp.employee_id')
            self.where("emp.company_id = %(company_id)s", company_id=self._company_id)

        self.group_by(
            "hsr.code",
            "COALESCE(hsr.name->>'es_CO', hsr.name->>'en_US')"
        )
        self.order_by("total_hours DESC")

        return self.build()


class DashboardAbsencesQueryBuilder(SQLQueryBuilder):
    """
    Builder para consultas de ausencias.

    Agrupa ausencias por tipo para gráficos del dashboard.
    """

    def __init__(self):
        super().__init__()
        self._company_id: Optional[int] = None
        self._department_id: Optional[int] = None
        self._date_from: Optional[date] = None
        self._date_to: Optional[date] = None

    def for_company(self, company_id: int) -> 'DashboardAbsencesQueryBuilder':
        self._company_id = company_id
        return self

    def for_department(self, department_id: Optional[int]) -> 'DashboardAbsencesQueryBuilder':
        self._department_id = department_id
        return self

    def in_period(self, date_from: date, date_to: date) -> 'DashboardAbsencesQueryBuilder':
        self._date_from = date_from
        self._date_to = date_to
        return self

    def build_by_type(self) -> Tuple[str, Dict[str, Any]]:
        """
        Construye query para ausencias agrupadas por tipo.
        """
        self.reset()

        self.select(
            "COALESCE(hlt.name->>'es_CO', hlt.name->>'en_US') AS type_name",
            "hlt.id AS type_id",
            "COALESCE(hlt.novelty, 'other') AS novelty_code",
            "COUNT(hl.id) AS leave_count",
            "SUM(hl.number_of_days) AS total_days",
            "COUNT(DISTINCT hl.employee_id) AS employee_count",
        )

        self.from_table('hr_leave', 'hl')
        self.join('hr_leave_type', 'hlt', 'hlt.id = hl.holiday_status_id')
        self.join('hr_employee', 'emp', 'emp.id = hl.employee_id')

        # Filtros
        self.where("hl.state = %(state)s", state='validate')
        self.where("""(
            (hl.request_date_from >= %(date_from)s AND hl.request_date_from <= %(date_to)s)
            OR (hl.request_date_to >= %(date_from)s AND hl.request_date_to <= %(date_to)s)
        )""", date_from=self._date_from, date_to=self._date_to)

        if self._company_id:
            self.where("emp.company_id = %(company_id)s", company_id=self._company_id)

        if self._department_id:
            self.where("emp.department_id = %(department_id)s", department_id=self._department_id)

        self.group_by("hlt.id", "COALESCE(hlt.name->>'es_CO', hlt.name->>'en_US')", "hlt.novelty")
        self.order_by("total_days DESC")

        return self.build()

    def build_accidents(self) -> Tuple[str, Dict[str, Any]]:
        """
        Construye query para accidentes laborales (novelty = 'irl').
        """
        self.reset()

        self.select(
            "hl.id",
            "COALESCE(hlt.name->>'es_CO', hlt.name->>'en_US') AS description",
            "emp.name AS employee_name",
            "emp.id AS employee_id",
            "COALESCE(dep.name->>'es_CO', dep.name->>'en_US', 'Sin Departamento') AS department_name",
            "hl.request_date_from AS date_from",
            "hl.request_date_to AS date_to",
            "hl.number_of_days AS days",
        )

        self.from_table('hr_leave', 'hl')
        self.join('hr_leave_type', 'hlt', 'hlt.id = hl.holiday_status_id')
        self.join('hr_employee', 'emp', 'emp.id = hl.employee_id')
        self.left_join('hr_department', 'dep', 'dep.id = emp.department_id')

        # Filtros - solo accidentes de trabajo
        self.where("hl.state = %(state)s", state='validate')
        self.where("hlt.novelty = %(novelty)s", novelty='irl')
        self.where("""(
            (hl.request_date_from >= %(date_from)s AND hl.request_date_from <= %(date_to)s)
            OR (hl.request_date_to >= %(date_from)s AND hl.request_date_to <= %(date_to)s)
        )""", date_from=self._date_from, date_to=self._date_to)

        if self._company_id:
            self.where("emp.company_id = %(company_id)s", company_id=self._company_id)

        if self._department_id:
            self.where("emp.department_id = %(department_id)s", department_id=self._department_id)

        self.order_by("hl.request_date_from DESC")

        return self.build()


class DashboardTrendQueryBuilder(SQLQueryBuilder):
    """
    Builder para consultas de tendencias.

    Agrupa datos por período para gráficos de tendencia.
    """

    def __init__(self):
        super().__init__()
        self._company_id: Optional[int] = None
        self._department_id: Optional[int] = None
        self._months_back: int = 6

    def for_company(self, company_id: int) -> 'DashboardTrendQueryBuilder':
        self._company_id = company_id
        return self

    def for_department(self, department_id: Optional[int]) -> 'DashboardTrendQueryBuilder':
        self._department_id = department_id
        return self

    def months_back(self, months: int) -> 'DashboardTrendQueryBuilder':
        self._months_back = months
        return self

    def build_payroll_trend(self, date_to: date) -> Tuple[str, Dict[str, Any]]:
        """
        Construye query para tendencia de nómina por mes.

        Retorna totales de nómina por mes para los últimos N meses.
        """
        self.reset()

        # Usar date_trunc para agrupar por mes
        self.select(
            "TO_CHAR(date_trunc('month', hp.date_from), 'YYYY-MM') AS period_key",
            "TO_CHAR(date_trunc('month', hp.date_from), 'Mon YYYY') AS period_label",
            "EXTRACT(YEAR FROM date_trunc('month', hp.date_from))::INTEGER AS year",
            "EXTRACT(MONTH FROM date_trunc('month', hp.date_from))::INTEGER AS month",
            "SUM(hp.net_wage) AS net_total",
            "COUNT(DISTINCT hp.id) AS payslip_count",
            "COUNT(DISTINCT hp.employee_id) AS employee_count",
        )

        self.from_table('hr_payslip', 'hp')

        # Filtros
        self.where("hp.state IN %(states)s", states=('done', 'paid'))
        self.where("hp.date_from >= %(date_start)s", date_start=date_to.replace(day=1) - relativedelta(months=self._months_back - 1))
        self.where("hp.date_from <= %(date_end)s", date_end=date_to)

        if self._company_id:
            self.where("hp.company_id = %(company_id)s", company_id=self._company_id)

        if self._department_id:
            self.join('hr_employee', 'emp', 'emp.id = hp.employee_id')
            self.where("emp.department_id = %(department_id)s", department_id=self._department_id)

        self.group_by("date_trunc('month', hp.date_from)")
        self.order_by("date_trunc('month', hp.date_from)")

        return self.build()

    def build_devengos_deducciones_trend(self, date_to: date) -> Tuple[str, Dict[str, Any]]:
        """
        Construye query para tendencia de devengos vs deducciones por mes.
        """
        self.reset()

        self.select(
            "TO_CHAR(hp.date_from, 'YYYY-MM') AS period_key",
            "TO_CHAR(hp.date_from, 'Mon YYYY') AS period_label",
            """SUM(CASE
                WHEN COALESCE(cat_parent.code, cat.code) = 'DEV_SALARIAL'
                     OR COALESCE(cat_parent.code, cat.code) LIKE 'DEV%'
                THEN hpl.total ELSE 0
            END) AS total_devengos""",
            """SUM(CASE
                WHEN COALESCE(cat_parent.code, cat.code) = 'DED'
                     OR COALESCE(cat_parent.code, cat.code) LIKE 'DED%'
                THEN ABS(hpl.total) ELSE 0
            END) AS total_deducciones""",
        )

        self.from_table('hr_payslip_line', 'hpl')
        self.join('hr_payslip', 'hp', 'hp.id = hpl.slip_id')
        self.join('hr_salary_rule_category', 'cat', 'cat.id = hpl.category_id')
        self.left_join('hr_salary_rule_category', 'cat_parent', 'cat_parent.id = cat.parent_id')

        # Filtros
        self.where("hp.state IN %(states)s", states=('done', 'paid'))
        self.where("hp.date_from >= %(date_start)s", date_start=date_to.replace(day=1) - relativedelta(months=self._months_back - 1))
        self.where("hp.date_from <= %(date_end)s", date_end=date_to)

        if self._company_id:
            self.where("hp.company_id = %(company_id)s", company_id=self._company_id)

        if self._department_id:
            self.join('hr_employee', 'emp', 'emp.id = hp.employee_id')
            self.where("emp.department_id = %(department_id)s", department_id=self._department_id)

        self.group_by("period_key", "period_label")
        self.order_by("period_key")

        return self.build()


class DashboardEmployeesQueryBuilder(SQLQueryBuilder):
    """
    Builder para consultas de empleados en el dashboard.
    """

    def __init__(self):
        super().__init__()
        self._company_id: Optional[int] = None
        self._department_id: Optional[int] = None
        self._date_from: Optional[date] = None
        self._date_to: Optional[date] = None

    def for_company(self, company_id: int) -> 'DashboardEmployeesQueryBuilder':
        self._company_id = company_id
        return self

    def for_department(self, department_id: Optional[int]) -> 'DashboardEmployeesQueryBuilder':
        self._department_id = department_id
        return self

    def in_period(self, date_from: date, date_to: date) -> 'DashboardEmployeesQueryBuilder':
        self._date_from = date_from
        self._date_to = date_to
        return self

    def build_by_city(self) -> Tuple[str, Dict[str, Any]]:
        """
        Construye query para empleados agrupados por ciudad.
        """
        self.reset()

        self.select(
            "COALESCE(city.name->>'es_CO', city.name->>'en_US', 'Sin Ciudad') AS city_name",
            "city.id AS city_id",
            "COUNT(DISTINCT emp.id) AS employee_count",
        )

        self.from_table('hr_employee', 'emp')
        self.left_join('res_city', 'city', 'city.id = emp.private_city_id')

        # Filtros - empleados activos
        self.where("emp.active = TRUE")
        self.where("(emp.departure_date IS NULL OR emp.departure_date > %(date_to)s)", date_to=self._date_to)

        if self._company_id:
            self.where("emp.company_id = %(company_id)s", company_id=self._company_id)

        if self._department_id:
            self.where("emp.department_id = %(department_id)s", department_id=self._department_id)

        self.group_by("city.id", "COALESCE(city.name->>'es_CO', city.name->>'en_US', 'Sin Ciudad')")
        self.order_by("employee_count DESC")

        return self.build()

    def build_new_employees(self) -> Tuple[str, Dict[str, Any]]:
        """
        Construye query para nuevos empleados en el período.
        """
        self.reset()

        self.select(
            "emp.id",
            "emp.name",
            "emp.identification_id",
            "COALESCE(dep.name->>'es_CO', dep.name->>'en_US', 'Sin Departamento') AS department_name",
            "COALESCE(job.name->>'es_CO', job.name->>'en_US') AS job_name",
            "emp.first_contract_date",
        )

        self.from_table('hr_employee', 'emp')
        self.left_join('hr_department', 'dep', 'dep.id = emp.department_id')
        self.left_join('hr_job', 'job', 'job.id = emp.job_id')

        # Filtros - nuevos en el período
        self.where("emp.first_contract_date >= %(date_from)s", date_from=self._date_from)
        self.where("emp.first_contract_date <= %(date_to)s", date_to=self._date_to)

        if self._company_id:
            self.where("emp.company_id = %(company_id)s", company_id=self._company_id)

        if self._department_id:
            self.where("emp.department_id = %(department_id)s", department_id=self._department_id)

        self.order_by("emp.first_contract_date DESC")

        return self.build()

    def build_expiring_contracts(self, days_ahead: int = 30) -> Tuple[str, Dict[str, Any]]:
        """
        Construye query para contratos próximos a vencer.

        Args:
            days_ahead: Días hacia adelante para buscar vencimientos
        """
        self.reset()

        self.select(
            "hc.id AS contract_id",
            "emp.id AS employee_id",
            "emp.name AS employee_name",
            "emp.identification_id",
            "COALESCE(dep.name->>'es_CO', dep.name->>'en_US', 'Sin Departamento') AS department_name",
            "COALESCE(job.name->>'es_CO', job.name->>'en_US') AS job_name",
            "hc.date_end AS contract_end_date",
            "(hc.date_end - CURRENT_DATE) AS days_remaining",
        )

        self.from_table('hr_contract', 'hc')
        self.join('hr_employee', 'emp', 'emp.id = hc.employee_id')
        self.left_join('hr_department', 'dep', 'dep.id = emp.department_id')
        self.left_join('hr_job', 'job', 'job.id = hc.job_id')

        # Filtros - contratos activos con fecha fin próxima
        self.where("hc.state = %(state)s", state='open')
        self.where("hc.date_end IS NOT NULL")
        self.where("hc.date_end >= CURRENT_DATE")
        self.where("hc.date_end <= CURRENT_DATE + %(days_ahead)s", days_ahead=days_ahead)

        if self._company_id:
            self.where("hc.company_id = %(company_id)s", company_id=self._company_id)

        if self._department_id:
            self.where("emp.department_id = %(department_id)s", department_id=self._department_id)

        self.order_by("hc.date_end ASC")

        return self.build()


class DashboardPendingLeavesQueryBuilder(SQLQueryBuilder):
    """
    Builder para consultas de ausencias pendientes de aprobación.
    """

    def __init__(self):
        super().__init__()
        self._company_id: Optional[int] = None
        self._department_id: Optional[int] = None

    def for_company(self, company_id: int) -> 'DashboardPendingLeavesQueryBuilder':
        self._company_id = company_id
        return self

    def for_department(self, department_id: Optional[int]) -> 'DashboardPendingLeavesQueryBuilder':
        self._department_id = department_id
        return self

    def build_pending_leaves(self) -> Tuple[str, Dict[str, Any]]:
        """
        Construye query para ausencias pendientes de aprobar.
        """
        self.reset()

        self.select(
            "hl.id",
            "COALESCE(hlt.name->>'es_CO', hlt.name->>'en_US') AS description",
            "emp.id AS employee_id",
            "emp.name AS employee_name",
            "COALESCE(dep.name->>'es_CO', dep.name->>'en_US', 'Sin Departamento') AS department_name",
            "COALESCE(hlt.name->>'es_CO', hlt.name->>'en_US') AS leave_type_name",
            "hlt.id AS leave_type_id",
            "hl.request_date_from",
            "hl.request_date_to",
            "hl.number_of_days",
            "hl.state",
            "(CURRENT_DATE - hl.request_date_from) AS request_age_days",
        )

        self.from_table('hr_leave', 'hl')
        self.join('hr_employee', 'emp', 'emp.id = hl.employee_id')
        self.join('hr_leave_type', 'hlt', 'hlt.id = hl.holiday_status_id')
        self.left_join('hr_department', 'dep', 'dep.id = emp.department_id')

        # Filtros - solo pendientes
        self.where("hl.state = %(state)s", state='confirm')

        if self._company_id:
            self.where("emp.company_id = %(company_id)s", company_id=self._company_id)

        if self._department_id:
            self.where("emp.department_id = %(department_id)s", department_id=self._department_id)

        self.order_by("hl.request_date_from DESC")

        return self.build()


class DashboardPayrollSummaryQueryBuilder(SQLQueryBuilder):
    """
    Builder para consultas de resumen de nómina por categoría.
    """

    def __init__(self):
        super().__init__()
        self._company_id: Optional[int] = None
        self._department_id: Optional[int] = None
        self._date_from: Optional[date] = None
        self._date_to: Optional[date] = None
        self._batch_id: Optional[int] = None

    def for_company(self, company_id: int) -> 'DashboardPayrollSummaryQueryBuilder':
        self._company_id = company_id
        return self

    def for_department(self, department_id: Optional[int]) -> 'DashboardPayrollSummaryQueryBuilder':
        self._department_id = department_id
        return self

    def in_period(self, date_from: date, date_to: date) -> 'DashboardPayrollSummaryQueryBuilder':
        self._date_from = date_from
        self._date_to = date_to
        return self

    def for_batch(self, batch_id: Optional[int]) -> 'DashboardPayrollSummaryQueryBuilder':
        self._batch_id = batch_id
        return self

    def build_summary_by_category(self, category_codes: Tuple[str, ...]) -> Tuple[str, Dict[str, Any]]:
        """
        Construye query para totales por códigos de categoría.

        Args:
            category_codes: Tupla de códigos de categoría a buscar
        """
        self.reset()

        self.select(
            "COALESCE(cat_parent.code, cat.code) AS category_code",
            "COALESCE(cat_parent.name->>'es_CO', cat_parent.name->>'en_US', cat.name->>'es_CO', cat.name->>'en_US') AS category_name",
            "SUM(hpl.total) AS total",
            "COUNT(DISTINCT hp.id) AS payslip_count",
            "COUNT(DISTINCT hp.employee_id) AS employee_count",
        )

        self.from_table('hr_payslip_line', 'hpl')
        self.join('hr_payslip', 'hp', 'hp.id = hpl.slip_id')
        self.join('hr_salary_rule_category', 'cat', 'cat.id = hpl.category_id')
        self.left_join('hr_salary_rule_category', 'cat_parent', 'cat_parent.id = cat.parent_id')

        # Filtros base
        self.where("hp.state IN %(states)s", states=('done', 'paid'))
        self.where("hp.date_from >= %(date_from)s", date_from=self._date_from)
        self.where("hp.date_to <= %(date_to)s", date_to=self._date_to)

        # Filtro por categorías
        self.where("""(
            cat.code IN %(category_codes)s
            OR cat_parent.code IN %(category_codes)s
        )""", category_codes=category_codes)

        if self._company_id:
            self.where("hp.company_id = %(company_id)s", company_id=self._company_id)

        if self._department_id:
            self.join('hr_employee', 'emp', 'emp.id = hp.employee_id')
            self.where("emp.department_id = %(department_id)s", department_id=self._department_id)

        if self._batch_id:
            self.where("hp.payslip_run_id = %(batch_id)s", batch_id=self._batch_id)

        self.group_by(
            "COALESCE(cat_parent.code, cat.code)",
            "COALESCE(cat_parent.name->>'es_CO', cat_parent.name->>'en_US', cat.name->>'es_CO', cat.name->>'en_US')"
        )
        self.order_by("total DESC")

        return self.build()

    def build_summary_by_rule_code(self, rule_codes: Tuple[str, ...]) -> Tuple[str, Dict[str, Any]]:
        """
        Construye query para totales por códigos de regla.

        Args:
            rule_codes: Tupla de códigos de regla a buscar
        """
        self.reset()

        self.select(
            "rule.code AS rule_code",
            "COALESCE(rule.name->>'es_CO', rule.name->>'en_US') AS rule_name",
            "cat.code AS category_code",
            "SUM(hpl.total) AS total",
            "COUNT(DISTINCT hp.id) AS payslip_count",
            "COUNT(DISTINCT hp.employee_id) AS employee_count",
        )

        self.from_table('hr_payslip_line', 'hpl')
        self.join('hr_payslip', 'hp', 'hp.id = hpl.slip_id')
        self.join('hr_salary_rule', 'rule', 'rule.id = hpl.salary_rule_id')
        self.join('hr_salary_rule_category', 'cat', 'cat.id = hpl.category_id')

        # Filtros base
        self.where("hp.state IN %(states)s", states=('done', 'paid'))
        self.where("hp.date_from >= %(date_from)s", date_from=self._date_from)
        self.where("hp.date_to <= %(date_to)s", date_to=self._date_to)
        self.where("rule.code IN %(rule_codes)s", rule_codes=rule_codes)

        if self._company_id:
            self.where("hp.company_id = %(company_id)s", company_id=self._company_id)

        if self._department_id:
            self.join('hr_employee', 'emp', 'emp.id = hp.employee_id')
            self.where("emp.department_id = %(department_id)s", department_id=self._department_id)

        if self._batch_id:
            self.where("hp.payslip_run_id = %(batch_id)s", batch_id=self._batch_id)

        self.group_by("rule.code", "COALESCE(rule.name->>'es_CO', rule.name->>'en_US')", "cat.code")
        self.order_by("total DESC")

        return self.build()


# Import necesario para build_payroll_trend y build_devengos_deducciones_trend
from dateutil.relativedelta import relativedelta


class DashboardAccidentsChartQueryBuilder(SQLQueryBuilder):
    """
    Builder para consultas de gráfico de accidentes (sst.accident).
    """

    def __init__(self):
        super().__init__()
        self._company_id: Optional[int] = None
        self._date_from: Optional[date] = None

    def for_company(self, company_id: int) -> 'DashboardAccidentsChartQueryBuilder':
        self._company_id = company_id
        return self

    def for_date(self, date_from: date) -> 'DashboardAccidentsChartQueryBuilder':
        self._date_from = date_from
        return self

    def build_accidents_by_month(self, months_back: int = 6) -> Tuple[str, Dict[str, Any]]:
        """
        Construye query para accidentes agrupados por mes.
        Retorna accidentes graves y leves (incidentes) por separado.
        """
        self.reset()

        # Generar serie de meses
        self.select(
            "TO_CHAR(date_series.month_date, 'Mon') AS month_label",
            "date_series.month_date AS month_start",
            """COALESCE(SUM(CASE
                WHEN acc.severity_general IN ('disability', 'permanent_disability', 'death')
                THEN 1 ELSE 0 END), 0) AS accidents_count""",
            """COALESCE(SUM(CASE
                WHEN acc.severity_general IN ('minor', 'medical')
                THEN 1 ELSE 0 END), 0) AS incidents_count""",
        )

        # Usar generate_series para los meses
        self.from_table(f"""(
            SELECT generate_series(
                DATE_TRUNC('month', %(date_from)s::date - INTERVAL '{months_back - 1} months'),
                DATE_TRUNC('month', %(date_from)s::date),
                '1 month'::interval
            )::date AS month_date
        )""", 'date_series', date_from=self._date_from)

        # Left join con accidentes
        self.left_join(
            'sst_accident', 'acc',
            """acc.date_accident >= date_series.month_date
               AND acc.date_accident < (date_series.month_date + INTERVAL '1 month')"""
        )

        if self._company_id:
            # El where debe ser en el ON del join para mantener los meses sin accidentes
            # Modificamos el último join (sst_accident) para incluir filtro de company
            self._joins[-1] = JoinDefinition(
                table='sst_accident',
                alias='acc',
                condition=f"""acc.date_accident >= date_series.month_date
                    AND acc.date_accident < (date_series.month_date + INTERVAL '1 month')
                    AND acc.employee_id IN (SELECT id FROM hr_employee WHERE company_id = {self._company_id})""",
                join_type='LEFT'
            )

        self.group_by("date_series.month_date")
        self.order_by("date_series.month_date ASC")

        return self.build()


class DashboardIncomeDeductionsQueryBuilder(SQLQueryBuilder):
    """
    Builder para consultas de gráfico de ingresos vs deducciones.
    """

    def __init__(self):
        super().__init__()
        self._company_id: Optional[int] = None
        self._department_id: Optional[int] = None
        self._date_from: Optional[date] = None
        self._date_to: Optional[date] = None

    def for_company(self, company_id: int) -> 'DashboardIncomeDeductionsQueryBuilder':
        self._company_id = company_id
        return self

    def for_department(self, department_id: Optional[int]) -> 'DashboardIncomeDeductionsQueryBuilder':
        self._department_id = department_id
        return self

    def in_period(self, date_from: date, date_to: date) -> 'DashboardIncomeDeductionsQueryBuilder':
        self._date_from = date_from
        self._date_to = date_to
        return self

    def build_totals_by_category(self) -> Tuple[str, Dict[str, Any]]:
        """
        Construye query para totales agrupados por categoría padre.
        Optimizado para evitar cargar miles de líneas en memoria.
        """
        self.reset()

        self.select(
            "COALESCE(cat_parent.code, cat.code) AS category_code",
            "COALESCE(cat_parent.name->>'es_CO', cat_parent.name->>'en_US', cat.name->>'es_CO', cat.name->>'en_US') AS category_name",
            "rule.code AS rule_code",
            "COALESCE(rule.name->>'es_CO', rule.name->>'en_US') AS rule_name",
            "SUM(ABS(hpl.total)) AS total",
            "COUNT(DISTINCT hp.id) AS payslip_count",
            "COUNT(DISTINCT hp.employee_id) AS employee_count",
        )

        self.from_table('hr_payslip_line', 'hpl')
        self.join('hr_payslip', 'hp', 'hp.id = hpl.slip_id')
        self.join('hr_salary_rule', 'rule', 'rule.id = hpl.salary_rule_id')
        self.join('hr_salary_rule_category', 'cat', 'cat.id = hpl.category_id')
        self.left_join('hr_salary_rule_category', 'cat_parent', 'cat_parent.id = cat.parent_id')

        # Filtros base
        self.where("hp.state IN %(states)s", states=('done', 'paid'))
        self.where("hp.date_from >= %(date_from)s", date_from=self._date_from)
        self.where("hp.date_to <= %(date_to)s", date_to=self._date_to)
        self.where("rule.sequence < 300")  # Solo líneas de detalle
        self.where("rule.appears_on_payslip = TRUE")

        # Excluir categorías de totales
        self.where("cat.code NOT IN %(total_cats)s", total_cats=(
            'NETO', 'BRUTO', 'TOT_DEV', 'TOT_DED', 'TOTAL_DEVENGADO',
            'TOTAL_DEDUCIDO', 'NET', 'GROSS'
        ))

        if self._company_id:
            self.where("hp.company_id = %(company_id)s", company_id=self._company_id)

        if self._department_id:
            self.join('hr_employee', 'emp', 'emp.id = hp.employee_id')
            self.where("emp.department_id = %(department_id)s", department_id=self._department_id)

        self.group_by(
            "COALESCE(cat_parent.code, cat.code)",
            "COALESCE(cat_parent.name->>'es_CO', cat_parent.name->>'en_US', cat.name->>'es_CO', cat.name->>'en_US')",
            "rule.code",
            "COALESCE(rule.name->>'es_CO', rule.name->>'en_US')"
        )
        self.order_by("total DESC")

        return self.build()

    def build_category_totals(self) -> Tuple[str, Dict[str, Any]]:
        """
        Construye query para totales agrupados solo por categoría (sin reglas).
        Más ligero para gráficos simples.
        """
        self.reset()

        self.select(
            "COALESCE(cat_parent.code, cat.code) AS category_code",
            "COALESCE(cat_parent.name->>'es_CO', cat_parent.name->>'en_US', cat.name->>'es_CO', cat.name->>'en_US') AS category_name",
            "SUM(ABS(hpl.total)) AS total",
            "COUNT(DISTINCT hp.id) AS payslip_count",
            "COUNT(DISTINCT hp.employee_id) AS employee_count",
        )

        self.from_table('hr_payslip_line', 'hpl')
        self.join('hr_payslip', 'hp', 'hp.id = hpl.slip_id')
        self.join('hr_salary_rule', 'rule', 'rule.id = hpl.salary_rule_id')
        self.join('hr_salary_rule_category', 'cat', 'cat.id = hpl.category_id')
        self.left_join('hr_salary_rule_category', 'cat_parent', 'cat_parent.id = cat.parent_id')

        # Filtros base
        self.where("hp.state IN %(states)s", states=('done', 'paid'))
        self.where("hp.date_from >= %(date_from)s", date_from=self._date_from)
        self.where("hp.date_to <= %(date_to)s", date_to=self._date_to)
        self.where("rule.sequence < 300")
        self.where("rule.appears_on_payslip = TRUE")

        # Excluir categorías de totales
        self.where("cat.code NOT IN %(total_cats)s", total_cats=(
            'NETO', 'BRUTO', 'TOT_DEV', 'TOT_DED', 'TOTAL_DEVENGADO',
            'TOTAL_DEDUCIDO', 'NET', 'GROSS'
        ))

        if self._company_id:
            self.where("hp.company_id = %(company_id)s", company_id=self._company_id)

        if self._department_id:
            self.join('hr_employee', 'emp', 'emp.id = hp.employee_id')
            self.where("emp.department_id = %(department_id)s", department_id=self._department_id)

        self.group_by(
            "COALESCE(cat_parent.code, cat.code)",
            "COALESCE(cat_parent.name->>'es_CO', cat_parent.name->>'en_US', cat.name->>'es_CO', cat.name->>'en_US')"
        )
        self.order_by("total DESC")

        return self.build()


class DashboardDisabilityQueryBuilder(SQLQueryBuilder):
    """
    Builder para consultas de gráfico de incapacidades.
    """

    def __init__(self):
        super().__init__()
        self._company_id: Optional[int] = None
        self._department_id: Optional[int] = None
        self._date_from: Optional[date] = None
        self._date_to: Optional[date] = None

    def for_company(self, company_id: int) -> 'DashboardDisabilityQueryBuilder':
        self._company_id = company_id
        return self

    def for_department(self, department_id: Optional[int]) -> 'DashboardDisabilityQueryBuilder':
        self._department_id = department_id
        return self

    def in_period(self, date_from: date, date_to: date) -> 'DashboardDisabilityQueryBuilder':
        self._date_from = date_from
        self._date_to = date_to
        return self

    def build_disability_by_type(self) -> Tuple[str, Dict[str, Any]]:
        """
        Construye query para incapacidades agrupadas por tipo de novedad.
        """
        self.reset()

        self.select(
            "UPPER(hlt.novelty) AS novelty_code",
            "COALESCE(hlt.name->>'es_CO', hlt.name->>'en_US') AS leave_type_name",
            "COUNT(*) AS cases",
            "COALESCE(SUM(hl.number_of_days), 0) AS total_days",
        )

        self.from_table('hr_leave', 'hl')
        self.join('hr_leave_type', 'hlt', 'hlt.id = hl.holiday_status_id')
        self.join('hr_employee', 'emp', 'emp.id = hl.employee_id')

        self.where("hl.state = %(state)s", state='validate')
        self.where("hlt.novelty IS NOT NULL")
        self.where("""(
            (hl.request_date_from >= %(date_from)s AND hl.request_date_from <= %(date_to)s)
            OR (hl.request_date_to >= %(date_from)s AND hl.request_date_to <= %(date_to)s)
        )""", date_from=self._date_from, date_to=self._date_to)

        if self._company_id:
            self.where("emp.company_id = %(company_id)s", company_id=self._company_id)

        if self._department_id:
            self.where("emp.department_id = %(department_id)s", department_id=self._department_id)

        self.group_by("UPPER(hlt.novelty)", "COALESCE(hlt.name->>'es_CO', hlt.name->>'en_US')")
        self.order_by("total_days DESC")

        return self.build()

    def build_disability_comparison(self) -> Tuple[str, Dict[str, Any]]:
        """
        Construye query para comparar incapacidades período actual vs anterior.
        """
        self.reset()

        prev_date_from = self._date_from - relativedelta(months=1)
        prev_date_to = self._date_to - relativedelta(months=1)

        self.select(
            "UPPER(hlt.novelty) AS novelty_code",
            "COALESCE(hlt.name->>'es_CO', hlt.name->>'en_US') AS leave_type_name",
            # Período actual
            """SUM(CASE
                WHEN hl.request_date_from >= %(date_from)s AND hl.request_date_from <= %(date_to)s
                THEN hl.number_of_days ELSE 0 END) AS current_days""",
            """COUNT(CASE
                WHEN hl.request_date_from >= %(date_from)s AND hl.request_date_from <= %(date_to)s
                THEN 1 END) AS current_cases""",
            # Período anterior
            """SUM(CASE
                WHEN hl.request_date_from >= %(prev_date_from)s AND hl.request_date_from <= %(prev_date_to)s
                THEN hl.number_of_days ELSE 0 END) AS prev_days""",
            """COUNT(CASE
                WHEN hl.request_date_from >= %(prev_date_from)s AND hl.request_date_from <= %(prev_date_to)s
                THEN 1 END) AS prev_cases""",
        )

        self._params['prev_date_from'] = prev_date_from
        self._params['prev_date_to'] = prev_date_to

        self.from_table('hr_leave', 'hl')
        self.join('hr_leave_type', 'hlt', 'hlt.id = hl.holiday_status_id')
        self.join('hr_employee', 'emp', 'emp.id = hl.employee_id')

        self.where("hl.state = %(state)s", state='validate')
        self.where("hlt.novelty IS NOT NULL")
        # Incluir ambos períodos
        self.where("""(
            (hl.request_date_from >= %(prev_date_from)s AND hl.request_date_from <= %(date_to)s)
        )""", date_from=self._date_from, date_to=self._date_to)

        if self._company_id:
            self.where("emp.company_id = %(company_id)s", company_id=self._company_id)

        if self._department_id:
            self.where("emp.department_id = %(department_id)s", department_id=self._department_id)

        self.group_by("UPPER(hlt.novelty)", "COALESCE(hlt.name->>'es_CO', hlt.name->>'en_US')")
        self.order_by("current_days DESC")

        return self.build()


class DashboardPayrollSummaryDetailQueryBuilder(SQLQueryBuilder):
    """
    Builder para consultas de resumen detallado de nómina.
    """

    def __init__(self):
        super().__init__()
        self._company_id: Optional[int] = None
        self._department_id: Optional[int] = None
        self._date_from: Optional[date] = None
        self._date_to: Optional[date] = None
        self._batch_id: Optional[int] = None

    def for_company(self, company_id: int) -> 'DashboardPayrollSummaryDetailQueryBuilder':
        self._company_id = company_id
        return self

    def for_department(self, department_id: Optional[int]) -> 'DashboardPayrollSummaryDetailQueryBuilder':
        self._department_id = department_id
        return self

    def in_period(self, date_from: date, date_to: date) -> 'DashboardPayrollSummaryDetailQueryBuilder':
        self._date_from = date_from
        self._date_to = date_to
        return self

    def for_batch(self, batch_id: Optional[int]) -> 'DashboardPayrollSummaryDetailQueryBuilder':
        self._batch_id = batch_id
        return self

    def build_summary_by_categories(self, categories_config: Dict[str, list]) -> Tuple[str, Dict[str, Any]]:
        """
        Construye query para totales por grupos de categorías.

        Args:
            categories_config: Dict con {'key': ['CAT1', 'CAT2', ...]}
        """
        self.reset()

        # Construir CASE para cada grupo de categorías
        case_expressions = [
            # Global counts
            "COUNT(DISTINCT hp.id) AS payslips_count",
            "COUNT(DISTINCT hp.employee_id) AS employees_count",
        ]
        for key, cat_codes in categories_config.items():
            cat_tuple = tuple(cat_codes) if cat_codes else ('__NONE__',)
            case_expressions.append(
                f"SUM(CASE WHEN cat.code IN %({key}_cats)s OR cat_parent.code IN %({key}_cats)s THEN ABS(hpl.total) ELSE 0 END) AS {key}_total"
            )
            case_expressions.append(
                f"COUNT(DISTINCT CASE WHEN cat.code IN %({key}_cats)s OR cat_parent.code IN %({key}_cats)s THEN hp.employee_id END) AS {key}_employees"
            )
            self._params[f'{key}_cats'] = cat_tuple

        self.select(*case_expressions)

        self.from_table('hr_payslip_line', 'hpl')
        self.join('hr_payslip', 'hp', 'hp.id = hpl.slip_id')
        self.join('hr_salary_rule', 'rule', 'rule.id = hpl.salary_rule_id')
        self.join('hr_salary_rule_category', 'cat', 'cat.id = hpl.category_id')
        # Join parent category to also match by parent code
        self.left_join('hr_salary_rule_category', 'cat_parent', 'cat_parent.id = cat.parent_id')

        self.where("hp.state IN %(states)s", states=('done', 'paid'))
        self.where("hp.date_from >= %(date_from)s", date_from=self._date_from)
        self.where("hp.date_to <= %(date_to)s", date_to=self._date_to)
        self.where("rule.appears_on_payslip = TRUE")

        if self._company_id:
            self.where("hp.company_id = %(company_id)s", company_id=self._company_id)

        if self._department_id:
            self.join('hr_employee', 'emp', 'emp.id = hp.employee_id')
            self.where("emp.department_id = %(department_id)s", department_id=self._department_id)

        if self._batch_id:
            self.where("hp.payslip_run_id = %(batch_id)s", batch_id=self._batch_id)

        return self.build()

    def build_simple_category_totals(self, category_codes: Tuple[str, ...]) -> Tuple[str, Dict[str, Any]]:
        """
        Construye query simple para totales por lista de categorías.
        """
        self.reset()

        self.select(
            "cat.code AS category_code",
            "COALESCE(cat.name->>'es_CO', cat.name->>'en_US') AS category_name",
            "SUM(ABS(hpl.total)) AS total",
            "COUNT(DISTINCT hp.id) AS payslip_count",
            "COUNT(DISTINCT hp.employee_id) AS employee_count",
        )

        self.from_table('hr_payslip_line', 'hpl')
        self.join('hr_payslip', 'hp', 'hp.id = hpl.slip_id')
        self.join('hr_salary_rule', 'rule', 'rule.id = hpl.salary_rule_id')
        self.join('hr_salary_rule_category', 'cat', 'cat.id = hpl.category_id')

        self.where("hp.state IN %(states)s", states=('done', 'paid'))
        self.where("hp.date_from >= %(date_from)s", date_from=self._date_from)
        self.where("hp.date_to <= %(date_to)s", date_to=self._date_to)
        self.where("cat.code IN %(category_codes)s", category_codes=category_codes)
        self.where("rule.appears_on_payslip = TRUE")

        if self._company_id:
            self.where("hp.company_id = %(company_id)s", company_id=self._company_id)

        if self._department_id:
            self.join('hr_employee', 'emp', 'emp.id = hp.employee_id')
            self.where("emp.department_id = %(department_id)s", department_id=self._department_id)

        if self._batch_id:
            self.where("hp.payslip_run_id = %(batch_id)s", batch_id=self._batch_id)

        self.group_by("cat.code", "COALESCE(cat.name->>'es_CO', cat.name->>'en_US')")
        self.order_by("total DESC")

        return self.build()
