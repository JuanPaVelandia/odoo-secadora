# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Elimina vistas duplicadas antes de la actualización"""
    if not version:
        return

    _logger.info("Ejecutando pre-migración lavish_hr_employee 1.5 - Limpieza de vistas duplicadas")

    # Lista de IDs de vistas duplicadas que deben eliminarse
    duplicate_views = [
        'view_hr_conf_certificate_income_tree',
        'view_hr_conf_certificate_income_form',
        'view_hr_conf_certificate_income_search',
        'view_hr_certificate_income_header_tree',
        'view_hr_certificate_income_header_form',
        'view_hr_certificate_income_header_search',
    ]

    for view_name in duplicate_views:
        # Buscar la vista en ir_model_data
        cr.execute("""
            SELECT imd.id, imd.res_id, imd.module
            FROM ir_model_data imd
            WHERE imd.name = %s
            AND imd.model = 'ir.ui.view'
            AND imd.module = 'lavish_hr_employee'
        """, (view_name,))
        results = cr.fetchall()

        for imd_id, view_id, module in results:
            _logger.info(f"Eliminando vista duplicada: {view_name} (ID: {view_id}, module: {module})")

            # Primero eliminar vistas hijas que heredan de esta
            cr.execute("DELETE FROM ir_ui_view WHERE inherit_id = %s", (view_id,))

            # Eliminar la vista
            cr.execute("DELETE FROM ir_ui_view WHERE id = %s", (view_id,))

            # Limpiar ir_model_data
            cr.execute("DELETE FROM ir_model_data WHERE id = %s", (imd_id,))

    # También buscar vistas huérfanas por nombre que puedan existir
    orphan_view_patterns = [
        '%hr_conf_certificate_income%',
        '%hr_certificate_income_header%',
    ]

    for pattern in orphan_view_patterns:
        cr.execute("""
            SELECT v.id, v.name, imd.id as imd_id
            FROM ir_ui_view v
            LEFT JOIN ir_model_data imd ON imd.res_id = v.id AND imd.model = 'ir.ui.view'
            WHERE v.name LIKE %s
            AND (imd.module = 'lavish_hr_employee' OR imd.id IS NULL)
        """, (pattern,))
        orphans = cr.fetchall()

        for view_id, view_name, imd_id in orphans:
            _logger.info(f"Eliminando vista huérfana: {view_name} (ID: {view_id})")
            cr.execute("DELETE FROM ir_ui_view WHERE inherit_id = %s", (view_id,))
            cr.execute("DELETE FROM ir_ui_view WHERE id = %s", (view_id,))
            if imd_id:
                cr.execute("DELETE FROM ir_model_data WHERE id = %s", (imd_id,))

    # Limpiar ir_act_window_view duplicados
    _logger.info("Limpiando ir_act_window_view duplicados...")
    cr.execute("""
        DELETE FROM ir_act_window_view
        WHERE id IN (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY act_window_id, view_mode
                    ORDER BY id DESC
                ) as rn
                FROM ir_act_window_view
            ) t
            WHERE t.rn > 1
        )
    """)
    deleted = cr.rowcount
    if deleted:
        _logger.info(f"Eliminados {deleted} registros duplicados de ir_act_window_view")

    _logger.info("Limpieza de vistas duplicadas completada")
