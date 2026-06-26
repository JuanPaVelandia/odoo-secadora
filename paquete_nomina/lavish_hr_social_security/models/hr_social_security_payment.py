# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class HrSocialSecurityPaymentLine(models.Model):
    """Líneas de historial de pagos de seguridad social"""
    _name = 'hr.social.security.payment.line'
    _description = 'Línea de Pago de Seguridad Social'
    _order = 'payment_date desc, id desc'

    social_security_id = fields.Many2one(
        'hr.payroll.social.security',
        string='Seguridad Social',
        required=True,
        ondelete='cascade',
        index=True
    )
    payment_date = fields.Date(
        string='Fecha de Pago',
        required=True,
        default=fields.Date.today
    )
    amount = fields.Float(
        string='Monto',
        required=True
    )
    payment_type = fields.Selection([
        ('payment', 'Pago Directo'),
        ('overpayment_applied', 'Sobrepago Aplicado'),
        ('refund', 'Reembolso'),
        ('adjustment', 'Ajuste')
    ], string='Tipo de Pago', required=True, default='payment')

    reference = fields.Char(
        string='Referencia',
        help='Número de transacción, cheque, etc.'
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Diario',
        domain=[('type', 'in', ['bank', 'cash'])]
    )
    move_id = fields.Many2one(
        'account.move',
        string='Asiento Contable',
        readonly=True
    )
    source_social_security_id = fields.Many2one(
        'hr.payroll.social.security',
        string='Origen (Sobrepago)',
        help='Periodo del cual se aplicó el sobrepago'
    )
    notes = fields.Text(string='Notas')

    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        related='social_security_id.company_id',
        store=True
    )

    # Campos informativos
    year = fields.Integer(
        string='Año',
        related='social_security_id.year',
        store=True
    )
    month = fields.Selection(
        related='social_security_id.month',
        string='Mes',
        store=True
    )

    @api.depends('payment_date', 'amount')
    def _compute_display_name(self):
        for record in self:
            record.display_name = f"Pago {record.payment_date} - ${record.amount:,.2f}"


class AccountMove(models.Model):
    """Extensión de account.move para relacionar con pagos de seguridad social"""
    _inherit = 'account.move'

    social_security_payment_id = fields.Many2one(
        'hr.payroll.social.security',
        string='Pago Seguridad Social',
        help='Referencia al periodo de seguridad social para pagos'
    )
    social_security_id = fields.Many2one(
        'hr.payroll.social.security',
        string='Seguridad Social (Contabilización)',
        help='Referencia al periodo de seguridad social para contabilización'
    )
