# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError, ValidationError, AccessError, RedirectWarning

_logger = logging.getLogger(__name__)

class L10ncoExogenousFormatFields(models.Model):
    _name = "l10n_co.exogenous_format_field"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Template for the creation of fields by format"
    _order = 'sequence asc, id'

    @staticmethod
    def _get_sources():
        return [('contact', _('Contact')), (
        'journal_items', _('Journal Items')),
        ('resolution', _('Resolution'))]

    name = fields.Text(string='Name', tracking=True)
    sequence = fields.Integer(string='Sequence')
    max_length = fields.Integer(string='Max Length', tracking=True)
    attribute = fields.Char(string='Attribute', tracking=True)
    source = fields.Selection(selection="_get_sources", string='Source', tracking=True)
    format_ids = fields.Many2many(comodel_name="l10n_co.exogenous_format", relation="l10n_co_exogenous_format_field_rel", column1="format_id", column2="field_id", string='Formats', tracking=True)
    active = fields.Boolean(string='Active', default=True, tracking=True)
    company_id = fields.Many2one(
        comodel_name='res.company', string='Company', default=lambda self: self.env.company.id)


    applies_to_company = fields.Boolean(
        string = 'Does it apply to companies?', 
        default = True,
        help="""
            If the field is selected it means that this field applies when the type of contact is a company, e.g. the company name, the check digit
        """)

    applies_to_contact = fields.Boolean(
        string = 'Does it apply to natural persons?', 
        default = True,
        help="""
            If the field is selected it means that this field applies when the type of contact is a natural person, e.g. the name, the last name
        """)

    is_unique_key = fields.Boolean(
        string = 'is it a unique key to format?', 
        default = False,        
        help="""
            If selected, it is used for the grouping of information by the fields that have this selected.
        """)

    format_applies_concepts = fields.Boolean(
        string = 'Format applies concepts?', 
        default = True,
        help="""
            If selected, it is used for the grouping of information by the fields that have this selected.
        """)
    
    field_odoo_id = fields.Many2one(comodel_name='ir.model.fields', string='Odoo Field', domain="[('model', '=', 'res.partner'), ('ttype', 'not in', ('one2many', 'many2many'))]")
    ttype = fields.Selection(related='field_odoo_id.ttype', readonly=True)
    relation = fields.Char(related='field_odoo_id.relation', readonly=True)
    
    field_odoo_internal_id = fields.Many2one(
        comodel_name='ir.model.fields', 
        string='Odoo relational field', 
        domain="[('model', '=', relation), ('ttype', 'not in', ('many2one' , 'one2many', 'many2many'))]")

    field_account_ids = fields.One2many(comodel_name='l10n_co.exogenous_format_field_account', inverse_name='format_field_id', string='Accounts')