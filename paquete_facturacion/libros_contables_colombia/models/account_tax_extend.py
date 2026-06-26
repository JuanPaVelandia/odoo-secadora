# -*- coding: utf-8 -*-
"""
Extensión de account.tax para agregar campo de tipo de impuesto colombiano.
"""

from odoo import models, fields, api, _


class AccountTaxExtend(models.Model):
    _inherit = 'account.tax'

    # Campo para clasificar el tipo de impuesto colombiano
    l10n_co_tax_type = fields.Selection(
        string="Tipo Impuesto CO",
        selection=[
            ('iva', 'IVA'),
            ('retefuente', 'Retención en la Fuente'),
            ('reteiva', 'Retención de IVA'),
            ('reteica', 'Retención de ICA'),
            ('inc', 'Impuesto Nacional al Consumo'),
            ('other', 'Otro'),
        ],
        help="Clasificación del impuesto para reportes contables colombianos.",
        tracking=True,
    )

    @api.onchange('withholding_concept_id')
    def _onchange_withholding_concept_id(self):
        """Auto-asignar tipo de impuesto basado en el concepto de retención."""
        if self.withholding_concept_id and self.withholding_concept_id.concept_type:
            self.l10n_co_tax_type = self.withholding_concept_id.concept_type

    @api.model
    def _auto_assign_tax_type(self):
        """Método para asignar automáticamente el tipo a impuestos existentes."""
        # Impuestos con concepto de retención
        taxes_with_concept = self.search([
            ('withholding_concept_id', '!=', False),
            ('l10n_co_tax_type', '=', False),
        ])
        for tax in taxes_with_concept:
            if tax.withholding_concept_id.concept_type:
                tax.l10n_co_tax_type = tax.withholding_concept_id.concept_type

        # IVA: tarifa positiva y nombre contiene IVA/VAT
        iva_taxes = self.search([
            ('l10n_co_tax_type', '=', False),
            ('amount', '>', 0),
            ('withholding_concept_id', '=', False),
            '|', '|',
            ('name', 'ilike', 'IVA'),
            ('name', 'ilike', 'VAT'),
            ('name', 'ilike', '19%'),
        ])
        iva_taxes.write({'l10n_co_tax_type': 'iva'})

        # ReteICA: tarifa negativa y nombre contiene ICA
        reteica_taxes = self.search([
            ('l10n_co_tax_type', '=', False),
            ('amount', '<', 0),
            '|',
            ('name', 'ilike', 'ICA'),
            ('name', 'ilike', 'Industria'),
        ])
        reteica_taxes.write({'l10n_co_tax_type': 'reteica'})

        return True
