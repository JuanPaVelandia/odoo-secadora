# -*- coding: utf-8 -*-
{
    'name': 'Báscula Secadora La Gran Colombia',
    'version': '18.0.1.0.0',
    'category': 'Operations',
    'summary': 'Módulo de pesaje para secadora de arroz',
    'description': """
        Módulo de Báscula para Secadora de Arroz
        =========================================

        Funcionalidades:
        - Registro de pesajes de entrada (compra de arroz)
        - Registro de pesajes de salida (venta/despacho)
        - Gestión de vehículos, conductores y transportadoras
        - Control de variedades de arroz
        - Doble pesada (bruto y tara)
        - Control de calidad (humedad, grano partido, impurezas)
    """,
    'author': 'Secadora La Gran Colombia S.A.S',
    'website': '',
    'depends': ['base', 'contacts', 'product'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'data/sequences.xml',
        'data/variedad_arroz_data.xml',
        'data/product_empaque_data.xml',
        'data/tipo_operacion_data.xml',
        'views/vehiculo_views.xml',
        'views/conductor_views.xml',
        'views/transportadora_views.xml',
        'views/variedad_arroz_views.xml',
        'views/lugar_views.xml',
        'views/tipo_operacion_views.xml',
        'views/servicio_regla_views.xml',
        'views/orden_servicio_views.xml',
        'views/pesaje_views.xml',
        'views/pesaje_report.xml',
        'views/res_config_settings_views.xml',
        'views/menu_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'bascula/static/src/js/peso_actual_field.js',
            'bascula/static/src/xml/peso_actual_field.xml',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
