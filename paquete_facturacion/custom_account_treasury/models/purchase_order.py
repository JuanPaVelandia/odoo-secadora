# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    payment_request_ids = fields.Many2many(
        'payment.request',
        'payment_request_purchase_order_rel',
        'order_id',
        'request_id',
        string='Solicitudes de Pago Asociadas',
        help='Solicitudes de pago/anticipo asociadas a esta orden'
    )

    payment_request_count = fields.Integer(
        string='# Solicitudes',
        compute='_compute_payment_request_count'
    )

    @api.depends('payment_request_ids')
    def _compute_payment_request_count(self):
        for order in self:
            order.payment_request_count = len(order.payment_request_ids)

    def action_create_payment_request(self):
        """Crear solicitud de pago/anticipo desde orden de compra"""
        self.ensure_one()

        if not self.partner_id:
            raise UserError(_('Debe tener un proveedor asignado'))

        # Buscar tipo de anticipo por defecto para compras
        advance_type = self.env['advance.type'].search([
            ('allow_purchase_orders', '=', True)
        ], limit=1)

        if not advance_type:
            raise UserError(_(
                'No se encontró un tipo de anticipo configurado para órdenes de compra.\n'
                'Configure un tipo de anticipo con "Permite Órdenes de Compra" activado.'
            ))

        # Calcular monto basado en el porcentaje del tipo de anticipo
        amount = 0.0
        if advance_type.auto_fill_amount and advance_type.percentage_advance:
            amount = self.amount_total * (advance_type.percentage_advance / 100)

        # Crear la solicitud
        request_vals = {
            'partner_id': self.partner_id.id,
            'request_type': 'advance',
            'advance_type_id': advance_type.id,
            'amount': amount,
            'currency_id': self.currency_id.id,
            'memo': _('Anticipo para orden %s') % self.name,
            'purchase_order_ids': [(6, 0, [self.id])],
        }

        request = self.env['payment.request'].create(request_vals)

        # Mensaje en chatter de la orden
        self.message_post(
            body=_('Se creó la solicitud de anticipo %s') % request.name,
            subject=_('Solicitud Creada'),
        )

        return {
            'name': _('Solicitud de Anticipo'),
            'type': 'ir.actions.act_window',
            'res_model': 'payment.request',
            'res_id': request.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_payment_requests(self):
        """Ver solicitudes de pago asociadas"""
        self.ensure_one()

        action = self.env['ir.actions.act_window']._for_xml_id(
            'custom_account_treasury.action_payment_request'
        )

        if len(self.payment_request_ids) == 1:
            action['views'] = [(False, 'form')]
            action['res_id'] = self.payment_request_ids.id
        else:
            action['domain'] = [('id', 'in', self.payment_request_ids.ids)]

        return action

    def action_add_to_payment_request(self):
        """Agregar esta orden a una solicitud existente"""
        self.ensure_one()

        return {
            'name': _('Agregar a Solicitud'),
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order.add.to.request.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_purchase_order_id': self.id,
                'default_partner_id': self.partner_id.id,
            }
        }
