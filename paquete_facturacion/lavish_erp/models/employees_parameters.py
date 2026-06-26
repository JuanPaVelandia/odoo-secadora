# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain as expression
import datetime


# ÁREAS
class XAreas(models.Model):
    _name = 'lavish.areas'
    _description = 'Áreas'
    _order = 'code,name'

    code = fields.Char(string='Código', size=10, required=True)
    name = fields.Char(string='Nombre', required=True)

    def _compute_display_name(self):
        for record in self:
            record.display_name = "{} | {}".format(record.code, record.name)

# CARGOS
class XJobTitle(models.Model):
    _name = 'lavish.job_title'
    _description = 'Cargos'
    _order = 'area_id,code,name'

    name = fields.Char(string='Nombre', required=True)
    area_id = fields.Many2one('lavish.areas', string='Área')
    code = fields.Char(string='Código', size=10, required=True)


    def _compute_display_name(self):
        for record in self:
            record.display_name = "{} | {}".format(record.code, record.name)

# GRUPOS DE TRABAJO
class XWorkGroups(models.Model):
    _name = 'lavish.work_groups'
    _description = 'Grupos de Trabajo'
    
    name = fields.Char(string='Nombre', required=True)
    code = fields.Char(string='Código', size=10, required=True)


    def _compute_display_name(self):
        for record in self:
            record.display_name = "{} | {}".format(record.code, record.name)
