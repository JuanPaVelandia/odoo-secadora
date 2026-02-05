# -*- coding: utf-8 -*-

from odoo import models, fields


class SecadoraVariedadArroz(models.Model):
    _name = 'secadora.variedad.arroz'
    _description = 'Variedades de Arroz'
    _order = 'name'

    name = fields.Char(
        string='Nombre',
        required=True,
        index=True,
        help='Ej: Fedearroz 67, Fedearroz 174, IR 1529'
    )
    codigo = fields.Char(string='Código')
    descripcion = fields.Text(string='Descripción')
    active = fields.Boolean(
        string='Activo',
        default=True
    )
