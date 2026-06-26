# -*- coding: utf-8 -*-
"""
Códigos de Reglas para Dashboard
=================================
Centraliza todos los códigos de reglas salariales usados en el dashboard.
Importa desde rule_generators para mantener consistencia.
"""

from .rule_generators import (
    BasicRulesGenerator,
    SocialSecurityRulesGenerator,
    DeductionRulesGenerator,
    AuxilioRulesGenerator,
    OvertimeRulesGenerator,
)

# =============================================================================
# CÓDIGOS DE SEGURIDAD SOCIAL
# =============================================================================

# Extraer códigos de SocialSecurityRulesGenerator
_ss_rules = {r['code']: r for r in SocialSecurityRulesGenerator.get_rules()}

SALUD_CODE = 'SSOCIAL001'
PENSION_CODE = 'SSOCIAL002'
FONDO_SUBSISTENCIA_CODE = 'SSOCIAL003'
FONDO_SOLIDARIDAD_CODE = 'SSOCIAL004'

SOCIAL_SECURITY_CODES = [SALUD_CODE, PENSION_CODE, FONDO_SUBSISTENCIA_CODE, FONDO_SOLIDARIDAD_CODE]
FONDOS_CODES = [FONDO_SUBSISTENCIA_CODE, FONDO_SOLIDARIDAD_CODE]

# =============================================================================
# CÓDIGOS DE RETENCIÓN EN LA FUENTE
# =============================================================================

RETENCION_NOMINA_CODE = 'RT_MET_01'
RETENCION_PRIMA_CODE = 'RET_PRIMA'
RETENCION_INDEM_CODE = 'RTF_INDEM'
RETENCION_FUENTE_CODE = 'RETFTE001'
RETENCION_PRIMA_ALT_CODE = 'RETFTE_PRIMA001'

RETENTION_CODES = [
    RETENCION_NOMINA_CODE,
    RETENCION_PRIMA_CODE,
    RETENCION_INDEM_CODE,
    RETENCION_FUENTE_CODE,
    RETENCION_PRIMA_ALT_CODE,
]

# =============================================================================
# CÓDIGOS DE SALARIO BÁSICO
# =============================================================================

_basic_rules = {r['code']: r for r in BasicRulesGenerator.get_rules()}

BASIC_CODE = 'BASIC'
BASIC_INTEGRAL_CODE = 'BASIC002'
BASIC_SOSTENIMIENTO_CODE = 'BASIC003'
BASIC_PARCIAL_CODE = 'BASIC004'
BASIC_DIA_CODE = 'BASIC005'

BASIC_CODES = [BASIC_CODE, BASIC_INTEGRAL_CODE, BASIC_SOSTENIMIENTO_CODE]
ALL_BASIC_CODES = list(_basic_rules.keys())

# =============================================================================
# CÓDIGOS DE AUXILIO
# =============================================================================

AUXILIO_TRANSPORTE_CODE = 'AUX000'
AUXILIO_CONECTIVIDAD_CODE = 'AUX00C'

AUXILIO_CODES = [AUXILIO_TRANSPORTE_CODE, AUXILIO_CONECTIVIDAD_CODE]

# =============================================================================
# CÓDIGOS DE PRÉSTAMOS Y EMBARGOS
# =============================================================================

PRESTAMO_CODE = 'P01'
PRESTAMO_NOVEDAD_CODE = 'PRESTAMO'
LIBRANZA_CODE = 'LIBRANZA'

PRESTAMO_CODES = [PRESTAMO_CODE, PRESTAMO_NOVEDAD_CODE]
PRESTAMO_KEYWORDS = ['PRESTAMO', 'LOAN']

EMBARGO_CODES = [
    'EMBARGO001', 'EMBARGO002', 'EMBARGO003', 'EMBARGO004',
    'EMBARGO005', 'EMBARGO007', 'EMBARGO009'
]

# =============================================================================
# CÓDIGOS DE OTRAS DEDUCCIONES
# =============================================================================

MEDPRE_CODE = 'MEDPRE'
ERROR_CODE = 'ERROR'
HORAS_CODE = 'HORAS'
ANTICIPO_CODE = 'ANTICIPO'
AVP_CODE = 'AVP'
DESCUENTO_CODE = 'DESCUENTO'
AFC_CODE = 'AFC'

OTHER_DEDUCTION_CODES = [
    MEDPRE_CODE, ERROR_CODE, HORAS_CODE, ANTICIPO_CODE,
    AVP_CODE, DESCUENTO_CODE, AFC_CODE
]

# =============================================================================
# CÓDIGOS DE CATEGORÍAS
# =============================================================================

CATEGORY_DEVENGADO = 'DEV_SALARIAL'
CATEGORY_RETENCION = 'RTEFTE'
CATEGORY_DEDUCCION = 'DEDUCCIONES'
CATEGORY_BASIC = 'BASIC'
CATEGORY_AUXILIO = 'AUX'
CATEGORY_SSOCIAL = 'SSOCIAL'
CATEGORY_EMBARGO = 'EM'

TOTAL_CATEGORIES = ['TOTALDEV', 'TOTALDED', 'NETO']

EARNINGS_CATEGORIES = [
    'BASIC', 'AUX', 'AUS', 'ALW', 'ACCIDENTE_TRABAJO',
    'DEV_NO_SALARIAL', 'DEV_SALARIAL', 'TOTALDEV', 'HEYREC',
    'COMISIONES', 'INCAPACIDAD', 'LICENCIA_MATERNIDAD',
    'LICENCIA_NO_REMUNERADA', 'LICENCIA_REMUNERADA',
    'PRESTACIONES_SOCIALES', 'PRIMA', 'VACACIONES'
]

DEDUCTION_CATEGORIES = [
    'DED', 'DEDUCCIONES', 'TOTALDED', 'SANCIONES', 'DESCUENTO_AFC', 'EM'
]

# =============================================================================
# PATRONES PARA BÚSQUEDA
# =============================================================================

OVERTIME_PATTERNS = ['EXTRA', 'HE']
DEDUCTION_PATTERNS = ['DED', 'DEDU']

# =============================================================================
# CONFIGURACIÓN DE DASHBOARD POR CONCEPTO
# =============================================================================

DASHBOARD_CONCEPTS = {
    'salud': {
        'rules': [SALUD_CODE],
        'name': 'Salud',
        'icon': 'fa-medkit',
        'color': 'info'
    },
    'pension': {
        'rules': [PENSION_CODE],
        'name': 'Pensión',
        'icon': 'fa-university',
        'color': 'primary'
    },
    'fondos': {
        'rules': FONDOS_CODES,
        'name': 'Fondos Solidaridad',
        'icon': 'fa-hands-helping',
        'color': 'secondary'
    },
    'retencion': {
        'rules': RETENTION_CODES[:3],  # RT_MET_01, RET_PRIMA, RTF_INDEM
        'name': 'Retención Fuente',
        'icon': 'fa-file-invoice-dollar',
        'color': 'warning'
    },
    'sueldo': {
        'categories': [CATEGORY_BASIC],
        'rules': BASIC_CODES,
        'name': 'Sueldo Básico',
        'icon': 'fa-money-bill',
        'color': 'success'
    },
    'auxilio': {
        'categories': [CATEGORY_AUXILIO],
        'rules': AUXILIO_CODES,
        'name': 'Auxilio Transporte',
        'icon': 'fa-bus',
        'color': 'info'
    },
    'prestamos': {
        'rules': PRESTAMO_CODES,
        'keywords': PRESTAMO_KEYWORDS,
        'name': 'Préstamos',
        'icon': 'fa-hand-holding-usd',
        'color': 'danger'
    },
    'embargos': {
        'rules': EMBARGO_CODES,
        'categories': [CATEGORY_EMBARGO],
        'name': 'Embargos',
        'icon': 'fa-gavel',
        'color': 'dark'
    },
    'deducciones': {
        'categories': DEDUCTION_CATEGORIES,
        'rules': OTHER_DEDUCTION_CODES + EMBARGO_CODES[:3],
        'name': 'Otras Deducciones',
        'icon': 'fa-minus-circle',
        'color': 'secondary'
    },
}

# =============================================================================
# FUNCIONES HELPER
# =============================================================================

def is_retention_code(code):
    """Verifica si un código es de retención en la fuente."""
    return code in RETENTION_CODES


def is_social_security_code(code):
    """Verifica si un código es de seguridad social."""
    return code in SOCIAL_SECURITY_CODES


def is_basic_code(code):
    """Verifica si un código es de salario básico."""
    return code in ALL_BASIC_CODES


def is_auxilio_code(code):
    """Verifica si un código es de auxilio."""
    return code in AUXILIO_CODES


def is_prestamo_code(code):
    """Verifica si un código es de préstamo."""
    if code in PRESTAMO_CODES:
        return True
    return any(keyword in code.upper() for keyword in PRESTAMO_KEYWORDS)


def is_overtime_code(code):
    """Verifica si un código es de horas extras."""
    code_upper = (code or '').upper()
    return any(pattern in code_upper for pattern in OVERTIME_PATTERNS)


def get_concept_config(concept_key):
    """Obtiene la configuración de un concepto del dashboard."""
    return DASHBOARD_CONCEPTS.get(concept_key, {})


def get_line_concept(line):
    """
    Determina el concepto de una línea de nómina.

    Args:
        line: hr.payslip.line record

    Returns:
        str: Clave del concepto ('salud', 'pension', 'sueldo', etc.) o None
    """
    code = (line.code or '').upper()
    rule_code = (line.salary_rule_id.code if line.salary_rule_id else '').upper()
    category_code = (line.category_id.code if line.category_id else '').upper()

    # Salud
    if code == SALUD_CODE or rule_code == SALUD_CODE:
        return 'salud'

    # Pensión
    if code == PENSION_CODE or rule_code == PENSION_CODE:
        return 'pension'

    # Fondos
    if code in FONDOS_CODES or rule_code in FONDOS_CODES:
        return 'fondos'

    # Retención
    if code in RETENTION_CODES[:3] or rule_code in RETENTION_CODES[:3]:
        return 'retencion'

    # Préstamos
    if is_prestamo_code(code) or is_prestamo_code(category_code):
        return 'prestamos'

    # Auxilio
    if code in AUXILIO_CODES or rule_code in AUXILIO_CODES:
        return 'auxilio'

    # Sueldo básico
    if code in BASIC_CODES or rule_code in BASIC_CODES:
        return 'sueldo'

    # Deducciones genéricas
    if any(pattern in category_code for pattern in DEDUCTION_PATTERNS) and line.total < 0:
        return 'deducciones'

    return None
