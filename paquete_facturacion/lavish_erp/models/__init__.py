# -*- coding: utf-8 -*-

# Base model extension
from . import base

# Account models
from . import account_journal
from . import account_move
from . import account_tax_group
from . import account_nomenclature_code

# Core Odoo extensions
from . import res_partner
from . import res_users
from . import product_category
from . import res_config_settings

# Location models
from . import res_city
from . import res_city_neighborhood

# DIAN models
from . import identification_type
from . import dian_type_code
from . import dian_uom_code

# Lavish parameter models
from . import lavish_holidays
from . import lavish_ciiu
from . import lavish_ica_tariffs
