# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)
    
class HrDepartment(models.Model):
    _name = 'hr.department'
    _inherit = ['hr.department', 'accounting.configuration.mixin']
    
    # Relaciones
    accounting_config_ids = fields.One2many(
        'hr.salary.rule.accounting',
        'department_id',
        string='Configuraciones Contables'
    )

