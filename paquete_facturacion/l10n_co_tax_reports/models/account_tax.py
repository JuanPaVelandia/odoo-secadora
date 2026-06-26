# -*- coding: utf-8 -*-
from odoo import models, fields, api


class AccountTax(models.Model):
    _inherit = 'account.tax'

    # Ubicación geográfica (para ICA municipal)
    l10n_co_state_id = fields.Many2one(
        'res.country.state',
        string='Departamento',
        domain="[('country_id.code', '=', 'CO')]",
        help='Departamento donde aplica este impuesto (principalmente para ICA)'
    )

    l10n_co_city_id = fields.Many2one(
        'res.city',
        string='Ciudad/Municipio',
        domain="[('state_id', '=', l10n_co_state_id)]",
        help='Ciudad donde aplica (importante para ICA municipal)'
    )

    # Actividades económicas CIIU
    l10n_co_activity_ids = fields.Many2many(
        'lavish.ciiu',
        'tax_activity_rel',
        'tax_id',
        'activity_id',
        string='Actividades CIIU',
        help='Actividades económicas a las que aplica este impuesto (modelo lavish.ciiu de lavish_erp)'
    )

    # Configuración de reportes
    l10n_co_report_code = fields.Char(
        'Código Casilla',
        help='Código de la casilla en el formulario DIAN (ej: "27", "42", etc.)'
    )

    l10n_co_form_type = fields.Selection([
        ('300', 'Form. 300 - IVA'),
        ('350', 'Form. 350 - ReteFuente'),
        ('ica', 'ICA Municipal'),
    ], string='Tipo Formulario')

    # Clasificación de retenciones
    l10n_co_is_withholding = fields.Boolean(
        'Es Retención',
        compute='_compute_is_withholding',
        store=True,
        help='Indica si este impuesto es una retención'
    )

    l10n_co_withholding_type = fields.Selection([
        ('renta', 'Retención Renta'),
        ('iva', 'Retención IVA'),
        ('ica', 'Retención ICA'),
    ], string='Tipo Retención')

    @api.depends('tributes')
    def _compute_is_withholding(self):
        """Identifica automáticamente si es retención según tributo DIAN"""
        for tax in self:
            tax.l10n_co_is_withholding = tax.tributes in ('05', '06', '07')


class AccountTaxGroup(models.Model):
    _inherit = 'account.tax.group'

    l10n_co_form_type = fields.Selection([
        ('300', 'Form. 300 - IVA'),
        ('350', 'Form. 350 - ReteFuente'),
        ('ica', 'ICA Municipal'),
    ], string='Tipo Formulario')

    l10n_co_report_section = fields.Char(
        'Sección Reporte',
        help='Sección del formulario donde se reporta'
    )
