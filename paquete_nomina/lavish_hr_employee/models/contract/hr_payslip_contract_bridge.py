# -*- coding: utf-8 -*-
from odoo import fields, models


class HrPayslipContractBridge(models.Model):
    _inherit = 'hr.payslip'

    contract_id = fields.Many2one(
        'hr.contract',
        string='Contrato',
        index=True,
        tracking=True,
        help='Contrato asociado a la nomina para compatibilidad con modelos legacy.'
    )
