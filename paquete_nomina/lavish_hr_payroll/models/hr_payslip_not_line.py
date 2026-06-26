# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class HrPayslipNotLine(models.Model):
    _name = 'hr.payslip.not.line'
    _description = 'Reglas no aplicadas'

    name = fields.Char(string='Nombre', required=True, translate=True)
    note = fields.Text(string='Descripcion')
    sequence = fields.Integer(
        string='Secuencia',
        required=True,
        index=True,
        default=5,
        help='Use to arrange calculation sequence'
    )
    run_id = fields.Many2one('hr.payslip.run', 'Lote de nomina')
    code = fields.Char(string='Codigo', required=True)
    slip_id = fields.Many2one(
        'hr.payslip',
        string='Nomina',
        required=True,
        ondelete='cascade'
    )
    salary_rule_id = fields.Many2one(
        'hr.salary.rule',
        string='Regla',
        required=True
    )
    category_id = fields.Many2one(
        related='salary_rule_id.category_id',
        string='Categoria',
        readonly=True,
        store=True
    )
    contract_id = fields.Many2one(
        'hr.contract',
        string='Contrato',
        required=True,
        index=True
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Empleado',
        required=True
    )
    entity_id = fields.Many2one('hr.employee.entities', string="Entidad")
    loan_id = fields.Many2one('hr.loan', 'Prestamo', readonly=True)
    rate = fields.Float(
        string='Porcentaje (%)',
        digits='Payroll Rate',
        default=100.0
    )
    amount = fields.Float(string='Importe', digits='Payroll')
    quantity = fields.Float(
        string='Cantidad',
        digits='Payroll',
        default=1.0
    )
    total = fields.Float(
        compute='_compute_total',
        string='Total',
        digits='Payroll',
        store=True
    )
    subtotal = fields.Float('Subtotal')
    category_code = fields.Char(
        related='salary_rule_id.category_id.code',
        string='Código Categoría',
        readonly=True,
        store=True
    )

    @api.depends('quantity', 'amount', 'rate', 'subtotal')
    def _compute_total(self):
        for line in self:
            if line.subtotal != 0.0:
                line.total = line.subtotal
            else:
                line.total = float(line.quantity) * line.amount * line.rate / 100

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if 'employee_id' not in values or 'contract_id' not in values:
                payslip = self.env['hr.payslip'].browse(values.get('slip_id'))
                values['employee_id'] = values.get('employee_id') or payslip.employee_id.id
                values['contract_id'] = values.get('contract_id') or payslip.contract_id and payslip.contract_id.id
                if not values['contract_id']:
                    raise UserError(_('You must set a contract to create a payslip line.'))
        return super(HrPayslipNotLine, self).create(vals_list)
