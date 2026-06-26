# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Pre-migracion: Eliminar tablas, vistas y datos de modelos no usados
    antes de actualizar el modulo.

    Modelos a eliminar:
    - dian.uom.code (CSV comentado)
    - dian.tax.type (CSV comentado)
    - tax.adjustments.wizard (wizard poco usado)
    - lavish.reports (report_execute_query.py no importado)
    - sale.order.negotiation.line (sale_order.py comentado)
    """
    if not version:
        return

    _logger.info("Pre-migracion lavish_erp 1.6: Eliminando modelos no usados")

    # Lista de modelos a eliminar
    models_to_delete = [
        'dian.uom.code',
        'dian.tax.type',
        'tax.adjustments.wizard',
        'lavish.reports',
        'sale.order.negotiation.line',
        'lavish.confirm.wizard',
        'lavish.res.branch',
    ]

    for model_name in models_to_delete:
        table_name = model_name.replace('.', '_')

        # Verificar si la tabla existe
        cr.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = %s
            )
        """, (table_name,))
        table_exists = cr.fetchone()[0]

        if not table_exists:
            _logger.info(f"  Tabla {table_name} no existe, saltando...")
            continue

        _logger.info(f"  Eliminando modelo: {model_name}")

        # 1. Eliminar vistas asociadas
        cr.execute("""
            DELETE FROM ir_ui_view
            WHERE model = %s
        """, (model_name,))
        deleted_views = cr.rowcount
        if deleted_views:
            _logger.info(f"    - Eliminadas {deleted_views} vistas")

        # 2. Eliminar acciones de ventana
        cr.execute("""
            DELETE FROM ir_act_window
            WHERE res_model = %s
        """, (model_name,))
        deleted_actions = cr.rowcount
        if deleted_actions:
            _logger.info(f"    - Eliminadas {deleted_actions} acciones")

        # 3. Eliminar reglas de acceso
        cr.execute("""
            SELECT id FROM ir_model WHERE model = %s
        """, (model_name,))
        model_row = cr.fetchone()
        if model_row:
            model_id = model_row[0]

            cr.execute("""
                DELETE FROM ir_model_access WHERE model_id = %s
            """, (model_id,))
            deleted_access = cr.rowcount
            if deleted_access:
                _logger.info(f"    - Eliminados {deleted_access} registros de acceso")

            cr.execute("""
                DELETE FROM ir_rule WHERE model_id = %s
            """, (model_id,))
            deleted_rules = cr.rowcount
            if deleted_rules:
                _logger.info(f"    - Eliminadas {deleted_rules} reglas")

        # 4. Eliminar campos relacionados
        cr.execute("""
            DELETE FROM ir_model_fields WHERE model = %s
        """, (model_name,))
        deleted_fields = cr.rowcount
        if deleted_fields:
            _logger.info(f"    - Eliminados {deleted_fields} campos")

        # 5. Eliminar el modelo del registro
        cr.execute("""
            DELETE FROM ir_model WHERE model = %s
        """, (model_name,))
        if cr.rowcount:
            _logger.info(f"    - Eliminado registro del modelo")

        # 6. Eliminar la tabla
        cr.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
        _logger.info(f"    - Tabla {table_name} eliminada")

    # Eliminar campos de sale.order relacionados con negotiation (si existen)
    cr.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'sale_order'
        AND column_name LIKE 'negotiation%'
    """)
    negotiation_columns = [row[0] for row in cr.fetchall()]

    for col in negotiation_columns:
        _logger.info(f"  Eliminando columna sale_order.{col}")
        cr.execute(f"ALTER TABLE sale_order DROP COLUMN IF EXISTS {col} CASCADE")

    # Eliminar campos de account.move relacionados con negotiation (si existen)
    cr.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'account_move'
        AND column_name LIKE 'negotiation%'
    """)
    am_negotiation_columns = [row[0] for row in cr.fetchall()]

    for col in am_negotiation_columns:
        _logger.info(f"  Eliminando columna account_move.{col}")
        cr.execute(f"ALTER TABLE account_move DROP COLUMN IF EXISTS {col} CASCADE")

    # Eliminar tabla M2M de branch_ids en res_users
    # NOTA: Estas tablas solo contienen relaciones usuario-sucursal, NO datos de usuarios
    # Los usuarios en res_users NO se afectan
    m2m_tables = [
        'lavish_res_branch_res_users_rel',
        'res_users_lavish_res_branch_rel',
    ]
    for m2m_table in m2m_tables:
        cr.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = %s
            )
        """, (m2m_table,))
        if cr.fetchone()[0]:
            cr.execute(f"DROP TABLE IF EXISTS {m2m_table} CASCADE")
            _logger.info(f"  Eliminada tabla M2M: {m2m_table}")

    # Eliminar vistas especificas por xml_id
    views_to_delete = [
        'lavish_erp.view_order_form_inherit_negotiation',
        'lavish_erp.view_move_form_inherit_negotiation',
        'lavish_erp.lavish_menu_action_reports',
        'lavish_erp.list_reports',
        'lavish_erp.form_reports',
        'lavish_erp.lavish_menu_action_report_rl',
        'lavish_erp.reports_lavish',
        'lavish_erp.action_confirm_wizard',
        'lavish_erp.view_confirm_wizard_form',
        'lavish_erp.lavish_menu_action_branch',
        'lavish_erp.list_branch',
        'lavish_erp.form_branch',
        'lavish_erp.menu_branch',
    ]

    for xml_id in views_to_delete:
        cr.execute("""
            DELETE FROM ir_model_data WHERE name = %s AND module = 'lavish_erp'
        """, (xml_id.split('.')[-1],))
        if cr.rowcount:
            _logger.info(f"  Eliminado xml_id: {xml_id}")

    _logger.info("Pre-migracion lavish_erp 1.6 completada")
