# -*- coding: utf-8 -*-
{
    'name': 'Embolsado en Silobolsas',
    'version': '19.0.2.0.0',
    'category': 'Operations',
    'summary': 'Registro de llenado de silobolsas con arroz en proceso',
    'description': """
        Embolsado en Silobolsas - Secadora La Gran Colombia
        ===================================================

        Funcionalidades:
        - Historial de taras (peso vacío) por pareja tractor+tolvo
        - Registro ágil de viajes con peso lleno capturado de la báscula en vivo
        - Panel de silobolsas: peso acumulado, fechas de embolsado inicial y final
        - Descuento del arroz embolsado del contenedor del tablero
        - Consumo del insumo silobolsa del inventario al llenar cada bolsa
        - Análisis de laboratorio por secciones del silobolsa
        - Estimación de peso seco (doble descuento) en contenedores configurados
    """,
    'author': 'Secadora La Gran Colombia S.A.S',
    'depends': ['bascula', 'secadora_bascula', 'secadora_tablero', 'secadora_calidad', 'stock', 'mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'data/config_parameter_data.xml',
        'views/silobolsa_views.xml',
        'views/embolsado_viaje_views.xml',
        'views/embolsado_tara_views.xml',
        'views/sitio_muestra_views.xml',
        'views/posicion_arroz_views.xml',
        'views/analisis_lab_views.xml',
        'wizard/registrar_viaje_wizard_views.xml',
        'views/menu_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'secadora_embolsado/static/src/js/peso_embolsado_field.js',
            'secadora_embolsado/static/src/xml/tablero_grid_embolsado.xml',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
    'post_init_hook': '_crear_producto_silobolsa',
}
