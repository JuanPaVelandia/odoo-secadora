# -*- coding: utf-8 -*-
"""
Migración 2.1: Preparar tabla hr_contract_type
===============================================
Asegura que la columna contract_category exista antes de la actualización.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Pre-migración: Verificar y crear columna contract_category si no existe"""
    _logger.info("=== INICIO PRE-MIGRACIÓN 2.1: Preparar hr_contract_type ===")

    # Verificar si la columna contract_category existe
    cr.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'hr_contract_type' AND column_name = 'contract_category'
    """)

    if not cr.fetchone():
        _logger.info("Columna contract_category no existe, creándola...")
        cr.execute("""
            ALTER TABLE hr_contract_type
            ADD COLUMN contract_category VARCHAR
        """)
        _logger.info("Columna contract_category creada")
    else:
        _logger.info("Columna contract_category ya existe")

    _logger.info("=== FIN PRE-MIGRACIÓN 2.1 ===")
