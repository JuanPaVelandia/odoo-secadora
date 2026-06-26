# -*- coding: utf-8 -*-
# Configuracion empresa
from . import res_company

# Tipos y catalogos DIAN (solo los que no existen en lavish_hr_employee)
from . import hr_type_note
from . import hr_payment_method
from . import hr_way_pay
from . import hr_accrued_rule
from . import hr_deduct_rule
from . import dian_rejection_glossary
from . import hr_contract_edi  # Extension de contrato para campos EDI

# Nomina electronica
from . import hr_payslip_edi
from . import hr_payslip_edi_line
from . import hr_payslip_edi_log
from . import hr_payslip_edi_run
from . import hr_payslip_edi_employee_summary
from . import hr_payslip_inherit
from . import nomina_xml_generator
