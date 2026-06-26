# -*- coding: utf-8 -*-
"""
Extension de hr.contract.history - Agrega estado 'Finalizado Por Liquidar'.
"""
from odoo import models, fields

class HrContractHistory(models.Model):
    _inherit = 'hr.contract.history'

    state = fields.Selection(selection_add=[('finished', 'Finalizado Por Liquidar')],ondelete={"finished": "set null"})
