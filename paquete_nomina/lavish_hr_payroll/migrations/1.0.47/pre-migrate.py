# -*- coding: utf-8 -*-
"""
Migration 1.0.47: Add employee_id column to hr_payslip_rule_override

This migration adds the employee_id column which is a stored related field.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Add employee_id column to hr_payslip_rule_override table.
    """
    if not version:
        return

    _logger.info("Starting migration 1.0.47: Adding employee_id to hr_payslip_rule_override")

    # Check if column exists
    cr.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'hr_payslip_rule_override'
        AND column_name = 'employee_id'
    """)

    if cr.fetchone():
        _logger.info("Column employee_id already exists, skipping creation")
    else:
        _logger.info("Creating employee_id column...")
        cr.execute("""
            ALTER TABLE hr_payslip_rule_override
            ADD COLUMN IF NOT EXISTS employee_id INTEGER
        """)
        _logger.info("Column employee_id created")

    # Update employee_id from payslip_id relation
    _logger.info("Updating employee_id from payslip relation...")
    cr.execute("""
        UPDATE hr_payslip_rule_override ro
        SET employee_id = p.employee_id
        FROM hr_payslip p
        WHERE ro.payslip_id = p.id
        AND ro.employee_id IS NULL
    """)
    updated = cr.rowcount
    _logger.info(f"Updated {updated} records with employee_id")

    _logger.info("Migration 1.0.47 completed successfully")
