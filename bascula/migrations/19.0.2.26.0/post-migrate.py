"""Recalcula los totales de bultos de las órdenes que tienen traslados.

Los totales son campos almacenados: cambiar el cómputo para que no cuente las
copias de traslado no basta, porque el valor viejo se queda escrito en la base
hasta que algo lo toque. Aquí se marcan para recálculo las órdenes afectadas.
"""
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    ordenes = env['secadora.orden.servicio'].search([
        ('registro_bultos_ids.trasladado_de_id', '!=', False),
    ])
    if not ordenes:
        _logger.info('No hay ordenes con traslados que recalcular.')
        return

    campos = env['secadora.orden.servicio']._fields
    env.add_to_compute(campos['total_bultos'], ordenes)
    env.add_to_compute(campos['peso_total_bultos'], ordenes)
    env.add_to_compute(campos['bultos_despachados'], ordenes)
    env.add_to_compute(campos['bultos_pendientes'], ordenes)
    env.add_to_compute(campos['peso_despachado'], ordenes)
    env.add_to_compute(campos['peso_pendiente'], ordenes)
    ordenes.flush_recordset()

    _logger.info('Ordenes con totales recalculados: %s (%s)',
                 len(ordenes), ordenes.mapped('name'))
