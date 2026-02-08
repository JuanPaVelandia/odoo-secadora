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
    'depends': ['base', 'contacts', 'stock', 'account'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequences.xml',
        'data/variedad_arroz_data.xml',
        'data/product_empaque_data.xml',
        'views/vehiculo_views.xml',
        'views/conductor_views.xml',
        'views/transportadora_views.xml',
        'views/variedad_arroz_views.xml',
        'views/orden_servicio_views.xml',
        'views/pesaje_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
