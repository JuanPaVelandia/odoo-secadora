# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Elimina vistas cacheadas con campos obsoletos antes de la actualización"""
    if not version:
        return

    _logger.info("Ejecutando pre-migración lavish_hr_payroll 1.0.12")

    # Buscar el ID de la vista por su external_id
    cr.execute("""
        SELECT res_id FROM ir_model_data
        WHERE module = 'lavish_hr_payroll'
        AND name = 'hr_payroll_res_partner_inherit'
        AND model = 'ir.ui.view'
    """)
    result = cr.fetchone()
    if result:
        view_id = result[0]
        _logger.info(f"Encontrada vista hr_payroll_res_partner_inherit con ID {view_id}")

        # Eliminar la vista
        cr.execute("DELETE FROM ir_ui_view WHERE id = %s", (view_id,))
        _logger.info("Vista eliminada")

        # Eliminar la referencia en ir_model_data
        cr.execute("""
            DELETE FROM ir_model_data
            WHERE module = 'lavish_hr_payroll'
            AND name = 'hr_payroll_res_partner_inherit'
        """)
        _logger.info("Referencia ir_model_data eliminada")
    else:
        _logger.info("Vista hr_payroll_res_partner_inherit no encontrada por external_id")

    # También buscar cualquier vista res.partner con el campo problemático
    cr.execute("""
        SELECT id, name FROM ir_ui_view
        WHERE model = 'res.partner'
        AND arch_db::text LIKE '%dian_obligation_type_ids%'
    """)
    problematic_views = cr.fetchall()
    for view_id, view_name in problematic_views:
        _logger.info(f"Eliminando vista problemática: {view_name} (ID: {view_id})")
        cr.execute("DELETE FROM ir_ui_view WHERE id = %s", (view_id,))

    if problematic_views:
        _logger.info(f"Eliminadas {len(problematic_views)} vistas con dian_obligation_type_ids")
