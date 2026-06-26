# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class HrPayslipWorkedDays(models.Model):
    """Extensión de Líneas de Días Trabajados para vincular con Tipos de Ausencia"""
    _inherit = 'hr.payslip.worked_days'

    # Campo para días de auxilio de transporte
    number_of_days_aux = fields.Float(
        string='Días Aux. Transp.',
        digits='Payroll',
        help='Número de días para cálculo del auxilio de transporte'
    )

    # Campo para horas de auxilio de transporte
    number_of_hours_aux = fields.Float(
        string='Horas Aux. Transp.',
        digits='Payroll',
        help='Número de horas para cálculo del auxilio de transporte'
    )

    # Campo símbolo para indicar si suma (+), resta (-) o es neutral
    symbol = fields.Char(
        string='Símbolo',
        size=1,
        help='Indica si el registro suma (+), resta (-) o es neutral en el cálculo'
    )

    # Campo monto para el valor calculado
    amount = fields.Float(
        string='Monto',
        digits='Payroll',
        help='Valor monetario calculado para esta línea'
    )

    # Relación con tipo de ausencia
    leave_type_id = fields.Many2one(
        'hr.leave.type',
        string='Tipo de Ausencia',
        help='Tipo de ausencia asociado a esta línea de días trabajados'
    )

    # Campos computados para mostrar información del tipo de ausencia
    leave_type_code = fields.Char(
        string='Código Ausencia',
        related='leave_type_id.code',
        store=True,
        readonly=True
    )

    leave_type_novelty = fields.Selection(
        string='Novedad PILA',
        related='leave_type_id.novelty',
        store=True,
        readonly=True
    )

    is_vacation_type = fields.Boolean(
        string='Es Vacación',
        related='leave_type_id.is_vacation',
        store=True,
        readonly=True
    )

    is_vacation_money = fields.Boolean(
        string='Vacación en Dinero',
        related='leave_type_id.is_vacation_money',
        store=True,
        readonly=True
    )

    # Campos para mostrar en kanban
    display_info = fields.Char(
        string='Info Display',
        compute='_compute_display_info',
        store=False
    )

    color_kanban = fields.Integer(
        string='Color Kanban',
        compute='_compute_kanban_color',
        store=False
    )

    @api.depends('code', 'name', 'number_of_days', 'leave_type_id')
    def _compute_display_info(self):
        """Computa información para mostrar en el kanban"""
        for record in self:
            if record.leave_type_id:
                record.display_info = f"{record.code} - {record.leave_type_id.name}"
            else:
                record.display_info = f"{record.code} - {record.name}"

    @api.depends('code', 'leave_type_id', 'is_paid')
    def _compute_kanban_color(self):
        """Asigna color según el tipo de código"""
        for record in self:
            if record.code == 'WORK100':
                record.color_kanban = 10  # Verde - días normales
            elif record.code == 'WORK_D':
                record.color_kanban = 7   # Azul - días del período
            elif record.is_vacation_type or record.is_vacation_money:
                record.color_kanban = 4   # Amarillo - vacaciones
            elif not record.is_paid:
                record.color_kanban = 1   # Rojo - no pagado
            elif record.leave_type_id:
                record.color_kanban = 3   # Naranja - ausencias
            else:
                record.color_kanban = 0   # Gris - otros

    @api.model_create_multi
    def create(self, vals_list):
        """Al crear, intentar asociar automáticamente el tipo de ausencia"""
        records = super().create(vals_list)

        # Si tiene un código y no tiene leave_type_id, buscar por código
        for record in records:
            if record.code and not record.leave_type_id:
                leave_type = self.env['hr.leave.type'].search([
                    ('code', '=', record.code)
                ], limit=1)

                if leave_type:
                    record.leave_type_id = leave_type.id

        return records
