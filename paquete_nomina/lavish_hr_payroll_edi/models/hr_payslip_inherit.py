# -*- coding: utf-8 -*-
"""
Extensión de hr.payslip para relacionar con nómina electrónica.
"""
from odoo import api, fields, models


class HrPayslipInherit(models.Model):
    _inherit = 'hr.payslip'

    epayslip_edi_ids = fields.Many2many(
        'hr.payslip.edi',
        'hr_payslip_edi_rel',
        'payslip_id',
        'edi_id',
        string='Nóminas Electrónicas',
        help='Documentos de nómina electrónica a los que pertenece esta nómina'
    )
    state_dian_display = fields.Selection([
        ('sin_documento', 'Sin Documento'),
        ('por_notificar', 'Por Notificar'),
        ('error', 'Error'),
        ('por_validar', 'Por Validar'),
        ('exitoso', 'Exitoso'),
        ('rechazado', 'Rechazado'),
    ], string='Estado DIAN', compute='_compute_state_dian_display', store=True)
    epayslip_edi_count = fields.Integer(
        string='Docs EDI', compute='_compute_state_dian_display', store=True
    )

    @api.depends('epayslip_edi_ids', 'epayslip_edi_ids.state_dian')
    def _compute_state_dian_display(self):
        for rec in self:
            edi_docs = rec.epayslip_edi_ids.filtered(lambda e: not e.credit_note)
            rec.epayslip_edi_count = len(rec.epayslip_edi_ids)
            if not edi_docs:
                rec.state_dian_display = 'sin_documento'
                continue
            # Prioridad: exitoso > por_validar > error/rechazado > por_notificar
            states = edi_docs.mapped('state_dian')
            if 'exitoso' in states:
                rec.state_dian_display = 'exitoso'
            elif 'por_validar' in states:
                rec.state_dian_display = 'por_validar'
            elif 'error' in states:
                rec.state_dian_display = 'error'
            elif 'rechazado' in states:
                rec.state_dian_display = 'rechazado'
            else:
                rec.state_dian_display = 'por_notificar'

    def action_open_edi_documents(self):
        """Abre los documentos EDI relacionados."""
        self.ensure_one()
        if len(self.epayslip_edi_ids) == 1:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'hr.payslip.edi',
                'res_id': self.epayslip_edi_ids.id,
                'view_mode': 'form',
                'target': 'current',
            }
        return {
            'type': 'ir.actions.act_window',
            'name': 'Nómina Electrónica',
            'res_model': 'hr.payslip.edi',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.epayslip_edi_ids.ids)],
            'target': 'current',
        }
