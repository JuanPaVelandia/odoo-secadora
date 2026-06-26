# -*- coding: utf-8 -*-
"""
Tipos de nota de ajuste para nómina electrónica DIAN.
"""
from odoo import fields, models


class HrTypeNote(models.Model):
    _name = 'hr.type.note'
    _description = 'Tipo de Nota Ajuste DIAN'

    name = fields.Char(string='Nombre', required=True)
    code = fields.Char(string='Código', required=True)
    active = fields.Boolean(string='Activo', default=True)
