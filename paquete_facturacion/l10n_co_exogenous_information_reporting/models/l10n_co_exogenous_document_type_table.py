# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError, ValidationError, AccessError, RedirectWarning

_logger = logging.getLogger(__name__)

class L10ncoExogenousDocumentTypeTable(models.Model):
    _name = "l10n_co.exogenous_document_type_table"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Template for the creation of the tables to be used per format"


    @api.constrains('name')
    def _check_unique_name(self):
        for record in self:
            if self.search_count([('name', '=', record.name)]) > 1:
                raise ValidationError(_("The name must be unique"))

    name = fields.Char(string='Name', tracking=True)
    active = fields.Boolean(string='Active', default=True, tracking=True)
    company_id = fields.Many2one(
        comodel_name='res.company', string='Company', default=lambda self: self.env.company.id)