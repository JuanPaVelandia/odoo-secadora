# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Elimina constraint validated_certificate antes de la actualización"""
    _logger.info("Ejecutando pre-migración lavish_hr_employee 1.1.1")

    # Eliminar constraint de foreign key de validated_certificate
    cr.execute("""
        ALTER TABLE res_company
        DROP CONSTRAINT IF EXISTS res_company_validated_certificate_fkey
    """)
    _logger.info("Constraint res_company_validated_certificate_fkey eliminado")

    # Limpiar la columna si tiene datos incompatibles (varchar vs integer)
    cr.execute("""
        SELECT data_type FROM information_schema.columns
        WHERE table_name = 'res_company' AND column_name = 'validated_certificate'
    """)
    result = cr.fetchone()
    if result and result[0] != 'character varying':
        _logger.info(f"Columna validated_certificate es {result[0]}, eliminando para recrear como varchar")
        cr.execute("""
            ALTER TABLE res_company DROP COLUMN IF EXISTS validated_certificate
        """)
        _logger.info("Columna validated_certificate eliminada, será recreada por Odoo")
