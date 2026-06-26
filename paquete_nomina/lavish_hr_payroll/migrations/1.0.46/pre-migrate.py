# -*- coding: utf-8 -*-
"""
Migration 1.0.46: Fix computed fields in hr_overtime

This migration updates stored computed fields that may be NULL for
records created before the compute functions were added or fixed.

Fields updated:
- date_only: Computed from date (Datetime -> Date)
- date_end_only: Computed from date_end
- total_hours: Sum of all overtime type columns
"""

import logging
from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Update computed fields in hr_overtime table.
    """
    if not version:
        return

    _logger.info("Starting migration 1.0.46: Fixing hr_overtime computed fields")

    # 1. Update date_only from date where NULL
    _logger.info("Updating date_only field for records where it's NULL...")
    cr.execute("""
        UPDATE hr_overtime
        SET date_only = DATE(date)
        WHERE date_only IS NULL AND date IS NOT NULL
    """)
    updated_date_only = cr.rowcount
    _logger.info(f"Updated {updated_date_only} records with date_only")

    # 2. Update date_end_only from date_end where NULL
    _logger.info("Updating date_end_only field for records where it's NULL...")
    cr.execute("""
        UPDATE hr_overtime
        SET date_end_only = DATE(date_end)
        WHERE date_end_only IS NULL AND date_end IS NOT NULL
    """)
    updated_date_end_only = cr.rowcount
    _logger.info(f"Updated {updated_date_end_only} records with date_end_only")

    # 3. Update total_hours where NULL or 0 but individual fields have values
    _logger.info("Updating total_hours field for records where it needs recomputation...")
    cr.execute("""
        UPDATE hr_overtime
        SET total_hours = (
            COALESCE(overtime_rn, 0) +
            COALESCE(overtime_ext_d, 0) +
            COALESCE(overtime_ext_n, 0) +
            COALESCE(overtime_eddf, 0) +
            COALESCE(overtime_endf, 0) +
            COALESCE(overtime_dof, 0) +
            COALESCE(overtime_rndf, 0) +
            COALESCE(overtime_rdf, 0) +
            COALESCE(overtime_rnf, 0)
        )
        WHERE total_hours IS NULL
           OR (total_hours = 0 AND (
               COALESCE(overtime_rn, 0) +
               COALESCE(overtime_ext_d, 0) +
               COALESCE(overtime_ext_n, 0) +
               COALESCE(overtime_eddf, 0) +
               COALESCE(overtime_endf, 0) +
               COALESCE(overtime_dof, 0) +
               COALESCE(overtime_rndf, 0) +
               COALESCE(overtime_rdf, 0) +
               COALESCE(overtime_rnf, 0)
           ) > 0)
    """)
    updated_total_hours = cr.rowcount
    _logger.info(f"Updated {updated_total_hours} records with total_hours")

    _logger.info("Migration 1.0.46 completed successfully")
