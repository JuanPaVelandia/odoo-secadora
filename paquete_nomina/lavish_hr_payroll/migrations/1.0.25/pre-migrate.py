# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Pre-migracion: Eliminar campos duplicados de hr_payslip_line.

    Campos eliminados:
    - line_type: Duplicado de category_type (ambos related a category_id.category_type)
    - period: Duplicado de period_id (Char vs Many2one)
    - commissioned: Campo sin uso
    """
    if not version:
        return

    _logger.info("Pre-migracion lavish_hr_payroll 1.0.25: Limpiando campos duplicados de hr_payslip_line")

    # Campos a eliminar de hr_payslip_line
    columns_to_drop = [
        'line_type',
        'period',
        'commissioned',
    ]

    for column in columns_to_drop:
        # Verificar si la columna existe
        cr.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.columns
                WHERE table_name = 'hr_payslip_line' AND column_name = %s
            )
        """, (column,))
        column_exists = cr.fetchone()[0]

        if column_exists:
            _logger.info(f"  Eliminando columna hr_payslip_line.{column}")
            cr.execute(f"ALTER TABLE hr_payslip_line DROP COLUMN IF EXISTS {column} CASCADE")

    # Limpiar ir_model_fields
    cr.execute("""
        DELETE FROM ir_model_fields
        WHERE model = 'hr.payslip.line'
          AND name IN %s
    """, (tuple(columns_to_drop),))
    deleted_fields = cr.rowcount
    if deleted_fields:
        _logger.info(f"  Eliminados {deleted_fields} registros de ir_model_fields")

    # Limpiar ir_model_data relacionados
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE model = 'ir.model.fields'
          AND (name LIKE '%line_type%' OR name LIKE '%commissioned%')
          AND module = 'lavish_hr_payroll'
    """)

    _logger.info("Pre-migracion lavish_hr_payroll 1.0.25 completada")
