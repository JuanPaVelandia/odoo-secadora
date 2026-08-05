# -*- coding: utf-8 -*-
from odoo import fields, models


class L10nCoExogenousColumnPreviewWizard(models.TransientModel):
    _name = 'l10n_co.exogenous_column_preview_wizard'
    _description = 'Preview de columnas del formato exógeno'

    format_setting_id = fields.Many2one(
        'l10n_co.exogenous_format_setting', string='Configuración')
    preview_html = fields.Html(string='Preview', sanitize=False)
