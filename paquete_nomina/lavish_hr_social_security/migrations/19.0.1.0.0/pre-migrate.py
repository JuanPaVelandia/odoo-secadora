# -*- coding: utf-8 -*-
"""
Pre-migración 19.0.1.0.0
========================
Limpia referencias huérfanas a hr.contract antes de recrear foreign keys.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    _logger.info("=== INICIO PRE-MIGRACIÓN lavish_hr_social_security ===")

    tables_to_cleanup = [
        'hr_executing_social_security',
    ]

    for table_name in tables_to_cleanup:
        cr.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = %s
                  AND column_name = 'contract_id'
            )
            """,
            (table_name,),
        )
        if not cr.fetchone()[0]:
            _logger.info("Tabla/columna %s.contract_id no disponible, se omite limpieza", table_name)
            continue

        cr.execute(
            f"""
            DELETE FROM {table_name}
             WHERE contract_id IS NOT NULL
               AND NOT EXISTS (
                   SELECT 1
                     FROM hr_contract hc
                    WHERE hc.id = {table_name}.contract_id
               )
            RETURNING id
            """
        )
        updated_ids = cr.fetchall()
        if updated_ids:
            _logger.warning(
                "Se eliminaron %s registros huérfanos por contract_id en %s",
                len(updated_ids),
                table_name,
            )
        else:
            _logger.info("No se encontraron referencias huérfanas en %s.contract_id", table_name)

    _logger.info("=== FIN PRE-MIGRACIÓN lavish_hr_social_security ===")
