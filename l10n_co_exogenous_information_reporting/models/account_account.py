# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountAccount(models.Model):
    _inherit = 'account.account'

    l10n_co_exo_is_mayor_valor = fields.Boolean(
        string='Mayor valor (exógena)',
        default=False,
        help="Marque si esta cuenta maneja valores de impuestos como mayor valor del costo/gasto. "
             "Se usa para filtrar en reportes exógenos")
    l10n_co_exo_is_retention = fields.Boolean(
        string='Retención (exógena)',
        default=False,
        help="Marque si esta cuenta maneja retenciones. "
             "Se usa para filtrar líneas de retención en reportes exógenos")
