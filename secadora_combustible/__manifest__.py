# -*- coding: utf-8 -*-
{
    'name': 'Combustible (ACPM)',
    'version': '19.0.1.1.0',
    'category': 'Operations',
    'summary': 'Compras de ACPM por finca y campaña, a partir de las facturas de proveedor',
    'description': """
        Combustible (ACPM)
        ==================

        Control del ACPM comprado, por finca y campaña, sin tocar la
        contabilidad de las facturas.

        - Las compras entran marcando la línea de la factura de proveedor como
          ACPM, con sus galones y su tipo.
        - ACPM de finca: finca y campaña (la campaña se propone por la fecha
          de la factura). Al asignar la finca se corrige la distribución
          analítica de la línea (plan Punto operativo) conservando lo demás.
        - ACPM de logística: vehículo (equipo de Mantenimiento marcado como
          vehículo).
        - Resumen de galones y pesos por tipo, finca, campaña, vehículo, mes
          y proveedor.
    """,
    'author': 'Secadora La Gran Colombia S.A.S',
    'depends': ['account', 'maintenance', 'bascula', 'finca_labores'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/account_move_line_views.xml',
        'views/acpm_compra_views.xml',
        'views/account_move_views.xml',
        'views/maintenance_equipment_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
