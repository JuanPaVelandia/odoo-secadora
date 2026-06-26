# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Limpia vistas huérfanas con campos DIAN que no existen"""
    if not version:
        return

    _logger.info("Ejecutando pre-migración lavish_hr_payroll 1.0.13")

    # Lista de campos DIAN que pueden estar en vistas huérfanas
    dian_fields = [
        'dian_obligation_type_ids',
        'dian_representation_type_id',
        'dian_fiscal_regime_id',
        'dian_fiscal_responsibility_ids',
        'dian_tributary_type_id',
        'dian_establishment_type_id',
    ]

    # Eliminar vistas de res.partner que referencian campos DIAN
    for field in dian_fields:
        cr.execute("""
            SELECT id, name FROM ir_ui_view
            WHERE model = 'res.partner'
            AND arch_db::text LIKE %s
        """, (f'%{field}%',))
        views = cr.fetchall()

        for view_id, view_name in views:
            _logger.info(f"Eliminando vista con campo {field}: {view_name} (ID: {view_id})")
            # Primero eliminar vistas hijas
            cr.execute("DELETE FROM ir_ui_view WHERE inherit_id = %s", (view_id,))
            # Luego eliminar la vista
            cr.execute("DELETE FROM ir_ui_view WHERE id = %s", (view_id,))

            # Limpiar ir_model_data
            cr.execute("""
                DELETE FROM ir_model_data
                WHERE model = 'ir.ui.view' AND res_id = %s
            """, (view_id,))

    # También limpiar la vista específica de este módulo si existe
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE module = 'lavish_hr_payroll'
        AND name = 'hr_payroll_res_partner_inherit'
    """)

    _logger.info("Limpieza de vistas DIAN completada")
