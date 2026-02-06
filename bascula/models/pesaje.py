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
    tipo_proceso = fields.Selection([
        ('entrada', 'Entrada (Compra)'),
        ('salida', 'Salida (Venta/Despacho)'),
    ], string='Tipo de Proceso', required=True, default='entrada', index=True)
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
        string='Peso Bruto (Kg)',
        help='Primera pesada - Vehículo lleno',
        digits=(12, 2)
    )
    peso_tara = fields.Float(
        string='Peso Tara (Kg)',
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

            # Usar peso actual de la báscula si está disponible
            peso_a_usar = record.peso_actual if record.peso_actual > 0 else 0

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

            # Usar peso actual de la báscula si está disponible
            peso_a_usar = record.peso_actual if record.peso_actual > 0 else 0

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
