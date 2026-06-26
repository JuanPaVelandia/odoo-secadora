# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class DianUnifyLinesWizard(models.TransientModel):
    _name = 'dian.unify.lines.wizard'
    _description = 'Wizard para Unificar Líneas del Documento DIAN'

    processor_id = fields.Many2one(
        'dian.document.processor',
        string='Documento',
        required=True,
        readonly=True
    )

    product_id = fields.Many2one(
        'product.product',
        string='Producto',
        required=True,
        domain="[('purchase_ok', '=', True)]",
        help='Producto que reemplazará todas las líneas actuales'
    )

    total_amount = fields.Monetary(
        string='Monto Total del Documento',
        currency_field='currency_id',
        readonly=True
    )

    line_count = fields.Integer(
        string='Cantidad de Líneas Actuales',
        readonly=True
    )

    currency_id = fields.Many2one(
        related='processor_id.document_currency_id',
        readonly=True
    )

    description = fields.Text(
        string='Descripción',
        help='Descripción para la línea unificada (opcional)'
    )

    quantity = fields.Float(
        string='Cantidad',
        default=1.0,
        required=True
    )

    uom_id = fields.Many2one(
        'uom.uom',
        string='Unidad de Medida',
        compute='_compute_uom_id',
        store=True,
        readonly=False
    )

    @api.depends('product_id')
    def _compute_uom_id(self):
        for wizard in self:
            if wizard.product_id:
                wizard.uom_id = wizard.product_id.uom_id
            else:
                wizard.uom_id = False

    def action_unify(self):
        """Unifica todas las líneas en una sola"""
        self.ensure_one()

        if not self.product_id:
            raise UserError(_("Debe seleccionar un producto"))

        # Calcular precio unitario para mantener el total
        price_unit = self.total_amount / self.quantity if self.quantity else 0

        # Guardar información de las líneas originales antes de eliminarlas
        original_lines = self.processor_id.line_ids
        original_line_info = []
        for line in original_lines:
            original_line_info.append({
                'id': line.id,
                'product_name': line.product_name,
                'quantity': line.quantity,
                'price_unit': line.price_unit,
                'price_subtotal': line.price_subtotal,
            })

        # Store original line data as JSON in notes field
        import json
        unified_data = json.dumps([{
            'sequence': line.sequence,
            'product_code': line.product_code or '',
            'product_name': line.product_name or '',
            'quantity': line.quantity,
            'uom': line.uom_id.name if line.uom_id else '',
            'price_unit': line.price_unit,
            'price_subtotal': line.price_subtotal,
        } for line in original_lines], ensure_ascii=False)

        # Eliminar todas las líneas actuales del documento
        original_lines.unlink()

        # Crear una única línea con el producto seleccionado
        new_line = self.env['dian.document.processor.line'].create({
            'processor_id': self.processor_id.id,
            'sequence': 1,
            'product_id': self.product_id.id,
            'product_code': self.product_id.default_code or '',
            'product_name': self.description or self.product_id.name,
            'quantity': self.quantity,
            'uom_id': self.uom_id.id,
            'uom_code': self.uom_id.name,
            'price_unit': price_unit,
            'price_subtotal': self.total_amount,
            'is_unified': True,
            'notes': f"Líneas unificadas:\n{unified_data}",
        })

        # Mensaje de éxito con detalle de líneas unificadas
        lines_detail = '<ul>'
        for info in original_line_info:
            lines_detail += f'<li>{info["product_name"]}: {info["quantity"]} x {info["price_unit"]:,.2f} = {info["price_subtotal"]:,.2f}</li>'
        lines_detail += '</ul>'

        self.processor_id.message_post(
            body=f'<p><strong>Líneas unificadas</strong></p>'
                 f'<p>{self.line_count} líneas consolidadas en 1 línea</p>'
                 f'<p><strong>Producto unificado:</strong> {self.product_id.display_name}</p>'
                 f'<p><strong>Cantidad:</strong> {self.quantity} {self.uom_id.name}</p>'
                 f'<p><strong>Precio unitario:</strong> {price_unit:,.2f}</p>'
                 f'<hr/>'
                 f'<p><strong>Líneas originales:</strong></p>'
                 f'{lines_detail}',
            message_type='notification'
        )

        return {'type': 'ir.actions.act_window_close'}
