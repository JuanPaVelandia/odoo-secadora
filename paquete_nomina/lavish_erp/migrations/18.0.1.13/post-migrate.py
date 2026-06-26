# -*- coding: utf-8 -*-
import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Asocia facturas existentes con su resolución DIAN basándose en el diario.
    Para facturas que ya tienen número, busca la resolución activa del diario.
    """
    if not version:
        return

    _logger.info("Migrando facturas a relación DIAN...")

    env = api.Environment(cr, SUPERUSER_ID, {})

    # Buscar facturas/documentos que tienen diario con control DIAN
    moves = env['account.move'].search([
        ('state', '=', 'posted'),
        ('dian_resolution_id', '=', False),
        ('journal_id.sequence_id.use_dian_control', '=', True),
    ])

    count = 0
    for move in moves:
        if move.journal_id.sequence_id:
            # Buscar resolución activa del diario
            resolution = env['ir.sequence.dian_resolution'].search([
                ('sequence_id', '=', move.journal_id.sequence_id.id),
                ('active_resolution', '=', True),
            ], limit=1)

            if resolution:
                move.dian_resolution_id = resolution.id
                count += 1

    _logger.info(f"Migración completada: {count} facturas actualizadas con resolución DIAN")
