# -*- coding: utf-8 -*-

"""
REGLAS SALARIALES - PRESTACIONES SOCIALES
==========================================

Métodos extraídos de hr_rule_adapted.py
Incluye: Prima, Cesantías, Intereses, Vacaciones, Provisiones

Estructura:
- prestaciones_helpers.py: Métodos auxiliares (historial, acumulados, etc.)
- prestaciones_calculo.py: Cálculos base y trazabilidad
- prestaciones_pagos.py: Prima, Cesantías, Intereses, Retroactivos
- prestaciones_vacaciones.py: Vacaciones de contrato
- prestaciones_provisiones.py: Provisiones y saldos contables
- prestaciones_acumulados.py: Acumulados y contadores
"""

from odoo import models


class HrSalaryRulePrestaciones(models.AbstractModel):
    """
    Mixin para reglas de prestaciones sociales.

    Hereda de hr.salary.rule.prestaciones.helpers para métodos auxiliares.
    """

    _name = 'hr.salary.rule.prestaciones'
    _inherit = ['hr.salary.rule.prestaciones.helpers']
    _description = 'Métodos para Prestaciones Sociales'
