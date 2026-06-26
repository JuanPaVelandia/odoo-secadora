# -*- coding: utf-8 -*-
"""
Generadores de Reglas Salariales
=================================
Módulos helper organizados por categoría para generar reglas salariales.
"""

from . import basic_rules
from . import incapacity_rules
from . import license_rules
from . import vacation_rules
from . import devengo_rules
from . import overtime_rules
from . import auxilio_rules
from . import prestaciones_rules
from . import social_security_rules
from . import deduction_rules
from . import provision_rules
from . import consolidacion_rules
from . import totalizer_rules

# Exportar clases generadoras directamente (ANTES de index)
from .basic_rules import BasicRulesGenerator
from .incapacity_rules import IncapacityRulesGenerator
from .license_rules import LicenseRulesGenerator
from .vacation_rules import VacationRulesGenerator
from .devengo_rules import DevengoRulesGenerator
from .overtime_rules import OvertimeRulesGenerator
from .auxilio_rules import AuxilioRulesGenerator
from .prestaciones_rules import PrestacionesRulesGenerator
from .social_security_rules import SocialSecurityRulesGenerator
from .deduction_rules import DeductionRulesGenerator
from .provision_rules import ProvisionRulesGenerator
from .consolidacion_rules import ConsolidacionRulesGenerator
from .totalizer_rules import TotalizerRulesGenerator

# Importar index DESPUES de las clases (evita circular import)
from .index import ALL_GENERATORS, GENERATORS_MAP

__all__ = [
    'basic_rules',
    'incapacity_rules',
    'license_rules',
    'vacation_rules',
    'devengo_rules',
    'overtime_rules',
    'auxilio_rules',
    'prestaciones_rules',
    'social_security_rules',
    'deduction_rules',
    'provision_rules',
    'consolidacion_rules',
    'totalizer_rules',
    'ALL_GENERATORS',
    'GENERATORS_MAP',
    # Generator classes
    'BasicRulesGenerator',
    'IncapacityRulesGenerator',
    'LicenseRulesGenerator',
    'VacationRulesGenerator',
    'DevengoRulesGenerator',
    'OvertimeRulesGenerator',
    'AuxilioRulesGenerator',
    'PrestacionesRulesGenerator',
    'SocialSecurityRulesGenerator',
    'DeductionRulesGenerator',
    'ProvisionRulesGenerator',
    'ConsolidacionRulesGenerator',
    'TotalizerRulesGenerator',
]
