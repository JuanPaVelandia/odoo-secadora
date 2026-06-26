# -*- coding: utf-8 -*-
"""
Pre-migracion 19.0.43
=====================
Limpia referencias huerfanas a hr.contract en tablas con contract_id nullable
antes de que Odoo recree llaves foraneas durante el upgrade.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    _logger.info("=== INICIO PRE-MIGRACION lavish_hr_payroll 19.0.43 ===")

    cr.execute(
        """
        SELECT c.table_name
        FROM information_schema.columns c
        JOIN information_schema.tables t
          ON t.table_schema = c.table_schema
         AND t.table_name = c.table_name
        WHERE c.table_schema = 'public'
          AND c.column_name = 'contract_id'
          AND c.is_nullable = 'YES'
          AND t.table_type = 'BASE TABLE'
        ORDER BY c.table_name
        """
    )
    contract_tables = [row[0] for row in cr.fetchall()]

    for table_name in contract_tables:
        cr.execute(
            f"""
            UPDATE "{table_name}" t
               SET contract_id = NULL
             WHERE contract_id IS NOT NULL
               AND NOT EXISTS (
                   SELECT 1
                     FROM hr_contract hc
                    WHERE hc.id = t.contract_id
               )
            RETURNING id
            """
        )
        updated_ids = cr.fetchall()
        if updated_ids:
            _logger.warning(
                "Se limpiaron %s referencias huerfanas de contract_id en %s",
                len(updated_ids),
                table_name,
            )
        else:
            _logger.info("Sin referencias huerfanas en %s.contract_id", table_name)

    _logger.info("=== FIN PRE-MIGRACION lavish_hr_payroll 19.0.43 ===")
