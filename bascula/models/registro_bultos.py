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

    # La variedad se venía guardando como texto en `observaciones`, así que no
    # se podía filtrar ni agrupar por ella. Como campo permite el inventario
    # por variedad y código, que es lo que se consulta en bodega.
    variedad_id = fields.Many2one(
        'secadora.variedad.arroz',
        string='Variedad',
        index=True,
        help='Variedad del arroz empacado. Se toma de los pesajes de entrada '
             'de la orden, y puede corregirse a mano.',
    )

    codigo_variedad = fields.Char(
        string='Código',
        related='variedad_id.codigo',
        store=True,
        help='Código de la variedad, el que identifica la semilla.',
    )

    es_semilla = fields.Boolean(
        string='Es Semilla',
        index=True,
        help='La semilla se lleva aparte del arroz comercial.',
    )

    bodega_id = fields.Many2one(
        'secadora.lugar',
        string='Bodega',
        domain=[('tipo', '=', 'bodega')],
        index=True,
        default=lambda self: self._bodega_por_defecto(),
        help='Bodega donde están los bultos. Nacen en la de la secadora y se '
             'cambian cuando el agricultor se los lleva a la suya.',
    )

    @api.model
    def _bodega_por_defecto(self):
        """La bodega de la secadora, configurable en Ajustes.

        Se resuelve por parámetro y no por nombre: renombrar la bodega no debe
        romper el automatismo.
        """
        bodega_id = int(self.env['ir.config_parameter'].sudo().get_param(
            'bascula.bodega_por_defecto_id', '0') or 0)
        if not bodega_id:
            return False
        bodega = self.env['secadora.lugar'].browse(bodega_id).exists()
        return bodega.id if bodega else False

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

    origen = fields.Selection([
        ('manual', 'Manual'),
        ('tablero', 'Despacho de Tablero'),
    ], string='Origen',
       default='manual',
       readonly=True,
       help='Los registros creados por un despacho del tablero representan '
            'arroz que ya salió de un contenedor: solo un administrador de '
            'báscula puede eliminarlos.')

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
        """Traer variedad y semilla desde los pesajes de entrada de la orden.

        Se rellena `variedad_id` cuando la orden trae una sola variedad, que es
        el caso normal. Si vinieran varias, se deja vacía para que alguien
        elija: inventar una sería peor que preguntar.

        `observaciones` sigue recibiendo el listado en texto, porque en las
        cargas mixtas es la única forma de ver todas las variedades juntas.
        """
        if not (self.producto_id and 'paddy' in (self.producto_id.name or '').lower()):
            self.observaciones = False
            return

        pesajes = self.orden_id.pesaje_entrada_ids
        variedades = pesajes.mapped('variedad_id')
        self.observaciones = ', '.join(variedades.mapped('name')) or False
        if len(variedades) == 1:
            self.variedad_id = variedades
        # La semilla se marca si algún pesaje de la orden venía como semilla.
        if any(pesajes.mapped('es_semilla')):
            self.es_semilla = True

    # ==================== MÉTODOS ====================

    @api.model_create_multi
    def create(self, vals_list):
        # El `default` del campo solo actúa en la interfaz; los registros que
        # crea el tablero al despachar llegan por código y se quedarían sin
        # bodega, que es justo el caso más frecuente.
        bodega_defecto = self._bodega_por_defecto()
        if bodega_defecto:
            for vals in vals_list:
                vals.setdefault('bodega_id', bodega_defecto)
        registros = super().create(vals_list)
        registros.mapped('orden_id').recalcular_servicios()
        registros._registrar_ingreso_en_bodega()
        return registros

    def write(self, vals):
        # La bodega anterior hay que leerla ANTES de escribir; después ya se
        # perdió y el movimiento quedaría sin origen.
        anteriores = {}
        if 'bodega_id' in vals:
            anteriores = {r.id: r.bodega_id for r in self}

        res = super().write(vals)

        if 'cantidad' in vals:
            self.mapped('orden_id').recalcular_servicios()
        if 'bodega_id' in vals:
            self._registrar_cambio_de_bodega(anteriores)
        return res

    # ==================== INVENTARIO EN BODEGA ====================

    def _registrar_ingreso_en_bodega(self):
        """Deja constancia de los bultos que nacen ya ubicados en una bodega."""
        Mov = self.env['secadora.movimiento.bultos'].sudo()
        for rec in self.filtered('bodega_id'):
            Mov.create({
                'registro_bultos_id': rec.id,
                'tipo': 'ingreso',
                'bodega_destino_id': rec.bodega_id.id,
                'cantidad': rec.cantidad,
            })

    def _registrar_cambio_de_bodega(self, anteriores):
        """Un ingreso si no tenía bodega, un traslado si cambió de sitio.

        Se anota la cantidad pendiente y no la empacada: lo que se mueve entre
        bodegas es lo que queda, no lo que ya salió.
        """
        Mov = self.env['secadora.movimiento.bultos'].sudo()
        for rec in self:
            antes = anteriores.get(rec.id)
            ahora = rec.bodega_id
            if antes == ahora:
                continue
            Mov.create({
                'registro_bultos_id': rec.id,
                'tipo': 'traslado' if antes and ahora else 'ingreso',
                'bodega_origen_id': antes.id if antes else False,
                'bodega_destino_id': ahora.id if ahora else False,
                'cantidad': rec.cantidad_pendiente or rec.cantidad,
            })

    def unlink(self):
        es_admin = self.env.user.has_group('bascula.group_bascula_admin')
        for record in self:
            if record.state != 'borrador':
                raise UserError(
                    'No se puede eliminar el registro de bultos %s: está %s. '
                    'Los registros confirmados o facturados no se eliminan.' % (
                        record.name, dict(record._fields['state'].selection).get(record.state))
                )
            if record.despacho_ids:
                raise UserError(
                    'No se puede eliminar el registro %s: tiene despachos '
                    'vinculados a pesajes de salida.' % record.name
                )
            if record.origen == 'tablero' and not es_admin:
                raise UserError(
                    'El registro %s nació de un despacho del tablero (arroz que ya '
                    'salió de un contenedor). Solo un administrador de báscula '
                    'puede eliminarlo.' % record.name
                )
        # Dejar rastro en el chatter de la OS con los datos, para poder
        # reconstruirlo si el borrado fue un error
        for record in self:
            if record.orden_id:
                record.orden_id.message_post(body=(
                    'Registro de bultos eliminado por %s: %s — %s × %s '
                    '(peso promedio %.2f kg, total %.2f kg, empaque %s, origen %s)' % (
                        self.env.user.name,
                        record.producto_id.display_name or '',
                        record.cantidad,
                        record.producto_empaque_id.display_name or '',
                        record.peso_promedio,
                        record.peso_total,
                        dict(record._fields['proveedor_empaque'].selection).get(record.proveedor_empaque, ''),
                        dict(record._fields['origen'].selection).get(record.origen, ''),
                    )
                ))
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
