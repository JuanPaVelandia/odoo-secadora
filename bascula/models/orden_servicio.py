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
        default='Nuevo',
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
        help='Cliente que solicita el servicio'
    )

    fecha_inicio = fields.Datetime(
        string='Fecha de Creación',
        default=fields.Datetime.now,
        required=True,
        readonly=True,
        tracking=True
    )

    fecha_fin = fields.Datetime(
        string='Fecha Finalización',
        tracking=True
    )

    tipo_servicio_id = fields.Many2one(
        'secadora.tipo.operacion',
        string='Tipo de Servicio',
        required=True,
        domain=[('es_servicio', '=', True), ('active', '=', True)],
        tracking=True,
        help='Tipo de servicio a realizar en esta orden'
    )

    # Campo legacy para compatibilidad con código existente
    tipo_servicio = fields.Char(
        string='Tipo Servicio (Legacy)',
        compute='_compute_tipo_servicio_legacy',
        store=True,
        help='Campo calculado para compatibilidad con código existente'
    )

    # ==================== DATOS DEL ARROZ ====================

    observaciones = fields.Text(
        string='Observaciones',
        tracking=True,
        help='Observaciones generales (variedades, instrucciones especiales, etc.)'
    )

    lote_cliente = fields.Char(
        string='Lote/Referencia del Cliente',
        tracking=True,
        help='Referencia o número de lote del cliente'
    )

    # ==================== PESAJES ====================

    pesaje_entrada_ids = fields.One2many(
        'secadora.pesaje',
        'orden_servicio_id',
        string='Pesajes de Entrada',
        domain=[('tipo_proceso', '=', 'entrada')],
        help='Pesajes de entrada del arroz (normalmente uno, pero puede haber varios viajes)'
    )

    pesaje_salida_ids = fields.One2many(
        'secadora.pesaje',
        'orden_servicio_id',
        string='Pesajes de Salida',
        domain=[('tipo_proceso', '=', 'salida')],
        help='Pesajes de salida del arroz (puede haber múltiples)'
    )

    pesaje_count = fields.Integer(
        string='Total Pesajes',
        compute='_compute_pesaje_count',
        store=False
    )

    # ==================== MEDICIONES ENTRADA ====================

    peso_entrada = fields.Float(
        string='Peso Entrada Total (kg)',
        compute='_compute_peso_entrada',
        store=True,
        digits=(12, 2),
        tracking=True,
        help='Suma de todos los pesos netos de los pesajes de entrada'
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

    total_a_facturar = fields.Float(
        string='Total a Facturar',
        compute='_compute_total_a_facturar',
        store=True,
        digits='Product Price',
        help='Total general: servicios + empaques'
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

    # TODO: Descomentar cuando se instale el módulo 'account'
    # factura_id = fields.Many2one(
    #     'account.move',
    #     string='Factura Generada',
    #     readonly=True,
    #     tracking=True,
    #     help='Factura de cliente generada para esta orden'
    # )

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

    def _compute_pesaje_count(self):
        for record in self:
            count = len(record.pesaje_entrada_ids) + len(record.pesaje_salida_ids)
            record.pesaje_count = count

    @api.depends('tipo_servicio_id.codigo')
    def _compute_tipo_servicio_legacy(self):
        """Calcular valor legacy de tipo_servicio para compatibilidad"""
        for record in self:
            if record.tipo_servicio_id:
                codigo = record.tipo_servicio_id.codigo
                # Mapear códigos a valores legacy
                if codigo == 'SECAMIENTO':
                    record.tipo_servicio = 'secamiento'
                elif codigo == 'PRELIMPIEZA':
                    record.tipo_servicio = 'prelimpieza'
                elif codigo == 'SEC_PRELIM':
                    record.tipo_servicio = 'secamiento_prelimpieza'
                else:
                    record.tipo_servicio = codigo.lower()
            else:
                record.tipo_servicio = False

    @api.depends('pesaje_entrada_ids.peso_neto')
    def _compute_peso_entrada(self):
        """Calcular peso total de entrada sumando todos los pesajes de entrada"""
        for record in self:
            record.peso_entrada = sum(record.pesaje_entrada_ids.mapped('peso_neto'))


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

    @api.depends('subtotal_servicios', 'subtotal_empaques')
    def _compute_total_a_facturar(self):
        """Calcular total general: servicios + empaques"""
        for record in self:
            record.total_a_facturar = record.subtotal_servicios + record.subtotal_empaques

    # ==================== MÉTODOS ====================

    @api.model
    def create(self, vals):
        if not vals.get('name') or vals.get('name') in ('/', 'Nuevo'):
            vals['name'] = self.env['ir.sequence'].next_by_code('secadora.orden.servicio') or 'OS-Nuevo'

        # Establecer tipo_servicio_id por defecto si no se proporciona
        if not vals.get('tipo_servicio_id'):
            tipo_default = self.env['secadora.tipo.operacion'].search([
                ('codigo', '=', 'SECAMIENTO'),
                ('es_servicio', '=', True),
                ('active', '=', True)
            ], limit=1)
            if tipo_default:
                vals['tipo_servicio_id'] = tipo_default.id

        return super(OrdenServicio, self).create(vals)

    def action_iniciar_proceso(self):
        for record in self:
            if record.state != 'borrador':
                raise UserError('Solo se pueden iniciar órdenes en estado Borrador.')
            if not record.pesaje_entrada_ids:
                raise UserError('Debe registrar al menos un pesaje de entrada antes de iniciar el proceso.')

            # Aplicar reglas de servicios automáticos
            record.aplicar_reglas_servicios()

            record.write({'state': 'en_proceso'})

    def action_listo_liquidar(self):
        for record in self:
            if record.state != 'en_proceso':
                raise UserError('Solo se pueden liquidar órdenes en proceso.')

            # Validar que modalidad_salida esté seleccionada
            if not record.modalidad_salida:
                raise UserError('Debe seleccionar una Modalidad de Salida antes de liquidar.')

            # Validar que haya al menos un pesaje de salida o bultos registrados
            if not record.pesaje_salida_ids and not record.registro_bultos_ids:
                raise UserError('Debe registrar al menos un pesaje de salida o bultos antes de liquidar.')

            record.write({'state': 'listo_liquidar', 'fecha_fin': fields.Datetime.now()})

    def action_confirmar_liquidacion(self):
        """Confirmar liquidación sin generar factura (para cuando no hay módulo account)"""
        for record in self:
            if record.state != 'listo_liquidar':
                raise UserError('Solo se pueden confirmar órdenes listas para liquidar.')
            record.write({'state': 'liquidado'})

    def action_volver_borrador(self):
        """Volver al estado Borrador desde En Proceso o Listo para Liquidar"""
        for record in self:
            if record.state == 'facturado':
                raise UserError('No se puede volver a Borrador una orden que ya está Facturada.')
            if record.state not in ('en_proceso', 'listo_liquidar', 'liquidado'):
                raise UserError('Solo se puede volver a Borrador desde En Proceso, Listo para Liquidar o Liquidado.')
            record.write({'state': 'borrador', 'fecha_fin': False})

    def action_volver_proceso(self):
        """Volver al estado En Proceso desde Listo para Liquidar o Liquidado"""
        for record in self:
            if record.state == 'facturado':
                raise UserError('No se puede volver a En Proceso una orden que ya está Facturada.')
            if record.state not in ('listo_liquidar', 'liquidado'):
                raise UserError('Solo se puede volver a En Proceso desde Listo para Liquidar o Liquidado.')
            record.write({'state': 'en_proceso', 'fecha_fin': False})

    def aplicar_reglas_servicios(self):
        """Aplicar reglas automáticas de servicios a esta orden"""
        self.ensure_one()

        # Buscar todas las reglas activas
        reglas = self.env['secadora.servicio.regla'].search([('active', '=', True)], order='sequence, id')

        for regla in reglas:
            # Evaluar si la regla aplica
            if regla.evaluar_condicion(self):
                # Verificar si ya existe una línea con este producto
                linea_existente = self.linea_servicio_ids.filtered(
                    lambda l: l.producto_id == regla.producto_id
                )

                if not linea_existente:
                    # Calcular cantidad
                    cantidad = regla.calcular_cantidad(self)

                    # Determinar precio a usar
                    if not regla.incluir_en_factura:
                        precio = 0.0
                    elif regla.precio_unitario:
                        precio = regla.precio_unitario
                    else:
                        precio = regla.producto_id.list_price

                    # Crear línea de servicio
                    self.env['secadora.orden.servicio.linea'].create({
                        'orden_id': self.id,
                        'producto_id': regla.producto_id.id,
                        'base_calculo': regla.base_calculo,
                        'cantidad': cantidad,
                        'precio_unitario': precio,
                        'descripcion': regla.name,
                    })

    def action_crear_pesaje_entrada(self):
        """Crear un pesaje de entrada vinculado a esta orden"""
        self.ensure_one()

        # Crear nuevo pesaje de entrada usando directamente el tipo_servicio_id
        vals = {
            'orden_servicio_id': self.id,
            'tercero_id': self.cliente_id.id if self.cliente_id else False,
            'direccion': 'entrada',
        }

        if self.tipo_servicio_id:
            vals['tipo_operacion_id'] = self.tipo_servicio_id.id

        pesaje = self.env['secadora.pesaje'].create(vals)

        # Abrir el pesaje creado
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'secadora.pesaje',
            'res_id': pesaje.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_crear_pesaje_salida(self):
        """Crear un pesaje de salida vinculado a esta orden"""
        self.ensure_one()

        # Crear nuevo pesaje de salida usando directamente el tipo_servicio_id
        vals = {
            'orden_servicio_id': self.id,
            'tercero_id': self.cliente_id.id if self.cliente_id else False,
            'direccion': 'salida',
        }

        if self.tipo_servicio_id:
            vals['tipo_operacion_id'] = self.tipo_servicio_id.id

        pesaje = self.env['secadora.pesaje'].create(vals)

        # Abrir el pesaje creado
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'secadora.pesaje',
            'res_id': pesaje.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_ver_pesajes(self):
        """Ver todos los pesajes vinculados a esta orden"""
        self.ensure_one()

        pesaje_ids = self.pesaje_entrada_ids.ids + self.pesaje_salida_ids.ids

        return {
            'type': 'ir.actions.act_window',
            'name': f'Pesajes - {self.name}',
            'res_model': 'secadora.pesaje',
            'domain': [('id', 'in', pesaje_ids)],
            'view_mode': 'list,form',
            'target': 'current',
            'context': {'default_orden_servicio_id': self.id}
        }

    # TODO: Descomentar cuando se instale el módulo 'account'
    # def action_generar_factura(self):
    #     self.ensure_one()
    #     if self.state not in ['listo_liquidar', 'liquidado']:
    #         raise UserError('La orden debe estar lista para liquidar.')
    #     if self.factura_id:
    #         raise UserError('Ya existe una factura generada para esta orden.')
    #
    #     lines = self._preparar_lineas_factura()
    #     if not lines:
    #         raise UserError('No hay líneas para facturar.')
    #
    #     factura = self.env['account.move'].create({
    #         'move_type': 'out_invoice',
    #         'partner_id': self.cliente_id.id,
    #         'invoice_date': fields.Date.today(),
    #         'invoice_origin': self.name,
    #         'invoice_line_ids': [(0, 0, line) for line in lines],
    #     })
    #
    #     self.write({'factura_id': factura.id, 'state': 'facturado'})
    #
    #     return {
    #         'type': 'ir.actions.act_window',
    #         'res_model': 'account.move',
    #         'res_id': factura.id,
    #         'view_mode': 'form',
    #         'target': 'current',
    #     }
    #
    # def _preparar_lineas_factura(self):
    #     self.ensure_one()
    #     lines = []
    #
    #     registros_empaques = self.registro_bultos_ids.filtered(
    #         lambda r: r.proveedor_empaque == 'secadora' and r.cobrar_empaque
    #     )
    #
    #     for registro in registros_empaques:
    #         lines.append({
    #             'product_id': registro.producto_empaque_id.id,
    #             'quantity': registro.cantidad,
    #             'price_unit': registro.precio_unitario_empaque,
    #             'name': f'{registro.producto_empaque_id.name} - {registro.fecha}',
    #         })
    #
    #     for servicio in self.linea_servicio_ids:
    #         lines.append({
    #             'product_id': servicio.producto_id.id,
    #             'quantity': servicio.cantidad,
    #             'price_unit': servicio.precio_unitario,
    #             'name': servicio.descripcion or servicio.producto_id.name,
    #         })
    #
    #     return lines

    def action_cancelar(self):
        for record in self:
            # TODO: Descomentar cuando se instale el módulo 'account'
            # if record.state == 'facturado':
            #     raise UserError('No se puede cancelar una orden facturada.')
            record.state = 'cancelado'

    # TODO: Descomentar cuando se instale el módulo 'account'
    # def action_ver_factura(self):
    #     self.ensure_one()
    #     if not self.factura_id:
    #         raise UserError('No hay factura generada para esta orden.')
    #     return {
    #         'type': 'ir.actions.act_window',
    #         'res_model': 'account.move',
    #         'res_id': self.factura_id.id,
    #         'view_mode': 'form',
    #         'target': 'current',
    #     }