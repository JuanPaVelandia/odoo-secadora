"""Re-create EPP smart button view fresh.

La vista view_hr_payslip_run_form_epp cambia su inherit_id desde el form minimo
de v19 core (hr_payroll.hr_payslip_run_form) hacia el form completo de lavish
(lavish_hr_payroll.view_hr_payslip_run_full_form), porque solo este ultimo
tiene <div name="button_box"> donde el smart button EPP se ancla.

Odoo valida el xpath del arch nuevo CONTRA el inherit_id viejo (todavia en DB),
fallando con 'button_box no localizable'. Workaround: borramos el record
previo para que el load XML lo recree con el nuevo inherit_id atomicamente.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        DELETE FROM ir_ui_view
        WHERE id IN (
            SELECT res_id FROM ir_model_data
            WHERE module = 'lavish_hr_payroll'
              AND name = 'view_hr_payslip_run_form_epp'
        )
    """)
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE module = 'lavish_hr_payroll'
          AND name = 'view_hr_payslip_run_form_epp'
    """)
    _logger.info("Vista view_hr_payslip_run_form_epp eliminada para reanclar al full_form")
