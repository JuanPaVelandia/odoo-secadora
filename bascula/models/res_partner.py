# -*- coding: utf-8 -*-

from odoo import models, fields


class ResPartner(models.Model):
    _inherit = 'res.partner'

    bultos_ids = fields.One2many(
        'secadora.registro.bultos',
        'cliente_id',
        string='Bultos Empacados',
    )
