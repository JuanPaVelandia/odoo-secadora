# -*- coding: utf-8 -*-
"""Índices SQL para acelerar las consultas de exógena, certificado de
ingresos y reporte 2276 sobre hr.payslip.line.

Las columnas state_slip / date_from / date_to / employee_id ya existen en
hr.payslip.line (lavish_hr_payroll) pero no están indexadas. Este módulo
crea índices simples y compuestos vía _auto_init() para que los read_group
con dominios típicos del módulo (employee_id + state_slip + rango fechas +
salary_rule_id) se ejecuten directo desde índice.
"""
from odoo import models, tools


class HrPayslipLine(models.Model):
    _inherit = 'hr.payslip.line'

    def init(self):
        # Índice por estado de la nómina (filtro recurrente done/paid)
        tools.create_index(
            self._cr,
            'hr_payslip_line_state_slip_idx',
            'hr_payslip_line',
            ['state_slip'],
        )
        # Índice por fecha desde de la línea (solapamiento con periodo)
        tools.create_index(
            self._cr,
            'hr_payslip_line_date_from_idx',
            'hr_payslip_line',
            ['date_from'],
        )
        # Índice por fecha hasta de la línea
        tools.create_index(
            self._cr,
            'hr_payslip_line_date_to_idx',
            'hr_payslip_line',
            ['date_to'],
        )
        # Índice compuesto que cubre el dominio típico del módulo:
        # employee + state + rango fechas. Usado por
        # _get_payslip_value_by_rules / _sum_payslip_rules.
        tools.create_index(
            self._cr,
            'hr_payslip_line_emp_state_dates_idx',
            'hr_payslip_line',
            ['employee_id', 'state_slip', 'date_from', 'date_to'],
        )
        # Índice por regla salarial + estado: para sumar todas las líneas
        # de una regla en un período sin filtro de empleado.
        tools.create_index(
            self._cr,
            'hr_payslip_line_rule_state_idx',
            'hr_payslip_line',
            ['salary_rule_id', 'state_slip'],
        )
