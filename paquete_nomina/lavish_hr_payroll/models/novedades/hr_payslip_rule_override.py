# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class HrPayslipRuleOverride(models.Model):
    _name = 'hr.payslip.rule.override'
    _description = 'Modificacion de Reglas de Nomina'

    payslip_id = fields.Many2one('hr.payslip', 'Nomina', required=True)
    rule_id = fields.Many2one('hr.salary.rule', 'Regla', required=True)
    override_type = fields.Selection([
        ('amount', 'Monto Base'),
        ('quantity', 'Cantidad'),
        ('rate', 'Tasa'),
        ('total', 'Total Final'),
    ], string='Tipo de Modificacion', required=True)
    value_original = fields.Float('Valor Original', readonly=True)
    value_override = fields.Float('Valor Nuevo')
    active = fields.Boolean('Aplicar Modificacion', default=True)
    description = fields.Text('Descripcion/Motivo')
    simulation_date = fields.Datetime('Fecha Simulacion', default=fields.Datetime.now)
    simulation_result = fields.Float('Resultado Simulado', readonly=True)
    difference = fields.Float('Diferencia', compute='_compute_difference')
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('simulated', 'Simulado'),
        ('applied', 'Aplicado')
    ], string='Estado', default='draft')

    @api.depends('value_original', 'value_override')
    def _compute_difference(self):
        for record in self:
            record.difference = record.value_override - record.value_original

    def action_simulate(self):
        self.ensure_one()
        if self.payslip_id.state not in ['draft', 'verify']:
            raise UserError(_('Solo se pueden simular ajustes en nominas en borrador o verificacion'))

        # Crear una copia del calculo original para simular
        result = self.payslip_id.with_context(
            simulate_override=True,
            override_rule=self.rule_id.code,
            override_type=self.override_type,
            override_value=self.value_override
        )._get_payslip_lines_lavish()

        # Encontrar el resultado simulado para esta regla
        rule_result = next((r for r in result if r['code'] == self.rule_id.code), None)
        if rule_result:
            self.simulation_result = rule_result['total']
            self.state = 'simulated'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Simulacion Completada'),
                'message': _('Resultado simulado: %s\nDiferencia: %s') % (
                    '{:,.2f}'.format(self.simulation_result),
                    '{:,.2f}'.format(self.difference)
                ),
                'sticky': False,
                'type': 'info'
            }
        }

    @api.onchange('value_override')
    def _onchange_value_override(self):
        if self.value_override and self.value_original:
            if abs((self.value_override - self.value_original) / self.value_original) > 0.5:
                return {
                    'warning': {
                        'title': _("Variacion Significativa"),
                        'message': _("El ajuste representa una variacion mayor al 50% del valor original. Por favor verifique.")
                    }
                }
