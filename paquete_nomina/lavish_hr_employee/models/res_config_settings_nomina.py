# -*- coding: utf-8 -*-
"""
Configuración Unificada de Nómina CO
====================================

Sigue el patrón de POS (Point of Sale) donde:
1. Hay un modelo principal (hr.annual.parameters) con todos los campos
2. res.config.settings tiene campos relacionados con prefijo 'nomina_'
3. El usuario selecciona el año/parámetro a configurar

Este módulo unifica:
- Parámetros anuales (SMMLV, UVT, porcentajes)
- Configuración de compañía (res.company)
- Opciones de cálculo de nómina
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ═══════════════════════════════════════════════════════════════════════════
    # SELECTOR DE PARÁMETROS (como pos_config_id en POS)
    # ═══════════════════════════════════════════════════════════════════════════

    def _default_annual_parameters(self):
        """Default al parámetro del año actual o el más reciente"""
        current_year = fields.Date.today().year
        params = self.env['hr.annual.parameters'].get_for_year(
            current_year,
            company_id=self.env.company.id,
            raise_if_not_found=False,
        )
        if not params:
            params = self.env['hr.annual.parameters'].search([
                ('company_ids', 'parent_of', [self.env.company.id])
            ], order='year desc', limit=1)
        return params

    nomina_annual_parameters_id = fields.Many2one(
        'hr.annual.parameters',
        string='Año de Parámetros',
        default=_default_annual_parameters,
        domain="[('company_ids', 'parent_of', [company_id])]",
        help='Seleccione el año de parámetros a configurar'
    )

    # Toggle para mostrar/ocultar opciones avanzadas
    nomina_show_advanced = fields.Boolean(
        string='Mostrar Opciones Avanzadas',
        default=False,
        config_parameter='lavish_hr_employee.nomina_show_advanced',
        help='Habilite para ver todas las opciones de configuración avanzada'
    )

    # Campo computado para mostrar el año seleccionado dinámicamente
    nomina_selected_year = fields.Char(
        string='Año Seleccionado',
        compute='_compute_nomina_selected_year',
        help='Año de los parámetros seleccionados'
    )

    @api.depends('nomina_annual_parameters_id', 'nomina_annual_parameters_id.year')
    def _compute_nomina_selected_year(self):
        for record in self:
            if record.nomina_annual_parameters_id:
                record.nomina_selected_year = str(record.nomina_annual_parameters_id.year)
            else:
                record.nomina_selected_year = str(fields.Date.today().year)

    # ═══════════════════════════════════════════════════════════════════════════
    # VALORES PRINCIPALES - Relacionados a hr.annual.parameters
    # ═══════════════════════════════════════════════════════════════════════════

    # --- Salario Mínimo ---
    nomina_smmlv_monthly = fields.Float(
        string='SMMLV Mensual',
        related='nomina_annual_parameters_id.smmlv_monthly',
        readonly=False,
        help='Salario Mínimo Mensual Legal Vigente. Base para calcular topes de seguridad social, '
             'auxilio de transporte (< 2 SMMLV), aportes FSP (> 4 SMMLV), y otros beneficios legales. '
             'Ejemplo 2024: $1.300.000'
    )
    nomina_smmlv_daily = fields.Float(
        string='SMMLV Diario',
        related='nomina_annual_parameters_id.smmlv_daily',
        readonly=True,
        help='SMMLV dividido entre 30 días. Se usa para calcular proporcionales de prestaciones, '
             'incapacidades (mínimo 2/3 del diario), y licencias. Ejemplo 2024: $43.333'
    )
    nomina_transportation_assistance = fields.Float(
        string='Auxilio de Transporte',
        related='nomina_annual_parameters_id.transportation_assistance_monthly',
        readonly=False,
        help='Auxilio mensual para empleados con salario < 2 SMMLV (Art. 2 Ley 15/1959). '
             'Se incluye en base de prima, cesantías e intereses, pero NO en seguridad social. '
             'Ejemplo 2024: $162.000'
    )

    # --- UVT y Retención ---
    nomina_value_uvt = fields.Float(
        string='Valor UVT',
        related='nomina_annual_parameters_id.value_uvt',
        readonly=False,
        help='Unidad de Valor Tributario. Base para calcular retención en la fuente, '
             'deducciones tributarias, y límites fiscales. Se actualiza anualmente por DIAN. '
             'Ejemplo 2024: $47.065'
    )
    nomina_top_source_retention = fields.Float(
        string='Tope Retención en la Fuente',
        related='nomina_annual_parameters_id.value_top_source_retention',
        readonly=False,
        help='Ingreso mensual a partir del cual se aplica retención en la fuente. '
             'Depende del procedimiento (1 o 2) y la tabla del Art. 383 ET. '
             'Ejemplo: Ingresos > 95 UVT mensuales están sujetos a retención.'
    )

    # --- Salario Integral ---
    nomina_min_integral_salary = fields.Float(
        string='Salario Mínimo Integral',
        related='nomina_annual_parameters_id.min_integral_salary',
        readonly=True,
        help='Mínimo legal para pactar salario integral = 13 SMMLV (10 salario + 30% prestaciones). '
             'Empleados con salario integral no reciben prima, cesantías ni intereses adicionales. '
             'Ejemplo 2024: 13 x $1.300.000 = $16.900.000'
    )
    nomina_porc_integral_salary = fields.Integer(
        string='Porcentaje Salarial Integral',
        related='nomina_annual_parameters_id.porc_integral_salary',
        readonly=False,
        help='Porcentaje del salario integral que constituye factor salarial para IBC. '
             'Por defecto 70% (Art. 132 CST). El 30% restante cubre prestaciones sociales. '
             'IBC salario integral = Salario x 70%'
    )

    # --- Incrementos ---
    nomina_increment_smlv = fields.Float(
        string='Incremento SMMLV (%)',
        related='nomina_annual_parameters_id.value_porc_increment_smlv',
        readonly=False,
        help='Porcentaje de incremento del SMMLV respecto al año anterior. '
             'Definido por Gobierno Nacional. Se usa para proyecciones y ajustes salariales. '
             'Ejemplo: Incremento 2024 = 12% sobre 2023.'
    )
    nomina_ipc = fields.Float(
        string='IPC (%)',
        related='nomina_annual_parameters_id.value_porc_ipc',
        readonly=False,
        help='Índice de Precios al Consumidor anual certificado por DANE. '
             'Base para ajuste de pensiones, arriendos, y algunos contratos. '
             'Ejemplo: IPC 2023 = 9.28%'
    )

    # ═══════════════════════════════════════════════════════════════════════════
    # SEGURIDAD SOCIAL - Relacionados a hr.annual.parameters
    # ═══════════════════════════════════════════════════════════════════════════

    # --- Salud ---
    nomina_health_company = fields.Float(
        string='% Salud Empresa',
        related='nomina_annual_parameters_id.value_porc_health_company',
        readonly=False,
        help='Porcentaje de aporte a salud que asume la empresa sobre el IBC (Ley 100/1993). '
             'Valor estándar: 8.5%. Se paga a la EPS elegida por el empleado.'
    )
    nomina_health_employee = fields.Float(
        string='% Salud Empleado',
        related='nomina_annual_parameters_id.value_porc_health_employee',
        readonly=False,
        help='Porcentaje de aporte a salud que se descuenta al empleado sobre el IBC. '
             'Valor estándar: 4%. Se descuenta directamente de la nómina.'
    )
    nomina_health_total = fields.Float(
        string='% Salud Total',
        related='nomina_annual_parameters_id.value_porc_health_total',
        readonly=True,
        help='Suma del aporte empresa + empleado. Valor estándar: 12.5%. '
             'Ejemplo: IBC $4M. Aporte total = $500K (Empresa $340K + Empleado $160K)'
    )

    # --- Pensión ---
    nomina_pension_company = fields.Float(
        string='% Pensión Empresa',
        related='nomina_annual_parameters_id.value_porc_pension_company',
        readonly=False,
        help='Porcentaje de aporte a pensión que asume la empresa sobre el IBC. '
             'Valor estándar: 12%. Se paga al fondo de pensiones (AFP) o Colpensiones.'
    )
    nomina_pension_employee = fields.Float(
        string='% Pensión Empleado',
        related='nomina_annual_parameters_id.value_porc_pension_employee',
        readonly=False,
        help='Porcentaje de aporte a pensión que se descuenta al empleado sobre el IBC. '
             'Valor estándar: 4%. Empleados con salario > 4 SMMLV aportan 1% adicional al FSP.'
    )
    nomina_pension_total = fields.Float(
        string='% Pensión Total',
        related='nomina_annual_parameters_id.value_porc_pension_total',
        readonly=True,
        help='Suma del aporte empresa + empleado. Valor estándar: 16%. '
             'Ejemplo: IBC $5M. Aporte total = $800K (Empresa $600K + Empleado $200K)'
    )

    # --- Parafiscales ---
    nomina_compensation_box = fields.Float(
        string='% Caja Compensación',
        related='nomina_annual_parameters_id.value_porc_compensation_box_company',
        readonly=False,
        help='Aporte a Caja de Compensación Familiar sobre nómina. Valor estándar: 4%. '
             'Beneficios para empleados: subsidio familiar, recreación, educación, vivienda. '
             'NO exonerado por Ley 1607 (siempre se paga).'
    )
    nomina_sena = fields.Float(
        string='% SENA',
        related='nomina_annual_parameters_id.value_porc_sena_company',
        readonly=False,
        help='Aporte al Servicio Nacional de Aprendizaje sobre nómina. Valor estándar: 2%. '
             'Exoneración Ley 1607: Empresas con empleados < 10 SMMLV no pagan si declaran renta. '
             'Financia formación técnica y tecnológica.'
    )
    nomina_icbf = fields.Float(
        string='% ICBF',
        related='nomina_annual_parameters_id.value_porc_icbf_company',
        readonly=False,
        help='Aporte al Instituto Colombiano de Bienestar Familiar sobre nómina. Valor estándar: 3%. '
             'Exoneración Ley 1607: Empresas con empleados < 10 SMMLV no pagan si declaran renta. '
             'Financia programas de protección a la niñez.'
    )

    # ═══════════════════════════════════════════════════════════════════════════
    # PROVISIONES - Relacionados a hr.annual.parameters
    # ═══════════════════════════════════════════════════════════════════════════

    nomina_provision_prima = fields.Float(
        string='% Provisión Prima',
        related='nomina_annual_parameters_id.value_porc_provision_bonus',
        readonly=False,
        help='Porcentaje mensual para provisionar prima de servicios. Valor estándar: 8.33%. '
             'Cálculo: 1 mes de salario / 12 meses = 8.33%. Se paga en junio y diciembre. '
             'Ejemplo: Salario $3M. Provisión mensual = $249.900'
    )
    nomina_provision_cesantias = fields.Float(
        string='% Provisión Cesantías',
        related='nomina_annual_parameters_id.value_porc_provision_cesantias',
        readonly=False,
        help='Porcentaje mensual para provisionar cesantías. Valor estándar: 8.33%. '
             'Cálculo: 1 mes de salario por año / 12 meses = 8.33%. Se consignan en febrero. '
             'Ejemplo: Salario $3M. Provisión mensual = $249.900'
    )
    nomina_provision_int_cesantias = fields.Float(
        string='% Provisión Int. Cesantías',
        related='nomina_annual_parameters_id.value_porc_provision_intcesantias',
        readonly=False,
        help='Porcentaje mensual para provisionar intereses sobre cesantías. Valor estándar: 1%. '
             'Cálculo: 12% anual / 12 meses = 1%. Se pagan a más tardar el 31 de enero. '
             'Ejemplo: Cesantías $3M. Intereses anuales = $360K'
    )
    nomina_provision_vacaciones = fields.Float(
        string='% Provisión Vacaciones',
        related='nomina_annual_parameters_id.value_porc_provision_vacation',
        readonly=False,
        help='Porcentaje mensual para provisionar vacaciones. Valor estándar: 4.17%. '
             'Cálculo: 15 días hábiles por año / 360 días = 4.17%. '
             'Ejemplo: Salario $3M. Provisión mensual = $125.100'
    )

    # ═══════════════════════════════════════════════════════════════════════════
    # OPCIONES DE CÁLCULO - Relacionados a hr.annual.parameters
    # ═══════════════════════════════════════════════════════════════════════════

    nomina_simple_provisions = fields.Boolean(
        string='Provisiones Simplificadas',
        related='nomina_annual_parameters_id.simple_provisions',
        readonly=False,
        help='ON: Calcula provisiones con porcentaje fijo (8.33% prima, 8.33% cesantías, etc.)\n'
             'OFF: Calcula provisiones con días exactos trabajados en el periodo'
    )
    nomina_provision_days_method = fields.Selection(
        related='nomina_annual_parameters_id.provision_days_method',
        readonly=False,
        help='Define si las provisiones se calculan con días completos del periodo '
             'o solo con los días trabajados (WORK100) del slip.'
    )
    nomina_rtf_projection = fields.Boolean(
        string='Retención Proyectada en 1ra Quincena',
        related='nomina_annual_parameters_id.rtf_projection',
        readonly=False,
        help='ON: Descuenta retención completa del mes en la primera quincena\n'
             'OFF: Distribuye retención proporcionalmente en cada periodo de pago'
    )
    nomina_ded_round = fields.Boolean(
        string='Redondear Deducciones SS',
        related='nomina_annual_parameters_id.ded_round',
        readonly=False,
        help='Redondea aportes de seguridad social al peso más cercano.\n'
             'Ejemplo: $234,567.45 -> $234,567'
    )
    nomina_rtf_round = fields.Boolean(
        string='Redondear Retención',
        related='nomina_annual_parameters_id.rtf_round',
        readonly=False,
        help='Redondea el valor de retención en la fuente al peso más cercano'
    )
    nomina_positive_net = fields.Boolean(
        string='Solo Neto Positivo',
        related='nomina_annual_parameters_id.positive_net',
        readonly=False,
        help='ON: Si las deducciones superan los devengados, ajusta para que el neto sea $0\n'
             'OFF: Permite netos negativos (empleado debe a la empresa)'
    )
    nomina_fragment_vac = fields.Boolean(
        string='Vacaciones Fragmentadas',
        related='nomina_annual_parameters_id.fragment_vac',
        readonly=False,
        help='Permite liquidar vacaciones en periodos menores a 15 días hábiles.\n'
             'Art. 190 CST: Mínimo 6 días consecutivos, resto fragmentable.'
    )
    nomina_prst_wo_susp = fields.Boolean(
        string='No Descontar Suspensiones de Prima',
        related='nomina_annual_parameters_id.prst_wo_susp',
        readonly=False,
        help='ON: Calcula prima sin descontar días de licencia no remunerada\n'
             'OFF: Descuenta días de suspensión del cálculo de prima'
    )

    # --- Métodos de Cálculo ---
    nomina_severance_calculation = fields.Selection(
        related='nomina_annual_parameters_id.severance_pay_calculation',
        readonly=False,
        help='Método para calcular cesantías:\n'
             '- Tradicional: Base x días / 360\n'
             '- Proporcional: Considera días exactos del mes'
    )
    nomina_overtime_method = fields.Selection(
        related='nomina_annual_parameters_id.overtime_calculation_method',
        readonly=False,
        help='Método para calcular horas extras:\n'
             '- 240 horas: Valor hora = Salario / 240\n'
             '- Horas mes: Valor hora = Salario / Horas del mes (Ley 2101)'
    )
    nomina_accounting_method = fields.Selection(
        related='nomina_annual_parameters_id.accounting_method',
        readonly=False,
        help='Método de contabilización desde el lote:\n'
             '- Por empleado: Un asiento contable por cada empleado\n'
             '- Por departamento: Agrupa asientos por departamento\n'
             '- Por cuenta analítica: Agrupa asientos por cuenta analítica\n'
             '- Asiento único: Un solo asiento para todo el lote'
    )
    
    nomina_accounting_line_grouping = fields.Selection(
        related='nomina_annual_parameters_id.accounting_line_grouping',
        readonly=False,
        help='Agrupación de líneas contables:\n'
             '- Agrupar líneas: Suma todas las líneas de la misma regla, cuenta y tercero en una sola línea contable\n'
             '- Detalle de líneas: Muestra cada línea de nómina como una línea contable separada\n\n'
             'Ejemplo con 3 empleados y misma regla "Salario":\n'
             '• Agrupar: 1 línea contable con total $9,000,000\n'
             '• Detalle: 3 líneas contables de $3,000,000 cada una'
    )

    # --- Calendario ---
    nomina_complete_february = fields.Boolean(
        string='Completar Febrero a 30 días',
        related='nomina_annual_parameters_id.complete_february_to_30',
        readonly=False,
        help='ON: Febrero se calcula como 30 días para prestaciones\n'
             'OFF: Febrero se calcula con sus días reales (28 o 29)'
    )
    nomina_apply_day_31 = fields.Boolean(
        string='Aplicar Regla Día 31',
        related='nomina_annual_parameters_id.apply_day_31',
        readonly=False,
        help='ON: Meses de 31 días se pagan como 31 días\n'
             'OFF: Todos los meses se pagan como 30 días'
    )

    # ═══════════════════════════════════════════════════════════════════════════
    # CONFIGURACIÓN DE COMPAÑÍA - Relacionados a res.company
    # ═══════════════════════════════════════════════════════════════════════════

    nomina_exonerated_law_1607 = fields.Boolean(
        string='Exonerado Ley 1607',
        related='company_id.exonerated_law_1607',
        readonly=False,
        help='ON: Empresa exonerada de aportes SENA e ICBF (Ley 1607/2012)\n'
             'Requisitos: Declarante de renta + empleados con salario < 10 SMMLV\n'
             'Ahorro: 5% sobre nómina (2% SENA + 3% ICBF)'
    )
    nomina_entity_arp_id = fields.Many2one(
        'hr.employee.entities',
        string='Entidad ARL',
        related='company_id.entity_arp_id',
        readonly=False,
        help='Administradora de Riesgos Laborales de la empresa.\n'
             'Ejemplos: Positiva, Sura, Colmena, Axa Colpatria'
    )
    nomina_type_contributor = fields.Selection(
        related='company_id.type_contributor',
        readonly=False,
        help='Tipo de aportante para PILA:\n'
             '1: Empleador\n'
             '2: Independiente\n'
             '3: Entidad sin ánimo de lucro'
    )
    nomina_include_absences_1393 = fields.Boolean(
        string='Incluir Ausencias en Ley 1393',
        related='company_id.include_absences_1393',
        readonly=False,
        help='ON: Incluye días de incapacidad y licencia en el cálculo del límite 40%\n'
             'OFF: Solo considera pagos efectivamente recibidos por el trabajador'
    )

    # ═══════════════════════════════════════════════════════════════════════════
    # HORAS LABORALES
    # ═══════════════════════════════════════════════════════════════════════════

    nomina_hours_monthly = fields.Float(
        string='Horas Mensuales',
        related='nomina_annual_parameters_id.hours_monthly',
        readonly=False,
        help='Horas laborales al mes según jornada. Ley 2101/2021:\n'
             '2023: 47h/sem = 235h/mes | 2024: 46h = 230h | 2025: 44h = 220h | 2026+: 42h = 210h'
    )
    nomina_hours_weekly = fields.Float(
        string='Horas Semanales',
        related='nomina_annual_parameters_id.hours_weekly',
        readonly=True,
        help='Jornada laboral semanal máxima. Se calcula automáticamente.\n'
             'Base para determinar horas extras (exceden la jornada ordinaria)'
    )
    nomina_hours_daily = fields.Float(
        string='Horas Diarias',
        related='nomina_annual_parameters_id.hours_daily',
        readonly=True,
        help='Jornada diaria ordinaria (típicamente 8 horas).\n'
             'Base para calcular valor hora = Salario / (Horas día x 30)'
    )

    # ═══════════════════════════════════════════════════════════════════════════
    # TOPES CALCULADOS (Solo lectura)
    # ═══════════════════════════════════════════════════════════════════════════

    nomina_top_4_smmlv = fields.Float(
        string='Tope 4 SMMLV (FSP)',
        related='nomina_annual_parameters_id.top_four_fsp_smmlv',
        readonly=True,
        help='Salario >= 4 SMMLV: Empleado aporta 1% adicional al Fondo de Solidaridad Pensional.\n'
             'Calculado: SMMLV x 4'
    )
    nomina_top_25_smmlv = fields.Float(
        string='Tope 25 SMMLV (IBC)',
        related='nomina_annual_parameters_id.top_twenty_five_smmlv',
        readonly=True,
        help='Tope máximo del IBC para seguridad social = 25 SMMLV.\n'
             'Ingresos superiores no generan aportes adicionales.'
    )
    nomina_top_10_smmlv = fields.Float(
        string='Tope 10 SMMLV',
        related='nomina_annual_parameters_id.top_ten_smmlv',
        readonly=True,
        help='Referencia para exoneración Ley 1607.\n'
             'Empleados con salario < 10 SMMLV: empresa no paga SENA/ICBF.'
    )
    nomina_top_aux_transporte = fields.Float(
        string='Tope Aux. Transporte (2 SMMLV)',
        related='nomina_annual_parameters_id.top_max_transportation_assistance',
        readonly=True,
        help='Empleados con salario < 2 SMMLV tienen derecho a auxilio de transporte.\n'
             'Calculado: SMMLV x 2'
    )

    # ═══════════════════════════════════════════════════════════════════════════
    # ACCIONES
    # ═══════════════════════════════════════════════════════════════════════════

    def action_open_annual_parameters(self):
        """Abre el formulario completo de parámetros anuales"""
        self.ensure_one()
        if not self.nomina_annual_parameters_id:
            raise UserError(_('Primero seleccione un año de parámetros'))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Parámetros %s') % self.nomina_annual_parameters_id.year,
            'res_model': 'hr.annual.parameters',
            'res_id': self.nomina_annual_parameters_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_copy_parameters_wizard(self):
        """Abre el wizard para copiar parámetros del año anterior"""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Copiar Parámetros de Año Anterior'),
            'res_model': 'hr.annual.parameters.copy.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_company_id': self.company_id.id,
                'default_source_year': fields.Date.today().year - 1,
                'default_target_year': fields.Date.today().year,
            }
        }

    def action_create_new_year(self):
        """Crea parámetros para un nuevo año"""
        current_year = fields.Date.today().year

        # Verificar si ya existe
        existing = self.env['hr.annual.parameters'].get_for_year(
            current_year,
            company_id=self.company_id.id,
            raise_if_not_found=False,
        )

        if existing:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Parámetros %s') % current_year,
                'res_model': 'hr.annual.parameters',
                'res_id': existing.id,
                'view_mode': 'form',
                'target': 'current',
            }

        # Abrir wizard para copiar
        return self.action_copy_parameters_wizard()

    def action_create_working_hours(self):
        """Crea configuración de horas laborales según Ley 2101"""
        if self.nomina_annual_parameters_id:
            return self.nomina_annual_parameters_id.action_create_working_hours()
        raise UserError(_('Primero seleccione un año de parámetros'))
