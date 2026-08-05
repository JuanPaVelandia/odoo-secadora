# -*- coding: utf-8 -*-
from odoo import fields, models, Command


class AccountMove(models.Model):
    _inherit = 'account.move'

    l10n_co_exogenous_skip = fields.Boolean(
        string='Omitir en exógena',
        default=False,
        index=True,
        copy=False,
        tracking=True,
        help="Si está activo, este asiento se EXCLUYE COMPLETO de los reportes DIAN exógena.")
    l10n_co_exogenous_colaboracion_contract_id = fields.Many2one(
        'l10n_co.exogenous_colaboracion_contract',
        string='Contrato de colaboración (DIAN)',
        index=True, copy=False,
        help='Si el asiento completo pertenece a un contrato de colaboración. '
             'Al postearlo, propaga a las líneas que no tengan contrato propio.')

    def write(self, vals):
        res = super().write(vals)
        if 'l10n_co_exogenous_colaboracion_contract_id' in vals:
            for m in self:
                if m.l10n_co_exogenous_colaboracion_contract_id:
                    m.line_ids.filtered(
                        lambda l: not l.l10n_co_exogenous_colaboracion_contract_id
                    ).write({
                        'l10n_co_exogenous_colaboracion_contract_id': m.l10n_co_exogenous_colaboracion_contract_id.id
                    })
        return res

    def action_open_exogenous_distribution_wizard(self):
        """Abre el wizard de distribución exógena para todas las líneas de los asientos seleccionados."""
        line_ids = self.mapped('line_ids').ids
        return {
            'type': 'ir.actions.act_window',
            'name': 'Distribución Exógena',
            'res_model': 'l10n_co.exogenous_aml_distribution_wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_line_ids': [Command.set(line_ids)],
                'default_move_ids': [Command.set(self.ids)],
                'default_apply_mode': 'moves',
            },
        }
