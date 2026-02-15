# -*- coding: utf-8 -*-
{
    'name': 'Calidad y Laboratorio - Secadora',
    'version': '18.0.1.0.0',
    'category': 'Operations',
    'summary': 'Análisis de calidad de arroz y peso comercial',
    'description': """
        Módulo de calidad y laboratorio para la Secadora La Gran Colombia.
        - Análisis de laboratorio con ~20 parámetros de calidad
        - Muestras múltiples (entrada, proceso, salida)
        - Peso comercial ajustado por humedad
        - Descuentos de peso por calidad
    """,
    'author': 'Secadora La Gran Colombia S.A.S',
    'depends': ['bascula', 'mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'data/descuento_calidad_data.xml',
        'data/origen_muestra_data.xml',
        'views/descuento_calidad_views.xml',
        'views/origen_muestra_views.xml',
        'views/analisis_lab_views.xml',
        'views/pesaje_views.xml',
        'views/orden_servicio_views.xml',
        'views/res_config_settings_views.xml',
        'views/menu_views.xml',
        'report/analisis_lab_report.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
