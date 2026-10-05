# -*- coding: utf-8 -*-
{
    'name': 'Secadora Báscula - Integración Inventarios',
    'version': '19.0.2.1.0',
    'summary': 'Conecta el módulo de báscula con inventarios (stock)',
    'description': """
        Integración Báscula ↔ Inventarios
        ==================================

        - Crea pickings automáticos al completar pesajes (compra/venta)
        - Maneja arroz de terceros con consignación (owner_id)
        - Inventario de empaques: entra por la factura de compra, sale al
          empacar bultos con empaque de la secadora y se cuadra por conteo
        - Ubicaciones especiales: Secado En Proceso, Prelimpieza
        - Smart buttons para navegar entre pesajes y pickings
    """,
    'category': 'Inventory/Inventory',
    'author': 'Secadora La Gran Colombia S.A.S',
    'depends': ['bascula', 'stock', 'account'],
    'data': [
        'data/res_groups_data.xml',
        'data/product_arroz_data.xml',
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/stock_location_data.xml',
        'views/stock_picking_views.xml',
        'views/stock_quant_views.xml',
        'views/pesaje_views.xml',
        'views/orden_servicio_views.xml',
        'views/empaque_views.xml',
    ],
    'post_init_hook': '_create_arroz_paddy',
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
