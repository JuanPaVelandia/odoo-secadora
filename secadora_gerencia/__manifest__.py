# -*- coding: utf-8 -*-
{
    'name': 'Gerencia - Secadora',
    'version': '19.0.1.1.0',
    'category': 'Operations',
    'summary': 'Reportes y tablero gerencial de la secadora',
    'description': """
        Módulo de Gerencia para la Secadora La Gran Colombia.
        - Menú Gerencia con los reportes de dirección
        - Reporte de producción por finca y lote (pivot + PDF)
        - Base para el dashboard gerencial
    """,
    'author': 'Secadora La Gran Colombia S.A.S',
    'depends': ['secadora_calidad'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
