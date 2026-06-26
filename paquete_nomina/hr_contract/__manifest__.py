# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# DECISIÓN ARQUITECTÓNICA (H-13):
# Odoo 19 renombró hr.contract → hr.version. Este fork mantiene hr.contract
# intencionalmente: el código propio tiene ~536 referencias y la migración
# implicaría un riesgo desproporcionado. Se mantiene el shim hasta que se
# planifique una migración controlada. No eliminar sin actualizar todas las
# referencias en lavish_hr_employee, lavish_hr_payroll, lavish_hr_social_security
# y l10n_co_e_payroll.

{
    'name': 'Employee Contracts',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Contracts',
    'sequence': 335,
    'description': """
Add all information on the employee form to manage contracts.
=============================================================

    * Contract
    * Place of Birth,
    * Medical Examination Date
    * Company Vehicle

You can assign several contracts per employee.
    """,
    'website': 'https://www.odoo.com/app/employees',
    'author': 'Odoo S.A.',
    'depends': ['hr'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/hr_contract_data.xml',
        'report/hr_contract_history_report_views.xml',
        'views/hr_contract_views.xml',
        'views/hr_employee_views.xml',
        'views/resource_calendar_views.xml',
        'views/res_config_settings_views.xml',
        'wizard/hr_departure_wizard_views.xml',
    ],
    'demo': ['data/hr_contract_demo.xml'],
    'installable': True,
    'application': True,
    'assets': {
        'web.assets_backend': [
            'hr_contract/static/src/**/*',
        ],
    },
    'license': 'LGPL-3',
}
