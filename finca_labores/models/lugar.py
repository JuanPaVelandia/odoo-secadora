# -*- coding: utf-8 -*-

from odoo import models, fields


class SecadoraLugar(models.Model):
    _inherit = 'secadora.lugar'

    # Contacto y no compañía: company_id es siempre la operadora (ver
    # memory/company-id-es-la-operadora.md), y fincas como La Alianza no
    # tienen compañía propia.
    dueno_id = fields.Many2one(
        'res.partner',
        string='Dueño',
        help='Quién responde por las labores de esta finca. Las labores '
             'registradas en la finca se cargan a este dueño.',
    )
