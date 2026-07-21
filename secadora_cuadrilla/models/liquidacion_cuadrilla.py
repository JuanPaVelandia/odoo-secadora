# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError


class LiquidacionCuadrilla(models.Model):
    _name = 'secadora.cuadrilla.liquidacion'
    _description = 'Liquidación de Cuadrilla'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'

    name = fields.Char(
        string='Número',
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: 'Nuevo',
    )
    fecha = fields.Date(
        string='Fecha',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    fecha_desde = fields.Date(
        string='Fecha Desde',
        required=True,
        tracking=True,
    )
    fecha_hasta = fields.Date(
        string='Fecha Hasta',
        required=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    linea_ids = fields.One2many(
        'secadora.cuadrilla.liquidacion.linea',
        'liquidacion_id',
        string='Líneas de Servicio',
    )
    deduccion_ids = fields.One2many(
        'secadora.cuadrilla.liquidacion.deduccion',
        'liquidacion_id',
        string='Deducciones',
    )
    total_servicios = fields.Float(
        string='Total Servicios ($)',
        compute='_compute_totales',
        store=True,
        digits=(12, 2),
    )
    total_deducciones = fields.Float(
        string='Total Deducciones ($)',
        compute='_compute_totales',
        store=True,
        digits=(12, 2),
    )
    total_neto = fields.Float(
        string='Total Neto ($)',
        compute='_compute_totales',
        store=True,
        digits=(12, 2),
    )
    cantidad_lineas = fields.Integer(
        string='Cantidad de Líneas',
        compute='_compute_totales',
        store=True,
    )
    state = fields.Selection([
        ('borrador', 'Borrador'),
        ('confirmado', 'Confirmado'),
        ('pagado', 'Pagado'),
        ('cancelado', 'Cancelado'),
    ], string='Estado', default='borrador', required=True, index=True, tracking=True)
    observaciones = fields.Text(string='Observaciones')
    usuario_id = fields.Many2one(
        'res.users',
        string='Responsable',
        default=lambda self: self.env.user,
        tracking=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'secadora.cuadrilla.liquidacion') or 'Nuevo'
        return super().create(vals_list)

    @api.depends('linea_ids.subtotal', 'deduccion_ids.monto')
    def _compute_totales(self):
        for rec in self:
            rec.total_servicios = sum(rec.linea_ids.mapped('subtotal'))
            rec.total_deducciones = sum(rec.deduccion_ids.mapped('monto'))
            rec.total_neto = rec.total_servicios - rec.total_deducciones
            rec.cantidad_lineas = len(rec.linea_ids)

    def action_confirmar(self):
        for rec in self:
            if not rec.linea_ids:
                raise UserError('Debe agregar al menos una línea de servicio antes de confirmar.')
            rec.state = 'confirmado'

    def action_pagar(self):
        for rec in self:
            if rec.state != 'confirmado':
                raise UserError('Solo se pueden marcar como pagadas liquidaciones confirmadas.')
            rec.state = 'pagado'

    def action_borrador(self):
        for rec in self:
            rec.state = 'borrador'

    def action_cancelar(self):
        for rec in self:
            if rec.state == 'pagado':
                raise UserError('No se puede cancelar una liquidación pagada.')
            rec.state = 'cancelado'

    def action_abrir_wizard_servicios(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Cargar Servicios',
            'res_model': 'secadora.cuadrilla.cargar.servicios.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_liquidacion_id': self.id,
                'default_fecha_desde': self.fecha_desde,
                'default_fecha_hasta': self.fecha_hasta,
            },
        }
