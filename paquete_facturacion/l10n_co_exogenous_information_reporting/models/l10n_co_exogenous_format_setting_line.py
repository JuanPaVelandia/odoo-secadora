# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError, ValidationError, AccessError, RedirectWarning

_logger = logging.getLogger(__name__)

class L10ncoExogenousFormatSettingLine(models.Model):
    _name = "l10n_co.exogenous_format_setting_line"
    _description = "Model for the configuration of the concepts and categories for the exogenous reporting lines"

    concept_id = fields.Many2one(comodel_name='l10n_co.exogenous_concept', string='Concept')
    format_field_id = fields.Many2one(comodel_name='l10n_co.exogenous_format_field', string='Format Field')
    format_setting_id = fields.Many2one(comodel_name='l10n_co.exogenous_format_setting', string='Format Setting')
    apply_concepts = fields.Boolean(string='Apply Concepts', related='format_setting_id.apply_concepts', readonly=True)