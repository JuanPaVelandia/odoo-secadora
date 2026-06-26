# -*- coding: utf-8 -*-
"""
Modelo hr.employee.endowment - Dotacion del empleado.
"""
from odoo import models, fields

class HrEmployeeEndowment(models.Model):
    _name = 'hr.employee.endowment'
    _description = 'Dotación'

    contract_id = fields.Many2one('hr.contract', 'Contrato', required=True, ondelete='cascade')
    date = fields.Date('Fecha de Entrega')
    supplies = fields.Char('Descripción - Periodo de entrega')
    attached = fields.Many2one('documents.document', string='Adjunto')

#Contratos