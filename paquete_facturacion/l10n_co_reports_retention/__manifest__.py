{
    'name': 'Colombia - Reports Retention Portal',
'version': '19.0.1.0.0',
    'description': """
        Portal de Certificados de Retención
        ====================================
        Permite a los usuarios del portal descargar certificados de retención:
        * Retención en ICA
        * Retención en IVA
        * Retención en Fuente
    """,
    'summary': 'Portal para descargar certificados de retención colombianos',
    'author': 'GarKeM',
    'license': 'LGPL-3',
    'category': 'Accounting/Localizations/Reporting',
    'depends': [
        'l10n_co',
        'portal',
        'l10n_co_reports'
    ],
    'data': [
        'views/portal_templates.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}