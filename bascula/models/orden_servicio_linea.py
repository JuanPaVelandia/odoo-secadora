# -*- coding: utf-8 -*-

from odoo import models, fields, api


class OrdenServicioLinea(models.Model):
    _name = 'secadora.orden.servicio.linea'
    _description = 'Línea de Servicio Adicional a Facturar'
    _order = 'orden_id, id'

    orden_id = fields.Many2one(
        'secadora.orden.servicio',
        string='Orden de Servicio',
        required=True,
        ondelete='cascade'
    )

    producto_id = fields.Many2one(
        'product.product',
        string='Servicio/Producto',
        required=True,
        domain=[('type', '=', 'service')],
        help='Servicio adicional a cobrar (ej: Cargue, Descargue, Limpieza)'
    )

    descripcion = fields.Text(
        string='Descripción',
        help='Descripción adicional del servicio'
    )

    base_calculo = fields.Selection([
        ('peso_entrada', 'Peso de Entrada'),
        ('peso_salida', 'Peso de Salida'),
        ('merma', 'Merma'),
        ('bultos', 'Cantidad de Bultos'),
        ('fijo', 'Valor Fijo'),
    ], string='Base de Cálculo',
       required=True,
       default='fijo',
       help='Base para calcular la cantidad del servicio')

    cantidad = fields.Float(
        string='Cantidad',
        required=True,
        digits=(12, 2),
        default=1.0,
        help='Cantidad a facturar'
    )

    precio_unitario = fields.Float(
        string='Precio Unitario',
        required=True,
        digits='Product Price',
        help='Precio por unidad'
    )

    subtotal = fields.Float(
        string='Subtotal',
        compute='_compute_subtotal',
        store=True,
        digits='Product Price',
        help='Cantidad × Precio Unitario'
    )

    # ==================== COMPUTED FIELDS ====================

    @api.depends('cantidad', 'precio_unitario')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.cantidad * line.precio_unitario

    @api.onchange('producto_id')
    def _onchange_producto_id(self):
        if self.producto_id:
            self.precio_unitario = self.producto_id.list_price
            self.descripcion = self.producto_id.name
