# -*- coding: utf-8 -*-

from odoo import models, fields


class SecadoraTipoDeduccion(models.Model):
    _name = 'secadora.tipo.deduccion'
    _description = 'Tipo de Deducción'
    _order = 'sequence, name'

    _sql_constraints = [
        ('codigo_company_unique', 'UNIQUE(codigo, company_id)',
         'Ya existe un tipo de deducción con este código para la misma empresa.'),
    ]

    name = fields.Char(
        string='Nombre',
        required=True,
    )
    codigo = fields.Char(
        string='Código',
        required=True,
        index=True,
    )
    tipo_calculo = fields.Selection([
        ('porcentaje', 'Porcentaje'),
        ('fijo', 'Monto Fijo'),
    ], string='Tipo de Cálculo', required=True, default='porcentaje')
    valor = fields.Float(
        string='Valor',
        required=True,
        digits=(12, 4),
        help='Porcentaje (ej: 2.5 para 2.5%) o monto fijo en pesos',
    )
    sequence = fields.Integer(
        string='Orden',
        default=10,
    )
    active = fields.Boolean(
        string='Activo',
        default=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        help='Vacío = aplica a todas las empresas',
    )
