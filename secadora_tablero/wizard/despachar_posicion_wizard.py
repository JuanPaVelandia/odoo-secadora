# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError


class DespacharPosicionLinea(models.TransientModel):
    _name = 'secadora.despachar.posicion.linea'
    _description = 'Línea de Despacho de Posición'

    wizard_id = fields.Many2one(
        'secadora.despachar.posicion.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade',
    )
    producto_id = fields.Many2one(
        'product.product',
        string='Producto',
        required=True,
        domain=[('categ_id.name', '=', 'Arroz')],
        help='Producto de arroz a despachar (ej: Arroz Paddy Seco)',
    )
    producto_empaque_id = fields.Many2one(
        'product.product',
        string='Tipo Empaque',
        required=True,
        domain=[('type', '=', 'consu')],
        help='Tipo de empaque (ej: Bulto 50 kg)',
    )
    cantidad_bultos = fields.Integer(
        string='Cantidad Bultos',
        default=0,
    )
    peso_promedio = fields.Float(
        string='Peso Promedio (kg)',
        digits=(8, 2),
        default=50.0,
    )
    peso_subtotal = fields.Float(
        string='Peso Subtotal (kg)',
        digits=(12, 2),
        compute='_compute_peso_subtotal',
        store=True,
    )
    proveedor_empaque = fields.Selection([
        ('secadora', 'Secadora'),
        ('cliente', 'Cliente'),
    ], string='Proveedor Empaque',
       default='secadora',
       required=True,
    )

    @api.depends('cantidad_bultos', 'peso_promedio')
    def _compute_peso_subtotal(self):
        for rec in self:
            rec.peso_subtotal = rec.cantidad_bultos * rec.peso_promedio

    @api.onchange('producto_empaque_id')
    def _onchange_producto_empaque_id(self):
        if self.producto_empaque_id:
            nombre = self.producto_empaque_id.name or ''
            if '50' in nombre:
                self.peso_promedio = 50.0
            elif '25' in nombre:
                self.peso_promedio = 25.0
            elif '10' in nombre:
                self.peso_promedio = 10.0


class DespacharPosicionWizard(models.TransientModel):
    _name = 'secadora.despachar.posicion.wizard'
    _description = 'Despachar Posiciones de Arroz'

    sitio_id = fields.Many2one(
        'secadora.sitio.muestra',
        string='Ubicación',
        required=True,
        readonly=True,
    )
    posicion_ids = fields.Many2many(
        'secadora.posicion.arroz',
        string='Posiciones a Despachar',
        domain="[('sitio_id', '=', sitio_id), ('state', '=', 'activo')]",
    )
    peso_total = fields.Float(
        string='Peso Posiciones (kg)',
        digits=(12, 2),
        compute='_compute_peso_total',
    )

    # Info computed desde posiciones
    cliente_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        compute='_compute_cliente_orden',
    )
    orden_servicio_id = fields.Many2one(
        'secadora.orden.servicio',
        string='Orden de Servicio',
        compute='_compute_cliente_orden',
    )
    modalidad_salida = fields.Selection(
        related='orden_servicio_id.modalidad_salida',
        string='Modalidad',
        readonly=True,
    )

    tipo_empaque = fields.Selection([
        ('total', 'Empaque Total (la tarjeta desaparece)'),
        ('parcial', 'Empaque Parcial (la tarjeta sigue activa)'),
    ], string='Tipo de Empaque',
       required=True,
       default='total',
    )

    # Líneas de despacho
    linea_ids = fields.One2many(
        'secadora.despachar.posicion.linea',
        'wizard_id',
        string='Líneas de Despacho',
    )
    peso_total_lineas = fields.Float(
        string='Peso Líneas (kg)',
        digits=(12, 2),
        compute='_compute_peso_total_lineas',
    )
    diferencia_peso = fields.Float(
        string='Diferencia (kg)',
        digits=(12, 2),
        compute='_compute_diferencia_peso',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'posicion_ids' in fields_list and res.get('sitio_id') and not res.get('posicion_ids'):
            posiciones = self.env['secadora.posicion.arroz'].search([
                ('sitio_id', '=', res['sitio_id']),
                ('state', '=', 'activo'),
            ])
            res['posicion_ids'] = [fields.Command.set(posiciones.ids)]

        # Validar posiciones
        if res.get('posicion_ids'):
            pos_ids = []
            for cmd in res['posicion_ids']:
                if cmd[0] == 6:  # Command.set
                    pos_ids = cmd[2]
            posiciones = self.env['secadora.posicion.arroz'].browse(pos_ids)

            terceros = posiciones.mapped('tercero_id')
            if len(terceros) > 1:
                raise UserError(
                    'Las posiciones pertenecen a distintos terceros.\n'
                    'Solo se puede despachar posiciones del mismo agricultor a la vez.'
                )

            ordenes = posiciones.mapped('orden_servicio_id')

            # Precargar línea de bultos solo si la modalidad es bultos
            orden = ordenes[0] if ordenes else False
            if orden and orden.modalidad_salida == 'bultos':
                producto_seco = self.env['product.template'].search(
                    [('name', '=', 'Arroz Paddy Seco')], limit=1
                )
                empaque_default = self.env.ref(
                    'bascula.product_bulto_50kg', raise_if_not_found=False
                )
                if producto_seco and empaque_default:
                    res['linea_ids'] = [(0, 0, {
                        'producto_id': producto_seco.product_variant_id.id,
                        'producto_empaque_id': empaque_default.id,
                        'cantidad_bultos': 0,
                        'peso_promedio': 50.0,
                        'proveedor_empaque': 'secadora',
                    })]

        return res

    @api.depends('posicion_ids', 'posicion_ids.peso_kg')
    def _compute_peso_total(self):
        for rec in self:
            rec.peso_total = sum(rec.posicion_ids.mapped('peso_kg'))

    @api.depends('posicion_ids', 'posicion_ids.tercero_id', 'posicion_ids.orden_servicio_id')
    def _compute_cliente_orden(self):
        for rec in self:
            if rec.posicion_ids:
                rec.cliente_id = rec.posicion_ids[0].tercero_id
                rec.orden_servicio_id = rec.posicion_ids[0].orden_servicio_id
            else:
                rec.cliente_id = False
                rec.orden_servicio_id = False

    @api.depends('linea_ids.peso_subtotal')
    def _compute_peso_total_lineas(self):
        for rec in self:
            rec.peso_total_lineas = sum(rec.linea_ids.mapped('peso_subtotal'))

    @api.depends('peso_total', 'peso_total_lineas')
    def _compute_diferencia_peso(self):
        for rec in self:
            rec.diferencia_peso = rec.peso_total - rec.peso_total_lineas

    def action_despachar(self):
        """Despachar posiciones según la modalidad de salida de la OS."""
        self.ensure_one()

        if not self.posicion_ids:
            raise UserError('Debe seleccionar al menos una posición.')

        # Validar mismo tercero
        terceros = self.posicion_ids.mapped('tercero_id')
        if len(terceros) > 1:
            raise UserError('Todas las posiciones deben pertenecer al mismo tercero.')

        ordenes = self.posicion_ids.mapped('orden_servicio_id')
        modalidad = self.modalidad_salida

        if modalidad == 'bultos':
            lineas_con_cantidad = self.linea_ids.filtered(lambda l: l.cantidad_bultos > 0)
            if not lineas_con_cantidad:
                raise UserError('Debe registrar al menos una línea con cantidad mayor a 0.')
            self._crear_registro_bultos(lineas_con_cantidad)

        # Marcar posiciones como despachadas si es granel/silobolsa, sin OS (compra), o empaque total
        if modalidad in ('granel', 'silobolsa') or not modalidad or self.tipo_empaque == 'total':
            MovimientoArroz = self.env['secadora.movimiento.arroz']
            etiqueta = modalidad or 'directo'
            for pos in self.posicion_ids:
                pos.write({'state': 'despachado'})
                MovimientoArroz.create({
                    'posicion_id': pos.id,
                    'sitio_origen_id': pos.sitio_id.id if pos.sitio_id else False,
                    'peso_kg': pos.peso_kg,
                    'tipo': 'despacho',
                    'notas': 'Despacho %s desde %s' % (etiqueta, self.sitio_id.name),
                })

        return {'type': 'ir.actions.act_window_close'}

    def _crear_registro_bultos(self, lineas):
        """Crear registros de bultos en las órdenes de servicio.

        Si ya existe un registro con el mismo producto, empaque, peso promedio,
        proveedor y observaciones, se suma la cantidad en vez de crear uno nuevo.
        """
        RegistroBultos = self.env['secadora.registro.bultos']

        # Agrupar por OS (normalmente será una sola)
        ordenes = self.posicion_ids.mapped('orden_servicio_id')
        variedades = self.posicion_ids.mapped('variedad_id')
        texto_variedades = ', '.join(v.name for v in variedades if v) or ''

        for os in ordenes:
            for linea in lineas:
                # Solo poner variedad en observaciones si el producto es paddy
                es_paddy = 'paddy' in (linea.producto_id.name or '').lower()
                observaciones = texto_variedades if es_paddy else ''

                # Buscar registro existente con mismos atributos
                existente = RegistroBultos.search([
                    ('orden_id', '=', os.id),
                    ('producto_id', '=', linea.producto_id.id),
                    ('producto_empaque_id', '=', linea.producto_empaque_id.id),
                    ('peso_promedio', '=', linea.peso_promedio),
                    ('proveedor_empaque', '=', linea.proveedor_empaque),
                    ('observaciones', '=', observaciones),
                    ('despachado', '=', False),
                ], limit=1)

                if existente:
                    existente.write({
                        'cantidad': existente.cantidad + linea.cantidad_bultos,
                    })
                else:
                    RegistroBultos.create({
                        'orden_id': os.id,
                        'producto_id': linea.producto_id.id,
                        'cantidad': linea.cantidad_bultos,
                        'peso_promedio': linea.peso_promedio,
                        'producto_empaque_id': linea.producto_empaque_id.id,
                        'proveedor_empaque': linea.proveedor_empaque,
                        'precio_unitario_empaque': linea.producto_empaque_id.list_price,
                        'observaciones': observaciones,
                    })
