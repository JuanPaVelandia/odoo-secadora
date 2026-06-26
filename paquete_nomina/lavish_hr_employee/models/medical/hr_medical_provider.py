# -*- coding: utf-8 -*-
from odoo import models, fields


class HrMedicalProvider(models.Model):
    _name = 'hr.medical.provider'
    _description = 'Proveedor Medico'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char('Nombre', required=True)
    provider_type = fields.Selection([
        ('laboratory', 'Laboratorio'),
        ('clinic', 'Clinica'),
        ('hospital', 'Hospital'),
        ('medical_center', 'Centro Medico'),
        ('specialist', 'Especialista'),
    ], string='Tipo', required=True)

    partner_id = fields.Many2one('res.partner', 'Contacto', required=True)
    nit = fields.Char('NIT', related='partner_id.vat')
    phone = fields.Char('Telefono', related='partner_id.phone')
    email = fields.Char('Email', related='partner_id.email')
    street = fields.Char('Direccion', related='partner_id.street')
    city = fields.Char('Ciudad', related='partner_id.city')

    service_ids = fields.Many2many('hr.medical.service', 'hr_medical_provider_hr_medical_service_rel', 'hr_medical_provider_id', 'hr_medical_service_id', string='Servicios')
    template_ids = fields.One2many('hr.medical.template', 'provider_id', 'Plantillas')

    active = fields.Boolean('Activo', default=True)
