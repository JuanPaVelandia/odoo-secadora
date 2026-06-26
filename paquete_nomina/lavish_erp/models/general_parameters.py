# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging
import datetime
_logger = logging.getLogger(__name__)


# Fechas comemorativas
class LavishDatesCommemorated(models.Model):
    _name = 'lavish.dates.commemorated'
    _description = 'Fechas conmemorativas'

    name = fields.Char('Descripción', required=True)
    date = fields.Date('Fecha', required=True)

    _date_commemorated_uniq = models.Constraint('unique(date)', 'Ya existe un día conmemorativo en esta fecha, por favor verificar.')

# Dias festivos
class lavishHolidays(models.Model):
    _name = 'lavish.holidays'
    _description = 'Días festivos'

    name = fields.Char('Descripción', required=True)
    date = fields.Date('Fecha', required=True)

    _date_holiday_uniq = models.Constraint('unique(date)', 'Ya existe un día festivo en esta fecha, por favor verificar.')

# CIIU
class Ciiu(models.Model):
    _name = 'lavish.ciiu'
    _description = 'CIIU - Actividades economicas'

    code = fields.Char('Codigo', required=True)
    name = fields.Char('Name', required=True)
    porcent_ica = fields.Float(string='Porcentaje ICA')
    
    @api.model
    def name_search(self, name, args=None, operator='ilike', limit=100):
        if not args:
            args = []
        if name:
            ciiu = self.search(['|', ('name', operator, name),('code', operator, name)] + args, limit=limit)
        else:
            ciiu = self.search(args, limit=limit)

        return [(r.id, r.display_name) for r in ciiu]

    def _compute_display_name(self):
        for record in self:
            name = record.name
            if record.code:
                name = u"[%s] %s" % (record.code, name)
            record.display_name = name

# SECTORES
class Sectors(models.Model):
    _name = 'lavish.sectors'
    _description = 'Sectores'

    code = fields.Char(string='Código', size=10,required=True)
    name = fields.Char(string='Nombre', required=True)

    def _compute_display_name(self):
        for record in self:
            record.display_name = "{} | {}".format(record.code, record.name)

# TIPOS DE VINCULACION
class XVinculationTypes(models.Model):
    _name = 'lavish.vinculation_types'
    _description = 'Tipos de vinculación'

    code = fields.Char(string='Código', size=10, required=True)
    name = fields.Char(string='Nombre', size=100, required=True)
    active = fields.Boolean(string='Activo')
    
    def _compute_display_name(self):
        for record in self:
            record.display_name = "{} | {}".format(record.code, record.name)

# RESPONSABILIDADES RUT
class XResponsibilitiesRut(models.Model):
    _name = 'lavish.responsibilities_rut'
    _description = 'Responsabilidades RUT'

    code = fields.Char(string='Identificador', size=10, required=True)
    description = fields.Char(string='Descripción', size=100, required=True)
    valid_for_fe = fields.Boolean(string='Valido para facturación electrónica')
    
    def _compute_display_name(self):
        for record in self:
            record.display_name = "{} | {}".format(record.code, record.description)

# TIPOS DE CONTACTO
class XContactTypes(models.Model):
    _name = 'lavish.contact_types'
    _description = 'Tipos de contacto'
    
    code = fields.Char(string='Código', size=10, required=True)
    name = fields.Char(string='Nombre', required=True)

    def _compute_display_name(self):
        for record in self:
            record.display_name = "{} | {}".format(record.code, record.name)

# TIPOS DE TERCERO
class XTypeThirdparty(models.Model):
    _name = 'lavish.type_thirdparty'
    _description = 'Tipos de tercero'
    
    code = fields.Char(string='Código', size=10, required=True)
    name = fields.Char(string='Nombre', required=True)
    is_company = fields.Boolean('¿Es un tipo de tercero compañia?')
    is_individual = fields.Boolean('¿Es un tipo de tercero individual?')
    types = fields.Selection([('1', 'Cliente / Cuenta'),
                              ('2', 'Contacto'),
                              ('3', 'Proveedor'),
                              ('4', 'Funcionario / Contratista')], string='Tipo', required=True)


    def _compute_display_name(self):
        for record in self:
            record.display_name = "{}".format(record.name)
