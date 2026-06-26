# -*- coding: utf-8 -*-
"""
Índice de Generadores de Reglas
================================
Exporta todos los generadores de reglas organizados por categoría.
"""

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

# Mapa de generadores por categoría para fácil acceso
GENERATORS_MAP = {
    'basic': BasicRulesGenerator,
    'incapacity': IncapacityRulesGenerator,
    'license': LicenseRulesGenerator,
    'vacation': VacationRulesGenerator,
    'devengo': DevengoRulesGenerator,
    'overtime': OvertimeRulesGenerator,
    'auxilio': AuxilioRulesGenerator,
    'prestaciones': PrestacionesRulesGenerator,
    'social_security': SocialSecurityRulesGenerator,
    'deduction': DeductionRulesGenerator,
    'provision': ProvisionRulesGenerator,
    'consolidacion': ConsolidacionRulesGenerator,
    'totalizer': TotalizerRulesGenerator,
}

# Lista de todos los generadores en orden de ejecución
ALL_GENERATORS = [
    BasicRulesGenerator,
    IncapacityRulesGenerator,
    LicenseRulesGenerator,
    VacationRulesGenerator,
    DevengoRulesGenerator,
    OvertimeRulesGenerator,
    AuxilioRulesGenerator,
    PrestacionesRulesGenerator,
    SocialSecurityRulesGenerator,
    DeductionRulesGenerator,
    ProvisionRulesGenerator,
    ConsolidacionRulesGenerator,
    TotalizerRulesGenerator,
]

__all__ = [
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
    'GENERATORS_MAP',
    'ALL_GENERATORS',
]
