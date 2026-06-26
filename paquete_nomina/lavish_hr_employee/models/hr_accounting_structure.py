# -*- coding: utf-8 -*-
"""
Sistema Flexible de Construccion de Cuentas Contables para Nomina
=================================================================

Permite configurar diferentes patrones de construccion de codigos de cuenta
basados en elementos como Departamento, Regla Salarial, Ubicacion y Puesto.

NUEVO: Sistema de Secciones por Tipo de Liquidacion
---------------------------------------------------
Permite definir estructuras contables por seccion:
- TOTALDEV: Total Devengos
- TOTALDED: Total Deducciones
- NET: Neto a Pagar
- PROVISIONES: Provisiones (cesantias, vacaciones, prima)
- IBD_SS: IBC Seguridad Social
- REGLAS_NORMALES: Reglas individuales

Cada seccion puede tener su propio patron de construccion y orden de ejecucion.

Patrones soportados:
- dept_rule_job: DEPT + RULE + JOB
- dept_rule_loc_job: DEPT + RULE + LOC + JOB
- dept_loc_rule_job: DEPT + LOC + RULE + JOB
- loc_dept_rule: LOC + DEPT + RULE
- custom: Orden personalizado
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import re


# =============================================================================
# TIPOS DE SECCION DISPONIBLES
# =============================================================================
SECTION_TYPES = [
    ('totaldev', 'TOTALDEV - Total Devengos'),
    ('totalded', 'TOTALDED - Total Deducciones'),
    ('net', 'NET - Neto a Pagar'),
    ('provisiones', 'PROVISIONES - Provisiones'),
    ('ibd_ss', 'IBD_SS - IBC Seguridad Social'),
    ('reglas_normales', 'REGLAS - Reglas Normales'),
]

# Mapeo de secciones a categorias de reglas salariales
SECTION_CATEGORY_MAP = {
    'totaldev': ['TOTALDEV', 'GROSS'],
    'totalded': ['TOTALDED'],
    'net': ['NET', 'NETO'],
    'provisiones': ['PROVISIONES', 'PROV_CES', 'PROV_VAC', 'PROV_PRIMA', 'PROV_INT_CES'],
    'ibd_ss': ['IBD', 'IBC', 'IBC_R', 'SSOCIAL', 'SSOCIAL001', 'SSOCIAL002'],
    'reglas_normales': ['BASIC', 'AUX', 'DEV', 'DED', 'DEDUCCIONES', 'DEV_SALARIAL',
                        'DEV_NO_SALARIAL', 'HEYREC', 'COMISIONES', 'HED', 'HEN', 'REC'],
}


class HrAccountingStructureConfig(models.Model):
    """Configuracion de estructura de cuentas contables"""
    _name = 'hr.accounting.structure.config'
    _description = 'Configuracion de Estructura Contable'
    _rec_name = 'name'

    name = fields.Char(
        string='Nombre',
        required=True,
        default='Configuracion Principal'
    )

    company_id = fields.Many2one(
        'res.company',
        string='Compania',
        required=True,
        default=lambda self: self.env.company
    )

    active = fields.Boolean(default=True)

    is_default = fields.Boolean(
        string='Configuracion por Defecto',
        help='Si esta marcado, esta configuracion se usara por defecto para la compania'
    )

    # =========================================================================
    # MODO DE CONFIGURACION: Global vs Por Secciones
    # =========================================================================
    config_mode = fields.Selection([
        ('global', 'Configuracion Global'),
        ('sections', 'Configuracion por Secciones'),
    ], string='Modo de Configuracion',
       default='global',
       required=True,
       help='Global: Un solo patron para todas las reglas. '
            'Secciones: Patron diferente por tipo de regla (TOTALDEV, TOTALDED, etc.)'
    )

    # Secciones de estructura (solo cuando config_mode = 'sections')
    section_ids = fields.One2many(
        'hr.accounting.structure.section',
        'config_id',
        string='Secciones',
        help='Secciones de configuracion contable por tipo de regla'
    )

    # Contador de secciones activas
    section_count = fields.Integer(
        string='Secciones Activas',
        compute='_compute_section_count'
    )

    @api.depends('section_ids', 'section_ids.active')
    def _compute_section_count(self):
        for record in self:
            record.section_count = len(record.section_ids.filtered('active'))

    # Modo de construccion
    use_manual_mode = fields.Boolean(
        string='Modo Manual',
        default=False,
        help='Activar para definir un orden personalizado de elementos'
    )

    include_location = fields.Boolean(
        string='Incluir Ubicacion',
        default=False,
        help='Incluir codigo de ubicacion/sucursal en la construccion de cuenta'
    )

    include_job = fields.Boolean(
        string='Incluir Puesto',
        default=False,
        help='Incluir codigo de puesto en la construccion de cuenta'
    )

    structure_pattern = fields.Selection([
        ('direct', 'Busqueda Directa (Sin construccion)'),
        ('dept_rule', 'Departamento + Regla'),
        ('dept_rule_job', 'Departamento + Regla + Puesto'),
        ('dept_rule_loc', 'Departamento + Regla + Ubicacion'),
        ('dept_rule_loc_job', 'Departamento + Regla + Ubicacion + Puesto'),
        ('dept_loc_rule_job', 'Departamento + Ubicacion + Regla + Puesto'),
        ('loc_dept_rule', 'Ubicacion + Departamento + Regla'),
        ('rule_dept', 'Regla + Departamento'),
        ('custom', 'Personalizado'),
    ], string='Patron de Estructura',
       default='direct',
       required=True,
       help='Patron para construir el codigo de cuenta contable'
    )

    custom_order = fields.Char(
        string='Orden Personalizado',
        help='Orden de elementos separados por coma: DEPT,LOC,RULE,JOB. Ejemplo: LOC,DEPT,RULE'
    )

    # Configuracion de longitud de codigos
    dept_code_length = fields.Integer(
        string='Longitud Codigo Departamento',
        default=4,
        help='Longitud del codigo del departamento (2-6 digitos)'
    )

    rule_code_length = fields.Integer(
        string='Longitud Codigo Regla',
        default=4,
        help='Longitud del codigo de la regla salarial (2-6 caracteres)'
    )

    loc_code_length = fields.Integer(
        string='Longitud Codigo Ubicacion',
        default=2,
        help='Longitud del codigo de ubicacion (2-4 digitos)'
    )

    job_code_length = fields.Integer(
        string='Longitud Codigo Puesto',
        default=2,
        help='Longitud del codigo del puesto (2-4 digitos)'
    )

    # Opciones de busqueda
    use_wildcard_search = fields.Boolean(
        string='Busqueda con Comodin',
        default=True,
        help='Permitir busqueda parcial con % cuando no se encuentra cuenta exacta'
    )

    fallback_to_parent_dept = fields.Boolean(
        string='Buscar en Departamento Padre',
        default=True,
        help='Si no encuentra cuenta, buscar con departamento padre'
    )

    search_levels = fields.Integer(
        string='Niveles de Busqueda',
        default=3,
        help='Numero de intentos de busqueda (exacto, sin ultimo nivel, wildcard, etc.)'
    )

    # Separador (opcional)
    use_separator = fields.Boolean(
        string='Usar Separador',
        default=False
    )

    separator = fields.Char(
        string='Separador',
        default='',
        help='Caracter separador entre elementos (vacio para concatenar directamente)'
    )

    notes = fields.Text(string='Notas')

    @api.constrains('custom_order')
    def _check_custom_order(self):
        """Validar formato del orden personalizado"""
        valid_elements = {'DEPT', 'LOC', 'RULE', 'JOB'}
        for record in self:
            if record.structure_pattern == 'custom' and record.custom_order:
                elements = [e.strip().upper() for e in record.custom_order.split(',')]
                invalid = set(elements) - valid_elements
                if invalid:
                    raise ValidationError(
                        _('Elementos invalidos en orden personalizado: %s. '
                          'Elementos validos: DEPT, LOC, RULE, JOB') % ', '.join(invalid)
                    )

    @api.constrains('is_default')
    def _check_default_unique(self):
        """Solo puede haber una configuracion por defecto por compania"""
        for record in self:
            if record.is_default:
                existing = self.search([
                    ('id', '!=', record.id),
                    ('company_id', '=', record.company_id.id),
                    ('is_default', '=', True)
                ])
                if existing:
                    raise ValidationError(
                        _('Ya existe una configuracion por defecto para esta compania: %s')
                        % existing[0].name
                    )

    @api.onchange('config_mode')
    def _onchange_config_mode(self):
        """Crear secciones por defecto al cambiar a modo secciones"""
        if self.config_mode == 'sections' and not self.section_ids:
            # Las secciones se crearan al guardar
            pass

    def action_create_default_sections(self):
        """Crear secciones por defecto para esta configuracion"""
        self.ensure_one()
        if self.config_mode != 'sections':
            raise UserError(_('Debe seleccionar modo "Configuracion por Secciones" primero'))

        Section = self.env['hr.accounting.structure.section']
        existing_types = self.section_ids.mapped('section_type')

        for sequence, (section_type, label) in enumerate(SECTION_TYPES, start=10):
            if section_type not in existing_types:
                Section.create({
                    'config_id': self.id,
                    'section_type': section_type,
                    'name': label.split(' - ')[1] if ' - ' in label else label,
                    'sequence': sequence,
                    'active': True,
                    'structure_pattern': 'direct',  # Por defecto busqueda directa
                })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Secciones Creadas'),
                'message': _('Se han creado %d secciones por defecto') % (len(SECTION_TYPES) - len(existing_types)),
                'type': 'success',
                'sticky': False,
            }
        }

    def get_section_for_rule(self, salary_rule):
        """
        Obtener la seccion correspondiente a una regla salarial.

        Args:
            salary_rule: hr.salary.rule record

        Returns:
            hr.accounting.structure.section record o False
        """
        self.ensure_one()

        if self.config_mode != 'sections':
            return False

        # Obtener codigo de categoria de la regla
        rule_code = (salary_rule.code or '').upper()
        category_code = (salary_rule.category_id.code or '').upper() if salary_rule.category_id else ''

        # Buscar seccion que coincida (ordenadas por prioridad)
        for section in self.section_ids.filtered('active').sorted('sequence'):
            # Verificar exclusiones primero
            if section.rule_codes_exclude:
                exclude_codes = [c.strip().upper() for c in section.rule_codes_exclude.split(',')]
                if rule_code in exclude_codes:
                    continue

            # Verificar si la regla coincide con las categorias de la seccion
            section_categories = [c.upper() for c in SECTION_CATEGORY_MAP.get(section.section_type, [])]

            # Agregar categorias personalizadas
            if section.rule_category_codes:
                custom_categories = [c.strip().upper() for c in section.rule_category_codes.split(',')]
                section_categories = list(set(section_categories + custom_categories))

            # Verificar por codigo de regla
            if rule_code and rule_code in section_categories:
                return section

            # Verificar por codigo de categoria
            if category_code and category_code in section_categories:
                return section

            # Verificar categoria padre si existe
            if salary_rule.category_id and salary_rule.category_id.parent_id:
                parent_code = (salary_rule.category_id.parent_id.code or '').upper()
                if parent_code and parent_code in section_categories:
                    return section

        # Fallback a seccion de reglas normales
        normal_section = self.section_ids.filtered(
            lambda s: s.section_type == 'reglas_normales' and s.active
        )
        return normal_section[0] if normal_section else False

    def get_account_code_elements(self, employee, salary_rule):
        """
        Obtener los elementos para construir el codigo de cuenta.

        Args:
            employee: hr.employee record
            salary_rule: hr.salary.rule record

        Returns:
            dict con los elementos: dept, rule, loc, job
        """
        self.ensure_one()

        elements = {}

        # Codigo departamento
        dept = employee.department_id
        elements['DEPT'] = self._get_dept_code(dept)

        # Codigo regla salarial
        elements['RULE'] = self._get_rule_code(salary_rule)

        # Codigo ubicacion (work_location)
        elements['LOC'] = self._get_location_code(employee)

        # Codigo puesto
        elements['JOB'] = self._get_job_code(employee)

        return elements

    def _get_dept_code(self, department):
        """Obtener codigo del departamento"""
        if not department:
            return ''

        # Primero intentar campo personalizado code_account
        if hasattr(department, 'code_account') and department.code_account:
            code = department.code_account
        # Luego intentar campo code estandar
        elif hasattr(department, 'code') and department.code:
            code = department.code
        else:
            # Usar ID formateado como fallback
            code = str(department.id).zfill(self.dept_code_length)

        return code[:self.dept_code_length].ljust(self.dept_code_length, '0')

    def _get_rule_code(self, salary_rule):
        """Obtener codigo de la regla salarial"""
        if not salary_rule:
            return ''

        code = salary_rule.code or ''
        return code[:self.rule_code_length].ljust(self.rule_code_length, ' ')

    def _get_location_code(self, employee):
        """Obtener codigo de ubicacion de trabajo"""
        if not self.include_location:
            return ''

        location = employee.address_id
        if not location:
            return ''

        # Intentar campo location_code personalizado
        if hasattr(location, 'location_code') and location.location_code:
            code = location.location_code
        else:
            # Usar ultimos digitos del ID
            code = str(location.id % 100).zfill(self.loc_code_length)

        return code[:self.loc_code_length].zfill(self.loc_code_length)

    def _get_job_code(self, employee):
        """Obtener codigo del puesto"""
        if not self.include_job:
            return ''

        job = employee.job_id
        if not job:
            return ''

        # Intentar campo code_account o code personalizado
        if hasattr(job, 'code_account') and job.code_account:
            code = job.code_account
        elif hasattr(job, 'code') and job.code:
            code = job.code
        else:
            code = str(job.id % 100).zfill(self.job_code_length)

        return code[:self.job_code_length].zfill(self.job_code_length)

    def build_account_code(self, employee, salary_rule):
        """
        Construir el codigo de cuenta segun el patron configurado.

        Args:
            employee: hr.employee record
            salary_rule: hr.salary.rule record

        Returns:
            str: Codigo de cuenta construido
        """
        self.ensure_one()

        if self.structure_pattern == 'direct':
            return None  # No construir, usar busqueda directa

        elements = self.get_account_code_elements(employee, salary_rule)
        sep = self.separator if self.use_separator else ''

        # Obtener orden de elementos segun patron
        if self.structure_pattern == 'custom':
            order = [e.strip().upper() for e in (self.custom_order or 'DEPT,RULE').split(',')]
        else:
            order = self._get_pattern_order()

        # Construir codigo
        parts = []
        for element in order:
            value = elements.get(element, '')
            if value:
                parts.append(value)

        return sep.join(parts)

    def _get_pattern_order(self):
        """Obtener orden de elementos segun patron seleccionado"""
        patterns = {
            'dept_rule': ['DEPT', 'RULE'],
            'dept_rule_job': ['DEPT', 'RULE', 'JOB'],
            'dept_rule_loc': ['DEPT', 'RULE', 'LOC'],
            'dept_rule_loc_job': ['DEPT', 'RULE', 'LOC', 'JOB'],
            'dept_loc_rule_job': ['DEPT', 'LOC', 'RULE', 'JOB'],
            'loc_dept_rule': ['LOC', 'DEPT', 'RULE'],
            'rule_dept': ['RULE', 'DEPT'],
        }
        return patterns.get(self.structure_pattern, ['DEPT', 'RULE'])

    def find_account(self, employee, salary_rule, account_type='debit'):
        """
        Buscar cuenta contable usando el patron configurado.

        Args:
            employee: hr.employee record
            salary_rule: hr.salary.rule record
            account_type: 'debit' o 'credit'

        Returns:
            account.account record o False
        """
        self.ensure_one()

        Account = self.env['account.account']
        company = employee.company_id

        # MODO SECCIONES: Delegar a la seccion correspondiente
        if self.config_mode == 'sections':
            section = self.get_section_for_rule(salary_rule)
            if section:
                return section.find_account(employee, salary_rule, account_type)
            # Si no hay seccion, usar busqueda directa
            return self._find_account_direct(employee, salary_rule, account_type)

        # MODO GLOBAL: Patron unico para todas las reglas
        # Patron directo: buscar en configuracion existente
        if self.structure_pattern == 'direct':
            return self._find_account_direct(employee, salary_rule, account_type)

        # Construir codigo
        built_code = self.build_account_code(employee, salary_rule)
        if not built_code:
            return False

        # Nivel 1: Busqueda exacta
        account = Account.search([
            ('code', '=', built_code),
            ('company_id', '=', company.id)
        ], limit=1)

        if account:
            return account

        # Nivel 2: Busqueda sin ultimo nivel (puesto)
        if self.include_job and self.search_levels >= 2:
            partial_code = self._remove_last_element(built_code)
            if partial_code:
                account = Account.search([
                    ('code', '=', partial_code),
                    ('company_id', '=', company.id)
                ], limit=1)
                if account:
                    return account

        # Nivel 3: Busqueda con wildcard
        if self.use_wildcard_search and self.search_levels >= 3:
            # Remover ultimos caracteres y buscar con like
            wildcard_code = built_code[:-2] + '%' if len(built_code) > 2 else built_code + '%'
            account = Account.search([
                ('code', '=like', wildcard_code),
                ('company_id', '=', company.id)
            ], limit=1)
            if account:
                return account

        # Nivel 4: Buscar con departamento padre
        if self.fallback_to_parent_dept and employee.department_id.parent_id:
            parent_dept = employee.department_id.parent_id
            # Recrear empleado virtual con depto padre para recalcular
            parent_code = self._build_with_parent_dept(employee, salary_rule, parent_dept)
            if parent_code:
                account = Account.search([
                    ('code', '=', parent_code),
                    ('company_id', '=', company.id)
                ], limit=1)
                if account:
                    return account

        return False

    def _find_account_direct(self, employee, salary_rule, account_type):
        """
        Busqueda directa en hr.salary.rule.accounting (metodo tradicional mejorado).
        """
        for account_rule in salary_rule.salary_rule_accounting:
            # Validar ubicacion de trabajo
            if account_rule.work_location and account_rule.work_location.id != employee.address_id.id:
                continue

            # Validar compania
            if account_rule.company and account_rule.company.id != employee.company_id.id:
                continue

            # Validar departamento (con busqueda en padres)
            if account_rule.department:
                dept = employee.department_id
                dept_match = False
                levels = 3  # Maximo niveles de busqueda en jerarquia
                while dept and levels > 0:
                    if account_rule.department.id == dept.id:
                        dept_match = True
                        break
                    dept = dept.parent_id
                    levels -= 1

                if not dept_match:
                    continue

            # Si llegamos aqui, la regla aplica
            if account_type == 'debit' and account_rule.debit_account:
                return account_rule.debit_account
            elif account_type == 'credit' and account_rule.credit_account:
                return account_rule.credit_account

        # Fallback a cuentas por defecto de la regla
        if account_type == 'debit':
            return salary_rule.account_debit
        return salary_rule.account_credit

    def _remove_last_element(self, code):
        """Remover ultimo elemento del codigo construido"""
        if self.use_separator and self.separator:
            parts = code.split(self.separator)
            return self.separator.join(parts[:-1]) if len(parts) > 1 else ''

        # Sin separador, remover ultimos N caracteres segun ultimo elemento
        order = self._get_pattern_order() if self.structure_pattern != 'custom' else \
                [e.strip().upper() for e in (self.custom_order or 'DEPT,RULE').split(',')]

        if not order:
            return code

        last_element = order[-1]
        length_map = {
            'DEPT': self.dept_code_length,
            'RULE': self.rule_code_length,
            'LOC': self.loc_code_length,
            'JOB': self.job_code_length,
        }

        remove_length = length_map.get(last_element, 2)
        return code[:-remove_length] if len(code) > remove_length else ''

    def _build_with_parent_dept(self, employee, salary_rule, parent_dept):
        """Construir codigo usando departamento padre"""
        elements = self.get_account_code_elements(employee, salary_rule)
        elements['DEPT'] = self._get_dept_code(parent_dept)

        sep = self.separator if self.use_separator else ''
        order = self._get_pattern_order() if self.structure_pattern != 'custom' else \
                [e.strip().upper() for e in (self.custom_order or 'DEPT,RULE').split(',')]

        parts = []
        for element in order:
            value = elements.get(element, '')
            if value:
                parts.append(value)

        return sep.join(parts)

    @api.model
    def get_default_config(self, company=None):
        """Obtener configuracion por defecto para una compania"""
        if not company:
            company = self.env.company

        config = self.search([
            ('company_id', '=', company.id),
            ('is_default', '=', True),
            ('active', '=', True)
        ], limit=1)

        if not config:
            # Crear configuracion por defecto si no existe
            config = self.create({
                'name': _('Configuracion por Defecto'),
                'company_id': company.id,
                'is_default': True,
                'structure_pattern': 'direct',
            })

        return config

    def action_simulate(self):
        """Abrir wizard de simulacion"""
        self.ensure_one()
        return {
            'name': _('Simular Construccion de Cuentas'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.accounting.structure.simulate.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_config_id': self.id}
        }


# =============================================================================
# MODELO DE SECCIONES DE ESTRUCTURA CONTABLE
# =============================================================================

class HrAccountingStructureSection(models.Model):
    """
    Seccion de Estructura Contable

    Permite definir patrones de construccion de cuentas diferentes
    para cada tipo de regla salarial (TOTALDEV, TOTALDED, NET, etc.)
    """
    _name = 'hr.accounting.structure.section'
    _description = 'Seccion de Estructura Contable'
    _order = 'sequence, id'
    _rec_name = 'display_name'

    config_id = fields.Many2one(
        'hr.accounting.structure.config',
        string='Configuracion',
        required=True,
        ondelete='cascade'
    )

    name = fields.Char(
        string='Nombre',
        required=True
    )

    display_name = fields.Char(
        string='Nombre Completo',
        compute='_compute_display_name',
        store=True
    )

    section_type = fields.Selection(
        selection=SECTION_TYPES,
        string='Tipo de Seccion',
        required=True,
        help='Tipo de reglas que maneja esta seccion'
    )

    sequence = fields.Integer(
        string='Orden de Ejecucion',
        default=10,
        help='Orden en que se procesan las secciones (menor = primero)'
    )

    active = fields.Boolean(
        string='Activo',
        default=True
    )

    # Colores para visualizacion
    color = fields.Integer(
        string='Color',
        default=0
    )

    # =========================================================================
    # PATRON DE CONSTRUCCION (heredado de config pero puede ser diferente)
    # =========================================================================
    structure_pattern = fields.Selection([
        ('direct', 'Busqueda Directa (Sin construccion)'),
        ('dept_rule', 'Departamento + Regla'),
        ('dept_rule_job', 'Departamento + Regla + Puesto'),
        ('dept_rule_loc', 'Departamento + Regla + Ubicacion'),
        ('dept_rule_loc_job', 'Departamento + Regla + Ubicacion + Puesto'),
        ('dept_loc_rule_job', 'Departamento + Ubicacion + Regla + Puesto'),
        ('loc_dept_rule', 'Ubicacion + Departamento + Regla'),
        ('rule_dept', 'Regla + Departamento'),
        ('custom', 'Personalizado'),
        ('inherit', 'Heredar de Configuracion'),
    ], string='Patron de Estructura',
       default='inherit',
       required=True,
       help='Patron para construir cuentas en esta seccion. "Heredar" usa el patron de la configuracion principal.'
    )

    custom_order = fields.Char(
        string='Orden Personalizado',
        help='Orden de elementos: DEPT,LOC,RULE,JOB'
    )

    # =========================================================================
    # CATEGORIAS DE REGLAS PERSONALIZADAS
    # =========================================================================
    rule_category_codes = fields.Char(
        string='Codigos de Categoria Adicionales',
        help='Codigos de categoria o regla adicionales separados por coma. '
             'Ej: PROV_CESANTIAS,PROV_INTERESES para agregar a esta seccion.'
    )

    rule_codes_exclude = fields.Char(
        string='Codigos a Excluir',
        help='Codigos de regla a excluir de esta seccion separados por coma.'
    )

    # =========================================================================
    # OPCIONES DE BUSQUEDA (pueden sobrescribir config)
    # =========================================================================
    use_wildcard_search = fields.Boolean(
        string='Busqueda con Comodin',
        default=True
    )

    fallback_to_parent_dept = fields.Boolean(
        string='Buscar en Departamento Padre',
        default=True
    )

    # =========================================================================
    # LONGITUD DE CODIGOS (puede ser diferente por seccion)
    # =========================================================================
    dept_code_length = fields.Integer(
        string='Longitud Codigo Departamento',
        default=4
    )

    rule_code_length = fields.Integer(
        string='Longitud Codigo Regla',
        default=4
    )

    loc_code_length = fields.Integer(
        string='Longitud Codigo Ubicacion',
        default=2
    )

    job_code_length = fields.Integer(
        string='Longitud Codigo Puesto',
        default=2
    )

    # Separador
    use_separator = fields.Boolean(
        string='Usar Separador',
        default=False
    )

    separator = fields.Char(
        string='Separador',
        default=''
    )

    # Estadisticas
    rule_count = fields.Integer(
        string='Reglas Asociadas',
        compute='_compute_rule_count'
    )

    notes = fields.Text(string='Notas')

    @api.depends('name', 'section_type')
    def _compute_display_name(self):
        type_labels = dict(SECTION_TYPES)
        for record in self:
            type_label = type_labels.get(record.section_type, '')
            type_prefix = type_label.split(' - ')[0] if ' - ' in type_label else record.section_type.upper()
            record.display_name = f"[{type_prefix}] {record.name}"

    def _compute_rule_count(self):
        """Contar reglas que pertenecen a esta seccion"""
        for record in self:
            categories = SECTION_CATEGORY_MAP.get(record.section_type, [])
            if record.rule_category_codes:
                custom_categories = [c.strip().upper() for c in record.rule_category_codes.split(',')]
                categories = list(set(categories + custom_categories))
            
            # Excluir codigos si estan definidos
            exclude_codes = []
            if record.rule_codes_exclude:
                exclude_codes = [c.strip().upper() for c in record.rule_codes_exclude.split(',')]

            domain = [
                '|',
                ('code', 'in', categories),
                ('category_id.code', 'in', categories)
            ]
            
            if exclude_codes:
                domain.append(('code', 'not in', exclude_codes))

            count = self.env['hr.salary.rule'].search_count(domain)
            record.rule_count = count

    def _get_effective_pattern(self):
        """Obtener patron efectivo (propio o heredado de config)"""
        self.ensure_one()
        if self.structure_pattern == 'inherit':
            return self.config_id.structure_pattern
        return self.structure_pattern

    def _get_pattern_order(self):
        """Obtener orden de elementos segun patron"""
        pattern = self._get_effective_pattern()
        patterns = {
            'dept_rule': ['DEPT', 'RULE'],
            'dept_rule_job': ['DEPT', 'RULE', 'JOB'],
            'dept_rule_loc': ['DEPT', 'RULE', 'LOC'],
            'dept_rule_loc_job': ['DEPT', 'RULE', 'LOC', 'JOB'],
            'dept_loc_rule_job': ['DEPT', 'LOC', 'RULE', 'JOB'],
            'loc_dept_rule': ['LOC', 'DEPT', 'RULE'],
            'rule_dept': ['RULE', 'DEPT'],
        }
        if pattern == 'custom' and self.custom_order:
            return [e.strip().upper() for e in self.custom_order.split(',')]
        return patterns.get(pattern, ['DEPT', 'RULE'])

    def get_account_code_elements(self, employee, salary_rule):
        """Obtener elementos para construir codigo de cuenta"""
        self.ensure_one()
        config = self.config_id

        elements = {}

        # Codigo departamento
        dept = employee.department_id
        elements['DEPT'] = self._get_dept_code(dept)

        # Codigo regla salarial
        elements['RULE'] = self._get_rule_code(salary_rule)

        # Codigo ubicacion
        elements['LOC'] = self._get_location_code(employee)

        # Codigo puesto
        elements['JOB'] = self._get_job_code(employee)

        return elements

    def _get_dept_code(self, department):
        """Obtener codigo del departamento"""
        if not department:
            return ''

        if hasattr(department, 'code_account') and department.code_account:
            code = department.code_account
        elif hasattr(department, 'code') and department.code:
            code = department.code
        else:
            code = str(department.id).zfill(self.dept_code_length)

        return code[:self.dept_code_length].ljust(self.dept_code_length, '0')

    def _get_rule_code(self, salary_rule):
        """Obtener codigo de la regla salarial"""
        if not salary_rule:
            return ''
        code = salary_rule.code or ''
        return code[:self.rule_code_length].ljust(self.rule_code_length, ' ')

    def _get_location_code(self, employee):
        """Obtener codigo de ubicacion de trabajo"""
        location = employee.address_id
        if not location:
            return ''

        if hasattr(location, 'location_code') and location.location_code:
            code = location.location_code
        else:
            code = str(location.id % 100).zfill(self.loc_code_length)

        return code[:self.loc_code_length].zfill(self.loc_code_length)

    def _get_job_code(self, employee):
        """Obtener codigo del puesto"""
        job = employee.job_id
        if not job:
            return ''

        if hasattr(job, 'code_account') and job.code_account:
            code = job.code_account
        elif hasattr(job, 'code') and job.code:
            code = job.code
        else:
            code = str(job.id % 100).zfill(self.job_code_length)

        return code[:self.job_code_length].zfill(self.job_code_length)

    def build_account_code(self, employee, salary_rule):
        """Construir codigo de cuenta segun patron de la seccion"""
        self.ensure_one()

        pattern = self._get_effective_pattern()
        if pattern == 'direct':
            return None

        elements = self.get_account_code_elements(employee, salary_rule)
        sep = self.separator if self.use_separator else ''
        order = self._get_pattern_order()

        parts = []
        for element in order:
            value = elements.get(element, '')
            if value:
                parts.append(value)

        return sep.join(parts)

    def find_account(self, employee, salary_rule, account_type='debit'):
        """
        Buscar cuenta contable usando el patron de esta seccion.

        Args:
            employee: hr.employee record
            salary_rule: hr.salary.rule record
            account_type: 'debit' o 'credit'

        Returns:
            account.account record o False
        """
        self.ensure_one()

        Account = self.env['account.account']
        company = employee.company_id
        pattern = self._get_effective_pattern()

        # Patron directo: buscar en configuracion existente
        if pattern == 'direct':
            return self._find_account_direct(employee, salary_rule, account_type)

        # Construir codigo
        built_code = self.build_account_code(employee, salary_rule)
        if not built_code:
            return False

        # Nivel 1: Busqueda exacta
        account = Account.search([
            ('code', '=', built_code),
            ('company_id', '=', company.id)
        ], limit=1)

        if account:
            return account

        # Nivel 2: Busqueda con wildcard
        if self.use_wildcard_search:
            wildcard_code = built_code[:-2] + '%' if len(built_code) > 2 else built_code + '%'
            account = Account.search([
                ('code', '=like', wildcard_code),
                ('company_id', '=', company.id)
            ], limit=1)
            if account:
                return account

        # Nivel 3: Buscar con departamento padre
        if self.fallback_to_parent_dept and employee.department_id.parent_id:
            parent_dept = employee.department_id.parent_id
            parent_code = self._build_with_parent_dept(employee, salary_rule, parent_dept)
            if parent_code:
                account = Account.search([
                    ('code', '=', parent_code),
                    ('company_id', '=', company.id)
                ], limit=1)
                if account:
                    return account

        # Fallback: busqueda directa
        return self._find_account_direct(employee, salary_rule, account_type)

    def _find_account_direct(self, employee, salary_rule, account_type):
        """Busqueda directa en hr.salary.rule.accounting"""
        for account_rule in salary_rule.salary_rule_accounting:
            # Validar ubicacion de trabajo
            if account_rule.work_location and account_rule.work_location.id != employee.address_id.id:
                continue

            # Validar compania
            if account_rule.company and account_rule.company.id != employee.company_id.id:
                continue

            # Validar departamento (con busqueda en padres)
            if account_rule.department:
                dept = employee.department_id
                dept_match = False
                levels = 3
                while dept and levels > 0:
                    if account_rule.department.id == dept.id:
                        dept_match = True
                        break
                    dept = dept.parent_id
                    levels -= 1

                if not dept_match:
                    continue

            # Si llegamos aqui, la regla aplica
            if account_type == 'debit' and account_rule.debit_account:
                return account_rule.debit_account
            elif account_type == 'credit' and account_rule.credit_account:
                return account_rule.credit_account

        # Fallback a cuentas por defecto de la regla
        if account_type == 'debit':
            return salary_rule.account_debit
        return salary_rule.account_credit

    def _build_with_parent_dept(self, employee, salary_rule, parent_dept):
        """Construir codigo usando departamento padre"""
        elements = self.get_account_code_elements(employee, salary_rule)
        elements['DEPT'] = self._get_dept_code(parent_dept)

        sep = self.separator if self.use_separator else ''
        order = self._get_pattern_order()

        parts = []
        for element in order:
            value = elements.get(element, '')
            if value:
                parts.append(value)

        return sep.join(parts)


class HrAccountingStructureSimulateWizard(models.TransientModel):
    """Wizard para simular construccion de cuentas"""
    _name = 'hr.accounting.structure.simulate.wizard'
    _description = 'Simulacion de Estructura Contable'

    config_id = fields.Many2one(
        'hr.accounting.structure.config',
        string='Configuracion',
        required=True
    )

    employee_ids = fields.Many2many(
        'hr.employee',
        string='Empleados',
        help='Dejar vacio para simular con todos los empleados activos'
    )

    salary_rule_ids = fields.Many2many(
        'hr.salary.rule',
        string='Reglas Salariales',
        help='Reglas a simular. Dejar vacio para todas las reglas con cuentas'
    )

    result_ids = fields.One2many(
        'hr.accounting.structure.simulate.result',
        'wizard_id',
        string='Resultados'
    )

    state = fields.Selection([
        ('config', 'Configuracion'),
        ('result', 'Resultados')
    ], default='config')

    # Estadisticas
    total_combinations = fields.Integer(string='Total Combinaciones', readonly=True)
    found_count = fields.Integer(string='Cuentas Encontradas', readonly=True)
    not_found_count = fields.Integer(string='No Encontradas', readonly=True)
    wildcard_count = fields.Integer(string='Por Comodin', readonly=True)

    def action_simulate(self):
        """Ejecutar simulacion"""
        self.ensure_one()

        config = self.config_id

        # Obtener empleados
        employees = self.employee_ids or self.env['hr.employee'].search([
            ('company_id', '=', config.company_id.id),
            ('active', '=', True)
        ], limit=50)  # Limitar para rendimiento

        # Obtener reglas
        rules = self.salary_rule_ids or self.env['hr.salary.rule'].search([
            '|',
            ('account_debit', '!=', False),
            ('account_credit', '!=', False)
        ], limit=20)

        # Limpiar resultados anteriores
        self.result_ids.unlink()

        results = []
        found = 0
        not_found = 0
        wildcard = 0

        Result = self.env['hr.accounting.structure.simulate.result']

        for employee in employees:
            for rule in rules:
                # Construir codigo
                built_code = config.build_account_code(employee, rule) or '-'

                # Buscar cuenta
                debit_account = config.find_account(employee, rule, 'debit')
                credit_account = config.find_account(employee, rule, 'credit')

                # Determinar estado
                if debit_account or credit_account:
                    if built_code != '-' and debit_account and debit_account.code != built_code:
                        status = 'wildcard'
                        wildcard += 1
                    else:
                        status = 'found'
                        found += 1
                else:
                    status = 'not_found'
                    not_found += 1

                results.append({
                    'wizard_id': self.id,
                    'employee_id': employee.id,
                    'department_id': employee.department_id.id,
                    'job_id': employee.job_id.id,
                    'work_location_id': employee.address_id.id,
                    'salary_rule_id': rule.id,
                    'built_code': built_code,
                    'debit_account_id': debit_account.id if debit_account else False,
                    'credit_account_id': credit_account.id if credit_account else False,
                    'status': status,
                })

        # Crear resultados
        Result.create(results)

        # Actualizar estadisticas
        self.write({
            'state': 'result',
            'total_combinations': len(results),
            'found_count': found,
            'not_found_count': not_found,
            'wildcard_count': wildcard,
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_back(self):
        """Volver a configuracion"""
        self.write({'state': 'config'})
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_export_excel(self):
        """Exportar resultados a Excel"""
        # TODO: Implementar exportacion
        raise UserError(_('Funcionalidad de exportacion pendiente de implementar'))


# =============================================================================
# EXTENSIONES DE MODELOS PARA CODIGOS CONTABLES
# =============================================================================

class HrDepartmentAccountingExtension(models.Model):
    """Extension de hr.department para codigos contables"""
    _inherit = 'hr.department'

    code_account = fields.Char(
        string='Codigo Contable',
        size=6,
        help='Codigo del departamento para construccion de cuentas contables (2-6 digitos)'
    )

    @api.constrains('code_account')
    def _check_code_account(self):
        for record in self:
            if record.code_account:
                if not record.code_account.isalnum():
                    raise ValidationError(
                        _('El codigo contable del departamento solo puede contener letras y numeros')
                    )


class HrJobAccountingExtension(models.Model):
    """Extension de hr.job para codigos contables"""
    _inherit = 'hr.job'

    code_account = fields.Char(
        string='Codigo Contable',
        size=4,
        help='Codigo del puesto para construccion de cuentas contables (2-4 digitos)'
    )

    @api.constrains('code_account')
    def _check_code_account(self):
        for record in self:
            if record.code_account:
                if not record.code_account.isalnum():
                    raise ValidationError(
                        _('El codigo contable del puesto solo puede contener letras y numeros')
                    )


class ResPartnerLocationExtension(models.Model):
    """Extension de res.partner para ubicaciones de trabajo"""
    _inherit = 'res.partner'

    is_work_location = fields.Boolean(
        string='Es Ubicacion de Trabajo',
        default=False,
        help='Marcar si este contacto representa una ubicacion de trabajo (sucursal, oficina, etc.)'
    )

    location_code = fields.Char(
        string='Codigo Ubicacion',
        size=4,
        help='Codigo de ubicacion para construccion de cuentas contables (2-4 digitos)'
    )

    location_type = fields.Selection([
        ('branch', 'Sucursal'),
        ('office', 'Oficina'),
        ('warehouse', 'Bodega'),
        ('plant', 'Planta'),
        ('remote', 'Remoto'),
        ('other', 'Otro'),
    ], string='Tipo de Ubicacion')

    accounting_code_prefix = fields.Char(
        string='Prefijo Contable',
        size=10,
        help='Prefijo especifico para cuentas contables de esta ubicacion'
    )

    @api.constrains('location_code')
    def _check_location_code(self):
        for record in self:
            if record.location_code:
                if not record.location_code.isalnum():
                    raise ValidationError(
                        _('El codigo de ubicacion solo puede contener letras y numeros')
                    )


# =============================================================================
# RESULTADOS DE SIMULACION
# =============================================================================

class HrAccountingStructureSimulateResult(models.TransientModel):
    """Resultados de simulacion"""
    _name = 'hr.accounting.structure.simulate.result'
    _description = 'Resultado de Simulacion'

    wizard_id = fields.Many2one(
        'hr.accounting.structure.simulate.wizard',
        string='Wizard',
        ondelete='cascade'
    )

    employee_id = fields.Many2one('hr.employee', string='Empleado')
    department_id = fields.Many2one('hr.department', string='Departamento')
    job_id = fields.Many2one('hr.job', string='Puesto')
    work_location_id = fields.Many2one('res.partner', string='Ubicacion')
    salary_rule_id = fields.Many2one('hr.salary.rule', string='Regla')

    built_code = fields.Char(string='Codigo Construido')
    debit_account_id = fields.Many2one('account.account', string='Cuenta Debito')
    credit_account_id = fields.Many2one('account.account', string='Cuenta Credito')

    status = fields.Selection([
        ('found', 'Encontrada'),
        ('not_found', 'No Encontrada'),
        ('wildcard', 'Por Comodin'),
        ('parent', 'Por Dept. Padre'),
    ], string='Estado')

    status_icon = fields.Char(compute='_compute_status_icon')

    @api.depends('status')
    def _compute_status_icon(self):
        icons = {
            'found': '✓',
            'not_found': '✗',
            'wildcard': '⚠',
            'parent': '↑',
        }
        for record in self:
            record.status_icon = icons.get(record.status, '')
