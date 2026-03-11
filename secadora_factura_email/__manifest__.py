# -*- coding: utf-8 -*-
{
    'name': 'Facturas Electrónicas desde Correo',
    'version': '18.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Procesa facturas electrónicas colombianas (UBL/DIAN) recibidas por correo',
    'description': """
        Facturas Electrónicas desde Correo
        ====================================

        Funcionalidades:
        - Recepción automática de correos con facturas electrónicas vía fetchmail
        - Extracción de adjuntos ZIP con XML (UBL 2.1 DIAN) + PDF
        - Parseo automático del XML de factura electrónica colombiana
        - Creación de facturas de proveedor (account.move) en borrador
        - Búsqueda/creación automática de proveedores por NIT
        - Detección de duplicados por CUFE
        - Soporte para Facturas, Notas Crédito y Notas Débito
    """,
    'author': 'Secadora La Gran Colombia S.A.S',
    'depends': ['account', 'mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/cron_data.xml',
        'views/factura_email_views.xml',
        'wizard/reprocesar_wizard_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
