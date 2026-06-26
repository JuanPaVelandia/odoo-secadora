from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class HrCalculationRtefteOrdinary(models.Model):
    _name = 'hr.calculation.rtefte.ordinary'
    _description = 'Calcula la Retención en la Fuente Ordinaria'

    range_initial = fields.Integer('Rango Inicial UVT',required=True)
    range_finally = fields.Integer('Rango Final UVT',required=True)
    subtract_uvt = fields.Integer('UVTs a restar ',required=True)
    addition_uvt = fields.Integer('UVTs a sumar ',required=True)
    porc = fields.Integer('Porcentaje',required=True)

    _change_rangei_uniq = models.Constraint('unique(range_initial)', 'Ya existe un registro con este rango inicial, por favor verficar.')
    _change_rangef_uniq = models.Constraint('unique(range_finally)', 'Ya existe un registro con este rango final, por favor verficar.')