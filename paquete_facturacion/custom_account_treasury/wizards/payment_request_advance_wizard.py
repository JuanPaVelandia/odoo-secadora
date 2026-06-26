# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class PaymentRequestAddOrders(models.TransientModel):
    """Wizard simplificado para agregar órdenes a solicitud"""
    _name = 'payment.request.add.orders'
    _description = 'Agregar Órdenes a Solicitud'

    request_id = fields.Many2one(
        'payment.request',
        string='Solicitud',
        required=True,
        readonly=True,
        default=lambda self: self.env.context.get('active_id')
    )

    partner_id = fields.Many2one(
        'res.partner',
        string='Tercero',
        related='request_id.partner_id',
        readonly=True
    )

    advance_type_id = fields.Many2one(
        'advance.type',
        related='request_id.advance_type_id',
        readonly=True
    )

    allow_sale_orders = fields.Boolean(
        related='request_id.allow_sale_orders',
        readonly=True
    )

    allow_purchase_orders = fields.Boolean(
        related='request_id.allow_purchase_orders',
        readonly=True
    )

    sale_order_ids = fields.Many2many(
        'sale.order',
        'wizard_add_orders_sale_rel',
        'wizard_id',
        'order_id',
        string='Pedidos de Venta'
    )

    purchase_order_ids = fields.Many2many(
        'purchase.order',
        'wizard_add_orders_purchase_rel',
        'wizard_id',
        'order_id',
        string='Órdenes de Compra'
    )

    def action_add_orders(self):
        """Agregar órdenes a la solicitud"""
        self.ensure_one()

        # Validar que tipo permita las órdenes seleccionadas
        if self.sale_order_ids and not self.allow_sale_orders:
            raise UserError(_('Este tipo de anticipo no permite órdenes de venta'))

        if self.purchase_order_ids and not self.allow_purchase_orders:
            raise UserError(_('Este tipo de anticipo no permite órdenes de compra'))

        # Agregar órdenes a la solicitud
        if self.sale_order_ids:
            self.request_id.sale_order_ids = [(4, order.id) for order in self.sale_order_ids]

        if self.purchase_order_ids:
            self.request_id.purchase_order_ids = [(4, order.id) for order in self.purchase_order_ids]

        # Mensaje en chatter
        orders_added = []
        if self.sale_order_ids:
            orders_added.append(_('%d pedidos de venta') % len(self.sale_order_ids))
        if self.purchase_order_ids:
            orders_added.append(_('%d órdenes de compra') % len(self.purchase_order_ids))

        if orders_added:
            self.request_id.message_post(
                body=_('Órdenes agregadas: %s') % ', '.join(orders_added),
                subject=_('Órdenes Asociadas'),
                message_type='notification'
            )

        return {'type': 'ir.actions.act_window_close'}
