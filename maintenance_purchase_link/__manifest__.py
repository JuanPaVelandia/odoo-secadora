{
    'name': 'Mantenimiento - Enlace con Facturas de Compra',
    'version': '18.0.2.0.0',
    'category': 'Maintenance',
    'summary': 'Asocia líneas de factura de compra a equipos y órdenes de mantenimiento',
    'description': """
        Permite al coordinador de mantenimiento asociar líneas de factura
        de compra clasificadas como "Mantenimiento" a equipos y órdenes de trabajo,
        brindando trazabilidad completa de costos de mantenimiento.
    """,
    'author': 'Secadora La Gran Colombia S.A.S',
    'license': 'LGPL-3',
    'depends': [
        'maintenance',
        'account',
        'purchase',
        'analytic',
        'bascula',
    ],
    'data': [
        'security/maintenance_security.xml',
        'security/ir.model.access.csv',
        'data/analytic_data.xml',
        'data/equipment_category_data.xml',
        'views/account_move_views.xml',
        'views/maintenance_equipment_views.xml',
        'views/maintenance_request_views.xml',
        'views/maintenance_cost_views.xml',
        'views/maintenance_horometro_views.xml',
        'wizards/assign_invoice_wizard_views.xml',
        'views/maintenance_menus.xml',
        'report/maintenance_cost_report.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
