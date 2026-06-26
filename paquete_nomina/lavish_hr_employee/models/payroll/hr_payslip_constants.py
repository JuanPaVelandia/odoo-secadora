# -*- coding: utf-8 -*-
"""
Constantes globales para nómina colombiana
==========================================

Este archivo centraliza todas las constantes, selecciones y configuraciones
usadas en el módulo de nómina.

Contenido:
- Constantes numéricas (días, precisión, etc.)
- Códigos especiales
- Tablas de retención en la fuente
- Mapeos de categorías
- Configuraciones de novedades PILA
- Selecciones para campos
- Funciones auxiliares (days360, round_1_decimal, json_serial)
- Clases de utilidad (PayslipLineAccumulator, PayslipCalculationContext)
"""

from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
from collections import defaultdict
import pytz

# ===============================================================================
# CONSTANTES NUMÉRICAS
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

# ===============================================================================
# CÓDIGOS ESPECIALES
# ===============================================================================

TPCT = 'total_previous_categories'
TPCP = 'total_previous_concepts'
NCI = 'non_constitutive_income'

# ===============================================================================
# TABLA DE RETENCIÓN EN LA FUENTE (Art. 383 E.T.)
# Formato: (desde_uvt, hasta_uvt, tarifa%, resta_uvt, suma_uvt)
# ===============================================================================

TABLA_RETENCION = [
    (0, 95, 0, 0, 0),
    (95, 150, 19, 95, 0),
    (150, 360, 28, 150, 10),
    (360, 640, 33, 360, 69),
    (640, 945, 35, 640, 162),
    (945, 2300, 37, 945, 268),
    (2300, float('inf'), 39, 2300, 770)
]

# ===============================================================================
# TOPES DEDUCCIONES RETENCIÓN EN LA FUENTE (UVT)
# ===============================================================================

TOPES_DEDUCCIONES_RTF = {
    'DEDDEP': {'uvt_mensual': 32, 'uvt_anual': 384, 'base_legal': 'Art. 387 Num. 1 ET', 'porcentaje_base': 10},
    'MEDPRE': {'uvt_mensual': 16, 'uvt_anual': 192, 'base_legal': 'Art. 387 Num. 2 ET'},
    'INTVIV': {'uvt_mensual': 100, 'uvt_anual': 1200, 'base_legal': 'Art. 119 y 387 Num. 3 ET'},
    'AFC': {'uvt_mensual': 316.67, 'uvt_anual': 3800, 'base_legal': 'Art. 126-4 ET', 'porcentaje_limite': 30},
    'AVC': {'uvt_mensual': 316.67, 'uvt_anual': 3800, 'base_legal': 'Art. 126-1 ET', 'porcentaje_limite': 30},
}

# ===============================================================================
# MAPEOS DE CATEGORÍAS
# ===============================================================================

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
        'DESCUENTO_AFC'
    ],
    'SOCIAL_SECURITY': ['SSOCIAL'],
    'PROVISIONS': ['PROV'],
    'BASES': ['IBC', 'IBD', 'IBC_R'],
    'OUTCOME': ['NET']
}

# ===============================================================================
# TIPOS DE NOVEDAD PILA
# ===============================================================================

# Lista simple de códigos válidos
VALID_NOVELTY_TYPES = [
    'sln', 'ige', 'irl', 'lma', 'lpa', 'vco', 'vdi',
    'vre', 'lr', 'lnr', 'lt', 'p'
]

# Selection para campos (hr.leave.type.novelty)
NOVELTY_TYPE_SELECTION = [
    ('sln', 'Suspension temporal del contrato de trabajo'),
    ('ige', 'Incapacidad EPS'),
    ('irl', 'Incapacidad por accidente de trabajo o Enfermedad laboral'),
    ('lma', 'Licencia de Maternidad'),
    ('lpa', 'Licencia de Paternidad'),
    ('vco', 'Vacaciones Compensadas (Dinero)'),
    ('vdi', 'Vacaciones Disfrutadas'),
    ('vre', 'Vacaciones por Retiro'),
    ('lr', 'Licencia remunerada'),
    ('lnr', 'Licencia no Remunerada'),
    ('lt', 'Licencia de Luto'),
    ('p', 'Permisos no remunerados D/H (No se envia en pila)'),
]

# ===============================================================================
# TIPO DE LIQUIDACIÓN DE VALORES (hr.leave.type.liquidacion_value)
# ===============================================================================

LIQUIDATION_VALUE_SELECTION = [
    ('IBC', 'IBC Mes Anterior'),
    ('YEAR', 'Promedio Ano Anterior'),
    ('WAGE', 'Sueldo Actual'),
    ('MIN', 'Parametros minimos de ley'),
]

# ===============================================================================
# CONFIGURACIÓN DE NOVEDADES PILA
# Usado en: cálculos de IBC, seguridad social, auxilio transporte
# ===============================================================================

NOVELTY_TYPES_CONFIG = {
    'sln': {
        'name': 'Suspension temporal del contrato',
        'descuenta_ss': True,       # NO suma al IBC
        'descuenta_trabajo': True,  # Resta dias trabajados
        'paga_salario': False,
        'paga_auxilio': False,
    },
    'ige': {
        'name': 'Incapacidad EPS',
        'descuenta_ss': False,      # Mantiene IBC
        'descuenta_trabajo': True,
        'paga_salario': True,
        'paga_auxilio': False,
        'tramos': True,             # Tiene porcentajes por rangos
    },
    'irl': {
        'name': 'Incapacidad ARL',
        'descuenta_ss': False,
        'descuenta_trabajo': True,
        'paga_salario': True,
        'paga_auxilio': False,
        'tramos': True,
    },
    'lma': {
        'name': 'Licencia de Maternidad',
        'descuenta_ss': False,
        'descuenta_trabajo': True,
        'paga_salario': True,
        'paga_auxilio': False,
    },
    'lpa': {
        'name': 'Licencia de Paternidad',
        'descuenta_ss': False,
        'descuenta_trabajo': True,
        'paga_salario': True,
        'paga_auxilio': False,
    },
    'vco': {
        'name': 'Vacaciones Compensadas (Dinero)',
        'descuenta_ss': False,
        'descuenta_trabajo': False,
        'paga_salario': True,
        'paga_auxilio': False,
    },
    'vdi': {
        'name': 'Vacaciones Disfrutadas',
        'descuenta_ss': False,
        'descuenta_trabajo': True,
        'paga_salario': True,
        'paga_auxilio': False,
    },
    'vre': {
        'name': 'Vacaciones por Retiro',
        'descuenta_ss': False,
        'descuenta_trabajo': True,
        'paga_salario': True,
        'paga_auxilio': False,
    },
    'lr': {
        'name': 'Licencia remunerada',
        'descuenta_ss': False,
        'descuenta_trabajo': True,
        'paga_salario': True,
        'paga_auxilio': True,       # Según configuración
    },
    'lnr': {
        'name': 'Licencia no Remunerada',
        'descuenta_ss': True,       # NO suma al IBC
        'descuenta_trabajo': True,
        'paga_salario': False,
        'paga_auxilio': False,
    },
    'lt': {
        'name': 'Licencia de Luto',
        'descuenta_ss': False,
        'descuenta_trabajo': True,
        'paga_salario': True,
        'paga_auxilio': True,
    },
    'p': {
        'name': 'Permisos no remunerados D/H',
        'descuenta_ss': True,       # NO suma al IBC
        'descuenta_trabajo': True,
        'paga_salario': False,
        'paga_auxilio': False,
        'no_pila': True,            # No se reporta en PILA
    },
}

# ===============================================================================
# MESES Y DIAS DE LA SEMANA
# ===============================================================================

MONTH_SELECTION = [
    ('0', 'Todos'),
    ('1', 'Enero'),
    ('2', 'Febrero'),
    ('3', 'Marzo'),
    ('4', 'Abril'),
    ('5', 'Mayo'),
    ('6', 'Junio'),
    ('7', 'Julio'),
    ('8', 'Agosto'),
    ('9', 'Septiembre'),
    ('10', 'Octubre'),
    ('11', 'Noviembre'),
    ('12', 'Diciembre')
]

MONTH_NAMES = {
    1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
    5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
    9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
}

WEEKDAY_NAMES = {
    0: 'Lunes', 1: 'Martes', 2: 'Miércoles', 3: 'Jueves',
    4: 'Viernes', 5: 'Sábado', 6: 'Domingo'
}


def get_month_name(month_number):
    """Obtiene el nombre del mes en español."""
    return MONTH_NAMES.get(month_number, '')


def get_weekday_name(weekday):
    """Obtiene el nombre del día de la semana en español."""
    return WEEKDAY_NAMES.get(weekday, '')


def format_date_spanish(date_obj, include_weekday=False, include_year=True):
    """Formatea una fecha en español.

    Args:
        date_obj: Objeto date o datetime
        include_weekday: Si incluir el día de la semana
        include_year: Si incluir el año

    Returns:
        String formateado (ej: "Lunes, 15 de Enero del 2025")
    """
    month_name = get_month_name(date_obj.month)
    weekday_name = get_weekday_name(date_obj.weekday())

    if include_year:
        if include_weekday:
            return f"{weekday_name}, {date_obj.day} de {month_name} del {date_obj.year}"
        return f"{date_obj.day} de {month_name} del {date_obj.year}"
    else:
        if include_weekday:
            return f"{weekday_name}, {date_obj.day} de {month_name}"
        return f"{date_obj.day} de {month_name}"


# ===============================================================================
# SELECCIONES PARA CAMPOS DE NÓMINA
# ===============================================================================

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
# FUNCIONES AUXILIARES
# ===============================================================================

def get_novelty_config(novelty_code):
    """
    Obtiene la configuración de una novedad según su código PILA.

    Args:
        novelty_code: Código de la novedad (sln, ige, irl, lma, lpa, etc.)

    Returns:
        dict con la configuración de la novedad, o None si no existe

    Ejemplo:
        config = get_novelty_config('ige')
        if config and not config['descuenta_ss']:
            # Mantiene IBC
    """
    return NOVELTY_TYPES_CONFIG.get(novelty_code)


def days360(start_date, end_date, method_eu=False):
    """
    Calcula el número de días entre dos fechas considerando todos los meses como de 30 días.
    Método comercial colombiano (360 días/año, 30 días/mes).
    Febrero también se trata como 30 días (28 o 29 de febrero = día 30).

    Args:
        start_date: Fecha de inicio
        end_date: Fecha de fin
        method_eu: Ignorado, se usa siempre método colombiano

    Returns:
        int: Número de días calculados con método 360
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


def to_decimal(value):
    """
    Convierte un valor a Decimal de manera segura.
    Evita imprecisión de float al convertir primero a string.

    Args:
        value: Valor a convertir (puede ser int, float, str, Decimal, None)

    Returns:
        Decimal: Valor convertido a Decimal
    """
    if isinstance(value, Decimal):
        return value
    elif value is None:
        return Decimal("0")
    return Decimal(str(value))


def json_serial(obj):
    """
    Función auxiliar para serializar objetos de Odoo y tipos básicos.
    Compatible con Odoo 18 (usa display_name en lugar de name_get).
    """
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    elif isinstance(obj, Decimal):
        return float(obj)
    elif hasattr(obj, '_name'):
        # Objeto de Odoo - usar display_name (Odoo 18 compatible)
        return {
            'id': getattr(obj, 'id', None),
            'name': getattr(obj, 'display_name', '') or getattr(obj, 'name', ''),
            'model': getattr(obj, '_name', '')
        }
    elif hasattr(obj, '__dict__'):
        return {k: v for k, v in obj.__dict__.items()
                if not k.startswith('_') and not callable(v)}
    raise TypeError(f"Type {type(obj)} not serializable")


def calc_check_digits(number):
    """
    Calculate the extra digits that should be appended to the number to make it a valid number.
    Source: python-stdnum iso7064.mod_97_10.calc_check_digits
    """
    number_base10 = ''.join(str(int(x, 36)) for x in number)
    checksum = int(number_base10) % 97
    return '%02d' % ((98 - 100 * checksum) % 97)


# ===============================================================================
# CLASES DE UTILIDAD
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
