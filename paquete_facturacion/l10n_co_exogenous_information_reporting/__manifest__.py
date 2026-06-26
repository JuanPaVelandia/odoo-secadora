# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name' : 'L10n Co Exogenous Information Reporting',
'version': '19.0.1.0.0',
    'summary': 'This module allows the configuration to make the DIAN exogenous information reports previously called magnetic media.',
    'author': 'Autosas',
    'sequence': 10,
    'category': 'Accounting/Localizations/Account Reports',
    'depends': ['account', 'l10n_co'],
    "data": [
        "security/ir.model.access.csv",
        "data/l10n_co_exogenous_document_type_table_data.xml",
        "data/l10n_co_exogenous_document_type_data.xml",
        "data/l10n_co_exogenous_format_data.xml",
        "data/l10n_co_exogenous_concept_data.xml",
        "data/l10n_co_exogenous_format_field_data.xml",
        "views/l10n_co_exogenous_document_type_table_views.xml",
        "views/l10n_co_exogenous_document_type_views.xml",
        "views/l10n_co_exogenous_concept_views.xml",
        "views/l10n_co_exogenous_format_field_views.xml",
        "views/l10n_co_exogenous_format_views.xml",
        "views/l10n_co_exogenous_format_setting_views.xml",
        "views/menus.xml",
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
    'currency': 'USD',
    'price': 80.00,
    'external_dependencies': {
        'python': ['openpyxl']
    },
}
