# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError


class Silobolsa(models.Model):
    _name = 'secadora.silobolsa'
    _description = 'Silobolsa de Arroz'
    _inherit = ['mail.thread']
    _order = 'id desc'

    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    name = fields.Char(
        string='Referencia',
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: 'Nuevo',
    )
    state = fields.Selection([
        ('abierto', 'Abierto'),
        ('cerrado', 'Cerrado'),
    ], string='Estado', default='abierto', required=True, tracking=True, index=True)
    ubicacion = fields.Char(
        string='Ubicación',
        help='Dónde está tendida la silobolsa (patio, lote, etc.)',
    )
    variedad_id = fields.Many2one(
        'secadora.variedad.arroz',
        string='Variedad',
        index=True,
    )
    viaje_ids = fields.One2many(
        'secadora.embolsado.viaje',
        'silobolsa_id',
        string='Viajes',
    )
    peso_total_kg = fields.Float(
        string='Peso Total (Kg)',
        digits=(12, 2),
        compute='_compute_totales_viajes',
        store=True,
    )
    cantidad_viajes = fields.Integer(
        string='Viajes Confirmados',
        compute='_compute_totales_viajes',
        store=True,
    )
    fecha_inicio = fields.Datetime(
        string='Inicio de Embolsado',
        compute='_compute_totales_viajes',
        store=True,
        help='Fecha del primer viaje confirmado.',
    )
    fecha_fin_embolsado = fields.Datetime(
        string='Fin de Embolsado',
        compute='_compute_totales_viajes',
        store=True,
        help='Fecha del último viaje confirmado.',
    )
    fecha_cierre = fields.Datetime(string='Fecha de Cierre', readonly=True)
    sitios_origen = fields.Char(
        string='Contenedores Origen',
        compute='_compute_sitios_origen',
    )
    stock_move_id = fields.Many2one(
        'stock.move',
        string='Consumo de Silobolsa',
        readonly=True,
        copy=False,
        help='Movimiento que consume 1 silobolsa del inventario.',
    )
    analisis_lab_ids = fields.One2many(
        'secadora.analisis.lab',
        'silobolsa_id',
        string='Análisis de Laboratorio',
    )
    analisis_count = fields.Integer(
        string='Nº Análisis',
        compute='_compute_analisis',
    )
    humedad_ultima = fields.Float(
        string='Humedad Última (%)',
        digits=(5, 2),
        compute='_compute_analisis',
        help='Humedad del análisis confirmado más reciente de esta silobolsa.',
    )
    notas = fields.Text(string='Notas')
    active = fields.Boolean(string='Activo', default=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('secadora.silobolsa') or 'Nuevo'
        return super().create(vals_list)

    def unlink(self):
        for rec in self:
            if rec.stock_move_id or any(v.state == 'confirmado' for v in rec.viaje_ids):
                raise UserError(
                    'No se puede eliminar la silobolsa %s: ya tiene viajes confirmados '
                    'o consumo de inventario. Ciérrela o archívela.' % rec.name
                )
        return super().unlink()

    @api.depends('viaje_ids.state', 'viaje_ids.peso_neto_kg', 'viaje_ids.fecha')
    def _compute_totales_viajes(self):
        for rec in self:
            confirmados = rec.viaje_ids.filtered(lambda v: v.state == 'confirmado')
            rec.peso_total_kg = sum(confirmados.mapped('peso_neto_kg'))
            rec.cantidad_viajes = len(confirmados)
            fechas = [f for f in confirmados.mapped('fecha') if f]
            rec.fecha_inicio = min(fechas) if fechas else False
            rec.fecha_fin_embolsado = max(fechas) if fechas else False

    @api.depends('viaje_ids.sitio_id', 'viaje_ids.state')
    def _compute_sitios_origen(self):
        for rec in self:
            sitios = rec.viaje_ids.filtered(
                lambda v: v.state == 'confirmado'
            ).mapped('sitio_id.name')
            rec.sitios_origen = ', '.join(dict.fromkeys(sitios))

    @api.depends('analisis_lab_ids.state', 'analisis_lab_ids.humedad', 'analisis_lab_ids.fecha_hora')
    def _compute_analisis(self):
        for rec in self:
            rec.analisis_count = len(rec.analisis_lab_ids)
            confirmados = rec.analisis_lab_ids.filtered(lambda a: a.state == 'confirmado')
            ultimo = confirmados.sorted(key=lambda a: (a.fecha_hora or fields.Datetime.now(), a.id))
            rec.humedad_ultima = ultimo[-1].humedad if ultimo else 0.0

    def _crear_consumo_silobolsa(self):
        """Consume 1 silobolsa del inventario (al confirmar el primer viaje)."""
        self.ensure_one()
        if self.stock_move_id:
            return

        producto = self.env['product.product'].search([('name', '=', 'Silobolsa')], limit=1)
        if not producto:
            raise UserError('No se encontró el producto "Silobolsa". Reinstale el módulo de embolsado.')

        location_stock = self.env.ref('stock.stock_location_stock', raise_if_not_found=False)
        location_production = self.env['stock.location']._get_produccion_secadora(self.company_id)
        if not location_stock or not location_production:
            raise UserError('No se encontraron las ubicaciones de inventario necesarias.')

        move = self.env['stock.move'].create({
            'description_picking': f'Consumo silobolsa - {self.name}',
            'product_id': producto.id,
            'product_uom_qty': 1,
            'product_uom': producto.uom_id.id,
            'location_id': location_stock.id,
            'location_dest_id': location_production.id,
            'origin': self.name,
        })
        move._action_confirm()
        move._action_assign()
        move._action_done()

        self.stock_move_id = move.id

    def action_cerrar(self):
        for rec in self:
            if rec.state != 'abierto':
                raise UserError('Solo se pueden cerrar silobolsas abiertas.')
            if any(v.state == 'borrador' for v in rec.viaje_ids):
                raise UserError(
                    'La silobolsa %s tiene viajes en borrador. '
                    'Confírmelos o elimínelos antes de cerrar.' % rec.name
                )
            rec.write({'state': 'cerrado', 'fecha_cierre': fields.Datetime.now()})

    def action_reabrir(self):
        if not self.env.user.has_group('secadora_embolsado.group_embolsado_admin'):
            raise UserError('Solo un administrador de embolsado puede reabrir una silobolsa.')
        for rec in self:
            if rec.state != 'cerrado':
                raise UserError('Solo se pueden reabrir silobolsas cerradas.')
            rec.write({'state': 'abierto', 'fecha_cierre': False})

    def action_registrar_viaje(self):
        self.ensure_one()
        return {
            'name': 'Registrar Viaje de Embolsado',
            'type': 'ir.actions.act_window',
            'res_model': 'secadora.registrar.viaje.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_silobolsa_id': self.id},
        }

    def action_ver_analisis(self):
        self.ensure_one()
        return {
            'name': 'Análisis de %s' % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'secadora.analisis.lab',
            'view_mode': 'list,form',
            'domain': [('silobolsa_id', '=', self.id)],
            'context': {'default_silobolsa_id': self.id},
        }

    def action_nuevo_analisis(self):
        self.ensure_one()
        return {
            'name': 'Nuevo Análisis de Silobolsa',
            'type': 'ir.actions.act_window',
            'res_model': 'secadora.analisis.lab',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_silobolsa_id': self.id,
                'default_variedad_id': self.variedad_id.id or False,
            },
        }
