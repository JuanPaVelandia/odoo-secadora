# -*- coding: utf-8 -*-

from odoo import models, fields


class OrigenMuestra(models.Model):
    _name = 'secadora.origen.muestra'
    _description = 'Origen de Muestra'
    _order = 'sequence, id'

    name = fields.Char(string='Nombre', required=True)
    codigo = fields.Char(string='Código')
    active = fields.Boolean(string='Activo', default=True)
    sequence = fields.Integer(string='Orden', default=10)


class SitioMuestra(models.Model):
    _name = 'secadora.sitio.muestra'
    _description = 'Sitio de Muestra'
    _order = 'origen_id, name'

    name = fields.Char(string='Nombre', required=True)
    origen_id = fields.Many2one(
        'secadora.origen.muestra',
        string='Categoría de Origen',
        required=True,
        index=True
    )
    codigo = fields.Char(string='Código')
    active = fields.Boolean(string='Activo', default=True)
