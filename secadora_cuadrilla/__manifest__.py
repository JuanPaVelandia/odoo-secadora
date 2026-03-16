# -*- coding: utf-8 -*-
{
    'name': 'Liquidaciones de Cuadrilla - Secadora La Gran Colombia',
    'version': '18.0.1.0.0',
    'category': 'Operations',
    'summary': 'Liquidaciones de servicios de cuadrilla (cargue, descargue, empacada, etc.)',
    'description': """
        Módulo de Liquidaciones de Cuadrilla
        =====================================

        Funcionalidades:
        - Tarifas por servicio ($/kg según base de peso)
        - Liquidación por rango de fechas desde órdenes de servicio
        - Deducciones y anticipos
        - Reporte PDF de liquidación
    """,
    'author': 'Secadora La Gran Colombia S.A.S',
    'depends': ['bascula', 'mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'views/cuadrilla_tarifa_views.xml',
        'views/liquidacion_cuadrilla_views.xml',
        'wizard/wizard_views.xml',
        'views/menu_views.xml',
        'report/liquidacion_cuadrilla_report.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
