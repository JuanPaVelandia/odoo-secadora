# -*- coding: utf-8 -*-
"""
Módulos de nómina
=================

Estructura:
- hr_slip_constante: Modelo principal de nómina con campos
- hr_payslip_number: Secuenciación de nóminas
- hr_payroll_account_move: Contabilización de nómina
- hr_payslip_line: Extensión de líneas de nómina
- hr_slip: Lógica principal de cálculo
- hr_payslip_run: Lotes de nómina
- services/: Servicios de cálculo

NOTA: hr_payslip_constants, hr_slip_data_structures y hr_slip_acumulacion
      están en lavish_hr_employee (módulo base)
"""
from . import hr_slip_constante
from . import hr_payslip_number
from . import hr_payroll_account_move
from . import hr_payslip_line
from . import hr_slip
from . import hr_payslip_run
from . import services
