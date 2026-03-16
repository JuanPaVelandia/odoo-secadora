# -*- coding: utf-8 -*-

from odoo import models, fields


class LiquidacionCuadrillaDeduccion(models.Model):
    _name = 'secadora.cuadrilla.liquidacion.deduccion'
    _description = 'Deducción de Liquidación de Cuadrilla'
    _order = 'sequence, id'

    liquidacion_id = fields.Many2one(
        'secadora.cuadrilla.liquidacion',
        string='Liquidación',
        required=True,
        ondelete='cascade',
    )
    sequence = fields.Integer(default=10)
    tipo = fields.Selection([
        ('anticipo', 'Anticipo'),
        ('deduccion', 'Deducción'),
        ('otro', 'Otro'),
    ], string='Tipo', required=True, default='deduccion')
    descripcion = fields.Char(string='Descripción', required=True)
    monto = fields.Float(string='Monto', required=True, digits=(12, 2))
    notas = fields.Text(string='Notas')
