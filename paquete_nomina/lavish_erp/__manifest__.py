# -*- coding: utf-8 -*-
{
    'name': "lavish_erp",
    'summary': """
        lavish ERP""",
    'description': """
        .lavish ERP.
    """,
    'author': "Lavish S.A.S",
    'category': 'lavishERP',
    'version': '19.0.1.20',
    'external_dependencies': {
        'python': ['dateutil', 'lxml', 'pytz', 'requests', 'stdnum', 'xlsxwriter', 'xlwt'],
    },
    'application': True,
    "license": "AGPL-3",
    'post_init_hook': 'post_init_hook',
    'depends': ['base',
        'contacts',
        'account',
        'account_tax_python',
        'l10n_co',
        'base_address_extended',
        "purchase",
        "base_setup",
        "sale"],
    'assets': {
        'web.assets_backend': [
            'lavish_erp/static/scss/style.scss',
            'lavish_erp/static/src/views/widgets/**/*',
        ],
    },
    'data': [
        # Datos base de identificación y ubicación (orden: país → estado → ciudad)
        'data/res.country.csv',
        'data/res_country_state.xml',
        'data/res.city.csv',
        'data/res.city.postal.csv',
        'data/res.city.neighborhood.csv',
        'data/l10n_latam.identification.type.csv',
        'data/account.nomenclature.code.csv', 
        'data/lavish.ciiu.csv',
        # Datos financieros
        'data/res.bank.csv',
        'data/account_tax_group.xml',
        # Seguridad
        'security/ir.model.access.csv',
        'views/res_country_state.xml',
        'views/res_country_view.xml',
        'views/product_category_view.xml',
        'views/res_partner.xml',
        'views/res_users.xml',
        'views/journal.xml',
        'views/account_move_view.xml',
        'views/general_actions.xml',
        'views/dian_config_views.xml',
        'views/res_city_neighborhood_view.xml',
        'views/general_menus.xml',
        'views/ica_tariffs_view.xml',
        'views/res_config_settings_view.xml',
    ]
}
