# -*- coding: utf-8 -*-

from odoo import models, fields


class SecadoraConductor(models.Model):
    _name = 'secadora.conductor'
    _description = 'Conductores'
    _order = 'name'

    name = fields.Char(
        string='Nombre',
        required=True,
        index=True
    )
    cedula = fields.Char(
        string='Cédula',
        required=True,
        index=True
    )
    telefono = fields.Char(string='Teléfono')
    licencia = fields.Char(string='Licencia de Conducción')
    licencia_vencimiento = fields.Date(string='Vencimiento Licencia')
    active = fields.Boolean(
        string='Activo',
        default=True
    )
    vehiculo_ids = fields.One2many(
        'secadora.vehiculo',
        'conductor_habitual_id',
        string='Vehículos'
    )

    _sql_constraints = [
        ('cedula_unique', 'unique(cedula)', 'La cédula del conductor debe ser única.')
    ]
