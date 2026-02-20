# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError


class PosicionArroz(models.Model):
    _name = 'secadora.posicion.arroz'
    _description = 'Posición de Arroz en Planta'
    _inherit = ['mail.thread']
    _order = 'fecha_movimiento desc, id desc'

    name = fields.Char(
        string='Referencia',
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: 'Nuevo',
    )
    pesaje_id = fields.Many2one(
        'secadora.pesaje',
        string='Pesaje',
        required=True,
        ondelete='restrict',
        index=True,
        tracking=True,
    )
    sitio_id = fields.Many2one(
        'secadora.sitio.muestra',
        string='Ubicación',
        domain=[('es_contenedor', '=', True)],
        group_expand='_read_group_sitio_ids',
        index=True,
        tracking=True,
    )
    peso_kg = fields.Float(
        string='Peso (Kg)',
        digits=(12, 2),
        tracking=True,
    )
    peso_original = fields.Float(
        string='Peso Original (Kg)',
        digits=(12, 2),
        readonly=True,
        help='Peso neto original del pesaje',
    )
    fecha_ingreso = fields.Datetime(
        string='Fecha Ingreso',
        default=fields.Datetime.now,
        readonly=True,
    )
    fecha_movimiento = fields.Datetime(
        string='Último Movimiento',
        default=fields.Datetime.now,
    )
    state = fields.Selection([
        ('activo', 'Activo'),
        ('retirado', 'Retirado'),
    ], string='Estado', default='activo', required=True, tracking=True, index=True)

    # Relaciones de división
    posicion_origen_id = fields.Many2one(
        'secadora.posicion.arroz',
        string='Posición Origen',
        readonly=True,
        help='Posición de la cual fue dividida',
    )
    posicion_hija_ids = fields.One2many(
        'secadora.posicion.arroz',
        'posicion_origen_id',
        string='Posiciones Derivadas',
    )

    notas = fields.Text(string='Notas')

    # Historial
    movimiento_ids = fields.One2many(
        'secadora.movimiento.arroz',
        'posicion_id',
        string='Historial de Movimientos',
    )

    # Campos related del pesaje (stored para búsqueda y kanban)
    tercero_id = fields.Many2one(
        related='pesaje_id.tercero_id',
        store=True,
        string='Tercero',
    )
    producto_id = fields.Many2one(
        related='pesaje_id.producto_id',
        store=True,
        string='Producto',
    )
    variedad_id = fields.Many2one(
        related='pesaje_id.variedad_id',
        store=True,
        string='Variedad',
    )
    placa_texto = fields.Char(
        related='pesaje_id.placa_texto',
        store=True,
        string='Placa',
    )
    orden_servicio_id = fields.Many2one(
        related='pesaje_id.orden_servicio_id',
        store=True,
        string='Orden de Servicio',
    )
    pesaje_name = fields.Char(
        related='pesaje_id.name',
        store=True,
        string='Tiquete',
    )

    es_division = fields.Boolean(
        string='Es División',
        compute='_compute_es_division',
        store=True,
    )

    @api.depends('posicion_origen_id')
    def _compute_es_division(self):
        for rec in self:
            rec.es_division = bool(rec.posicion_origen_id)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('secadora.posicion.arroz') or 'Nuevo'
        return super().create(vals_list)

    def write(self, vals):
        # Detectar cambio de sitio_id (drag-and-drop en kanban)
        if 'sitio_id' in vals:
            for rec in self:
                old_sitio = rec.sitio_id
                new_sitio_id = vals['sitio_id']
                if old_sitio.id != new_sitio_id and new_sitio_id:
                    self.env['secadora.movimiento.arroz'].create({
                        'posicion_id': rec.id,
                        'sitio_origen_id': old_sitio.id if old_sitio else False,
                        'sitio_destino_id': new_sitio_id,
                        'peso_kg': rec.peso_kg,
                        'tipo': 'movimiento',
                        'notas': f'Movido de {old_sitio.name or "Sin ubicación"} a {self.env["secadora.sitio.muestra"].browse(new_sitio_id).name}',
                    })
            vals['fecha_movimiento'] = fields.Datetime.now()
        return super().write(vals)

    @api.model
    def _read_group_sitio_ids(self, sitios, domain):
        """Mostrar todas las columnas contenedoras en el kanban, incluso las vacías."""
        return self.env['secadora.sitio.muestra'].search(
            [('es_contenedor', '=', True)],
            order='sequence, id',
        )

    def action_dividir(self):
        """Abrir wizard de división."""
        self.ensure_one()
        if self.state != 'activo':
            raise UserError('Solo se pueden dividir posiciones activas.')
        return {
            'name': 'Dividir Posición',
            'type': 'ir.actions.act_window',
            'res_model': 'secadora.dividir.posicion.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_posicion_id': self.id,
                'default_peso_actual': self.peso_kg,
            },
        }

    def action_retirar(self):
        """Marcar como retirado (arroz salió de la planta)."""
        for rec in self:
            if rec.state != 'activo':
                raise UserError('Solo se pueden retirar posiciones activas.')
            rec.state = 'retirado'
            self.env['secadora.movimiento.arroz'].create({
                'posicion_id': rec.id,
                'sitio_origen_id': rec.sitio_id.id if rec.sitio_id else False,
                'peso_kg': rec.peso_kg,
                'tipo': 'retiro',
                'notas': 'Arroz retirado de la planta',
            })

    def action_reactivar(self):
        """Reactivar una posición retirada."""
        for rec in self:
            if rec.state != 'retirado':
                raise UserError('Solo se pueden reactivar posiciones retiradas.')
            rec.state = 'activo'
