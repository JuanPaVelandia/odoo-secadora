# -*- coding: utf-8 -*-
"""
Líneas de Nómina Electrónica y Días Trabajados.
"""
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HrPayslipEdiLine(models.Model):
    _name = 'hr.payslip.edi.line'
    _description = 'Línea de Nómina Electrónica'
    _order = 'version_id, sequence, code'

    slip_id = fields.Many2one(
        'hr.payslip.edi', string='Nómina Electrónica',
        required=True, ondelete='cascade'
    )
    name = fields.Char(string='Nombre', required=True)
    code = fields.Char(string='Código', required=True)
    sequence = fields.Integer(string='Secuencia', default=5, index=True)
    salary_rule_id = fields.Many2one(
        'hr.salary.rule', string='Regla Salarial',
        help='Opcional para líneas informativas'
    )
    category_id = fields.Many2one(related='salary_rule_id.category_id', store=True)
    dev_or_ded = fields.Selection(
        [('devengo', 'Devengo'), ('deduccion', 'Deducción')],
        string='Tipo',
        compute='_compute_dev_or_ded',
        store=True
    )

    @api.depends('salary_rule_id', 'salary_rule_id.devengado_rule_id', 'salary_rule_id.deduccion_rule_id')
    def _compute_dev_or_ded(self):
        """Determina si la línea es devengo o deducción basándose en la regla salarial."""
        for line in self:
            if line.salary_rule_id:
                if line.salary_rule_id.devengado_rule_id:
                    line.dev_or_ded = 'devengo'
                elif line.salary_rule_id.deduccion_rule_id:
                    line.dev_or_ded = 'deduccion'
                else:
                    line.dev_or_ded = False
            else:
                line.dev_or_ded = False
    version_id = fields.Many2one('hr.version', string='Versión Contrato', index=True)
    employee_id = fields.Many2one('hr.employee', string='Empleado')

    quantity = fields.Float(string='Cantidad', default=1.0)
    rate = fields.Float(string='Tasa (%)', default=100.0)
    amount = fields.Float(string='Monto')
    total = fields.Float(string='Total', compute='_compute_total', store=True)

    # Campos para ausencias y extras
    leave_id = fields.Many2one('hr.leave', string='Ausencia')
    departure_date = fields.Date(string='Fecha Salida')
    return_date = fields.Date(string='Fecha Regreso')
    overtime_id = fields.Many2one('hr.overtime', string='Hora Extra')

    # Campos adicionales para XML DIAN
    line_type = fields.Selection([
        ('normal', 'Normal'),
        ('informativo', 'Informativo'),
    ], string='Tipo Línea', default='normal')
    rate_2 = fields.Float(string='Tasa Secundaria (%)')
    total_2 = fields.Float(string='Total Secundario')

    # Campos para líneas informativas
    info_type = fields.Selection([
        ('ausencia', 'Ausencia'),
        ('dotacion', 'Dotación'),
        ('sindicato', 'Sindicato'),
        ('fondo_pension', 'Fondo Pensión'),
        ('fondo_cesantias', 'Fondo Cesantías'),
        ('eps', 'EPS'),
        ('arl', 'ARL'),
        ('caja_compensacion', 'Caja Compensación'),
        ('banco', 'Banco'),
        ('cuenta', 'Cuenta Bancaria'),
        ('centro_costo', 'Centro de Costo'),
        ('otro', 'Otro'),
    ], string='Tipo Informativo', help='Tipo de información para líneas informativas')
    info_value = fields.Char(string='Valor Informativo', help='Valor de texto para líneas informativas')
    info_code = fields.Char(string='Código Entidad', help='Código de la entidad (NIT, código, etc.)')
    info_percentage = fields.Float(string='Porcentaje Info', help='Porcentaje informativo (ej: aporte sindicato)')
    info_notes = fields.Text(string='Observaciones', help='Notas adicionales')

    # Código DIAN (del devengado/deduccion rule)
    dian_code = fields.Char(
        string='Código DIAN',
        compute='_compute_dian_code',
        store=True,
    )

    @api.depends('salary_rule_id', 'salary_rule_id.devengado_rule_id',
                 'salary_rule_id.deduccion_rule_id')
    def _compute_dian_code(self):
        for line in self:
            if line.salary_rule_id:
                dev = line.salary_rule_id.devengado_rule_id
                ded = line.salary_rule_id.deduccion_rule_id
                line.dian_code = (dev.code if dev else ded.code if ded else '')
            else:
                line.dian_code = ''

    # Relacionados
    date_from = fields.Date(related='slip_id.date_from', store=True)
    date_to = fields.Date(related='slip_id.date_to', store=True)
    company_id = fields.Many2one(related='slip_id.company_id')

    @api.depends('quantity', 'amount', 'rate')
    def _compute_total(self):
        for line in self:
            line.total = float(line.quantity) * line.amount * line.rate / 100

    @api.onchange('line_type', 'info_type')
    def _onchange_info_type(self):
        """Auto-completar nombre y código para líneas informativas."""
        if self.line_type == 'informativo' and self.info_type:
            type_names = {
                'ausencia': 'Ausencia',
                'dotacion': 'Dotación',
                'sindicato': 'Sindicato',
                'fondo_pension': 'Fondo de Pensión',
                'fondo_cesantias': 'Fondo de Cesantías',
                'eps': 'EPS',
                'arl': 'ARL',
                'caja_compensacion': 'Caja de Compensación',
                'banco': 'Banco',
                'cuenta': 'Cuenta Bancaria',
                'centro_costo': 'Centro de Costo',
                'otro': 'Otro',
            }
            if not self.name or self.name in type_names.values():
                self.name = type_names.get(self.info_type, 'Informativo')
            if not self.code:
                self.code = 'INFO_' + self.info_type.upper()

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            # Para líneas informativas, employee_id y contract_id son opcionales
            is_informativo = values.get('line_type') == 'informativo'

            if 'employee_id' not in values or 'version_id' not in values:
                payslip = self.env['hr.payslip.edi'].browse(values.get('slip_id'))
                values.setdefault('employee_id', payslip.employee_id.id)
                values.setdefault('version_id', payslip.version_id.id if payslip.version_id else False)

            # Solo validar versión de contrato para líneas normales
            if not is_informativo and not values.get('version_id'):
                raise UserError(_('Debe asignar una versión de contrato para crear una línea de nómina.'))

            # Auto-generar código si no existe para informativas
            if is_informativo and not values.get('code'):
                info_type = values.get('info_type', 'otro')
                values['code'] = 'INFO_' + info_type.upper()

        return super().create(vals_list)


class HrPayslipEdiWorkedDays(models.Model):
    _name = 'hr.payslip.edi.worked_days'
    _description = 'Días Trabajados Nómina Electrónica'
    _order = 'payslip_id, sequence'

    payslip_id = fields.Many2one(
        'hr.payslip.edi', string='Nómina Electrónica',
        required=True, ondelete='cascade', index=True
    )
    work_entry_type_id = fields.Many2one(
        'hr.work.entry.type', string='Tipo',
        required=True
    )
    name = fields.Char(related='work_entry_type_id.name', string='Descripción')
    code = fields.Char(related='work_entry_type_id.code', string='Código')
    sequence = fields.Integer(string='Secuencia', default=10, index=True)

    number_of_days = fields.Float(string='Días')
    number_of_hours = fields.Float(string='Horas')
    amount = fields.Monetary(string='Monto', compute='_compute_amount', store=True)
    is_paid = fields.Boolean(string='Pagado', compute='_compute_is_paid', store=True)

    version_id = fields.Many2one(related='payslip_id.version_id', string='Versión Contrato')
    currency_id = fields.Many2one(related='payslip_id.currency_id')

    @api.depends('work_entry_type_id', 'payslip_id.struct_id')
    def _compute_is_paid(self):
        for wd in self:
            struct = wd.payslip_id.struct_id
            if struct and hasattr(struct, 'unpaid_work_entry_type_ids'):
                wd.is_paid = wd.work_entry_type_id.id not in struct.unpaid_work_entry_type_ids.ids
            else:
                wd.is_paid = True

    @api.depends('is_paid', 'number_of_hours', 'payslip_id.version_id')
    def _compute_amount(self):
        for wd in self:
            if not wd.version_id or not wd.is_paid:
                wd.amount = 0
                continue
            if hasattr(wd.payslip_id, 'wage_type') and wd.payslip_id.wage_type == 'hourly':
                wd.amount = wd.version_id.hourly_wage * wd.number_of_hours
            else:
                total_hours = sum(wd.payslip_id.worked_days_line_ids.mapped('number_of_hours')) or 1
                wd.amount = (wd.version_id.wage * wd.number_of_hours) / total_hours
