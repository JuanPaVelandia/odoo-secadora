# -*- coding: utf-8 -*-
"""
Wizard para mostrar advertencias de datos faltantes en lote de nóminas.
"""
from odoo import api, fields, models, _


class HrPayslipEdiRunWarningWizard(models.TransientModel):
    _name = 'hr.payslip.edi.run.warning.wizard'
    _description = 'Advertencias Lote Nómina Electrónica'

    run_id = fields.Many2one(
        'hr.payslip.edi.run', string='Lote',
        required=True, ondelete='cascade'
    )
    warning_text = fields.Text(
        string='Advertencias',
        readonly=True
    )
    slip_ids = fields.Many2many(
        'hr.payslip.edi', string='Nóminas a Enviar'
    )
    error_count = fields.Integer(string='Cantidad de Errores')

    def action_continue(self):
        """Continúa con el envío ignorando las advertencias."""
        self.ensure_one()
        self.run_id.action_force_validar_dian()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Proceso Completado'),
                'message': _('Se inició el envío a DIAN. Revise el estado de cada nómina.'),
                'type': 'warning',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }

    def action_cancel(self):
        """Cancela y permite corregir los errores."""
        return {'type': 'ir.actions.act_window_close'}
