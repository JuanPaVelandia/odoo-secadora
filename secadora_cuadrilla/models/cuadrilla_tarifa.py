# -*- coding: utf-8 -*-

from odoo import models, fields


class CuadrillaTarifa(models.Model):
    _name = 'secadora.cuadrilla.tarifa'
    _description = 'Tarifa de Cuadrilla por Servicio'
    _order = 'producto_id'
    _sql_constraints = [
        ('producto_company_uniq', 'UNIQUE(producto_id, company_id)',
         'Ya existe una tarifa para este servicio en esta empresa.'),
    ]

    producto_id = fields.Many2one(
        'product.product',
        string='Servicio',
        required=True,
        domain=[('type', '=', 'service')],
    )
    name = fields.Char(
        string='Nombre',
        related='producto_id.name',
    )
    tarifa = fields.Float(
        string='Tarifa ($/kg)',
        required=True,
        digits=(12, 2),
    )
    base_peso = fields.Selection([
        ('peso_entrada', 'Peso de Entrada'),
        ('peso_salida', 'Peso de Salida'),
        ('peso_neto', 'Peso Neto'),
        ('bultos', 'Cantidad de Bultos'),
        ('fijo', 'Cantidad Fija'),
    ], string='Base de Peso', required=True, default='peso_entrada')
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        help='Vacío = aplica a todas las empresas',
    )
