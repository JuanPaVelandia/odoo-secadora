# -*- coding: utf-8 -*-
from odoo import models, fields


class HrMedicalTemplate(models.Model):
    _name = 'hr.medical.template'
    _description = 'Plantilla de Examen Medico'

    name = fields.Char('Nombre', required=True)
    provider_id = fields.Many2one('hr.medical.provider', 'Proveedor')

    exam_type = fields.Selection([
        ('ingress', 'Ingreso'),
        ('periodic', 'Periodico'),
        ('retirement', 'Retiro'),
        ('post_incapacity', 'Post Incapacidad'),
        ('special', 'Especial'),
        ('height_work', 'Trabajo en Alturas'),
        ('confined_spaces', 'Espacios Confinados'),
    ], string='Tipo de Examen', required=True)

    service_ids = fields.Many2many('hr.medical.service', 'hr_medical_service_hr_medical_template_rel', 'hr_medical_template_id', 'hr_medical_service_id', string='Servicios Incluidos')
    preparation_instructions = fields.Html('Instrucciones de Preparacion')
    duration_hours = fields.Float('Duracion (horas)', default=2.0)
    validity_months = fields.Integer('Vigencia (meses)', default=12)

    active = fields.Boolean('Activo', default=True)
