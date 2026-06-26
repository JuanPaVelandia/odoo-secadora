# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    """Extiende sale.order para gestión de anticipos"""
    _inherit = 'sale.order'

    advance_request_ids = fields.One2many(
        'advance.request',
        'sale_order_id',
        string='Solicitudes de Anticipo'
    )

    advance_count = fields.Integer(
        string='# Anticipos',
        compute='_compute_advance_count'
    )

    total_advance_amount = fields.Monetary(
        string='Total Anticipos',
        currency_field='currency_id',
        compute='_compute_advance_amount'
    )

    total_advance_available = fields.Monetary(
        string='Anticipos Disponibles',
        currency_field='currency_id',
        compute='_compute_advance_amount'
    )

    advance_percentage = fields.Float(
        string='% Anticipo',
        default=30,
        help='Porcentaje de anticipo sugerido'
    )

    has_advances = fields.Boolean(
        string='Tiene Anticipos',
        compute='_compute_advance_count'
    )

    @api.depends('advance_request_ids')
    def _compute_advance_count(self):
        """Cuenta solicitudes de anticipo"""
        for order in self:
            order.advance_count = len(order.advance_request_ids)
            order.has_advances = bool(order.advance_request_ids)

    @api.depends('advance_request_ids', 'advance_request_ids.amount_paid', 'advance_request_ids.amount_available')
    def _compute_advance_amount(self):
        """Calcula montos de anticipos"""
        for order in self:
            requests = order.advance_request_ids.filtered(lambda r: r.state not in ['cancelled'])
            order.total_advance_amount = sum(requests.mapped('amount_paid'))
            order.total_advance_available = sum(requests.mapped('amount_available'))

    def action_create_advance_request(self):
        """Crea solicitud de anticipo desde orden de venta"""
        self.ensure_one()

        if self.state not in ['sale', 'done']:
            raise UserError(_('La orden debe estar confirmada para solicitar un anticipo'))

        # Buscar tipo de anticipo
        advance_type = self.env['advance.type'].search([
            ('code', '=', 'SALE_ADVANCE')
        ], limit=1)

        if not advance_type:
            # Crear tipo por defecto
            advance_type = self.env['advance.type'].create({
                'name': 'Anticipo de Venta',
                'code': 'SALE_ADVANCE',
                'advance_type': 'customer',
                'sequence': 10
            })

        # Calcular monto sugerido
        suggested_amount = self.amount_total * (self.advance_percentage / 100)

        # Crear solicitud
        request = self.env['advance.request'].create({
            'request_type': 'customer',
            'advance_type_id': advance_type.id,
            'partner_id': self.partner_id.id,
            'sale_order_id': self.id,
            'amount_requested': suggested_amount,
            'description': _('Anticipo para orden de venta %s') % self.name,
            'analytic_account_id': self.analytic_account_id.id if self.analytic_account_id else False,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'user_id': self.user_id.id
        })

        # Abrir la solicitud creada
        return {
            'name': _('Solicitud de Anticipo'),
            'type': 'ir.actions.act_window',
            'res_model': 'advance.request',
            'res_id': request.id,
            'view_mode': 'form',
            'target': 'current'
        }

    def action_view_advances(self):
        """Ver anticipos de la orden"""
        self.ensure_one()
        return {
            'name': _('Anticipos'),
            'type': 'ir.actions.act_window',
            'res_model': 'advance.request',
            'view_mode': 'kanban,list,form',
            'domain': [('sale_order_id', '=', self.id)],
            'context': {
                'default_sale_order_id': self.id,
                'default_partner_id': self.partner_id.id,
                'default_request_type': 'customer'
            }
        }

    def action_create_advance_invoice(self):
        """Crea factura de anticipo"""
        self.ensure_one()

        if not self.advance_request_ids:
            raise UserError(_('No hay solicitudes de anticipo para esta orden'))

        # Buscar anticipos pagados
        paid_advances = self.advance_request_ids.filtered(
            lambda r: r.state == 'paid' and r.amount_available > 0
        )

        if not paid_advances:
            raise UserError(_('No hay anticipos pagados disponibles'))

        # Crear wizard para seleccionar anticipo
        wizard = self.env['sale.advance.invoice.wizard'].create({
            'sale_order_id': self.id,
            'advance_request_ids': [(6, 0, paid_advances.ids)]
        })

        return {
            'name': _('Crear Factura de Anticipo'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.advance.invoice.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new'
        }


class PurchaseOrder(models.Model):
    """Extiende purchase.order para gestión de anticipos"""
    _inherit = 'purchase.order'

    advance_request_ids = fields.One2many(
        'advance.request',
        'purchase_order_id',
        string='Solicitudes de Anticipo'
    )

    advance_count = fields.Integer(
        string='# Anticipos',
        compute='_compute_advance_count'
    )

    total_advance_amount = fields.Monetary(
        string='Total Anticipos',
        currency_field='currency_id',
        compute='_compute_advance_amount'
    )

    total_advance_available = fields.Monetary(
        string='Anticipos Disponibles',
        currency_field='currency_id',
        compute='_compute_advance_amount'
    )

    advance_percentage = fields.Float(
        string='% Anticipo',
        default=30,
        help='Porcentaje de anticipo sugerido'
    )

    has_advances = fields.Boolean(
        string='Tiene Anticipos',
        compute='_compute_advance_count'
    )

    @api.depends('advance_request_ids')
    def _compute_advance_count(self):
        """Cuenta solicitudes de anticipo"""
        for order in self:
            order.advance_count = len(order.advance_request_ids)
            order.has_advances = bool(order.advance_request_ids)

    @api.depends('advance_request_ids', 'advance_request_ids.amount_paid', 'advance_request_ids.amount_available')
    def _compute_advance_amount(self):
        """Calcula montos de anticipos"""
        for order in self:
            requests = order.advance_request_ids.filtered(lambda r: r.state not in ['cancelled'])
            order.total_advance_amount = sum(requests.mapped('amount_paid'))
            order.total_advance_available = sum(requests.mapped('amount_available'))

    def action_create_advance_request(self):
        """Crea solicitud de anticipo desde orden de compra"""
        self.ensure_one()

        if self.state not in ['purchase', 'done']:
            raise UserError(_('La orden debe estar confirmada para solicitar un anticipo'))

        # Buscar tipo de anticipo
        advance_type = self.env['advance.type'].search([
            ('code', '=', 'PURCHASE_ADVANCE')
        ], limit=1)

        if not advance_type:
            # Crear tipo por defecto
            advance_type = self.env['advance.type'].create({
                'name': 'Anticipo a Proveedor',
                'code': 'PURCHASE_ADVANCE',
                'advance_type': 'supplier',
                'sequence': 10
            })

        # Calcular monto sugerido
        suggested_amount = self.amount_total * (self.advance_percentage / 100)

        # Crear solicitud
        request = self.env['advance.request'].create({
            'request_type': 'supplier',
            'advance_type_id': advance_type.id,
            'partner_id': self.partner_id.id,
            'purchase_order_id': self.id,
            'amount_requested': suggested_amount,
            'description': _('Anticipo para orden de compra %s') % self.name,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'user_id': self.user_id.id
        })

        # Abrir la solicitud creada
        return {
            'name': _('Solicitud de Anticipo'),
            'type': 'ir.actions.act_window',
            'res_model': 'advance.request',
            'res_id': request.id,
            'view_mode': 'form',
            'target': 'current'
        }

    def action_view_advances(self):
        """Ver anticipos de la orden"""
        self.ensure_one()
        return {
            'name': _('Anticipos'),
            'type': 'ir.actions.act_window',
            'res_model': 'advance.request',
            'view_mode': 'kanban,list,form',
            'domain': [('purchase_order_id', '=', self.id)],
            'context': {
                'default_purchase_order_id': self.id,
                'default_partner_id': self.partner_id.id,
                'default_request_type': 'supplier'
            }
        }


class ResPartner(models.Model):
    """Extiende res.partner para mostrar información de anticipos"""
    _inherit = 'res.partner'

    advance_request_ids = fields.One2many(
        'advance.request',
        'partner_id',
        string='Solicitudes de Anticipo'
    )

    advance_count = fields.Integer(
        string='# Anticipos',
        compute='_compute_advance_info'
    )

    total_advance_balance = fields.Monetary(
        string='Saldo de Anticipos',
        currency_field='currency_id',
        compute='_compute_advance_info',
        help='Saldo total de anticipos disponibles'
    )

    customer_advance_balance = fields.Monetary(
        string='Anticipos como Cliente',
        currency_field='currency_id',
        compute='_compute_advance_info'
    )

    supplier_advance_balance = fields.Monetary(
        string='Anticipos como Proveedor',
        currency_field='currency_id',
        compute='_compute_advance_info'
    )

    @api.depends('advance_request_ids')
    def _compute_advance_info(self):
        """Calcula información de anticipos del partner"""
        for partner in self:
            requests = partner.advance_request_ids.filtered(
                lambda r: r.state in ['paid', 'reconciled']
            )
            partner.advance_count = len(requests)

            # Anticipos como cliente
            customer_requests = requests.filtered(
                lambda r: r.request_type == 'customer'
            )
            partner.customer_advance_balance = sum(
                customer_requests.mapped('amount_available')
            )

            # Anticipos como proveedor
            supplier_requests = requests.filtered(
                lambda r: r.request_type == 'supplier'
            )
            partner.supplier_advance_balance = sum(
                supplier_requests.mapped('amount_available')
            )

            # Balance total
            partner.total_advance_balance = (
                partner.customer_advance_balance - partner.supplier_advance_balance
            )

    def action_view_advances(self):
        """Ver anticipos del partner"""
        self.ensure_one()
        return {
            'name': _('Anticipos de %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'advance.request',
            'view_mode': 'kanban,list,form,pivot',
            'domain': [('partner_id', '=', self.id)],
            'context': {
                'default_partner_id': self.id,
                'search_default_with_balance': 1
            }
        }