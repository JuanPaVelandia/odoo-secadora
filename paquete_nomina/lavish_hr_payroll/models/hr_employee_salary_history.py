# -*- coding: utf-8 -*-
"""
Historial de Salarios del Empleado
==================================
Modelo para registrar cambios salariales historicos de los empleados.
Extraido de res_config_settings.py para mejor organizacion.
"""

from odoo import api, fields, models, _
import logging

_logger = logging.getLogger(__name__)


class HrEmployeeSalaryHistory(models.Model):
    _name = 'hr.employee.salary.history'
    _description = 'Historial de Salarios del Empleado'
    _order = 'date desc, id desc'

    name = fields.Char(
        string='Referencia',
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
        help="Contrato asociado"
    )

    date = fields.Date(
        string='Fecha',
        required=True,
        index=True,
        help="Fecha efectiva de este salario"
    )

    wage = fields.Float(
        string='Salario',
        digits='Payroll',
        required=True,
        help="Valor del salario basico"
    )

    old_wage = fields.Float(
        string='Salario anterior',
        digits='Payroll',
        help="Valor del salario antes del cambio"
    )

    worked_days = fields.Integer(
        string='Dias trabajados',
        help="Dias efectivamente trabajados con este salario"
    )

    unpaid_absences = fields.Integer(
        string='Ausencias no pagadas',
        help="Dias de ausencias no remuneradas durante este periodo"
    )

    reason = fields.Char(
        string='Motivo',
        help="Razon del cambio salarial"
    )

    reason_id = fields.Many2one(
        'hr.salary.change.reason',
        string='Motivo de cambio',
        help="Razon catalogada del cambio salarial"
    )

    change_type = fields.Selection([
        ('increase', 'Aumento'),
        ('decrease', 'Disminucion'),
        ('initial', 'Inicial')
    ], string='Tipo de cambio',
       compute='_compute_change_type',
       store=True,
       help="Indica si fue un aumento o disminucion"
    )

    percentage_change = fields.Float(
        string='% Cambio',
        digits=(5, 2),
        compute='_compute_change_type',
        store=True,
        help="Porcentaje de cambio respecto al salario anterior"
    )

    payslip_id = fields.Many2one(
        'hr.payslip',
        string='Nomina',
        ondelete='set null',
        help="Nomina relacionada con este registro"
    )

    document_number = fields.Char(
        string='# Documento',
        help="Numero de documento que respalda el cambio"
    )

    change_user_id = fields.Many2one(
        'res.users',
        string='Usuario',
        default=lambda self: self.env.user.id,
        help="Usuario que realizo el cambio"
    )

    company_id = fields.Many2one(
        'res.company',
        string='Compania',
        required=True,
        default=lambda self: self.env.company
    )

    active = fields.Boolean(
        string='Activo',
        default=True,
        help="Permite archivar registros historicos muy antiguos"
    )

    @api.depends('employee_id', 'date', 'wage')
    def _compute_display_name(self):
        """Genera un nombre descriptivo para el registro"""
        for record in self:
            if record.employee_id and record.date:
                record.name = f"{record.employee_id.name} - {record.date.strftime('%Y-%m-%d')} - {record.wage:,.0f}"
            else:
                record.name = "Cambio Salarial"

    @api.depends('wage', 'old_wage')
    def _compute_change_type(self):
        """Determina si fue aumento o disminucion y calcula el porcentaje"""
        for record in self:
            if not record.old_wage or record.old_wage == 0:
                record.change_type = 'initial'
                record.percentage_change = 0
            elif record.wage > record.old_wage:
                record.change_type = 'increase'
                record.percentage_change = ((record.wage / record.old_wage) - 1) * 100
            elif record.wage < record.old_wage:
                record.change_type = 'decrease'
                record.percentage_change = ((record.old_wage / record.wage) - 1) * -100
            else:
                record.change_type = 'initial'
                record.percentage_change = 0

    @api.model
    def create_from_salary_change(self, contract_id, date, wage, old_wage=0.0, reason=False, reason_id=False, document_number=False):
        """Crea un registro historico de cambio salarial"""
        if not contract_id or not date or not wage:
            return False

        contract = self.env['hr.contract'].browse(contract_id)
        if not contract or not contract.employee_id:
            return False

        values = {
            'employee_id': contract.employee_id.id,
            'contract_id': contract.id,
            'date': date,
            'wage': wage,
            'old_wage': old_wage,
            'reason': reason or 'Cambio salarial',
            'reason_id': reason_id,
            'document_number': document_number,
            'company_id': contract.company_id.id
        }

        return self.create(values)

    @api.model
    def update_worked_days(self, employee_id, date_from, date_to, worked_days, unpaid_absences=0):
        """Actualiza los dias trabajados para el registro salarial vigente"""
        if not employee_id or not date_from or not date_to:
            return False
        salary_record = self.search([
            ('employee_id', '=', employee_id),
            ('date', '<=', date_to)
        ], order='date desc', limit=1)

        if salary_record:
            salary_record.write({
                'worked_days': worked_days,
                'unpaid_absences': unpaid_absences
            })
            return salary_record
        return False


class HrSalaryChangeReason(models.Model):
    """Catalogo de motivos de cambio salarial"""
    _name = 'hr.salary.change.reason'
    _description = 'Motivo de Cambio Salarial'
    _order = 'sequence, name'

    name = fields.Char(string='Nombre', required=True)
    code = fields.Char(string='Codigo')
    sequence = fields.Integer(string='Secuencia', default=10)
    active = fields.Boolean(string='Activo', default=True)
    description = fields.Text(string='Descripcion')
