from odoo import models, fields, api, _
from datetime import datetime, timedelta, date
from dateutil.relativedelta import relativedelta
import calendar
from collections import defaultdict
import re
import math
from odoo.exceptions import UserError, ValidationError
from odoo.tools.safe_eval import safe_eval
from odoo.tools import format_date, formatLang, frozendict, date_utils, format_amount
from decimal import Decimal, getcontext, ROUND_HALF_UP
import logging
import operator
_logger = logging.getLogger(__name__)
# Tabla de retención
TABLA_RETENCION = [
    (0, 95, 0, 0, 0),
    (95, 150, 19, 95, 0),
    (150, 360, 28, 150, 10),
    (360, 640, 33, 360, 69),
    (640, 945, 35, 640, 162),
    (945, 2300, 37, 945, 268),
    (2300, float('inf'), 39, 2300, 770)
]
DAYS_YEAR = 360
def days360(start_date, end_date, method_eu=True):
    """
    Calcula días usando método bancario 30/360.
    Estándar colombiano para cálculos de nómina.
    """
    start_day = start_date.day
    start_month = start_date.month
    start_year = start_date.year
    end_day = end_date.day
    end_month = end_date.month
    end_year = end_date.year

    if start_day == 31:
        start_day = 30

    if end_day == 31:
        if method_eu is False and start_day != 30:
            end_day = 1
            if end_month == 12:
                end_year += 1
                end_month = 1
            else:
                end_month += 1
        else:
            end_day = 30
    
    if end_month == 2 and end_day in (28, 29):
        end_day = 30

    return (end_day + end_month * 30 + end_year * 360 -
            start_day - start_month * 30 - start_year * 360 + 1)


def get_monthly_hours_ley2101(calculation_date, annual_parameters=None):
    """
    Obtiene horas mensuales según Ley 2101 de Colombia.
    Reducción gradual de jornada laboral.
    """
    if annual_parameters and annual_parameters.hours_monthly > 0:
        return float(annual_parameters.hours_monthly)
    
    year = calculation_date.year
    month = calculation_date.month
    day = calculation_date.day
    
    if year < 2023:
        return 240.0
    elif year == 2023:
        return 240.0 if (month < 7 or (month == 7 and day < 15)) else 235.0
    elif year == 2024:
        return 235.0 if (month < 7 or (month == 7 and day < 15)) else 230.0
    elif year == 2025:
        return 230.0 if (month < 7 or (month == 7 and day < 15)) else 220.0
    elif year == 2026:
        return 220.0 if (month < 7 or (month == 7 and day < 15)) else 210.0
    else:
        return 210.0



class HrSalaryRule(models.Model):
    _name = 'hr.salary.rule'
    _inherit = ['hr.salary.rule','mail.thread', 'mail.activity.mixin']
    
    # Constantes de clase para cálculos
    DIAS_ANIO = Decimal("360")
    DIAS_MES = Decimal("30")
    CODIGOS_AUXILIO = ["AUX000", "AUX00C", "AUX1111", "AUX_CONECTIVIDAD"]
    
    # =====================================================
    # MÉTODOS AUXILIARES PARA CÁLCULOS
    # =====================================================
    
    @api.model
    def _a_decimal(self, valor):
        """Convierte valor a Decimal de forma segura."""
        if isinstance(valor, Decimal):
            return valor
        if valor is None:
            return Decimal("0")
        return Decimal(str(valor))
    
    @api.model
    def _redondear2(self, valor):
        """Redondea a 2 decimales con ROUND_HALF_UP."""
        return self._a_decimal(valor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    
    @api.model
    def _tiene_flag_prestacion(self, linea, flag_name):
        """
        Método central para validar si una línea tiene un flag de prestación.
        
        Args:
            linea: Diccionario de la línea (de query o de localdict)
            flag_name: Nombre del flag a buscar (base_cesantias, base_prima, etc)
            
        Returns:
            bool: True si tiene el flag activo
            
        Busca en este orden:
        1. En metadata si existe
        2. En el objeto de la línea si existe
        3. En la regla salarial directamente
        """
        # 1. Verificar en metadata
        metadata = linea.get("metadata") or {}
        if metadata.get(flag_name):
            return True
            
        # 2. Si metadata tiene objeto, verificar ahí
        if metadata.get("object"):
            obj = metadata["object"]
            if hasattr(obj, flag_name) and getattr(obj, flag_name, False):
                return True
                
        # 3. Verificar en line_obj si existe
        line_obj = linea.get("line_obj")
        if line_obj:
            # Si es una línea de nómina real
            if hasattr(line_obj, 'salary_rule_id'):
                rule = line_obj.salary_rule_id
                if hasattr(rule, flag_name):
                    return bool(getattr(rule, flag_name, False))
                    
        # 4. Buscar por código si tenemos acceso al env
        code = linea.get("code")
        if code and hasattr(self, 'env'):
            rule = self.env['hr.salary.rule'].search([('code', '=', code)], limit=1)
            if rule and hasattr(rule, flag_name):
                return bool(getattr(rule, flag_name, False))
                
        return False
    
    @api.model
    def _get_lineas_con_flag(self, localdict, flag_name):
        """
        Obtiene todas las líneas que tienen un flag específico.
        
        Args:
            localdict: Diccionario local con datos de cálculo
            flag_name: Nombre del flag (base_cesantias, base_prima, etc)
            
        Returns:
            list: Lista de diccionarios con las líneas filtradas
        """
        lineas = []
        
        # Usar query si está disponible
        if 'query' in localdict:
            q = query(localdict)
            todas = q.get()
            
            for linea in todas:
                if self._tiene_flag_prestacion(linea, flag_name):
                    lineas.append(linea)
                    
        # Si no hay query, buscar en cache directamente
        elif 'cache' in localdict:
            cache = localdict['cache']
            for key in cache.values.keys():
                if not key.endswith('_metadata') and not key.endswith('_log'):
                    # Buscar la regla para verificar el flag
                    rule = self.env['hr.salary.rule'].search([('code', '=', key)], limit=1)
                    if rule and hasattr(rule, flag_name) and getattr(rule, flag_name, False):
                        lineas.append({
                            'code': key,
                            'total': cache.get(key, 0),
                            'metadata': cache.get(f"{key}_metadata", {})
                        })
                        
        return lineas
    
    @api.model
    def _get_conceptos_historicos_prestacion(self, contrato, fecha_inicio, fecha_fin, flag_name):
        """
        Obtiene conceptos históricos con un flag específico de prestación.
        
        Args:
            contrato: Objeto hr.contract
            fecha_inicio: Fecha inicio de búsqueda
            fecha_fin: Fecha fin de búsqueda
            flag_name: Nombre del flag (base_cesantias, base_prima, etc)
            
        Returns:
            dict: {codigo: {'nombre': str, 'total': Decimal}}
        """
        conceptos = {}
        
        if not contrato or not fecha_inicio or not fecha_fin:
            return conceptos
            
        # Buscar nóminas históricas
        nominas = self.env['hr.payslip'].search([
            ('contract_id', '=', contrato.id),
            ('state', 'in', ['done', 'paid']),
            ('date_from', '>=', fecha_inicio),
            ('date_to', '<=', fecha_fin)
        ])
        
        if nominas:
            # Buscar líneas con el flag específico
            campo_flag = f"salary_rule_id.{flag_name}"
            lineas = self.env["hr.payslip.line"].search([
                ("slip_id", "in", nominas.ids),
                (campo_flag, "=", True),
            ])
            
            for linea in lineas:
                codigo = linea.salary_rule_id.code
                # Excluir salario básico y auxilios
                if codigo in self.CODIGOS_AUXILIO or codigo == "BASIC":
                    continue
                    
                valor = self._a_decimal(linea.total)
                if valor == 0:
                    continue
                    
                if codigo not in conceptos:
                    conceptos[codigo] = {
                        'nombre': linea.salary_rule_id.name,
                        'total': Decimal("0")
                    }
                conceptos[codigo]['total'] += valor
                
        return conceptos
    
    # Campos existentes mantenidos y mejorados
    struct_id = fields.Many2one(tracking=True)
    active = fields.Boolean(tracking=True)
    sequence = fields.Integer(tracking=True)
    condition_select = fields.Selection(tracking=True)
    amount_select = fields.Selection(
        selection_add=[('concept', 'Concept Code')], 
        ondelete={'concept': 'set default'}
    )
    amount_python_compute = fields.Text(tracking=True)
    appears_on_payslip = fields.Boolean(tracking=True)
    
    # Campos específicos lavish
    types_employee = fields.Many2many('hr.types.employee', string='Tipos de Empleado', tracking=True)
    account_code = fields.Char(
        string='Base Codigo De Cuenta',
        size=10,
        help="""
        Código base para generar automáticamente cuentas crédito.
        Ejemplo: Departamento 5105
            - Seguridad Social: 23XXXX (pasivos)
            - Prestaciones: 26XXXX (provisiones)
            - Neto a Pagar: 11XXXX (bancos)
        
        El sistema construirá códigos específicos según el tipo de regla y codigo de la regla:
        - Seguridad Social: 51 0505 (Gasto)
        - Seguridad Social: 23 7501 (pasivos)
        - Prestaciones:     26 0501 (provisiones)
        """
    )
    aplicar_cobro = fields.Selection([
        ('15', 'Primera quincena'),
        ('30', 'Segunda quincena'),
        ('0', 'Siempre')
    ], 'Aplicar cobro', tracking=True)
    
    modality_value = fields.Selection([
        ('fijo', 'Valor fijo'),
        ('diario', 'Valor diario'),
        ('diario_efectivo', 'Valor diario del día efectivamente laborado')
    ], 'Modalidad de valor', tracking=True)
    
    # Campos para prestaciones sociales
    base_prima = fields.Boolean('Para prima', tracking=True)
    base_cesantias = fields.Boolean('Para cesantías', tracking=True)
    base_vacaciones = fields.Boolean('Para vacaciones tomadas', tracking=True)
    base_vacaciones_dinero = fields.Boolean('Para vacaciones dinero', tracking=True)
    base_intereses_cesantias = fields.Boolean('Para intereses de cesantías', tracking=True)
    base_auxtransporte_tope = fields.Boolean('Para tope de auxilio de transporte', tracking=True)
    base_compensation = fields.Boolean('Para liquidación de indemnización', tracking=True)

    # Base de Seguridad Social
    base_seguridad_social = fields.Boolean('Para seguridad social', tracking=True)
    base_arl = fields.Boolean('Para ARL', tracking=True)
    
    # Campo para activar configuraciones contables
    has_priority_flow = fields.Boolean(
        string='Activar Configuraciones Contables',
        default=False,
        help='Si está activo, permite configurar múltiples prioridades contables para esta regla'
    )
    
    # Campo One2many para el modelo nuevo
    accounting_priority_ids = fields.One2many(
        'hr.salary.rule.accounting.priority',
        'salary_rule_id',
        string='Prioridades Contables',
        help='Configuraciones de prioridad contable para esta regla'
    )
    base_parafiscales = fields.Boolean('Para parafiscales', tracking=True)
    
    # Campos adicionales
    proyectar_nom = fields.Boolean('Proyectar en nomina')
    proyectar_ret = fields.Boolean('Proyectar en Retencion')
    is_leave = fields.Boolean('Es Ausencia', tracking=True)
    is_recargo = fields.Boolean('Es Recargos', tracking=True)
    deduction_applies_bonus = fields.Boolean('Aplicar deducción en Prima', tracking=True)
    account_tax_id = fields.Many2one("account.tax", "Impuesto de Retefuente Laboral")
    
    deduct_deductions = fields.Selection([
        ('all', 'Todas las deducciones'),
        ('law', 'Solo las deducciones de ley')
    ], 'Tener en cuenta al descontar', default='all', tracking=True)
    
    rounding_method = fields.Selection([
        ('no_round', 'Sin redondeo'),
        ('round1', 'Redondear a entero'),
        ('round100', 'Redondear al 100 más cercano'),
        ('round1000', 'Redondear al 1000 más cercano'),
        ('round2d', 'Redondear a 2 decimales')
    ], string='Método de redondeo', default='no_round')
    
    restart_one_month_prima = fields.Boolean('Restar 1 mes al promedio de los acumulados en prima', tracking=True)
    liquidar_con_base = fields.Boolean('Liquidar con IBC mes anterior', tracking=True)
    excluir_ret = fields.Boolean('Excluir de Calculo retefuente', tracking=True)
    is_projectable_rtf = fields.Boolean(
        string='Proyectable para Retención / Fondos',
        default=False,
        help='Indica si este concepto debe ser proyectado en el cálculo de retención en la fuente'
    )
    
    descontar_suspensiones = fields.Boolean('Descontar Licencia No remuneradas', tracking=True)
    salary_rule_accounting = fields.One2many('hr.salary.rule.accounting', 'salary_rule', string="Contabilización", tracking=True)
    
    # Reportes
    display_days_worked = fields.Boolean(string='Mostrar la cantidad de días trabajados en los formatos de impresión', tracking=True)
    short_name = fields.Char(string='Nombre corto/reportes')
    process = fields.Selection([
        ('nomina', 'Nónima'),
        ('vacaciones', 'Vacaciones'),
        ('prima', 'Prima'),
        ('cesantias', 'Cesantías'),
        ('intereses_cesantias', 'Intereses de cesantías'),
        ('contrato', 'Liq. de Contrato'),
        ('otro', 'Otro')
    ], string='Proceso')
    
    novedad_ded = fields.Selection([
        ('cont', 'Contrato'),
        ('Noved', 'Novedad'),
        ('0', 'No')
    ], 'Opcion de Novedad', tracking=True)
    
    not_include_flat_payment_file = fields.Boolean(string='No incluir en archivo plano de pagos')
    
    # Empleados públicos
    account_id_cxp = fields.Many2one('account.account', string='Cuenta CXP', company_dependent=True)
    state_budget_item = fields.Char(string='Rubro')
    state_budget_resource = fields.Char(string='Recurso')
    # Campos para reglas y categorías adicionales
    categorias_adicionales = fields.Many2many(
        'hr.salary.rule.category',
        'hr_rule_category_adicionales_rel',
        'rule_id',
        'category_id',
        string='Categorías Adicionales',
        domain=[
            ('code', 'not in', ['DEV_SALARIAL', 'DEV_NO_SALARIAL', 'PRESTACIONES_SOCIALES', 'AUX', 'IND', 'DEDUCCIONES'])
        ],
        help='Seleccione categorías adicionales para incluir en los cálculos',
        tracking=True
    )
    reglas_adicionales = fields.Many2many(
        'hr.salary.rule',
        'hr_rule_reglas_adicionales_rel',
        'rule_parent_id',
        'rule_child_id',
        string='Reglas Adicionales',
        domain=[
            ('code', 'not in', ['TOTALDEV', 'TOTALDED', 'NET'])
        ],
        help='Seleccione reglas adicionales para incluir en los cálculos de totaldev, totalded y net',
        tracking=True
    )
    type_concepts = fields.Selection([
        ('base', 'Básicos'),
        ('contrato', 'Fijo Contrato'),
        ('ley', 'Por Ley'),
        ('novedad', 'Novedad Variable'),
        ('prestacion', 'Prestación Social'),
        ('prestamos', 'Préstamos'),
        ('by_partner', 'Pago a Terceros'),
        ('provisiones', 'Provisiones Prestación'),
        ('provisiones_consolidas', 'Provisiones Consolidadas'),
        ('seguridad_social', 'Seguridad Social'),
        ('tributaria', 'Deducción Tributaria'),
        ('other', 'Otros')
    ], string='Tipo de Concepto', default='other', tracking=True)
    
    dev_or_ded = fields.Selection([
        ('devengo', 'Devengo'),
        ('deduccion', 'Deducción'),
        ('provisiones', 'Provisiones'),
        ('no_net', 'No Afecta Neto'),
        ('info', 'Informativo'),
        ('none', 'Ninguna')
    ], string='Naturaleza', default='none', tracking=True)
    
    enable_accounting = fields.Boolean(
        string='Habilitar Contabilización',
        default=True,
        help='Si está activo, esta regla generará movimientos contables',
        tracking=True
    )
    
    # Relaciones
    accounting_config_ids = fields.One2many(
        'hr.salary.rule.accounting',
        'salary_rule',
        string='Configuraciones Contables'
    )
    
    accounting_config_count = fields.Integer(
        string='# Configuraciones',
        compute='_compute_accounting_config_count'
    )
    
    @api.depends('accounting_config_ids')
    def _compute_accounting_config_count(self):
        for rule in self:
            rule.accounting_config_count = len(rule.accounting_config_ids)
    
    # =====================================================
    # BOTONES DE ACCIÓN
    # =====================================================
    
    def action_view_accounting_configs(self):
        """Ver configuraciones contables"""
        self.ensure_one()
        return {
            'name': f'Configuraciones de {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'hr.salary.rule.accounting',
            'view_mode': 'list,form',
            'domain': [('salary_rule_id', '=', self.id)],
            'context': {
                'default_salary_rule_id': self.id,
                'default_company_id': self.env.company.id,
            }
        }
    
    def action_generate_for_this_rule(self):
        """Genera configuración para esta regla específica en el contexto actual"""
        self.ensure_one()
        
        if not self.enable_accounting:
            raise UserError(_("Esta regla no tiene habilitada la contabilización"))
        
        # Obtener contexto (departamento o job del empleado actual si existe)
        active_model = self.env.context.get('active_model')
        active_id = self.env.context.get('active_id')
        
        if active_model == 'hr.department' and active_id:
            department = self.env['hr.department'].browse(active_id)
            result = department._create_or_update_accounting_config(self)
        elif active_model == 'hr.job' and active_id:
            job = self.env['hr.job'].browse(active_id)
            result = job._create_or_update_accounting_config(self)
        else:
            # Crear configuración global de compañía
            result = self._create_global_accounting_config()
        
        if result == 'created':
            message = "Configuración creada exitosamente"
        elif result == 'updated':
            message = "Configuración actualizada exitosamente"
        else:
            message = "No se pudo crear la configuración"
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Generación Completada',
                'message': message,
                'type': 'success' if result else 'warning'
            }
        }
    
    def action_generate_for_all_departments(self):
        """Genera configuración para todos los departamentos"""
        self.ensure_one()
        
        if not self.enable_accounting:
            raise UserError(_("Esta regla no tiene habilitada la contabilización"))
        
        departments = self.env['hr.department'].search([
            ('code_account', '!=', False),
            ('skip_accounting', '=', False)
        ])
        
        if not departments:
            raise UserError(_("No hay departamentos con código contable configurado"))
        
        created = 0
        updated = 0
        
        for dept in departments:
            try:
                result = dept._create_or_update_accounting_config(self)
                if result == 'created':
                    created += 1
                elif result == 'updated':
                    updated += 1
            except Exception as e:
                _logger.error(f"Error con departamento {dept.name}: {e}")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Generación Masiva Completada',
                'message': f"✓ {created} creadas\n✓ {updated} actualizadas",
                'type': 'success'
            }
        }
    
    def _create_global_accounting_config(self):
        """Crea configuración global para la compañía"""
        # Determinar cuentas por defecto
        debit_account = False
        credit_account = False
        
        if self.type_concepts == 'base' and self.dev_or_ded == 'devengo':
            debit_code = '510506'  # Sueldos
        elif self.type_concepts == 'seguridad_social' and self.dev_or_ded == 'deduccion':
            credit_code = '23'  # Aportes
        else:
            return False
        
        # Buscar o crear cuentas
        Account = self.env['account.account']
        
        if 'debit_code' in locals():
            debit_account = Account.search([
                ('code', '=', debit_code),
                ('company_ids', '=', self.env.company.id)
            ], limit=1)
        
        if 'credit_code' in locals():
            credit_account = Account.search([
                ('code', '=', credit_code),
                ('company_ids', '=', self.env.company.id)
            ], limit=1)
        
        if not debit_account and not credit_account:
            return False
        
        # Crear configuración
        AccountingConfig = self.env['hr.salary.rule.accounting']
        
        existing = AccountingConfig.search([
            ('salary_rule', '=', self.id),
            ('company_id', '=', self.env.company.id),
            ('department_id', '=', False),
            ('job_id', '=', False),
            ('employee_id', '=', False)
        ], limit=1)
        
        config_data = {
            'salary_rule_id': self.id,
            'company_id': self.env.company.id,
            'priority_type': 'company',
            'debit_account_id': debit_account.id if debit_account else False,
            'credit_account_id': credit_account.id if credit_account else False,
        }
        
        if existing:
            existing.write(config_data)
            return 'updated'
        else:
            AccountingConfig.create(config_data)
            return 'created'

    def _compute_rule_lavish(self, localdict):
        """
        :param localdict: dictionary containing the current computation environment
        :return: returns a tuple (amount, qty, rate, leave, log, other)
        :rtype: (float, float, float, bool/dict, bool/str, list)
        """
        self.ensure_one()
        res = 0, 0, 0, 0, 0, []
        localdict['days360'] = days360
        localdict['get_monthly_hours'] = lambda d: get_monthly_hours_ley2101(d, localdict.get('annual_parameters'))
        
        # Funciones matemáticas disponibles en safe_eval
        localdict['abs'] = abs
        localdict['round'] = round
        localdict['min'] = min
        localdict['max'] = max
        localdict['sum'] = sum
        localdict['len'] = len
        localdict['pow'] = pow
        
        # Funciones matemáticas usando math internamente sin exponer el módulo
        localdict['ceil'] = lambda x: math.ceil(x)
        localdict['floor'] = lambda x: math.floor(x)
        localdict['sqrt'] = lambda x: math.sqrt(x)
        
        # Funciones de redondeo especiales
        localdict['round_up'] = lambda x, d=0: math.ceil(x * (10**d)) / (10**d)
        localdict['round_down'] = lambda x, d=0: math.floor(x * (10**d)) / (10**d)
        
        # Tipos de fecha disponibles
        localdict['datetime'] = datetime
        localdict['date'] = date
        localdict['timedelta'] = timedelta
        localdict['relativedelta'] = relativedelta
    
        try:
            if self.amount_select == 'fix':
                try:
                    return (
                        self.amount_fix or 0.0, 
                        float(safe_eval(self.quantity, localdict)), 
                        100.0,
                        False,
                        False,
                        False
                    )
                except Exception as e:
                    self._raise_error(localdict, _("Wrong quantity defined for:"), e, "amount_fix calculation")
                        
            if self.amount_select == 'percentage':
                try:
                    return (
                        float(safe_eval(self.amount_percentage_base, localdict)),
                        float(safe_eval(self.quantity, localdict)),
                        self.amount_percentage or 0.0,
                        False,
                        False,
                        False
                    )
                except Exception as e:
                    self._raise_error(localdict, _("Wrong percentage base or quantity defined for:"), e, "percentage calculation")
                        
            if self.amount_select == 'code':
                try:
                    safe_eval(self.amount_python_compute or "result = 0", localdict, mode='exec')
                    result = float(localdict.get('result', 0))
                    result_qty = localdict.get('result_qty', 1.0) or 1
                    result_rate = localdict.get('result_rate', 100.0) or 100
                    return (
                        result,
                        result_qty,
                        result_rate,
                        False,
                        False,
                        False
                    )
                except Exception as e:
                    error_context = {
                        'code': self.amount_python_compute,
                        'location': 'Python code evaluation'
                    }
                    self._raise_error(localdict, _("Wrong python code defined for:"), e, "code evaluation", error_context)
                        
            if self.amount_select == 'concept':
                try:
                    method = getattr(self, f'_{str(self.code).lower()}', None)
                    if method:
                        res = method(localdict)
                        return float(res[0]), res[1], res[2], res[3], res[4], res[5]
                    return float(res[0]), res[1], res[2], res[3], res[4], res[5]
                except Exception as e:
                    error_context = {
                        'method_name': f'_{str(self.code).lower()}',
                        'location': 'Concept method execution'
                    }
                    self._raise_error(localdict, _("Wrong python code defined for:"), e, "concept execution", error_context)
                        
        except Exception as e:
            self._raise_error(localdict, _("Unexpected error in rule computation:"), e, "general computation")
            
    def _raise_error(self, localdict, error_type, e, error_location=None, error_context=None):
        """
        Raise a detailed error message with context information
        Args:
            localdict: The local dictionary with computation context
            error_type: Type of error that occurred
            e: The exception object
            error_location: Where the error occurred
            error_context: Additional context about the error (optional)
        """
        import traceback
        import sys
        
        # Get the full traceback
        exc_type, exc_value, exc_traceback = sys.exc_info()
        trace_details = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        
        # Get relevant code if available
        code_context = ""
        if error_context and 'code' in error_context:
            code_context = f"\n\nRelevant code:\n{error_context['code']}"
        
        # Get specific error details
        error_details = f"\n\nError Location: {error_location}"
        if error_context:
            for key, value in error_context.items():
                if key != 'code':  # Skip code as it's already included above
                    error_details += f"\n{key}: {value}"
        
        # Build the complete error message
        error_message = _("""%s
        - Employee: %s
        - Contract: %s
        - Payslip: %s
        - Salary rule: %s (%s)
        - Error type: %s
        - Error message: %s
        %s
        %s

        Traceback:
        %s""",
            error_type,
            localdict['employee'].name,
            localdict['contract'].name,
            localdict['slip'].name,
            self.name,
            self.code,
            type(e).__name__,
            str(e),
            error_details,
            code_context,
            trace_details)
        
        raise UserError(error_message)
   
  
    # =====================================================
    # MÉTODO MAESTRO UNIFICADO DE CONSULTA
    # =====================================================
    
    def _get_period_data(self, localdict, periods=None, filters=None, include_multi=True, return_type='dict'):
        """
        Método maestro para obtener datos de cualquier periodo con filtros flexibles
        """
        periods = periods or ['current']
        filters = filters or {}
        
        if isinstance(periods, str):
            periods = [periods]
        
        # Obtener IDs de nóminas según periodos
        payslip_ids = self._get_payslip_ids_from_periods(localdict, periods)
        
        # Inicializar resultado con estructura completa
        result = {
            'total': 0.0,
            'quantity': 0.0,
            'entries': [],
            'by_rule': defaultdict(lambda: {
                'total': 0, 
                'quantity': 0, 
                'entries': [], 
                'rule': None,
                'name': '',
                'category': '',
                'lines': []
            }),
            'by_category': defaultdict(lambda: {
                'total': 0, 
                'quantity': 0, 
                'entries': [], 
                'rules': set(),
                'lines': []
            })
        }
        
        # Procesar líneas de nómina si hay IDs
        if payslip_ids:
            lines = self._get_filtered_lines(localdict, payslip_ids, filters)
            
            for line in lines:
                entry = self._create_detailed_entry(line)
                self._add_entry_to_result(entry, result, line)
        
        # Procesar rules_multi si está habilitado
        if include_multi and 'rules_multi' in localdict:
            multi_entries = self._process_rules_multi_detailed(localdict['rules_multi'], filters)
            for entry in multi_entries:
                self._add_entry_to_result(entry, result, None)
        
        # Retornar según tipo solicitado
        if return_type == 'total':
            return result['total']
        elif return_type == 'quantity':
            return result['quantity']
        elif return_type == 'entries':
            return result['entries']
        else:
            return result
    
    def _get_payslip_ids_from_periods(self, localdict, periods):
        """Obtiene IDs de nóminas de los periodos especificados"""
        all_ids = set()
        
        period_mapping = {
            'current': 'current_month',
            'before': 'before_month', 
            'prima': 'prima_current_month',
            'cesantias': 'cesantias_current_month'
        }
        
        for period in periods:
            if period in period_mapping:
                key = period_mapping[period]
                if key in localdict and localdict[key]:
                    if isinstance(localdict[key], (set, list, tuple)):
                        all_ids.update(localdict[key])
                    else:
                        all_ids.add(localdict[key])
        
        # Excluir la nómina actual si existe
        if 'slip' in localdict and localdict['slip']:
            all_ids.discard(localdict['slip'].id)
        
        return list(all_ids)
    
    def _get_filtered_lines(self, localdict, payslip_ids, filters):
        """Obtiene líneas filtradas"""
        domain = [
            ('slip_id', 'in', payslip_ids),
            ('contract_id', '=', localdict['contract'].id)
        ]
        
        # Aplicar filtros de dominio
        if 'rules' in filters:
            rules = filters['rules'] if isinstance(filters['rules'], list) else [filters['rules']]
            domain.append(('salary_rule_id.code', 'in', rules))
        
        if 'exclude_rules' in filters:
            excluded = filters['exclude_rules'] if isinstance(filters['exclude_rules'], list) else [filters['exclude_rules']]
            domain.append(('salary_rule_id.code', 'not in', excluded))
        
        lines = self.env['hr.payslip.line'].search(domain)
        
        # Filtrar líneas adicionales
        return [line for line in lines if self._line_passes_filters(line, filters)]
    
    def _line_passes_filters(self, line, filters):
        """Verifica si una línea pasa todos los filtros"""
        rule = line.salary_rule_id
        category = rule.category_id
        
        # Filtro de categorías
        if 'categories' in filters:
            categories = filters['categories'] if isinstance(filters['categories'], list) else [filters['categories']]
            cat_code = category.code if category else None
            parent_code = category.parent_id.code if category and category.parent_id else None
            if not (cat_code in categories or parent_code in categories):
                return False
        
        # Filtro de categorías excluidas
        if 'exclude_categories' in filters:
            excluded = filters['exclude_categories'] if isinstance(filters['exclude_categories'], list) else [filters['exclude_categories']]
            cat_code = category.code if category else None
            parent_code = category.parent_id.code if category and category.parent_id else None
            if cat_code in excluded or parent_code in excluded:
                return False
        
        # Filtros de base
        base_filters = {
            'base_ss': 'base_seguridad_social',
            'base_prima': 'base_prima',
            'base_cesantias': 'base_cesantias',
            'base_vacaciones': 'base_vacaciones'
        }
        
        for filter_key, attr_name in base_filters.items():
            if filter_key in filters and filters[filter_key]:
                if not getattr(rule, attr_name, False):
                    return False
        
        # Otros filtros
        if 'dev_ded' in filters and rule.dev_or_ded != filters['dev_ded']:
            return False
        
        if 'min_amount' in filters and abs(line.total) < filters['min_amount']:
            return False
        
        if 'conditions' in filters and callable(filters['conditions']):
            if not filters['conditions'](rule):
                return False
        
        return True
    
    def _create_detailed_entry(self, line):
        """Crea entrada detallada desde línea"""
        rule = line.salary_rule_id
        category = rule.category_id
        
        return {
            'rule_code': rule.code,
            'rule_name': rule.name,
            'rule_id': rule.id,
            'rule': rule,
            'category': category.code if category else None,
            'category_name': category.name if category else None,
            'parent_category': category.parent_id.code if category and category.parent_id else None,
            'total': float(line.total),
            'quantity': float(line.quantity),
            'rate': float(line.rate) if hasattr(line, 'rate') else 100.0,
            'amount': float(line.amount) if hasattr(line, 'amount') else float(line.total),
            'slip_id': line.slip_id.id,
            'slip_name': line.slip_id.name,
            'date_from': line.slip_id.date_from,
            'date_to': line.slip_id.date_to,
            'source': 'payslip_line',
            'line_id': line.id,
            'leave_id': line.leave_id.id if hasattr(line, 'leave_id') and line.leave_id else None
        }
    
    def _process_rules_multi_detailed(self, rules_multi, filters):
        """Procesa rules_multi con detalle completo"""
        entries = []
        
        for code, rule_data in rules_multi.items():
            current = rule_data.get('current', {})
            rule_obj = current.get('object')
            
            if not current.get('total', 0) and not filters.get('include_zeros'):
                continue
            
            # Aplicar filtros de código
            if 'rules' in filters:
                rules = filters['rules'] if isinstance(filters['rules'], list) else [filters['rules']]
                if code not in rules:
                    continue
            
            if 'exclude_rules' in filters:
                excluded = filters['exclude_rules'] if isinstance(filters['exclude_rules'], list) else [filters['exclude_rules']]
                if code in excluded:
                    continue
            
            # Crear entrada detallada
            category = rule_obj.category_id if rule_obj else None
            
            entry = {
                'rule_code': code,
                'rule_name': rule_obj.name if rule_obj else current.get('name', code),
                'rule_id': rule_obj.id if rule_obj else None,
                'rule': rule_obj,
                'category': category.code if category else current.get('category'),
                'category_name': category.name if category else None,
                'parent_category': category.parent_id.code if category and category.parent_id else None,
                'total': float(current.get('total', 0)),
                'quantity': float(current.get('quantity', 0)),
                'rate': float(current.get('rate', 100)),
                'amount': float(current.get('amount', current.get('total', 0))),
                'source': 'rules_multi',
                'payslip_id': current.get('payslip_id'),
                'log': current.get('log', {})
            }
            
            # Verificar filtros adicionales
            if self._entry_passes_filters(entry, filters):
                entries.append(entry)
        
        return entries
    
    def _entry_passes_filters(self, entry, filters):
        """Verifica si una entrada pasa los filtros"""
        # Similar a _line_passes_filters pero para entradas
        if 'categories' in filters:
            categories = filters['categories'] if isinstance(filters['categories'], list) else [filters['categories']]
            if not (entry.get('category') in categories or entry.get('parent_category') in categories):
                return False
        
        if 'exclude_categories' in filters:
            excluded = filters['exclude_categories'] if isinstance(filters['exclude_categories'], list) else [filters['exclude_categories']]
            if entry.get('category') in excluded or entry.get('parent_category') in excluded:
                return False
        
        if 'min_amount' in filters and abs(entry.get('total', 0)) < filters['min_amount']:
            return False
        
        return True
    
    def _add_entry_to_result(self, entry, result, line=None):
        """Agrega entrada al resultado con todos los detalles"""
        result['entries'].append(entry)
        result['total'] += entry['total']
        result['quantity'] += entry['quantity']
        
        # Agrupar por regla
        rule_code = entry['rule_code']
        result['by_rule'][rule_code]['total'] += entry['total']
        result['by_rule'][rule_code]['quantity'] += entry['quantity']
        result['by_rule'][rule_code]['entries'].append(entry)
        result['by_rule'][rule_code]['name'] = entry['rule_name']
        result['by_rule'][rule_code]['category'] = entry['category']
        if line:
            result['by_rule'][rule_code]['lines'].append(line)
        if not result['by_rule'][rule_code]['rule'] and entry.get('rule'):
            result['by_rule'][rule_code]['rule'] = entry['rule']
        
        # Agrupar por categoría
        for cat_key in ['category', 'parent_category']:
            category = entry.get(cat_key)
            if category:
                result['by_category'][category]['total'] += entry['total']
                result['by_category'][category]['quantity'] += entry['quantity']
                result['by_category'][category]['entries'].append(entry)
                result['by_category'][category]['rules'].add(rule_code)
                if line:
                    result['by_category'][category]['lines'].append(line)
    
    # =====================================================
    # MÉTODOS DE SALARIO (hr_rule.py originales)
    # =====================================================
    
    def _basic(self, localdict):
        """Sueldo básico estándar"""
        return self._calculate_salary_generic(localdict, 'basic')
    
    
    def _basic002(self, localdict):
        """Sueldo básico integral"""
        return self._calculate_salary_generic(localdict, 'integral')
    
    def _basic003(self, localdict):
        """Cuota sostenimiento aprendices"""
        return self._calculate_salary_generic(localdict, 'sostenimiento')
    
    def _basic004(self, localdict):
        """Sueldo básico tiempo parcial"""
        return self._calculate_salary_generic(localdict, 'parcial')

    def _basic005(self, localdict):
        """Sueldo por día"""
        return self._calculate_salary_generic(localdict, 'por_dia')
    
    def _calculate_salary_generic(self, localdict, salary_type='basic'):
        """Método genérico para cálculo de salarios"""
        contract = localdict['contract']
        slip = localdict['slip']
        worked_days = localdict.get('worked_days', {})
        annual_parameters = localdict.get('annual_parameters')
        
        salary_configs = {
            'basic': {
                'name': 'SUELDO BASICO',
                'modalities': ['basico', 'especie', 'variable']
            },
            'integral': {
                'name': 'SUELDO BASICO INTEGRAL',
                'modalities': ['integral']
            },
            'sostenimiento': {
                'name': 'CUOTA DE SOSTENIMIENTO',
                'modalities': ['sostenimiento']
            },
            'parcial': {
                'name': 'SUELDO TIEMPO PARCIAL',
                'modalities': ['basico', 'especie', 'variable']
            },
            'por_dia': {
                'name': 'SUELDO POR DIA',
                'modalities': ['basico', 'especie', 'variable']
            }
        }
        
        config = salary_configs.get(salary_type, salary_configs['basic'])
        
        if salary_type == 'parcial':
            if not contract.parcial and contract.contract_type != 'fijo_parcial':
                return 0, 0, 0, config['name'], {'status': 'not_applicable'}, {}
        
        if contract.subcontract_type:
            return 0, 0, 0, config['name'], {'status': 'subcontract'}, {}
        
        if salary_type not in ['parcial', 'por_dia'] and contract.modality_salary not in config['modalities']:
            return 0, 0, 0, config['name'], {'status': 'invalid_modality'}, {}
        
        if worked_days.WORK100:
            worked = worked_days.WORK100
            total_days = float(worked.number_of_days)
            total_hours = float(worked.number_of_hours)
        else:
            total_days = 30.0
            total_hours = 240.0
        
        # Para sueldo por día, respetar WORK100 porque ya descuenta ausencias,
        # días fuera de contrato y otros ajustes de nómina.
        if salary_type == 'por_dia':
            dias_calculo = localdict.get('dias_calculo', 0)
            if slip and hasattr(slip, 'manual_days') and slip.manual_days:
                dias_calculo = float(slip.manual_days)
            if not dias_calculo:
                dias_calculo = total_days
            total_days = dias_calculo
        
        # Calcular salario considerando cambios y tipo
        wage = float(contract.wage)
        
        # Aplicar factor parcial si corresponde
        if salary_type == 'parcial':
            factor = contract.factor if hasattr(contract, 'factor') and contract.factor else 0.5
            wage = wage * factor
            percentage = int(factor * 100)
            config['name'] = f'SUELDO TIEMPO PARCIAL ({percentage}%)'
        elif salary_type == 'por_dia':
            config['name'] = f'SUELDO POR DIA ({int(total_days)} días)'
        
        # Buscar cambios de salario en el periodo
        cambios = contract.change_wage_ids.filtered(
            lambda c: slip.date_from <= c.date_start <= slip.date_to
        ) if slip and hasattr(contract, 'change_wage_ids') else False
        
        if cambios:
            # Hay cambio de salario en el periodo
            change = cambios[0]
            change_day = change.date_start
            new_wage = float(change.wage)
            
            # Aplicar factor parcial al nuevo salario también
            if salary_type == 'parcial':
                new_wage = new_wage * factor
            
            days_before = days360(slip.date_from, change_day - timedelta(days=1))
            days_after = days360(change_day, slip.date_to)
            
            rate_old = wage / 30
            rate_new = new_wage / 30
            
            total_pay = (rate_old * days_before) + (rate_new * days_after)
            
            log_data = {
                'has_changes': True,
                'old_wage': wage,
                'new_wage': new_wage,
                'change_date': change_day,
                'days_before': days_before,
                'days_after': days_after,
                'total': total_pay,
                'salary_type': salary_type
            }
            
            if salary_type == 'parcial':
                log_data['factor'] = factor
        else:
            # Sin cambios
            rate = wage / 30
            total_pay = rate * total_days
            
            log_data = {
                'has_changes': False,
                'wage': wage,
                'days': total_days,
                'rate': rate,
                'total': total_pay,
                'salary_type': salary_type
            }
            
            if salary_type == 'parcial':
                log_data['factor'] = factor
        
        return float(total_pay / total_days) if total_days > 0 else 0, total_days, 100, config['name'], log_data, {}
    # =====================================================
    # MÉTODOS DE AUXILIOS (hr_rule.py originales)
    # =====================================================
    
    def _aux000(self, localdict):
        """Auxilio de transporte"""
        return self._calculate_auxilio_generic(localdict, 'transporte', 'AUX000')
    
    def _aux00c(self, localdict):
        """Auxilio de conectividad"""
        return self._calculate_auxilio_generic(localdict, 'conectividad', 'AUX00C')

    def _is_apprentice_lectiva(self, contract=None, employee=None):
        """Determina si el empleado/contrato corresponde a aprendiz en etapa lectiva."""
        if not contract:
            return False

        ctype = contract.contract_type_id
        is_apprentice = bool(
            ctype and (getattr(ctype, 'is_apprenticeship', False) or getattr(ctype, 'contract_category', False) == 'aprendizaje')
        )
        if not is_apprentice:
            return False

        stage = getattr(contract, 'apprentice_stage', False)
        if stage == 'lectiva':
            return True

        if employee and getattr(employee, 'tipo_coti_id', False):
            return employee.tipo_coti_id.code == '12'

        return False
    
    def _calculate_auxilio_generic(self, localdict, tipo_auxilio, codigo_auxilio):
        """Método genérico para auxilios"""
        contract = localdict['contract']
        employee = localdict.get('employee')
        slip = localdict['slip']
        annual_parameters = localdict.get('annual_parameters')
        worked_days = localdict.get('worked_days', {})
        
        # Configuración
        auxilio_configs = {
            'transporte': {
                'name': 'AUXILIO DE TRANSPORTE',
                'monthly_value': annual_parameters.transportation_assistance_monthly if annual_parameters else 0,
                'salary_limit': 2 * annual_parameters.smmlv_monthly if annual_parameters else 0,
                'check_field': 'not_pay_auxtransportation'
            },
            'conectividad': {
                'name': 'AUXILIO DE CONECTIVIDAD',
                'monthly_value': annual_parameters.value_auxilio_conectividad if annual_parameters else 0,
                'salary_limit': annual_parameters.top_max_auxilio_conectividad if annual_parameters else 0,
                'check_field': 'remote_work_allowance'
            }
        }
        
        config = auxilio_configs[tipo_auxilio]
        
        # Validaciones básicas
        if tipo_auxilio == 'transporte' and contract.contract_type_id and not contract.contract_type_id.has_auxilio_transporte:
            return 0, 0, 0, config['name'], {'status': 'disabled_by_contract_type'}, {}

        if tipo_auxilio == 'transporte' and contract.modality_aux == 'no':
            return 0, 0, 0, config['name'], {'status': 'disabled_by_modality_aux'}, {}

        if tipo_auxilio == 'transporte' and contract.not_pay_auxtransportation:
            return 0, 0, 0, config['name'], {'status': 'disabled'}, {}

        if tipo_auxilio == 'transporte' and self._is_apprentice_lectiva(contract, employee):
            return 0, 0, 0, config['name'], {'status': 'disabled_apprentice_lectiva'}, {}
        
        if tipo_auxilio == 'conectividad' and not contract.remote_work_allowance:
            return 0, 0, 0, config['name'], {'status': 'disabled'}, {}
        
        # Calcular días
        dias = 30
        if hasattr(worked_days, 'WORK100'):
            dias = worked_days.WORK100.number_of_days
        if (
            tipo_auxilio == 'transporte'
            and contract.full_auxtransportation_settlement
            and slip.struct_id.process == 'contrato'
        ):
            # En liquidación, forzar valor mensual completo
            dias = 30
        
        # Calcular valor
        daily_value = config['monthly_value'] / 30
        total = daily_value * dias
        
        # Validar tope salarial
        if not contract.not_validate_top_auxtransportation:
            salary_base = self._get_salary_base_for_aux(localdict)
            if salary_base > config['salary_limit']:
                return 0, 0, 0, config['name'], {'status': 'exceeds_limit', 'limit': config['salary_limit']}, {}
        
        log_data = {
            'daily_value': daily_value,
            'days': dias,
            'total': total,
            'status': 'success'
        }
        
        return daily_value, dias, 100, config['name'], log_data, {}
    
    def _get_salary_base_for_aux(self, localdict):
        """Obtiene base salarial para validación de auxilio"""
        contract = localdict['contract']
        
        # Obtener salario básico del mes
        basic_data = self._get_period_data(
            localdict,
            periods=['current'],
            filters={'categories': 'BASIC'},
            include_multi=True,
            return_type='total'
        )
        
        if contract.only_wage == 'wage':
            return contract.wage
        elif contract.only_wage == 'wage_dev':
            dev_data = self._get_period_data(
                localdict,
                periods=['current'],
                filters={'categories': 'DEV_SALARIAL'},
                return_type='total'
            )
            return contract.wage + (dev_data - basic_data)
        else:
            return basic_data
    
    # =====================================================
    # MÉTODOS DE HORAS EXTRAS (hr_rule.py originales)
    # =====================================================
    
    def _heyrec001(self, localdict):
        """Horas extra diurnas"""
        return self._compute_overtime_generic(localdict, 'HEYREC001', 125.0, 'overtime_ext_d')
    
    def _heyrec002(self, localdict):
        """Horas extra diurnas dominical/festiva"""
        return self._compute_overtime_generic(localdict, 'HEYREC002', 200.0, 'overtime_eddf')
    
    def _heyrec003(self, localdict):
        """Horas extra nocturna"""
        return self._compute_overtime_generic(localdict, 'HEYREC003', 175.0, 'overtime_ext_n')
    
    def _heyrec004(self, localdict):
        """Horas recargo festivo"""
        return self._compute_overtime_generic(localdict, 'HEYREC004', 110.0, 'overtime_rndf')
    
    def _heyrec005(self, localdict):
        """Horas recargo nocturno"""
        return self._compute_overtime_generic(localdict, 'HEYREC005', 35.0, 'overtime_rn')
    
    def _compute_overtime_generic(self, localdict, rule_code, percentage, field_name):
        """Método genérico para horas extras"""
        contract = localdict['contract']
        employee = localdict['employee']
        slip = localdict['slip']
        
        if contract.not_pay_overtime:
            return 0, 0, 0, f'HE {rule_code}', {'status': 'disabled'}, {}
        
        # Buscar registros de horas extras
        overtime_records = self.env['hr.overtime'].search([
            ('employee_id', '=', employee.id),
            ('date', '>=', slip.date_from),
            ('date_end', '<=', slip.date_to)
        ])
        
        total_hours = 0
        total_value = 0
        details = []
        
        for overtime in overtime_records:
            hours = getattr(overtime, field_name, 0)
            if hours > 0:
                # Calcular valor
                base_hours = 240  # Por defecto
                hourly_rate = contract.wage / base_hours
                value = hourly_rate * (percentage / 100) * hours
                
                total_hours += hours
                total_value += value
                
                details.append({
                    'date': overtime.date,
                    'hours': hours,
                    'value': value
                })
        
        if total_hours == 0:
            return 0, 0, percentage, f'HE {rule_code}', {'status': 'no_hours'}, {}
        
        rate = total_value / total_hours if total_hours > 0 else 0
        
        log_data = {
            'percentage': percentage,
            'total_hours': total_hours,
            'total_value': total_value,
            'details': details
        }
        
        return rate, total_hours, percentage, f'HE {rule_code}', log_data, {}
    
    # =====================================================
    # MÉTODOS DE SEGURIDAD SOCIAL (hr_rule.py originales)
    # =====================================================
    
    def _ssocial001(self, localdict):
        """Salud empleado"""
        return self._calculate_social_security_generic(
            localdict, 'salud', 'value_porc_health_employee', 'SSOCIAL001'
        )
    
    def _ssocial002(self, localdict):
        """Pensión empleado"""
        return self._calculate_social_security_generic(
            localdict, 'pension', 'value_porc_pension_employee', 'SSOCIAL002'
        )
    
    def _ssocial003(self, localdict):
        """Fondo de solidaridad"""
        return self._calculate_solidarity_fund(localdict)
    
    def _ssocial004(self, localdict):
        """Fondo de subsistencia"""
        return self._calculate_subsistence_fund(localdict)
    
    def _calculate_social_security_generic(self, localdict, tipo_ss, param_field, rule_code):
        """Método genérico para seguridad social"""
        contract = localdict['contract']
        employee = localdict['employee']
        annual_parameters = localdict.get('annual_parameters')
        contract_type = contract.contract_type_id

        # Regla negocio: aprendiz etapa lectiva no aporta salud ni pensión.
        if self._is_apprentice_lectiva(contract, employee):
            return 0, 0, 0, f'{tipo_ss} empleado', {'status': 'apprentice_lectiva_exempt'}, {}

        # Enlace directo con tipo de contrato.
        if tipo_ss == 'salud' and contract_type and not contract_type.has_salud:
            return 0, 0, 0, f'{tipo_ss} empleado', {'status': 'disabled_by_contract_type'}, {}
        if tipo_ss == 'pension' and contract_type and not contract_type.has_pension:
            return 0, 0, 0, f'{tipo_ss} empleado', {'status': 'disabled_by_contract_type'}, {}
        
        # Validaciones
        if employee.subtipo_coti_id:
            if tipo_ss == 'salud' and employee.subtipo_coti_id.not_contribute_eps:
                return 0, 0, 0, f'{tipo_ss} empleado', {'status': 'no_contribution'}, {}
            if tipo_ss == 'pension' and employee.subtipo_coti_id.not_contribute_pension:
                return 0, 0, 0, f'{tipo_ss} empleado', {'status': 'no_contribution'}, {}
        
        # Obtener IBC
        ibc_data = self._get_period_data(
            localdict,
            periods=['current'],
            filters={'rules': 'IBD'},
            include_multi=True
        )
        
        ibc = ibc_data['total'] if ibc_data['total'] else contract.wage
        
        # Obtener porcentaje
        porcentaje = getattr(annual_parameters, param_field, 0) if annual_parameters else 4
        
        # Verificar pagos previos en el mes
        prev_payments = self._get_period_data(
            localdict,
            periods=['current'],
            filters={'rules': rule_code},
            include_multi=False,
            return_type='total'
        )
        
        base = ibc - prev_payments
        valor = base * (porcentaje / 100)
        
        log_data = {
            'ibc': ibc,
            'porcentaje': porcentaje,
            'prev_payments': prev_payments,
            'base': base,
            'valor': valor
        }
        
        return base, -1, porcentaje, f'{tipo_ss} empleado', log_data, {}
    
    def _calculate_solidarity_fund(self, localdict):
        """Calcula fondo de solidaridad"""
        annual_parameters = localdict.get('annual_parameters')
        
        # Obtener IBC
        ibc, dias, _, _, log_data, _ = self._ibd(localdict, calculate_for='FONDOS')
        ibc = ibc * dias
        
        smmlv = annual_parameters.smmlv_monthly if annual_parameters else 0
        
        if ibc <= 4 * smmlv:
            return 0, 0, 0, 'Fondo solidaridad', {'status': 'below_limit', 'ibc': ibc, 'limit': 4 * smmlv}, {}
        
        porcentaje = 0.5
        valor = ibc * (porcentaje / 100)
        
        log_data = {
            'ibc': ibc,
            'smmlv_range': ibc / smmlv,
            'porcentaje': porcentaje,
            'valor': valor
        }
        
        return ibc, -1, porcentaje, 'Fondo solidaridad', log_data, {}
    
    def _calculate_subsistence_fund(self, localdict):
        """Calcula fondo de subsistencia"""
        annual_parameters = localdict.get('annual_parameters')
        
        # Obtener IBC
        ibc, dias, _, _, log_data, _ = self._ibd(localdict, calculate_for='FONDOS')
        ibc = ibc * dias
        
        smmlv = annual_parameters.smmlv_monthly if annual_parameters else 0
        
        # Determinar porcentaje según rango
        if ibc <= 4 * smmlv:
            porcentaje = 0.0
        elif ibc <= 16 * smmlv:
            porcentaje = 0.5
        elif ibc <= 17 * smmlv:
            porcentaje = 0.7
        elif ibc <= 18 * smmlv:
            porcentaje = 0.9
        elif ibc <= 19 * smmlv:
            porcentaje = 1.1
        elif ibc <= 20 * smmlv:
            porcentaje = 1.3
        else:
            porcentaje = 1.5
        
        if porcentaje == 0:
            return 0, 0, 0, 'Fondo subsistencia', {'status': 'below_limit', 'ibc': ibc}, {}
        
        valor = ibc * (porcentaje / 100)
        
        log_data = {
            'ibc': ibc,
            'smmlv_range': ibc / smmlv,
            'porcentaje': porcentaje,
            'valor': valor
        }
        
        return ibc, -1, porcentaje, 'Fondo subsistencia', log_data, {}
    
    # =====================================================
    # MÉTODOS DE IBC/IBD (hr_rule_ibd.py originales)
    # =====================================================
    
    def _ibd(self, localdict, calculate_for='IBC'):
        """Cálculo de IBC/IBD completo con procesamiento de vacaciones"""
        contract = localdict['contract']
        slip = localdict['slip']
        annual_parameters = localdict.get('annual_parameters')
        
        # Inicializar estructura de datos IBC
        _ibd = {
            'METADATA': {
                'fecha_calculo': datetime.now(),
                'smmlv': annual_parameters.smmlv_monthly if annual_parameters else 0,
                'tipo_calculo': calculate_for,
            },
            'CONCEPTOS': {
                'salariales': {},
                'no_salariales': {},
                'vacaciones': {},
                'ausencias': {},
                'incapacidades': {},
            },
            'CALCULOS': {},
            'VALIDACIONES': {
                'aplico_minimo': False,
                'aplico_maximo': False,
                'uso_ibc_anterior': False,
            },
            'MES_ANTERIOR': {},
            'NOVEDADES': [],
        }
        
        # Validación aprendices
        if contract.contract_type == 'aprendizaje':
            _ibd['VALIDACIONES']['es_aprendiz'] = True
            localdict['ibd_data'] = _ibd
            return 0, 0, 100, 'IBC Aprendizaje', _ibd, {}
        
        # 1. Obtener días trabajados
        worked_data = self._calculate_worked_days(slip, localdict)
        dias_trabajados = worked_data['total_days']
        _ibd['CALCULOS']['dias_trabajados'] = dias_trabajados
        
        # 2. Recopilar ausencias
        all_absences = self._collect_all_absences_unified(slip, contract, localdict)
        
        # 3. Recopilar conceptos normales
        all_concepts = self._collect_all_normal_concepts(slip, contract, localdict, all_absences)
        
        # 4. Obtener IBC mes anterior si hay ausencias con liquidar_con_base
        daily_rate = 0
        if any(abs_data.get('liquidar_con_base') for abs_data in all_absences.values()):
            prev_ibc_data = self._calculate_prev_month_ibc_unified(contract, localdict, slip)
            daily_rate = prev_ibc_data['tarifa_diaria']
            _ibd['MES_ANTERIOR'] = prev_ibc_data
            _ibd['VALIDACIONES']['uso_ibc_anterior'] = True
        
        # 5. Procesar todos los datos
        processing_result = self._process_all_data(all_absences, all_concepts, daily_rate, slip, _ibd)
        
        # 6. Calcular IBC final con regla del 40%
        final_calc = self._calculate_final_ibc(
            processing_result, annual_parameters, calculate_for, localdict, _ibd
        )
        
        # 7. Calcular valor día
        day_value_info = self._calculate_day_value(
            final_calc['ibc_final'],
            dias_trabajados,
            worked_data.get('total_hours', 0),
            worked_data.get('wage_type', 'monthly'),
            annual_parameters
        )
        
        # Actualizar estructura con cálculos finales
        _ibd['CALCULOS'].update({
            'base_salarial': processing_result['totales']['base_salarial'],
            'base_no_salarial': processing_result['totales']['base_no_salarial'],
            'total_vacaciones': processing_result['totales']['total_vacaciones'],
            'ausencias_no_remuneradas_dias': processing_result['ausencias_no_remuneradas_days'],
            'dias_ibc': dias_trabajados - processing_result['ausencias_no_remuneradas_days'],
            **final_calc,
            **day_value_info
        })
        
        # Guardar en localdict
        localdict['ibd_data'] = _ibd
        
        nombre = f'IBC - Base: ${final_calc["ibc_final"]:,.0f}'
        
        return (
            day_value_info['valor_dia'],
            dias_trabajados,
            100,
            nombre,
            _ibd,
            {}
        )
    
    def _calculate_worked_days(self, slip, localdict):
        """Calcula días y horas trabajadas"""
        result = {
            'total_days': 30.0,
            'total_hours': 0.0,
            'wage_type': 'monthly'
        }
        
        if slip:
            if slip.struct_type_id:
                result['wage_type'] = slip.struct_type_id.wage_type or 'monthly'
            
            # Buscar en worked_days_line_ids
            work100_lines = slip.worked_days_line_ids.filtered(lambda x: x.code == 'WORK100')
            for wd in work100_lines:
                result['total_days'] = float(wd.number_of_days or 0)
                if result['wage_type'] == 'hourly':
                    result['total_hours'] = float(wd.number_of_hours or 0)
        
        # Agregar días de current_month
        if localdict.get("current_month"):
            payslip_ids = list(localdict["current_month"])
            if payslip_ids:
                payslips = self.env['hr.payslip'].browse(payslip_ids)
                for ps in payslips:
                    work100_lines = ps.worked_days_line_ids.filtered(lambda x: x.code == 'WORK100')
                    for wd in work100_lines:
                        days_to_add = float(wd.number_of_days or 0)
                        if days_to_add > 0:
                            result['total_days'] += days_to_add
                        if result['wage_type'] == 'hourly':
                            result['total_hours'] += float(wd.number_of_hours or 0)
        
        return result
    
    def _collect_all_absences_unified(self, slip, contract, localdict):
        """Recopila todas las ausencias de manera unificada"""
        temp_dict = {}
        
        slip_ids = []
        if slip:
            slip_ids.append(slip.id)
        if localdict.get("current_month"):
            slip_ids.extend(list(localdict["current_month"]))
        
        if not slip_ids:
            return {}
        
        domain = [
            ('payslip_id', 'in', slip_ids),
            ('state', 'in', ['validated', 'paid']),
            ('leave_id.state', 'in', ('validate', 'validate1')),
            ('contract_id', '=', contract.id)
        ]
        
        leave_lines = self.env['hr.leave.line'].search(domain, order='date, id')
        
        for ll in leave_lines:
            if not ll.leave_id or not ll.rule_id:
                continue
            
            # Excluir reglas especiales
            if ll.rule_id.code in {"AUX001", "AUX00C", "SSOCIAL003", "SSOCIAL004", "IBD", "IBC", "IBF"}:
                continue
            
            composite_key = (ll.leave_id.id, ll.rule_id.id)
            
            if composite_key not in temp_dict:
                leave_type = ll.leave_id.holiday_status_id
                
                temp_dict[composite_key] = {
                    'name': ll.leave_id.name,
                    'rule_name': ll.rule_id.name,
                    'rule_code': ll.rule_id.code,
                    'rule_id': ll.rule_id,
                    'total_days': 0,
                    'total_amount': 0,
                    'leave_type': leave_type,
                    'leave_type_name': leave_type.name if leave_type else 'N/A',
                    'date_from': ll.leave_id.date_from.date() if ll.leave_id.date_from else ll.date,
                    'date_to': ll.leave_id.date_to.date() if ll.leave_id.date_to else ll.date,
                    'leave_id': ll.leave_id,
                    'novelty': leave_type.novelty if leave_type and hasattr(leave_type, 'novelty') else None,
                    'is_unpaid': bool(leave_type.unpaid_absences) if leave_type and hasattr(leave_type, 'unpaid_absences') else False,
                    'liquidar_con_base': bool(ll.rule_id.liquidar_con_base),
                    'base_seguridad_social': bool(ll.rule_id.base_seguridad_social),
                    'category_code': self._get_category_code(ll.rule_id),
                    'individual_entries': []
                }
            
            # Acumular datos
            data = temp_dict[composite_key]
            days = float(ll.days_payslip or ll.days_assigned or 0)
            amount = float(ll.amount or 0)
            
            data['total_days'] += days
            data['total_amount'] += amount
            
            data['individual_entries'].append({
                'date': ll.date,
                'days': days,
                'amount': amount,
                'payslip_id': ll.payslip_id.id
            })
        
        # Convertir a diccionario final
        absence_dict = {}
        for (leave_id, rule_id), data in temp_dict.items():
            composite_key = f"{leave_id}_{rule_id}"
            absence_dict[composite_key] = data
        
        return absence_dict
    
    def _collect_all_normal_concepts(self, slip, contract, localdict, absence_dict):
        """Recopila conceptos normales (no ausencias)"""
        normal_concepts = {}

        # Agregar reglas del slip actual desde localdict['rules'] (Odoo 19)
        rules = localdict.get('rules', {})
        for code, rule_data in rules.items():
            rule_obj = getattr(rule_data, 'rule', None)
            if not rule_obj:
                continue
            rule_code = rule_obj.code or code
            if rule_code in ['AUX001', 'AUX00C', 'IBD', 'IBC', 'IBF']:
                continue

            total = getattr(rule_data, 'total', 0) or 0
            if total == 0:
                continue

            quantity = getattr(rule_data, 'quantity', 0) or 0
            category_code = self._get_category_code(rule_obj)
            if rule_code not in normal_concepts:
                normal_concepts[rule_code] = {
                    'rule_id': rule_obj,
                    'rule_name': rule_obj.name or rule_code,
                    'rule_code': rule_code,
                    'category_code': category_code,
                    'total_amount': 0,
                    'total_quantity': 0,
                    'base_seguridad_social': bool(rule_obj.base_seguridad_social),
                    'entries_by_date': []
                }

            normal_concepts[rule_code]['total_amount'] += total
            normal_concepts[rule_code]['total_quantity'] += quantity
            normal_concepts[rule_code]['entries_by_date'].append({
                'date': slip.date_from if slip else datetime.now().date(),
                'amount': total,
                'source': 'localdict_rules'
            })
        
        # Obtener de current_month
        if localdict.get("current_month"):
            current_data = self._get_period_data(
                localdict,
                periods=['current'],
                filters={
                    'exclude_rules': ['AUX001', 'AUX00C', 'IBD', 'IBC', 'IBF']
                }
            )
            
            for rule_code, rule_data in current_data['by_rule'].items():
                if rule_data['total'] != 0:
                    normal_concepts[rule_code] = {
                        'rule_id': rule_data.get('rule'),
                        'rule_name': rule_data.get('name', rule_code),
                        'rule_code': rule_code,
                        'category_code': rule_data.get('category'),
                        'total_amount': rule_data['total'],
                        'total_quantity': rule_data['quantity'],
                        'base_seguridad_social': bool(rule_data.get('rule').base_seguridad_social) if rule_data.get('rule') else False,
                        'entries_by_date': rule_data['entries']
                    }
        
        # Obtener de rules_multi
        if localdict.get('rules_multi'):
            for code, rule_data in localdict['rules_multi'].items():
                if code in ['AUX001', 'AUX00C', 'IBD', 'IBC', 'IBF']:
                    continue
                
                current = rule_data.get('current', {})
                rule_obj = current.get('object')
                
                if current.get('total', 0) != 0:
                    if code not in normal_concepts:
                        normal_concepts[code] = {
                            'rule_id': rule_obj,
                            'rule_name': rule_obj.name if rule_obj else code,
                            'rule_code': code,
                            'category_code': self._get_category_code(rule_obj) if rule_obj else current.get('category'),
                            'total_amount': 0,
                            'total_quantity': 0,
                            'base_seguridad_social': bool(rule_obj.base_seguridad_social) if rule_obj else False,
                            'entries_by_date': []
                        }
                    
                    normal_concepts[code]['total_amount'] += current.get('total', 0)
                    normal_concepts[code]['total_quantity'] += current.get('quantity', 0)
                    normal_concepts[code]['entries_by_date'].append({
                        'date': slip.date_from if slip else datetime.now().date(),
                        'amount': current.get('total', 0),
                        'source': 'rules_multi'
                    })
        
        return normal_concepts
    
    def _process_all_data(self, all_absences, all_concepts, daily_rate, slip, _ibd):
        """Procesa todos los datos recopilados"""
        result = {
            'totales': {
                'base_salarial': 0.0,
                'base_no_salarial': 0.0,
                'total_vacaciones': 0.0,
                'vac_mes_actual': 0.0,
                'vac_mes_anterior': 0.0,
                'vacaciones_vdi_current': 0.0,
                'vacaciones_vdi_previous': 0.0,
                'vacaciones_vco_current': 0.0,
                'vacaciones_vco_previous': 0.0,
            },
            'conceptos_tabla': [],
            'ausencias_no_remuneradas_days': 0.0,
            'force_ibc': False
        }
        
        # 1. Procesar conceptos normales
        for code, concept in all_concepts.items():
            amount = concept['total_amount']
            
            if amount == 0:
                continue
            
            if self._is_non_salary(concept.get('rule_id'), concept.get('category_code')):
                tipo = 'NO SALARIAL'
                result['totales']['base_no_salarial'] += amount
            elif self._is_salary_base(concept.get('rule_id'), concept.get('category_code')):
                tipo = 'SALARIAL'
                result['totales']['base_salarial'] += amount
            else:
                continue
            
            result['conceptos_tabla'].append({
                'tipo': tipo,
                'nombre': concept['rule_name'],
                'codigo': concept['rule_code'],
                'valor_original': amount,
                'valor_ibc': amount,
                'cantidad': concept['total_quantity']
            })
            
            # Agregar a estructura IBC
            tipo_concepto = 'no_salariales' if tipo == 'NO SALARIAL' else 'salariales'
            _ibd['CONCEPTOS'][tipo_concepto][code] = {
                'nombre': concept['rule_name'],
                'cantidad': concept['total_quantity'],
                'valor_original': amount,
                'valor_calculado': amount,
                'categoria': concept.get('category_code'),
                'es_base': True
            }
        
        # 2. Procesar ausencias
        for key, absence in all_absences.items():
            processed = self._process_single_absence(absence, daily_rate, slip, _ibd)
            
            # Actualizar totales
            result['totales']['base_salarial'] += processed.get('base_salarial', 0)
            result['ausencias_no_remuneradas_days'] += processed.get('dias_no_remunerados', 0)
            
            if processed.get('force_ibc'):
                result['force_ibc'] = True
            
            # Procesar vacaciones
            if processed.get('tipo_vacacion'):
                self._update_vacation_totals(result['totales'], processed)
            
            if processed.get('tabla_entry'):
                result['conceptos_tabla'].append(processed['tabla_entry'])
            
            if processed.get('novedad'):
                _ibd['NOVEDADES'].append(processed['novedad'])
        
        return result
    
    def _process_single_absence(self, absence_data, daily_rate, slip, _ibd):
        """Procesa una ausencia individual"""
        result = {
            'base_salarial': 0,
            'dias_no_remunerados': 0,
            'force_ibc': False,
            'tabla_entry': None,
        }
        
        rule = absence_data['rule_id']
        amount = absence_data['total_amount']
        days = absence_data['total_days']
        novelty = absence_data.get('novelty')
        is_unpaid = absence_data.get('is_unpaid')
        
        nombre = absence_data['rule_name']
        valor_original = amount
        valor_ibc = amount
        tipo = 'AUSENCIA'
        
        # Crear novedad base
        novedad = {
            'fecha': absence_data.get('date_from'),
            'concepto': nombre,
            'dias': days,
            'valor_original': valor_original
        }
        
        if is_unpaid:
            # Ausencia no remunerada
            result['dias_no_remunerados'] = days
            valor_ibc = 0
            tipo = 'AUSENCIA NO REMUNERADA'
            novedad['tipo'] = tipo
            
        elif novelty in ['vdi', 'vco']:
            # Vacaciones
            vac_data = self._process_vacation(
                rule, amount, days, absence_data.get('leave_type'),
                absence_data.get('date_from'), False, novelty, daily_rate, slip
            )
            
            result['tipo_vacacion'] = novelty
            result['vacacion_data'] = vac_data
            tipo = vac_data['tipo']
            valor_ibc = vac_data['valor_ibc']
            
            # Agregar a conceptos de vacaciones
            _ibd['CONCEPTOS']['vacaciones'][f"{novelty}_{absence_data.get('leave_id').id}"] = {
                'nombre': nombre,
                'cantidad': vac_data['dias_efectivos'],
                'valor_original': amount,
                'valor_calculado': valor_ibc,
                'dias': vac_data['dias_efectivos'],
                'categoria': absence_data.get('category_code'),
                'es_base': vac_data['hace_base']
            }
            
        elif absence_data.get('liquidar_con_base') and daily_rate > 0:
            # Ausencia con IBC anterior
            result['force_ibc'] = True
            
            if novelty in ['ige', 'irl', 'lma']:
                # Incapacidad
                tipo = 'INCAPACIDAD'
                result['base_salarial'] = valor_ibc
                
                _ibd['CONCEPTOS']['incapacidades'][f"INC_{absence_data.get('leave_id').id}"] = {
                    'nombre': nombre,
                    'cantidad': days,
                    'valor_original': amount,
                    'valor_calculado': valor_ibc,
                    'dias': days,
                    'categoria': absence_data.get('category_code'),
                    'es_base': True
                }
            else:
                # Otra ausencia con IBC
                valor_ibc = days * daily_rate
                tipo = 'AUSENCIA - IBC ANTERIOR'
                result['base_salarial'] = valor_ibc
                
                _ibd['CONCEPTOS']['ausencias'][f"AUS_IBC_{absence_data.get('leave_id').id}"] = {
                    'nombre': f'{nombre} (IBC anterior)',
                    'cantidad': days,
                    'valor_original': amount,
                    'valor_calculado': valor_ibc,
                    'dias': days,
                    'categoria': absence_data.get('category_code'),
                    'es_base': True
                }
        else:
            # Ausencia normal
            result['base_salarial'] = amount
        
        # Crear entrada para tabla
        result['tabla_entry'] = {
            'tipo': tipo,
            'nombre': nombre,
            'codigo': absence_data.get('rule_code'),
            'valor_original': valor_original,
            'valor_ibc': valor_ibc,
            'cantidad': days
        }
        
        result['novedad'] = novedad
        
        return result
    
    def _process_vacation(self, rule, amount, days, leave_type, start_date,
                         cross_month, novelty, daily_rate, slip):
        """Procesa vacaciones"""
        hace_base = True
        if novelty == 'vco':
            hace_base = bool(rule.base_seguridad_social)
        
        dias_efectivos = days
        
        # Calcular días efectivos si cruza mes
        if cross_month and start_date and slip:
            fecha_fin_vacacion = start_date + relativedelta(days=int(days) - 1)
            
            if fecha_fin_vacacion < slip.date_from:
                dias_efectivos = 0
            elif start_date < slip.date_from:
                if fecha_fin_vacacion <= slip.date_to:
                    dias_efectivos = (fecha_fin_vacacion - slip.date_from).days + 1
                else:
                    dias_efectivos = (slip.date_to - slip.date_from).days + 1
        
        valor_ibc = dias_efectivos * daily_rate if hace_base else 0
        
        tipo = 'VACACIONES DISFRUTADAS' if novelty == 'vdi' else 'VACACIONES COMPENSADAS'
        
        return {
            'tipo': tipo,
            'valor_original': amount,
            'valor_ibc': valor_ibc,
            'hace_base': hace_base,
            'dias_efectivos': dias_efectivos,
            'cruza_mes': cross_month
        }
    
    def _update_vacation_totals(self, totales, processed):
        """Actualiza totales de vacaciones"""
        vac_data = processed['vacacion_data']
        novelty = processed['tipo_vacacion']
        
        totales['total_vacaciones'] += vac_data['valor_original']
        
        if novelty == 'vdi':
            if vac_data['cruza_mes']:
                totales['vacaciones_vdi_previous'] += vac_data['valor_ibc']
                totales['vac_mes_anterior'] += vac_data['valor_original']
            else:
                totales['vacaciones_vdi_current'] += vac_data['valor_ibc']
                totales['vac_mes_actual'] += vac_data['valor_original']
        else:  # vco
            if vac_data['cruza_mes']:
                totales['vacaciones_vco_previous'] += vac_data['valor_ibc'] if vac_data['hace_base'] else 0
                totales['vac_mes_anterior'] += vac_data['valor_original']
            else:
                totales['vacaciones_vco_current'] += vac_data['valor_ibc'] if vac_data['hace_base'] else 0
                totales['vac_mes_actual'] += vac_data['valor_original']
    
    def _calculate_prev_month_ibc_unified(self, contract, localdict, slip):
        """Calcula el IBC del mes anterior"""
        prev_data = {
            'ibc': 0.0,
            'dias': 30.0,
            'tarifa_diaria': 0.0,
            'fuente': 'No disponible',
            'fecha_referencia': ''
        }
        
        if not slip:
            return prev_data
        
        mes_previo = slip.date_from - relativedelta(months=1)
        prev_data['fecha_referencia'] = mes_previo.strftime('%Y-%m')
        
        # Buscar en seguridad social
        ss = self.env['hr.payroll.social.security'].search([
            ('year', '=', mes_previo.year),
            ('month', '=', str(mes_previo.month)),
            ('state', 'in', ['done', 'accounting'])
        ], limit=1)
        
        if ss:
            ss_line = ss.executing_social_security_ids.filtered(
                lambda x: x.contract_id.id == contract.id
            )
            for linea in ss_line:
                valor_base = float(linea.nValorBaseSalud or 0)
                if valor_base > 0:
                    dias_ss = float(linea.nDiasLiquidados or 30)
                    prev_data['ibc'] = valor_base
                    prev_data['dias'] = dias_ss
                    prev_data['fuente'] = 'Seguridad Social'
                    break
        
        # Si no se encontró, usar salario
        if prev_data['ibc'] == 0:
            prev_data['ibc'] = float(contract.wage or 0)
            prev_data['fuente'] = 'Salario contractual'
        
        prev_data['tarifa_diaria'] = prev_data['ibc'] / prev_data['dias'] if prev_data['dias'] > 0 else 0
        
        return prev_data
    
    def _calculate_final_ibc(self, processing_result, annual_parameters, calculate_for, localdict, _ibd):
        """Calcula el IBC final aplicando reglas del 40% y topes"""
        totales = processing_result['totales']
        
        # IBC base
        ibc_base_puro = totales['base_salarial']
        
        # IBC para cálculo del 40%
        ibc_40 = totales['base_salarial'] + totales.get('vac_actual_para_40', 0) - totales.get('vac_anterior_para_40', 0)
        
        # Remuneración total para 40%
        remuneracion_para_40 = ibc_40 + totales['base_no_salarial']
        
        # Aplicar 40%
        porcentaje_40 = annual_parameters.value_porc_statute_1395/100 if annual_parameters else 0.4
        tope_40 = remuneracion_para_40 * porcentaje_40
        excedente = max(0.0, totales['base_no_salarial'] - tope_40)
        
        # IBC base final
        ibc_base_final = totales['base_salarial'] + excedente
        ibc_sin_topes = ibc_base_final
        
        # Lógica especial para FONDOS
        fondos_prev_month = False
        vacaciones_a_incluir = 0.0
        
        if calculate_for == 'FONDOS':
            # Verificar si ya se calcularon fondos el mes anterior
            if localdict.get('before_month'):
                prev_slip_ids = list(localdict['before_month'])
                fondos_previos = self.env['hr.payslip.line'].search([
                    ('slip_id', 'in', prev_slip_ids),
                    ('salary_rule_id.code', '=', self.code),
                    ('contract_id', '=', localdict['contract'].id),
                    ('amount', '!=', 0)
                ], limit=1)
                
                if fondos_previos:
                    fondos_prev_month = True
                    _ibd['VALIDACIONES']['fondos_mes_anterior'] = True
            
            # Incluir vacaciones según corresponda
            for codigo, concepto in _ibd['CONCEPTOS']['vacaciones'].items():
                if concepto.get('es_base', False):
                    if not concepto.get('cruza_mes', False):
                        vacaciones_a_incluir += concepto['valor_calculado']
                    elif not fondos_prev_month:
                        vacaciones_a_incluir += concepto['valor_calculado']
            
            ibc_sin_topes = ibc_base_final + vacaciones_a_incluir
        
        # Aplicar topes
        smmlv = annual_parameters.smmlv_monthly if annual_parameters else 0
        ibc_max = 25.0 * smmlv
        ibc_final = min(ibc_sin_topes, ibc_max)
        
        # Actualizar validaciones
        _ibd['VALIDACIONES']['aplico_maximo'] = ibc_sin_topes > ibc_max
        _ibd['VALIDACIONES']['incluyo_vacaciones'] = vacaciones_a_incluir > 0
        
        return {
            'ibc_base_puro': ibc_base_puro,
            'ibc_40': ibc_40,
            'remuneracion_para_40': remuneracion_para_40,
            'tope_40': tope_40,
            'excedente_40': excedente,
            'ibc_base_final': ibc_base_final,
            'ibc_sin_topes': ibc_sin_topes,
            'ibc_final': ibc_final,
            'vacaciones_a_incluir': vacaciones_a_incluir,
            'fondos_prev_month': fondos_prev_month,
            'aplico_maximo': ibc_sin_topes > ibc_max,
        }
    
    def _calculate_day_value(self, ibc_final, dias_ibc, total_hours, wage_type, annual_parameters):
        """Calcula el valor día según tipo de salario"""
        if wage_type == 'hourly' and total_hours > 0:
            hours_per_day = float(annual_parameters.hours_per_day or 8) if annual_parameters else 8
            day_value = (ibc_final / total_hours) * hours_per_day
            return {
                'valor_dia': day_value,
                'tipo_calculo': 'hourly',
                'horas_trabajadas': total_hours,
                'horas_por_dia': hours_per_day
            }
        else:
            day_value = ibc_final / dias_ibc if dias_ibc > 0 else 0
            return {
                'valor_dia': day_value,
                'tipo_calculo': 'monthly'
            }
    
    def _get_category_code(self, rule):
        """Obtiene código de categoría"""
        if rule and rule.category_id:
            if rule.category_id.code:
                return rule.category_id.code
            elif rule.category_id.parent_id and rule.category_id.parent_id.code:
                return rule.category_id.parent_id.code
        return ''
    
    def _is_salary_base(self, rule, category_code=None):
        """Verifica si es base salarial"""
        # Solo reglas marcadas explícitamente
        if rule and getattr(rule, 'base_seguridad_social', False):
            return True
        return False
    
    def _is_non_salary(self, rule, category_code=None):
        """Verifica si es no salarial"""
        if category_code is None and rule:
            category_code = self._get_category_code(rule)
        
        if rule and rule.category_id:
            if rule.category_id.code == 'DEV_NO_SALARIAL':
                return True
            elif rule.category_id.parent_id and rule.category_id.parent_id.code == 'DEV_NO_SALARIAL':
                return True
        
        return category_code == 'DEV_NO_SALARIAL'
    
    # =====================================================
    # MÉTODOS DE RETENCIÓN EN LA FUENTE
    # =====================================================
    
    def _rt_met_01(self, localdict):
        """Retención en la fuente - Método ordinario"""
        return self._calculate_retention_generic(localdict, tipo='nomina')
    
    def _calculate_retention_generic(self, localdict, tipo='nomina'):
        """Método genérico para retención"""
        contract = localdict['contract']
        slip = localdict['slip']
        employee = localdict['employee']
        annual_parameters = localdict['annual_parameters']
        
        # Inicializar diccionario
        retention_data = {
            'tipo': tipo,
            'year': slip.date_to.year,
            'month': slip.date_to.month,
            'employee': {
                'id': employee.id,
                'name': employee.name,
                'document': employee.identification_id
            }
        }
        
        # Validación aprendices
        if contract.contract_type == 'aprendizaje':
            retention_data['status'] = 'no_applicable'
            localdict['retention_data'] = retention_data
            return 0, 0, 0, 'No aplica para aprendices', retention_data, {}
        
        # Determinar método según procedimiento
        if contract.retention_procedure == 'extranjero_no_residente':
            return self._calculate_retention_foreigner(localdict, retention_data)
        elif contract.retention_procedure == 'fixed':
            return self._calculate_retention_fixed(localdict, retention_data)
        else:
            return self._calculate_retention_ordinary(localdict, retention_data, tipo)
    
    def _calculate_retention_ordinary(self, localdict, retention_data, tipo_especial=None):
        """Cálculo ordinario de retención"""
        contract = localdict['contract']
        slip = localdict['slip']
        annual_parameters = localdict['annual_parameters']
        
        # Días trabajados
        dias_trabajados = 30
        worked_days = localdict.get('worked_days', {})
        if hasattr(worked_days, 'WORK100'):
            dias_trabajados = worked_days.WORK100.number_of_days
        
        retention_data['dias_trabajados'] = dias_trabajados
        
        # Proyección
        debe_proyectar = contract.proyectar_ret and slip.date_from.day <= 15
        retention_data['es_proyectado'] = debe_proyectar
        
        # Obtener ingresos
        if tipo_especial == 'prima':
            ingresos_data = self._get_period_data(
                localdict,
                periods=['current'],
                filters={'rules': 'PRIMA'},
                return_type='dict'
            )
            ingresos = {
                'total': ingresos_data['total'],
                'salario': 0,
                'dev_salarial': ingresos_data['total'],
                'dev_no_salarial': 0
            }
        else:
            # Ingresos normales
            ingresos_data = self._get_period_data(
                localdict,
                periods=['current'],
                filters={'categories': ['BASIC', 'DEV_SALARIAL', 'DEV_NO_SALARIAL']}
            )
            
            ingresos = {
                'salario': ingresos_data['by_category'].get('BASIC', {}).get('total', 0),
                'dev_salarial': ingresos_data['by_category'].get('DEV_SALARIAL', {}).get('total', 0),
                'dev_no_salarial': ingresos_data['by_category'].get('DEV_NO_SALARIAL', {}).get('total', 0),
                'total': 0
            }
            ingresos['total'] = sum(ingresos.values())
        
        retention_data['ingresos'] = ingresos
        
        # Proyectar si es necesario
        if debe_proyectar and dias_trabajados > 0:
            factor = 30.0 / dias_trabajados
            for key in ingresos:
                ingresos[key] *= factor
        
        # Aportes obligatorios
        aportes_data = self._get_period_data(
            localdict,
            periods=['current'],
            filters={'rules': ['SSOCIAL001', 'SSOCIAL002', 'SSOCIAL003', 'SSOCIAL004']}
        )
        
        aportes = {
            'salud': aportes_data['by_rule'].get('SSOCIAL001', {}).get('total', 0),
            'pension': aportes_data['by_rule'].get('SSOCIAL002', {}).get('total', 0),
            'solidaridad': aportes_data['by_rule'].get('SSOCIAL004', {}).get('total', 0),
            'subsistencia': aportes_data['by_rule'].get('SSOCIAL003', {}).get('total', 0)
        }
        aportes['total_pension'] = aportes['pension'] + aportes['solidaridad'] + aportes['subsistencia']
        
        retention_data['aportes'] = aportes
        
        # Base gravable
        ing_no_gravados = aportes['total_pension'] + aportes['salud']
        ing_base = ingresos['total'] - ing_no_gravados
        
        # Deducciones y rentas exentas (simplificado)
        deducciones = {'total': 0}
        rentas_exentas = {'total': 0, 'renta_exenta_25': 0}
        
        # Subtotales
        subtotal_ibr1 = ing_base - deducciones['total']
        subtotal_ibr2 = subtotal_ibr1 - rentas_exentas['total']
        
        # Renta exenta 25%
        renta_exenta_25 = min(
            subtotal_ibr2 * 0.25,
            annual_parameters.value_uvt * (790.0 / 12.0)
        )
        
        # Total beneficios y límites
        total_beneficios = deducciones['total'] + rentas_exentas['total'] + renta_exenta_25
        limite_40 = ing_base * 0.4
        limite_uvt = annual_parameters.value_uvt * (1340.0 / 12.0)
        beneficios_limitados = min(total_beneficios, limite_40, limite_uvt)
        
        # Base gravable final
        subtotal_ibr3 = ing_base - beneficios_limitados
        ibr_uvts = subtotal_ibr3 / annual_parameters.value_uvt if annual_parameters.value_uvt > 0 else 0
        
        retention_data['subtotales'] = {
            'ibr1': subtotal_ibr1,
            'ibr2': subtotal_ibr2,
            'ibr3': subtotal_ibr3,
            'ibr_uvts': ibr_uvts
        }
        
        # Aplicar tabla de retención
        retencion = 0
        rate = 0
        
        if contract.retention_procedure == '102':
            retencion = subtotal_ibr3 * (contract.rtf_rate / 100.0)
            rate = contract.rtf_rate
        else:
            for desde, hasta, tarifa, resta_uvt, suma_uvt in TABLA_RETENCION:
                if desde <= ibr_uvts < hasta:
                    if desde > 0:
                        retencion = (((ibr_uvts - resta_uvt) * (tarifa / 100.0)) + suma_uvt) * annual_parameters.value_uvt
                        rate = tarifa
                    break
        
        # Restar retención anterior
        retencion_anterior = self._get_period_data(
            localdict,
            periods=['current'],
            filters={'rules': 'RT_MET_01'},
            return_type='total'
        )
        
        retencion_def = max(0, retencion - abs(retencion_anterior))
        
        # Ajustar por proyección
        if debe_proyectar:
            retencion_def = retencion_def / 2.0
        
        retention_data['retencion_calculada'] = retencion
        retention_data['retencion_anterior'] = abs(retencion_anterior)
        retention_data['retencion_definitiva'] = retencion_def
        retention_data['tarifa'] = rate
        
        # Guardar en localdict
        localdict['retention_data'] = retention_data
        
        nombre = f'Retención - Base: ${subtotal_ibr3:,.0f}'
        
        return retencion_def, -1, rate, nombre, retention_data, {}
    
    def _calculate_retention_fixed(self, localdict, retention_data):
        """Retención con monto fijo"""
        contract = localdict['contract']
        valor_fijo = contract.fixed_value_retention_procedure
        
        retention_data['tipo'] = 'monto_fijo'
        retention_data['valor'] = valor_fijo
        
        localdict['retention_data'] = retention_data
        
        return valor_fijo, -1, 100, f'Retención Fijo: ${valor_fijo:,.0f}', retention_data, {}
    
    def _calculate_retention_foreigner(self, localdict, retention_data):
        """Retención extranjero no residente"""
        # Obtener ingresos totales
        ingresos_data = self._get_period_data(
            localdict,
            periods=['current'],
            filters={'categories': ['BASIC', 'DEV_SALARIAL', 'DEV_NO_SALARIAL']}
        )
        
        base = ingresos_data['total']
        retencion = base * 0.20
        
        retention_data['tipo'] = 'extranjero_no_residente'
        retention_data['base'] = base
        retention_data['tarifa'] = 20
        retention_data['retencion'] = retencion
        
        localdict['retention_data'] = retention_data
        
        return retencion, -1, 20, f'Retención Extranjero - Base: ${base:,.0f}', retention_data, {}
    
    # =====================================================
    # MÉTODOS DE PRESTACIONES SOCIALES
    # =====================================================
    
    def _prima(self, localdict):
        """Cálculo de prima de servicios"""
        return self._calculate_prestacion_generic(localdict, 'prima', 'base_prima')
    
    def _cesantias(self, localdict):
        """Cálculo de cesantías"""
        return self._calculate_prestacion_generic(localdict, 'ces', 'base_cesantias')
    
    def _int_cesantias(self, localdict):
        """Cálculo de intereses de cesantías"""
        result = self._calculate_prestacion_generic(localdict, 'int_ces', 'base_cesantias')
        
        # Ajustar para intereses (12% anual)
        val_prest = result[0]
        dias = result[1]
        
        porcentaje = (0.12 * dias) / DAYS_YEAR
        val_prest_ajustado = val_prest * porcentaje
        
        return val_prest_ajustado, dias, 100, result[3], result[4], result[5]
    
    def _calculate_prestacion_generic(self, localdict, tipo_prestacion, param_base):
        """Método genérico para prestaciones sociales"""
        contract = localdict['contract']
        slip = localdict['slip']
        annual_parameters = localdict.get('annual_parameters')
        
        # Determinar periodo
        if localdict.get('rule', {}).get('code') in ('CES_YEAR', 'INTCES_YEAR'):
            year = slip.date_to.year - 1
            d0 = date(year, 1, 1)
            d1 = date(year, 12, 31)
            if contract.date_start and contract.date_start > d0:
                d0 = contract.date_start
        else:
            d0 = slip.date_from
            d1 = slip.date_to
        
        # Calcular días
        plain = days360(d0, d1)
        
        # Obtener suspensiones no remuneradas
        leave_lines = self.env['hr.leave.line'].search([
            ('leave_id.employee_id', '=', contract.employee_id.id),
            ('leave_id.state', '=', 'validate'),
            ('leave_id.unpaid_absences', '=', True),
            ('date', '<=', d1),
            ('date', '>=', d0)
        ])
        
        susp = sum(line.days_payslip for line in leave_lines)
        eff = max(plain - susp, 0)
        
        # Obtener salario base
        wage = contract.wage
        
        # Obtener componentes variables
        base_data = self._get_period_data(
            localdict,
            periods=['current'],
            filters={param_base: True}
        )
        
        total_var = base_data['total']
        
        # Calcular auxilio transporte
        aux_trans = 0
        if contract.modality_aux == 'basico':
            salary_validation = self._get_salary_base_for_aux(localdict)
            if salary_validation <= 2 * annual_parameters.smmlv_monthly:
                aux_trans = annual_parameters.transportation_assistance_monthly
        
        # Base de cálculo
        base_amt = wage + aux_trans + (total_var / eff * 30) if eff > 0 else wage + aux_trans
        base_diaria = base_amt / DAYS_YEAR
        
        # Valor prestación
        val_prest = base_diaria * eff
        
        # Crear diccionario de datos
        prestacion_data = {
            'tipo': tipo_prestacion,
            'periodo': {'desde': d0, 'hasta': d1},
            'dias': {'totales': plain, 'suspension': susp, 'efectivos': eff},
            'base': {
                'salario': wage,
                'auxilio': aux_trans,
                'variable': total_var,
                'total': base_amt,
                'diaria': base_diaria
            },
            'valor': val_prest
        }
        
        # Guardar en localdict
        localdict[f'{tipo_prestacion}_data'] = prestacion_data
        
        nombre = f'{tipo_prestacion.upper()} - {eff} días'
        
        return val_prest, eff, 100, nombre, prestacion_data, {}


    def _calculate_total_from_rules(self, localdict, category, exclude_not_in_net=True):
        """Calcula totales desde rules_multi por categorías"""
        rules_multi = localdict['rules_multi']
        total = 0
        details = {}
        category_totals = {}
        
        for code, rule_data in rules_multi.items():
            current = rule_data['current']
            rule_obj = current.get('object')
            
            if not rule_obj:
                continue
                
            if exclude_not_in_net and rule_obj.not_computed_in_net:
                continue
            
            cat_code = rule_obj.category_id.code
            parent_cat_code = rule_obj.category_id.parent_id.code if rule_obj.category_id.parent_id else None
            
            if cat_code in category or (parent_cat_code and parent_cat_code in category):
                amount = current.get('total', 0)
                total += amount
                details[code] = amount
                
                category_key = cat_code if cat_code in category else parent_cat_code
                if category_key not in category_totals:
                    category_totals[category_key] = 0
                category_totals[category_key] += amount
        
        return total, 1, 100, False, category_totals, details

    def _totaldev(self, localdict):
        """Calcula el total de devengos"""
        return self._calculate_total_from_rules(
            localdict, 
            category=['DEV_SALARIAL', 'DEV_NO_SALARIAL', 'PRESTACIONES_SOCIALES', 'AUX', 'IND']
        )

    def _totalded(self, localdict):
        """Calcula el total de deducciones.
        Fix v19: incluir SSOCIAL (salud/pension), RET (retencion) ademas de DED,
        ya que las reglas reales de deduccion usan esas categorias en Colombia,
        no la literal 'DED'.
        """
        return self._calculate_total_from_rules(
            localdict,
            category=['DED', 'SSOCIAL', 'SS', 'SS_EMP', 'RET', 'RETEFUENTE', 'DEDUCCIONES']
        )

    def _net(self, localdict):
        """Calcula el neto a pagar (devengos - deducciones)"""
        # Calcular devengos
        devengos, _, _, _, cat_devengos, det_devengos = self._calculate_total_from_rules(
            localdict,
            category=['DEV_SALARIAL', 'DEV_NO_SALARIAL', 'PRESTACIONES_SOCIALES', 'AUX', 'IND']
        )

        # Calcular deducciones - mismo fix que _totalded
        deducciones, _, _, _, cat_deducciones, det_deducciones = self._calculate_total_from_rules(
            localdict,
            category=['DED', 'SSOCIAL', 'SS', 'SS_EMP', 'RET', 'RETEFUENTE', 'DEDUCCIONES']
        )
        
        # Calcular neto
        neto = devengos + deducciones  # deducciones ya vienen negativas
        
        # Preparar diccionario de resumen
        resumen = {
            'devengos': devengos,
            'deducciones': deducciones,
            'neto': neto,
            'categorias': {
                **cat_devengos,
                'DEDUCCIONES': deducciones
            },
            'detalles': {
                **det_devengos,
                **det_deducciones
            }
        }
        
        return neto, 1, 100, False, resumen, {'neto': neto}
