# -*- coding: utf-8 -*-

from odoo import fields, models


class HrTypesEmployee(models.Model):
    _name = 'hr.types.employee'
    _description = 'Tipos de Empleado'
    _order = 'code, name'
    _rec_name = 'name'

    code = fields.Char(string='Código', required=True, index=True)
    name = fields.Char(string='Nombre', required=True, translate=True)
    description = fields.Text(string='Descripción')
    active = fields.Boolean(string='Activo', default=True)
