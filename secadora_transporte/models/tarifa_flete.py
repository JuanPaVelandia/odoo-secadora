# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


class SecadoraTarifaFlete(models.Model):
    _name = 'secadora.tarifa.flete'
    _description = 'Tarifa de Flete por Ruta'
    _order = 'origen_id, destino_id'
    _ruta_producto_unico = models.Constraint(
        'UNIQUE(origen_id, destino_id, producto_id)',
        'Ya existe una tarifa para esta ruta y producto (origen → destino → producto).',
    )

    origen_id = fields.Many2one(
        'secadora.lugar',
        string='Origen',
        required=True,
        index=True,
    )
    destino_id = fields.Many2one(
        'secadora.lugar',
        string='Destino',
        required=True,
        index=True,
    )
    producto_id = fields.Many2one(
        'product.product',
        string='Producto',
        index=True,
        help='Producto al que aplica esta tarifa. Vacío = tarifa general para '
             'cualquier producto de la ruta. Si hay una tarifa específica para '
             'el producto del flete, esa tiene prioridad sobre la general.',
    )
    tarifa_tipo = fields.Selection([
        ('por_kg', 'Por Kilogramo'),
        ('por_viaje', 'Por Viaje'),
        ('por_bulto', 'Por Bulto'),
    ], string='Tipo de Tarifa', required=True, default='por_viaje')

    tarifa_unitaria = fields.Float(
        string='Tarifa Unitaria',
        required=True,
        digits='Product Price',
    )
    active = fields.Boolean(string='Activo', default=True)
    notas = fields.Text(string='Notas')

    @api.constrains('origen_id', 'destino_id', 'producto_id')
    def _check_general_unica(self):
        """Una sola tarifa GENERAL (sin producto) por ruta.

        El UNIQUE de PostgreSQL trata cada NULL como distinto, así que no
        impide dos tarifas generales de la misma ruta; se valida aquí.
        """
        for rec in self:
            if rec.producto_id:
                continue
            dup = self.search_count([
                ('origen_id', '=', rec.origen_id.id),
                ('destino_id', '=', rec.destino_id.id),
                ('producto_id', '=', False),
                ('id', '!=', rec.id),
            ])
            if dup:
                raise ValidationError(
                    'Ya existe una tarifa general (sin producto) para esta ruta. '
                    'Edita esa, o asígnale un producto a esta tarifa.')

    @api.constrains('origen_id', 'destino_id')
    def _check_origen_destino_diferente(self):
        for rec in self:
            if rec.origen_id and rec.destino_id and rec.origen_id == rec.destino_id:
                raise UserError('El origen y destino de la tarifa deben ser diferentes.')

    @api.depends('origen_id', 'destino_id')
    def _compute_display_name(self):
        for rec in self:
            if rec.origen_id and rec.destino_id:
                rec.display_name = f'{rec.origen_id.name} → {rec.destino_id.name}'
            else:
                rec.display_name = 'Nueva Tarifa'
