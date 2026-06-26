# -*- coding: utf-8 -*-
"""
Servicios de Nómina
===================

Estructura:
- period_payslip_query_service: Servicio de consultas consolidadas (Odoo model)
- period_novelties_service: Servicio de consulta de novedades del período (Python class)
- old/: Servicios legacy con lógica de cálculo (pendientes de refactorizar)
"""

# Servicios activos: Consultas de novedades del período
from . import period_payslip_query_service
from .period_novelties_service import PeriodNoveltiesService
from .worked_days_calculation_service import WorkedDaysCalculationService
from .leave_calculation_service import LeaveCalculationService
from .period_calculation_service import PeriodCalculationService
from .payslip_html_report_service import PayslipHtmlReportService
from .payslip_history_service import PayslipHistoryService
from .payslip_line_calculation_service import PayslipLineCalculationService

