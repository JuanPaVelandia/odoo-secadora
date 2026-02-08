{
    'name': 'Secadora Báscula',
    'version': '18.0.1.0.0',
    'summary': 'Añade número de tiquete a las recepciones de inventario',
    'description': """
        Este módulo añade un campo personalizado 'Número de Tiquete' (x_numero_tiquete)
        al modelo stock.picking y lo muestra en la vista de formulario.
    """,
    'category': 'Inventory/Inventory',
    'author': 'User',
    'depends': ['stock'],
    'data': [
        'views/stock_picking_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
