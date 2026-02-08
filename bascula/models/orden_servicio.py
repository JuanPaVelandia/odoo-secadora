# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


class OrdenServicio(models.Model):
    _name = 'secadora.orden.servicio'
    _description = 'Orden de Servicio para Terceros'
    _order = 'fecha_inicio desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Número de Orden',
        required=True,
        readonly=True,
        default='/',
        copy=False,
        tracking=True,
        help='Número de orden de servicio generado automáticamente'
    )

    cliente_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        required=True,
        tracking=True,
        index=True,
        domain=[('customer_rank', '>', 0)],
        help='Cliente que solicita el servicio'
    )

    fecha_inicio = fields.Datetime(
        string='Fecha Inicio',
        default=fields.Datetime.now,
        required=True,
        tracking=True
    )

    fecha_fin = fields.Datetime(
        string='Fecha Finalización',
        tracking=True
    )

    tipo_servicio = fields.Selection([
        ('secamiento', 'Secamiento'),
        ('prelimpieza', 'Prelimpieza'),
        ('secamiento_prelimpieza', 'Secamiento + Prelimpieza'),
    ], string='Tipo de Servicio',
       required=True,
       default='secamiento',
       tracking=True,
       help='Tipo de servicio principal a realizar')

    # ==================== DATOS DEL ARROZ ====================

    variedad_id = fields.Many2one(
        'secadora.variedad.arroz',
        string='Variedad de Arroz',
        tracking=True,
        help='Variedad del arroz (ej: Fedearroz 67)'
    )

    lote_cliente = fields.Char(
        string='Lote/Referencia del Cliente',
        tracking=True,
        help='Referencia o número de lote del cliente'
    )

    # ==================== PESAJES ====================

    pesaje_entrada_id = fields.Many2one(
        'secadora.pesaje',
        string='Pesaje de Entrada',
        readonly=True,
        help='Pesaje cuando ingresa el arroz'
    )

    pesaje_salida_ids = fields.One2many(
        'secadora.pesaje',
        'orden_servicio_id',
        string='Pesajes de Salida',
        domain=[('tipo_proceso', '=', 'salida')],
        help='Pesajes de salida del arroz (puede haber múltiples)'
    )

    # ==================== MEDICIONES ENTRADA ====================

    peso_entrada = fields.Float(
        string='Peso Entrada (kg)',
        digits=(12, 2),
        tracking=True,
        help='Peso del arroz al ingresar'
    )

    humedad_inicial = fields.Float(
        string='Humedad Inicial (%)',
        digits=(5, 2),
        tracking=True,
        help='Porcentaje de humedad al ingresar'
    )

    impureza_inicial = fields.Float(
        string='Impureza Inicial (%)',
        digits=(5, 2),
        tracking=True,
        help='Porcentaje de impureza al ingresar'
    )

    # ==================== ESTIMACIONES ====================

    merma_estimada_porcentaje = fields.Float(
        string='Merma Estimada (%)',
        compute='_compute_merma_estimada',
        store=True,
        digits=(5, 2),
        help='Estimación de merma basada en humedad e impureza'
    )

    peso_salida_estimado = fields.Float(
        string='Peso Salida Estimado (kg)',
        compute='_compute_peso_salida_estimado',
        store=True,
        digits=(12, 2),
        help='Estimación del peso de salida después de secar'
    )

    # ==================== MODALIDAD DE SALIDA ====================

    modalidad_salida = fields.Selection([
        ('bultos', 'Empaque en Bultos'),
        ('granel', 'Granel (Pesaje Báscula)'),
        ('silobolsa', 'Almacenamiento en Silobolsa'),
    ], string='Modalidad de Salida',
       tracking=True,
       help='Cómo se entregará el arroz al cliente')

    # ==================== REGISTRO DE BULTOS ====================

    registro_bultos_ids = fields.One2many(
        'secadora.registro.bultos',
        'orden_id',
        string='Registro de Bultos Empacados',
        help='Registro de bultos empacados día a día'
    )

    total_bultos = fields.Integer(
        string='Total Bultos',
        compute='_compute_totales_bultos',
        store=True,
        help='Cantidad total de bultos empacados'
    )

    peso_total_bultos = fields.Float(
        string='Peso Total Bultos (kg)',
        compute='_compute_totales_bultos',
        store=True,
        digits=(12, 2),
        help='Peso total según conteo de bultos'
    )

    total_empaques_secadora = fields.Integer(
        string='Empaques Secadora',
        compute='_compute_totales_bultos',
        store=True,
        help='Bultos provistos por la secadora (se cobran)'
    )

    total_empaques_cliente = fields.Integer(
        string='Empaques Cliente',
        compute='_compute_totales_bultos',
        store=True,
        help='Bultos provistos por el cliente (no se cobran)'
    )

    subtotal_empaques = fields.Float(
        string='Subtotal Empaques',
        compute='_compute_totales_bultos',
        store=True,
        digits='Product Price',
        help='Total a cobrar por empaques provistos por secadora'
    )

    # ==================== PESO SALIDA BÁSCULA ====================

    peso_salida_bascula = fields.Float(
        string='Peso Salida Báscula (kg)',
        compute='_compute_peso_salida_bascula',
        store=True,
        digits=(12, 2),
        help='Suma de pesos netos de todos los pesajes de salida'
    )

    # ==================== PESO SALIDA REAL ====================

    peso_salida_real = fields.Float(
        string='Peso Salida Real (kg)',
        compute='_compute_peso_salida_real',
        store=True,
        digits=(12, 2),
        help='Peso real de salida: viene de bultos o báscula según modalidad'
    )

    # ==================== MERMA REAL ====================

    merma_real = fields.Float(
        string='Merma Real (kg)',
        compute='_compute_merma_real',
        store=True,
        digits=(12, 2),
        help='Diferencia entre peso entrada y peso salida'
    )

    merma_real_porcentaje = fields.Float(
        string='Merma Real (%)',
        compute='_compute_merma_real',
        store=True,
        digits=(5, 2),
        help='Porcentaje de merma real'
    )

    # ==================== SERVICIOS ADICIONALES ====================

    linea_servicio_ids = fields.One2many(
        'secadora.orden.servicio.linea',
        'orden_id',
        string='Servicios Adicionales',
        help='Servicios adicionales a facturar (cargue, descargue, limpieza, etc.)'
    )

    subtotal_servicios = fields.Float(
        string='Subtotal Servicios',
        compute='_compute_subtotal_servicios',
        store=True,
        digits='Product Price',
        help='Total de servicios adicionales'
    )

    # ==================== SERVICIOS RÁPIDOS ====================

    servicio_descargue = fields.Boolean(
        string='Servicio de Descargue',
        help='Marcar si se prestó servicio de descargue'
    )

    servicio_cargue = fields.Boolean(
        string='Servicio de Cargue',
        help='Marcar si se prestó servicio de cargue'
    )

    servicio_limpieza_adicional = fields.Boolean(
        string='Limpieza Adicional',
        help='Marcar si se prestó servicio de limpieza adicional'
    )

    # ==================== FACTURACIÓN ====================

    factura_id = fields.Many2one(
        'account.move',
        string='Factura Generada',
        readonly=True,
        tracking=True,
        help='Factura de cliente generada para esta orden'
    )

    # ==================== ESTADOS ====================

    state = fields.Selection([
        ('borrador', 'Borrador'),
        ('en_proceso', 'En Proceso'),
        ('listo_liquidar', 'Listo para Liquidar'),
        ('liquidado', 'Liquidado'),
        ('facturado', 'Facturado'),
        ('cancelado', 'Cancelado'),
    ], string='Estado',
       default='borrador',
       required=True,
       tracking=True)

    # ==================== CAMPOS COMPUTADOS ====================

    @api.depends('humedad_inicial', 'impureza_inicial')
    def _compute_merma_estimada(self):
        for record in self:
            if record.humedad_inicial or record.impureza_inicial:
                humedad = record.humedad_inicial or 0
                impureza = record.impureza_inicial or 0
                record.merma_estimada_porcentaje = humedad + impureza
            else:
                record.merma_estimada_porcentaje = 0.0

    @api.depends('peso_entrada', 'merma_estimada_porcentaje')
    def _compute_peso_salida_estimado(self):
        for record in self:
            if record.peso_entrada and record.merma_estimada_porcentaje:
                merma_kg = record.peso_entrada * (record.merma_estimada_porcentaje / 100)
                record.peso_salida_estimado = record.peso_entrada - merma_kg
            else:
                record.peso_salida_estimado = record.peso_entrada

    @api.depends('registro_bultos_ids.cantidad',
                 'registro_bultos_ids.peso_promedio',
                 'registro_bultos_ids.proveedor_empaque',
                 'registro_bultos_ids.subtotal_empaque')
    def _compute_totales_bultos(self):
        for record in self:
            total_bultos = 0
            peso_total = 0
            empaques_secadora = 0
            empaques_cliente = 0
            subtotal_empaques = 0

            for linea in record.registro_bultos_ids:
                total_bultos += linea.cantidad
                peso_total += linea.peso_total

                if linea.proveedor_empaque == 'secadora':
                    empaques_secadora += linea.cantidad
                    subtotal_empaques += linea.subtotal_empaque
                else:
                    empaques_cliente += linea.cantidad

            record.total_bultos = total_bultos
            record.peso_total_bultos = peso_total
            record.total_empaques_secadora = empaques_secadora
            record.total_empaques_cliente = empaques_cliente
            record.subtotal_empaques = subtotal_empaques

    @api.depends('pesaje_salida_ids.peso_neto')
    def _compute_peso_salida_bascula(self):
        for record in self:
            record.peso_salida_bascula = sum(
                record.pesaje_salida_ids.mapped('peso_neto')
            )

    @api.depends('modalidad_salida', 'peso_total_bultos', 'peso_salida_bascula')
    def _compute_peso_salida_real(self):
        for record in self:
            if record.modalidad_salida == 'bultos':
                record.peso_salida_real = record.peso_total_bultos
            else:
                record.peso_salida_real = record.peso_salida_bascula

    @api.depends('peso_entrada', 'peso_salida_real')
    def _compute_merma_real(self):
        for record in self:
            if record.peso_entrada and record.peso_salida_real:
                record.merma_real = record.peso_entrada - record.peso_salida_real
                if record.peso_entrada > 0:
                    record.merma_real_porcentaje = (record.merma_real / record.peso_entrada * 100)
                else:
                    record.merma_real_porcentaje = 0.0
            else:
                record.merma_real = 0.0
                record.merma_real_porcentaje = 0.0

    @api.depends('linea_servicio_ids.subtotal')
    def _compute_subtotal_servicios(self):
        for record in self:
            record.subtotal_servicios = sum(record.linea_servicio_ids.mapped('subtotal'))

    # ==================== MÉTODOS ====================

    @api.model
    def create(self, vals):
        if vals.get('name', '/') == '/':
            vals['name'] = self.env['ir.sequence'].next_by_code('secadora.orden.servicio') or '/'
        return super(OrdenServicio, self).create(vals)

    def action_iniciar_proceso(self):
        for record in self:
            if record.state != 'borrador':
                raise UserError('Solo se pueden iniciar órdenes en estado Borrador.')
            if not record.peso_entrada:
                raise UserError('Debe registrar el peso de entrada antes de iniciar el proceso.')
            record.write({'state': 'en_proceso', 'fecha_inicio': fields.Datetime.now()})

    def action_listo_liquidar(self):
        for record in self:
            if record.state != 'en_proceso':
                raise UserError('Solo se pueden liquidar órdenes en proceso.')
            if not record.peso_salida_real:
                raise UserError('Debe registrar el peso de salida antes de liquidar.')
            record.write({'state': 'listo_liquidar', 'fecha_fin': fields.Datetime.now()})

    def action_volver_proceso(self):
        for record in self:
            record.state = 'en_proceso'

    def action_generar_factura(self):
        self.ensure_one()
        if self.state not in ['listo_liquidar', 'liquidado']:
            raise UserError('La orden debe estar lista para liquidar.')
        if self.factura_id:
            raise UserError('Ya existe una factura generada para esta orden.')

        lines = self._preparar_lineas_factura()
        if not lines:
            raise UserError('No hay líneas para facturar.')

        factura = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.cliente_id.id,
            'invoice_date': fields.Date.today(),
            'invoice_origin': self.name,
            'invoice_line_ids': [(0, 0, line) for line in lines],
        })

        self.write({'factura_id': factura.id, 'state': 'facturado'})

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': factura.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _preparar_lineas_factura(self):
        self.ensure_one()
        lines = []

        registros_empaques = self.registro_bultos_ids.filtered(
            lambda r: r.proveedor_empaque == 'secadora' and r.cobrar_empaque
        )

        for registro in registros_empaques:
            lines.append({
                'product_id': registro.producto_empaque_id.id,
                'quantity': registro.cantidad,
                'price_unit': registro.precio_unitario_empaque,
                'name': f'{registro.producto_empaque_id.name} - {registro.fecha}',
            })

        for servicio in self.linea_servicio_ids:
            lines.append({
                'product_id': servicio.producto_id.id,
                'quantity': servicio.cantidad,
                'price_unit': servicio.precio_unitario,
                'name': servicio.descripcion or servicio.producto_id.name,
            })

        return lines

    def action_cancelar(self):
        for record in self:
            if record.state == 'facturado':
                raise UserError('No se puede cancelar una orden facturada.')
            record.state = 'cancelado'

    def action_ver_factura(self):
        self.ensure_one()
        if not self.factura_id:
            raise UserError('No hay factura generada para esta orden.')
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.factura_id.id,
            'view_mode': 'form',
            'target': 'current',
        }