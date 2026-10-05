# -*- coding: utf-8 -*-

from odoo import models, fields

UNIDADES = [
    ('ha', 'Hectárea'),
    ('bulto', 'Bulto'),
    ('dia', 'Día'),
    ('mes', 'Mes'),
    ('unidad', 'Unidad'),
]


class FincaLabor(models.Model):
    _name = 'finca.labor'
    _description = 'Labor de Finca'
    _order = 'tipo, sequence, name'

    _name_tipo_unique = models.Constraint(
        'UNIQUE(name, tipo)',
        'Ya existe una labor con ese nombre.',
    )

    name = fields.Char(string='Labor', required=True)
    sequence = fields.Integer(default=10)
    tipo = fields.Selection([
        ('contrato', 'Por contrato'),
        ('jornal', 'Jornal'),
    ], string='Tipo', required=True, default='contrato')
    unidad = fields.Selection(UNIDADES, string='Unidad', required=True, default='ha')
    valor_unitario = fields.Float(
        string='Tarifa',
        digits=(12, 2),
        help='Valor por unidad. Se propone al registrar la labor y se puede ajustar.',
    )
    active = fields.Boolean(default=True)
    notes = fields.Text(string='Notas')
