# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError


class RegistroBultos(models.Model):
    _name = 'secadora.registro.bultos'
    _description = 'Registro de Bultos Empacados'
    _order = 'fecha desc'

    orden_id = fields.Many2one(
        'secadora.orden.servicio',
        string='Orden de Servicio',
        required=True,
        ondelete='cascade',
        index=True
    )

    fecha = fields.Date(
        string='Fecha Empaque',
        required=True,
        default=fields.Date.context_today
    )

    cantidad = fields.Integer(
        string='Cantidad de Bultos',
        required=True,
        help='Número de bultos empacados'
    )

    peso_promedio = fields.Float(
        string='Peso Promedio (kg)',
        required=True,
        default=50.0,
        digits=(8, 2),
        help='Peso promedio de cada bulto en kg'
    )

    peso_total = fields.Float(
        string='Peso Total (kg)',
        compute='_compute_peso_total',
        store=True,
        digits=(12, 2),
        help='Peso total = cantidad × peso promedio'
    )

    producto_empaque_id = fields.Many2one(
        'product.product',
        string='Tipo de Empaque',
        required=True,
        domain=[('type', '=', 'product')],
        help='Producto de tipo empaque (ej: Bulto 50kg, Bulto 25kg)'
    )

    proveedor_empaque = fields.Selection([
        ('secadora', 'Secadora (Se cobra)'),
        ('cliente', 'Cliente (No se cobra)'),
    ], string='¿Quién provee el empaque?',
       required=True,
       default='secadora',
       help='Si el cliente trae sus propios bultos, seleccionar Cliente')

    precio_unitario_empaque = fields.Float(
        string='Precio Unit. Empaque',
        digits='Product Price',
        help='Precio por bulto (solo si provee secadora)'
    )

    cobrar_empaque = fields.Boolean(
        string='Cobrar Empaque',
        compute='_compute_cobrar_empaque',
        store=True,
        help='Se cobra si provee secadora'
    )

    subtotal_empaque = fields.Float(
        string='Subtotal Empaques',
        compute='_compute_subtotal_empaque',
        store=True,
        digits='Product Price',
        help='Total a cobrar por estos empaques'
    )

    stock_move_id = fields.Many2one(
        'stock.move',
        string='Movimiento de Inventario',
        readonly=True,
        help='Movimiento que consume empaques del inventario'
    )

    observaciones = fields.Text(
        string='Observaciones'
    )

    usuario_id = fields.Many2one(
        'res.users',
        string='Registrado por',
        default=lambda self: self.env.user,
        readonly=True
    )

    state = fields.Selection([
        ('borrador', 'Borrador'),
        ('confirmado', 'Confirmado'),
        ('facturado', 'Facturado'),
    ], string='Estado', default='borrador')

    # ==================== COMPUTED FIELDS ====================

    @api.depends('cantidad', 'peso_promedio')
    def _compute_peso_total(self):
        for record in self:
            record.peso_total = record.cantidad * record.peso_promedio

    @api.depends('proveedor_empaque')
    def _compute_cobrar_empaque(self):
        for record in self:
            record.cobrar_empaque = (record.proveedor_empaque == 'secadora')

    @api.depends('cantidad', 'precio_unitario_empaque', 'cobrar_empaque')
    def _compute_subtotal_empaque(self):
        for record in self:
            if record.cobrar_empaque:
                record.subtotal_empaque = record.cantidad * record.precio_unitario_empaque
            else:
                record.subtotal_empaque = 0.0

    @api.onchange('producto_empaque_id')
    def _onchange_producto_empaque_id(self):
        if self.producto_empaque_id:
            self.precio_unitario_empaque = self.producto_empaque_id.list_price

    # ==================== MÉTODOS ====================

    def action_confirmar(self):
        for record in self:
            if record.state != 'borrador':
                continue

            if record.proveedor_empaque == 'secadora' and record.producto_empaque_id:
                record._crear_movimiento_inventario()

            record.state = 'confirmado'

    def _crear_movimiento_inventario(self):
        self.ensure_one()

        location_prod = self.env.ref('stock.location_production', raise_if_not_found=False)
        location_inventory = self.env['stock.location'].search([
            ('usage', '=', 'internal')
        ], limit=1)

        if not location_prod or not location_inventory:
            raise UserError('No se encontraron las ubicaciones de inventario necesarias.')

        move = self.env['stock.move'].create({
            'name': f'Consumo empaques - {self.orden_id.name}',
            'product_id': self.producto_empaque_id.id,
            'product_uom_qty': self.cantidad,
            'product_uom': self.producto_empaque_id.uom_id.id,
            'location_id': location_inventory.id,
            'location_dest_id': location_prod.id,
            'origin': self.orden_id.name,
        })

        move._action_confirm()
        move._action_assign()
        move._action_done()

        self.stock_move_id = move.id
