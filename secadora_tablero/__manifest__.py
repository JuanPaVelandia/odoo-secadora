# -*- coding: utf-8 -*-
{
    'name': 'Tablero de Arroz en Planta',
    'version': '18.0.1.0.0',
    'category': 'Operations',
    'summary': 'Tablero Kanban para rastrear arroz en ubicaciones físicas de la planta',
    'description': """
        Tablero de Arroz en Planta - Secadora La Gran Colombia
        ======================================================

        Funcionalidades:
        - Tablero estilo Kanban para visualizar ubicación del arroz en planta
        - Auto-creación de tarjetas al completar pesaje de entrada
        - Arrastre entre columnas (Tolva, Silos, Bodega, etc.)
        - División de tarjetas cuando el arroz está en múltiples ubicaciones
        - Historial completo de movimientos para auditoría
    """,
    'author': 'Secadora La Gran Colombia S.A.S',
    'depends': ['bascula', 'secadora_calidad', 'mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'views/posicion_arroz_views.xml',
        'views/movimiento_arroz_views.xml',
        'views/sitio_muestra_views.xml',
        'views/pesaje_views.xml',
        'wizard/dividir_posicion_wizard_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
