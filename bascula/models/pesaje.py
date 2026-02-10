# -*- coding: utf-8 -*-

from datetime import datetime
import pytz
from odoo import models, fields, api
from odoo.exceptions import UserError


class SecadoraPesaje(models.Model):
    _name = 'secadora.pesaje'
    _description = 'Registro de Pesaje'
    _order = 'name desc'

    # Información básica
    name = fields.Char(
        string='Número',
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: 'Nuevo'
    )
    fecha = fields.Date(
        string='Fecha',
        required=True,
        default=lambda self: self._get_colombia_date(),
        index=True,
        readonly=True
    )
    hora_entrada = fields.Datetime(string='Hora Entrada')
    hora_salida = fields.Datetime(string='Hora Salida')

    # Tipo de Operación (desde catálogo)
    tipo_operacion_id = fields.Many2one(
        'secadora.tipo.operacion',
        string='Tipo de Operación',
        required=True,
        index=True,
        help='Selecciona el tipo de operación: compra, venta, servicio de secamiento, etc.'
    )

    # Campo legacy mantenido por compatibilidad (computed)
    tipo_proceso = fields.Selection([
        ('entrada', 'Entrada'),
        ('salida', 'Salida'),
    ], string='Dirección', compute='_compute_tipo_proceso', store=True, index=True)

    state = fields.Selection([
        ('borrador', 'Borrador'),
        ('en_transito', 'En Tránsito'),
        ('completado', 'Completado'),
        ('cancelado', 'Cancelado'),
    ], string='Estado', default='borrador', required=True, index=True)

    # Vehículo y transporte
    vehiculo_id = fields.Many2one(
        'secadora.vehiculo',
        string='Vehículo',
        required=True,
        index=True
    )
    placa_texto = fields.Char(
        string='Placa',
        related='vehiculo_id.placa',
        store=True,
        readonly=True
    )
    conductor_id = fields.Many2one(
        'secadora.conductor',
        string='Conductor'
    )
    cedula_conductor = fields.Char(
        string='Cédula Conductor',
        related='conductor_id.cedula',
        readonly=True
    )
    transportadora_id = fields.Many2one(
        'secadora.transportadora',
        string='Transportadora'
    )

    # Tercero (agricultor/cliente)
    tercero_id = fields.Many2one(
        'res.partner',
        string='Tercero (Agricultor/Cliente)',
        required=True,
        index=True
    )
    nit_tercero = fields.Char(
        string='NIT/CC',
        compute='_compute_nit_tercero',
        store=True,
        readonly=True
    )

    # Origen y destino
    origen_id = fields.Many2one(
        'secadora.lugar',
        string='Origen',
        help='Lugar de origen (finca, bodega, etc.)'
    )
    lote_finca = fields.Char(
        string='Lote',
        help='Lote o número específico (ej: 180, La Esperanza)'
    )
    destino_id = fields.Many2one(
        'secadora.lugar',
        string='Destino',
        help='Lugar de destino (finca, bodega, etc.)'
    )

    # Producto
    producto_id = fields.Many2one(
        'product.product',
        string='Producto',
        help='Producto del inventario',
        domain=[('type', 'in', ['product', 'consu'])],
        index=True
    )
    variedad_id = fields.Many2one(
        'secadora.variedad.arroz',
        string='Variedad de Arroz'
    )

    # Vínculo con Orden de Servicio
    orden_servicio_id = fields.Many2one(
        'secadora.orden.servicio',
        string='Orden de Servicio',
        index=True,
        help='Orden de servicio a la que pertenece este pesaje (opcional para compra/venta)'
    )

    # Dirección del pesaje (reemplaza tipo_proceso para mayor claridad)
    direccion = fields.Selection([
        ('entrada', 'Entrada'),
        ('salida', 'Salida'),
    ], string='Dirección',
       required=True,
       default='entrada',
       help='Dirección del pesaje: Entrada o Salida')

    # Pesaje
    peso_actual = fields.Float(
        string='Peso Actual (Kg)',
        help='Peso en tiempo real desde la báscula',
        digits=(12, 2),
        readonly=True
    )
    escuchando_bascula = fields.Boolean(
        string='Escuchando Báscula',
        default=False,
        help='Indica si el sistema está recibiendo peso de la báscula'
    )
    peso_bruto = fields.Float(
        string='Peso Lleno (Kg)',
        help='Primera pesada - Vehículo lleno',
        digits=(12, 2)
    )
    peso_tara = fields.Float(
        string='Peso Vacío (Kg)',
        help='Segunda pesada - Vehículo vacío',
        digits=(12, 2)
    )
    peso_neto = fields.Float(
        string='Peso Neto (Kg)',
        compute='_compute_peso_neto',
        store=True,
        readonly=True,
        digits=(12, 2)
    )

    # Calidad
    humedad = fields.Float(
        string='Humedad (%)',
        digits=(5, 2)
    )
    grano_partido = fields.Float(
        string='Grano Partido (%)',
        digits=(5, 2)
    )
    impurezas = fields.Float(
        string='Impurezas (%)',
        digits=(5, 2)
    )

    # Remisión
    bultos = fields.Integer(string='Bultos')
    precio = fields.Float(
        string='Precio',
        digits=(12, 2)
    )
    plazo = fields.Char(string='Plazo')
    observaciones = fields.Text(string='Observaciones')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('secadora.pesaje') or 'Nuevo'
        return super().create(vals_list)

    @api.onchange('tipo_operacion_id')
    def _onchange_tipo_operacion_direccion(self):
        """Auto-llenar dirección si el tipo de operación tiene dirección fija (compra/venta)"""
        if self.tipo_operacion_id and self.tipo_operacion_id.direccion_fija:
            # Compra/Venta tienen dirección automática
            self.direccion = self.tipo_operacion_id.direccion_fija

    @api.onchange('orden_servicio_id')
    def _onchange_orden_servicio(self):
        """Auto-llenar campos cuando se selecciona una orden de servicio"""
        if self.orden_servicio_id:
            # Auto-llenar tercero desde el cliente de la orden
            if self.orden_servicio_id.cliente_id:
                self.tercero_id = self.orden_servicio_id.cliente_id
            # Auto-llenar tipo_operacion_id desde el tipo de servicio de la orden
            if self.orden_servicio_id.tipo_servicio_id:
                self.tipo_operacion_id = self.orden_servicio_id.tipo_servicio_id

    @api.depends('direccion', 'tipo_operacion_id')
    def _compute_tipo_proceso(self):
        """Compute tipo_proceso desde direccion para mantener compatibilidad LEGACY"""
        for record in self:
            if record.direccion:
                record.tipo_proceso = record.direccion
            elif record.tipo_operacion_id:
                # Fallback a direccion legacy del tipo_operacion
                record.tipo_proceso = record.tipo_operacion_id.direccion or 'entrada'
            else:
                record.tipo_proceso = 'entrada'

    @api.depends('peso_bruto', 'peso_tara')
    def _compute_peso_neto(self):
        for record in self:
            if record.peso_bruto and record.peso_tara:
                record.peso_neto = record.peso_bruto - record.peso_tara
            else:
                record.peso_neto = 0.0

    @api.depends('tercero_id')
    def _compute_nit_tercero(self):
        for record in self:
            record.nit_tercero = record.tercero_id.vat or ''

    @api.constrains('orden_servicio_id', 'tercero_id')
    def _check_tercero_matches_orden(self):
        """Validar que el tercero del pesaje coincida con el cliente de la orden de servicio"""
        for record in self:
            if record.orden_servicio_id and record.tercero_id:
                if record.tercero_id != record.orden_servicio_id.cliente_id:
                    raise UserError(
                        f'El tercero del pesaje ({record.tercero_id.name}) no coincide con '
                        f'el cliente de la orden de servicio ({record.orden_servicio_id.cliente_id.name}).\n\n'
                        f'Solo se pueden vincular pesajes del mismo cliente a una orden de servicio.'
                    )

    @api.constrains('tipo_operacion_id', 'direccion')
    def _check_direccion_coherente(self):
        """Validar que la dirección sea coherente con el tipo de operación"""
        for record in self:
            if record.tipo_operacion_id and record.tipo_operacion_id.direccion_fija:
                # Si el tipo de operación tiene dirección fija, debe coincidir
                if record.direccion != record.tipo_operacion_id.direccion_fija:
                    tipo_nombre = record.tipo_operacion_id.name
                    direccion_esperada = 'Entrada' if record.tipo_operacion_id.direccion_fija == 'entrada' else 'Salida'
                    direccion_actual = 'Entrada' if record.direccion == 'entrada' else 'Salida'

                    raise UserError(
                        f'⚠️ ERROR DE DIRECCIÓN\n\n'
                        f'Tipo de Operación: {tipo_nombre}\n'
                        f'Dirección esperada: {direccion_esperada}\n'
                        f'Dirección seleccionada: {direccion_actual}\n\n'
                        f'Una "{tipo_nombre}" siempre debe ser "{direccion_esperada}".\n'
                        f'Por favor corrija la dirección antes de guardar.'
                    )

    def _get_colombia_date(self):
        """Obtiene la fecha actual de Colombia (America/Bogota)"""
        colombia_tz = pytz.timezone('America/Bogota')
        utc_now = datetime.now(pytz.UTC)
        colombia_now = utc_now.astimezone(colombia_tz)
        return colombia_now.date()

    def _get_colombia_time(self):
        """Obtiene la hora actual de Colombia (America/Bogota)"""
        colombia_tz = pytz.timezone('America/Bogota')
        utc_now = datetime.now(pytz.UTC)
        colombia_now = utc_now.astimezone(colombia_tz)
        # Convertir de vuelta a UTC para almacenar en Odoo
        return colombia_now.astimezone(pytz.UTC).replace(tzinfo=None)

    def action_primera_pesada(self):
        for record in self:
            if record.state != 'borrador':
                raise UserError('Solo se puede registrar la primera pesada en estado borrador.')

            # Obtener peso actual de la báscula
            peso_a_usar = record.peso_actual if record.peso_actual > 0 else 0

            # Si no hay peso_actual en este registro (ej: registro nuevo sin guardar),
            # buscar el último peso disponible en la BD
            if peso_a_usar <= 0:
                ultimo_pesaje = self.search([
                    ('peso_actual', '>', 0),
                    ('state', 'in', ['borrador', 'en_transito'])
                ], order='write_date desc', limit=1)

                if ultimo_pesaje:
                    peso_a_usar = ultimo_pesaje.peso_actual
                    # Actualizar el peso_actual de este registro también
                    record.peso_actual = peso_a_usar

            # Validación según tipo de proceso
            if record.tipo_proceso == 'entrada':
                # Entrada: 1ª pesada = peso bruto (camión lleno)
                if peso_a_usar <= 0:
                    raise UserError('No hay peso disponible desde la báscula. Verifica que el simulador/báscula esté enviando datos.')
                record.peso_bruto = peso_a_usar
            else:
                # Salida: 1ª pesada = peso tara (camión vacío)
                if peso_a_usar <= 0:
                    raise UserError('No hay peso disponible desde la báscula. Verifica que el simulador/báscula esté enviando datos.')
                record.peso_tara = peso_a_usar

            record.write({
                'hora_entrada': self._get_colombia_time(),
                'state': 'en_transito'
            })

    def action_segunda_pesada(self):
        for record in self:
            if record.state != 'en_transito':
                raise UserError('Solo se puede registrar la segunda pesada en estado en tránsito.')

            # Obtener peso actual de la báscula
            peso_a_usar = record.peso_actual if record.peso_actual > 0 else 0

            # Si no hay peso_actual en este registro, buscar el último peso disponible
            if peso_a_usar <= 0:
                ultimo_pesaje = self.search([
                    ('peso_actual', '>', 0),
                    ('state', 'in', ['borrador', 'en_transito'])
                ], order='write_date desc', limit=1)

                if ultimo_pesaje:
                    peso_a_usar = ultimo_pesaje.peso_actual
                    # Actualizar el peso_actual de este registro también
                    record.peso_actual = peso_a_usar

            # Validación según tipo de proceso
            if record.tipo_proceso == 'entrada':
                # Entrada: 2ª pesada = peso tara (camión vacío)
                if peso_a_usar <= 0:
                    raise UserError('No hay peso disponible desde la báscula. Verifica que el simulador/báscula esté enviando datos.')
                if not record.peso_bruto or record.peso_bruto <= 0:
                    raise UserError('Debe tener registrado el peso bruto de la primera pesada.')
                record.peso_tara = peso_a_usar
            else:
                # Salida: 2ª pesada = peso bruto (camión lleno)
                if peso_a_usar <= 0:
                    raise UserError('No hay peso disponible desde la báscula. Verifica que el simulador/báscula esté enviando datos.')
                if not record.peso_tara or record.peso_tara <= 0:
                    raise UserError('Debe tener registrado el peso tara de la primera pesada.')
                record.peso_bruto = peso_a_usar

            # Validar que el peso neto no sea negativo
            peso_neto_calc = record.peso_bruto - record.peso_tara
            if peso_neto_calc <= 0:
                raise UserError(f'El peso neto no puede ser negativo o cero. Peso bruto: {record.peso_bruto} kg, Peso tara: {record.peso_tara} kg')

            record.write({
                'hora_salida': self._get_colombia_time(),
                'state': 'completado'
            })

    def action_cancelar(self):
        for record in self:
            if record.state == 'completado':
                raise UserError('No se puede cancelar un pesaje completado.')
            record.state = 'cancelado'

    def action_borrador(self):
        for record in self:
            record.state = 'borrador'

    # ===== MÉTODOS PARA INTEGRACIÓN CON BÁSCULA =====

    @api.model
    def actualizar_peso_bascula(self, pesaje_id, peso, api_key):
        """
        Método llamado por el bridge externo para actualizar el peso en tiempo real

        Args:
            pesaje_id: ID del pesaje activo
            peso: Peso actual en kg
            api_key: Clave de autenticación

        Returns:
            dict: {'success': bool, 'peso': float, 'message': str}
        """
        # Validar API Key
        api_key_config = self.env['ir.config_parameter'].sudo().get_param('bascula.api_key', '')
        if not api_key_config or api_key != api_key_config:
            return {'success': False, 'message': 'API Key inválida'}

        try:
            pesaje = self.browse(pesaje_id)
            if not pesaje.exists():
                return {'success': False, 'message': 'Pesaje no encontrado'}

            # Actualizar peso actual
            pesaje.sudo().write({'peso_actual': peso, 'escuchando_bascula': True})

            return {
                'success': True,
                'peso': peso,
                'message': 'Peso actualizado correctamente'
            }
        except Exception as e:
            return {'success': False, 'message': str(e)}

    @api.model
    def obtener_pesaje_activo(self, api_key):
        """
        Obtiene el pesaje que está actualmente esperando pesaje

        Args:
            api_key: Clave de autenticación

        Returns:
            dict: {'success': bool, 'pesaje_id': int, 'state': str}
        """
        # Validar API Key
        api_key_config = self.env['ir.config_parameter'].sudo().get_param('bascula.api_key', '')
        if not api_key_config or api_key != api_key_config:
            return {'success': False, 'message': 'API Key inválida'}

        # Buscar pesaje en borrador o en tránsito (más reciente)
        pesaje = self.search([
            ('state', 'in', ['borrador', 'en_transito'])
        ], order='id desc', limit=1)

        if pesaje:
            return {
                'success': True,
                'pesaje_id': pesaje.id,
                'state': pesaje.state,
                'tipo_proceso': pesaje.tipo_proceso,
                'placa': pesaje.placa_texto or ''
            }
        else:
            return {
                'success': False,
                'message': 'No hay pesajes activos esperando pesaje'
            }

    def action_refrescar_peso(self):
        """Refrescar el peso actual desde la base de datos"""
        for record in self:
            # Solo refrescar, Odoo recargará el valor actual desde la BD
            record.invalidate_recordset(['peso_actual', 'escuchando_bascula'])
        return True

    def action_usar_peso_actual(self):
        """Usar el peso actual de la báscula y asignarlo al campo correspondiente"""
        for record in self:
            if record.peso_actual <= 0:
                raise UserError('No hay peso actual de la báscula disponible.')

            if record.state == 'borrador':
                # Asignar a peso bruto (entrada) o peso tara (salida)
                if record.tipo_proceso == 'entrada':
                    record.peso_bruto = record.peso_actual
                else:
                    record.peso_tara = record.peso_actual
            elif record.state == 'en_transito':
                # Asignar a peso tara (entrada) o peso bruto (salida)
                if record.tipo_proceso == 'entrada':
                    record.peso_tara = record.peso_actual
                else:
                    record.peso_bruto = record.peso_actual

    def action_crear_orden_servicio(self):
        """Crear una nueva Orden de Servicio vinculada a este pesaje"""
        self.ensure_one()

        if self.orden_servicio_id:
            raise UserError('Este pesaje ya está vinculado a una orden de servicio.')

        # Obtener tipo_servicio_id desde tipo_operacion_id si existe
        tipo_servicio_id = False
        if self.tipo_operacion_id and self.tipo_operacion_id.es_servicio:
            tipo_servicio_id = self.tipo_operacion_id.id

        # Crear nueva orden
        orden_vals = {
            'cliente_id': self.tercero_id.id if self.tercero_id else False,
        }
        if tipo_servicio_id:
            orden_vals['tipo_servicio_id'] = tipo_servicio_id

        orden = self.env['secadora.orden.servicio'].create(orden_vals)

        # Vincular pesaje a la orden y guardar
        self.write({'orden_servicio_id': orden.id})

        # Mensaje de éxito
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Orden Creada',
                'message': f'Orden {orden.name} creada y vinculada exitosamente',
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.act_window_close',
                }
            }
        }
