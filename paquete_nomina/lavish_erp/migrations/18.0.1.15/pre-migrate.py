# -*- coding: utf-8 -*-
"""
Migracion para corregir typo en campo firs_name -> first_name
"""
import logging
from odoo.tools.sql import column_exists

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    has_firs_name = column_exists(cr, 'res_partner', 'firs_name')
    has_first_name = column_exists(cr, 'res_partner', 'first_name')

    if has_firs_name and has_first_name:
        # Ambas columnas existen: copiar datos de firs_name a first_name donde first_name este vacio
        _logger.info('Ambas columnas existen, copiando datos de firs_name a first_name')
        cr.execute("""
            UPDATE res_partner
            SET first_name = firs_name
            WHERE (first_name IS NULL OR first_name = '')
              AND firs_name IS NOT NULL AND firs_name != ''
        """)
        # Eliminar columna vieja
        _logger.info('Eliminando columna firs_name')
        cr.execute("ALTER TABLE res_partner DROP COLUMN firs_name")
        _logger.info('Migracion completada')

    elif has_firs_name and not has_first_name:
        # Solo existe firs_name: renombrar
        _logger.info('Renombrando columna firs_name a first_name en res_partner')
        cr.execute("""
            ALTER TABLE res_partner
            RENAME COLUMN firs_name TO first_name
        """)
        _logger.info('Columna renombrada exitosamente')

    else:
        _logger.info('Columna firs_name no existe, nada que migrar')
