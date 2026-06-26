# -*- coding: utf-8 -*-
"""
Pre-migration script for lavish_hr_employee 1.22

Adds pay_transport_allowance column to hr_work_entry_type table.
This field determines if the work entry type should pay transport allowance.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    _logger.info("Pre-migrate 1.22: Adding pay_transport_allowance to hr_work_entry_type")

    # Check if table exists
    cr.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'hr_work_entry_type'
        )
    """)
    if not cr.fetchone()[0]:
        _logger.info("Table hr_work_entry_type does not exist, skipping")
        return

    # Check if column exists
    cr.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns
            WHERE table_name = 'hr_work_entry_type'
            AND column_name = 'pay_transport_allowance'
        )
    """)

    if not cr.fetchone()[0]:
        _logger.info("Adding column pay_transport_allowance to hr_work_entry_type")
        try:
            cr.execute("""
                ALTER TABLE hr_work_entry_type
                ADD COLUMN pay_transport_allowance BOOLEAN DEFAULT TRUE
            """)
            _logger.info("Column pay_transport_allowance added successfully")

            # Set pay_transport_allowance=FALSE for work entry types linked to
            # leave types that should NOT pay transport allowance
            # These are typically: vacations, unpaid leaves, suspensions
            cr.execute("""
                UPDATE hr_work_entry_type wet
                SET pay_transport_allowance = FALSE
                WHERE wet.code IN (
                    'VACDISFRUTADAS',
                    'VACATIONS_MONEY',
                    'LICENCIA_NO_REMUNERADA',
                    'INAS_INJU',
                    'SUSP_CONTRATO',
                    'SANCION',
                    'INAS_INJU_D'
                )
            """)
            updated = cr.rowcount
            _logger.info(f"Updated {updated} work entry types to NOT pay transport allowance")

        except Exception as e:
            _logger.warning(f"Error adding column pay_transport_allowance: {e}")
    else:
        _logger.info("Column pay_transport_allowance already exists, skipping")

    _logger.info("Pre-migrate 1.22: Completed")
