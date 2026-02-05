# -*- coding: utf-8 -*-

from odoo import models, fields


class SecadoraTransportadora(models.Model):
    _name = 'secadora.transportadora'
    _description = 'Empresas Transportadoras'
    _order = 'name'

    name = fields.Char(
        string='Nombre',
        required=True,
        index=True
    )
    nit = fields.Char(string='NIT')
    telefono = fields.Char(string='Teléfono')
    direccion = fields.Text(string='Dirección')
    contacto = fields.Char(string='Contacto')
    active = fields.Boolean(
        string='Activo',
        default=True
    )
    vehiculo_ids = fields.One2many(
        'secadora.vehiculo',
        'transportadora_id',
        string='Vehículos'
    )
