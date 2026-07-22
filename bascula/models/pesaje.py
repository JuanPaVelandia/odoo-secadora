# -*- coding: utf-8 -*-

from datetime import datetime
import pytz
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


class SecadoraPesaje(models.Model):
    _name = 'secadora.pesaje'
    _description = 'Registro de Pesaje'
    _inherit = ['mail.thread']
    _order = 'name desc'
    _peso_valido = models.Constraint(
        'CHECK(peso_bruto >= peso_tara OR peso_bruto = 0 OR peso_tara = 0)',
        'El peso bruto no puede ser menor al peso tara.',
    )
    _peso_bruto_no_negativo = models.Constraint(
        'CHECK(peso_bruto >= 0)',
        'El peso lleno (bruto) no puede ser negativo.',
    )
    _peso_tara_no_negativo = models.Constraint(
        'CHECK(peso_tara >= 0)',
        'El peso vacío (tara) no puede ser negativo.',
    )
    _name_company_unique = models.Constraint(
        'UNIQUE(name, company_id)',
        'Número de pesaje duplicado para esta empresa.',
    )

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
    ], string='Estado', default='borrador', required=True, index=True, tracking=True)

    # Flag de edición: cuando un pesaje está completado, sus campos quedan de
    # solo lectura (salvo producto y calidad). El botón "Reabrir para editar"
    # (solo Administrador Báscula) lo activa para permitir editar todo, incluido
    # el peso. Es un desbloqueo temporal: al guardar los cambios se vuelve a
    # poner en False automáticamente (ver write), re-bloqueando el pesaje.
    permite_edicion = fields.Boolean(
        string='Edición desbloqueada',
        default=False,
        copy=False,
    )
    # Verdadero cuando el pesaje debe estar de solo lectura (completado y sin
    # desbloqueo). Se calcula en Python para poder usar en la vista un modificador
    # simple `readonly="bloqueado"` — Odoo 18 no evalúa bien expresiones con `and`
    # en los atributos readonly/invisible.
    bloqueado = fields.Boolean(
        string='Bloqueado',
        compute='_compute_bloqueado',
    )
    # El peso es de solo lectura salvo cuando un pesaje completado fue reabierto.
    peso_bloqueado = fields.Boolean(
        string='Peso bloqueado',
        compute='_compute_bloqueado',
    )

    @api.depends('state', 'permite_edicion')
    def _compute_bloqueado(self):
        for rec in self:
            rec.bloqueado = rec.state == 'completado' and not rec.permite_edicion
            # Peso editable únicamente al reabrir un completado; bloqueado el resto.
            rec.peso_bloqueado = not (rec.state == 'completado' and rec.permite_edicion)

    # Vehículo y transporte
    vehiculo_id = fields.Many2one(
        'secadora.vehiculo',
        string='Vehículo',
        required=True,
        index=True,
        tracking=True,
    )
    placa_texto = fields.Char(
        string='Placa',
        related='vehiculo_id.placa',
        store=True,
        readonly=True
    )
    conductor_id = fields.Many2one(
        'secadora.conductor',
        string='Conductor',
        tracking=True,
    )
    cedula_conductor = fields.Char(
        string='Cédula Conductor',
        related='conductor_id.cedula',
        readonly=True
    )
    transportadora_id = fields.Many2one(
        'secadora.transportadora',
        string='Transportadora',
        tracking=True,
    )

    # Multi-empresa
    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    empresa_arroz_id = fields.Many2one(
        'res.company',
        string='Empresa del Arroz',
        index=True,
        tracking=True,
        help='Empresa dueña del arroz. Se auto-detecta desde el tercero.',
    )

    es_semilla = fields.Boolean(
        string='Es Semilla',
        default=False,
        help='Marcar si este viaje transporta semilla. Las posiciones de semilla no se pueden combinar en el tablero.',
    )

    # Tercero (agricultor/cliente)
    tercero_id = fields.Many2one(
        'res.partner',
        string='Tercero (Agricultor/Cliente)',
        required=True,
        index=True,
        tracking=True,
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
        required=True,
        tracking=True,
        help='Lugar de origen (finca, bodega, etc.)'
    )
    lote_id = fields.Many2one(
        'secadora.lote',
        string='Lote',
        tracking=True,
        domain="[('finca_id', '=', origen_id)]",
        help='Lote de la finca de origen. Para cargas de varios lotes, marcar "Carga Mixta".',
    )
    carga_mixta = fields.Boolean(
        string='Carga Mixta',
        help='Marcar cuando la mula trae arroz de varios lotes/fincas. '
             'El peso neto se prorratea por bultos entre las líneas de distribución.',
    )
    distribucion_ids = fields.One2many(
        'secadora.pesaje.distribucion',
        'pesaje_id',
        string='Distribución por Finca/Lote',
    )
    lote_finca = fields.Char(
        string='Lote (texto legacy)',
        help='(Legacy) Texto libre del lote, migrado al catálogo en lote_id. '
             'Se conserva como respaldo de auditoría de la migración.'
    )
    destino_id = fields.Many2one(
        'secadora.lugar',
        string='Destino',
        required=True,
        tracking=True,
        help='Lugar de destino (finca, bodega, etc.)'
    )

    # Producto
    producto_id = fields.Many2one(
        'product.product',
        string='Producto',
        help='Producto del inventario',
        domain=[('type', '=', 'consu')],
        index=True,
        tracking=True,
    )
    variedad_id = fields.Many2one(
        'secadora.variedad.arroz',
        string='Variedad de Arroz',
        tracking=True,
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
        digits=(12, 0),
        readonly=True
    )
    peso_actual_fecha = fields.Datetime(
        string='Hora del Peso Actual',
        readonly=True,
        help='Cuándo escribió el bridge el último peso en este pesaje. '
             'Sin esta marca, un peso viejo quedaba pegado al registro y '
             'las pesadas capturaban el peso de otro momento u otro camión.',
    )
    escuchando_bascula = fields.Boolean(
        string='Escuchando Báscula',
        default=False,
        help='Indica si el sistema está recibiendo peso de la báscula'
    )
    peso_bruto = fields.Float(
        string='Peso Lleno (Kg)',
        help='Primera pesada - Vehículo lleno',
        digits=(12, 0),
        tracking=True,
    )
    peso_tara = fields.Float(
        string='Peso Vacío (Kg)',
        help='Segunda pesada - Vehículo vacío',
        digits=(12, 0),
        tracking=True,
    )
    peso_neto = fields.Float(
        string='Peso Neto (Kg)',
        compute='_compute_peso_neto',
        store=True,
        readonly=True,
        digits=(12, 0)
    )

    # Calidad
    humedad = fields.Float(
        string='Humedad (%)',
        digits=(5, 2),
        tracking=True,
    )
    grano_partido = fields.Float(
        string='Grano Partido (%)',
        digits=(5, 2),
        tracking=True,
    )
    impurezas = fields.Float(
        string='Impurezas (%)',
        digits=(5, 2),
        tracking=True,
    )

    # Campos relacionados para visibilidad en vista
    os_modalidad_salida = fields.Selection(
        related='orden_servicio_id.modalidad_salida',
        string='Modalidad Salida OS',
    )

    # Líneas de despacho de bultos (pesajes de salida de servicio con modalidad bultos)
    despacho_bultos_ids = fields.One2many(
        'secadora.despacho.bultos',
        'pesaje_id',
        string='Bultos a Despachar',
        help='Detalle de bultos a despachar en este pesaje de salida',
    )

    peso_total_bultos_despacho = fields.Float(
        string='Peso Bultos (kg)',
        compute='_compute_diferencia_bultos',
        digits=(12, 2),
    )
    diferencia_bultos = fields.Float(
        string='Diferencia Báscula vs Bultos (kg)',
        compute='_compute_diferencia_bultos',
        digits=(12, 2),
    )
    diferencia_bultos_pct = fields.Float(
        string='Diferencia (%)',
        compute='_compute_diferencia_bultos',
        digits=(5, 2),
    )
    alerta_diferencia_bultos = fields.Boolean(
        string='Alerta Diferencia',
        compute='_compute_diferencia_bultos',
    )

    @api.depends('despacho_bultos_ids.peso_subtotal', 'peso_neto')
    def _compute_diferencia_bultos(self):
        for rec in self:
            peso_bultos = sum(rec.despacho_bultos_ids.mapped('peso_subtotal'))
            rec.peso_total_bultos_despacho = peso_bultos
            if peso_bultos and rec.peso_neto:
                rec.diferencia_bultos = rec.peso_neto - peso_bultos
                rec.diferencia_bultos_pct = (rec.diferencia_bultos / peso_bultos) * 100
                rec.alerta_diferencia_bultos = abs(rec.diferencia_bultos_pct) > 0.1
            else:
                rec.diferencia_bultos = 0
                rec.diferencia_bultos_pct = 0
                rec.alerta_diferencia_bultos = False

    # Remisión
    bultos = fields.Integer(string='Bultos', tracking=True)
    precio = fields.Float(
        string='Precio',
        digits=(12, 0),
        tracking=True,
    )
    plazo = fields.Char(string='Plazo')
    observaciones = fields.Text(string='Observaciones', help='Notas internas adicionales del proceso de pesaje.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('secadora.pesaje') or 'Nuevo'
            # No dejar que el formulario pise peso_actual con 0
            # (el simulador/bridge lo actualiza via API)
            vals.pop('peso_actual', None)
        return super().create(vals_list)

    def write(self, vals):
        # No dejar que el formulario pise peso_actual con 0
        # (el simulador/bridge lo actualiza via API)
        if 'peso_actual' in vals and not vals['peso_actual']:
            vals.pop('peso_actual')

        # Re-bloqueo automático: si un pesaje fue reabierto para editar
        # (permite_edicion=True) y ahora se guardan cambios del usuario, volver a
        # bloquearlo. Se excluye el propio flag y los computados/peso_actual para
        # no re-bloquear en escrituras internas que no son la edición del admin.
        campos_edicion = set(vals) - {'permite_edicion', 'peso_actual'}
        if campos_edicion and 'permite_edicion' not in vals:
            desbloqueados = self.filtered(lambda p: p.permite_edicion)
            if desbloqueados:
                vals = dict(vals, permite_edicion=False)

        res = super().write(vals)
        # Si cambió algo que afecta el peso de la orden, recalcular sus
        # servicios automáticos (fuera de cualquier campo calculado).
        if {'peso_bruto', 'peso_tara', 'state', 'orden_servicio_id'} & set(vals):
            ordenes = self.mapped('orden_servicio_id')
            if ordenes:
                ordenes.recalcular_servicios()
        return res

    @api.onchange('tipo_operacion_id')
    def _onchange_tipo_operacion_direccion(self):
        """Auto-llenar dirección si el tipo de operación tiene dirección fija (compra/venta)"""
        if self.tipo_operacion_id and self.tipo_operacion_id.direccion_fija:
            # Compra/Venta tienen dirección automática
            self.direccion = self.tipo_operacion_id.direccion_fija

    @api.onchange('direccion')
    def _onchange_direccion_planta(self):
        """Auto-asignar planta como origen (salida) o destino (entrada)."""
        lugar_id = int(self.env['ir.config_parameter'].sudo().get_param(
            'bascula.lugar_planta_id', '0'))
        if not lugar_id:
            # Fallback al parámetro de transporte si existe
            lugar_id = int(self.env['ir.config_parameter'].sudo().get_param(
                'secadora_transporte.lugar_planta_id', '0'))
        if not lugar_id:
            return
        planta = self.env['secadora.lugar'].browse(lugar_id).exists()
        if not planta:
            return
        if self.direccion == 'entrada':
            self.destino_id = planta
            if self.origen_id == planta:
                self.origen_id = False
        elif self.direccion == 'salida':
            self.origen_id = planta
            if self.destino_id == planta:
                self.destino_id = False

    @api.onchange('origen_id')
    def _onchange_origen_lote(self):
        """Limpiar el lote si no pertenece a la nueva finca de origen.

        No se limpia la distribución de carga mixta: sus líneas pueden
        referirse a fincas distintas del origen del pesaje.
        """
        if self.lote_id and self.lote_id.finca_id != self.origen_id:
            self.lote_id = False

    @api.onchange('carga_mixta')
    def _onchange_carga_mixta(self):
        if self.carga_mixta:
            self.lote_id = False
        elif self.distribucion_ids:
            return {
                'warning': {
                    'title': 'Carga mixta con líneas',
                    'message': 'Este pesaje tiene líneas de distribución por lote. '
                               'Mientras existan, el reporte de producción usará las líneas. '
                               'Elimínalas si la carga es de un solo lote.',
                }
            }

    @api.constrains('bultos', 'distribucion_ids')
    def _check_distribucion_bultos(self):
        """La distribución por lote debe cuadrar con los bultos del pesaje."""
        for record in self:
            if record.distribucion_ids and record.bultos > 0:
                total_lineas = sum(record.distribucion_ids.mapped('bultos'))
                if total_lineas != record.bultos:
                    raise ValidationError(
                        f'La distribución por finca/lote no cuadra con los bultos del pesaje.\n'
                        f'Bultos del pesaje: {record.bultos}\n'
                        f'Bultos distribuidos: {total_lineas}'
                    )

    @api.onchange('despacho_bultos_ids')
    def _onchange_despacho_producto_calidad(self):
        """Al escoger bultos empacados en una salida, auto-llenar Producto y
        Calidad: producto desde el registro de bultos, y variedad/es_semilla
        desde los pesajes de entrada de la orden de servicio del registro."""
        if self.direccion != 'salida':
            return
        registros = self.despacho_bultos_ids.mapped('registro_bultos_id')
        if not registros:
            return
        registro = registros[0]
        if registro.producto_id:
            self.producto_id = registro.producto_id
        entradas = registro.orden_id.pesaje_entrada_ids
        if entradas:
            variedades = [e.variedad_id for e in entradas if e.variedad_id]
            if variedades:
                # La variedad más frecuente entre las entradas de la OS
                self.variedad_id = max(set(variedades), key=variedades.count)
            self.es_semilla = any(entradas.mapped('es_semilla'))

    @api.onchange('vehiculo_id')
    def _onchange_vehiculo_datos(self):
        """Auto-llenar transportadora y conductor desde el vehículo seleccionado.

        Al cambiar el vehículo (placa) se re-asignan la transportadora y el
        conductor desde el vehículo, aunque ya tuvieran valor: si se corrige la
        placa, la transportadora debe corregirse en consecuencia. Cuando el
        vehículo no define transportadora/conductor propios, se conserva el
        valor actual para no perder una elección manual previa.
        """
        if self.vehiculo_id:
            if self.vehiculo_id.transportadora_id:
                self.transportadora_id = self.vehiculo_id.transportadora_id
            if self.vehiculo_id.conductor_habitual_id:
                self.conductor_id = self.vehiculo_id.conductor_habitual_id

    @api.onchange('tercero_id')
    def _onchange_tercero_empresa(self):
        """Auto-detectar empresa del arroz desde el tercero"""
        if self.tercero_id:
            empresa = self.env['res.company'].search([
                ('partner_id', '=', self.tercero_id.id)
            ], limit=1)
            if empresa:
                self.empresa_arroz_id = empresa.id
            else:
                self.empresa_arroz_id = False

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

    @api.constrains('vehiculo_id', 'transportadora_id')
    def _check_vehiculo_transportadora(self):
        """Validar que la placa pertenezca a la transportadora del pesaje.

        Si el vehículo tiene transportadora asignada en el catálogo, el pesaje
        debe tener esa misma transportadora: ni distinta ni vacía. Si el
        vehículo no tiene transportadora registrada, no hay contra qué validar
        y se permite guardar.
        """
        for record in self:
            transp_vehiculo = record.vehiculo_id.transportadora_id
            if not record.vehiculo_id or not transp_vehiculo:
                continue
            if not record.transportadora_id:
                raise UserError(
                    f'El pesaje no tiene transportadora, pero la placa '
                    f'{record.vehiculo_id.placa} pertenece a '
                    f'"{transp_vehiculo.name}".\n\n'
                    f'Asigne la transportadora al pesaje (o corrija la placa).'
                )
            if record.transportadora_id != transp_vehiculo:
                raise UserError(
                    f'La placa {record.vehiculo_id.placa} pertenece a la transportadora '
                    f'"{transp_vehiculo.name}", no a '
                    f'"{record.transportadora_id.name}".\n\n'
                    f'Corrija la transportadora del pesaje o la placa. Si el vehículo '
                    f'cambió de transportadora, actualícelo primero en el catálogo de vehículos.'
                )

    @api.constrains('peso_bruto', 'peso_tara')
    def _check_pesos_coherentes(self):
        """Validar bruto >= tara cuando ambos están registrados (>0).

        Cubre ediciones directas por API/importación o ajustes manuales tras
        completar el pesaje, no solo el flujo de las pesadas.
        """
        for record in self:
            if record.peso_bruto > 0 and record.peso_tara > 0:
                if record.peso_bruto < record.peso_tara:
                    raise UserError(
                        f'El peso lleno ({record.peso_bruto:.0f} kg) no puede ser menor '
                        f'que el peso vacío ({record.peso_tara:.0f} kg).'
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

    # Antigüedad máxima (segundos) del peso global para considerarlo "en vivo".
    PESO_GLOBAL_MAX_ANTIGUEDAD = 15

    def _peso_bascula_reciente(self):
        """Devuelve el último peso global de la báscula si es reciente, o 0.

        Reemplaza el antiguo fallback que tomaba el peso de OTRO pesaje activo
        (podía capturar el peso de un camión distinto). El peso global lo
        publica el bridge para la báscula física; solo se acepta si llegó
        hace menos de PESO_GLOBAL_MAX_ANTIGUEDAD segundos.
        """
        ICP = self.env['ir.config_parameter'].sudo()
        try:
            peso = float(ICP.get_param('bascula.last_weight', '0') or 0)
        except (TypeError, ValueError):
            return 0.0
        if peso <= 0:
            return 0.0
        ts_str = ICP.get_param('bascula.last_weight_timestamp', False)
        if not ts_str:
            return 0.0
        try:
            # Tolerar el formato isoformat con 'T' de valores ya guardados.
            ts = fields.Datetime.from_string(ts_str.replace('T', ' ')[:19])
        except (TypeError, ValueError):
            return 0.0
        antiguedad = (fields.Datetime.now() - ts).total_seconds()
        if antiguedad > self.PESO_GLOBAL_MAX_ANTIGUEDAD:
            return 0.0
        return peso

    def _peso_actual_fresco(self):
        """peso_actual del registro solo si el bridge lo escribió hace poco.

        Cuando el bridge se detiene, el último peso queda guardado en el
        registro; sin control de antigüedad, una pesada posterior capturaba
        ese valor viejo (de otro momento u otro camión) en vez del peso real
        de la báscula.
        """
        self.ensure_one()
        if self.peso_actual <= 0 or not self.peso_actual_fecha:
            return 0.0
        antiguedad = (fields.Datetime.now() - self.peso_actual_fecha).total_seconds()
        if antiguedad > self.PESO_GLOBAL_MAX_ANTIGUEDAD:
            return 0.0
        return self.peso_actual

    def action_primera_pesada(self):
        for record in self:
            # Lock row to prevent race condition on concurrent state transitions
            self.env.cr.execute(
                'SELECT id FROM secadora_pesaje WHERE id = %s FOR UPDATE NOWAIT',
                [record.id]
            )
            record.invalidate_recordset(['state'])
            if record.state != 'borrador':
                raise UserError('Solo se puede registrar la primera pesada en estado borrador.')

            # Obtener peso actual de la báscula (solo si es reciente)
            peso_a_usar = record._peso_actual_fresco()

            # Si no hay peso_actual fresco en este registro (ej: registro
            # nuevo sin guardar, o bridge detenido), usar el peso global
            # reciente. NO se toma el peso de otro pesaje (otro camión).
            if peso_a_usar <= 0:
                peso_global = self._peso_bascula_reciente()
                if peso_global > 0:
                    peso_a_usar = peso_global
                    record.peso_actual = peso_a_usar
                    record.peso_actual_fecha = fields.Datetime.now()

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
            # Lock row to prevent race condition on concurrent state transitions
            self.env.cr.execute(
                'SELECT id FROM secadora_pesaje WHERE id = %s FOR UPDATE NOWAIT',
                [record.id]
            )
            record.invalidate_recordset(['state'])
            if record.state != 'en_transito':
                raise UserError('Solo se puede registrar la segunda pesada en estado en tránsito.')

            # Obtener peso actual de la báscula (solo si es reciente)
            peso_a_usar = record._peso_actual_fresco()

            # Si no hay peso_actual fresco en este registro, usar el peso
            # global reciente. NO se toma el peso de otro pesaje.
            if peso_a_usar <= 0:
                peso_global = self._peso_bascula_reciente()
                if peso_global > 0:
                    peso_a_usar = peso_global
                    record.peso_actual = peso_a_usar
                    record.peso_actual_fecha = fields.Datetime.now()

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

            # Confirmar líneas de despacho de bultos
            if record.despacho_bultos_ids:
                record.despacho_bultos_ids.write({'confirmado': True})
                record._aplicar_resumen_despacho()

    def _aplicar_resumen_despacho(self):
        """Escribe en observaciones un resumen del despacho de bultos.

        Las observaciones se imprimen en el tiquete, así el conductor y el
        cliente ven qué bultos salieron. Si el pesaje se reabre y se vuelve a
        completar, el resumen anterior se reemplaza (se conserva el texto que
        el basculero haya escrito antes del resumen).
        """
        self.ensure_one()
        if self.direccion != 'salida' or not self.despacho_bultos_ids:
            return
        lineas = []
        for d in self.despacho_bultos_ids:
            reg = d.registro_bultos_id
            detalle = f"{d.cantidad} bultos"
            if reg.orden_id:
                detalle += f" ({reg.orden_id.name})"
            lineas.append(detalle)
        total_bultos = sum(self.despacho_bultos_ids.mapped('cantidad'))
        productos = ', '.join(dict.fromkeys(
            d.registro_bultos_id.producto_id.display_name
            for d in self.despacho_bultos_ids
            if d.registro_bultos_id.producto_id))
        resumen = 'Despacho'
        if productos:
            resumen += f' {productos}'
        resumen += ': ' + ', '.join(lineas)
        if len(lineas) > 1:
            resumen += f" = {total_bultos} bultos"
        resumen += f" / {self.peso_total_bultos_despacho:,.0f} kg."
        base = self.observaciones or ''
        if 'Despacho:' in base:
            base = base.split('Despacho:')[0].rstrip()
        self.observaciones = (base + '\n' if base else '') + resumen

    def action_cancelar(self):
        for record in self:
            if record.state == 'completado':
                raise UserError('No se puede cancelar un pesaje completado.')
            record.state = 'cancelado'

    def action_borrador(self):
        for record in self:
            record.state = 'borrador'

    def _motivos_bloqueo_reapertura(self):
        """Razones por las que este pesaje NO debe poder reabrirse para editar.

        Devuelve una lista de textos; vacía = se puede reabrir. Los módulos que
        añaden documentos aguas abajo (transporte, liquidación) extienden este
        método para añadir sus propias razones cuando esos documentos ya están
        liquidados o facturados.
        """
        self.ensure_one()
        motivos = []
        os = self.orden_servicio_id
        if os and os.state in ('liquidado', 'facturado'):
            estado = dict(os._fields['state'].selection).get(os.state, os.state)
            motivos.append(f'Orden de servicio {os.name} ({estado})')
        return motivos

    def action_reabrir_edicion(self):
        """Desbloquear un pesaje completado para editar todos sus campos.

        Reservado al grupo Administrador Báscula (control en la vista). Activa el
        flag permite_edicion para esta sesión de edición, permitiendo modificar
        incluso el peso sin cambiar el estado del pesaje.
        """
        self.ensure_one()
        if not self.env.user.has_group('bascula.group_bascula_admin'):
            raise UserError('Solo el Administrador de Báscula puede reabrir un pesaje completado.')
        if self.state != 'completado':
            raise UserError('Solo se puede reabrir la edición de un pesaje completado.')
        # Impedir reabrir si hay documentos aguas abajo ya comprometidos
        # (liquidados/facturados): editar el peso los descuadraría. Cada módulo
        # (transporte, liquidación, OS) añade sus razones en _motivos_bloqueo_reapertura.
        motivos = self._motivos_bloqueo_reapertura()
        if motivos:
            raise UserError(
                'No se puede reabrir el pesaje %s porque ya tiene documentos '
                'facturados o liquidados:\n- %s' % (self.name, '\n- '.join(motivos))
            )
        # Idempotente: si ya estaba reabierto, no repetir el mensaje del chatter.
        if self.permite_edicion:
            return
        self.permite_edicion = True
        # Dejar rastro en el chatter de quién reabrió y cuándo; los cambios que
        # haga después quedan registrados por el tracking de los campos.
        self.message_post(
            body=f'Pesaje reabierto para edición por {self.env.user.name}.',
        )

    def action_cerrar_edicion(self):
        """Volver a bloquear un pesaje completado que estaba en edición.

        Cierra explícitamente la sesión de edición abierta con
        action_reabrir_edicion, sin depender de que se hayan guardado cambios.
        """
        self.ensure_one()
        if not self.permite_edicion:
            return
        self.permite_edicion = False

    def action_imprimir_tiquete(self):
        """Abrir el tiquete PDF en una pestaña del navegador (visor de PDF),
        sin descargarlo: desde ahí se imprime directo con Ctrl+P o el botón
        de imprimir del visor."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/report/pdf/bascula.report_pesaje_tiquete_document/{self.id}',
            'target': 'new',
        }

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
            try:
                pesaje_id = int(pesaje_id)
            except (TypeError, ValueError):
                return {'success': False, 'message': 'pesaje_id inválido'}

            pesaje = self.sudo().browse(pesaje_id)
            if not pesaje.exists():
                return {'success': False, 'message': 'Pesaje no encontrado'}

            # Nota: No se filtra por company_id aquí porque este método se
            # llama desde el bridge externo (auth='none' + sudo). La API key
            # ya provee la autenticación. Los métodos de usuario (action_primera_pesada,
            # action_segunda_pesada) sí filtran por empresa del usuario.

            # Guardar como peso global para formularios nuevos (sin guardar).
            # Formato estándar (no isoformat): el lector no entiende la 'T'.
            self.env['ir.config_parameter'].sudo().set_param('bascula.last_weight', str(peso))
            self.env['ir.config_parameter'].sudo().set_param(
                'bascula.last_weight_timestamp',
                fields.Datetime.to_string(fields.Datetime.now())
            )

            # Actualizar el peso SOLO en el pesaje que está en la báscula.
            # El bridge nos dice cuál es (pesaje_id). Escribir a todos los
            # pesajes activos contaminaba el peso entre camiones simultáneos.
            if pesaje.state in ('borrador', 'en_transito'):
                pesaje.write({
                    'peso_actual': peso,
                    'peso_actual_fecha': fields.Datetime.now(),
                    'escuchando_bascula': True,
                })

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
        # Nota: No se filtra por company_id aquí porque este método se
        # llama desde el bridge externo (auth='none' + sudo). La API key
        # ya provee la autenticación.
        pesaje = self.search([
            ('state', 'in', ['borrador', 'en_transito']),
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

    @api.model
    def actualizar_peso_global_bascula(self, peso, api_key):
        """Actualiza el peso global para formularios nuevos sin pesaje guardado."""
        api_key_config = self.env['ir.config_parameter'].sudo().get_param('bascula.api_key', '')
        if not api_key_config or api_key != api_key_config:
            return {'success': False, 'message': 'API Key inválida'}

        try:
            peso_val = float(peso)
            if peso_val < 0 or peso_val > 100000:
                return {'success': False, 'message': 'Peso fuera de rango'}

            self.env['ir.config_parameter'].sudo().set_param('bascula.last_weight', str(peso_val))
            # Formato estándar de Odoo (espacio, no la 'T' de isoformat): el
            # lector usa fields.Datetime.from_string y la 'T' lo rompía, con lo
            # que el peso global se descartaba SIEMPRE por "viejo".
            timestamp = fields.Datetime.to_string(fields.Datetime.now())
            self.env['ir.config_parameter'].sudo().set_param('bascula.last_weight_timestamp', timestamp)

            # Solo se guarda el peso global (para formularios nuevos sin guardar).
            # NO se propaga a los pesajes activos: cada pesaje recibe su peso
            # dirigido vía actualizar_peso_bascula(pesaje_id, ...). Propagar aquí
            # contaminaba el peso entre camiones distintos.

            return {
                'success': True,
                'peso_actual': peso_val,
                'timestamp': timestamp,
                'message': 'Peso global actualizado'
            }
        except Exception as e:
            return {'success': False, 'message': str(e)}

    @api.model
    def obtener_peso_actual_global_ui(self):
        """Devuelve el último peso global para el widget en formularios nuevos."""
        peso_str = self.env['ir.config_parameter'].sudo().get_param('bascula.last_weight', '0')
        timestamp = self.env['ir.config_parameter'].sudo().get_param('bascula.last_weight_timestamp', False)
        try:
            peso_val = float(peso_str or 0)
        except Exception:
            peso_val = 0.0

        return {
            'success': True,
            'peso_actual': peso_val,
            'timestamp': timestamp,
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
            if record._peso_actual_fresco() <= 0:
                raise UserError(
                    'No hay peso reciente de la báscula. Verifica que el '
                    'bridge/simulador esté corriendo y enviando datos.'
                )

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
