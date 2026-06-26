# -*- coding: utf-8 -*-
from odoo import models, fields, api


PARTNER_NAMES_ORDER = [
    ('first_last', 'Nombres Apellidos'),
    ('last_first', 'Apellidos Nombres'),
    ('last_first_comma', 'Apellidos, Nombres'),
]


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    partner_names_order = fields.Selection(
        PARTNER_NAMES_ORDER,
        string='Orden de nombres',
        default='first_last',
        config_parameter='partner_names_order',
        help='Define el orden en que se muestran los nombres de personas naturales:\n'
             '- Nombres Apellidos: Juan Carlos Perez Garcia\n'
             '- Apellidos Nombres: Perez Garcia Juan Carlos\n'
             '- Apellidos, Nombres: Perez Garcia, Juan Carlos'
    )
