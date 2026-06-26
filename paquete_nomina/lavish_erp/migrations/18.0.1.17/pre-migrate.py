# -*- coding: utf-8 -*-
"""
Migracion para eliminar vistas del modulo lavish_erp y sus herencias
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    _logger.info('Eliminando vistas heredadas del modulo lavish_erp')

    # Primero eliminar vistas que heredan de las vistas de lavish_erp
    cr.execute("""
        DELETE FROM ir_ui_view
        WHERE inherit_id IN (
            SELECT v.id FROM ir_ui_view v
            JOIN ir_model_data d ON d.res_id = v.id AND d.model = 'ir.ui.view'
            WHERE d.module = 'lavish_erp'
        )
    """)

    # Eliminar referencias de ir_model_data de las vistas heredadas
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE model = 'ir.ui.view'
        AND res_id NOT IN (SELECT id FROM ir_ui_view)
    """)

    _logger.info('Eliminando vistas del modulo lavish_erp')

    # Eliminar las vistas propias del modulo
    cr.execute("""
        DELETE FROM ir_ui_view
        WHERE id IN (
            SELECT res_id FROM ir_model_data
            WHERE module = 'lavish_erp' AND model = 'ir.ui.view'
        )
    """)

    # Eliminar referencias de ir_model_data de las vistas
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE module = 'lavish_erp' AND model = 'ir.ui.view'
    """)

    _logger.info('Migracion de vistas completada')
