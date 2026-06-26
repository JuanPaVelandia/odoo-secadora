# -*- coding: utf-8 -*-

"""
CONFIGURACIÓN Y CONSTANTES PARA REGLAS SALARIALES
==================================================

Este archivo centraliza todas las configuraciones, constantes y métodos de ayuda
utilizados en el cálculo de reglas salariales para Colombia.

Autor: Sistema de Nómina
Fecha: 2025-11-09
Versión: Odoo 19
"""

from decimal import Decimal, ROUND_HALF_UP
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

DAYS_YEAR = 360  
DAYS_NATURAL_YEAR = 365
DAYS_MONTH = 30  



PRESTACIONES_CONFIG = {
    'vacaciones': {
        'campo_base': 'base_vacaciones',
        'tasa': 4.17,
        'nombre': "VACACIONES",
        'codigo': 'PRV_VAC',
        'tipo_prest': 'vacaciones',
        'periodo': 'variable',
        'incluye_auxilio': False,
        'metodo_forzado': 'simple',
        'descripcion': 'Vacaciones - 15 días hábiles por año trabajado'
    },
    'prima': {
        'campo_base': 'base_prima',
        'tasa': 8.33,
        'nombre': "PRIMA",
        'codigo': 'PRV_PRIM',
        'tipo_prest': 'prima',
        'periodo': 'semestral',
        'incluye_auxilio': True,
        'metodo_forzado': None,
        'descripcion': 'Prima de servicios - 1 mes de salario por año (2 pagos semestrales)'
    },
    'cesantias': {
        'campo_base': 'base_cesantias',
        'tasa': 8.33,
        'nombre': "CESANTÍAS",
        'codigo': 'PRV_CES',
        'tipo_prest': 'cesantias',
        'periodo': 'anual',
        'incluye_auxilio': True,
        'metodo_forzado': None,
        'descripcion': 'Cesantías - 1 mes de salario por año trabajado'
    },
    'intereses': {
        'campo_base': 'base_cesantias',
        'tasa': 12,
        'nombre': "INTERESES CESANTÍAS",
        'codigo': 'PRV_ICES',
        'tipo_prest': 'intereses',
        'periodo': 'anual',
        'incluye_auxilio': False,
        'metodo_forzado': None,
        'dependencia': 'PRV_CES',
        'descripcion': 'Intereses sobre cesantías - 12% anual'
    }
}

PRESTACIONES_BASE_FIELDS = {
    'prima': {
        'legacy': 'base_prima',
        'provision': 'base_prima_provision',
        'liquidacion': 'base_prima_liquidacion',
    },
    'cesantias': {
        'legacy': 'base_cesantias',
        'provision': 'base_cesantias_provision',
        'liquidacion': 'base_cesantias_liquidacion',
    },
    'intereses': {
        'legacy': 'base_intereses_cesantias',
        'provision': 'base_intereses_cesantias_provision',
        'liquidacion': 'base_intereses_cesantias_liquidacion',
    },
    'intereses_cesantias': {
        'legacy': 'base_intereses_cesantias',
        'provision': 'base_intereses_cesantias_provision',
        'liquidacion': 'base_intereses_cesantias_liquidacion',
    },
    'vacaciones': {
        'legacy': 'base_vacaciones',
        'provision': 'base_vacaciones_provision',
        'liquidacion': 'base_vacaciones_liquidacion',
    },
    'vacaciones_dinero': {
        'legacy': 'base_vacaciones_dinero',
        'provision': 'base_vacaciones_dinero_provision',
        'liquidacion': 'base_vacaciones_dinero_liquidacion',
    },
}


def get_prestacion_base_field(tipo_prestacion, contexto='liquidacion'):
    """
    Retorna el campo base de regla salarial según tipo y contexto.

    Args:
        tipo_prestacion: prima, cesantias, intereses, vacaciones, vacaciones_dinero
        contexto: 'provision', 'liquidacion' o 'legacy'

    Returns:
        str: Nombre del campo base en hr.salary.rule.
    """
    field_config = PRESTACIONES_BASE_FIELDS.get(tipo_prestacion, PRESTACIONES_BASE_FIELDS['prima'])
    if contexto in ('provision', 'liquidacion'):
        return field_config[contexto]
    return field_config['legacy']


def get_contextual_base_field(campo_base_legacy, contexto='liquidacion'):
    """
    Convierte un campo legacy base_* al campo separado por contexto.

    Args:
        campo_base_legacy: Campo legacy (ej: base_prima)
        contexto: 'provision', 'liquidacion' o 'legacy'
    """
    if contexto not in ('provision', 'liquidacion'):
        return campo_base_legacy

    for field_config in PRESTACIONES_BASE_FIELDS.values():
        if field_config['legacy'] == campo_base_legacy:
            return field_config[contexto]

    return campo_base_legacy



CODIGOS_LIQUIDACION = {
    'vacaciones': 'VACCONTRATO',
    'prima': 'PRIMA',
    'cesantias': 'CESANTIAS',
    'intereses': 'INTCESANTIAS'
}


CATEGORIAS_EXCLUIDAS = ['BASIC', 'AUX']

CATEGORIAS_VARIABLES_ACTUALES = ['HEYREC', 'COMISIONES', 'BONIFICACIONES']
CATEGORIAS_VARIABLES_ACUMULADAS = ['HEYREC', 'o_SALARY', 'COMP', 'O_EARN']

CATEGORIAS_DEVENGOS_SALARIALES = ['DEV_SALARIAL']



TIPOS_COTIZANTES_EXENTOS = ['12', '19']




INDEM_CONFIG = {
    'salario_bajo': {  # < 10 SMMLV
        'limite_smmlv': 10,
        'anio_1': 30,  # días por año 1
        'anios_2_5': 20,  # días por año del 2 al 5
        'anios_6_mas': 13.33,  # días por año del 6 en adelante
    },
    'salario_alto': {  # >= 10 SMMLV
        'limite_smmlv': 10,
        'anio_1': 20,  # días por año 1
        'anios_adicionales': 15,  # días por cada año adicional
    },
    'contrato_obra': {
        'minimo_dias': 15  # Mínimo de días para contrato por obra
    }
}


# ══════════════════════════════════════════════════════════════════════════
# SEGURIDAD SOCIAL - PORCENTAJES
# ══════════════════════════════════════════════════════════════════════════

SEGURIDAD_SOCIAL_CONFIG = {
    'salud': {
        'empleado': 4.0,
        'empleador': 8.5,
        'total': 12.5
    },
    'pension': {
        'empleado': 4.0,
        'empleador': 12.0,
        'total': 16.0
    },
    'arl': {
        'nivel_1': 0.522,
        'nivel_2': 1.044,
        'nivel_3': 2.436,
        'nivel_4': 4.350,
        'nivel_5': 6.960
    },
    'fondo_solidaridad': {
        'rango_4_16': 1.0,  # 4-16 SMMLV
        'rango_16_17': 1.2,  # 16-17 SMMLV
        'rango_17_18': 1.4,  # 17-18 SMMLV
        'rango_18_19': 1.6,  # 18-19 SMMLV
        'rango_19_20': 1.8,  # 19-20 SMMLV
        'rango_20_mas': 2.0,  # > 20 SMMLV
    }
}


# ══════════════════════════════════════════════════════════════════════════
# PARAFISCALES - PORCENTAJES
# ══════════════════════════════════════════════════════════════════════════

PARAFISCALES_CONFIG = {
    'sena': 2.0,
    'icbf': 3.0,
    'caja_compensacion': 4.0
}


# ══════════════════════════════════════════════════════════════════════════
# HORAS EXTRAS Y RECARGOS - PORCENTAJES
# ══════════════════════════════════════════════════════════════════════════

HORAS_EXTRAS_CONFIG = {
    'HED': {
        'nombre': 'Hora Extra Diurna',
        'recargo': 25.0,  # 25% adicional
        'codigo': 'HED'
    },
    'HEN': {
        'nombre': 'Hora Extra Nocturna',
        'recargo': 75.0,  # 75% adicional
        'codigo': 'HEN'
    },
    'HEDF': {
        'nombre': 'Hora Extra Diurna Festiva',
        'recargo': 100.0,  # 100% adicional
        'codigo': 'HEDF'
    },
    'HENF': {
        'nombre': 'Hora Extra Nocturna Festiva',
        'recargo': 150.0,  # 150% adicional
        'codigo': 'HENF'
    },
    'RN': {
        'nombre': 'Recargo Nocturno',
        'recargo': 35.0,  # 35% adicional
        'codigo': 'RN'
    },
    'RDF': {
        'nombre': 'Recargo Dominical/Festivo',
        'recargo': 75.0,  # 75% adicional
        'codigo': 'RDF'
    },
    'RDNF': {
        'nombre': 'Recargo Dominical/Festivo Nocturno',
        'recargo': 110.0,  # 110% adicional
        'codigo': 'RDNF'
    }
}


# ══════════════════════════════════════════════════════════════════════════
# RETENCIÓN EN LA FUENTE - CONFIGURACIÓN
# ══════════════════════════════════════════════════════════════════════════

RETENCION_CONFIG = {
    'conceptos_exentos': [
        'SALUD',
        'PENSION',
        'AFC',  # Ahorro Fondo Cesantías
        'MEDICINA_PREPAGADA',
        'DEPENDIENTES',
        'INTERESES_VIVIENDA'
    ],
    'limites_exencion': {
        'pension_voluntaria': 0.30,  # 30% del ingreso laboral
        'medicina_prepagada': 16,  # 16 UVT mensuales
        'dependientes': 32,  # 32 UVT mensuales
        'intereses_vivienda': 100,  # 100 UVT mensuales
    },
    'renta_exenta_genegal': 0.25,  # 25% del ingreso neto
    'limite_renta_exenta': 790  # 790 UVT mensuales (240*12/12)
}


# ══════════════════════════════════════════════════════════════════════════
# MÉTODOS DE UTILIDAD
# ══════════════════════════════════════════════════════════════════════════

def to_decimal(value):
    """
    Convierte un valor a Decimal de manera segura.

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


def decimal_round(value, precision=2):
    """
    Redondea un valor Decimal al número de decimales especificado.

    Args:
        value: Valor a redondear
        precision: Número de decimales (default: 2)

    Returns:
        Decimal: Valor redondeado
    """
    value = to_decimal(value)
    decimal_precision = Decimal(f'0.{"0" * precision}1')
    return value.quantize(decimal_precision, rounding=ROUND_HALF_UP)


def round_payroll_amount(amount, decimals=0):
    """
    Redondea montos de nómina para consistencia en cálculos.

    Por defecto redondea a enteros (decimals=0) para evitar
    discrepancias contables por centavos.

    Compatible con lavish_hr_payroll.models.utils.round_payroll_amount

    Args:
        amount: Monto a redondear (int, float, Decimal, None)
        decimals: Número de decimales (default: 0 para enteros)

    Returns:
        Decimal: Monto redondeado
    """
    if amount is None:
        return Decimal('0')

    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))

    if decimals == 0:
        return amount.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    else:
        quantizer = Decimal(10) ** -decimals
        return amount.quantize(quantizer, rounding=ROUND_HALF_UP)


def days360(date_from, date_to):
    """
    Calcula dias entre dos fechas usando el metodo comercial colombiano 360 dias.
    Metodo: Cada mes tiene 30 dias, año tiene 360 dias.
    Febrero tambien se trata como 30 dias (28 o 29 de febrero = dia 30).
    Incluye ambos dias (inicio y fin) en el calculo.

    Args:
        date_from: Fecha inicial
        date_to: Fecha final

    Returns:
        int: Numero de dias calculados (inclusivo)
    """
    if not date_from or not date_to:
        return 0

    day1 = date_from.day
    day2 = date_to.day

    if day1 == 31 or (date_from.month == 2 and day1 >= 28):
        day1 = 30
    else:
        day1 = min(day1, 30)

    if day2 == 31 or (date_to.month == 2 and day2 >= 28):
        day2 = 30
    else:
        day2 = min(day2, 30)

    return (
        (date_to.year - date_from.year) * 360 +
        (date_to.month - date_from.month) * 30 +
        (day2 - day1) + 1
    )


def normalizar_base_dias(base_dias, default=DAYS_YEAR):
    """
    Normaliza la base de dias para calculos (360/365).

    Args:
        base_dias: Valor origen (str/int/None)
        default: Base por defecto si no es valida

    Returns:
        int: Base de dias (360 o 365)
    """
    try:
        base_val = int(base_dias)
    except (TypeError, ValueError):
        return default

    if base_val == DAYS_NATURAL_YEAR:
        return DAYS_NATURAL_YEAR
    if base_val == DAYS_YEAR:
        return DAYS_YEAR
    return default


def dias_periodo_base(date_from, date_to, base_dias, incluir_inicio=True):
    """
    Calcula dias entre fechas segun base 360 o 365.

    Args:
        date_from: Fecha inicial
        date_to: Fecha final
        base_dias: Base anual (360 o 365)
        incluir_inicio: Si incluye el dia inicial

    Returns:
        int: Dias calculados
    """
    if not date_from or not date_to or date_from > date_to:
        return 0

    base_dias = normalizar_base_dias(base_dias)

    if base_dias == DAYS_NATURAL_YEAR:
        delta = (date_to - date_from).days
        return delta + (1 if incluir_inicio else 0)

    if incluir_inicio:
        return days360(date_from, date_to)
    if date_from >= date_to:
        return 0
    return days360(date_from + timedelta(days=1), date_to)


def validar_tipo_cotizante(employee):
    """
    Valida si el empleado está exento de prestaciones por tipo de cotizante.

    Args:
        employee: Objeto hr.employee

    Returns:
        bool: True si está exento, False si no
    """
    if employee.tipo_coti_id and employee.tipo_coti_id.code in TIPOS_COTIZANTES_EXENTOS:
        return True
    return False


def validar_salario_integral(contract):
    """
    Valida si el contrato es de salario integral.

    Args:
        contract: Objeto hr.contract

    Returns:
        bool: True si es integral, False si no
    """
    return contract.modality_salary == 'integral'


def calcular_smmlv_periodo(annual_parameters, dias_periodo):
    """
    Calcula el SMMLV proporcional al período.

    Args:
        annual_parameters: Parámetros anuales
        dias_periodo: Días del período

    Returns:
        float: SMMLV proporcional
    """
    if not annual_parameters:
        return 0

    smmlv_mensual = annual_parameters.smmlv_monthly
    return (smmlv_mensual / 30) * dias_periodo


def calcular_auxilio_transporte_periodo(annual_parameters, dias_periodo):
    """
    Calcula el auxilio de transporte proporcional al período.

    Args:
        annual_parameters: Parámetros anuales
        dias_periodo: Días del período

    Returns:
        float: Auxilio de transporte proporcional
    """
    if not annual_parameters:
        return 0

    auxilio_mensual = annual_parameters.transportation_assistance_monthly
    return (auxilio_mensual / 30) * dias_periodo


def determinar_periodo_prestacion(tipo_prestacion, slip, contract):
    """
    Determina el período de cálculo según tipo de prestación.

    Args:
        tipo_prestacion: Tipo de prestación ('prima', 'cesantias', 'intereses', 'vacaciones')
        slip: Nómina actual
        contract: Contrato del empleado

    Returns:
        dict: {'date_from': fecha_inicio, 'date_to': fecha_fin}
    """
    date_to = slip.date_to

    if tipo_prestacion in ['cesantias', 'intereses']:
        # Año completo
        date_from = date(date_to.year, 1, 1)
        if slip.struct_process == 'contrato' and slip.date_liquidacion:
            date_to = slip.date_liquidacion
        if contract.date_start and contract.date_start > date_from:
            date_from = contract.date_start

    elif tipo_prestacion == 'prima':
        # Semestre
        if date_to.month <= 6:
            date_from = date(date_to.year, 1, 1)
        else:
            date_from = date(date_to.year, 7, 1)
        if slip.struct_process == 'contrato' and slip.date_liquidacion:
            date_to = slip.date_liquidacion
        if contract.date_start and contract.date_start > date_from:
            date_from = contract.date_start

    else:  # vacaciones
        date_from = slip.date_from
        if slip.struct_process == 'contrato' and slip.date_liquidacion:
            date_to = slip.date_liquidacion

    return {
        'date_from': date_from,
        'date_to': date_to
    }


def filtrar_conceptos_por_base(rules, campo_base, excluir_categorias=None):
    """
    Filtra conceptos de reglas según campo base y excluye categorías.

    Args:
        rules: Diccionario de reglas del payslip
        campo_base: Campo base a filtrar ('base_prima', 'base_cesantias', etc.)
        excluir_categorias: Lista de categorías a excluir (default: ['BASIC', 'AUX'])

    Returns:
        list: Lista de conceptos filtrados con {'codigo', 'nombre', 'valor'}
    """
    if excluir_categorias is None:
        excluir_categorias = CATEGORIAS_EXCLUIDAS

    conceptos_incluidos = []
    total = 0.0

    if not rules:
        return conceptos_incluidos, total

    for code, rule_data in rules.items():
        rule_obj = rule_data.rule
        if not rule_obj:
            continue

        # Excluir categorías
        if rule_data.category_code in excluir_categorias:
            continue

        # Solo conceptos que tengan marcado el campo base
        try:
            campo_valor = rule_obj[campo_base] if campo_base in rule_obj._fields else False
        except Exception:  # noqa: BLE001 – acceso defensivo a campo de regla, fallback a False
            _logger.debug("Error accediendo al campo '%s' de la regla %s", campo_base, getattr(rule_obj, 'code', '?'), exc_info=True)
            campo_valor = False

        if campo_valor:
            valor = rule_data.total
            total += valor
            if valor > 0:
                conceptos_incluidos.append({
                    'codigo': code,
                    'nombre': rule_obj.name,
                    'valor': valor,
                    'categoria': rule_data.category_code
                })

    return conceptos_incluidos, total


def calcular_valor_hora(salario_mensual, horas_mes=240):
    """
    Calcula el valor de la hora de trabajo.

    Args:
        salario_mensual: Salario mensual del empleado
        horas_mes: Horas al mes (default: 240 = 8 horas * 30 días)

    Returns:
        float: Valor de la hora
    """
    return salario_mensual / horas_mes if horas_mes > 0 else 0


def calcular_recargo_hora(valor_hora, tipo_recargo):
    """
    Calcula el recargo de hora extra según tipo.

    Args:
        valor_hora: Valor base de la hora
        tipo_recargo: Tipo de recargo ('HED', 'HEN', 'HEDF', etc.)

    Returns:
        float: Valor de la hora con recargo
    """
    config = HORAS_EXTRAS_CONFIG.get(tipo_recargo)
    if not config:
        return valor_hora

    recargo = config['recargo']
    return valor_hora * (1 + recargo / 100)


def preparar_datos_visualizacion(metodo, **kwargs):
    """
    Prepara estructura de datos para visualización.

    Args:
        metodo: 'simple' o 'complejo'
        **kwargs: Datos adicionales

    Returns:
        dict: Datos estructurados para visualización
    """
    data_visual = {
        'metodo': metodo,
        'fecha_calculo': date.today().strftime('%Y-%m-%d')
    }
    data_visual.update(kwargs)
    return data_visual


# ══════════════════════════════════════════════════════════════════════════
# HELPERS PARA DICCIONARIOS DE LÍNEAS (Compatible con services/)
# ══════════════════════════════════════════════════════════════════════════

def crear_linea_dict(rule, amount, quantity=1.0, rate=100.0, slip=None, contract=None, **kwargs):
    """
    Crea un diccionario de línea estandarizado compatible con hr.payslip.line.

    Estructura idéntica a la usada en lavish_hr_payroll/models/services/.

    Args:
        rule: hr.salary.rule record
        amount: Monto base de la línea
        quantity: Cantidad (días, horas, etc.) - default 1.0
        rate: Porcentaje (0-100) - default 100.0
        slip: hr.payslip record (opcional)
        contract: hr.contract record (opcional)
        **kwargs: Campos adicionales (entity_id, concept_id, loan_id, etc.)

    Returns:
        dict: Diccionario listo para crear hr.payslip.line
    """
    if not rule:
        return None

    total = float(round_payroll_amount(amount * quantity * rate / 100.0))

    linea = {
        'sequence': rule.sequence if rule.sequence else 0,
        'code': rule.code if rule.code else '',
        'name': kwargs.get('name') or (rule.name if rule.name else ''),
        'salary_rule_id': rule.id if rule.id else False,
        'contract_id': contract.id if contract and contract.id else False,
        'employee_id': contract.employee_id.id if contract and contract.employee_id else False,
        'entity_id': kwargs.get('entity_id', False),
        'amount': float(amount),
        'quantity': float(quantity),
        'rate': float(rate),
        'total': total,
        'slip_id': slip.id if slip and slip.id else False,
        'run_id': slip.payslip_run_id.id if slip and slip.payslip_run_id and slip.payslip_run_id.id else False,
    }

    # Agregar campos adicionales (concept_id, loan_id, novedad_id, etc.)
    for key, value in kwargs.items():
        if key not in linea and key != 'name':
            linea[key] = value

    return linea


def crear_log_data(status, tipo, **kwargs):
    """
    Crea diccionario de log/debug estandarizado para reglas.

    Args:
        status: 'success', 'rejected', 'error', 'no_data', etc.
        tipo: Tipo de regla ('basic', 'auxilio', 'prestacion', etc.)
        **kwargs: Datos adicionales del cálculo

    Returns:
        dict: Diccionario de log estructurado
    """
    log = {
        'status': status,
        'tipo': tipo,
        'fecha_calculo': date.today().strftime('%Y-%m-%d'),
    }
    log.update(kwargs)
    return log


def crear_data_kpi(base, dias, total, **kwargs):
    """
    Crea diccionario de KPIs para visualización en widgets.

    Compatible con la estructura usada en prestaciones_sociales.py.

    Args:
        base: Base de cálculo (salario diario, valor hora, etc.)
        dias: Días o cantidad usada en el cálculo
        total: Total calculado
        **kwargs: KPIs adicionales

    Returns:
        dict: Diccionario de KPIs
    """
    kpi = {
        'base': float(base),
        'dias': float(dias),
        'total': float(total),
        'formula': kwargs.get('formula', f'{base:,.2f} x {dias} = {total:,.2f}'),
    }
    kpi.update(kwargs)
    return kpi


def crear_resultado_regla(amount, quantity, rate, nombre, log_data=None, data_kpi=None, **extras):
    """
    Crea la tupla de retorno estándar para métodos de reglas.

    Los métodos de reglas retornan: (amount, quantity, rate, name, log_html, data_dict)

    Args:
        amount: Monto/rate por unidad
        quantity: Cantidad (días, horas, etc.)
        rate: Porcentaje (0-100)
        nombre: Nombre descriptivo para la línea
        log_data: Diccionario de log (opcional)
        data_kpi: Diccionario de KPIs (opcional)
        **extras: Datos adicionales para el diccionario final

    Returns:
        tuple: (amount, quantity, rate, nombre, '', data_dict)
    """
    data = {}

    if log_data:
        data['log'] = log_data

    if data_kpi:
        data['data_kpi'] = data_kpi

    data.update(extras)

    return (float(amount), float(quantity), float(rate), nombre, '', data)


def crear_resultado_vacio(nombre, razon='', tipo=''):
    """
    Crea resultado vacío para cuando una regla no aplica.

    Args:
        nombre: Nombre de la regla
        razon: Razón por la que no aplica
        tipo: Tipo de regla

    Returns:
        tuple: (0, 0, 0, nombre, '', log_data)
    """
    log_data = crear_log_data('rejected', tipo, reason=razon) if razon else {}
    return (0, 0, 0, nombre, '', log_data)


# ══════════════════════════════════════════════════════════════════════════
# VALIDACIONES Y REGLAS DE NEGOCIO
# ══════════════════════════════════════════════════════════════════════════

def validar_aplica_auxilio_transporte(salario_base, salario_variable, smmlv, modality_aux):
    """
    Valida si aplica auxilio de transporte según salario.

    Args:
        salario_base: Salario base mensual
        salario_variable: Salario variable mensual
        smmlv: Salario mínimo legal vigente
        modality_aux: Modalidad de auxilio ('basico' o 'variable')

    Returns:
        bool: True si aplica, False si no
    """
    dos_smmlv = 2 * smmlv

    if modality_aux == 'basico':
        return salario_base < dos_smmlv
    elif modality_aux == 'variable':
        return salario_variable < dos_smmlv

    return False


def obtener_escala_indemnizacion(salario_total, smmlv):
    """
    Obtiene la escala de indemnización según salario.

    Args:
        salario_total: Salario total mensual
        smmlv: Salario mínimo legal vigente

    Returns:
        str: 'salario_bajo' o 'salario_alto'
    """
    limite = INDEM_CONFIG['salario_bajo']['limite_smmlv']

    if salario_total < (limite * smmlv):
        return 'salario_bajo'
    else:
        return 'salario_alto'


# ══════════════════════════════════════════════════════════════════════════
# FORMATEO Y PRESENTACIÓN
# ══════════════════════════════════════════════════════════════════════════

def formatear_moneda(valor):
    """
    Formatea un valor como moneda.

    Args:
        valor: Valor numérico

    Returns:
        str: Valor formateado como "$1,234.56"
    """
    return f"${valor:,.2f}"


def formatear_porcentaje(valor):
    """
    Formatea un valor como porcentaje.

    Args:
        valor: Valor numérico (ej: 25 para 25%)

    Returns:
        str: Valor formateado como "25.00%"
    """
    return f"{valor:.2f}%"


def generar_nombre_prestacion(tipo, periodo_info):
    """
    Genera nombre descriptivo para prestación.

    Args:
        tipo: Tipo de prestación
        periodo_info: Información del período

    Returns:
        str: Nombre descriptivo
    """
    config = PRESTACIONES_CONFIG.get(tipo)
    if not config:
        return tipo.upper()

    nombre_base = config['nombre']

    if tipo == 'prima':
        semestre = 1 if periodo_info.get('mes_fin', 12) <= 6 else 2
        anio = periodo_info.get('anio', date.today().year)
        return f"{nombre_base} {semestre}° SEMESTRE {anio}"
    elif tipo in ['cesantias', 'intereses']:
        anio = periodo_info.get('anio', date.today().year)
        return f"{nombre_base} AÑO {anio}"
    else:
        return nombre_base


def obtener_dias_liquidacion(localdict):
    """
    Obtiene los días a liquidar en liquidaciones de contrato.

    Prioridad:
    1. Días manuales (si están configurados) - para ajustes o cuando no hay más nóminas
    2. BASIC005.quantity (días pagados en la nómina)
    3. Cálculo days360 entre fechas del slip

    Args:
        localdict (dict): Diccionario de contexto con slip, contract, rules, etc.

    Returns:
        dict: {
            'days': float - Días a liquidar
            'source': str - Origen: 'manual_days', 'basic005_quantity', 'days360', 'not_liquidacion'
            'is_liquidacion': bool
            'metadata': dict con info adicional
        }
    """
    slip = localdict.get('slip') or localdict.get('payslip')
    rules = localdict.get('rules', {})

    resultado = {
        'days': 0.0,
        'source': 'not_liquidacion',
        'is_liquidacion': False,
        'metadata': {}
    }

    if not slip:
        return resultado

    # Verificar si es liquidación
    is_liquidacion = (slip.struct_process == 'contrato' and slip.date_liquidacion)
    resultado['is_liquidacion'] = is_liquidacion

    if not is_liquidacion:
        return resultado

    # PRIORIDAD 1: Días manuales (para ajustes o cuando no hay más nóminas)
    if slip.use_manual_days:
        if slip.manual_days and slip.manual_days > 0:
            resultado['days'] = float(slip.manual_days)
            resultado['source'] = 'manual_days'
            resultado['metadata']['manual_days_value'] = slip.manual_days
            resultado['metadata']['manual_override'] = True
            return resultado

    # PRIORIDAD 2: BASIC005 (días pagados)
    basic005 = rules.get('BASIC005')
    if basic005 and basic005.quantity:
        resultado['days'] = float(basic005.quantity)
        resultado['source'] = 'basic005_quantity'
        resultado['metadata']['basic005_quantity'] = basic005.quantity
        resultado['metadata']['basic005_available'] = True
        return resultado

    # PRIORIDAD 3: Calcular days360 entre fechas del slip
    if slip.date_from and slip.date_to:
        dias_calculados = days360(slip.date_from, slip.date_to)
        resultado['days'] = float(dias_calculados)
        resultado['source'] = 'days360'
        resultado['metadata']['date_from'] = slip.date_from.strftime('%Y-%m-%d')
        resultado['metadata']['date_to'] = slip.date_to.strftime('%Y-%m-%d')
        resultado['metadata']['calculated'] = True
        return resultado

    return resultado


# ══════════════════════════════════════════════════════════════════════════
# FESTIVOS COLOMBIANOS (Ley Emiliani - Ley 51 de 1983)
# ══════════════════════════════════════════════════════════════════════════

def get_easter_date(year):
    """
    Calcula la fecha de Pascua usando el algoritmo de Gauss.

    Args:
        year: Ano para calcular

    Returns:
        date: Fecha de Pascua
    """
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def mover_a_lunes(fecha):
    """
    Mueve una fecha al lunes siguiente si no es lunes (Ley Emiliani).

    Args:
        fecha: date a evaluar

    Returns:
        date: Lunes siguiente o la misma fecha si ya es lunes
    """
    dia_semana = fecha.weekday()  # 0=Lunes, 6=Domingo
    if dia_semana == 0:
        return fecha
    dias_a_sumar = 7 - dia_semana
    return fecha + timedelta(days=dias_a_sumar)


def get_festivos_colombianos(year):
    """
    Obtiene los festivos colombianos para un ano dado.
    Implementa la Ley Emiliani (Ley 51 de 1983) para festivos trasladables.

    Base Legal:
    - Ley 51 de 1983 (Ley Emiliani): Traslado de festivos a lunes
    - Codigo Sustantivo del Trabajo: Descanso remunerado en festivos

    Args:
        year: Ano para obtener festivos

    Returns:
        list[dict]: Lista de festivos con fecha, nombre y si es trasladable
    """
    festivos = []

    # ══════════════════════════════════════════════════════════════════════
    # FESTIVOS FIJOS (No se trasladan)
    # ══════════════════════════════════════════════════════════════════════
    festivos_fijos = [
        (date(year, 1, 1), 'Ano Nuevo', False),
        (date(year, 5, 1), 'Dia del Trabajo', False),
        (date(year, 7, 20), 'Dia de la Independencia', False),
        (date(year, 8, 7), 'Batalla de Boyaca', False),
        (date(year, 12, 8), 'Inmaculada Concepcion', False),
        (date(year, 12, 25), 'Navidad', False),
    ]

    for fecha, nombre, trasladable in festivos_fijos:
        festivos.append({
            'fecha': fecha,
            'nombre': nombre,
            'trasladable': trasladable,
            'fecha_original': fecha,
        })

    # ══════════════════════════════════════════════════════════════════════
    # FESTIVOS TRASLADABLES (Ley Emiliani - se mueven al lunes)
    # ══════════════════════════════════════════════════════════════════════
    festivos_emiliani = [
        (date(year, 1, 6), 'Reyes Magos'),
        (date(year, 3, 19), 'San Jose'),
        (date(year, 6, 29), 'San Pedro y San Pablo'),
        (date(year, 8, 15), 'Asuncion de la Virgen'),
        (date(year, 10, 12), 'Dia de la Raza'),
        (date(year, 11, 1), 'Todos los Santos'),
        (date(year, 11, 11), 'Independencia de Cartagena'),
    ]

    for fecha_original, nombre in festivos_emiliani:
        fecha_trasladada = mover_a_lunes(fecha_original)
        festivos.append({
            'fecha': fecha_trasladada,
            'nombre': nombre,
            'trasladable': True,
            'fecha_original': fecha_original,
            'fue_trasladado': fecha_trasladada != fecha_original,
        })

    # ══════════════════════════════════════════════════════════════════════
    # SEMANA SANTA (Basados en Pascua)
    # ══════════════════════════════════════════════════════════════════════
    pascua = get_easter_date(year)

    # Jueves Santo (3 dias antes de Pascua) - NO trasladable
    jueves_santo = pascua - timedelta(days=3)
    festivos.append({
        'fecha': jueves_santo,
        'nombre': 'Jueves Santo',
        'trasladable': False,
        'fecha_original': jueves_santo,
        'relativo_a': 'Pascua -3 dias',
    })

    # Viernes Santo (2 dias antes de Pascua) - NO trasladable
    viernes_santo = pascua - timedelta(days=2)
    festivos.append({
        'fecha': viernes_santo,
        'nombre': 'Viernes Santo',
        'trasladable': False,
        'fecha_original': viernes_santo,
        'relativo_a': 'Pascua -2 dias',
    })

    # ══════════════════════════════════════════════════════════════════════
    # FESTIVOS MOVILES BASADOS EN PASCUA (Trasladables a lunes)
    # ══════════════════════════════════════════════════════════════════════
    festivos_pascua_emiliani = [
        (39, 'Ascension del Senor'),      # 39 dias despues de Pascua
        (60, 'Corpus Christi'),            # 60 dias despues de Pascua
        (68, 'Sagrado Corazon de Jesus'),  # 68 dias despues de Pascua
    ]

    for dias_despues, nombre in festivos_pascua_emiliani:
        fecha_original = pascua + timedelta(days=dias_despues)
        fecha_trasladada = mover_a_lunes(fecha_original)
        festivos.append({
            'fecha': fecha_trasladada,
            'nombre': nombre,
            'trasladable': True,
            'fecha_original': fecha_original,
            'fue_trasladado': fecha_trasladada != fecha_original,
            'relativo_a': f'Pascua +{dias_despues} dias',
        })

    # Ordenar por fecha
    festivos.sort(key=lambda x: x['fecha'])

    return festivos


def get_festivos_en_periodo(date_from, date_to):
    """
    Obtiene los festivos dentro de un periodo especifico.

    Args:
        date_from: Fecha inicio del periodo
        date_to: Fecha fin del periodo

    Returns:
        list[dict]: Festivos dentro del periodo
    """
    festivos = []

    # Obtener festivos de los anos involucrados
    anos = set([date_from.year, date_to.year])
    for ano in anos:
        festivos.extend(get_festivos_colombianos(ano))

    # Filtrar por periodo
    festivos_periodo = [
        f for f in festivos
        if date_from <= f['fecha'] <= date_to
    ]

    return festivos_periodo


def contar_dias_laborales(date_from, date_to, incluir_sabados=False):
    """
    Cuenta los dias laborales en un periodo (excluyendo festivos y fines de semana).

    Args:
        date_from: Fecha inicio
        date_to: Fecha fin
        incluir_sabados: Si True, cuenta sabados como laborales

    Returns:
        dict: {
            'dias_totales': int,
            'dias_laborales': int,
            'festivos': int,
            'sabados': int,
            'domingos': int,
            'detalle_festivos': list
        }
    """
    festivos = get_festivos_en_periodo(date_from, date_to)
    fechas_festivos = {f['fecha'] for f in festivos}

    dias_totales = 0
    dias_laborales = 0
    sabados = 0
    domingos = 0
    festivos_count = 0

    current = date_from
    while current <= date_to:
        dias_totales += 1
        dia_semana = current.weekday()

        if current in fechas_festivos:
            festivos_count += 1
        elif dia_semana == 6:  # Domingo
            domingos += 1
        elif dia_semana == 5:  # Sabado
            sabados += 1
            if incluir_sabados:
                dias_laborales += 1
        else:  # Lunes a Viernes
            dias_laborales += 1

        current += timedelta(days=1)

    return {
        'dias_totales': dias_totales,
        'dias_laborales': dias_laborales,
        'festivos': festivos_count,
        'sabados': sabados,
        'domingos': domingos,
        'detalle_festivos': festivos,
    }


# ══════════════════════════════════════════════════════════════════════════
# ESTRUCTURA ESTANDAR DE COMPUTATION PARA VISUALIZACION
# ══════════════════════════════════════════════════════════════════════════

# Tipos de visualizacion disponibles
TIPOS_VISUALIZACION = {
    'basico': {
        'nombre': 'Salario Basico',
        'template': 'generic',
        'mostrar_formula': True,
    },
    'auxilio': {
        'nombre': 'Auxilio de Transporte',
        'template': 'generic',
        'mostrar_formula': True,
    },
    'ibd': {
        'nombre': 'Ingreso Base de Cotizacion',
        'template': 'ibd',
        'mostrar_formula': True,
        'mostrar_pasos': True,
        'mostrar_base_legal': True,
    },
    'seguridad_social': {
        'nombre': 'Seguridad Social',
        'template': 'seguridad_social',
        'mostrar_formula': True,
    },
    'prestacion': {
        'nombre': 'Prestacion Social',
        'template': 'prestacion',
        'mostrar_formula': True,
        'mostrar_pasos': True,
    },
    'retencion': {
        'nombre': 'Retencion en la Fuente',
        'template': 'retencion',
        'mostrar_formula': True,
        'mostrar_pasos': True,
        'mostrar_base_legal': True,
    },
    'hora_extra': {
        'nombre': 'Hora Extra / Recargo',
        'template': 'hora_extra',
        'mostrar_formula': True,
        'mostrar_detalle': True,
    },
    'indemnizacion': {
        'nombre': 'Indemnizacion',
        'template': 'indemnizacion',
        'mostrar_formula': True,
        'mostrar_pasos': True,
        'mostrar_base_legal': True,
    },
    'prestamo': {
        'nombre': 'Prestamo / Deduccion',
        'template': 'prestamo',
        'mostrar_saldo': True,
    },
    'novedad': {
        'nombre': 'Novedad / Ausencia',
        'template': 'novedad',
    },
    'generic': {
        'nombre': 'Calculo General',
        'template': 'generic',
        'mostrar_formula': True,
    },
}


def crear_computation_estandar(tipo_visualizacion, **kwargs):
    """
    Crea una estructura de computation estandarizada para el widget.

    Esta estructura es la que el widget debe leer directamente,
    sin necesidad de recalcular nada en el frontend.

    Args:
        tipo_visualizacion: Tipo de visualizacion (ibd, retencion, prestacion, etc.)
        **kwargs: Datos especificos del calculo

    Returns:
        dict: Estructura estandarizada para el widget
    """
    config = TIPOS_VISUALIZACION.get(tipo_visualizacion, TIPOS_VISUALIZACION['generic'])

    computation = {
        # Metadatos de visualizacion
        'tipo_visualizacion': tipo_visualizacion,
        'template': config.get('template', 'generic'),
        'titulo': kwargs.get('titulo', config.get('nombre', '')),

        # Formula y explicacion (siempre presente)
        'formula': kwargs.get('formula', ''),
        'explicacion': kwargs.get('explicacion', ''),

        # Indicadores KPI (badges/chips en el widget)
        'indicadores': kwargs.get('indicadores', []),
        # Ejemplo: [{'label': 'Dias', 'value': 30, 'color': 'info'}]

        # Pasos del calculo (para visualizacion detallada)
        'pasos': kwargs.get('pasos', []),
        # Ejemplo: [{'label': 'Base', 'value': 1000000, 'format': 'currency'}]

        # Base legal (para reglas con normativa)
        'base_legal': kwargs.get('base_legal', ''),
        'elemento_ley': kwargs.get('elemento_ley', ''),
        'articulos': kwargs.get('articulos', []),

        # Datos crudos para calculos adicionales si se necesitan
        'datos': kwargs.get('datos', {}),

        # IDs de lineas relacionadas (para trazabilidad)
        'line_ids': kwargs.get('line_ids', []),
        'acum_line_ids': kwargs.get('acum_line_ids', []),

        # Comparacion con periodo anterior
        'valor_anterior': kwargs.get('valor_anterior', None),
        'variacion': kwargs.get('variacion', None),

        # Timestamp
        'fecha_calculo': date.today().strftime('%Y-%m-%d'),
    }

    # Agregar campos opcionales segun tipo
    if config.get('mostrar_pasos'):
        computation['mostrar_pasos'] = True
    if config.get('mostrar_base_legal'):
        computation['mostrar_base_legal'] = True
    if config.get('mostrar_detalle'):
        computation['mostrar_detalle'] = True
    if config.get('mostrar_saldo'):
        computation['mostrar_saldo'] = True

    return computation


def crear_indicador(label, value, color='secondary', formato='text'):
    """
    Crea un indicador KPI para mostrar en el widget.

    Args:
        label: Etiqueta del indicador
        value: Valor a mostrar
        color: Color del badge (primary, secondary, success, warning, danger, info)
        formato: Formato del valor (text, currency, number, percentage)

    Returns:
        dict: Indicador formateado
    """
    return {
        'label': label,
        'value': value,
        'color': color,
        'formato': formato,
    }


def crear_paso_calculo(label, value, formato='currency', highlight=False, base_legal=None,
                       items=None, descripcion=None, formula=None, notas=None):
    """
    Crea un paso de calculo para mostrar en el widget.

    Args:
        label: Descripcion del paso (etiqueta corta)
        value: Valor del paso
        formato: Formato del valor (currency, number, text, percentage)
        highlight: Si True, resalta este paso como resultado final
        base_legal: Referencia legal opcional
        items: Lista de items detallados para expandir (opcional)
               Cada item: {'nombre': str, 'valor': float, 'formato': str, 'nota': str,
                          'esResta': bool, 'esSuma': bool, 'icono': str}
        descripcion: Explicacion del paso (texto largo)
        formula: Formula del calculo (texto)
        notas: Lista de notas adicionales [{'texto': str, 'icono': str}]

    Returns:
        dict: Paso de calculo formateado
    """
    paso = {
        'label': label,
        'value': value,
        'format': formato,
    }
    if highlight:
        paso['highlight'] = True
    if base_legal:
        paso['base_legal'] = base_legal
    if items:
        paso['items'] = items
    if descripcion:
        paso['descripcion'] = descripcion
    if formula:
        paso['formula_texto'] = formula
    if notas:
        paso['notas'] = notas
    return paso
