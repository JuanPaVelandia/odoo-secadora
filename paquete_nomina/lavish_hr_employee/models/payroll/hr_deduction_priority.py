# -*- coding: utf-8 -*-
"""
PRIORIDAD DE DEDUCCIONES
========================

Modelo para configurar el orden y prioridad de las deducciones
cuando se aplica el límite del 50% de devengos (Art. 149 CST).

Las deducciones obligatorias (salud, pensión, retención) siempre
se descuentan primero, independientemente de la secuencia.
"""

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class HrDeductionPriority(models.Model):
    """Configuración de prioridad de deducciones para límite 50%"""
    
    _name = 'hr.deduction.priority'
    _description = 'Prioridad de Deducciones'
    _order = 'sequence, id'
    _rec_name = 'display_name'

    # =========================================================================
    # CAMPOS PRINCIPALES
    # =========================================================================

    sequence = fields.Integer(
        string='Secuencia',
        default=100,
        help='Orden de prioridad para descontar. Menor número = mayor prioridad.'
    )

    name = fields.Char(
        string='Nombre',
        required=True,
        help='Nombre descriptivo de la configuración'
    )

    salary_rule_id = fields.Many2one(
        'hr.salary.rule',
        string='Regla Salarial',
        domain="[('category_id.code', 'in', ['DED', 'DEDUCCIONES', 'SSOCIAL', 'RETENCION'])]",
        help='Regla salarial de deducción específica'
    )

    category_id = fields.Many2one(
        'hr.salary.rule.category',
        string='Categoría',
        domain="[('code', 'in', ['DED', 'DEDUCCIONES', 'SSOCIAL', 'RETENCION'])]",
        help='Categoría de deducciones (aplica a todas las reglas de la categoría)'
    )

    rule_code = fields.Char(
        string='Código de Regla',
        help='Código de regla salarial (alternativo a seleccionar regla)'
    )

    is_mandatory = fields.Boolean(
        string='Obligatoria',
        default=False,
        help='''Deducción obligatoria que SIEMPRE se descuenta.
        
Las deducciones obligatorias no aplican al límite del 50%:
- Seguridad Social (Salud, Pensión)
- Retención en la Fuente
- Aportes parafiscales

Estas se descuentan primero, luego las limitables.'''
    )

    is_active = fields.Boolean(
        string='Activo',
        default=True
    )

    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        default=lambda self: self.env.company,
        help='Compañía (vacío = aplica a todas)'
    )

    notes = fields.Text(
        string='Notas',
        help='Observaciones sobre esta configuración'
    )

    # =========================================================================
    # CAMPOS COMPUTADOS
    # =========================================================================

    display_name = fields.Char(
        compute='_compute_display_name',
        store=True
    )

    priority_type = fields.Selection([
        ('rule', 'Regla Específica'),
        ('category', 'Categoría'),
        ('code', 'Código'),
    ], string='Tipo', compute='_compute_priority_type', store=True)

    @api.depends('name', 'sequence', 'is_mandatory')
    def _compute_display_name(self):
        for record in self:
            mandatory = ' [OBLIGATORIA]' if record.is_mandatory else ''
            record.display_name = f"[{record.sequence}] {record.name}{mandatory}"

    @api.depends('salary_rule_id', 'category_id', 'rule_code')
    def _compute_priority_type(self):
        for record in self:
            if record.salary_rule_id:
                record.priority_type = 'rule'
            elif record.category_id:
                record.priority_type = 'category'
            elif record.rule_code:
                record.priority_type = 'code'
            else:
                record.priority_type = False

    # =========================================================================
    # ONCHANGE
    # =========================================================================

    @api.onchange('salary_rule_id')
    def _onchange_salary_rule_id(self):
        """Auto-completar campos cuando se selecciona una regla salarial"""
        if self.salary_rule_id:
            # Auto-completar nombre si está vacío
            if not self.name:
                self.name = self.salary_rule_id.name

            # Auto-completar código
            self.rule_code = self.salary_rule_id.code

            # Auto-completar categoría
            if self.salary_rule_id.category_id:
                self.category_id = self.salary_rule_id.category_id

            # Auto-detectar si es obligatoria (SSOCIAL o RETENCION)
            if self.salary_rule_id.category_id:
                Category = self.env['hr.salary.rule.category']

                # Buscar categorías obligatorias
                ssocial_cat = Category.search([('code', '=', 'SSOCIAL')], limit=1)
                retencion_cat = Category.search([('code', '=', 'RETENCION')], limit=1)

                mandatory_cat_ids = set()
                if ssocial_cat:
                    mandatory_cat_ids.update(Category.search([('id', 'child_of', ssocial_cat.id)]).ids)
                if retencion_cat:
                    mandatory_cat_ids.update(Category.search([('id', 'child_of', retencion_cat.id)]).ids)

                # Verificar si la categoría de la regla es obligatoria
                self.is_mandatory = self.salary_rule_id.category_id.id in mandatory_cat_ids

    @api.onchange('category_id')
    def _onchange_category_id(self):
        """Auto-detectar si categoría es obligatoria"""
        if self.category_id:
            Category = self.env['hr.salary.rule.category']

            # Buscar categorías obligatorias
            ssocial_cat = Category.search([('code', '=', 'SSOCIAL')], limit=1)
            retencion_cat = Category.search([('code', '=', 'RETENCION')], limit=1)

            mandatory_cat_ids = set()
            if ssocial_cat:
                mandatory_cat_ids.update(Category.search([('id', 'child_of', ssocial_cat.id)]).ids)
            if retencion_cat:
                mandatory_cat_ids.update(Category.search([('id', 'child_of', retencion_cat.id)]).ids)

            # Verificar si la categoría es obligatoria
            self.is_mandatory = self.category_id.id in mandatory_cat_ids

    # =========================================================================
    # VALIDACIONES
    # =========================================================================

    @api.constrains('salary_rule_id', 'category_id', 'rule_code')
    def _check_at_least_one(self):
        for record in self:
            if not record.salary_rule_id and not record.category_id and not record.rule_code:
                raise ValidationError(
                    _('Debe especificar al menos una Regla Salarial, Categoría o Código.')
                )

    @api.constrains('sequence')
    def _check_sequence(self):
        for record in self:
            if record.sequence < 1:
                raise ValidationError(_('La secuencia debe ser mayor a 0.'))

    # =========================================================================
    # MÉTODOS DE CONSULTA
    # =========================================================================

    @api.model
    def get_priority_for_rule(self, rule_code, category_code=None, company_id=None):
        """
        Obtiene la prioridad configurada para una regla.
        
        Args:
            rule_code: Código de la regla salarial
            category_code: Código de la categoría (opcional)
            company_id: ID de la compañía (opcional)
            
        Returns:
            dict: {
                'sequence': int,
                'is_mandatory': bool,
                'found': bool,
            }
        """
        domain = [('is_active', '=', True)]
        
        if company_id:
            domain.append('|')
            domain.append(('company_id', '=', False))
            domain.append(('company_id', '=', company_id))
        
        # Buscar por regla específica primero
        priority = self.search(domain + [
            '|',
            ('rule_code', '=', rule_code),
            ('salary_rule_id.code', '=', rule_code)
        ], limit=1, order='sequence')
        
        if priority:
            return {
                'sequence': priority.sequence,
                'is_mandatory': priority.is_mandatory,
                'found': True,
                'name': priority.name,
            }
        
        # Buscar por categoría
        if category_code:
            priority = self.search(domain + [
                ('category_id.code', '=', category_code)
            ], limit=1, order='sequence')
            
            if priority:
                return {
                    'sequence': priority.sequence,
                    'is_mandatory': priority.is_mandatory,
                    'found': True,
                    'name': priority.name,
                }
        
        # No encontrado - usar valores por defecto
        return {
            'sequence': 999,
            'is_mandatory': False,
            'found': False,
            'name': None,
        }

    @api.model
    def get_all_priorities(self, company_id=None):
        """
        Obtiene todas las prioridades configuradas.
        
        Returns:
            tree: Lista ordenada de prioridades
        """
        domain = [('is_active', '=', True)]
        
        if company_id:
            domain.append('|')
            domain.append(('company_id', '=', False))
            domain.append(('company_id', '=', company_id))
        
        priorities = self.search(domain, order='sequence')
        
        return [{
            'id': p.id,
            'sequence': p.sequence,
            'name': p.name,
            'rule_code': p.rule_code or (p.salary_rule_id.code if p.salary_rule_id else None),
            'category_code': p.category_id.code if p.category_id else None,
            'is_mandatory': p.is_mandatory,
            'priority_type': p.priority_type,
        } for p in priorities]

    @api.model
    def get_mandatory_categories(self, company_id=None):
        """
        Obtiene lista de códigos de reglas/categorías obligatorias.
        
        Returns:
            set: Conjunto de códigos obligatorios
        """
        domain = [('is_active', '=', True), ('is_mandatory', '=', True)]
        
        if company_id:
            domain.append('|')
            domain.append(('company_id', '=', False))
            domain.append(('company_id', '=', company_id))
        
        priorities = self.search(domain)
        
        codes = set()
        for p in priorities:
            if p.rule_code:
                codes.add(p.rule_code)
            if p.salary_rule_id:
                codes.add(p.salary_rule_id.code)
            if p.category_id:
                codes.add(p.category_id.code)
        
        return codes

    # =========================================================================
    # DATOS POR DEFECTO
    # =========================================================================

    @api.model
    def create_default_priorities(self):
        """
        Crea las prioridades por defecto para deducciones colombianas.
        
        Lee las reglas de deduccion existentes y crea prioridades
        basadas en su secuencia y categoria.
        
        Usa child_of para incluir subcategorias de deducciones.
        
        Secuencias:
        - 201-209: Obligatorias (SSOCIAL, RETENCION)
        - 210+: Limitables (otras deducciones)
        """
        SalaryRule = self.env['hr.salary.rule']
        Category = self.env['hr.salary.rule.category']
        
        # Buscar categorias padre de deducciones
        parent_categories = Category.search([
            ('code', 'in', ['DED', 'DEDUCCIONES', 'SSOCIAL', 'RETENCION'])
        ])
        
        if not parent_categories:
            return []
        
        # Buscar reglas de deduccion usando child_of para incluir subcategorias
        deduction_rules = SalaryRule.search([
            ('category_id', 'child_of', parent_categories.ids),
            ('active', '=', True),
        ], order='sequence')
        
        created = []
        
        # Categorias obligatorias (incluyendo hijos)
        ssocial_cat = Category.search([('code', '=', 'SSOCIAL')], limit=1)
        retencion_cat = Category.search([('code', '=', 'RETENCION')], limit=1)
        
        mandatory_cat_ids = set()
        if ssocial_cat:
            mandatory_cat_ids.update(Category.search([('id', 'child_of', ssocial_cat.id)]).ids)
        if retencion_cat:
            mandatory_cat_ids.update(Category.search([('id', 'child_of', retencion_cat.id)]).ids)
        
        for rule in deduction_rules:
            # Verificar si ya existe
            existing = self.search([
                '|',
                ('rule_code', '=', rule.code),
                ('salary_rule_id', '=', rule.id),
            ], limit=1)
            
            if existing:
                continue
            
            # Determinar si es obligatoria (categoria o subcategoria de SSOCIAL/RETENCION)
            is_mandatory = rule.category_id.id in mandatory_cat_ids if rule.category_id else False
            
            # Crear prioridad
            record = self.create({
                'sequence': rule.sequence or 250,
                'name': rule.name,
                'salary_rule_id': rule.id,
                'rule_code': rule.code,
                'is_mandatory': is_mandatory,
                'notes': f'Creado automaticamente desde regla {rule.code}',
            })
            created.append(record.name)
        
        return created
