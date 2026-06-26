from odoo import models, fields, api, _
from datetime import datetime, timedelta, date
from dateutil.relativedelta import relativedelta
import calendar
from odoo.exceptions import UserError, ValidationError
import time
from odoo.tools.safe_eval import safe_eval
import json
from odoo.tools.float_utils import float_round
import logging
_logger = logging.getLogger(__name__)
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from collections import defaultdict
from odoo.tools import format_date, formatLang, frozendict, date_utils,format_amount


class AccountAccount(models.Model):
    _inherit = 'account.account'
    
    payroll_concept = fields.Boolean(string='Aplica Concepto de nómina', default=False, help='Indica si esta cuenta se puede usar en los conceptos, para evitar mostrar todo el plan de cuenta')

# NOTA: Tipos de empleado ahora usan el campo nativo employee_type de Odoo
# Valores disponibles: employee, student, trainee, contractor, freelance
# Para filtrar reglas salariales por tipo, usar el campo employee_type_domain en hr.salary.rule
# Ejemplo de uso en regla: employee_type_domain = "employee,contractor"

#Tabla de riesgos profesionales
class HrContractRisk(models.Model):
    _name = 'hr.contract.risk'
    _description = 'Riesgos profesionales'

    code = fields.Char('Codigo', size=10, required=True)
    name = fields.Char('Nombre', size=100, required=True)
    percent = fields.Float('Porcentaje', digits=(12,3), required=True, help='porcentaje del riesgo profesional')
    date = fields.Date('Fecha vigencia')

    _change_code_uniq = models.Constraint('unique(code)', 'Ya existe un riesgo con este código, por favor verificar')

class LavishEconomicActivityLevelRisk(models.Model):
    _name = 'lavish.economic.activity.level.risk'
    _description = 'Actividad económica por nivel de riesgo'

    risk_class_id = fields.Many2one('hr.contract.risk','Clase de riesgo', required=True)
    code_ciiu_id = fields.Many2one('lavish.ciiu','CIIU', required=True)
    code = fields.Char('Código', required=True)
    name = fields.Char('Descripción', required=True)

    _economic_activity_level_risk_uniq = models.Constraint('unique(risk_class_id,code_ciiu_id,code)', 'Ya existe un riesgo con este código, por favor verificar')

    @api.depends(
        'risk_class_id',
        'risk_class_id.code',
        'code_ciiu_id',
        'code_ciiu_id.code',
        'code_ciiu_id.name',
        'code'
    )
    def _compute_display_name(self):
        for record in self:
            risk_code = record.risk_class_id.code if record.risk_class_id else ''
            ciiu_code = record.code_ciiu_id.code if record.code_ciiu_id else ''
            ciiu_name = record.code_ciiu_id.name if record.code_ciiu_id else ''
            record.display_name = "{}{}{} | {}".format(
                risk_code,
                ciiu_code,
                record.code or '',
                ciiu_name
            )

#Tabla tipos de entidades
class HrContribRegister(models.Model):
    _name = 'hr.contribution.register'
    _description = 'Tipo de Entidades'
    
    name = fields.Char('Nombre', required=True)
    type_entities = fields.Selection([('none', 'No aplica'),
                             ('eps', 'Entidad promotora de salud'),
                             ('pension', 'Fondo de pensiones'),
                             ('cesantias', 'Fondo de cesantias'),
                             ('caja', 'Caja de compensación'),
                             ('riesgo', 'Aseguradora de riesgos profesionales'),
                             ('sena', 'SENA'),
                             ('icbf', 'ICBF'),
                             ('solidaridad', 'Fondo de solidaridad'),
                             ('subsistencia', 'Fondo de subsistencia')], 'Tipo', required=True)
    note = fields.Text('Description')

    _change_name_uniq = models.Constraint('unique(name)', 'Ya existe un tipo de entidad con este nombre, por favor verificar')

#Tabla de entidades
class HrEmployeeEntities(models.Model):
    _name = 'hr.employee.entities'
    _description = 'Entidades empleados'

    partner_id = fields.Many2one('res.partner', 'Entidad', help='Entidad relacionada')
    name = fields.Char(related="partner_id.name", readonly=True,string="Nombre")
    business_name = fields.Char(related="partner_id.business_name", readonly=True,string="Nombre de negocio")
    types_entities = fields.Many2many('hr.contribution.register',
                                      'hr_employee_entities_hr_contribution_register_rel',
                                      'hr_employee_entities_id', 'hr_contribution_register_id',
                                      string='Tipo de entidad')
    code_pila_eps = fields.Char('Código PILA')
    code_pila_ccf = fields.Char('Código PILA para CCF')
    code_pila_regimen = fields.Char('Código PILA Regimen de excepción')
    code_pila_exterior = fields.Char('Código PILA Reside en el exterior')
    order = fields.Selection([('territorial', 'Orden Terrritorial'),
                             ('nacional', 'Orden Nacional')], 'Orden de la entidad')
    debit_account = fields.Many2one('account.account', string='Cuenta débito', company_dependent=True)
    credit_account = fields.Many2one('account.account', string='Cuenta crédito', company_dependent=True)
    _change_partner_uniq = models.Constraint('unique(partner_id)', 'Ya existe una entidad asociada a este tercero, por favor verificar')

    @api.depends('partner_id', 'partner_id.business_name', 'partner_id.name')
    def _compute_display_name(self):
        for record in self:
            business_name = record.partner_id.business_name if record.partner_id else ''
            if business_name:
                record.display_name = "{}".format(business_name)
            else:
                partner_name = record.partner_id.name if record.partner_id else ''
                record.display_name = "{}".format(partner_name)

#Categorias reglas salariales herencia

class HrCategoriesSalaryRules(models.Model):
    _inherit = 'hr.salary.rule.category'
    _description = 'Categorías de Reglas Salariales'
    _order = 'sequence, id'

    group_payroll_voucher = fields.Boolean(
        string='Agrupar comprobante de nómina',
        help='Si está marcado, las reglas salariales de esta categoría se agruparán en el comprobante de nómina'
    )
    sequence = fields.Integer(
        help='Secuencia para determinar el orden de las categorías'
    )
    active = fields.Boolean(
        string='Activo',
        default=True,
        help='Si está desmarcado, esta categoría se ocultará pero no se eliminará'
    )
    category_type = fields.Selection([
       ('basic', 'Salario Básico'),
       ('earnings', 'Devengos Salariales'),
       ('earnings_non_salary', 'Devengos No Salariales'),
       ('o_rights', 'Otros Derechos'),
       ('benefits', 'Prestaciones Sociales'),
       ('additional', 'Complementarios'),
       ('non_taxed_earnings', 'Ingresos No Gravados'),
       ('deductions', 'Deducciones'),
       ('contributions', 'Aportes'),
       ('provisions', 'Provisiones'),
       ('totals', 'Totales'),
       ('other', 'Otros')
    ], string='Tipo de Categoría', help='Tipo funcional de la categoría para cálculos automatizados')
   
    def toggle_active(self):
        for record in self:
            record.active = not record.active
            
#Contabilización reglas salariales
class HrSalaryRuleAccounting(models.Model):
    _name ='hr.salary.rule.accounting'
    _description = 'Contabilización reglas salariales'    

    salary_rule = fields.Many2one('hr.salary.rule', string = 'Regla salarial')
    department = fields.Many2one('hr.department', string = 'Departamento')
    company = fields.Many2one('res.company', string = 'Compañía')
    work_location = fields.Many2one('res.partner', string = 'Ubicación de trabajo')
    third_debit = fields.Selection([('entidad', 'Entidad'),
                                    ('compañia', 'Compañia'),
                                    ('empleado', 'Empleado')], string='Tercero débito') 
    third_credit = fields.Selection([('entidad', 'Entidad'),
                                    ('compañia', 'Compañia'),
                                    ('empleado', 'Empleado')], string='Tercero crédito')
    debit_account = fields.Many2one('account.account', string = 'Cuenta débito', company_dependent=True)
    credit_account = fields.Many2one('account.account', string = 'Cuenta crédito', company_dependent=True)

#Estructura Salariales - Herencia
class HrPayrollStructure(models.Model):
    _inherit = 'hr.payroll.structure'

    @api.model
    def _get_default_rule_ids(self):
        default_rules = []
        if self.country_id.code == 'CO':
            if self.process == 'prima':
                # Añade las reglas para 'primas'
                default_rules.append((0, 0, {
                    # Detalles de la regla para 'primas'
                }))
            elif self.process == 'vacaciones':
                # Añade las reglas para 'nomina base'
                default_rules.append((0, 0, {
                    # Detalles de la regla para 'nomina base'
                }))
            elif self.process == 'cesantias':
                # Añade la regla para 'cesantias'
                default_rules.append((0, 0, {
                    'name': _('Cesantias'),
                    'sequence': 1,
                    'code': 'CESANTIAS',
                    'category_id': self.env.ref('lavish_hr_employee.PRESTACIONES_SOCIALES').id,
                    'condition_select': 'python',
                    # Usar employee.employee_type (nativo Odoo) para validar tipo
                    # Ejemplo: result = payslip.get_salary_rule('CESANTIAS', employee.employee_type)
                    'condition_python': 'result = payslip.get_salary_rule(\'CESANTIAS\', employee.employee_type)',
                    'amount_select': 'code',
                    'amount_python_compute': """
                        result = 0.0
                        obj_salary_rule = result
                        if obj_salary_rule:
                            date_start = payslip.date_from
                            date_end = payslip.date_to
                            if inherit_contrato != 0:
                                date_start = payslip.date_cesantias
                                date_end = payslip.date_liquidacion
                            accumulated = payslip.get_accumulated_cesantias(date_start,date_end) + values_base_cesantias
                            result = accumulated""",
                }))
        return default_rules

    process = fields.Selection([('nomina', 'Nónima'),
                                ('vacaciones', 'Vacaciones'),
                                ('prima', 'Prima'),
                                ('cesantias', 'Cesantías'),
                                ('intereses_cesantias', 'Intereses de cesantías'),
                                ('contrato', 'Liq. de Contrato'),
                                ('consolidacion', 'Consolidación'),
                                ('otro', 'Otro')], string='Proceso')
    regular_pay = fields.Boolean('Pago standar')
    regular_31 = fields.Boolean('Pago Dia 31')
    rule_ids = fields.One2many(
        'hr.salary.rule', 'struct_id',
        string='Salary Rules', default=_get_default_rule_ids)

    @api.onchange('regular_pay')
    def onchange_regular_pay(self):
        for record in self:
            record.process = 'nomina' if record.regular_pay == True else False  
  
    @api.onchange('process')
    def _onchange_process(self):
        if not self._origin:
            self.rule_ids = self._get_default_rule_ids()

class HrWorkEntryType(models.Model):
    _name = 'hr.work.entry.type'
    _inherit = ['hr.work.entry.type','mail.thread', 'mail.activity.mixin']

    code = fields.Char(tracking=True)
    sequence = fields.Integer(tracking=True)
    round_days = fields.Selection(tracking=True)
    round_days_type = fields.Selection(tracking=True)
    is_leave = fields.Boolean(tracking=True)
    is_unforeseen = fields.Boolean(tracking=True)

