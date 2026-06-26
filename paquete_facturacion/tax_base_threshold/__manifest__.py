# -*- coding: utf-8 -*-
{
    'name': 'Colombian Tax Base Threshold',
    'version': '19.0.2.6.0',
    'category': 'Accounting/Localizations',
    'summary': 'Colombian withholding taxes with UVT-based thresholds and progressive rates',
    'description': """
Colombian Tax Base Threshold
============================

Complete Colombian withholding tax management system including:

FEATURES:
---------
* Tax Parameters (UVT/SMMLV) by year
* Withholding Concepts:
  - Retención en la Fuente (Compras, Servicios, Honorarios, Salarios)
  - ReteIVA (Bienes, Servicios)
  - INC (Restaurantes, Telefonía)
  - ReteICA

* Rate Types:
  - Fixed Rate (e.g., IVA 19%, Servicios 4%)
  - By Contributor Type (Declarant 2.5% / Non-Declarant 3.5%)
  - Progressive Brackets (Salary withholding table Art. 383 E.T.)

* Automatic Threshold Validation:
  - Minimum base in UVT or fixed amount
  - Date-based rate selection
  - Partner contributor type detection

INCLUDED DATA (2023-2025):
--------------------------
* UVT Values: 2023 ($42,412), 2024 ($47,065), 2025 ($49,799)
* SMMLV Values: 2023, 2024, 2025
* Withholding Concepts with rates
* Salary progressive brackets (Art. 383 E.T.)
* Decreto 0572/2025 updates

LEGAL REFERENCES:
-----------------
* Estatuto Tributario (Art. 383, 392, 401, 437-1)
* Ley 2010 de 2019
* Ley 2277 de 2022
* Decreto 0572 de 2025
    """,
    'author': 'Donsson',
    'website': 'https://www.donsson.com',
    'depends': ['account', 'base', 'sale', 'purchase', 'base_address_extended', 'lavish_erp'],
    'data': [
        # Security
        'security/ir.model.access.csv',
        # Views
        'views/tax_general_parameter_views.xml',
        'views/withholding_concept_views.xml',
        'views/withholding_rate_views.xml',
        'views/tax_base_threshold_views.xml',
        'views/ica_tariff_views.xml',
        'views/account_tax_views.xml',
        'views/account_journal_views.xml',
        'views/sale_order_views.xml',
        'views/purchase_order_views.xml',
        'views/menu_views.xml',
        # Data
        'data/withholding_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
