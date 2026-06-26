# -*- coding: utf-8 -*-
"""
Utilidades para cálculos de nómina colombiana.
Re-exporta constantes de hr_payslip_constants y añade clases auxiliares.
"""

from datetime import date

# ===============================================================================
# RE-EXPORTAR CONSTANTES Y FUNCIONES DE hr_payslip_constants
# ===============================================================================

from .hr_payslip_constants import (
    # Constantes numéricas
    DAYS_YEAR,
    DAYS_YEAR_NATURAL,
    DAYS_MONTH,
    PRECISION_TECHNICAL,
    PRECISION_DISPLAY,
    DATETIME_MIN,
    DATETIME_MAX,
    HOURS_PER_DAY,
    UTC,
    # Códigos especiales
    TPCT,
    TPCP,
    NCI,
    # Tablas y mapeos
    TABLA_RETENCION,
    TOPES_DEDUCCIONES_RTF,
    CATEGORY_MAPPINGS,
    VALID_NOVELTY_TYPES,
    NOVELTY_TYPE_SELECTION,
    LIQUIDATION_VALUE_SELECTION,
    NOVELTY_TYPES_CONFIG,
    # Selecciones
    TYPE_PERIOD,
    TYPE_BIWEEKLY,
    MOVE_TYPE_SELECTION,
    COMPUTATION_STATUS_SELECTION,
    RIBBON_COLOR_SELECTION,
    # Funciones
    get_novelty_config,
    days360,
    round_1_decimal,
    json_serial,
    MONTH_NAMES,
    get_month_name,
    calc_check_digits,
    # Clases
    PayslipLineAccumulator,
)


# ===============================================================================
# CLASE PARA GESTIÓN DE PERÍODOS ANTERIORES
# ===============================================================================

class PeriodoAnterior:
    """
    Stub de PeriodoAnterior para cuando lavish_hr_payroll no está instalado.
    Proporciona una interfaz compatible pero retorna valores vacíos.
    """

    def __init__(self, payslip):
        self.payslip = payslip
        self._cache = {}
        try:
            from .hr_slip_data_structures import CategoryCollection
            self._CategoryCollection = CategoryCollection
        except ImportError:
            self._CategoryCollection = dict

    def _has_accumulation_methods(self):
        return hasattr(self.payslip, '_get_categories_accumulated')

    def cargar_periodo(self, start_date, end_date):
        if self._has_accumulation_methods():
            cache_key = f"period_{start_date}_{end_date}"
            if cache_key in self._cache:
                return self._cache[cache_key]
            contract_id = self.payslip.contract_id.id if self.payslip.contract_id else None
            result = self.payslip._get_categories_accumulated(
                start_date, end_date,
                [contract_id] if contract_id else None
            )
            if isinstance(result, dict) and contract_id in result:
                collection = result[contract_id]
            else:
                collection = self._CategoryCollection()
            self._cache[cache_key] = collection
            return collection
        return self._CategoryCollection()

    def obtener_categoria(self, category_code, start_date, end_date):
        categories = self.cargar_periodo(start_date, end_date)
        if hasattr(categories, 'get'):
            return categories.get(category_code)
        return None

    def obtener_total_categoria(self, category_codes, start_date, end_date):
        categories = self.cargar_periodo(start_date, end_date)
        if hasattr(categories, 'get_total'):
            codes_list = category_codes if isinstance(category_codes, list) else [category_codes]
            return categories.get_total(category_codes=codes_list)
        return 0.0

    def obtener_ausencias_por_tipo(self, novelty, start_date, end_date):
        return []

    def obtener_totales_ausencias(self, start_date, end_date):
        return {}

    def obtener_horas_extras(self, start_date, end_date, fecha_fin=None):
        if self._has_accumulation_methods() and hasattr(self.payslip, '_get_overtime_accumulated'):
            cache_key = f"overtime_{start_date}_{end_date}_{fecha_fin}"
            if cache_key in self._cache:
                return self._cache[cache_key]
            contract_id = self.payslip.contract_id.id if self.payslip.contract_id else None
            employee_id = self.payslip.employee_id.id if self.payslip.employee_id else None
            result = self.payslip._get_overtime_accumulated(
                start_date, end_date,
                fecha_fin=fecha_fin,
                contract_id=contract_id,
                employee_id=employee_id
            )
            self._cache[cache_key] = result
            return result
        return {'by_period': [], 'total_hours': 0, 'overtime_ids': [], 'totals': {}}

    def filtrar_reglas(self, start_date, end_date, **filters):
        return []

    def obtener_reglas_por_categoria(self, category_code, start_date, end_date, **filters):
        category = self.obtener_categoria(category_code, start_date, end_date)
        if not category:
            return []
        if hasattr(category, 'filter_rules') and filters:
            return category.filter_rules(**filters)
        elif hasattr(category, 'rules'):
            return category.rules
        return []

    def limpiar_cache(self):
        self._cache.clear()


# ===============================================================================
# CARGADOR DE PARÁMETROS ANUALES
# ===============================================================================

_PARAM_CACHE = {}


class ParamLoader:
    """Cargador de parámetros anuales con cache simple."""

    @staticmethod
    def _read_params(env, company_id: int, year: int) -> dict:
        global _PARAM_CACHE
        cache_key = (company_id, year)
        if cache_key in _PARAM_CACHE:
            return _PARAM_CACHE[cache_key]
        rec = env['hr.annual.parameters'].get_for_year(
            year, company_id=company_id, raise_if_not_found=True
        )
        params = {
            'SMMLV': rec.smmlv_monthly,
            'SMMLV_DAILY': rec.smmlv_daily,
            'TOPE_25_SMMLV': rec.top_twenty_five_smmlv,
            'TOPE_40': rec.value_porc_statute_1395 / 100,
            'INT_FACTOR': rec.porc_integral_salary / 100,
        }
        _PARAM_CACHE[cache_key] = params
        return params

    @classmethod
    def for_date(cls, env, d: date) -> dict:
        return cls._read_params(env, env.company.id, d.year)

    @classmethod
    def clear_cache(cls, env=None):
        global _PARAM_CACHE
        _PARAM_CACHE.clear()

    @classmethod
    def obtener_parametro_vigente(cls, env, fecha: date, clave: str) -> float:
        """Obtiene valor vigente de un parámetro según fecha (Ley 2466/2025)."""
        PARAMETROS_VIGENCIA = [
            (date(2025, 7, 1), date(2026, 6, 30), 'RECARGO_DOMINICAL', 0.80),
            (date(2026, 7, 1), date(2027, 6, 30), 'RECARGO_DOMINICAL', 0.90),
            (date(2027, 7, 1), None, 'RECARGO_DOMINICAL', 1.00),
            (date(2025, 12, 25), None, 'RECARGO_NOCTURNO', 0.35),
            (date(2025, 1, 1), date(2025, 12, 31), 'JORNADA_SEMANAL', 44.0),
            (date(2026, 1, 1), None, 'JORNADA_SEMANAL', 42.0),
            (date(2025, 1, 1), None, 'CONTRATO_FIJO_MAX_ANIOS', 4),
        ]
        for fecha_inicio, fecha_fin, param_clave, valor in PARAMETROS_VIGENCIA:
            if param_clave == clave and fecha >= fecha_inicio:
                if fecha_fin is None or fecha <= fecha_fin:
                    return valor
        defaults = {
            'RECARGO_DOMINICAL': 0.75,
            'RECARGO_NOCTURNO': 0.35,
            'JORNADA_SEMANAL': 48.0,
            'CONTRATO_FIJO_MAX_ANIOS': 3,
        }
        return defaults.get(clave, 0.0)
