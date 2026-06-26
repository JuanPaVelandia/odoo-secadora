# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class TreasuryBankChargeType(models.Model):
    """Tipos de cargos bancarios para conciliacion"""
    _name = 'treasury.bank.charge.type'
    _description = 'Tipo de Cargo Bancario'
    _order = 'sequence, name'

    name = fields.Char(
        string='Nombre',
        required=True,
        help='Nombre del tipo de cargo (ej: Comision, GMF, IVA Comision)'
    )
    code = fields.Char(
        string='Codigo',
        required=True,
        help='Codigo unico para identificar el tipo de cargo'
    )
    sequence = fields.Integer(
        string='Secuencia',
        default=10
    )
    active = fields.Boolean(
        string='Activo',
        default=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compania',
        required=True,
        default=lambda self: self.env.company
    )

    # Configuracion contable
    account_id = fields.Many2one(
        'account.account',
        string='Cuenta Contable',
        domain="[('active', '=', True)]",
        help='Cuenta donde se registra este cargo. Si no se define, usa la cuenta por defecto de gastos bancarios de la compania.'
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Tercero',
        help='Tercero por defecto para este cargo. Si no se define, usa el del banco.'
    )

    # Tipo de cargo
    charge_type = fields.Selection([
        ('expense', 'Gasto'),
        ('tax', 'Impuesto'),
        ('withholding', 'Retencion'),
        ('other', 'Otro')
    ], string='Tipo', default='expense', required=True)

    # Configuracion de IVA
    apply_iva = fields.Boolean(
        string='Aplica IVA',
        default=False,
        help='Indica si este cargo tiene IVA asociado'
    )
    iva_account_id = fields.Many2one(
        'account.account',
        string='Cuenta IVA',
        domain="[('active', '=', True)]",
        help='Cuenta para registrar el IVA de este cargo'
    )
    iva_rate = fields.Float(
        string='Tasa IVA (%)',
        default=19.0,
        help='Tasa de IVA aplicable'
    )

    # Calculo automatico
    calculation_type = fields.Selection([
        ('fixed', 'Monto Fijo'),
        ('percentage', 'Porcentaje'),
        ('manual', 'Manual')
    ], string='Tipo de Calculo', default='manual', required=True)

    fixed_amount = fields.Float(
        string='Monto Fijo',
        help='Monto fijo a aplicar si el tipo de calculo es Fijo'
    )
    percentage = fields.Float(
        string='Porcentaje (%)',
        help='Porcentaje a aplicar sobre el monto base'
    )
    percentage_base = fields.Selection([
        ('transaction', 'Monto Transaccion'),
        ('balance', 'Saldo')
    ], string='Base del Porcentaje', default='transaction')

    # Aplicabilidad
    apply_to_inbound = fields.Boolean(
        string='Aplica a Ingresos',
        default=True,
        help='Aplicar este cargo en transacciones de ingreso'
    )
    apply_to_outbound = fields.Boolean(
        string='Aplica a Egresos',
        default=True,
        help='Aplicar este cargo en transacciones de egreso'
    )

    # Notas
    description = fields.Text(
        string='Descripcion',
        help='Descripcion detallada del cargo'
    )

    _sql_constraints = [
        ('code_company_uniq', 'unique(code, company_id)',
         'El codigo debe ser unico por compania!')
    ]

    @api.onchange('charge_type')
    def _onchange_charge_type(self):
        """Valores por defecto segun el tipo de cargo"""
        if self.charge_type == 'tax':
            self.apply_iva = False
        elif self.charge_type == 'expense':
            self.apply_iva = True

    def calculate_amount(self, base_amount):
        """Calcula el monto del cargo segun su configuracion"""
        self.ensure_one()
        if self.calculation_type == 'fixed':
            return self.fixed_amount
        elif self.calculation_type == 'percentage':
            return base_amount * (self.percentage / 100)
        return 0.0

    def get_iva_amount(self, charge_amount):
        """Calcula el monto de IVA para este cargo"""
        self.ensure_one()
        if self.apply_iva and self.iva_rate:
            return charge_amount * (self.iva_rate / 100)
        return 0.0

    def toggle_active(self):
        """Alterna el estado activo/archivado"""
        for record in self:
            record.active = not record.active
