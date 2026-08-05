# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    l10n_co_exogenous_partner_id = fields.Many2one(
        'res.partner',
        string='Tercero (DIAN exógena)',
        help='Partner reportado como tercero cuando este diario se agrupa en formatos exógenos. '
             'Típico uso: para diarios bancarios indicar el partner del banco (BBVA, Bancolombia, etc.) '
             'que se reportará en formatos como 1019, 1008, 1009 al activar "Agrupar por diario".')
