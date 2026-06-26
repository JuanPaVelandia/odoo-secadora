# -*- coding: utf-8 -*-

"""
MÓDULO DE REGLAS SALARIALES ORGANIZADAS
========================================

Este módulo contiene todos los métodos de cálculo de reglas salariales
organizados por categoría para mejor mantenibilidad.

Estructura:
- config_reglas: Constantes y utilidades globales
- base_fields: Punto central de exportación de todos los mixins
- basic: Salario básico y variantes
- aux: Auxilios de transporte y conectividad
- ibd_sss: IBD y Seguridad Social
- prestaciones_sociales: Base del mixin de prestaciones
- prestaciones_calculo: Cálculo base y trazabilidad
- prestaciones_pagos: Prima, Cesantías, Intereses, Retroactivos
- prestaciones_vacaciones: Vacaciones y liquidación
- prestaciones_provisiones: Provisiones y saldos contables
- prestaciones_acumulados: Acumulados y contadores
- retenciones: Retenciones en la fuente
- indemnizacion: Indemnización por terminación de contrato
- horas_extras: Horas extras y recargos
- otros: Métodos auxiliares y totales
"""

from . import config_reglas
from . import base_fields
from . import basic
from . import auxilios
from . import ibd_sss
from . import seguridad_social
from . import prestaciones_helpers
from . import prestaciones_sociales
from . import prestaciones_liquidacion
from . import vacaciones
from . import prestaciones_calculo
from . import prestaciones_pagos
from . import prestaciones_vacaciones
from . import prestaciones_provisiones
from . import prestaciones_acumulados
from . import prestaciones_consolidacion
from . import prestaciones_adjustment_builder
from . import prestaciones_detail
from . import prestaciones_provision_loader
from . import retenciones
from . import indemnizacion
from . import horas_extras
from . import otros

# Nota: Motor de flujo V2 movido a lavish_hr_payroll/models/services/
