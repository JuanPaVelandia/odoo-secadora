# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError, ValidationError, AccessError, RedirectWarning

_logger = logging.getLogger(__name__)

class L10ncoExogenousFormat(models.Model):
    _name = "l10n_co.exogenous_format"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Module for the creation of formats required for exogenous information"
    _rec_name = 'code'
    
    def _compute_display_name(self):
        for rec in self:
            name_format = rec.name or ''
            if len(name_format) > 100:
                name_format = name_format[0:100] + '...'
            rec.display_name = f'[{rec.code}] {name_format}'

    @api.constrains('name', 'code')
    def _check_unique_name_code(self):
        for record in self:
            if self.search_count([('name', '=', record.name), ('code', '=', record.code)]) > 1:
                raise ValidationError(_("Name and code must be unique"))


    name = fields.Char(string='Name', tracking=True)
    code = fields.Char(string='Code', tracking=True, size=4)
    active = fields.Boolean(string='Active', default=True, tracking=True)
    
    version = fields.Char(string='Version', tracking=True)
    appendix = fields.Char(string='Appendix', tracking=True)
    
    document_type_table_id = fields.Many2one(comodel_name='l10n_co.exogenous_document_type_table', string='Document Type Table', tracking=True)
    is_it_with_date_range = fields.Boolean(string = 'Is it with date range?', default = True)
    apply_concepts = fields.Boolean(string='Apply Concepts?', default=False)
    applying_smaller_amounts = fields.Boolean(string = 'Applying smaller amounts?', default = False)
    smaller_ammounts = fields.Monetary(string = 'Maximum amount', currency_field='company_currency_id', default = 0.0)
    company_id = fields.Many2one(
        comodel_name='res.company', string='Company', default=lambda self: self.env.company.id)

    company_currency_id = fields.Many2one(
        string='Company Currency',
        related='company_id.currency_id', readonly=True,
    )

