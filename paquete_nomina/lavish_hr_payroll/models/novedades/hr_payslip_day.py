# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import date


DAY_TYPE = [
    ('W', 'Trabajado'),
    ('A', 'Ausencia'),
    ('X', 'Sin contrato'),
    ('V', 'VIRTUAL'),
    ('P', 'Permiso'),
    ('H', 'Feriado'),
    ('E', 'Excepcion'),
    ('D', 'Dia de descanso'),
    ('S', 'Sabado'),
    ('C', 'Compensacion'),
]


class HrPayslipDay(models.Model):
    _name = 'hr.payslip.day'
    _description = 'Dias de Nomina'
    _order = 'day'

    payslip_id = fields.Many2one(
        comodel_name='hr.payslip',
        string='Nomina',
        required=True,
        ondelete='cascade'
    )
    day_type = fields.Selection(string='Tipo', selection=DAY_TYPE)
    day = fields.Integer(string='Dia')
    name = fields.Char(string='Nombre', compute="_compute_name")
    subtotal = fields.Float('Subtotal')
    is_holiday = fields.Boolean(
        'Es Festivo',
        default=False,
        help="Indica si este dia es un dia festivo oficial"
    )
    is_sunday = fields.Boolean(
        'Es Domingo',
        default=False,
        help="Indica si este dia es domingo"
    )
    is_saturday = fields.Boolean(
        'Es Sabado',
        default=False,
        help="Indica si este dia es sabado"
    )
    is_permission = fields.Boolean(
        'Con Permiso',
        default=False,
        help="Indica si este dia tiene un permiso registrado (informativo)"
    )
    is_absence = fields.Boolean(
        'Con Ausencia',
        default=False,
        help="Indica si este dia tiene una ausencia que descuenta dias"
    )
    is_day_31 = fields.Boolean(
        'Es Dia 31',
        default=False,
        help="Indica si este dia es el 31 del mes"
    )
    is_feb_last = fields.Boolean(
        'Ultimo de Febrero',
        default=False,
        help="Indica si este dia es el ultimo de febrero (28 o 29)"
    )
    is_virtual = fields.Boolean(
        'Dia Virtual',
        default=False,
        help="Indica si es un dia virtual añadido para calculos"
    )
    feb_adjust = fields.Integer(
        'Ajuste Febrero',
        default=0,
        help="Dias de ajuste para febrero: 2 para feb-28, 1 para feb-29"
    )
    leave_line_id = fields.Many2one(
        'hr.leave.line',
        'Linea de Ausencia',
        help="Linea de ausencia asociada a este dia"
    )
    date_full = fields.Date(
        'Fecha Completa',
        compute='_compute_date_full',
        store=True,
        help="Fecha completa (año-mes-dia)"
    )
    day_of_week = fields.Selection([
        ('0', 'Lunes'),
        ('1', 'Martes'),
        ('2', 'Miercoles'),
        ('3', 'Jueves'),
        ('4', 'Viernes'),
        ('5', 'Sabado'),
        ('6', 'Domingo'),
    ], string='Dia Semana', compute='_compute_date_full', store=True)

    @api.depends('day', 'day_type')
    def _compute_name(self):
        for record in self:
            record.name = str(record.day) + (record.day_type or '')

    @api.depends('payslip_id.date_from', 'day')
    def _compute_date_full(self):
        """Calcula la fecha completa y el dia de la semana"""
        for record in self:
            if not record.payslip_id or not record.payslip_id.date_from or not record.day:
                record.date_full = False
                record.day_of_week = False
                continue
            payslip_date = record.payslip_id.date_from
            try:
                date_full = date(payslip_date.year, payslip_date.month, record.day)
                record.date_full = date_full
                record.day_of_week = str(date_full.weekday())
            except ValueError:
                record.date_full = False
                record.day_of_week = False
