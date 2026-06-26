# -*- coding: utf-8 -*-
from odoo import models, fields, api


class TreasuryBankChargeLine(models.Model):
    """Linea de cargo bancario aplicado a un pago"""
    _name = 'treasury.bank.charge.line'
    _description = 'Linea de Cargo Bancario'
    _order = 'sequence, id'

    payment_id = fields.Many2one(
        'account.payment',
        string='Pago',
        required=True,
        ondelete='cascade'
    )
    charge_type_id = fields.Many2one(
        'treasury.bank.charge.type',
        string='Tipo de Cargo',
        required=True,
        ondelete='restrict'
    )
    sequence = fields.Integer(
        related='charge_type_id.sequence',
        store=True
    )
    name = fields.Char(
        related='charge_type_id.name',
        string='Descripcion'
    )
    code = fields.Char(
        related='charge_type_id.code'
    )

    # Montos
    base_amount = fields.Monetary(
        string='Monto Base',
        currency_field='currency_id',
        help='Monto sobre el cual se calcula el cargo'
    )
    charge_amount = fields.Monetary(
        string='Monto Cargo',
        currency_field='currency_id',
        compute='_compute_amounts',
        store=True,
        readonly=False
    )
    iva_amount = fields.Monetary(
        string='IVA',
        currency_field='currency_id',
        compute='_compute_amounts',
        store=True,
        readonly=False
    )
    total_amount = fields.Monetary(
        string='Total',
        currency_field='currency_id',
        compute='_compute_total',
        store=True
    )

    currency_id = fields.Many2one(
        related='payment_id.currency_id',
        store=True
    )
    company_id = fields.Many2one(
        related='payment_id.company_id',
        store=True
    )

    # Configuracion contable (heredada del tipo pero editable)
    account_id = fields.Many2one(
        'account.account',
        string='Cuenta Contable',
        compute='_compute_account',
        store=True,
        readonly=False
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Tercero',
        compute='_compute_partner',
        store=True,
        readonly=False
    )

    @api.depends('charge_type_id', 'base_amount')
    def _compute_amounts(self):
        for line in self:
            if line.charge_type_id and line.base_amount:
                line.charge_amount = line.charge_type_id.calculate_amount(line.base_amount)
                line.iva_amount = line.charge_type_id.get_iva_amount(line.charge_amount)
            else:
                line.charge_amount = 0.0
                line.iva_amount = 0.0

    @api.depends('charge_amount', 'iva_amount')
    def _compute_total(self):
        for line in self:
            line.total_amount = line.charge_amount + line.iva_amount

    @api.depends('charge_type_id', 'payment_id.company_id')
    def _compute_account(self):
        for line in self:
            if line.charge_type_id.account_id:
                line.account_id = line.charge_type_id.account_id
            elif line.payment_id.company_id.bank_expense_account_id:
                line.account_id = line.payment_id.company_id.bank_expense_account_id
            else:
                line.account_id = False

    @api.depends('charge_type_id', 'payment_id.company_id')
    def _compute_partner(self):
        for line in self:
            if line.charge_type_id.partner_id:
                line.partner_id = line.charge_type_id.partner_id
            elif line.payment_id.company_id.bank_expense_partner_id:
                line.partner_id = line.payment_id.company_id.bank_expense_partner_id
            else:
                line.partner_id = line.payment_id.partner_id or False


class AccountJournal(models.Model):
    """Extension de diario para configurar cargos bancarios"""
    _inherit = 'account.journal'

    charge_type_ids = fields.Many2many(
        'treasury.bank.charge.type',
        'journal_charge_type_rel',
        'journal_id',
        'charge_type_id',
        string='Tipos de Cargo Bancario',
        help='Cargos que se aplican automaticamente a los pagos de este diario (GMF, Comision, etc.)'
    )


class AccountPayment(models.Model):
    """Extension de pago para cargos bancarios"""
    _inherit = 'account.payment'

    # Lineas de cargo calculadas
    charge_line_ids = fields.One2many(
        'treasury.bank.charge.line',
        'payment_id',
        string='Cargos Bancarios'
    )

    # Total de cargos
    total_charges = fields.Monetary(
        string='Total Cargos',
        currency_field='currency_id',
        compute='_compute_total_charges',
        store=True
    )

    # Monto neto (monto - cargos)
    net_amount = fields.Monetary(
        string='Monto Neto',
        currency_field='currency_id',
        compute='_compute_net_amount',
        store=True,
        help='Monto del pago menos los cargos bancarios'
    )

    # Total salida banco (pago + cargos)
    total_bank_output = fields.Monetary(
        string='Total Salida Banco',
        currency_field='currency_id',
        compute='_compute_total_bank_output',
        store=True,
        help='Monto total que salio del banco (pago + cargos)'
    )

    # Resumen de cargos en HTML
    charges_summary_html = fields.Html(
        string='Resumen de Cargos',
        compute='_compute_charges_summary'
    )

    @api.depends('charge_line_ids.total_amount')
    def _compute_total_charges(self):
        for payment in self:
            payment.total_charges = sum(payment.charge_line_ids.mapped('total_amount'))

    @api.depends('amount', 'total_charges')
    def _compute_net_amount(self):
        for payment in self:
            payment.net_amount = payment.amount - payment.total_charges

    @api.depends('amount', 'total_charges')
    def _compute_total_bank_output(self):
        for payment in self:
            payment.total_bank_output = payment.amount + payment.total_charges

    @api.depends('charge_line_ids', 'amount', 'total_charges', 'reconciled_invoice_ids')
    def _compute_charges_summary(self):
        for payment in self:
            if not payment.charge_line_ids:
                payment.charges_summary_html = False
                continue

            currency = payment.currency_id
            lines = []

            # Factura(s) relacionada(s)
            invoices = payment.reconciled_invoice_ids
            if invoices:
                inv_names = ', '.join(invoices.mapped('name'))
                lines.append(f'<tr><td><strong>Factura(s):</strong></td><td colspan="2">{inv_names}</td></tr>')

            lines.append('<tr><td colspan="3"><hr/></td></tr>')

            # Monto del pago
            lines.append(f'<tr><td>Pago Principal</td><td style="text-align:right">{currency.symbol} {payment.amount:,.2f}</td><td></td></tr>')

            # Detalle de cargos
            lines.append('<tr><td colspan="3"><strong>Cargos Bancarios:</strong></td></tr>')
            for charge in payment.charge_line_ids:
                lines.append(f'<tr><td style="padding-left:20px">{charge.name}</td>'
                           f'<td style="text-align:right">{currency.symbol} {charge.charge_amount:,.2f}</td>'
                           f'<td style="text-align:right;color:#666">{charge.code}</td></tr>')
                if charge.iva_amount:
                    lines.append(f'<tr><td style="padding-left:40px;font-size:0.9em">IVA {charge.name}</td>'
                               f'<td style="text-align:right;font-size:0.9em">{currency.symbol} {charge.iva_amount:,.2f}</td>'
                               f'<td></td></tr>')

            lines.append('<tr><td colspan="3"><hr/></td></tr>')

            # Totales
            lines.append(f'<tr><td><strong>Total Cargos:</strong></td>'
                        f'<td style="text-align:right"><strong>{currency.symbol} {payment.total_charges:,.2f}</strong></td><td></td></tr>')
            lines.append(f'<tr style="background:#f5f5f5"><td><strong>TOTAL SALIDA BANCO:</strong></td>'
                        f'<td style="text-align:right"><strong>{currency.symbol} {payment.total_bank_output:,.2f}</strong></td><td></td></tr>')

            payment.charges_summary_html = f'<table class="table table-sm" style="width:auto">{chr(10).join(lines)}</table>'

    @api.onchange('journal_id', 'amount')
    def _onchange_journal_apply_charges(self):
        """Aplica automaticamente los cargos del diario cuando cambia"""
        if not self.journal_id or not self.journal_id.charge_type_ids:
            return

        base_amount = abs(self.amount) if self.amount else 0.0
        existing_types = self.charge_line_ids.mapped('charge_type_id')

        # Filtrar tipos segun direccion del pago
        applicable_types = self.journal_id.charge_type_ids.filtered(
            lambda t: (self.payment_type == 'outbound' and t.apply_to_outbound) or
                      (self.payment_type == 'inbound' and t.apply_to_inbound)
        )

        commands = []
        for charge_type in applicable_types:
            if charge_type not in existing_types:
                commands.append((0, 0, {
                    'charge_type_id': charge_type.id,
                    'base_amount': base_amount,
                }))

        if commands:
            self.charge_line_ids = commands

    def action_recalculate_charges(self):
        """Recalcula los cargos basado en el monto actual"""
        for payment in self:
            base_amount = abs(payment.amount) if payment.amount else 0.0
            for line in payment.charge_line_ids:
                line.base_amount = base_amount

    def action_apply_journal_charges(self):
        """Aplica todos los cargos configurados en el diario"""
        self.ensure_one()
        if not self.journal_id.charge_type_ids:
            return

        base_amount = abs(self.amount) if self.amount else 0.0
        existing_types = self.charge_line_ids.mapped('charge_type_id')

        # Filtrar tipos segun direccion del pago
        applicable_types = self.journal_id.charge_type_ids.filtered(
            lambda t: (self.payment_type == 'outbound' and t.apply_to_outbound) or
                      (self.payment_type == 'inbound' and t.apply_to_inbound)
        )

        for charge_type in applicable_types:
            if charge_type not in existing_types:
                self.env['treasury.bank.charge.line'].create({
                    'payment_id': self.id,
                    'charge_type_id': charge_type.id,
                    'base_amount': base_amount,
                })

    # TODO: Implementar generacion de lineas de cargo en asiento
    # Por ahora desactivado para evitar errores - los cargos se registran pero no generan asiento automatico
    # def _prepare_move_line_default_vals(self, write_off_line_vals=None, force_balance=None):
    #     """Extiende para agregar lineas de cargo al asiento con salida de banco por concepto"""
    #     res = super()._prepare_move_line_default_vals(write_off_line_vals, force_balance)
    #     # Logica pendiente de revisar
    #     return res
