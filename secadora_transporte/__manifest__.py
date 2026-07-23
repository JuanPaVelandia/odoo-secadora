# -*- coding: utf-8 -*-
{
    'name': 'Transporte - Secadora La Gran Colombia',
    'version': '19.0.1.3.0',
    'category': 'Operations',
    'summary': 'Gestión de fletes y transporte de arroz',
    'description': """
        Módulo de Transporte para Secadora de Arroz
        ============================================

        Funcionalidades:
        - Registro de fletes entre fincas, bodegas y planta
        - Costos de transporte (por kg, por viaje, por bulto)
        - Vínculo con pesajes
        - Soporte cross-company (flete visible desde empresa origen y destino)
    """,
    'author': 'Secadora La Gran Colombia S.A.S',
    'depends': ['bascula', 'mail', 'account', 'custom_webviewlink'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'views/tarifa_flete_views.xml',
        'views/flete_views.xml',
        'views/orden_servicio_views.xml',
        'views/orden_servicio_report.xml',
        'views/pesaje_views.xml',
        'views/transportadora_views.xml',
        'views/partner_views.xml',
        'wizard/asociar_factura_wizard_views.xml',
        'wizard/imprimir_viajes_pagar_wizard_views.xml',
        'views/res_config_settings_views.xml',
        'views/account_move_views.xml',
        'views/viajes_por_pagar_report.xml',
        'views/tablero_transporte_views.xml',
        'views/menu_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'secadora_transporte/static/src/css/tablero_transporte.css',
            'secadora_transporte/static/src/xml/tablero_transporte.xml',
            'secadora_transporte/static/src/js/tablero_transporte.js',
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
