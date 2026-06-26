# -*- coding: utf-8 -*-
"""
Servicios de Nómina - Archivos legacy (pendientes de refactorizar)
"""

from . import ausencias
from . import prestamos
from . import novedades
from . import conceptos
from . import lineas
from . import horas_extras
from . import prestaciones
from . import worked_days
from . import setup
from . import accumulation

from .lavish_payroll_compute import (
    LavishPayrollCompute,
    compute_payslip,
    process_batch,
)

from .ausencias import AusenciaService
from .prestamos import PrestamoService
from .novedades import NovedadService
from .conceptos import ConceptoService
from .lineas import LineaService
from .horas_extras import HoraExtraService
from .prestaciones import PromedioService
from .worked_days import WorkedDaysService

# Servicios de acumulación
from .accumulation import (
    AusenciaAccumulationService,
    NominaAccumulationService,
    SueldoAccumulationService,
)

# Funciones de test
from .lavish_payroll import (
    test_compute_departamento,
    test_compute_single,
    test_recompute_ausencias,
    run_test,
)

# Servicio optimizado para reportes de nomina
from .payroll_report_query_service import PayrollReportQueryService
