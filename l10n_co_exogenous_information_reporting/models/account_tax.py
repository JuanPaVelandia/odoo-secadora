# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountTax(models.Model):
    _inherit = 'account.tax'

    l10n_co_exo_is_mayor_valor = fields.Boolean(
        string='Mayor valor (exógena)',
        default=False,
        help="Marque si este impuesto se trata como mayor valor del costo/gasto "
             "y no como impuesto descontable. Se usa para filtrar en reportes exógenos")
    l10n_co_exo_is_retention = fields.Boolean(
        string='Retención (exógena)',
        default=False,
        help="Marque si este impuesto es una retención asociada. "
             "Se usa para filtrar líneas de retención en reportes exógenos")
