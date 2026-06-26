# -*- coding: utf-8 -*-
"""
VACACIONES EN LIQUIDACION
=========================
Metodo de pago para regla salarial de vacaciones en liquidacion de contrato.

Codigos de reglas salariales que usan estos metodos:
- VACCONTRATO: _vaccontrato()
"""
from odoo import models, api
import logging

_logger = logging.getLogger(__name__)


class HrSalaryRuleVacaciones(models.AbstractModel):
    """
    Servicio para calculo de vacaciones en liquidacion de contrato.

    Metodos de pago (llamados por reglas con amount_select='concept'):
    - _vaccontrato(): Codigo VACCONTRATO
    """
    _name = 'hr.salary.rule.prestaciones.liquidacion'
    _inherit = 'hr.salary.rule.prestaciones.liquidacion'

    def _vaccontrato(self, localdict):
        """
        VACACIONES EN LIQUIDACION - Codigo regla: VACCONTRATO

        Formula: (Base * Dias) / 720
        Considera: Dias acumulados pendientes de disfrute

        CORREGIDO Bug #4: En liquidaciones, calcula ajuste (total - provisiones - pagos).

        Returns:
            tuple: (amount, qty, rate, name, log, data)
        """
        slip = localdict['slip']

        # Parametros del concepto VACCONTRATO
        promedio_info = self._get_mesesapromediar(localdict, 'vacaciones')
        params_prestacion = {
            'diasperiodo': 720,
            'diasapagar': 15,
            'mesesapromediar': promedio_info['mesesapromediar'],
            'promediar_salario': promedio_info['promediar_salario'],
            'cambio_salario': promedio_info['cambio_salario'],
            'codigo_provision': 'PRV_VAC',
            'codigo_regla': 'VACCONTRATO',
        }
        params_prestacion.update(self._get_cuentas_contables('VACCONTRATO', 'PRV_VAC'))

        # Determinar contexto segun estructura
        struct_process = slip.struct_id.process if slip.struct_id else 'nomina'
        context = 'liquidacion' if struct_process == 'contrato' else 'pago'

        # Sueldo y dias a pagar
        prestaciones_svc = self.env['hr.salary.rule.prestaciones']
        sueldo_info = prestaciones_svc._get_sueldo_dias_a_pagar(localdict, 'vacaciones')
        variable_base = prestaciones_svc._get_variable_base(localdict, 'vacaciones')

        # Promedio (considera no_promediar_sueldo_prestaciones)
        promedio = prestaciones_svc._compute_promedio(localdict, sueldo_info, variable_base, context)

        # Auxilio de transporte
        auxilio = prestaciones_svc._get_auxilio(localdict, 'vacaciones', promedio, sueldo_info)

        return self._build_calculo(
            localdict, 'vacaciones', params_prestacion,
            sueldo_info, variable_base, promedio, auxilio, context
        )
