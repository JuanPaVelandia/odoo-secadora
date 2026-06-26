# -*- coding: utf-8 -*-
from . import mixins
from . import builders

from . import reglas

# Estructuras de datos compartidas (utilidades Python puras)
from . import hr_slip_data_structures
from . import hr_slip_utils
# NOTA: hr_slip_constante y hr_slip_acumulacion contienen modelos de Odoo
# que dependen de lavish_hr_payroll y se cargan cuando ese módulo se instala

from . import (
    hr_payroll_hours_helper,
    hr_parameterization,
    hr_annual_parameters,
    hr_certificate_income_config,
    hr_salary_increase,
    hr_loan_category,
    hr_income_certificate_request,
    hr_loan_request,
    hr_loan_inherit,
    hr_employee_update_parent,
    hr_employee,
    hr_types_employee,
    contract,  # Carpeta con modelos de contrato divididos
    hr_contract_type,  # Extension hr.contract.type Ley 2466/2025
    hr_leave,
    hr_birthday_list,
    hr_labor_certificate_template,
    hr_skills,
    res_user,
    hr_retencion_service,
    epp_dotacion,
    employee,
    medical,
    hr_rule_adapted,
    res_config_settings_nomina,
    item_classification,  # Matriz de clasificacion de items
    hr_accounting_structure,  # Sistema flexible de construccion de cuentas contables
    services,  # Servicios de consultas consolidadas
    hr_deduction_priority,  # Prioridad de deducciones para limite 50%
    hr_certificate_income,
    hr_contract_concepts_updated,
    hr_contract_extender,
    hr_employee_report_curriculum,
    lavish_extender_tools,
    hr_lavish_extra_tool_prestaciones,
    hr_leave_type_level,
    hr_payroll_report_lavish,
    hr_payslip_flow_mixin,
    hr_payslip_line_review,
    hr_salary_history_report,
    hr_salary_rule_accounting,
    hr_slip_acumulacion,
)
