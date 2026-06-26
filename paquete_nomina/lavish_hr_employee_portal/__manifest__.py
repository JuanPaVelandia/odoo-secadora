# -*- coding: utf-8 -*-
{
    'name': "Portal de Empleados",
    'summary': """
        Portal web para empleados - Consulta de nómina, solicitudes y certificados""",
    'description': """
        Portal de Autoservicio para Empleados
        =======================================

        Este módulo proporciona un portal web completo para los empleados donde pueden:

        * Consultar sus desprendibles de pago (nómina)
        * Solicitar ausencias y permisos
        * Solicitar dotación y EPP (Elementos de Protección Personal)
        * Consultar certificados médicos
        * Generar certificados laborales
        * Solicitar certificados de ingresos y retenciones
        * Solicitar préstamos
        * Ver información personal y de contrato

        El portal está diseñado con Bootstrap 5 y proporciona una interfaz moderna
        y responsive para que los empleados accedan desde cualquier dispositivo.
    """,
    'author': 'Lavish S.A.S',
    'category': 'Human Resources/Portal',
    'version': '19.0.1.1',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'portal',
        'website',
        'lavish_hr_employee',
        'lavish_hr_payroll',
    ],
    'data': [
        # Data
        'data/hr_portal_sequences.xml',

        # Security
        'security/portal_security.xml',
        'security/ir.model.access.csv',

        # Views
        'views/hr_employee_portal_views.xml',

        # Templates
        'templates/employee_portal_templates.xml',
        'templates/portal_profile_chatter_tabs.xml',
        'templates/employee_portal_simulation.xml',

        # Menus
        'views/portal_menus.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            # Custom CSS para el portal
            'lavish_hr_employee_portal/static/src/css/portal_employee.css',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
