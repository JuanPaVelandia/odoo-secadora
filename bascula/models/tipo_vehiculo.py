# -*- coding: utf-8 -*-

from odoo import models, fields


class TipoVehiculo(models.Model):
    _name = 'secadora.tipo.vehiculo'
    _description = 'Tipo de Vehículo'
    _order = 'name'

    name = fields.Char(
        string='Nombre',
        required=True,
    )
    active = fields.Boolean(
        string='Activo',
        default=True,
    )

    _name_unique = models.Constraint(
        'unique(name)', 'El tipo de vehículo debe ser único.',
    )
