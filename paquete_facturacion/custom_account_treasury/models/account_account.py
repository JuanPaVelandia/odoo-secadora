# -*- coding: utf-8 -*-
from odoo import models, fields, api


class AccountAccount(models.Model):
    _inherit = 'account.account'

    # ========== CAMPOS DE ANTICIPOS ==========
    used_for_advance_payment = fields.Boolean(
        string='Cuenta Anticipo',
        help='Marca esta cuenta como cuenta de anticipos'
    )
    is_advance_account = fields.Boolean(
        string='Es Cuenta de Anticipo',
        related='used_for_advance_payment',
        store=True,
        readonly=False
    )
    advance_account_type = fields.Selection([
        ('sale', 'Anticipo de Cliente'),
        ('purchase', 'Anticipo de Proveedor')
    ], string='Tipo de Cuenta de Anticipo')

    # ========== CAMPOS DE PRÉSTAMOS ==========
    used_for_loan = fields.Boolean(
        string='Cuenta de Préstamo',
        help='Marca esta cuenta como cuenta de préstamos para cruce con facturas'
    )
    is_loan_account = fields.Boolean(
        string='Es Cuenta de Préstamo',
        related='used_for_loan',
        store=True,
        readonly=False
    )
    loan_account_type = fields.Selection([
        ('customer', 'Préstamo a Cliente'),
        ('supplier', 'Préstamo de Proveedor'),
        ('employee', 'Préstamo a Empleado')
    ], string='Tipo de Cuenta de Préstamo')

    # ========== ONCHANGES ==========

    @api.onchange('used_for_advance_payment')
    def onchange_used_for_advance_payment(self):
        if self.used_for_advance_payment:
            self.reconcile = True

    @api.onchange('used_for_loan')
    def onchange_used_for_loan(self):
        """Habilitar reconciliación para cuentas de préstamos"""
        if self.used_for_loan:
            self.reconcile = True

    # ========== MÉTODOS OVERRIDE ==========

    def write(self, vals):
        if vals.get('used_for_advance_payment'):
            vals['reconcile'] = True
        if vals.get('used_for_loan'):
            vals['reconcile'] = True
        return super().write(vals)
