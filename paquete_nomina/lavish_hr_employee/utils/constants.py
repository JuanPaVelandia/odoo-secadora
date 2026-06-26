# -*- coding: utf-8 -*-
"""
Constantes globales para el módulo de nómina
"""

from decimal import Decimal, getcontext

# Configuración de precisión decimal
getcontext().prec = 10

# Constantes de tiempo
DAYS_YEAR = 360
DAYS_YEAR_NATURAL = 365
DAYS_MONTH = 30

# Constantes de precisión
PRECISION_TECHNICAL = 10
PRECISION_DISPLAY = 0

# Constantes de jornada laboral
HOURS_PER_DAY = 8  # Por defecto si no están en parámetros anuales

# Factores de provisiones
FACTOR_VACACIONES = Decimal('0.0417')  # 4.17%
FACTOR_PRIMA = Decimal('0.0833')  # 8.33%
FACTOR_CESANTIAS = Decimal('0.0833')  # 8.33%
FACTOR_INTERESES = Decimal('0.12')  # 12%

# Límites salariales
SMMLV_TOPE_AUX_TRANSPORTE = 2  # 2 SMMLV
SMMLV_TOPE_INTEGRAL = 10  # 10 SMMLV para salario integral
