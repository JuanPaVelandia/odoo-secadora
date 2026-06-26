from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from dateutil.relativedelta import relativedelta

class HrAccumulatedPayroll(models.Model):
    _name = 'hr.accumulated.payroll'
    _description = 'Acumulados de nómina'

    employee_id = fields.Many2one('hr.employee', string='Empleado')
    employee_identification = fields.Char('Identificación empleado')
    salary_rule_id = fields.Many2one('hr.salary.rule',string='Regla salarial', required=True)
    date = fields.Date('Fecha', required=True)
    amount = fields.Float(string='Valor')
    contract_id = fields.Many2one('hr.contract', string='Contrato')
    origin_payslip_id = fields.Many2one('hr.payslip', string='Nómina de origen')
    origin_payslip_line_id = fields.Many2one('hr.payslip.line', string='Línea de nómina origen', help='Línea específica que generó este acumulado')
    note = fields.Text('Nota')

    # Campos para clasificación y trazabilidad del acumulado
    accumulated_type = fields.Selection([
        ('auto', 'Automático'),
        ('inception', 'Carga Inicial'),
        ('novelty', 'Novedad'),
        ('absence', 'Ausencia'),
        ('adjustment', 'Ajuste Manual'),
    ], string='Tipo de Acumulado', default='auto', required=True,
       help='Tipo de registro: Automático (generado por nómina), Carga Inicial (migración de datos), '
            'Novedad (horas extras, bonos), Ausencia (licencias, incapacidades), Ajuste Manual')

    # Campos para novedades y ausencias
    quantity = fields.Float(string='Cantidad', help='Cantidad de horas, días, etc.')
    date_from = fields.Date(string='Fecha Inicio', help='Fecha de inicio de la novedad o ausencia')
    date_to = fields.Date(string='Fecha Fin', help='Fecha de fin de la novedad o ausencia')

    # Información de origen del cálculo
    source_rule_ids = fields.Many2many(
        'hr.salary.rule',
        'hr_accumulated_source_rule_rel',
        'accumulated_id',
        'rule_id',
        string='Reglas de Origen',
        help='Reglas salariales que se utilizaron para calcular este acumulado'
    )

    # Campos para guardar líneas relacionadas (histórico para ajustes)
    accounting_line_ids = fields.Many2many(
        'account.move.line',
        'hr_accumulated_accounting_rel',
        'accumulated_id',
        'accounting_line_id',
        string='Líneas Contables Relacionadas',
        help='Líneas contables consideradas en el cálculo de este acumulado'
    )
    payslip_line_ids = fields.Many2many(
        'hr.payslip.line',
        'hr_accumulated_payslip_line_rel',
        'accumulated_id',
        'payslip_line_id',
        string='Líneas de Nómina Relacionadas',
        help='Líneas de nóminas anteriores consideradas en el cálculo de este acumulado'
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('employee_identification'):
                obj_employee = self.env['hr.employee'].search(
                    [('identification_id', '=', vals.get('employee_identification'))],
                    limit=1
                )
                if obj_employee:
                    vals['employee_id'] = obj_employee.id
            
            if vals.get('employee_id'):
                obj_employee = self.env['hr.employee'].search(
                    [('id', '=', vals.get('employee_id'))],
                    limit=1
                )
                if obj_employee:
                    vals['employee_identification'] = obj_employee.identification_id

        return super().create(vals_list)              