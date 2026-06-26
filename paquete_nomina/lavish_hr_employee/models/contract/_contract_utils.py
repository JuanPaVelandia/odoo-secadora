# -*- coding: utf-8 -*-
"""
Utilidades compartidas para modelos de contrato.
Centraliza imports, constantes y funciones usadas por multiples archivos.
"""
import calendar
import logging

_logger = logging.getLogger(__name__)

# =============================================================================
# CONSTANTES DE PRECISION
# =============================================================================
PRECISION_TECHNICAL = 10
PRECISION_DISPLAY = 2

# =============================================================================
# MENSAJES DE ADVERTENCIA (usados principalmente en hr_contract.py)
# =============================================================================
CONTRACT_GROUP_ID_HELP = """
Este campo permite agrupar los contratos, segun se va a calcular la nomina.
Sirve para grupos que no sea por banco, centro de costo y/o ciudad de desempeno.
"""

ARL_ID_HELP = "ARL en el caso que el empleado sea independiente"

ANALYTIC_DISTRIBUTION_TOTAL_WARN = """: La suma de las distribuciones analiticas debe ser 100.0%%,
Valor actual: %s%%"""

CONTRACT_EXTENSION_NO_RECORD_WARN = """
Para prorrogar el contrato por favor registre una prorroga
"""

CONTRACT_EXTENSION_MAX_WARN = """
No es posible realizar una prorroga por un periodo inferior
a un ano despues de tener 3 o mas prorrogas
"""

NO_PARTNER_REF_WARN = """
No se encontro el numero de documento en el contacto
"""

IN_FORCE_CONTRACT_WARN = """
El empleado ya tiene un contrato activo: %s.
"""

NO_WAGE_HISTORY = """
El contrato %s no tiene un historial de salarios.
"""

MANY_WAGE_HISTORY = """
El contrato %s tiene %s cambios salariales en este rango %s a %s.
Solo se permite 1 por periodo.
"""

LAST_ONE = -1


# =============================================================================
# FUNCIONES COMPARTIDAS
# =============================================================================

def days360(start_date, end_date, method_eu=True):
    """
    Calcula el numero de dias entre dos fechas considerando meses de 30 dias.

    Metodo estandar para calculo de nomina colombiana (dias 360).

    Args:
        start_date: Fecha inicial
        end_date: Fecha final
        method_eu: True para metodo europeo (default), False para metodo US

    Returns:
        int: Numero de dias entre las fechas
    """
    start_day = start_date.day
    start_month = start_date.month
    start_year = start_date.year
    end_day = end_date.day
    end_month = end_date.month
    end_year = end_date.year

    # Ajuste del dia inicial
    if (start_day == 31 or
        (method_eu is False and start_month == 2 and
         (start_day == 29 or (start_day == 28 and not calendar.isleap(start_year))))):
        start_day = 30

    # Ajuste del dia final
    if end_day == 31:
        if method_eu is False and start_day != 30:
            end_day = 1
            if end_month == 12:
                end_year += 1
                end_month = 1
            else:
                end_month += 1
        else:
            end_day = 30

    # Febrero siempre se ajusta a 30
    if end_month == 2 and end_day in (28, 29):
        end_day = 30

    return (
        end_day + end_month * 30 + end_year * 360 -
        start_day - start_month * 30 - start_year * 360 + 1
    )
