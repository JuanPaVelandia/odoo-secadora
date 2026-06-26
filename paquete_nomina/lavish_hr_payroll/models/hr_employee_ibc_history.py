# -*- coding: utf-8 -*-
"""
Historial IBC del Empleado
==========================
Modelo para registrar el Ingreso Base de Cotizacion historico.
Extraido de res_config_settings.py para mejor organizacion.
"""

from odoo import api, fields, models, _
import logging

_logger = logging.getLogger(__name__)


class HrEmployeeIbcHistory(models.Model):
    _name = 'hr.employee.ibc.history'
    _description = 'Historial IBC del Empleado'
    _order = 'year desc, month desc, id desc'

    name = fields.Char(
        string='Nombre',
        store=True,
        index=True
    )

    employee_id = fields.Many2one(
        'hr.employee',
        string='Empleado',
        required=True,
        ondelete='cascade',
        index=True,
        help="Empleado al que pertenece este registro"
    )

    contract_id = fields.Many2one(
        'hr.contract',
        string='Contrato',
        required=True,
        ondelete='cascade',
        index=True,
        help="Contrato vigente al momento del registro"
    )

    year = fields.Integer(
        string='Ano',
        required=True,
        index=True,
        help="Ano al que corresponde este registro IBC"
    )

    month = fields.Integer(
        string='Mes',
        required=True,
        index=True,
        help="Mes al que corresponde este registro IBC (1-12)"
    )

    ibc_value = fields.Float(
        string='Valor IBC',
        digits='Payroll',
        required=True,
        help="Ingreso Base de Cotizacion calculado para este periodo"
    )

    ibc_daily = fields.Float(
        string='IBC diario',
        digits='Payroll',
        store=True,
        help="Valor IBC diario (IBC / dias cotizados)"
    )

    ibc_days = fields.Integer(
        string='Dias cotizados',
        default=30,
        help="Dias efectivamente cotizados en este periodo"
    )

    date_from = fields.Date(
        string='Fecha inicio',
        help="Fecha de inicio del periodo"
    )

    date_to = fields.Date(
        string='Fecha fin',
        help="Fecha de fin del periodo"
    )

    payslip_id = fields.Many2many(
        'hr.payslip',
        string='Nomina',
        help="Nomina que genero este registro"
    )

    wage = fields.Float(
        string='Salario base',
        digits='Payroll',
        help="Salario base del empleado en este periodo"
    )

    salarial_items = fields.Float(
        string='Componentes salariales',
        digits='Payroll',
        help="Valor de componentes salariales adicionales (horas extra, recargos, etc.)"
    )

    non_salarial_items = fields.Float(
        string='Componentes no salariales',
        digits='Payroll',
        help="Valor de componentes no salariales"
    )

    rule40_limit = fields.Float(
        string='Limite 40%',
        digits='Payroll',
        store=True,
        help="Limite del 40% para componentes no salariales"
    )

    applied_40_rule = fields.Boolean(
        string='Aplico regla 40%',
        help="Indica si se aplico la regla del 40% para componentes no salariales"
    )

    exceed_40_value = fields.Float(
        string='Excedente 40%',
        digits='Payroll',
        store=True,
        help="Valor que excede el limite del 40%"
    )

    company_id = fields.Many2one(
        'res.company',
        string='Compania',
        required=True,
        default=lambda self: self.env.company
    )

    @api.depends('employee_id', 'year', 'month', 'ibc_value')
    def _compute_display_name(self):
        """Genera nombre descriptivo"""
        for record in self:
            if record.employee_id and record.year and record.month:
                record.name = f"{record.employee_id.name} - {record.year}/{record.month:02d} - IBC: {record.ibc_value:,.0f}"
            else:
                record.name = "Registro IBC"

    @api.model
    def get_ibc_for_period(self, employee_id, year, month):
        """Obtiene el IBC registrado para un periodo especifico"""
        return self.search([
            ('employee_id', '=', employee_id),
            ('year', '=', year),
            ('month', '=', month)
        ], limit=1)

    @api.model
    def get_ibc_history(self, employee_id, months=12):
        """Obtiene el historial de IBC de los ultimos N meses"""
        return self.search([
            ('employee_id', '=', employee_id)
        ], order='year desc, month desc', limit=months)

    @api.model
    def get_average_ibc(self, employee_id, months=3):
        """Calcula el promedio IBC de los ultimos N meses"""
        records = self.get_ibc_history(employee_id, months)
        if not records:
            return 0.0
        return sum(records.mapped('ibc_value')) / len(records)
