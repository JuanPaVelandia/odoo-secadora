# -*- coding: utf-8 -*-
"""
Resumen de Nóminas Electrónicas por Empleado.
Modelo transitorio para mostrar agrupación en el lote.
"""
from odoo import api, fields, models


class HrPayslipEdiEmployeeSummary(models.TransientModel):
    _name = 'hr.payslip.edi.employee.summary'
    _description = 'Resumen Nómina Electrónica por Empleado'

    run_id = fields.Many2one(
        'hr.payslip.edi.run', string='Lote',
        required=True, ondelete='cascade'
    )
    employee_id = fields.Many2one(
        'hr.employee', string='Empleado',
        required=True
    )

    # Contadores
    payslip_count = fields.Integer(string='Cantidad Nóminas')
    done_count = fields.Integer(string='Nóminas Listas')
    dian_ok_count = fields.Integer(string='DIAN Exitosos')
    dian_error_count = fields.Integer(string='DIAN Errores')
    dian_pending_count = fields.Integer(string='DIAN Pendientes')

    # Totales
    total_devengados = fields.Float(string='Total Devengados')
    total_deducciones = fields.Float(string='Total Deducciones')
    total_neto = fields.Float(string='Total Neto')

    # Indicadores de estado
    all_dian_ok = fields.Boolean(
        string='Todos DIAN OK',
        compute='_compute_status'
    )
    has_dian_errors = fields.Boolean(
        string='Tiene Errores DIAN',
        compute='_compute_status'
    )
    has_pending_dian = fields.Boolean(
        string='Tiene Pendientes DIAN',
        compute='_compute_status'
    )

    @api.depends('dian_ok_count', 'dian_error_count', 'dian_pending_count', 'done_count')
    def _compute_status(self):
        for record in self:
            record.all_dian_ok = (
                record.done_count > 0 and
                record.dian_ok_count == record.done_count
            )
            record.has_dian_errors = record.dian_error_count > 0
            record.has_pending_dian = (
                record.dian_pending_count > 0 and
                record.dian_error_count == 0
            )
