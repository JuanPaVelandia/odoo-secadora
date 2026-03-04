# -*- coding: utf-8 -*-
{
    'name': 'Liquidaciones de Compra - Secadora La Gran Colombia',
    'version': '18.0.1.0.0',
    'category': 'Operations',
    'summary': 'Liquidaciones de compra de arroz para agricultores',
    'description': """
        Módulo de Liquidaciones de Compra
        ==================================

        Funcionalidades:
        - Consolidación de pesajes de compra por agricultor
        - Deducciones automáticas (fletes, descargue, retenciones)
        - Cálculo de peso comercial desde análisis de laboratorio
        - Reporte PDF para soporte de facturación del agricultor
    """,
    'author': 'Secadora La Gran Colombia S.A.S',
    'depends': ['bascula', 'secadora_calidad', 'secadora_transporte', 'mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'views/precio_compra_views.xml',
        'views/tipo_deduccion_views.xml',
        'views/partner_views.xml',
        'views/liquidacion_views.xml',
        'views/pesaje_views.xml',
        'wizard/crear_liquidacion_wizard_views.xml',
        'views/menu_views.xml',
        'report/liquidacion_report.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
