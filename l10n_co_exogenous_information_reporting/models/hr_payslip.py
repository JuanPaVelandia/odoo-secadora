# -*- coding: utf-8 -*-
from odoo import fields, models, tools


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    employee_severance_pay = fields.Boolean(
        string='Cesantías pagadas al empleado',
        default=False,
        index=True,
        help='Marcar cuando esta nómina liquida cesantías directamente al '
             'empleado (régimen tradicional / pago retiro) en lugar de '
             'consignarlas al fondo. Se usa para clasificar cesantías en el '
             'certificado de ingresos y en el reporte 2276.'
    )

    def init(self):
        # Índice compuesto típico para clasificar cesantías por empleado en
        # un periodo: filtra por employee_id + estado + flag de cesantías.
        tools.create_index(
            self._cr,
            'hr_payslip_emp_state_severance_idx',
            'hr_payslip',
            ['employee_id', 'state', 'employee_severance_pay'],
        )
