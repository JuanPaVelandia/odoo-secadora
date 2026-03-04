# -*- coding: utf-8 -*-

from odoo import models, fields


class SecadoraLiquidacionDeduccion(models.Model):
    _name = 'secadora.liquidacion.deduccion'
    _description = 'Deducción de Liquidación'
    _order = 'sequence, id'

    liquidacion_id = fields.Many2one(
        'secadora.liquidacion',
        string='Liquidación',
        required=True,
        ondelete='cascade',
        index=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        related='liquidacion_id.company_id',
        store=True,
    )
    sequence = fields.Integer(
        string='Orden',
        default=10,
    )
    tipo = fields.Selection([
        ('flete', 'Flete'),
        ('descargue', 'Descargue'),
        ('retencion', 'Retención'),
        ('otro', 'Otro'),
    ], string='Tipo', required=True, default='otro')
    descripcion = fields.Char(
        string='Descripción',
        required=True,
    )
    monto = fields.Float(
        string='Monto ($)',
        required=True,
        digits=(12, 2),
    )
    flete_id = fields.Many2one(
        'secadora.flete',
        string='Flete Vinculado',
        help='Flete vinculado (cuando se carga automáticamente)',
    )
    tipo_deduccion_id = fields.Many2one(
        'secadora.tipo.deduccion',
        string='Tipo Deducción',
        help='Tipo de deducción (cuando se aplica automáticamente)',
    )
    notas = fields.Text(string='Notas')
