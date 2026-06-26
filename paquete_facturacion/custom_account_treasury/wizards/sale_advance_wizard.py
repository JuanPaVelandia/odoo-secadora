# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class SaleAdvanceWizard(models.TransientModel):
    """
    Wizard para crear anticipos desde órdenes de venta.
    Permite seleccionar múltiples órdenes y crear anticipo directo o solicitud.
    """
    _name = 'sale.advance.wizard'
    _description = 'Wizard Anticipo de Venta'

    # ========== SELECCIÓN DE ÓRDENES ==========

    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        required=True,
        domain=[('customer_rank', '>', 0)]
    )

    sale_order_ids = fields.Many2many(
        'sale.order',
        'sale_advance_wizard_order_rel',
        'wizard_id',
        'order_id',
        string='Pedidos de Venta',
        domain="[('partner_id', '=', partner_id), ('state', 'in', ['draft', 'sent', 'sale'])]"
    )

    # ========== CONFIGURACIÓN DE ANTICIPO ==========

    advance_type_id = fields.Many2one(
        'advance.type',
        string='Tipo de Anticipo',
        domain=[('document_type', '=', 'customer')],
        required=True
    )

    percentage = fields.Float(
        string='% Anticipo',
        default=100.0,
        help='Porcentaje del total de pedidos a anticipar'
    )

    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        required=True,
        default=lambda self: self.env.company.currency_id
    )

    # Montos calculados
    orders_total = fields.Monetary(
        string='Total Pedidos',
        currency_field='currency_id',
        compute='_compute_amounts',
        store=True
    )

    orders_paid = fields.Monetary(
        string='Ya Cobrado',
        currency_field='currency_id',
        compute='_compute_amounts',
        store=True
    )

    orders_pending = fields.Monetary(
        string='Pendiente',
        currency_field='currency_id',
        compute='_compute_amounts',
        store=True
    )

    amount = fields.Monetary(
        string='Monto Anticipo',
        currency_field='currency_id',
        required=True
    )

    # ========== OPCIONES ==========

    create_mode = fields.Selection([
        ('direct', 'Crear Anticipo Directo'),
        ('request', 'Crear Solicitud de Anticipo'),
    ], string='Modo', default='request', required=True)

    journal_id = fields.Many2one(
        'account.journal',
        string='Diario de Cobro',
        domain=[('type', 'in', ['bank', 'cash'])]
    )

    payment_date = fields.Date(
        string='Fecha de Cobro',
        default=fields.Date.context_today
    )

    memo = fields.Char(
        string='Referencia/Memo'
    )

    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company
    )

    # ========== LÍNEAS DE DETALLE ==========

    line_ids = fields.One2many(
        'sale.advance.wizard.line',
        'wizard_id',
        string='Detalle de Pedidos'
    )

    # ========== COMPUTED ==========

    @api.depends('sale_order_ids', 'sale_order_ids.amount_total')
    def _compute_amounts(self):
        for wizard in self:
            orders_total = sum(wizard.sale_order_ids.mapped('amount_total'))
            # Calcular lo ya cobrado (anticipos existentes)
            orders_paid = 0.0
            for order in wizard.sale_order_ids:
                # Sumar anticipos recibidos de este cliente relacionados con esta orden
                advances = self.env['account.payment'].search([
                    ('partner_id', '=', order.partner_id.id),
                    ('advance', '=', True),
                    ('payment_type', '=', 'inbound'),
                    ('state', '=', 'posted'),
                ])
                for adv in advances:
                    if order in adv.sale_order_ids:
                        orders_paid += adv.amount

            wizard.orders_total = orders_total
            wizard.orders_paid = orders_paid
            wizard.orders_pending = orders_total - orders_paid

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        """Limpiar pedidos al cambiar cliente"""
        self.sale_order_ids = False
        self.line_ids = False

        # Buscar tipo de anticipo por defecto
        if not self.advance_type_id:
            advance_type = self.env['advance.type'].search([
                ('document_type', '=', 'customer'),
                ('allow_sale_orders', '=', True)
            ], limit=1)
            if advance_type:
                self.advance_type_id = advance_type
                self.percentage = advance_type.percentage_advance or 100.0

    @api.onchange('advance_type_id')
    def _onchange_advance_type_id(self):
        """Actualizar porcentaje según tipo"""
        if self.advance_type_id:
            self.percentage = self.advance_type_id.percentage_advance or 100.0
            self._compute_advance_amount()

    @api.onchange('sale_order_ids', 'percentage')
    def _onchange_orders_or_percentage(self):
        """Recalcular monto y líneas al cambiar pedidos o porcentaje"""
        self._compute_advance_amount()
        self._update_lines()

    def _compute_advance_amount(self):
        """Calcula el monto del anticipo basado en pedidos y porcentaje"""
        if self.sale_order_ids:
            total = sum(self.sale_order_ids.mapped('amount_total'))
            self.amount = total * (self.percentage / 100)
        else:
            self.amount = 0.0

    def _update_lines(self):
        """Actualiza las líneas de detalle según los pedidos seleccionados"""
        lines = []
        for order in self.sale_order_ids:
            lines.append((0, 0, {
                'sale_order_id': order.id,
                'order_amount': order.amount_total,
                'advance_amount': order.amount_total * (self.percentage / 100),
            }))
        self.line_ids = [(5, 0, 0)] + lines

    # ========== ACCIONES ==========

    def action_create_advance(self):
        """Crea el anticipo según el modo seleccionado"""
        self.ensure_one()

        if not self.sale_order_ids:
            raise UserError(_('Debe seleccionar al menos un pedido de venta'))

        if self.amount <= 0:
            raise UserError(_('El monto del anticipo debe ser mayor a cero'))

        if self.create_mode == 'direct':
            return self._create_direct_advance()
        else:
            return self._create_advance_request()

    def _create_direct_advance(self):
        """Crea un cobro de anticipo directo"""
        if not self.journal_id:
            raise UserError(_('Debe seleccionar un diario de cobro para anticipo directo'))

        if not self.advance_type_id.account_id:
            raise UserError(_('El tipo de anticipo debe tener una cuenta contable configurada'))

        # Crear el pago (cobro)
        payment_vals = {
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': self.partner_id.id,
            'amount': self.amount,
            'currency_id': self.currency_id.id,
            'journal_id': self.journal_id.id,
            'date': self.payment_date,
            'ref': self.memo or _('Anticipo PV: %s') % ', '.join(self.sale_order_ids.mapped('name')),
            'advance': True,
            'destination_account_id': self.advance_type_id.account_id.id,
            'sale_order_ids': [(6, 0, self.sale_order_ids.ids)],
        }

        payment = self.env['account.payment'].create(payment_vals)

        # Mensaje en los pedidos
        for order in self.sale_order_ids:
            order.message_post(
                body=_('Se recibió anticipo %s por %s %s') % (
                    payment.name,
                    self.currency_id.symbol,
                    '{:,.2f}'.format(self.amount)
                ),
            )

        # Abrir el pago creado
        return {
            'name': _('Anticipo Recibido'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'res_id': payment.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _create_advance_request(self):
        """Crea una solicitud de anticipo"""
        # Usar advance.request en lugar de payment.request
        request_vals = {
            'partner_id': self.partner_id.id,
            'request_type': 'customer',
            'advance_type_id': self.advance_type_id.id,
            'amount_requested': self.amount,
            'currency_id': self.currency_id.id,
            'description': self.memo or _('Anticipo PV: %s') % ', '.join(self.sale_order_ids.mapped('name')),
            'sale_order_id': self.sale_order_ids[0].id if len(self.sale_order_ids) == 1 else False,
        }

        request = self.env['advance.request'].create(request_vals)

        # Mensaje en los pedidos
        for order in self.sale_order_ids:
            order.message_post(
                body=_('Se creó solicitud de anticipo %s') % request.name,
            )

        return {
            'name': _('Solicitud de Anticipo'),
            'type': 'ir.actions.act_window',
            'res_model': 'advance.request',
            'res_id': request.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.model
    def action_open_from_treasury(self):
        """Acción para abrir el wizard desde tesorería"""
        return {
            'name': _('Crear Anticipo de Venta'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.advance.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_create_mode': 'request',
            }
        }


class SaleAdvanceWizardLine(models.TransientModel):
    """Líneas de detalle del wizard de anticipo"""
    _name = 'sale.advance.wizard.line'
    _description = 'Línea de Wizard Anticipo de Venta'

    wizard_id = fields.Many2one(
        'sale.advance.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade'
    )

    sale_order_id = fields.Many2one(
        'sale.order',
        string='Pedido de Venta',
        required=True
    )

    order_name = fields.Char(
        related='sale_order_id.name',
        string='Número'
    )

    order_date = fields.Datetime(
        related='sale_order_id.date_order',
        string='Fecha'
    )

    order_amount = fields.Monetary(
        string='Total Pedido',
        currency_field='currency_id'
    )

    advance_amount = fields.Monetary(
        string='Monto Anticipo',
        currency_field='currency_id'
    )

    currency_id = fields.Many2one(
        related='wizard_id.currency_id',
        string='Moneda'
    )

    include = fields.Boolean(
        string='Incluir',
        default=True
    )
