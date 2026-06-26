# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AccountJournal(models.Model):
    """
    Extension of account.journal for ICA configuration by journal

    Permite configurar la ciudad para cálculo de ICA por diario,
    útil para empresas con múltiples sucursales en diferentes municipios.
    """
    _inherit = 'account.journal'

    # Ciudad para ICA del diario (override del cálculo automático)
    ica_city_id = fields.Many2one(
        'res.city',
        string='ICA Municipality',
        help='Municipality for ICA calculation. If set, overrides the automatic '
             'calculation based on company/partner city.'
    )
    use_journal_ica_city = fields.Boolean(
        string='Use Journal ICA City',
        default=False,
        help='If checked, use the journal ICA city instead of the automatic calculation.'
    )

    # Tarifa ICA por defecto del diario
    ica_tariff_id = fields.Many2one(
        'ica.tariff',
        string='Default ICA Tariff',
        domain="[('municipality_id', '=', ica_city_id)]",
        help='Default ICA tariff for this journal. If set, uses this tariff directly.'
    )

    @api.onchange('ica_city_id')
    def _onchange_ica_city_id(self):
        """Clear tariff when city changes"""
        if self.ica_city_id:
            self.use_journal_ica_city = True
            # Search for default tariff
            tariff = self.env['ica.tariff'].search([
                ('municipality_id', '=', self.ica_city_id.id),
                ('active', '=', True),
            ], limit=1)
            if tariff:
                self.ica_tariff_id = tariff
            else:
                self.ica_tariff_id = False
        else:
            self.use_journal_ica_city = False
            self.ica_tariff_id = False
