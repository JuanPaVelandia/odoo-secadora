# -*- coding: utf-8 -*-
"""
Conjuntos de campos por tabla
=============================

Define los campos minimos, estandar y completos para cada tabla.
Esto evita consultar campos innecesarios y mejora el rendimiento.

Uso:
    fields = PAYSLIP_LINE_FIELDS['minimal']
    # ['id', 'total', 'category_id', 'salary_rule_id']
"""
from typing import Dict, List

# =============================================================================
# HR_PAYSLIP_LINE - Lineas de nomina
# =============================================================================
PAYSLIP_LINE_FIELDS: Dict[str, List[str]] = {
    # Campos minimos para calculos basicos
    'minimal': [
        'id',
        'total',
        'category_id',
        'salary_rule_id',
    ],
    # Campos estandar para reportes
    'standard': [
        'id',
        'slip_id',
        'total',
        'amount',
        'quantity',
        'rate',
        'category_id',
        'salary_rule_id',
    ],
    # Campos completos incluyendo fechas y relaciones
    'full': [
        'id',
        'slip_id',
        'total',
        'amount',
        'quantity',
        'rate',
        'category_id',
        'salary_rule_id',
        'date_from',
        'date_to',
        'leave_id',
        'computation',
    ],
    # Campos para acumulacion (GROUP BY)
    'accumulation': [
        'category_id',
        'salary_rule_id',
        'SUM(total) AS total_amount',
        'SUM(amount) AS sum_amount',
        'SUM(quantity) AS sum_quantity',
        'AVG(rate) AS avg_rate',
        'ARRAY_AGG(id) AS line_ids',
    ],
}

# =============================================================================
# HR_LEAVE_LINE - Lineas de ausencia
# =============================================================================
LEAVE_LINE_FIELDS: Dict[str, List[str]] = {
    'minimal': [
        'id',
        'leave_id',
        'date',
    ],
    'standard': [
        'id',
        'leave_id',
        'date',
        'amount',
        'state',
        'days_payslip',
    ],
    'full': [
        'id',
        'leave_id',
        'date',
        'amount',
        'state',
        'days_payslip',
        'payslip_id',
        'sequence',
    ],
    'accumulation': [
        'COUNT(id) AS days_count',
        'SUM(COALESCE(amount, 0)) AS total_amount',
        'ARRAY_AGG(id) AS line_ids',
    ],
}

# =============================================================================
# HR_PAYSLIP - Nominas
# =============================================================================
PAYSLIP_FIELDS: Dict[str, List[str]] = {
    'minimal': [
        'id',
        'contract_id',
        'state',
    ],
    'standard': [
        'id',
        'contract_id',
        'employee_id',
        'state',
        'date_from',
        'date_to',
        'number',
    ],
    'full': [
        'id',
        'contract_id',
        'employee_id',
        'company_id',
        'state',
        'date_from',
        'date_to',
        'number',
        'struct_id',
        'move_type',
    ],
}

# =============================================================================
# HR_SALARY_RULE - Reglas salariales
# =============================================================================
RULE_FIELDS: Dict[str, List[str]] = {
    'minimal': [
        'id',
        'code',
    ],
    'standard': [
        'id',
        'code',
        'name',
        'category_id',
    ],
    'full': [
        'id',
        'code',
        'name',
        'category_id',
        'sequence',
        'struct_id',
    ],
}

# =============================================================================
# HR_SALARY_RULE_CATEGORY - Categorias
# =============================================================================
CATEGORY_FIELDS: Dict[str, List[str]] = {
    'minimal': [
        'id',
        'code',
    ],
    'standard': [
        'id',
        'code',
        'name',
        'parent_id',
    ],
    'full': [
        'id',
        'code',
        'name',
        'parent_id',
        'category_type',
    ],
}

# =============================================================================
# HR_LEAVE - Ausencias
# =============================================================================
LEAVE_FIELDS: Dict[str, List[str]] = {
    'minimal': [
        'id',
        'contract_id',
        'holiday_status_id',
    ],
    'standard': [
        'id',
        'contract_id',
        'employee_id',
        'holiday_status_id',
        'state',
        'date_from',
        'date_to',
    ],
    'full': [
        'id',
        'contract_id',
        'employee_id',
        'holiday_status_id',
        'state',
        'date_from',
        'date_to',
        'number_of_days',
        'request_date_from',
        'request_date_to',
    ],
}

# =============================================================================
# HR_LEAVE_TYPE - Tipos de ausencia
# =============================================================================
LEAVE_TYPE_FIELDS: Dict[str, List[str]] = {
    'minimal': [
        'id',
        'code',
    ],
    'standard': [
        'id',
        'code',
        'name',
        'novelty',
    ],
    'full': [
        'id',
        'code',
        'name',
        'novelty',
        'liquidacion_value',
        'unpaid_absences',
        'discounting_bonus_days',
    ],
}

# =============================================================================
# ALIAS ESTANDAR PARA JOINS
# =============================================================================
TABLE_ALIASES = {
    'hr_payslip': 'HP',
    'hr_payslip_line': 'HPL',
    'hr_salary_rule': 'HSR',
    'hr_salary_rule_category': 'HSRC',
    'hr_leave': 'HL',
    'hr_leave_line': 'HLL',
    'hr_leave_type': 'HLT',
    'hr_overtime': 'HO',
    'hr_contract': 'HC',
    'hr_employee': 'HE',
}

# =============================================================================
# ESTADOS VALIDOS
# =============================================================================
VALID_PAYSLIP_STATES = ('done', 'paid')
VALID_LEAVE_STATES = ('validate', 'validated', 'paid')
VALID_LEAVE_LINE_STATES = ('validate', 'validated', 'paid')

# =============================================================================
# CAMPOS JSONB TRADUCIBLES (Odoo 17+)
# =============================================================================
# En Odoo 17, los campos traducibles se almacenan como JSONB:
# {"es_CO": "Departamento", "en_US": "Department"}
#
# Para extraer el valor en SQL, usar: field->>'es_CO'

# Mapeo de tabla -> campos que son JSONB traducibles
TRANSLATABLE_FIELDS = {
    'hr_department': ['name'],
    'hr_job': ['name'],
    'hr_leave_type': ['name'],
    'hr_salary_rule': ['name'],
    'hr_salary_rule_category': ['name'],
    'res_city': ['name'],
    'res_country_state': ['name'],
    'res_country': ['name'],
    'account_journal': ['name'],
    'product_product': ['name'],
    'product_template': ['name'],
    'uom_uom': ['name'],
}

# Idioma por defecto y fallback
DEFAULT_LANG = 'es_CO'
FALLBACK_LANG = 'en_US'


def translatable_sql(
    table_alias: str,
    field_name: str = 'name',
    alias: str = None,
    default: str = None,
    lang: str = DEFAULT_LANG,
    fallback_lang: str = FALLBACK_LANG
) -> str:
    """
    Genera SQL para extraer texto de un campo JSONB traducible.

    Args:
        table_alias: Alias de la tabla (ej: 'dep', 'hlt')
        field_name: Nombre del campo (default: 'name')
        alias: Alias para el resultado (ej: 'department_name')
        default: Valor por defecto si es NULL
        lang: Idioma principal (default: es_CO)
        fallback_lang: Idioma de respaldo (default: en_US)

    Returns:
        SQL string para el campo

    Ejemplos:
        >>> translatable_sql('dep', alias='department_name', default='Sin Departamento')
        "COALESCE(dep.name->>'es_CO', dep.name->>'en_US', 'Sin Departamento') AS department_name"

        >>> translatable_sql('hlt', alias='type_name')
        "COALESCE(hlt.name->>'es_CO', hlt.name->>'en_US') AS type_name"

        >>> translatable_sql('rule', 'name')
        "COALESCE(rule.name->>'es_CO', rule.name->>'en_US')"
    """
    field_ref = f"{table_alias}.{field_name}"

    if default:
        expr = f"COALESCE({field_ref}->>'{lang}', {field_ref}->>'{fallback_lang}', '{default}')"
    else:
        expr = f"COALESCE({field_ref}->>'{lang}', {field_ref}->>'{fallback_lang}')"

    if alias:
        return f"{expr} AS {alias}"
    return expr


def translatable_coalesce_sql(
    *field_refs,
    alias: str = None,
    default: str = None,
    lang: str = DEFAULT_LANG,
    fallback_lang: str = FALLBACK_LANG
) -> str:
    """
    Genera SQL para COALESCE de múltiples campos JSONB traducibles.

    Args:
        *field_refs: Tuplas de (table_alias, field_name) o strings 'alias.field'
        alias: Alias para el resultado
        default: Valor por defecto
        lang: Idioma principal
        fallback_lang: Idioma de respaldo

    Ejemplos:
        >>> translatable_coalesce_sql(('cat_parent', 'name'), ('cat', 'name'), alias='category_name')
        "COALESCE(cat_parent.name->>'es_CO', cat_parent.name->>'en_US', cat.name->>'es_CO', cat.name->>'en_US') AS category_name"

        >>> translatable_coalesce_sql('dep.name', 'job.name', alias='location')
        "COALESCE(dep.name->>'es_CO', dep.name->>'en_US', job.name->>'es_CO', job.name->>'en_US') AS location"
    """
    parts = []
    for ref in field_refs:
        if isinstance(ref, tuple):
            table_alias, field_name = ref
            field_ref = f"{table_alias}.{field_name}"
        else:
            field_ref = ref
        parts.append(f"{field_ref}->>'{lang}'")
        parts.append(f"{field_ref}->>'{fallback_lang}'")

    if default:
        parts.append(f"'{default}'")

    expr = f"COALESCE({', '.join(parts)})"

    if alias:
        return f"{expr} AS {alias}"
    return expr


# =============================================================================
# SHORTCUTS PARA CAMPOS COMUNES
# =============================================================================
def dept_name_sql(alias: str = 'dep', result_alias: str = 'department_name') -> str:
    """SQL para nombre de departamento."""
    return translatable_sql(alias, 'name', result_alias, 'Sin Departamento')


def job_name_sql(alias: str = 'job', result_alias: str = 'job_name') -> str:
    """SQL para nombre de puesto."""
    return translatable_sql(alias, 'name', result_alias)


def leave_type_name_sql(alias: str = 'hlt', result_alias: str = 'leave_type_name') -> str:
    """SQL para nombre de tipo de ausencia."""
    return translatable_sql(alias, 'name', result_alias)


def rule_name_sql(alias: str = 'rule', result_alias: str = 'rule_name') -> str:
    """SQL para nombre de regla salarial."""
    return translatable_sql(alias, 'name', result_alias)


def category_name_sql(alias: str = 'cat', result_alias: str = 'category_name') -> str:
    """SQL para nombre de categoría."""
    return translatable_sql(alias, 'name', result_alias)


def parent_category_name_sql(
    parent_alias: str = 'cat_parent',
    child_alias: str = 'cat',
    result_alias: str = 'category_name'
) -> str:
    """SQL para nombre de categoría con fallback a categoría padre."""
    return translatable_coalesce_sql(
        (parent_alias, 'name'), (child_alias, 'name'),
        alias=result_alias
    )
