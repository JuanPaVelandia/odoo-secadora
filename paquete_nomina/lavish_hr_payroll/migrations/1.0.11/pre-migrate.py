# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Elimina vistas cacheadas con campos obsoletos antes de la actualización"""
    if not version:
        return

    _logger.info("Ejecutando pre-migración lavish_hr_payroll 1.0.11")

    # Eliminar la vista que referencia dian_obligation_type_ids (campo que ya no existe)
    # arch_db es jsonb, usamos cast a text para buscar
    cr.execute("""
        DELETE FROM ir_ui_view
        WHERE name = 'res.partner'
        AND model = 'res.partner'
        AND arch_db::text LIKE '%dian_obligation_type_ids%'
    """)
    deleted = cr.rowcount
    if deleted:
        _logger.info(f"Eliminadas {deleted} vistas con campo dian_obligation_type_ids obsoleto")

    # Limpiar también la referencia en ir_model_data
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE module = 'lavish_hr_payroll'
        AND model = 'ir.ui.view'
        AND name = 'hr_payroll_res_partner_inherit'
    """)
    if cr.rowcount:
        _logger.info("Eliminada referencia ir_model_data para hr_payroll_res_partner_inherit")
