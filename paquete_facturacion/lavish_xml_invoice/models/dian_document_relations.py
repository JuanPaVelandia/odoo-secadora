# -*- coding: utf-8 -*-
"""
Relaciones del Documento DIAN con Stock, Pagos y Notas de Crédito
Asocia automáticamente movimientos de stock, pagos y notas relacionadas
"""

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class DianDocumentProcessor(models.Model):
    """Extensión para relacionar con stock, pagos y notas"""
    _inherit = 'dian.document.processor'

    # ===== RELACIONES CON STOCK =====
    picking_ids = fields.Many2many(
        'stock.picking',
        string='Albaranes',
        compute='_compute_pickings',
        help='Albaranes relacionados con las órdenes de compra asociadas'
    )

    picking_count = fields.Integer(
        string='# Albaranes',
        compute='_compute_pickings'
    )

    move_ids = fields.Many2many(
        'stock.move',
        string='Movimientos de Stock',
        compute='_compute_stock_moves',
        help='Movimientos de stock de los productos del documento'
    )

    move_count = fields.Integer(
        string='# Movimientos',
        compute='_compute_stock_moves'
    )

    # ===== RELACIONES CON NOTAS DE CRÉDITO/DÉBITO =====
    credit_note_ids = fields.One2many(
        'dian.document.processor',
        'billing_reference_cufe',
        domain=[('document_type', '=', '91')],
        string='Notas de Crédito',
        help='Notas de crédito que referencian este documento'
    )

    credit_note_count = fields.Integer(
        string='# NC',
        compute='_compute_credit_notes'
    )

    debit_note_ids = fields.One2many(
        'dian.document.processor',
        'billing_reference_cufe',
        domain=[('document_type', '=', '92')],
        string='Notas de Débito',
        help='Notas de débito que referencian este documento'
    )

    debit_note_count = fields.Integer(
        string='# ND',
        compute='_compute_debit_notes'
    )

    # Documento original (para NC/ND)
    origin_document_id = fields.Many2one(
        'dian.document.processor',
        string='Documento de Origen',
        compute='_compute_origin_document',
        store=True,
        help='Documento original que referencia esta NC/ND'
    )

    # ===== RELACIONES CON PAGOS =====
    payment_ids = fields.Many2many(
        'account.payment',
        string='Pagos',
        compute='_compute_payments',
        help='Pagos relacionados con la factura creada'
    )

    payment_count = fields.Integer(
        string='# Pagos',
        compute='_compute_payments'
    )

    payment_state = fields.Selection([
        ('not_paid', 'No Pagado'),
        ('in_payment', 'En Proceso'),
        ('paid', 'Pagado'),
        ('partial', 'Parcial'),
        ('reversed', 'Revertido'),
    ], string='Estado de Pago',
       compute='_compute_payment_state')

    amount_paid = fields.Monetary(
        string='Monto Pagado',
        currency_field='document_currency_id',
        compute='_compute_payment_amounts'
    )

    amount_residual = fields.Monetary(
        string='Saldo Pendiente',
        currency_field='document_currency_id',
        compute='_compute_payment_amounts'
    )

    # ========== CÓMPUTOS ==========

    @api.depends('purchase_order_ids')
    def _compute_pickings(self):
        """Obtiene albaranes de las órdenes de compra"""
        for processor in self:
            pickings = processor.purchase_order_ids.mapped('picking_ids')
            processor.picking_ids = pickings
            processor.picking_count = len(pickings)

    @api.depends('line_ids.product_id', 'purchase_order_ids')
    def _compute_stock_moves(self):
        """Obtiene movimientos de stock de los productos"""
        for processor in self:
            moves = self.env['stock.move']

            # Desde órdenes de compra
            if processor.purchase_order_ids:
                moves |= processor.purchase_order_ids.mapped('picking_ids.move_ids')

            # Alternativamente, buscar por productos y fecha
            if not moves and processor.line_ids:
                products = processor.line_ids.mapped('product_id')
                if products and processor.issue_date:
                    date_from = processor.issue_date
                    date_to = processor.issue_date

                    moves = self.env['stock.move'].search([
                        ('product_id', 'in', products.ids),
                        ('date', '>=', date_from),
                        ('date', '<=', date_to),
                        ('partner_id', '=', processor.supplier_id.id),
                    ], limit=100)

            processor.move_ids = moves
            processor.move_count = len(moves)

    @api.depends('cufe')
    def _compute_credit_notes(self):
        """Cuenta notas de crédito relacionadas"""
        for processor in self:
            if processor.cufe:
                notes = self.env['dian.document.processor'].search([
                    ('billing_reference_cufe', '=', processor.cufe),
                    ('document_type', '=', '91')
                ])
                processor.credit_note_count = len(notes)
            else:
                processor.credit_note_count = 0

    @api.depends('cufe')
    def _compute_debit_notes(self):
        """Cuenta notas de débito relacionadas"""
        for processor in self:
            if processor.cufe:
                notes = self.env['dian.document.processor'].search([
                    ('billing_reference_cufe', '=', processor.cufe),
                    ('document_type', '=', '92')
                ])
                processor.debit_note_count = len(notes)
            else:
                processor.debit_note_count = 0

    @api.depends('billing_reference_cufe')
    def _compute_origin_document(self):
        """Busca el documento original para NC/ND"""
        for processor in self:
            if processor.document_type in ['91', '92'] and processor.billing_reference_cufe:
                origin = self.env['dian.document.processor'].search([
                    ('cufe', '=', processor.billing_reference_cufe)
                ], limit=1)
                processor.origin_document_id = origin
            else:
                processor.origin_document_id = False

    @api.depends('invoice_id')
    def _compute_payments(self):
        """Obtiene pagos de la factura"""
        for processor in self:
            if processor.invoice_id:
                # Obtener pagos desde reconciliaciones
                payments = self.env['account.payment']
                # Buscar pagos que tengan líneas reconciliadas con esta factura
                if hasattr(processor.invoice_id, '_get_reconciled_payments'):
                    payments = processor.invoice_id._get_reconciled_payments()
                else:
                    # Método alternativo compatible
                    reconciled_lines = processor.invoice_id.line_ids.filtered(
                        lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable')
                    ).mapped('matched_debit_ids.debit_move_id.payment_id') | processor.invoice_id.line_ids.filtered(
                        lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable')
                    ).mapped('matched_credit_ids.credit_move_id.payment_id')
                    payments = reconciled_lines.filtered(lambda p: p)

                processor.payment_ids = payments
                processor.payment_count = len(payments)
            else:
                processor.payment_ids = False
                processor.payment_count = 0

    @api.depends('invoice_id', 'invoice_id.payment_state')
    def _compute_payment_state(self):
        """Obtiene estado de pago de la factura"""
        for processor in self:
            if processor.invoice_id:
                state_map = {
                    'not_paid': 'not_paid',
                    'in_payment': 'in_payment',
                    'paid': 'paid',
                    'partial': 'partial',
                    'reversed': 'reversed',
                }
                processor.payment_state = state_map.get(
                    processor.invoice_id.payment_state,
                    'not_paid'
                )
            else:
                processor.payment_state = 'not_paid'

    @api.depends('invoice_id', 'invoice_id.amount_residual', 'invoice_id.amount_total')
    def _compute_payment_amounts(self):
        """Calcula montos pagados y pendientes"""
        for processor in self:
            if processor.invoice_id:
                processor.amount_paid = processor.invoice_id.amount_total - processor.invoice_id.amount_residual
                processor.amount_residual = processor.invoice_id.amount_residual
            else:
                processor.amount_paid = 0.0
                processor.amount_residual = processor.amount_total

    # ========== ACCIONES ==========

    def action_view_pickings(self):
        """Abre vista de albaranes"""
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Albaranes'),
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.picking_ids.ids)],
            'context': {'default_partner_id': self.supplier_id.id},
        }

    def action_view_stock_moves(self):
        """Abre vista de movimientos de stock"""
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Movimientos de Stock'),
            'res_model': 'stock.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.move_ids.ids)],
        }

    def action_view_credit_notes(self):
        """Abre vista de notas de crédito"""
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Notas de Crédito'),
            'res_model': 'dian.document.processor',
            'view_mode': 'list,form',
            'domain': [
                ('billing_reference_cufe', '=', self.cufe),
                ('document_type', '=', '91')
            ],
            'context': {
                'default_supplier_id': self.supplier_id.id,
                'default_billing_reference_cufe': self.cufe,
                'default_document_type': '91',
            },
        }

    def action_view_debit_notes(self):
        """Abre vista de notas de débito"""
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Notas de Débito'),
            'res_model': 'dian.document.processor',
            'view_mode': 'list,form',
            'domain': [
                ('billing_reference_cufe', '=', self.cufe),
                ('document_type', '=', '92')
            ],
            'context': {
                'default_supplier_id': self.supplier_id.id,
                'default_billing_reference_cufe': self.cufe,
                'default_document_type': '92',
            },
        }

    def action_view_payments(self):
        """Abre vista de pagos"""
        self.ensure_one()

        if not self.invoice_id:
            raise UserError(_('Debe crear la factura primero para ver los pagos'))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Pagos'),
            'res_model': 'account.payment',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.payment_ids.ids)],
            'context': {
                'default_partner_id': self.supplier_id.id,
                'default_partner_type': 'supplier',
                'default_payment_type': 'outbound',
            },
        }

    def action_view_origin_document(self):
        """Abre el documento original (para NC/ND)"""
        self.ensure_one()

        if not self.origin_document_id:
            raise UserError(_('No se encontró el documento de origen'))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Documento de Origen'),
            'res_model': 'dian.document.processor',
            'res_id': self.origin_document_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ========== MÉTODOS AUXILIARES ==========

    def _get_stock_location_from_po(self):
        """Obtiene ubicación de stock desde la OC"""
        if self.purchase_order_ids:
            return self.purchase_order_ids[0].picking_type_id.default_location_dest_id
        return self.env.ref('stock.stock_location_stock', raise_if_not_found=False)

    def _link_credit_note_to_invoice(self):
        """Vincula nota de crédito a la factura original"""
        self.ensure_one()

        if self.document_type != '91' or not self.origin_document_id:
            return

        if self.origin_document_id.invoice_id and self.invoice_id:
            # Crear línea de reverso en la factura original
            _logger.info(
                f"Nota de crédito {self.document_number} vinculada a factura "
                f"{self.origin_document_id.invoice_id.name}"
            )
