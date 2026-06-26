# -*- coding: utf-8 -*-
from odoo import models, fields, api


class HrEmployeeBenefitsHistory(models.Model):
    """Historico de prestaciones sociales del empleado"""
    _name = 'hr.employee.benefits.history'
    _description = 'Historico de Prestaciones Sociales'
    _order = 'year desc, date_from desc'

    employee_id = fields.Many2one(
        'hr.employee',
        string='Empleado',
        required=True,
        ondelete='cascade',
        index=True
    )

    contract_id = fields.Many2one(
        'hr.contract',
        string='Contrato',
        ondelete='set null'
    )

    company_id = fields.Many2one(
        'res.company',
        string='Compania',
        related='employee_id.company_id',
        store=True
    )

    benefit_type = fields.Selection([
        ('prima', 'Prima de Servicios'),
        ('cesantias', 'Cesantias'),
        ('intereses_cesantias', 'Intereses sobre Cesantias'),
        ('vacaciones', 'Vacaciones'),
    ], string='Tipo de Prestacion', required=True, index=True)

    period_type = fields.Selection([
        ('first_semester', 'Primer Semestre'),
        ('second_semester', 'Segundo Semestre'),
        ('annual', 'Anual'),
        ('partial', 'Parcial'),
        ('liquidation', 'Liquidacion'),
    ], string='Tipo de Periodo', default='first_semester')

    year = fields.Integer(
        string='Ano',
        required=True,
        index=True
    )

    date_from = fields.Date(
        string='Fecha Desde',
        required=True
    )

    date_to = fields.Date(
        string='Fecha Hasta',
        required=True
    )

    payslip_id = fields.Many2one(
        'hr.payslip',
        string='Nomina',
        ondelete='set null'
    )

    payslip_run_id = fields.Many2one(
        'hr.payslip.run',
        string='Lote de Nomina',
        ondelete='set null'
    )

    days_worked = fields.Integer(
        string='Dias Trabajados',
        default=0
    )

    days_paid = fields.Integer(
        string='Dias Pagados',
        default=0
    )

    base_amount = fields.Monetary(
        string='Base de Calculo',
        currency_field='currency_id'
    )

    amount = fields.Monetary(
        string='Valor Pagado',
        currency_field='currency_id'
    )

    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        related='company_id.currency_id'
    )

    state = fields.Selection([
        ('draft', 'Borrador'),
        ('confirmed', 'Confirmado'),
        ('paid', 'Pagado'),
    ], string='Estado', default='draft', index=True)

    notes = fields.Text(string='Observaciones')

    _unique_benefit_period = models.Constraint('unique(employee_id, benefit_type, period_type, year)',
                                               'Ya existe un registro de esta prestacion para este empleado en el mismo periodo')
