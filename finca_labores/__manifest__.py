# -*- coding: utf-8 -*-
{
    'name': 'Labores de Finca',
    'version': '19.0.1.5.0',
    'category': 'Operations',
    'summary': 'Labores por contrato, jornales y trabajos de maquinaria por finca, con saldo por operador',
    'description': """
        Labores de Finca
        ================

        Reemplaza las hojas de Google "Consolidado" y "Fincas" de cada campaña.

        - Campañas (ej. 2026-2027) y dueño de cada finca
        - Catálogo de labores con su tarifa ($/ha, $/bulto, $/día...)
        - Labores por contrato: labor x cantidad x tarifa, repartida entre
          los operadores que la hicieron
        - Jornales por persona y periodo
        - Trabajos de maquinaria por equipo, con tope por tipo de equipo
        - Saldo por dueño y operador: trabajos menos los pagos registrados
          en contabilidad (account.payment)
        - Estado de cuenta en PDF por operador

        Es control operativo: no genera asientos contables.
    """,
    'author': 'Secadora La Gran Colombia S.A.S',
    'depends': ['bascula', 'account', 'mail', 'maintenance', 'maintenance_purchase_link'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'data/labor_data.xml',
        'views/campana_views.xml',
        'views/labor_views.xml',
        'views/lugar_views.xml',
        'views/res_partner_views.xml',
        'views/socio_views.xml',
        'views/contrato_views.xml',
        'views/jornal_views.xml',
        'views/maquinaria_trabajo_views.xml',
        'views/account_payment_views.xml',
        'views/movimiento_views.xml',
        'wizard/estado_cuenta_wizard_views.xml',
        'wizard/resumen_views.xml',
        'report/estado_cuenta_report.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
