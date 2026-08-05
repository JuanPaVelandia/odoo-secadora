# -*- coding: utf-8 -*-
from odoo import fields, models, Command


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    l10n_co_exogenous_format_field_id = fields.Many2one('l10n_co.exogenous_format_field',
        string='Columna exógena (manual)',
        check_company=True,
        help="Columna del formato DIAN a la que se debe ubicar esta línea. "
             "Si se fija, sobrescribe la detección automática por cuenta/impuesto.",
        index=True,
    )
    l10n_co_exogenous_concept_id = fields.Many2one('l10n_co.exogenous_concept',
        string='Concepto exógeno (manual)',
        check_company=True,
        help="Concepto DIAN asignado manualmente a la línea.",
        index=True,
    )
    l10n_co_exogenous_assignment_reason = fields.Char(
        string='Motivo asignación exógena',
        help="Razón de la asignación manual (ej: IVA mayor valor, colaboración empresarial)")
    l10n_co_exogenous_percentage = fields.Float(
        string='% a columna primaria',
        default=100.0,
        help="Porcentaje del valor que se distribuye a la columna primaria. "
             "El residuo (100 - %) se asigna a la columna secundaria si está definida. "
             "Uso típico: prorrateo IVA común/exento (Art. 490 E.T.)")
    l10n_co_exogenous_secondary_field_id = fields.Many2one('l10n_co.exogenous_format_field',
        string='Columna secundaria (residuo)',
        check_company=True,
        help="Columna a la que se asigna el residuo (100 - %) cuando se prorratea")
    l10n_co_exogenous_skip = fields.Boolean(
        string='Omitir en exógena',
        default=False,
        index=True,
        help="Si está activo, esta línea se EXCLUYE de los reportes DIAN exógena.")
    l10n_co_exogenous_colaboracion_contract_id = fields.Many2one(
        'l10n_co.exogenous_colaboracion_contract',
        string='Contrato de colaboración (DIAN)',
        index=True,
        help='Si la línea pertenece a un contrato de colaboración, se reporta en los formatos 5247-5252.')

    def action_open_exogenous_distribution_wizard(self):
        """Abre el wizard para asignar campos exógena a las líneas seleccionadas."""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Distribución Exógena',
            'res_model': 'l10n_co.exogenous_aml_distribution_wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_line_ids': [Command.set(self.ids)],
                'default_apply_mode': 'lines',
            },
        }

