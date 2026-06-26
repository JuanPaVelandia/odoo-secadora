# -*- coding: utf-8 -*-

from . import controllers
from . import models
from . import report
from . import wizard


def pre_init_hook(env):
    """Elimina vistas obsoletas que causan errores de carga"""
    env.cr.execute("""
        DELETE FROM ir_ui_view
        WHERE name LIKE '%test%payslip%'
        AND model = 'hr.payslip.employees'
    """)
    env.cr.execute("""
        DELETE FROM ir_model_data
        WHERE model = 'ir.ui.view'
        AND name LIKE '%test%'
        AND module = 'lavish_hr_payroll'
    """)