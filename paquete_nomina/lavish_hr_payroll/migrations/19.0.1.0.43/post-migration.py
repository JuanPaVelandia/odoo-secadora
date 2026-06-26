# -*- coding: utf-8 -*-
"""
Restaura el nombre 'Lotes' en el menú de Liquidaciones.

En Odoo 19 enterprise la traducción es_CO del menú hr_payroll.menu_hr_payslip_run
viene como 'Periodos de nómina', lo que confunde a usuarios que vienen de v18
donde el menú se llamaba 'Lotes'. Forzamos el nombre en todos los idiomas.

También limpia 'A pagar' (huérfano: el menú base lo eliminó Odoo 19 enterprise
pero lavish_hr_payroll/views/menus.xml todavía intenta reparentarlo, dejándolo
sin acción y sin uso). Lo desactivamos para que no aparezca como item vacío.
"""
import logging
_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        UPDATE ir_ui_menu m
        SET name = jsonb_build_object('en_US', 'Lotes', 'es_CO', 'Lotes', 'es', 'Lotes')
        FROM ir_model_data d
        WHERE d.res_id = m.id
          AND d.model = 'ir.ui.menu'
          AND d.module = 'hr_payroll'
          AND d.name = 'menu_hr_payslip_run'
    """)
    if cr.rowcount:
        _logger.info("post-migration 19.0.1.0.43: nombre 'Lotes' restaurado en %s menú(s)", cr.rowcount)

    cr.execute("""
        UPDATE ir_ui_menu m
        SET active = false
        FROM ir_model_data d
        WHERE d.res_id = m.id
          AND d.model = 'ir.ui.menu'
          AND d.module = 'hr_payroll'
          AND d.name = 'menu_hr_payroll_employee_payslips_to_pay'
          AND m.action IS NULL
    """)
    if cr.rowcount:
        _logger.info("post-migration 19.0.1.0.43: 'A pagar' desactivado (era huérfano sin acción)")
