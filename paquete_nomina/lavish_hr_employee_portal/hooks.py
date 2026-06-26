# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def pre_init_hook(cr):
    """
    Hook de pre-inicialización para limpiar vistas antiguas del portal

    Este hook se ejecuta ANTES de instalar el módulo y elimina:
    - Vistas del portal que puedan existir en el módulo anterior
    - Templates del portal antiguos
    - Menús del portal que ya no se usan

    Args:
        cr: Database cursor
    """
    _logger.info("=" * 80)
    _logger.info("Iniciando limpieza de vistas antiguas del portal...")
    _logger.info("=" * 80)

    # Lista de vistas a eliminar (por nombre exacto)
    vistas_a_eliminar = [
        'lavish_hr_employee.employee_portal_template',
        'lavish_hr_employee.portal_access_denied',
        'lavish_hr_employee.portal_error',
        'lavish_hr_employee.portal_no_employee',
        'lavish_hr_employee.portal_my_home_menu_employee',
        'lavish_hr_employee.employee_portal_simulation_selector',
    ]

    # Eliminar vistas por XML ID
    for vista_xml_id in vistas_a_eliminar:
        try:
            cr.execute("""
                DELETE FROM ir_ui_view
                WHERE id IN (
                    SELECT res_id FROM ir_model_data
                    WHERE module = 'lavish_hr_employee'
                    AND name = %s
                    AND model = 'ir.ui.view'
                )
            """, (vista_xml_id.split('.')[-1],))

            if cr.rowcount > 0:
                _logger.info(f"✓ Vista eliminada: {vista_xml_id}")
        except Exception as e:
            _logger.warning(f"✗ Error al eliminar vista {vista_xml_id}: {str(e)}")

    # Eliminar vistas por patrón de nombre (cualquier vista con "portal" en el nombre del módulo anterior)
    try:
        cr.execute("""
            DELETE FROM ir_ui_view
            WHERE id IN (
                SELECT res_id FROM ir_model_data
                WHERE module = 'lavish_hr_employee'
                AND model = 'ir.ui.view'
                AND name LIKE '%%portal%%'
            )
        """)
        if cr.rowcount > 0:
            _logger.info(f"✓ {cr.rowcount} vista(s) con 'portal' eliminadas del módulo anterior")
    except Exception as e:
        _logger.warning(f"✗ Error al eliminar vistas por patrón: {str(e)}")

    # Eliminar templates QWeb del portal
    try:
        cr.execute("""
            DELETE FROM ir_ui_view
            WHERE type = 'qweb'
            AND key LIKE '%%employee_portal%%'
            AND id IN (
                SELECT res_id FROM ir_model_data
                WHERE module = 'lavish_hr_employee'
            )
        """)
        if cr.rowcount > 0:
            _logger.info(f"✓ {cr.rowcount} template(s) QWeb del portal eliminados")
    except Exception as e:
        _logger.warning(f"✗ Error al eliminar templates QWeb: {str(e)}")

    # Eliminar menús del portal
    menus_a_eliminar = [
        'lavish_hr_employee.menu_hr_employee_portal_root',
        'lavish_hr_employee.menu_hr_employee_portal_simulation',
    ]

    for menu_xml_id in menus_a_eliminar:
        try:
            cr.execute("""
                DELETE FROM ir_ui_menu
                WHERE id IN (
                    SELECT res_id FROM ir_model_data
                    WHERE module = 'lavish_hr_employee'
                    AND name = %s
                    AND model = 'ir.ui.menu'
                )
            """, (menu_xml_id.split('.')[-1],))

            if cr.rowcount > 0:
                _logger.info(f"✓ Menú eliminado: {menu_xml_id}")
        except Exception as e:
            _logger.warning(f"✗ Error al eliminar menú {menu_xml_id}: {str(e)}")

    # Eliminar acciones del portal
    try:
        cr.execute("""
            DELETE FROM ir_act_url
            WHERE id IN (
                SELECT res_id FROM ir_model_data
                WHERE module = 'lavish_hr_employee'
                AND model = 'ir.actions.act_url'
                AND name LIKE '%%portal%%'
            )
        """)
        if cr.rowcount > 0:
            _logger.info(f"✓ {cr.rowcount} acción(es) URL del portal eliminadas")
    except Exception as e:
        _logger.warning(f"✗ Error al eliminar acciones URL: {str(e)}")

    # Eliminar datos relacionados en ir_model_data
    try:
        cr.execute("""
            DELETE FROM ir_model_data
            WHERE module = 'lavish_hr_employee'
            AND name LIKE '%%portal%%'
            AND model IN ('ir.ui.view', 'ir.ui.menu', 'ir.actions.act_url')
        """)
        if cr.rowcount > 0:
            _logger.info(f"✓ {cr.rowcount} registro(s) de metadatos del portal eliminados")
    except Exception as e:
        _logger.warning(f"✗ Error al eliminar metadatos: {str(e)}")

    _logger.info("=" * 80)
    _logger.info("Limpieza de vistas antiguas del portal completada")
    _logger.info("=" * 80)


def post_init_hook(cr, registry):
    """
    Hook de post-inicialización para verificar la instalación

    Args:
        cr: Database cursor
        registry: Odoo registry
    """
    _logger.info("=" * 80)
    _logger.info("Verificando instalación del módulo Portal de Empleados...")
    _logger.info("=" * 80)

    # Verificar que las vistas del nuevo módulo se instalaron correctamente
    try:
        cr.execute("""
            SELECT COUNT(*) FROM ir_ui_view
            WHERE id IN (
                SELECT res_id FROM ir_model_data
                WHERE module = 'lavish_hr_employee_portal'
                AND model = 'ir.ui.view'
            )
        """)
        count = cr.fetchone()[0]
        _logger.info(f"✓ {count} vista(s) del nuevo módulo instaladas correctamente")
    except Exception as e:
        _logger.error(f"✗ Error al verificar vistas: {str(e)}")

    # Verificar modelos
    try:
        cr.execute("""
            SELECT model FROM ir_model
            WHERE model IN ('hr.income.certificate.request', 'hr.loan.request')
        """)
        modelos = [row[0] for row in cr.fetchall()]
        _logger.info(f"✓ Modelos del portal registrados: {', '.join(modelos)}")
    except Exception as e:
        _logger.error(f"✗ Error al verificar modelos: {str(e)}")

    # Verificar controladores registrados
    _logger.info("✓ Controladores del portal disponibles en:")
    _logger.info("  - /my/employee")
    _logger.info("  - /my/employee/<id>?token=<token>")
    _logger.info("  - /my/employee/simulate")

    _logger.info("=" * 80)
    _logger.info("Instalación del Portal de Empleados completada exitosamente")
    _logger.info("=" * 80)


def uninstall_hook(cr, registry):
    """
    Hook de desinstalación para limpiar datos residuales

    Args:
        cr: Database cursor
        registry: Odoo registry
    """
    _logger.info("=" * 80)
    _logger.info("Desinstalando módulo Portal de Empleados...")
    _logger.info("=" * 80)

    # Advertencia: Los datos de solicitudes NO se eliminan
    _logger.warning("NOTA: Las solicitudes de certificados y préstamos NO se eliminan")
    _logger.warning("Los datos se mantienen en la base de datos para preservar el historial")

    # Limpiar tokens de acceso al portal (opcional)
    try:
        cr.execute("""
            UPDATE hr_employee
            SET portal_access_token = NULL,
                show_in_portal = FALSE
            WHERE portal_access_token IS NOT NULL
        """)
        if cr.rowcount > 0:
            _logger.info(f"✓ Tokens de acceso al portal limpiados ({cr.rowcount} empleados)")
    except Exception as e:
        _logger.warning(f"✗ Error al limpiar tokens: {str(e)}")

    _logger.info("=" * 80)
    _logger.info("Desinstalación completada")
    _logger.info("=" * 80)
