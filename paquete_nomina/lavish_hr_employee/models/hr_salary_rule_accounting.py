# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)

class HrSalaryRuleAccounting(models.Model):
    """Configuración contable para reglas salariales"""
    _name = 'hr.salary.rule.accounting'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Contabilización reglas salariales'
    _order = 'sequence, priority_type, id'
    _rec_name = 'display_name'
    
    # Campos principales
    salary_rule = fields.Many2one(
        'hr.salary.rule',
        string='Regla salarial',
        required=True,
        ondelete='cascade'
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Empleado'
    )
    
    department_id = fields.Many2one(
        'hr.department',
        string='Departamento'
    )
    
    job_id = fields.Many2one(
        'hr.job',
        string='Puesto de trabajo'
    )
    
    work_location_id = fields.Many2one(
        'res.partner',
        string='Ubicación de trabajo'
    )
    
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company
    )
    has_priority_flow = fields.Boolean(related='salary_rule.has_priority_flow'
    )
    priority_type = fields.Selection([
        ('employee', 'Por Empleado'),
        ('job', 'Por Puesto'),
        ('department', 'Por Departamento'),
        ('location', 'Por Ubicación'),
        ('company', 'Por Compañía'),
        ('default', 'Por Defecto')
    ], string='Tipo de Prioridad', default='default', required=True)
    
    sequence = fields.Integer(
        string='Secuencia',
        default=10
    )
    
    third_debit = fields.Selection([
        ('entidad', 'Entidad'),
        ('compania', 'Compañía'),
        ('empleado', 'Empleado')
    ], string='Tercero débito')
    
    third_credit = fields.Selection([
        ('entidad', 'Entidad'),
        ('compania', 'Compañía'),
        ('empleado', 'Empleado')
    ], string='Tercero crédito')
    
    debit_account_id = fields.Many2one(
        'account.account',
        string='Cuenta débito',
        domain="[('company_ids', '=', company_id)]"
    )
    
    credit_account_id = fields.Many2one(
        'account.account',
        string='Cuenta crédito',
        domain="[('company_ids', '=', company_id)]"
    )

    
    accounting_flow = fields.Char(
        string='Flujo Contable',
        compute='_compute_accounting_flow',
        store=False
    )
    
    active = fields.Boolean(
        string='Activo',
        default=True
    )
    
    @api.depends('salary_rule', 'employee_id', 'department_id', 'job_id')
    def _compute_display_name(self):
        for record in self:
            parts = [record.salary_rule.name or 'Sin Regla']
            
            if record.employee_id:
                parts.append(f"Emp: {record.employee_id.name}")
            elif record.job_id:
                parts.append(f"Puesto: {record.job_id.name}")
            elif record.department_id:
                parts.append(f"Depto: {record.department_id.name}")
            
            record.display_name = ' - '.join(parts)
    
    @api.depends('debit_account_id', 'credit_account_id', 'third_debit', 'third_credit')
    def _compute_accounting_flow(self):
        for record in self:
            flow = []
            
            if record.debit_account_id:
                third = dict(self._fields['third_debit'].selection).get(record.third_debit, '-') if record.third_debit else '-'
                flow.append(f"DB: {record.debit_account_id.code} ({third})")
            
            if record.credit_account_id:
                third = dict(self._fields['third_credit'].selection).get(record.third_credit, '-') if record.third_credit else '-'
                flow.append(f"CR: {record.credit_account_id.code} ({third})")
            
            record.accounting_flow = " → ".join(flow) if flow else "Sin configuración"


    # =====================================================
    # CAMPOS COMPUTADOS
    # =====================================================
    
    @api.depends('salary_rule.name', 'priority_type', 'employee_id', 'job_id', 'department_id')
    def _compute_name(self):
        """Genera un nombre descriptivo para la configuración"""
        for record in self:
            if not record.salary_rule:
                record.name = 'Configuración Contable'
                continue
                
            parts = [record.salary_rule.name]
            
            if record.employee_id:
                parts.append(f"- {record.employee_id.name}")
            elif record.job_id:
                parts.append(f"- {record.job_id.name}")
            elif record.department_id:
                parts.append(f"- {record.department_id.name}")
            elif record.priority_type != 'default':
                parts.append(f"- {dict(record._fields['priority_type'].selection).get(record.priority_type)}")
                
            record.name = ' '.join(parts)
    
    # =====================================================
    # VALIDACIONES
    # =====================================================
    
    @api.constrains('debit_account_id', 'credit_account_id')
    def _check_different_accounts(self):
        """Valida que las cuentas débito y crédito sean diferentes"""
        for record in self:
            if record.debit_account_id == record.credit_account_id:
                raise ValidationError(
                    _("Las cuentas débito y crédito deben ser diferentes")
                )
    
    @api.constrains('employee_id', 'job_id', 'department_id', 'priority_type')
    def _check_priority_consistency(self):
        """Valida consistencia entre tipo de prioridad y filtros"""
        for record in self:
            if record.priority_type == 'employee' and not record.employee_id:
                raise ValidationError(
                    _("Para prioridad 'Empleado' debe especificar un empleado")
                )
            elif record.priority_type == 'job' and not record.job_id:
                raise ValidationError(
                    _("Para prioridad 'Puesto' debe especificar un puesto de trabajo")
                )
            elif record.priority_type == 'department' and not record.department_id:
                raise ValidationError(
                    _("Para prioridad 'Departamento' debe especificar un departamento")
                )
    
    @api.constrains('salary_rule', 'employee_id', 'job_id', 'department_id', 'company_id')
    def _check_unique_configuration(self):
        """Evita duplicados de configuración para la misma combinación"""
        for record in self:
            domain = [
                ('id', '!=', record.id),
                ('salary_rule', '=', record.salary_rule.id),
                ('company_id', '=', record.company_id.id),
                ('employee_id', '=', record.employee_id.id if record.employee_id else False),
                ('job_id', '=', record.job_id.id if record.job_id else False),
                ('department_id', '=', record.department_id.id if record.department_id else False),
                ('work_location_id', '=', record.work_location_id.id if record.work_location_id else False),
            ]
            
            existing = self.search(domain, limit=1)
            if existing:
                raise ValidationError(
                    _("Ya existe una configuración contable para esta combinación de "
                      "regla salarial, empleado, puesto, departamento y ubicación")
                )
    
    # =====================================================
    # MÉTODOS DE BÚSQUEDA
    # =====================================================
    
    @api.model
    def get_accounting_data(self, salary_rule, employee, payslip_line=None):
        """
        Obtiene la configuración contable para una regla y empleado
        usando el sistema de prioridades si está habilitado
        """
        if not salary_rule or not employee:
            return {}
            
        # Si la regla tiene sistema de prioridades, usar búsqueda por prioridades
        if salary_rule.has_priority_flow:
            return self._get_accounting_with_priorities(salary_rule, employee, payslip_line)
        else:
            return self._get_traditional_accounting(salary_rule, employee, payslip_line)
    
    def _get_accounting_with_priorities(self, salary_rule, employee, payslip_line=None):
        """Búsqueda usando sistema de prioridades"""
        
        # Obtener configuraciones ordenadas por prioridad
        priority_configs = salary_rule.accounting_priority_ids.sorted('priority_sequence')
        
        for config in priority_configs:
            result = self._evaluate_priority_config(config, employee, payslip_line)
            if result:
                return result
        
        # Si no encuentra nada, buscar configuración por defecto
        return self._search_default_accounting(salary_rule, employee.company_id)
    
    def _get_traditional_accounting(self, salary_rule, employee, payslip_line=None):
        """Búsqueda tradicional con filtros"""
        
        accounting_records = salary_rule.salary_rule_accounting.filtered('active')
        
        for account_rule in accounting_records:
            if self._validate_filters(account_rule, employee, payslip_line):
                return {
                    'debit_account_id': account_rule.debit_account_id.id,
                    'credit_account_id': account_rule.credit_account_id.id,
                    'third_debit': account_rule.third_debit,
                    'third_credit': account_rule.third_credit,
                    'source': 'traditional'
                }
        
        return {}
    
    def _evaluate_priority_config(self, config, employee, payslip_line=None):
        """Evalúa una configuración de prioridad específica"""
        
        priority_type = config.priority_type
        
        if priority_type == 'employee':
            return self._search_employee_accounting(config.salary_rule, employee)
        elif priority_type == 'entity':
            return self._search_entity_accounting(payslip_line, employee)
        elif priority_type == 'job':
            return self._search_job_accounting(config.salary_rule, employee)
        elif priority_type == 'department':
            return self._search_department_accounting(config.salary_rule, employee)
        elif priority_type == 'company':
            return self._search_company_accounting(config.salary_rule, employee.company_id)
        elif priority_type == 'default':
            return self._search_default_accounting(config.salary_rule, employee.company_id)
        
        return {}
    
    def _search_employee_accounting(self, salary_rule, employee):
        """Buscar configuración específica por empleado"""
        config = self.search([
            ('salary_rule', '=', salary_rule.id),
            ('employee_id', '=', employee.id),
            ('active', '=', True)
        ], limit=1)
        
        if config:
            return {
                'debit_account_id': config.debit_account_id.id,
                'credit_account_id': config.credit_account_id.id,
                'third_debit': config.third_debit,
                'third_credit': config.third_credit,
                'source': 'employee'
            }
        return {}
    
    def _search_entity_accounting(self, payslip_line, employee):
        """Buscar usando cuentas de entidad (si existe entity_id en la línea)"""
        if not payslip_line or not hasattr(payslip_line, 'entity_id') or not payslip_line.entity_id:
            return {}
            
        entity = payslip_line.entity_id
        if entity.debit_account_id and entity.credit_account_id:
            return {
                'debit_account_id': entity.debit_account_id.id,
                'credit_account_id': entity.credit_account_id.id,
                'third_debit': 'entidad',
                'third_credit': 'entidad',
                'source': 'entity'
            }
        return {}
    
    def _search_job_accounting(self, salary_rule, employee):
        """Buscar configuración por puesto de trabajo"""
        if not employee.job_id:
            return {}
            
        config = self.search([
            ('salary_rule', '=', salary_rule.id),
            ('job_id', '=', employee.job_id.id),
            ('employee_id', '=', False),
            ('active', '=', True)
        ], limit=1)
        
        if config:
            return {
                'debit_account_id': config.debit_account_id.id,
                'credit_account_id': config.credit_account_id.id,
                'third_debit': config.third_debit,
                'third_credit': config.third_credit,
                'source': 'job'
            }
        return {}
    
    def _search_department_accounting(self, salary_rule, employee):
        """Buscar configuración por departamento"""
        if not employee.department_id:
            return {}
            
        config = self.search([
            ('salary_rule', '=', salary_rule.id),
            ('department_id', '=', employee.department_id.id),
            ('employee_id', '=', False),
            ('job_id', '=', False),
            ('active', '=', True)
        ], limit=1)
        
        if config:
            return {
                'debit_account_id': config.debit_account_id.id,
                'credit_account_id': config.credit_account_id.id,
                'third_debit': config.third_debit,
                'third_credit': config.third_credit,
                'source': 'department'
            }
        return {}
    
    def _search_company_accounting(self, salary_rule, company):
        """Buscar configuración por compañía"""
        config = self.search([
            ('salary_rule', '=', salary_rule.id),
            ('company_id', '=', company.id),
            ('employee_id', '=', False),
            ('job_id', '=', False),
            ('department_id', '=', False),
            ('active', '=', True)
        ], limit=1)
        
        if config:
            return {
                'debit_account_id': config.debit_account_id.id,
                'credit_account_id': config.credit_account_id.id,
                'third_debit': config.third_debit,
                'third_credit': config.third_credit,
                'source': 'company'
            }
        return {}
    
    def _search_default_accounting(self, salary_rule, company):
        """Buscar configuración por defecto"""
        config = self.search([
            ('salary_rule', '=', salary_rule.id),
            ('company_id', '=', company.id),
            ('employee_id', '=', False),
            ('job_id', '=', False),
            ('department_id', '=', False),
            ('work_location_id', '=', False),
            ('active', '=', True)
        ], limit=1)
        
        if config:
            return {
                'debit_account_id': config.debit_account_id.id,
                'credit_account_id': config.credit_account_id.id,
                'third_debit': config.third_debit,
                'third_credit': config.third_credit,
                'source': 'default'
            }
        return {}
    
    def _validate_filters(self, account_rule, employee, payslip_line=None):
        """Valida filtros tradicionales"""
        
        if account_rule.employee_id and account_rule.employee_id != employee:
            return False
        
        if account_rule.job_id and account_rule.job_id != employee.job_id:
            return False
        
        if account_rule.department_id and account_rule.department_id != employee.department_id:
            return False
        
        if account_rule.work_location_id and account_rule.work_location_id != employee.address_id:
            return False
        
        if account_rule.company_id != employee.company_id:
            return False
        
        return True

class HrSalaryRuleAccountingPriority(models.Model):
    """Configuración de prioridades para reglas salariales"""
    _name = 'hr.salary.rule.accounting.priority'
    _description = 'Prioridades de Contabilización'
    _order = 'salary_rule_id, priority_sequence'
    
    salary_rule_id = fields.Many2one(
        'hr.salary.rule',
        string='Regla Salarial',
        required=True,
        ondelete='cascade'
    )
    
    priority_type = fields.Selection([
        ('employee', 'Empleado'),
        ('entity', 'Entidad'),
        ('job', 'Puesto'),
        ('department', 'Departamento'),
        ('company', 'Compañía'),
        ('default', 'Por Defecto'),
        ('novelity', 'Novedades'),
        ('leave', 'Licencias'),
        ('novelity_contract', 'Novedad De Contracto'),
    ], string='Tipo de Prioridad', required=True)
    
    priority_sequence = fields.Integer(
        string='Orden',
        default=10,
        help='Menor número = Mayor prioridad'
    )
    
    active = fields.Boolean(
        string='Activo',
        default=True
    )
    
    description = fields.Char(
        string='Descripción',
        compute='_compute_description'
    )
    
    @api.depends('priority_type')
    def _compute_description(self):
        priority_labels = dict(self._fields['priority_type'].selection)
        for record in self:
            record.description = priority_labels.get(record.priority_type, '')