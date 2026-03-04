# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError


class SecadoraFlete(models.Model):
    _name = 'secadora.flete'
    _description = 'Flete de Transporte'
    _inherit = ['mail.thread']
    _order = 'fecha desc, id desc'
    _sql_constraints = [
        ('pesaje_unico', 'UNIQUE(pesaje_id)',
         'Este pesaje ya tiene un flete asociado. Un pesaje solo puede tener un flete.'),
        ('peso_kg_positivo', 'CHECK(peso_kg >= 0)',
         'El peso del flete no puede ser negativo.'),
        ('costo_total_positivo', 'CHECK(costo_total >= 0)',
         'El costo total del flete no puede ser negativo.'),
    ]

    name = fields.Char(
        string='Número',
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: 'Nuevo',
    )

    company_id = fields.Many2one(
        'res.company',
        string='Empresa que Paga',
        required=True,
        default=lambda self: self.env.company,
        index=True,
        tracking=True,
        help='Empresa responsable del pago del flete',
    )

    fecha = fields.Date(
        string='Fecha',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )

    # ==================== TERCERO ====================

    tercero_id = fields.Many2one(
        'res.partner',
        string='Tercero (Agricultor)',
        index=True,
        tracking=True,
        help='Agricultor o cliente responsable del flete',
    )
    pago_flete = fields.Selection([
        ('agricultor', 'Agricultor paga directo'),
        ('secadora', 'Secadora paga y descuenta'),
    ], string='Modalidad de Pago', default='agricultor',
       tracking=True,
       help='Quién asume el costo del flete')

    # ==================== RUTA ====================

    origen_id = fields.Many2one(
        'secadora.lugar',
        string='Origen',
        help='Lugar de origen del flete',
    )
    destino_id = fields.Many2one(
        'secadora.lugar',
        string='Destino',
        help='Lugar de destino del flete',
    )
    empresa_origen_id = fields.Many2one(
        'res.company',
        string='Empresa Origen',
        index=True,
        help='Empresa propietaria del lugar de origen (para visibilidad cross-company)',
    )
    empresa_destino_id = fields.Many2one(
        'res.company',
        string='Empresa Destino',
        index=True,
        help='Empresa propietaria del lugar de destino (para visibilidad cross-company)',
    )

    # ==================== TRANSPORTE ====================

    vehiculo_id = fields.Many2one(
        'secadora.vehiculo',
        string='Vehículo',
        required=True,
        tracking=True,
    )
    placa_texto = fields.Char(
        related='vehiculo_id.placa',
        string='Placa',
        store=True,
        readonly=True,
    )
    conductor_id = fields.Many2one(
        'secadora.conductor',
        string='Conductor',
    )
    transportadora_id = fields.Many2one(
        'secadora.transportadora',
        string='Transportadora',
    )

    # ==================== CARGA ====================

    producto_id = fields.Many2one(
        'product.product',
        string='Producto',
        domain=[('type', '=', 'consu')],
    )
    variedad_id = fields.Many2one(
        'secadora.variedad.arroz',
        string='Variedad',
    )
    peso_kg = fields.Float(
        string='Peso (Kg)',
        digits=(12, 2),
    )
    bultos = fields.Integer(
        string='Bultos',
    )
    humedad = fields.Float(
        string='Humedad (%)',
        digits=(5, 2),
    )
    impurezas = fields.Float(
        string='Impurezas (%)',
        digits=(5, 2),
    )

    # ==================== VÍNCULO ====================

    pesaje_id = fields.Many2one(
        'secadora.pesaje',
        string='Pesaje',
        index=True,
        help='Pesaje vinculado a este flete',
    )

    orden_servicio_id = fields.Many2one(
        'secadora.orden.servicio',
        string='Orden de Servicio',
        related='pesaje_id.orden_servicio_id',
        store=True,
        readonly=True,
    )

    pesaje_direccion = fields.Selection(
        related='pesaje_id.direccion',
        string='Dirección Pesaje',
    )

    # ==================== COSTOS ====================

    tarifa_id = fields.Many2one(
        'secadora.tarifa.flete',
        string='Tarifa Aplicada',
        help='Tarifa del catálogo. Se aplica automáticamente según origen/destino, o se puede seleccionar manualmente.',
    )

    tarifa_tipo = fields.Selection([
        ('por_kg', 'Por Kilogramo'),
        ('por_viaje', 'Por Viaje'),
        ('por_bulto', 'Por Bulto'),
    ], string='Tipo de Tarifa', default='por_kg')

    tarifa_unitaria = fields.Float(
        string='Tarifa Unitaria',
        digits='Product Price',
    )

    costo_total = fields.Float(
        string='Costo Total',
        compute='_compute_costo_total',
        store=True,
        digits='Product Price',
    )

    valor_adicional = fields.Float(
        string='Valor Adicional',
        digits='Product Price',
    )
    razon_adicional = fields.Char(
        string='Razón del Valor Adicional',
    )

    # ==================== PESO DESTINO ====================

    peso_destino_kg = fields.Float(
        string='Peso en Destino (Kg)',
        digits=(12, 2),
        help='Peso registrado en el tiquete del destino (ej: molino). Si se llena, el costo se calcula con este peso.',
    )
    usar_peso_destino = fields.Boolean(
        string='Usar Peso Destino para Costo',
        help='Si está marcado, el costo total se calcula con el peso del destino en vez del peso de la secadora.',
    )
    tiquete_destino = fields.Binary(
        string='Tiquete de Destino',
        help='Foto o PDF del tiquete de recibo en el destino.',
    )
    tiquete_destino_nombre = fields.Char(
        string='Nombre del Tiquete',
    )

    factura_transportadora_id = fields.Many2one(
        'account.move',
        string='Factura Transportadora',
        domain="[('move_type', '=', 'in_invoice'), ('state', '!=', 'cancel')]",
        tracking=True,
        copy=False,
    )

    # ==================== ESTADO ====================

    state = fields.Selection([
        ('borrador', 'Borrador'),
        ('confirmado', 'Confirmado'),
        ('en_ruta', 'En Ruta'),
        ('entregado', 'Entregado'),
        ('liquidado', 'Liquidado'),
        ('facturado', 'Facturado'),
        ('cancelado', 'Cancelado'),
    ], string='Estado', default='borrador', required=True, tracking=True, index=True)

    observaciones = fields.Text(string='Observaciones')

    # ==================== COMPUTED ====================

    @api.depends('tarifa_tipo', 'tarifa_unitaria', 'peso_kg', 'bultos',
                 'peso_destino_kg', 'usar_peso_destino', 'valor_adicional')
    def _compute_costo_total(self):
        for rec in self:
            peso = rec.peso_destino_kg if rec.usar_peso_destino and rec.peso_destino_kg else rec.peso_kg
            if rec.tarifa_tipo == 'por_kg':
                base = rec.tarifa_unitaria * peso
            elif rec.tarifa_tipo == 'por_bulto':
                base = rec.tarifa_unitaria * rec.bultos
            elif rec.tarifa_tipo == 'por_viaje':
                base = rec.tarifa_unitaria
            else:
                base = 0.0
            rec.costo_total = base + (rec.valor_adicional or 0.0)

    # ==================== ONCHANGE ====================

    @api.model
    def _buscar_tarifa(self, origen_id, destino_id):
        """Busca tarifa activa para el par origen→destino."""
        if not origen_id or not destino_id:
            return False
        return self.env['secadora.tarifa.flete'].search([
            ('origen_id', '=', origen_id),
            ('destino_id', '=', destino_id),
            ('active', '=', True),
        ], limit=1)

    def _aplicar_tarifa(self):
        """Aplica tarifa encontrada a los campos del flete."""
        tarifa = self._buscar_tarifa(self.origen_id.id, self.destino_id.id)
        if tarifa:
            self.tarifa_id = tarifa
            self.tarifa_tipo = tarifa.tarifa_tipo
            self.tarifa_unitaria = tarifa.tarifa_unitaria

    @api.onchange('origen_id')
    def _onchange_origen_id(self):
        if self.origen_id and self.origen_id.company_id:
            self.empresa_origen_id = self.origen_id.company_id
        if self.origen_id and self.destino_id:
            self._aplicar_tarifa()

    @api.onchange('destino_id')
    def _onchange_destino_id(self):
        if self.destino_id and self.destino_id.company_id:
            self.empresa_destino_id = self.destino_id.company_id
        if self.origen_id and self.destino_id:
            self._aplicar_tarifa()

    @api.onchange('tarifa_id')
    def _onchange_tarifa_id(self):
        """Actualizar tipo y unitaria cuando se selecciona/cambia tarifa manualmente."""
        if self.tarifa_id:
            self.tarifa_tipo = self.tarifa_id.tarifa_tipo
            self.tarifa_unitaria = self.tarifa_id.tarifa_unitaria

    @api.onchange('vehiculo_id')
    def _onchange_vehiculo_id(self):
        if self.vehiculo_id:
            if self.vehiculo_id.conductor_habitual_id:
                self.conductor_id = self.vehiculo_id.conductor_habitual_id
            if self.vehiculo_id.transportadora_id:
                self.transportadora_id = self.vehiculo_id.transportadora_id

    @api.onchange('tercero_id')
    def _onchange_tercero_id(self):
        if self.tercero_id:
            self.pago_flete = self.tercero_id.flete_pago or 'agricultor'
            # Auto-detectar empresa que paga desde el tercero
            empresa = self.env['res.company'].search([
                ('partner_id', '=', self.tercero_id.id)
            ], limit=1)
            if empresa:
                self.company_id = empresa

    @api.onchange('pesaje_id')
    def _onchange_pesaje_id(self):
        if self.pesaje_id:
            self.vehiculo_id = self.pesaje_id.vehiculo_id
            self.conductor_id = self.pesaje_id.conductor_id
            self.transportadora_id = self.pesaje_id.transportadora_id
            self.producto_id = self.pesaje_id.producto_id
            self.variedad_id = self.pesaje_id.variedad_id
            if self.pesaje_id.peso_neto:
                self.peso_kg = self.pesaje_id.peso_neto
            self.bultos = self.pesaje_id.bultos
            self.humedad = self.pesaje_id.humedad
            self.impurezas = self.pesaje_id.impurezas
            if self.pesaje_id.origen_id:
                self.origen_id = self.pesaje_id.origen_id
            if self.pesaje_id.destino_id:
                self.destino_id = self.pesaje_id.destino_id
            if self.pesaje_id.tercero_id:
                self.tercero_id = self.pesaje_id.tercero_id
                self.pago_flete = self.pesaje_id.tercero_id.flete_pago or 'agricultor'
            if self.pesaje_id.empresa_arroz_id:
                self.company_id = self.pesaje_id.empresa_arroz_id

    # ==================== CRUD ====================

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('secadora.flete') or 'Nuevo'
            # Auto-aplicar tarifa si no viene tarifa_unitaria
            if not vals.get('tarifa_unitaria') and vals.get('origen_id') and vals.get('destino_id'):
                tarifa = self._buscar_tarifa(vals['origen_id'], vals['destino_id'])
                if tarifa:
                    vals['tarifa_id'] = tarifa.id
                    vals['tarifa_tipo'] = tarifa.tarifa_tipo
                    vals['tarifa_unitaria'] = tarifa.tarifa_unitaria
        return super().create(vals_list)

    def unlink(self):
        for rec in self:
            if rec.state not in ('borrador', 'cancelado'):
                raise UserError(
                    f'No se puede eliminar el flete {rec.name} en estado '
                    f'"{dict(self._fields["state"].selection).get(rec.state, rec.state)}". '
                    f'Solo se pueden eliminar fletes en borrador o cancelados.'
                )
        return super().unlink()

    # ==================== ACCIONES ====================

    def action_confirmar(self):
        for rec in self:
            if rec.state != 'borrador':
                raise UserError('Solo se pueden confirmar fletes en borrador.')
            rec.state = 'confirmado'

    def action_en_ruta(self):
        for rec in self:
            if rec.state != 'confirmado':
                raise UserError('Solo se pueden poner en ruta fletes confirmados.')
            rec.state = 'en_ruta'

    def action_entregar(self):
        for rec in self:
            if rec.state not in ('confirmado', 'en_ruta'):
                raise UserError('Solo se pueden entregar fletes confirmados o en ruta.')
            rec.state = 'entregado'

    def action_liquidar(self):
        for rec in self:
            if rec.state != 'entregado':
                raise UserError('Solo se pueden liquidar fletes entregados.')
            rec.state = 'liquidado'

    def action_facturar(self):
        for rec in self:
            if rec.state != 'liquidado':
                raise UserError('Solo se pueden facturar fletes liquidados.')
            if not rec.factura_transportadora_id:
                raise UserError(f'El flete {rec.name} no tiene factura de transportadora asociada.')
            if rec.factura_transportadora_id.state == 'cancel':
                raise UserError(
                    f'La factura {rec.factura_transportadora_id.name} asociada al flete '
                    f'{rec.name} está cancelada. Asocie una factura válida.'
                )
            rec.state = 'facturado'

    def action_cancelar(self):
        for rec in self:
            if rec.state in ('liquidado', 'facturado'):
                raise UserError('No se puede cancelar un flete liquidado o facturado.')
            rec.state = 'cancelado'

    def action_borrador(self):
        for rec in self:
            if rec.state != 'cancelado':
                raise UserError('Solo se puede volver a borrador desde cancelado.')
            rec.state = 'borrador'

    def action_ver_factura(self):
        self.ensure_one()
        if not self.factura_transportadora_id:
            raise UserError('Este flete no tiene factura de transportadora asociada.')
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.factura_transportadora_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
