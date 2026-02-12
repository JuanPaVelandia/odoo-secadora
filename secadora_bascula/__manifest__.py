# -*- coding: utf-8 -*-
{
    'name': 'Secadora Báscula - Integración Inventarios',
    'version': '18.0.2.0.0',
    'summary': 'Conecta el módulo de báscula con inventarios (stock)',
    'description': """
        Integración Báscula ↔ Inventarios
        ==================================

        - Crea pickings automáticos al completar pesajes (compra/venta)
        - Maneja arroz de terceros con consignación (owner_id)
        - Consume empaques del inventario al confirmar bultos
        - Ubicaciones especiales: Secado En Proceso, Prelimpieza
        - Smart buttons para navegar entre pesajes y pickings
    """,
    'category': 'Inventory/Inventory',
    'author': 'Secadora La Gran Colombia S.A.S',
    'depends': ['bascula', 'stock'],
    'data': [
        'data/res_groups_data.xml',
        'data/product_arroz_data.xml',
        'data/stock_location_data.xml',
        'views/stock_picking_views.xml',
        'views/pesaje_views.xml',
        'views/orden_servicio_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
