# -*- coding: utf-8 -*-
"""
Módulos de novedades de nómina
==============================

Modelos para gestión de novedades y procesos:
- hr_cesantias: Cesantías e intereses
- hr_loans: Préstamos y libranzas
- hr_novelties_different_concepts: Novedades de conceptos diferentes
- hr_novelties_independents: Novedades independientes
- hr_overtime: Horas extras y recargos
- hr_payslip_rule_override: Sobrescritura de reglas
- hr_salary_increase: Aumento salarial masivo
- hr_accumulated_payroll: Acumulados de nómina
- hr_payroll_posting: Contabilización de pagos
- hr_payroll_flat_file: Archivo plano de pagos
- hr_transfers_of_entities: Traslado de entidades
- hr_work_entry: Entradas de trabajo
- hr_payslip_worked_days: Días trabajados
- hr_period: Períodos de nómina
- hr_payslip_day: Días de nómina
"""


# NOTA H-04: hr_leave NO se importa desde este paquete.
# El archivo canónico es lavish_hr_payroll/models/hr_leave.py (importado en models/__init__.py).
# lavish_hr_payroll/models/novedades/hr_leave.py es una copia obsoleta/incompleta (3927 líneas
# vs 4205 líneas en el canónico) y NO debe activarse aquí para evitar doble registro del modelo hr.leave.
from . import hr_loans
from . import hr_novelties_different_concepts
from . import hr_novelties_independents
from . import hr_overtime
from . import hr_payslip_rule_override
from . import hr_salary_increase
from . import hr_accumulated_payroll
from . import hr_payroll_posting
from . import hr_payroll_flat_file
from . import hr_transfers_of_entities
from . import hr_work_entry
from . import hr_payslip_worked_days
from . import hr_period
from . import hr_payslip_day
