# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class L10ncoExogenousAmlDistributionWizard(models.TransientModel):
    _name = "l10n_co.exogenous_aml_distribution_wizard"
    _description = "Asigna campos exógena a múltiples account.move.line"

    apply_mode = fields.Selection(
        [('lines', 'Líneas seleccionadas'),
         ('moves', 'Todas las líneas de los asientos seleccionados')],
        string='Aplicar a', default='lines', required=True,
    )
    line_ids = fields.Many2many('account.move.line', string='Líneas afectadas')
    move_ids = fields.Many2many('account.move', string='Asientos afectados')
    line_count = fields.Integer(compute='_compute_counts', string='Líneas')
    move_count = fields.Integer(compute='_compute_counts', string='Asientos')

    set_skip = fields.Boolean(string='Cambiar "Omitir en exógena" (línea)')
    skip_value = fields.Boolean(string='Omitir (línea)')

    set_move_skip = fields.Boolean(string='Cambiar "Omitir en exógena" (asiento completo)')
    move_skip_value = fields.Boolean(string='Omitir asiento')

    set_format_field = fields.Boolean(string='Cambiar Columna exógena')
    format_field_id = fields.Many2one(
        'l10n_co.exogenous_format_field', string='Columna (manual)')
    set_secondary_field = fields.Boolean(string='Cambiar Columna secundaria')
    secondary_field_id = fields.Many2one(
        'l10n_co.exogenous_format_field', string='Columna secundaria (residuo)')

    set_concept = fields.Boolean(string='Cambiar Concepto exógena')
    concept_id = fields.Many2one(
        'l10n_co.exogenous_concept', string='Concepto (manual)')

    set_percentage = fields.Boolean(string='Cambiar % a columna primaria')
    percentage = fields.Float(string='%', default=100.0)

    set_reason = fields.Boolean(string='Cambiar Motivo asignación')
    reason = fields.Char(string='Motivo asignación exógena')

    @api.depends('line_ids', 'move_ids')
    def _compute_counts(self):
        for w in self:
            w.line_count = len(w.line_ids)
            w.move_count = len(w.move_ids)

    def _resolve_target_lines(self):
        if self.apply_mode == 'moves' and self.move_ids:
            return self.move_ids.mapped('line_ids')
        return self.line_ids

    def action_apply(self):
        self.ensure_one()
        targets = self._resolve_target_lines()
        if not targets:
            raise UserError(_('No hay líneas para actualizar.'))

        vals = {}
        if self.set_skip:
            vals['l10n_co_exogenous_skip'] = self.skip_value
        if self.set_format_field:
            vals['l10n_co_exogenous_format_field_id'] = self.format_field_id.id or False
        if self.set_secondary_field:
            vals['l10n_co_exogenous_secondary_field_id'] = self.secondary_field_id.id or False
        if self.set_concept:
            vals['l10n_co_exogenous_concept_id'] = self.concept_id.id or False
        if self.set_percentage:
            vals['l10n_co_exogenous_percentage'] = self.percentage
        if self.set_reason:
            vals['l10n_co_exogenous_assignment_reason'] = self.reason or False

        if not vals and not self.set_move_skip:
            raise UserError(_('Marca al menos un campo a cambiar.'))

        if vals:
            targets.write(vals)

        if self.set_move_skip:
            moves = self.move_ids if self.apply_mode == 'moves' and self.move_ids else targets.mapped('move_id')
            moves.write({'l10n_co_exogenous_skip': self.move_skip_value})

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Distribución actualizada'),
                'message': _('%d líneas actualizadas') % len(targets),
                'type': 'success',
                'sticky': False,
            }
        }
