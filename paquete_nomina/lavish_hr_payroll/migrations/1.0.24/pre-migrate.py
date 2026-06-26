# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Pre-migracion: Eliminar campos payroll_electronic y payroll_peoplepass
    de res_company.

    Estos campos no se usan y fueron eliminados del modelo.
    """
    if not version:
        return

    _logger.info("Pre-migracion lavish_hr_payroll 1.0.24: Limpiando campos no usados")

    # Campos a eliminar de res_company
    columns_to_drop = [
        'payroll_electronic_operator',
        'payroll_electronic_username_ws',
        'payroll_electronic_password_ws',
        'payroll_electronic_company_id_ws',
        'payroll_electronic_account_id_ws',
        'payroll_electronic_service_ws',
        'payroll_peoplepass_journal_id',
        'payroll_peoplepass_debit_account_id',
        'payroll_peoplepass_credit_account_id',
    ]

    for column in columns_to_drop:
        # Verificar si la columna existe
        cr.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.columns
                WHERE table_name = 'res_company' AND column_name = %s
            )
        """, (column,))
        column_exists = cr.fetchone()[0]

        if column_exists:
            _logger.info(f"  Eliminando columna res_company.{column}")
            cr.execute(f"ALTER TABLE res_company DROP COLUMN IF EXISTS {column} CASCADE")

    # Limpiar ir_model_fields
    cr.execute("""
        DELETE FROM ir_model_fields
        WHERE model = 'res.company'
          AND name IN %s
    """, (tuple(columns_to_drop),))
    deleted_fields = cr.rowcount
    if deleted_fields:
        _logger.info(f"  Eliminados {deleted_fields} registros de ir_model_fields")

    # Limpiar ir_model_data relacionados
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE model = 'ir.model.fields'
          AND name LIKE '%payroll_electronic%'
          AND module = 'lavish_hr_payroll'
    """)
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE model = 'ir.model.fields'
          AND name LIKE '%payroll_peoplepass%'
          AND module = 'lavish_hr_payroll'
    """)

    _logger.info("Pre-migracion lavish_hr_payroll 1.0.24 completada")
