# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from datetime import datetime, timedelta, date
from odoo.exceptions import UserError, ValidationError
from odoo.tools.sql import column_exists
from odoo.tools import SQL
import time

from .hr_payslip_constants import MONTH_NAMES

# Tabla de parametros anuales
class HrAnnualParameters(models.Model):
    _name = 'hr.annual.parameters'
    _description = 'Parámetros anuales'

    active = fields.Boolean('Activo', default=True, help='Si está desmarcado, el registro no aparecerá en las búsquedas')
    year = fields.Integer('Año', required=True)
    smmlv_monthly = fields.Float('Valor mensual SMMLV', required=True)
    smmlv_daily = fields.Float('Valor diario SMMLV', compute='_values_smmlv', store=True)
    top_four_fsp_smmlv = fields.Float('Tope 4 salarios FSP', compute='_values_smmlv', store=True)
    top_twenty_five_smmlv = fields.Float('Tope 25 salarios', compute='_values_smmlv', store=True)
    top_ten_smmlv = fields.Float('Tope 10 salarios', compute='_values_smmlv', store=True)
    transportation_assistance_monthly = fields.Float('Valor mensual Auxilio Transporte', required=True)
    transportation_assistance_daily = fields.Float('Valor diario Auxilio Transporte',
                                                   compute='_value_transportation_assistance_daily', store=True)
    top_max_transportation_assistance = fields.Float('Tope maxímo para pago', compute='_values_smmlv', store=True)
    min_integral_salary = fields.Float('Salario mínimo integral', compute='_values_smmlv', store=True)
    porc_integral_salary = fields.Integer('Porcentaje salarial', required=True)
    value_factor_integral_salary = fields.Float('Valor salarial', compute='_values_integral_salary', store=True)
    value_factor_integral_performance = fields.Float('Valor prestacional', compute='_values_integral_salary',
                                                     store=True)

    value_auxilio_conectividad = fields.Float('Valor Auxilio Conectividad', help="Valor del auxilio de conectividad para empleados", default=0)
    top_max_auxilio_conectividad = fields.Float('Tope maxímo para pago Auxilio Conectividad', compute='_values_smmlv', store=True, readonly=False,
                                                 help="Tope máximo para pago del auxilio de conectividad, por defecto 2 salarios mínimos legales mensuales vigentes")

    # Básicos Horas Laborales
    hours_daily = fields.Float(digits='Payroll', string='Horas diarias', )
    hours_weekly = fields.Float(digits='Payroll', string='Horas semanales', )
    hours_fortnightly = fields.Float(digits='Payroll', string='Horas quincenales', )
    hours_monthly = fields.Float(digits='Payroll', string='Horas mensuales', store=True, )
    # Seguridad Social
    weight_contribution_calculations = fields.Boolean('Cálculos de aportes al peso')
    # Salud
    value_porc_health_company = fields.Float('Porcentaje empresa salud', required=True)
    value_porc_health_employee = fields.Float('Porcentaje empleado salud', required=True)
    value_porc_health_total = fields.Float('Porcentaje total salud', compute='_value_porc_health_total', store=True)
    value_porc_health_employee_foreign = fields.Float('Porcentaje aporte extranjero', required=True)
    # Pension
    value_porc_pension_company = fields.Float('Porcentaje empresa pensión', required=True)
    value_porc_pension_employee = fields.Float('Porcentaje empleado pensión', required=True)
    value_porc_pension_total = fields.Float('Porcentaje total pensión', compute='_value_porc_pension_total', store=True)
    # Aportes parafiscales
    value_porc_compensation_box_company = fields.Float('Caja de compensación', required=True)
    value_porc_sena_company = fields.Float('SENA', required=True)
    value_porc_icbf_company = fields.Float('ICBF', required=True)
    # Provisiones prestaciones
    value_porc_provision_bonus = fields.Float('Prima', required=True)
    value_porc_provision_cesantias = fields.Float('Cesantías', required=True)
    value_porc_provision_intcesantias = fields.Float('Intereses Cesantías', required=True)
    value_porc_provision_vacation = fields.Float('Vacaciones', required=True)
    # Tope Ley 1395
    value_porc_statute_1395 = fields.Integer('Porcentaje (%)', required=True)
    # Tributario
    # Retención en la fuente
    value_uvt = fields.Float('Valor UVT', required=True)
    value_top_source_retention = fields.Float('Tope para el calculo de retención en la fuente', required=True)
    # Incrementos
    value_porc_increment_smlv = fields.Float('Incremento SMLV', required=True)
    value_porc_ipc = fields.Float('Porcentaje IPC', required=True)
    # NOTA: Los campos de certificado de ingresos y retenciones se movieron a hr.certificate.income.header
    #PRESTACIONES SOCIALES SECTOR PUBLICO Y DISTRITAL
    food_subsidy_amount = fields.Integer(string="Subsidio de alimentación")
    bonus_services_rendered = fields.Integer(string="Tope Bonificación por servicios prestados (B.S.P)")
    food_subsidy_tope = fields.Integer(string="Tope Subsidio de alimentación")
    percentage_public = fields.Integer(string="Porcentaje Emp. Publicos")
    company_ids = fields.Many2many(
        'res.company',
        string='Compañías',
        required=True,
        readonly=False,
        depends_context=('uid',),
        default=lambda self: self.env.company,
        help='Compañías a las que aplican estos parámetros anuales.',
    )
    
    name = fields.Char(
        string='Nombre',
        compute='_compute_displays_name',
        store=True
    )

    simple_provisions = fields.Boolean(
        'Cálculo de provisiones simple',
        default=False,
        help="Usa método de porcentaje fijo para provisiones en lugar del consolidado"
    )
    simple_provision_fortnight_mode = fields.Selection([
        ('by_fortnight', 'Provisionar en cada quincena'),
        ('last_fortnight_full', 'Todo en la última quincena'),
    ], string='Modo provisión quincenal (simple)', default='by_fortnight',
       help='Define cómo se provisiona cuando la nómina es quincenal en provisiones simples.')
    simple_provision_days_mode = fields.Selection([
        ('worked_days', 'Días trabajados'),
        ('full_days', 'Días completos del período'),
    ], string='Días para provisión (simple)', default='worked_days',
       help='En provisiones simples por quincena, usar días trabajados o días completos del período.')
    auxilio_days_mode = fields.Selection([
        ('worked_days', 'Días trabajados'),
        ('full_days', 'Días completos del período'),
    ], string='Días para auxilio (AUX000)', default='worked_days',
       help='Define si AUX000 usa días trabajados o todos los días del período de nómina.')
    rtf_projection = fields.Boolean(
        'Cálculo de retención proyectada en primera quincena',
        default=False,
        help="Proyecta el salario completo en primera quincena para cálculo de retención"
    )
    
    ded_round = fields.Boolean(
        'Redondeo de deducciones EPS, PEN, FSO',
        default=False,
        help="Redondea al entero más cercano las deducciones de seguridad social"
    )
    
    rtf_round = fields.Boolean(
        'Redondeo de retención en la fuente',
        default=False,
        help="Redondea la retención en la fuente al múltiplo de 1000 más cercano"
    )
    aux_apr_lectiva = fields.Boolean(
        'Auxilio de transporte a aprendices en etapa lectiva',
        default=False,
        help="Otorga auxilio de transporte a aprendices en etapa lectiva"
    )
    
    aux_apr_prod = fields.Boolean(
        'Auxilio de transporte a aprendices en etapa productiva',
        default=False,
        help="Otorga auxilio de transporte a aprendices en etapa productiva"
    )
    
    fragment_vac = fields.Boolean(
        'Vacaciones fragmentadas',
        default=False,
        help="Permite fragmentar vacaciones en periodos menores a 15 días"
    )
    
    prv_vac_cpt = fields.Boolean(
        'Provisión de vacaciones por conceptos',
        default=False,
        help="Calcula provisión de vacaciones por conceptos marcados como base"
    )
    
    aux_prst = fields.Boolean(
        'Incorporación de auxilio de transporte en prestaciones sin promediar',
        default=False,
        help="Incluye auxilio de transporte en prestaciones sin considerar topes"
    )
    
    aus_prev = fields.Boolean(
        'Pago de ausencias de periodos anteriores',
        default=False,
        help="Permite pagar ausencias reportadas con posterioridad al periodo"
    )
    
    positive_net = fields.Boolean(
        'Cierre de nómina solo con neto positivo',
        default=True,
        help="Impide cerrar nóminas con valor neto negativo"
    )
    
    nonprofit = fields.Boolean(
        'Empresa sin ánimo de lucro',
        default=False,
        help="Omite validaciones de topes para parafiscales que aplican a empresas con ánimo de lucro"
    )
    
    prst_wo_susp = fields.Boolean(
        'No descontar suspensiones de prima',
        default=False,
        help="No resta días de suspensión para cálculo de prima"
    )
    
    accounting_method = fields.Selection([
        ('employee', 'Por empleado'),
        ('department', 'Por departamento'),
        ('analytic', 'Por cuenta analítica'),
        ('single', 'Asiento único')
    ], string='Método de contabilización', default='single',
       help="Define cómo se contabiliza desde el lote:\n"
            "- Por empleado: Un asiento contable por cada empleado\n"
            "- Por departamento: Agrupa asientos por departamento\n"
            "- Por cuenta analítica: Agrupa asientos por cuenta analítica\n"
            "- Asiento único: Un solo asiento para todo el lote")
    
    accounting_line_grouping = fields.Selection([
        ('group', 'Agrupar líneas'),
        ('detail', 'Detalle de líneas')
    ], string='Agrupación de líneas contables', default='group',
       help="Define si las líneas de la misma regla salarial se agrupan o se muestran individualmente:\n"
            "- Agrupar líneas: Suma todas las líneas de la misma regla, cuenta y tercero en una sola línea contable\n"
            "- Detalle de líneas: Muestra cada línea de nómina como una línea contable separada\n\n"
            "Ejemplo con 3 empleados y misma regla 'Salario':\n"
            "• Agrupar: 1 línea contable con total $9,000,000\n"
            "• Detalle: 3 líneas contables de $3,000,000 cada una")
    
    default_accounting_date = fields.Selection([
        ('period_end', 'Fin de período'),
        ('process_date', 'Fecha de proceso'),
        ('specific_date', 'Fecha específica por lote')
    ], string='Fecha de contabilización predeterminada', default='period_end',
       help="Define fecha predeterminada para asientos contables")
    overtime_calculation_method = fields.Selection([
        ('standard', 'Estándar (Salario actual)'), 
        ('average_3m', 'Promedio 3 meses'),
        ('average_6m', 'Promedio 6 meses'),
        ('last_salary', 'IBL Mes anterior')
    ], string='Método de cálculo horas extras', default='standard',
       help="Define base salarial para cálculo de horas extras")
    complete_february_to_30 = fields.Boolean(
        string='Completar febrero a 30 días',
        default=True,
        help='Si está activo, en febrero se añadirán días adicionales para llegar a 30'
    )
    
    month_change_policy = fields.Selection([
        ('use_workdays', 'Usar días trabajados para completar'),
        ('use_absence', 'Continuar con el tipo de ausencia')
    ], string='Política para cambio de mes', 
       default='use_absence',
       help='Define cómo manejar las ausencias que continúan de un mes a otro:'
            '\n- Usar días trabajados: si una ausencia termina el último día del mes,'
            ' los días siguientes (31 o feb 29/30) se tratarán como días trabajados'
            '\n- Continuar ausencia: si una ausencia termina el último día del mes,'
            ' se continuará con el mismo tipo de ausencia para completar a 30 días.')
    
    apply_day_31 = fields.Boolean(
        string='Aplicar regla para día 31',
        default=True,
        help='Si está activo, el día 31 se manejará como un día adicional según reglas especiales'
    )
    severance_pay_calculation = fields.Selection([
        ('consolidated', 'Consolidado (Base Real)'),
        ('simplified', 'Simplificado (Porcentaje)')
    ], string='Cálculo de cesantías', default='consolidated',
       help="Método para calcular cesantías")
    store_payroll_history = fields.Boolean(
        'Almacenar histórico detallado de Sueldo',
        default=True,
        help="Guarda información detallada para consultas históricas y promedios"
    )
    ibc_history_months = fields.Integer(
        'Meses de historia IBC a mantener',
        default=24,
        help="Meses de historia IBC que se mantendrán por empleado"
    )

    # Configuracion IBC global para licencias
    use_ibl_as_ibc_global = fields.Boolean(
        string='Usar IBL como IBC en licencias (Ley)',
        default=True,
        help='Segun la ley, para licencias remuneradas (luto, paternidad, maternidad) el IBC '
             'debe ser el del mes anterior al inicio de la licencia, no el salario actual. '
             'Si esta activo, se usara el IBL calculado como base para la cotizacion a seguridad social '
             'en todos los tipos de ausencia que tengan habilitada esta opcion.'
    )

    # =========================================================================
    # LEY 2466 DE 2025 - REFORMA LABORAL COLOMBIA
    # =========================================================================

    # --- Jornada Nocturna (Art. cambio de 9pm a 7pm) ---
    night_shift_start_hour = fields.Integer(
        string='Hora inicio jornada nocturna',
        default=19,
        help='Hora de inicio de jornada nocturna (formato 24h). '
             'Ley 2466/2025: 19 (7pm). Antes: 21 (9pm)'
    )
    night_shift_end_hour = fields.Integer(
        string='Hora fin jornada nocturna',
        default=6,
        help='Hora de fin de jornada nocturna (formato 24h). Default: 6 (6am)'
    )
    night_shift_surcharge = fields.Float(
        string='Recargo nocturno (%)',
        default=35.0,
        help='Porcentaje de recargo por hora nocturna. Default: 35%'
    )

    # --- Recargo Dominical y Festivo (Gradual) ---
    sunday_holiday_surcharge = fields.Float(
        string='Recargo dominical/festivo (%)',
        default=80.0,
        help='Porcentaje de recargo por trabajo en domingos y festivos.\n'
             'Ley 2466/2025 - Gradualidad:\n'
             '- Jul 2025: 80%\n'
             '- Jul 2026: 90%\n'
             '- Jul 2027: 100%'
    )


    # --- Formula de calculo de horas extras ---
    overtime_formula_type = fields.Selection([
        ('classic', 'Formula clasica (Salario / 240)'),
        ('legal', 'Formula legal (Salario / Horas mes)')
    ], string='Formula horas extras', default='classic',
        help='Seleccione el tipo de formula para calcular el valor hora:\n'
             '- Clasica: Salario / 240 (asume 8 horas x 30 dias)\n'
             '- Legal: Salario / (Horas semanales / 6 * 30)\n'
             'Ejemplo con 44 horas semanales: Salario / 220\n'
             'Ejemplo con 42 horas semanales: Salario / 210'
    )
    sync_working_hours_on_save = fields.Boolean(
        string='Sincronizar horas al guardar',
        default=True,
        help='Si está activo, al guardar los parámetros anuales se creará automáticamente '
             'la configuración de horas laborales según la Ley 2101/2021 para todas las empresas.'
    )

    # --- Licencia de Paternidad (Gradual) ---
    paternity_leave_days = fields.Integer(
        string='Días licencia paternidad',
        default=14,
        help='Días de licencia de paternidad.\n'
             'Ley 2466/2025 - Gradualidad:\n'
             '- 2024: 14 días (2 semanas)\n'
             '- 2025: 21 días (3 semanas)\n'
             '- 2026: 28 días (4 semanas)'
    )

    # --- Contrato de Aprendizaje como Laboral ---
    apprentice_full_social_security = fields.Boolean(
        string='Aprendices con SS completa (Ley 2466)',
        default=False,
        help='Si está activo, los aprendices aportan a todos los sistemas de seguridad social:\n'
             'EPS, Pensión, ARL, Caja de Compensación, SENA, ICBF.\n'
             'Ley 2466/2025: Contrato de aprendizaje es contrato laboral a término fijo.'
    )
    apprentice_lectiva_salary_percent = fields.Float(
        string='% Salario aprendiz etapa lectiva',
        default=75.0,
        help='Porcentaje del SMMLV para etapa lectiva. Ley 2466: 75%'
    )
    apprentice_practica_salary_percent = fields.Float(
        string='% Salario aprendiz etapa práctica',
        default=100.0,
        help='Porcentaje del SMMLV para etapa práctica. Ley 2466: 100%'
    )

    # --- Contratos a Término Fijo (Límite 4 años) ---
    fixed_term_max_years = fields.Integer(
        string='Máximo años contrato término fijo',
        default=4,
        help='Duración máxima de contratos a término fijo incluyendo prórrogas.\n'
             'Ley 2466/2025: 4 años (antes 3 años).\n'
             'Al superar este límite, se convierte en indefinido.'
    )

    # --- Trabajadores Plataformas Digitales ---
    platform_worker_ibc_percent = fields.Float(
        string='% IBC trabajadores plataforma',
        default=40.0,
        help='Porcentaje de ingresos para base de cotización de trabajadores de plataformas digitales.\n'
             'Ley 2466/2025: 40% del total de ingresos.'
    )
    platform_worker_health_platform_percent = fields.Float(
        string='% Salud plataforma (independiente)',
        default=60.0,
        help='Porcentaje de salud que asume la plataforma para trabajadores independientes.\n'
             'Ley 2466: 60% plataforma, 40% trabajador.'
    )
    platform_worker_pension_platform_percent = fields.Float(
        string='% Pensión plataforma (independiente)',
        default=60.0,
        help='Porcentaje de pensión que asume la plataforma para trabajadores independientes.\n'
             'Ley 2466: 60% plataforma, 40% trabajador.'
    )

    # --- Trabajadores Domésticos ---
    domestic_worker_written_contract_required = fields.Boolean(
        string='Contrato escrito obligatorio (domésticos)',
        default=True,
        help='Ley 2466/2025: El contrato de trabajo doméstico debe ser escrito.\n'
             'Si no hay contrato escrito, se considera a término indefinido.'
    )

    working_hours_ids = fields.One2many('hr.company.working.hours', 'annual_parameter_id', string='Configuración de horas laborales')

    # =========================================================================
    # MÉTODOS LEY 2466
    # =========================================================================

    @api.model
    def get_sunday_holiday_surcharge(self, date_work=None):
        """
        Obtiene el porcentaje de recargo dominical/festivo según la fecha.
        Implementa la gradualidad de la Ley 2466/2025.

        Args:
            date_work: Fecha del trabajo (default: hoy)

        Returns:
            float: Porcentaje de recargo (75, 80, 90 o 100)
        """
        if not date_work:
            date_work = date.today()

        # Gradualidad Ley 2466/2025
        if date_work >= date(2027, 7, 1):
            return 100.0
        elif date_work >= date(2026, 7, 1):
            return 90.0
        elif date_work >= date(2025, 7, 1):
            return 80.0
        else:
            return 75.0

    @api.model
    def get_night_shift_start_hour(self, date_work=None):
        """
        Obtiene la hora de inicio de jornada nocturna según la fecha.
        Ley 2466/2025: Cambia de 9pm a 7pm desde dic 2025.

        Args:
            date_work: Fecha del trabajo (default: hoy)

        Returns:
            int: Hora de inicio (19 o 21)
        """
        if not date_work:
            date_work = date.today()

        # Ley 2466/2025 - Vigencia desde 25 dic 2025
        if date_work >= date(2025, 12, 25):
            return 19  # 7pm
        else:
            return 21  # 9pm

    @api.model
    def get_paternity_leave_days(self, birth_date=None):
        """
        Obtiene los días de licencia de paternidad según el año de nacimiento.
        Implementa la gradualidad de la Ley 2466/2025.

        Args:
            birth_date: Fecha de nacimiento del hijo (default: hoy)

        Returns:
            int: Días de licencia (14, 21 o 28)
        """
        if not birth_date:
            birth_date = date.today()

        year = birth_date.year

        if year >= 2026:
            return 28  # 4 semanas
        elif year >= 2025:
            return 21  # 3 semanas
        else:
            return 14  # 2 semanas
    @api.depends('company_ids', 'year')
    def _compute_displays_name(self):
        """Genera un nombre descriptivo para el registro"""
        for record in self:
            companies = record.company_ids
            if record.year and companies:
                if len(companies) == 1:
                    record.name = f"Políticas de Nómina {companies[0].name} - {record.year}"
                else:
                    record.name = f"Políticas de Nómina ({len(companies)} compañías) - {record.year}"
            elif record.year:
                record.name = f"Políticas de Nómina {record.year}"
            else:
                record.name = _("Políticas de Nómina")
    
    # -------------------------------------------------------------------------
    # Migración y utilidades multi-compañía (company_ids)
    # -------------------------------------------------------------------------
    def init(self):
        """
        Migración idempotente:
        - Si existe una columna legacy `company_id` (Many2one) en la tabla, poblarla en `company_ids`
          para evitar registros sin compañías tras la migración a Many2many.
        """
        field = self._fields.get('company_ids')
        if not field:
            return

        if not column_exists(self._cr, self._table, 'company_id'):
            return

        relation = field.relation
        col1 = field.column1
        col2 = field.column2

        self._cr.execute(SQL(
            """
            INSERT INTO %s (%s, %s)
            SELECT p.id, p.company_id
            FROM %s p
            WHERE p.company_id IS NOT NULL
              AND NOT EXISTS (
                SELECT 1 FROM %s r WHERE r.%s = p.id
              )
            """,
            SQL.identifier(relation),
            SQL.identifier(col1),
            SQL.identifier(col2),
            SQL.identifier(self._table),
            SQL.identifier(relation),
            SQL.identifier(col1),
        ))

    @api.constrains('year', 'company_ids')
    def _check_company_year_overlap(self):
        """
        Evita que una misma compañía esté en múltiples registros del mismo año.
        """
        for record in self:
            if not record.year or not record.company_ids:
                continue

            duplicates = self.search([
                ('id', '!=', record.id),
                ('year', '=', record.year),
                ('company_ids', 'in', record.company_ids.ids),
            ])
            if duplicates:
                conflict_companies = record.company_ids & duplicates.mapped('company_ids')
                names = ", ".join(conflict_companies.mapped('name')) if conflict_companies else _("(sin compañía)")
                raise ValidationError(
                    _('Ya existe un registro de parámetros para el año %s en las compañías: %s') % (record.year, names)
                )

    @api.model
    def get_for_year(self, year, company_id=None, raise_if_not_found=True):
        """
        Obtiene los parámetros anuales para un año y compañía.

        La búsqueda considera `company_ids` (Many2many) y jerarquía de compañías:
        - Si company_id es None: busca solo por año (parámetros globales)
        - Si company_id está definido: preferencia por registros que incluyan la compañía
        - Fallback a registros asignados a una empresa padre (patrón similar a cuentas contables)
        """
        # Si no se especifica empresa, buscar solo por año
        if company_id is None:
            candidates = self.sudo().search([
                ('year', '=', year),
                ('active', '=', True),
            ], limit=1, order='id desc')
            if candidates:
                return candidates
            if raise_if_not_found:
                raise UserError(_('Faltan parámetros anuales para el año %s') % year)
            return self.browse()

        # Búsqueda con empresa específica
        company = self.env['res.company'].sudo().browse(company_id)

        candidates = self.sudo().search([
            ('year', '=', year),
            ('company_ids', 'parent_of', [company_id]),
            ('active', '=', True),
        ])

        if candidates:
            parent_chain = company.parent_ids.ids if company else [company_id]
            parent_pos = {cid: idx for idx, cid in enumerate(parent_chain)}
            chain_len = len(parent_chain) - 1

            def score(rec):
                companies = rec.company_ids
                direct = company_id in companies.ids
                if direct:
                    distance = 0
                else:
                    distances = []
                    for comp in companies:
                        pos = parent_pos.get(comp.id)
                        if pos is not None:
                            distances.append(chain_len - pos)
                    distance = min(distances) if distances else 9999
                return (
                    0 if direct else 1,          # direct first
                    distance,                    # closest parent first
                    len(companies) or 9999,      # more specific first
                    -rec.id,                     # stable tie-breaker
                )

            return min(candidates, key=score)

        # Fallback: buscar sin filtro de empresa (parámetros globales)
        fallback = self.sudo().search([
            ('year', '=', year),
            ('active', '=', True),
        ], limit=1, order='id desc')
        if fallback:
            return fallback

        if raise_if_not_found:
            raise UserError(_('Faltan parámetros anuales para el año %s') % year)

        return self.browse()

    @api.model
    def get_policies(self, company_id=None, date=None):
        if not company_id:
            company_id = self.env.company.id
        if not date:
            date = fields.Date.today()
            
        year = date.year
        
        # Buscar políticas para ese año y compañía
        policies = self.get_for_year(year, company_id=company_id, raise_if_not_found=False)
        
        # Si no existen, buscar las del año más reciente
        if not policies:
            policies = self.search([
                ('company_ids', 'parent_of', [company_id]),
                ('active', '=', True)
            ], order='year desc', limit=1)
            
        if not policies:
            raise UserError(_('No se encontraron parámetros anuales configurados para la compañía y año solicitados.'))
            
        return policies

    # Metodos
    def _compute_display_name(self):
        """Override display name to show year and company if set."""
        for record in self:
            companies = record.company_ids
            if companies:
                if len(companies) == 1:
                    record.display_name = f"Parámetros {record.year} - {companies[0].name}"
                else:
                    record.display_name = f"Parámetros {record.year} - ({len(companies)} compañías)"
            else:
                record.display_name = f"Parámetros {record.year}"

    @api.depends('smmlv_monthly')
    def _values_smmlv(self):
        for record in self:
            record.smmlv_daily = record.smmlv_monthly / 30
            record.top_four_fsp_smmlv = 4 * record.smmlv_monthly
            record.top_twenty_five_smmlv = 25 * record.smmlv_monthly
            record.top_ten_smmlv = 10 * record.smmlv_monthly
            record.top_max_transportation_assistance = 2 * record.smmlv_monthly
            record.min_integral_salary = 13 * record.smmlv_monthly
            record.top_max_auxilio_conectividad = 2 * record.smmlv_monthly

    @api.depends('transportation_assistance_monthly')
    def _value_transportation_assistance_daily(self):
        for rec in self:
            rec.transportation_assistance_daily = rec.transportation_assistance_monthly / 30

    @api.depends('porc_integral_salary')
    def _values_integral_salary(self):
        for rec in self:
            porc_integral_salary_rest = 100 - rec.porc_integral_salary
            value_factor_integral_salary = round(rec.min_integral_salary / ((porc_integral_salary_rest / 100) + 1), 0)
            value_factor_integral_performance = round(rec.min_integral_salary - value_factor_integral_salary, 0)
            rec.value_factor_integral_salary = value_factor_integral_salary
            rec.value_factor_integral_performance = value_factor_integral_performance

    @api.depends('hours_monthly')
    def _compute_hours(self):
        for rec in self:
            if rec.hours_monthly:
                rec.hours_weekly = 7 * (rec.hours_monthly / 30)
                rec.hours_fortnightly = 15 * (rec.hours_monthly / 30)
                rec.hours_daily = rec.hours_monthly / 30
            else:
                rec.hours_daily = 0
                rec.hours_weekly = 0
                rec.hours_fortnightly = 0
                

    @api.onchange('hours_monthly')
    def _onchange_hours_monthly(self):
        """Actualiza los campos de horas cuando cambia el valor mensual en la interfaz"""
        for rec in self:
            if rec.hours_monthly:
                rec.hours_daily = rec.hours_monthly / 30
                rec.hours_weekly = 7 * rec.hours_daily
                rec.hours_fortnightly = 15 * rec.hours_daily

    @api.depends('value_porc_health_company', 'value_porc_health_employee')
    def _value_porc_health_total(self):
        for rec in self:
            rec.value_porc_health_total = rec.value_porc_health_company + rec.value_porc_health_employee

    @api.depends('value_porc_pension_company', 'value_porc_pension_employee')
    def _value_porc_pension_total(self):
        for rec in self:
            rec.value_porc_pension_total = rec.value_porc_pension_company + rec.value_porc_pension_employee

    # Validaciones
    @api.onchange('porc_integral_salary')
    def _onchange_porc_integral_salary(self):
        for record in self:
            if record.porc_integral_salary > 100:
                raise UserError(_('El porcentaje salarial integral no puede ser mayor a 100. Por favor verificar.'))

                # Funcionalidades

    def get_values_integral_salary(self, integral_salary, get_value):
        for rec in self:
            porc_integral_salary_rest = 100 - rec.porc_integral_salary
            value_factor_integral_salary = round(integral_salary / ((porc_integral_salary_rest / 100) + 1), 0)
            value_factor_integral_performance = round(integral_salary - value_factor_integral_salary, 0)
            value_factor_integral_salary = value_factor_integral_salary
            value_factor_integral_performance = value_factor_integral_performance
        return value_factor_integral_salary if get_value == 0 else value_factor_integral_performance

    def write(self, vals):
        """
        Override write para sincronizar configuración de horas laborales
        cuando se cambia overtime_formula_type a 'legal' y sync_working_hours_on_save está activo.
        """
        result = super().write(vals)

        # Si cambió overtime_formula_type a 'legal' o se activó la sincronización
        if vals.get('overtime_formula_type') == 'legal' or vals.get('sync_working_hours_on_save'):
            for rec in self:
                if rec.overtime_formula_type == 'legal' and rec.sync_working_hours_on_save:
                    # Crear configuración de horas si no existe
                    rec._sync_working_hours_for_legal_formula()

        return result

    def _sync_working_hours_for_legal_formula(self):
        """
        Sincroniza la configuración de horas laborales para fórmula legal.
        Crea registros de hr.company.working.hours si no existen.
        """
        self.ensure_one()
        WorkingHours = self.env['hr.company.working.hours']
        companies = self.company_ids or self.env.company

        for company in companies:
            # Verificar si ya existen registros para este año y compañía
            existing = WorkingHours.search([
                ('company_id', '=', company.id),
                ('year', '=', self.year)
            ], limit=1)

            if not existing:
                # Llamar al método existente para crear la configuración
                self.action_create_working_hours()
                break  # Solo una vez ya que el método crea para todas las empresas

    def action_create_working_hours(self):
        """
        Crea registros de horas de trabajo por PERIODO DE VIGENCIA
        según la Ley 2101 de 2021 que establece la reducción gradual
        exactamente el 15 de julio de cada año.

        En lugar de crear 12 registros (uno por mes), crea registros
        por periodo continuo con las mismas horas laborales.
        """
        self.ensure_one()

        year = self.year
        companies = self.company_ids or self.env.company

        # Definir periodos de vigencia según la Ley 2101 de 2021
        # Formato: (fecha_inicio, fecha_fin, horas_semanales, horas_mensuales, descripción)
        periods = []

        if year < 2023:
            # Antes de 2023: 48 horas todo el año
            periods = [
                (f'{year}-01-01', f'{year}-12-31', 48.0, 240.0, f'Periodo completo {year} - 48h/semana')
            ]
        elif year == 2023:
            # 2023: 48h hasta el 14 de julio, 47h desde el 15 de julio
            periods = [
                (f'{year}-01-01', f'{year}-07-14', 48.0, 240.0, f'Enero a Julio 14, {year} - 48h/semana'),
                (f'{year}-07-15', f'{year}-12-31', 47.0, 235.0, f'Julio 15 a Diciembre, {year} - 47h/semana')
            ]
        elif year == 2024:
            # 2024: 47h hasta el 14 de julio, 46h desde el 15 de julio
            periods = [
                (f'{year}-01-01', f'{year}-07-14', 47.0, 235.0, f'Enero a Julio 14, {year} - 47h/semana'),
                (f'{year}-07-15', f'{year}-12-31', 46.0, 230.0, f'Julio 15 a Diciembre, {year} - 46h/semana')
            ]
        elif year == 2025:
            # 2025: 46h hasta el 14 de julio, 44h desde el 15 de julio
            periods = [
                (f'{year}-01-01', f'{year}-07-14', 46.0, 230.0, f'Enero a Julio 14, {year} - 46h/semana'),
                (f'{year}-07-15', f'{year}-12-31', 44.0, 220.0, f'Julio 15 a Diciembre, {year} - 44h/semana')
            ]
        elif year == 2026:
            # 2026: 44h hasta el 14 de julio, 42h desde el 15 de julio
            periods = [
                (f'{year}-01-01', f'{year}-07-14', 44.0, 220.0, f'Enero a Julio 14, {year} - 44h/semana'),
                (f'{year}-07-15', f'{year}-12-31', 42.0, 210.0, f'Julio 15 a Diciembre, {year} - 42h/semana')
            ]
        else:
            # 2027 en adelante: 42 horas todo el año
            periods = [
                (f'{year}-01-01', f'{year}-12-31', 42.0, 210.0, f'Periodo completo {year} - 42h/semana')
            ]

        # Crear registros por periodo de vigencia (por compañía seleccionada)
        created_count = 0
        for company in companies:
            for start_date_str, end_date_str, max_hours, hours_to_pay, description in periods:
                start_date = fields.Date.from_string(start_date_str)

                # Verificar si ya existe un registro para este periodo
                existing = self.env['hr.company.working.hours'].search([
                    ('company_id', '=', company.id),
                    ('effective_date', '=', start_date),
                    ('max_hours_per_week', '=', max_hours)
                ], limit=1)

                if existing:
                    continue

                # Determinar mes para compatibilidad (usar el mes de inicio del periodo)
                month = start_date.month

                # Crear el registro de periodo
                self.env['hr.company.working.hours'].create({
                    'company_id': company.id,
                    'year': year,
                    'month': month,
                    'max_hours_per_week': max_hours,
                    'hours_to_pay': hours_to_pay,
                    'effective_date': start_date,
                    'notes': f'{description}. Vigente desde {start_date_str} hasta {end_date_str}. Ley 2101 de 2021',
                    'annual_parameter_id': self.id
                })
                created_count += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Configuración de horas creada'),
                'message': _('Se han creado %s periodos de horas laborales para el año %s según la Ley 2101 de 2021.') % (created_count, year),
                'sticky': False,
                'type': 'success',
            }
        }

class HrCompanyWorkingHours(models.Model):
    _name = 'hr.company.working.hours'
    _description = 'Horas Laborales por Empresa'
    _order = 'year desc, month desc'
    
    name = fields.Char(
        string='Nombre',
        compute='_compute_name',
        store=True
    )
     
    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        index=True
    )
    
    year = fields.Integer(
        string='Año',
        required=True,
        default=lambda self: fields.Date.today().year,
        index=True
    )
    
    month = fields.Integer(
        string='Mes',
        required=True,
        default=lambda self: fields.Date.today().month,
        index=True
    )
    
    max_hours_per_week = fields.Float(
        string='Horas máximas por semana',
        required=True,
        help="Jornada laboral semanal máxima según normativa vigente"
    )
    
    hours_per_month = fields.Float(
        string='Horas laborales mensuales',
        compute='_compute_monthly_hours',
        store=True,
        help="Horas laborales totales por mes"
    )
    
    hours_to_pay = fields.Float(
        string='Horas a pagar',
        required=True,
        help="Horas que deben pagarse según la normativa"
    )
    
    effective_date = fields.Date(
        string='Fecha de vigencia',
        required=True,
        help="Fecha desde la cual aplica esta configuración"
    )
    
    notes = fields.Text(
        string='Notas',
        help="Observaciones adicionales sobre esta configuración"
    )

    annual_parameter_id = fields.Many2one('hr.annual.parameters', 'Parámetro relacionado', ondelete='cascade')

    # Configuración de horario semanal
    lunch_duration_hours = fields.Float(
        string='Duración Almuerzo (Horas)',
        default=2.0,
        help='Duración del almuerzo en horas'
    )

    lunch_start_time = fields.Float(
        string='Hora Inicio Almuerzo',
        default=12.0,
        help='Hora de inicio del almuerzo (formato 24h decimal, ej: 12.0 = 12:00, 12.5 = 12:30)'
    )

    lunch_end_time = fields.Float(
        string='Hora Fin Almuerzo',
        compute='_compute_lunch_end_time',
        store=True,
        help='Hora de finalización del almuerzo calculada automáticamente'
    )

    works_saturday = fields.Boolean(
        string='Trabaja Sábados',
        default=False,
        help='Indica si el horario incluye trabajo los sábados'
    )

    work_start_time = fields.Float(
        string='Hora Inicio Trabajo',
        default=8.0,
        help='Hora de inicio de la jornada laboral (formato 24h)'
    )

    hours_per_day = fields.Float(
        string='Horas por Día',
        compute='_compute_hours_per_day',
        store=True,
        help='Horas laborales por día (sin contar almuerzo)'
    )

    work_end_time = fields.Float(
        string='Hora Fin Trabajo',
        compute='_compute_work_end_time',
        store=True,
        help='Hora de fin de la jornada laboral calculada'
    )
    
    @api.depends('lunch_start_time', 'lunch_duration_hours')
    def _compute_lunch_end_time(self):
        for record in self:
            record.lunch_end_time = record.lunch_start_time + record.lunch_duration_hours

    @api.depends('max_hours_per_week', 'works_saturday')
    def _compute_hours_per_day(self):
        for record in self:
            working_days = 6 if record.works_saturday else 5
            record.hours_per_day = record.max_hours_per_week / working_days if working_days > 0 else 0

    @api.depends('work_start_time', 'hours_per_day', 'lunch_duration_hours')
    def _compute_work_end_time(self):
        for record in self:
            total_day_hours = record.hours_per_day + record.lunch_duration_hours
            record.work_end_time = record.work_start_time + total_day_hours

    def action_create_resource_calendar(self):
        """
        Crea un resource.calendar basado en la configuración de horas laborales
        """
        self.ensure_one()

        # Nombre del calendario
        calendar_name = f"Horario {self.name} - {self.max_hours_per_week}h/semana"

        # Verificar si ya existe un calendario con este nombre
        existing_calendar = self.env['resource.calendar'].search([
            ('name', '=', calendar_name),
            ('company_id', '=', self.company_id.id)
        ], limit=1)

        if existing_calendar:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Calendario ya existe'),
                    'message': _('Ya existe un calendario con este nombre. Puede editarlo directamente.'),
                    'sticky': False,
                    'type': 'warning',
                }
            }

        # Crear el calendario
        calendar_vals = {
            'name': calendar_name,
            'company_id': self.company_id.id if self.company_id else False,
            'hours_per_day': self.hours_per_day,
            'tz': 'America/Bogota',
        }

        calendar = self.env['resource.calendar'].create(calendar_vals)

        # Definir días de la semana (0=Lunes, 6=Domingo)
        days_of_week = [
            ('0', 'Lunes'),
            ('1', 'Martes'),
            ('2', 'Miércoles'),
            ('3', 'Jueves'),
            ('4', 'Viernes'),
            ('5', 'Sábado'),
            ('6', 'Domingo'),
        ]

        # Crear las attendances (líneas de horario)
        for day_number, day_name in days_of_week:
            # Domingo siempre descansa
            if day_number == '6':
                continue

            # Sábado solo si works_saturday está activo
            if day_number == '5' and not self.works_saturday:
                continue

            # Turno de mañana (antes del almuerzo)
            morning_vals = {
                'name': f'{day_name} - Mañana',
                'dayofweek': day_number,
                'hour_from': self.work_start_time,
                'hour_to': self.lunch_start_time,
                'calendar_id': calendar.id,
            }
            self.env['resource.calendar.attendance'].create(morning_vals)

            # Turno de tarde (después del almuerzo)
            afternoon_vals = {
                'name': f'{day_name} - Tarde',
                'dayofweek': day_number,
                'hour_from': self.lunch_end_time,
                'hour_to': self.work_end_time,
                'calendar_id': calendar.id,
            }
            self.env['resource.calendar.attendance'].create(afternoon_vals)

        return {
            'type': 'ir.actions.act_window',
            'name': _('Calendario Creado'),
            'res_model': 'resource.calendar',
            'res_id': calendar.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.depends('year', 'month', 'company_id')
    def _compute_name(self):
        """Genera un nombre descriptivo para el registro"""
        for record in self:
            if record.month and record.year:
                month_name = MONTH_NAMES.get(record.month, str(record.month))
                name = f"Horas Laborales - {month_name} {record.year}"
            else:
                name = "Horas Laborales"
            record.name = name
    
    @api.depends('max_hours_per_week')
    def _compute_monthly_hours(self):
        """Calcula las horas mensuales basadas en las horas semanales"""
        for record in self:
            # Multiplicamos por 4.33 semanas que tiene un mes en promedio
            record.hours_per_month = round(record.max_hours_per_week * 4.33, 1)
    
    _company_year_effective_unique = models.Constraint('UNIQUE(company_id, year, effective_date)',
                                                       'Ya existe un registro para esta empresa, año y fecha de vigencia')
    
