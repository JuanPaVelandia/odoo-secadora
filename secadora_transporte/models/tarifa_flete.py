# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError


class SecadoraTarifaFlete(models.Model):
    _name = 'secadora.tarifa.flete'
    _description = 'Tarifa de Flete por Ruta'
    _order = 'origen_id, destino_id'
    _sql_constraints = [
        ('ruta_unica', 'UNIQUE(origen_id, destino_id)',
         'Ya existe una tarifa para esta ruta (origen → destino).'),
    ]

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
