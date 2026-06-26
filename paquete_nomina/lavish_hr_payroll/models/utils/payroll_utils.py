# -*- coding: utf-8 -*-
"""
Utilidades centralizadas para cálculos de nómina colombiana
"""
from decimal import Decimal, ROUND_HALF_UP
import math

def round_payroll_amount(amount, decimals=0):
    """
    Redondea montos de nómina de forma consistente.

    Por defecto redondea a entero (sin decimales) para evitar descuadres contables.
    Usa Decimal para precisión.

    Args:
        amount: Monto a redondear (float, int o Decimal)
        decimals: Número de decimales (default 0 = entero)

    Returns:
        Decimal redondeado
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

def round_to_100(amount):
    """Redondea al múltiplo de 100 más cercano hacia arriba"""
    return int(math.ceil(float(amount) / 100.0)) * 100

def round_to_1000(amount):
    """Redondea al múltiplo de 1000 más cercano"""
    return round(float(amount), -3)
