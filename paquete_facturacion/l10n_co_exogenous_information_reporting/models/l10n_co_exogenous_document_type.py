# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError, ValidationError, AccessError, RedirectWarning

_logger = logging.getLogger(__name__)

class L10ncoExogenousDocumentType(models.Model):
    _name = "l10n_co.exogenous_document_type"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Template for the creation of detail tables of document types required for exogenous information formats."

    @api.constrains('name', 'code', 'type_document_id')
    def _check_unique_name(self):
        for record in self:
            if self.search_count([('name', '=', record.name), ('code', '=', record.code), ('type_document_id', '=', record.type_document_id.id)]) > 1:
                raise ValidationError(_("Name, code and document type must be unique"))

    name = fields.Char(string='Name', tracking=True)
    type_document_id = fields.Many2one(comodel_name='l10n_latam.identification.type', string='Document type', tracking=True)
    active = fields.Boolean(string='Active', default=True, tracking=True)
    code = fields.Char(string='Code', tracking=True, size=2)
    document_type_table_ids = fields.Many2many(comodel_name="l10n_co.exogenous_document_type_table", relation="l10n_co_exogenous_document_type_table_rel", column1="document_type_id", column2="document_type_table_id", string='Tables')

    company_id = fields.Many2one(
        comodel_name='res.company', string='Company', default=lambda self: self.env.company.id)