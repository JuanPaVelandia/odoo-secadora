# -*- coding: utf-8 -*-
"""
Utilidades Python puras para cálculos de nómina.
Este archivo NO contiene modelos de Odoo, solo constantes y funciones auxiliares.
"""

from collections import defaultdict
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
import calendar
import pytz

# ===============================================================================
# CONSTANTES GLOBALES
# ===============================================================================

DAYS_YEAR = 360
DAYS_YEAR_NATURAL = 365
DAYS_MONTH = 30
PRECISION_TECHNICAL = 10
PRECISION_DISPLAY = 0
DATETIME_MIN = datetime.min.time()
DATETIME_MAX = datetime.max.time()
HOURS_PER_DAY = 8
UTC = pytz.UTC

# Códigos especiales
TPCT = 'total_previous_categories'
TPCP = 'total_previous_concepts'
NCI = 'non_constitutive_income'

# Tabla de retención en la fuente (en UVT)
# Formato: (desde, hasta, porcentaje, desde, impuesto_marginal)
TABLA_RETENCION = [
    (0, 95, 0, 0, 0),
    (95, 150, 19, 95, 0),
    (150, 360, 28, 150, 10),
    (360, 640, 33, 360, 69),
    (640, 945, 35, 640, 162),
    (945, 2300, 37, 945, 268),
    (2300, float('inf'), 39, 2300, 770)
]

# Mapeos de categorías para clasificación automática
CATEGORY_MAPPINGS = {
    'EARNINGS': [
        'BASIC', 'AUX', 'AUS', 'ALW', 'ACCIDENTE_TRABAJO',
        'DEV_NO_SALARIAL', 'DEV_SALARIAL', 'TOTALDEV', 'HEYREC',
        'COMISIONES', 'INCAPACIDAD', 'LICENCIA_MATERNIDAD',
        'LICENCIA_NO_REMUNERADA', 'LICENCIA_REMUNERADA',
        'PRESTACIONES_SOCIALES', 'PRIMA', 'VACACIONES'
    ],
    'DEDUCTIONS': [
        'DED', 'DEDUCCIONES', 'TOTALDED', 'SANCIONES',
        'DESCUENTO_AFC', 'SSOCIAL'
    ],
    'PROVISIONS': ['PROV'],
    'BASES': ['IBC', 'IBD', 'IBC_R'],
    'OUTCOME': ['NET']
}

# Tipos de novedad válidos para PILA
VALID_NOVELTY_TYPES = [
    'sln', 'ige', 'irl', 'lma', 'lpa', 'vco', 'vdi',
    'vre', 'lr', 'lnr', 'lt', 'p'
]

TYPE_PERIOD = [
    ('monthly', 'Mensual'),
    ('bi-monthly', 'Quincenal'),
    ('weekly', 'Semanal'),
    ('dualmonth', 'Cada 2 Meses'),
    ('quarterly', 'Cada Cuatro meses'),
    ('semi-annually', 'Cada 6 Meses'),
    ('annually', 'Anual'),
]

TYPE_BIWEEKLY = [
    ('first', 'Primera Quincena'),
    ('second', 'Segunda Quincena')
]

MOVE_TYPE_SELECTION = [
    ('payroll', 'Nomina'),
    ('prima', 'Prima'),
    ('cesantias', 'Cesantias'),
    ('vacaciones', 'Vacaciones'),
    ('liquidacion', 'Liquidacion Final'),
    ('otros', 'Otros'),
    ('r_payroll', 'Reversion de Nomina'),
    ('r_prima', 'Reversion Prima'),
    ('r_cesantias', 'Reversion Cesantias'),
    ('r_vacaciones', 'Reversion Vacaciones'),
    ('r_liquidacion', 'Reversion Liquidacion'),
    ('r_otros', 'Reversion Otros')
]

COMPUTATION_STATUS_SELECTION = [
    ('draft', 'Borrador'),
    ('computing', 'Calculando'),
    ('computed', 'Calculado'),
    ('error', 'Error'),
]

RIBBON_COLOR_SELECTION = [
    ('warning', 'Advertencia'),
    ('info', 'Información'),
    ('success', 'Éxito'),
    ('danger', 'Peligro')
]

# ===============================================================================
# FUNCIONES AUXILIARES GLOBALES
# ===============================================================================

def days360(start_date, end_date, method_eu=False):
    """
    Calcula el numero de dias entre dos fechas considerando todos los meses como de 30 dias.
    Metodo comercial colombiano (360 dias/año, 30 dias/mes).
    Febrero tambien se trata como 30 dias (28 o 29 de febrero = dia 30).

    Args:
        start_date: Fecha de inicio
        end_date: Fecha de fin
        method_eu: Ignorado, se usa siempre metodo colombiano

    Returns:
        int: Numero de dias calculados con metodo 360
    """
    start_day = start_date.day
    end_day = end_date.day

    if start_day == 31 or (start_date.month == 2 and start_day >= 28):
        start_day = 30
    else:
        start_day = min(start_day, 30)

    if end_day == 31 or (end_date.month == 2 and end_day >= 28):
        end_day = 30
    else:
        end_day = min(end_day, 30)

    return (
        (end_date.year - start_date.year) * 360 +
        (end_date.month - start_date.month) * 30 +
        (end_day - start_day) + 1
    )

def round_1_decimal(value):
    """Redondea a 1 decimal usando ROUND_HALF_UP."""
    return float(Decimal(str(value)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP))

def json_serial(obj):
    """Función auxiliar para serializar objetos de Odoo y tipos básicos.
    Compatible con Odoo 19 (usa display_name en lugar de name_get).
    """
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    elif isinstance(obj, Decimal):
        return float(obj)
    elif hasattr(obj, '_name'):
        # Objeto de Odoo - usar display_name (Odoo 19 compatible)
        return {
            'id': getattr(obj, 'id', None),
            'name': getattr(obj, 'display_name', '') or getattr(obj, 'name', ''),
            'model': getattr(obj, '_name', '')
        }
    elif hasattr(obj, '__dict__'):
        return {k: v for k, v in obj.__dict__.items()
                if not k.startswith('_') and not callable(v)}
    raise TypeError(f"Type {type(obj)} not serializable")


# ===============================================================================
# CLASE ACUMULADOR DE LÍNEAS
# ===============================================================================

class PayslipLineAccumulator:
    """Clase para acumular líneas de nómina de forma eficiente."""

    def __init__(self):
        self.lines = defaultdict(lambda: {
            'amount': 0,
            'quantity': 0,
            'rate': 100,
            'total': 0,
            'details': [],
            'metadata': {}
        })

    def add(self, code, amount=0, quantity=1, rate=100, total=None, detail=None, **metadata):
        """Agrega o acumula valores para un código de línea."""
        line = self.lines[code]
        line['rate'] = rate
        line['amount'] += amount
        line['quantity'] += quantity

        if total is None:
            total = amount * quantity * rate / 100.0
        line['total'] += total

        if detail:
            line['details'].append(detail)

        line['metadata'].update(metadata)
        return dict(line)

    def get(self, code):
        """Obtiene los valores acumulados para un código."""
        return dict(self.lines.get(code, {}))

    def get_all(self):
        """Obtiene todas las líneas acumuladas."""
        return dict(self.lines)


# ===============================================================================
# CLASE PARA GESTIÓN DE PERÍODOS ANTERIORES (Stub)
# ===============================================================================

class PeriodoAnterior:
    """
    Stub de PeriodoAnterior para cuando lavish_hr_payroll no está instalado.

    Esta clase proporciona una interfaz compatible pero retorna valores vacíos
    hasta que los métodos de acumulación estén disponibles en hr.payslip.
    """

    def __init__(self, payslip):
        self.payslip = payslip
        self._cache = {}
        # Intentar importar CategoryCollection para retornos vacíos
        try:
            from .hr_slip_data_structures import CategoryCollection
            self._CategoryCollection = CategoryCollection
        except ImportError:
            self._CategoryCollection = dict

    def _has_accumulation_methods(self):
        """Verifica si el payslip tiene los métodos de acumulación."""
        return hasattr(self.payslip, '_get_categories_accumulated')

    def cargar_periodo(self, start_date, end_date):
        """Carga categorías de un período."""
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
        """Obtiene una categoría específica del período."""
        categories = self.cargar_periodo(start_date, end_date)
        if hasattr(categories, 'get'):
            return categories.get(category_code)
        return None

    def obtener_total_categoria(self, category_codes, start_date, end_date):
        """Obtiene total de una o más categorías."""
        categories = self.cargar_periodo(start_date, end_date)
        if hasattr(categories, 'get_total'):
            codes_list = category_codes if isinstance(category_codes, list) else [category_codes]
            return categories.get_total(category_codes=codes_list)
        return 0.0

    def obtener_ausencias_por_tipo(self, novelty, start_date, end_date):
        """Filtra ausencias por tipo (novelty)."""
        return []

    def obtener_totales_ausencias(self, start_date, end_date):
        """Obtiene totales agrupados por tipo de ausencia."""
        return {}

    def obtener_horas_extras(self, start_date, end_date, fecha_fin=None):
        """Obtiene horas extras del período."""
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
        """Filtra reglas del período según criterios."""
        return []

    def obtener_reglas_por_categoria(self, category_code, start_date, end_date, **filters):
        """Obtiene reglas de una categoría específica con filtros opcionales."""
        category = self.obtener_categoria(category_code, start_date, end_date)
        if not category:
            return []
        if hasattr(category, 'filter_rules') and filters:
            return category.filter_rules(**filters)
        elif hasattr(category, 'rules'):
            return category.rules
        return []

    def limpiar_cache(self):
        """Limpia cache interno."""
        self._cache.clear()
