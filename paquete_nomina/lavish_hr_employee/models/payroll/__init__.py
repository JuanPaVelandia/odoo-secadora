# -*- coding: utf-8 -*-
# Estructuras de datos compartidas (utilidades Python puras)
from . import hr_payslip_constants
from . import hr_slip_data_structures
from . import hr_slip_utils

# NOTA: Los modelos de Odoo (hr_annual_parameters, hr_parameterization, etc.)
# se cargan desde models/__init__.py (versión completa).
# Este subpaquete es importado vía odoo.addons para constantes Python puras;
# no debe re-registrar modelos aquí para evitar doble definición de _name.

# NOTA: hr_slip_acumulacion contiene modelos de Odoo que dependen de
# lavish_hr_payroll y se cargan cuando ese módulo se instala
