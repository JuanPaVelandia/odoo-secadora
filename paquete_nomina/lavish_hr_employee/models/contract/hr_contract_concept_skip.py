# -*- coding: utf-8 -*-
"""
Modelo hr.contract.concept.skip - Control de saltos de cuotas en conceptos.
"""
from odoo import models, fields, api, _

class HrContractConceptSkip(models.Model):
    _name = 'hr.contract.concept.skip'
    _description = 'Control de Saltos de Cuotas'
    _inherit = ['mail.thread']
    _order = 'period_skip desc'

    name = fields.Char('Nombre', compute='_compute_name', store=True)
    concept_id = fields.Many2one('hr.contract.concepts', 'Concepto', required=True, ondelete='cascade')
    period_skip = fields.Date('Fecha de Salto', required=True)
    period_double = fields.Boolean('Recuperar con pago doble', default=True,
        help='Si está marcado, el valor saltado se recuperará con pago doble en la siguiente cuota')
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('approved', 'Confirmado')
    ], string='Estado', default='draft', tracking=True)

    @api.depends('concept_id', 'period_skip')
    def _compute_name(self):
        for record in self:
            if record.concept_id and record.period_skip:
                indicator = '1Q' if record.period_skip.day <= 15 else '2Q'
                record.name = f"Salto {indicator} {record.period_skip.strftime('%m/%Y')}"
            else:
                record.name = "Nuevo Salto"

    def action_approve(self):
        """Confirmar el salto"""
        self.write({'state': 'approved'})
        self.message_post(body=_("Salto confirmado para %s") % self.period_skip.strftime('%d/%m/%Y'))

    def check_skip_applies(self, date_from, date_to):
        """Valida si el salto aplica para el período"""
        self.ensure_one()
        if self.state != 'approved':
            return False
        return date_from <= self.period_skip <= date_to

