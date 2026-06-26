# -*- coding: utf-8 -*-
"""
Migracion para eliminar modelos dian.type_code y dian.tax.type
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    # Eliminar registros de ir_model_data
    _logger.info('Eliminando registros de dian.type_code y dian.tax.type de ir_model_data')
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE model IN ('dian.type_code', 'dian.tax.type')
    """)

    # Eliminar registros de ir_model_fields
    _logger.info('Eliminando campos de dian.type_code y dian.tax.type')
    cr.execute("""
        DELETE FROM ir_model_fields
        WHERE model IN ('dian.type_code', 'dian.tax.type')
    """)

    # Eliminar registros de ir_model_access
    _logger.info('Eliminando permisos de dian.type_code y dian.tax.type')
    cr.execute("""
        DELETE FROM ir_model_access
        WHERE model_id IN (
            SELECT id FROM ir_model WHERE model IN ('dian.type_code', 'dian.tax.type')
        )
    """)

    # Eliminar modelos de ir_model
    _logger.info('Eliminando modelos dian.type_code y dian.tax.type de ir_model')
    cr.execute("""
        DELETE FROM ir_model
        WHERE model IN ('dian.type_code', 'dian.tax.type')
    """)

    # Eliminar tablas si existen
    _logger.info('Eliminando tablas dian_type_code y dian_tax_type')
    cr.execute("DROP TABLE IF EXISTS dian_type_code CASCADE")
    cr.execute("DROP TABLE IF EXISTS dian_tax_type CASCADE")

    _logger.info('Migracion completada')
