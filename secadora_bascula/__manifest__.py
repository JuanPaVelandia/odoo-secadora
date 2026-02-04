{
    'name': 'Secadora Báscula',
    'version': '18.0.1.0.0',
    'summary': 'Integración de báscula para Secadora Gran Colombia',
    'description': '''
        Módulo para integrar la báscula Prometálicos con Odoo.
        - Agrega campos de tiquete y placa a recepciones
        - Preparado para integración con báscula
    ''',
    'author': 'Secadora Gran Colombia',
    'category': 'Inventory',
    'depends': ['stock'],
    'data': [
        'views/stock_picking_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
