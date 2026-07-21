# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError


class RegistroBultos(models.Model):
    _name = 'secadora.registro.bultos'
    _description = 'Registro de Bultos Empacados'
    _order = 'fecha desc'
    _rec_name = 'name'

    name = fields.Char(
        string='Descripción',
        compute='_compute_name',
        store=True,
    )

    @api.depends('cantidad', 'producto_id', 'producto_empaque_id', 'fecha')
    def _compute_name(self):
        for record in self:
            producto = record.producto_id.name or ''
            empaque = record.producto_empaque_id.name or ''
            record.name = f"{record.cantidad} bultos {producto} - {empaque} - {record.fecha}"

    orden_id = fields.Many2one(
        'secadora.orden.servicio',
        string='Orden de Servicio',
        required=True,
        ondelete='cascade',
        index=True
    )

    cliente_id = fields.Many2one(
        'res.partner',
        string='Dueño / Agricultor',
        related='orden_id.cliente_id',
        store=True,
        index=True,
    )

    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        related='orden_id.company_id',
        store=True,
        index=True,
    )

    producto_id = fields.Many2one(
        'product.product',
        string='Producto',
        domain=[('categ_id.name', '=', 'Arroz')],
        help='Producto de arroz empacado (ej: Arroz Paddy Seco, Rechazo)'
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
        domain=[('type', '=', 'consu')],
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

    # TODO: Descomentar cuando se instale el módulo 'stock'
    # stock_move_id = fields.Many2one(
    #     'stock.move',
    #     string='Movimiento de Inventario',
    #     readonly=True,
    #     help='Movimiento que consume empaques del inventario'
    # )

    # ==================== DESPACHO ====================

    despacho_ids = fields.One2many(
        'secadora.despacho.bultos',
        'registro_bultos_id',
        string='Despachos',
        help='Líneas de despacho asociadas a este registro',
    )

    cantidad_despachada = fields.Integer(
        string='Despachados',
        compute='_compute_despacho',
        store=True,
        help='Cantidad de bultos ya despachados',
    )

    cantidad_pendiente = fields.Integer(
        string='Pendientes',
        compute='_compute_despacho',
        store=True,
        help='Cantidad de bultos pendientes por despachar',
    )

    despachado = fields.Boolean(
        string='Despachado',
        compute='_compute_despacho',
        store=True,
        help='Indica si todos los bultos de este registro fueron despachados',
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

    @api.depends('despacho_ids.cantidad', 'despacho_ids.confirmado', 'cantidad')
    def _compute_despacho(self):
        for record in self:
            confirmados = record.despacho_ids.filtered('confirmado')
            despachada = sum(confirmados.mapped('cantidad'))
            record.cantidad_despachada = despachada
            record.cantidad_pendiente = record.cantidad - despachada
            record.despachado = despachada >= record.cantidad

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

    @api.onchange('producto_id')
    def _onchange_producto_id(self):
        if self.producto_id and 'paddy' in (self.producto_id.name or '').lower():
            pesajes = self.orden_id.pesaje_entrada_ids
            variedades = pesajes.mapped('variedad_id.name')
            variedades_unicas = list(dict.fromkeys(v for v in variedades if v))
            if variedades_unicas:
                self.observaciones = ', '.join(variedades_unicas)
            else:
                self.observaciones = False
        else:
            self.observaciones = False

    # ==================== MÉTODOS ====================

    @api.model_create_multi
    def create(self, vals_list):
        registros = super().create(vals_list)
        registros.mapped('orden_id').recalcular_servicios()
        return registros

    def write(self, vals):
        res = super().write(vals)
        if 'cantidad' in vals:
            self.mapped('orden_id').recalcular_servicios()
        return res

    def unlink(self):
        ordenes = self.mapped('orden_id')
        res = super().unlink()
        ordenes.recalcular_servicios()
        return res

    def action_confirmar(self):
        for record in self:
            if record.state != 'borrador':
                continue
            # El consumo de empaques del inventario lo maneja el módulo
            # secadora_bascula (que extiende este método) cuando stock está
            # instalado. Aquí solo se cambia el estado.
            record.state = 'confirmado'
