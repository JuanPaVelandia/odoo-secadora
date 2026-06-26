# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)
class HrDepartment(models.Model):
    _name = 'hr.job'
    _inherit = ['hr.job', 'accounting.configuration.mixin']
    
    accounting_config_ids = fields.One2many(
        'hr.salary.rule.accounting',
        'job_id',
        string='Configuraciones Contables'
    )
