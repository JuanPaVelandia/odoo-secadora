# -*- coding: utf-8 -*-
from odoo import fields, models


class L10ncoExogenousFormatFieldOverride(models.Model):
    _name = "l10n_co.exogenous_format_field_override"
    _description = "Override por formato de las propiedades XSD de un format_field"
    _check_company_auto = True
    _order = "sequence asc, id"

    format_id = fields.Many2one('l10n_co.exogenous_format', required=True, ondelete='cascade', index=True,
        check_company=True)
    field_id = fields.Many2one('l10n_co.exogenous_format_field', required=True, ondelete='cascade', index=True,
        check_company=True)
    sequence = fields.Integer()
    xsd_type = fields.Char()
    xsd_pattern = fields.Char()
    xsd_required = fields.Boolean()
    max_length = fields.Integer()
    min_length = fields.Integer()
    xsd_min_value = fields.Char()
    xsd_max_value = fields.Char()
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    _uniq_format_field = models.Constraint(
        'UNIQUE(format_id, field_id)',
        'Solo puede haber un override por (formato, campo).')
