# -*- coding: utf-8 -*-
from odoo import models, fields


class HrMedicalService(models.Model):
    _name = 'hr.medical.service'
    _description = 'Servicio Medico'

    name = fields.Char('Nombre', required=True)
    code = fields.Char('Codigo')
    description = fields.Text('Descripcion')

    service_type = fields.Selection([
        ('blood_test', 'Examenes de Sangre'),
        ('urine_test', 'Examenes de Orina'),
        ('xray', 'Rayos X'),
        ('ultrasound', 'Ecografia'),
        ('electrocardiogram', 'Electrocardiograma'),
        ('spirometry', 'Espirometria'),
        ('audiometry', 'Audiometria'),
        ('optometry', 'Optometria'),
        ('psychology', 'Psicologia'),
        ('occupational', 'Medicina Ocupacional'),
        ('height_work', 'Trabajo en Alturas'),
        ('confined_spaces', 'Espacios Confinados'),
        ('other', 'Otro'),
    ], string='Tipo', required=True)

    price = fields.Float('Precio')
    product_id = fields.Many2one('product.product', 'Producto')
