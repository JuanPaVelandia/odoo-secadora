# -*- coding: utf-8 -*-
{
    'name': 'Lavish: Nómina Electrónica DIAN',
    'version': '19.0.1.0',
    'category': 'Nómina',
    'license': 'OPL-1',
    'summary': 'Nómina Electrónica Colombia - Consolidado DIAN',
    'description': """
Lavish: Nómina Electrónica DIAN Colombia
=========================================

Módulo consolidado para la gestión de Nómina Electrónica según normativa DIAN.

Incluye:
- Generación de XML NominaIndividual y NominaIndividualDeAjuste
- Firma digital XAdES-EPES
- Comunicación SOAP con DIAN
- Gestión de documentos electrónicos (hr.payslip.edi)
- Lotes masivos de nómina electrónica
- Configuración de empresa para nómina electrónica
- Tipos de trabajador, contratos y reglas salariales DIAN
- Notificaciones por correo electrónico
- Reenvío y consulta de estado DIAN
    """,
    'author': 'Lavish S.A.S',
    'external_dependencies': {
        'python': ['cryptography', 'dateutil', 'lxml', 'pytz'],
    },
    'website': 'https://lavishsoft.co',
    'maintainer': 'Lavish S.A.S',
    'depends': [
        'hr',
        'hr_holidays',
        'hr_work_entry_holidays',
        'hr_payroll',
        'lavish_hr_employee',
        'lavish_hr_payroll',
    ],
    'data': [
        # Security
        'security/security.xml',
        'security/ir.model.access.csv',
        # Data
        'data/ir_sequence.xml',
        'data/hr_type_note_data.xml',
        'data/hr_payment_method_data.xml',
        'data/hr_way_pay_data.xml',
        'data/nomina_templates.xml',
        # Report must load before mail_template (mail_template referencia action_report_payslip_edi_electronic)
        'report/report_payslip_edi_electronic.xml',
        'data/mail_template.xml',
        'data/hr_accrued_rule_data.xml',
        'data/hr_deduct_rule_data.xml',
        'data/dian_rejection_glossary_data.xml',
        # Wizard (antes de vistas que los referencian)
        'wizard/hr_epayslips_by_employees_view.xml',
        'wizard/hr_payslip_edi_xml_preview_view.xml',
        'wizard/retry_wizard_view.xml',
        'wizard/run_warning_wizard_view.xml',
        'wizard/partial_adjustment_wizard_view.xml',
        'wizard/batch_adjustment_wizard_view.xml',
        # Views
        'views/res_company_view.xml',
        'views/hr_payslip_edi_view.xml',
        # Wizard que depende de menu_hr_payroll_edi_root (definido en hr_payslip_edi_view.xml)
        'wizard/selective_dian_wizard_view.xml',
        'views/hr_contract_edi_view.xml',
        'views/hr_type_note_view.xml',
        'views/hr_payment_method_view.xml',
        'views/hr_way_pay_view.xml',
        'views/hr_salary_rule_edi_view.xml',
        'views/hr_accrued_rule_view.xml',
        'views/hr_deduct_rule_view.xml',
        'views/dian_rejection_glossary_view.xml',
        'views/hr_payslip_edi_status_view.xml',
        # Data/Actions
        'data/ir_actions.xml',
    ],
    'demo': [],
    'pre_init_hook': 'pre_init_hook',
    'installable': True,
    'auto_install': False,
    'application': True,
}
