# -*- coding: utf-8 -*-
"""
Service SQL - Sistema unificado de consultas SQL para nomina colombiana
=======================================================================

Estructura de archivos:
- field_sets.py: Conjuntos de campos por tabla (minimal, standard, full)
- base_query_builder.py: Builder base con soporte CTE, ARRAY_AGG, UNION
- result_types.py: Dataclasses tipadas para resultados

Consultas por tipo (un archivo por tipo):
- payslip_line_queries.py: Consultas de lineas de nomina (hr_payslip_line)
- leave_line_queries.py: Consultas de lineas de ausencia (hr_leave_line)
- worked_days_queries.py: Consultas de dias trabajados (hr_payslip_day)
- overtime_queries.py: Consultas de horas extras (hr_overtime)
- novelties_queries.py: Consultas de novedades (hr_novelties_different_concepts)
- period_queries.py: Builder base para consultas de periodo
- ibd_queries.py: Consultas de IBD (seguridad social)
- retenciones_queries.py: Consultas de retencion en la fuente
- prestaciones_queries.py: Consultas de prestaciones sociales
- auxilio_transporte_queries.py: Consultas de auxilio de transporte
- leave_period_queries.py: Consultas de ausencias por periodo

Uso:
    from odoo.addons.lavish_hr_employee.models.services.service_sql import (
        PayslipLineQueryBuilder,
        LeaveLineQueryBuilder,
        IBDQueryBuilder,
        RetencionesQueryBuilder,
        PrestacionesQueryBuilder,
        AuxilioTransporteQueryBuilder,
        LeavePeriodQueryBuilder,
    )
"""
# Constantes y tipos
from .field_sets import (
    PAYSLIP_LINE_FIELDS,
    LEAVE_LINE_FIELDS,
    PAYSLIP_FIELDS,
    RULE_FIELDS,
    CATEGORY_FIELDS,
    VALID_PAYSLIP_STATES,
    VALID_LEAVE_STATES,
)
from .result_types import (
    PayslipLineResult,
    LeaveLineResult,
    AccumulatedResult,
    CategoryAccumulatedResult,
)

# Builder base
from .base_query_builder import SQLQueryBuilder

# Consultas de entidades
from .payslip_line_queries import PayslipLineQueryBuilder
from .leave_line_queries import LeaveLineQueryBuilder
from .worked_days_queries import WorkedDaysQueryBuilder
from .overtime_queries import OvertimeQueryBuilder
from .novelties_queries import NoveltiesQueryBuilder

# Consultas de periodo (clase base)
from .period_queries import PeriodQueryBuilder

# Consultas especializadas por tipo (un archivo por tipo)
from .ibd_queries import IBDQueryBuilder
from .retenciones_queries import RetencionesQueryBuilder
from .prestaciones_queries import PrestacionesQueryBuilder
from .auxilio_transporte_queries import AuxilioTransporteQueryBuilder
from .leave_period_queries import LeavePeriodQueryBuilder

# Consultas de dashboard
from .dashboard_queries import (
    DashboardKPIsQueryBuilder,
    DashboardOvertimeQueryBuilder,
    DashboardAbsencesQueryBuilder,
    DashboardTrendQueryBuilder,
    DashboardEmployeesQueryBuilder,
    DashboardPendingLeavesQueryBuilder,
    DashboardPayrollSummaryQueryBuilder,
    # Nuevos builders para gráficos
    DashboardAccidentsChartQueryBuilder,
    DashboardIncomeDeductionsQueryBuilder,
    DashboardDisabilityQueryBuilder,
    DashboardPayrollSummaryDetailQueryBuilder,
)
