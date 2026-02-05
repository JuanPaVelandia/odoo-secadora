# -*- coding: utf-8 -*-

from odoo import models, fields


class SecadoraLugar(models.Model):
    _name = 'secadora.lugar'
    _description = 'Lugares (Fincas, Bodegas, etc.)'
    _order = 'name'

    name = fields.Char(
        string='Nombre',
        required=True,
        index=True,
        help='Nombre del lugar (Ej: Finca La Esperanza, Bodega Central)'
    )
    tipo = fields.Selection([
        ('finca', 'Finca'),
        ('bodega', 'Bodega'),
        ('planta', 'Planta'),
        ('otro', 'Otro'),
    ], string='Tipo de Lugar', default='finca')
    codigo = fields.Char(string='Código')
    direccion = fields.Text(string='Dirección')
    municipio = fields.Char(string='Municipio')
    departamento = fields.Char(string='Departamento')
    contacto = fields.Char(string='Contacto')
    telefono = fields.Char(string='Teléfono')
    active = fields.Boolean(
        string='Activo',
        default=True
    )
    notes = fields.Text(string='Notas')
