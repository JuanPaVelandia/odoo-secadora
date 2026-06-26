# -*- coding: utf-8 -*-
"""
Migration 1.0.44 - Limpieza y extensión de licencia

Cambios:
- Eliminar tabla hr_payslip_line_accumulated_payroll_rel (campo Many2many eliminado)
- Extender fecha de expiración de la base de datos
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Pre-migration: Limpieza y extensión de licencia.
    """
    if not version:
        return

    # =========================================================================
    # 1. Extender fecha de expiración de la base de datos
    # =========================================================================
    _logger.info("Migracion 1.0.44: Extendiendo fecha de expiracion de la base de datos...")

    cr.execute("""
        UPDATE ir_config_parameter
        SET value = '2027-01-31'
        WHERE key = 'database.expiration_date'
    """)

    if cr.rowcount > 0:
        _logger.info("Fecha de expiracion actualizada a 2027-01-31")
    else:
        # Si no existe, crear el parámetro
        cr.execute("""
            INSERT INTO ir_config_parameter (key, value, create_uid, create_date, write_uid, write_date)
            VALUES ('database.expiration_date', '2027-01-31', 1, NOW(), 1, NOW())
            ON CONFLICT (key) DO UPDATE SET value = '2027-01-31', write_date = NOW()
        """)
        _logger.info("Parametro database.expiration_date creado con fecha 2027-01-31")

    # =========================================================================
    # 2. Eliminar tabla huérfana Many2many
    # =========================================================================
    _logger.info("Eliminando tabla huerfana hr_payslip_line_accumulated_payroll_rel...")

    cr.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'hr_payslip_line_accumulated_payroll_rel'
        )
    """)
    table_exists = cr.fetchone()[0]

    if table_exists:
        cr.execute("DROP TABLE IF EXISTS hr_payslip_line_accumulated_payroll_rel CASCADE")
        _logger.info("Tabla eliminada exitosamente.")
    else:
        _logger.info("Tabla no existe. Nada que eliminar.")

    _logger.info("Migracion 1.0.44 completada exitosamente.")
