# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError, ValidationError, AccessError, RedirectWarning

_logger = logging.getLogger(__name__)

class L10ncoExogenousFormatFieldsAccount(models.Model):
    _name = "l10n_co.exogenous_format_field_account"

    @staticmethod
    def _get_accumulated():
        return [('tax_base_amount', _('Balance')), (
        'credit', _('Credit')), ('debit', _('Debit')),(
        'base', _('Base'))]


    name = fields.Selection(string='Accumulated by', selection="_get_accumulated", default='balance')
    account_ids = fields.Many2many(comodel_name='account.account', string='Accounts')

    format_field_id = fields.Many2one(comodel_name="l10n_co.exogenous_format_field", string='Format Field')
    concept_id = fields.Many2one(comodel_name="l10n_co.exogenous_concept", string='Concept')