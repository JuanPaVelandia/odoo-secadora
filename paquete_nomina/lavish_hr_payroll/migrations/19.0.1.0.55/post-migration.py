"""Renombrar menu raiz Empleados -> Contratos en es/es_CO/es_419/en_US.

En v18 enterprise el menu raiz tenia name="Contracts" (es_CO="Contratos").
En v19 fue renombrado a name="Employees" (es_CO="Empleados"). Mantenemos el
xmlid pero forzamos el nombre v18 en todas las locales.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        UPDATE ir_ui_menu
        SET name = jsonb_build_object('en_US', 'Contratos', 'es', 'Contratos',
                                      'es_CO', 'Contratos', 'es_419', 'Contratos')
        WHERE id IN (
            SELECT res_id FROM ir_model_data
            WHERE module = 'hr_payroll' AND name = 'menu_hr_payroll_employees'
        )
    """)
    _logger.info("Menu raiz hr_payroll.menu_hr_payroll_employees renombrado a Contratos")
