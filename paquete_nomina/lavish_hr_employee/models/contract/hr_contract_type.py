# -*- coding: utf-8 -*-
"""
Extensión del modelo hr.contract.type para Colombia
====================================================
Implementa los parámetros de tipos de contrato según la Ley 2466 de 2025
(Reforma Laboral Colombia).

Tipos de contrato soportados:
- Término Fijo: Máximo 4 años incluyendo renovaciones
- Término Indefinido: Modalidad preferente por defecto
- Obra o Labor: Sin fecha fija, termina al completar la obra
- Aprendizaje: 75% SMMLV en etapa lectiva, 100% en productiva
- Ocasional/Transitorio: Máximo 30 días
- Agropecuario: Nuevo tipo para el sector rural

Referencia Legal:
- Ley 2466 de 2025 (Reforma Laboral)
- Artículo 64 del CST (Indemnización)
  URL: http://www.secretariasenado.gov.co/senado/basedoc/codigo_sustantivo_trabajo_pr001.html#64
- Artículo 46 del CST (Contratos a término fijo)
- Ley 789 de 2002, Artículo 28

Autor: Bohio Consultores
Fecha: 2025
"""

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from dateutil.relativedelta import relativedelta


class HrContractType(models.Model):
    _inherit = 'hr.contract.type'
    _description = 'Tipo de Contrato Laboral Colombia'

    # =========================================================================
    # CAMPOS DE IDENTIFICACIÓN LEGAL
    # =========================================================================

    code = fields.Char(
        string='Código',
        help='Código interno del tipo de contrato'
    )

    contract_category = fields.Selection([
        ('fijo', 'Término Fijo'),
        ('indefinido', 'Término Indefinido'),
        ('obra', 'Obra o Labor'),
        ('aprendizaje', 'Aprendizaje'),
        ('ocasional', 'Ocasional/Transitorio'),
        ('agropecuario', 'Agropecuario'),
    ], string='Categoría de Contrato', required=True, default='indefinido',
       help='Categoría legal del contrato según la Ley 2466 de 2025')

    description = fields.Text(
        string='Descripción Legal',
        help='Descripción del tipo de contrato según la normativa colombiana'
    )

    active = fields.Boolean(default=True)

    # =========================================================================
    # CAMPOS DE DURACIÓN Y RENOVACIÓN
    # =========================================================================

    requires_end_date = fields.Boolean(
        string='Requiere Fecha Fin',
        default=False,
        help='Si el contrato requiere fecha de finalización obligatoria'
    )

    max_duration_months = fields.Integer(
        string='Duración Máxima (meses)',
        default=0,
        help='Duración máxima del contrato en meses. 0 = sin límite. '
             'Para término fijo: 48 meses (4 años) según Ley 2466/2025'
    )

    max_duration_days = fields.Integer(
        string='Duración Máxima (días)',
        default=0,
        help='Duración máxima en días. Aplica para contratos ocasionales (30 días máx.)'
    )

    max_renewals = fields.Integer(
        string='Renovaciones Máximas',
        default=0,
        help='Número máximo de renovaciones permitidas. 0 = sin límite'
    )

    auto_convert_indefinite = fields.Boolean(
        string='Conversión Automática a Indefinido',
        default=False,
        help='Si al superar la duración máxima o renovaciones, '
             'el contrato se convierte automáticamente a indefinido'
    )

    renewal_notice_days = fields.Integer(
        string='Días Preaviso Renovación',
        default=30,
        help='Días de anticipación para notificar la no renovación del contrato. '
             'Según Art. 46 CST, debe ser mínimo 30 días antes del vencimiento.'
    )

    auto_renewal = fields.Boolean(
        string='Renovación Automática',
        default=True,
        help='Si el contrato se renueva automáticamente cuando no hay preaviso. '
             'Art. 46 numeral 1 del CST.'
    )

    # =========================================================================
    # CAMPOS DE PRESTACIONES SOCIALES
    # =========================================================================

    has_prima = fields.Boolean(
        string='Derecho a Prima',
        default=True,
        help='Si el tipo de contrato tiene derecho a prima de servicios'
    )

    has_cesantias = fields.Boolean(
        string='Derecho a Cesantías',
        default=True,
        help='Si el tipo de contrato tiene derecho a cesantías'
    )

    has_intereses_cesantias = fields.Boolean(
        string='Derecho a Intereses Cesantías',
        default=True,
        help='Si el tipo de contrato tiene derecho a intereses sobre cesantías'
    )

    has_vacaciones = fields.Boolean(
        string='Derecho a Vacaciones',
        default=True,
        help='Si el tipo de contrato tiene derecho a vacaciones'
    )

    has_dotacion = fields.Boolean(
        string='Derecho a Dotación',
        default=True,
        help='Si el tipo de contrato tiene derecho a dotación'
    )

    has_auxilio_transporte = fields.Boolean(
        string='Derecho a Auxilio Transporte',
        default=True,
        help='Si el tipo de contrato tiene derecho a auxilio de transporte'
    )

    # =========================================================================
    # CAMPOS DE SEGURIDAD SOCIAL
    # =========================================================================

    has_salud = fields.Boolean(
        string='Afiliación a Salud',
        default=True,
        help='Si el tipo de contrato requiere afiliación a EPS'
    )

    has_pension = fields.Boolean(
        string='Afiliación a Pensión',
        default=True,
        help='Si el tipo de contrato requiere afiliación a pensión. '
             'Ley 2466: Aprendices ahora tienen derecho a pensión.'
    )

    has_riesgos = fields.Boolean(
        string='Afiliación a ARL',
        default=True,
        help='Si el tipo de contrato requiere afiliación a ARL'
    )

    has_caja_compensacion = fields.Boolean(
        string='Afiliación a Caja Compensación',
        default=True,
        help='Si el tipo de contrato requiere afiliación a caja de compensación'
    )

    has_parafiscales = fields.Boolean(
        string='Aportes Parafiscales',
        default=True,
        help='Si el tipo de contrato genera aportes parafiscales (SENA, ICBF)'
    )

    # =========================================================================
    # CAMPOS ESPECÍFICOS PARA APRENDIZAJE (Ley 2466/2025)
    # =========================================================================

    is_apprenticeship = fields.Boolean(
        string='Es Contrato de Aprendizaje',
        default=False,
        help='Marca si este tipo de contrato es de aprendizaje'
    )

    apprentice_wage_pct_lectiva = fields.Float(
        string='% SMMLV Etapa Lectiva',
        default=75.0,
        help='Porcentaje del SMMLV para la etapa lectiva. '
             'Ley 2466: 75% del SMMLV'
    )

    apprentice_wage_pct_productiva = fields.Float(
        string='% SMMLV Etapa Productiva',
        default=100.0,
        help='Porcentaje del SMMLV para la etapa productiva. '
             'Ley 2466: 100% del SMMLV'
    )

    apprentice_max_duration_months = fields.Integer(
        string='Duración Máxima Aprendizaje (meses)',
        default=24,
        help='Duración máxima del contrato de aprendizaje en meses'
    )

    has_social_benefits_aprendiz = fields.Boolean(
        string='Aprendiz con Prestaciones Sociales',
        default=True,
        help='Si el aprendiz tiene derecho a prestaciones sociales (prima, cesantías, vacaciones). '
             'Según la Ley 2466/2025, los aprendices ahora tienen derecho a prestaciones sociales.'
    )

    # =========================================================================
    # CAMPOS ESPECÍFICOS PARA AGROPECUARIO (Ley 2466/2025)
    # =========================================================================

    is_agricultural = fields.Boolean(
        string='Es Contrato Agropecuario',
        default=False,
        help='Marca si este tipo de contrato es agropecuario'
    )

    agricultural_special_rules = fields.Boolean(
        string='Reglas Especiales Agropecuarias',
        default=False,
        help='Aplica reglas especiales de jornada y descanso para el sector rural'
    )

    # =========================================================================
    # CAMPOS PARA INDEMNIZACIÓN (Art. 64 CST, Ley 789/2002 Art. 28)
    # =========================================================================

    indemnization_type = fields.Selection([
        ('dias_faltantes', 'Días Faltantes (Fijo/Obra)'),
        ('tabla_antiguedad', 'Tabla por Antigüedad (Indefinido)'),
        ('no_aplica', 'No Aplica'),
    ], string='Tipo de Indemnización', default='tabla_antiguedad',
       help='''Tipo de cálculo de indemnización por despido sin justa causa:

- Días Faltantes: Para contratos a término fijo y obra/labor.
  Art. 64 CST: "El valor de los salarios correspondientes al tiempo
  que faltare para cumplir el plazo estipulado del contrato."
  Para obra/labor: mínimo 15 días si el tiempo restante es menor.

- Tabla por Antigüedad: Para contratos a término indefinido.
  Se aplica la tabla del Art. 64 CST según años de servicio.

- No Aplica: Para contratos ocasionales y de aprendizaje.

Referencia: http://www.secretariasenado.gov.co/senado/basedoc/codigo_sustantivo_trabajo_pr001.html#64''')

    indemnization_min_days = fields.Integer(
        string='Días Mínimos Indemnización',
        default=15,
        help='Días mínimos de indemnización para contratos por obra o labor. '
             'Art. 64 CST: Mínimo 15 días de salario.'
    )

    include_variable_salary = fields.Boolean(
        string='Incluir Salario Variable',
        default=True,
        help='''Si se debe incluir el promedio de conceptos salariales variables
para el cálculo de la indemnización:
- Comisiones
- Bonificaciones salariales
- Horas extras
- Otros conceptos que constituyan salario'''
    )

    variable_salary_months = fields.Integer(
        string='Meses para Promedio Variable',
        default=12,
        help='Número de meses para calcular el promedio del salario variable. '
             'Por defecto 12 meses (último año laborado).'
    )

    # =========================================================================
    # CAMPOS DE SINDICALIZACIÓN (Ley 2466/2025)
    # =========================================================================

    has_union_rights = fields.Boolean(
        string='Derecho a Sindicalización',
        default=True,
        help='Si el tipo de contrato tiene derecho a sindicalización. '
             'Ley 2466: Aprendices ahora pueden sindicalizarse.'
    )

    # =========================================================================
    # CAMPOS DE CONTROL
    # =========================================================================

    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        default=lambda self: self.env.company
    )

    country_id = fields.Many2one(
        'res.country',
        string='Pais',
        help='Pais donde aplica este tipo de contrato. Dejar vacio para todos los paises.'
    )

    notes = fields.Text(
        string='Notas',
        help='Notas adicionales sobre el tipo de contrato'
    )

    # =========================================================================
    # CONSTRAINS
    # =========================================================================

    @api.constrains('max_duration_months', 'contract_category')
    def _check_max_duration(self):
        """Valida la duración máxima según la categoría."""
        for record in self:
            if record.contract_category == 'fijo' and record.max_duration_months > 48:
                raise ValidationError(_(
                    'La duración máxima para contratos a término fijo no puede '
                    'superar 48 meses (4 años) según la Ley 2466 de 2025.'
                ))
            if record.contract_category == 'ocasional' and record.max_duration_days > 30:
                raise ValidationError(_(
                    'La duración máxima para contratos ocasionales no puede '
                    'superar 30 días según la normativa laboral.'
                ))

    @api.constrains('apprentice_wage_pct_lectiva', 'apprentice_wage_pct_productiva')
    def _check_apprentice_wages(self):
        """Valida los porcentajes de aprendizaje."""
        for record in self:
            if record.is_apprenticeship:
                if record.apprentice_wage_pct_lectiva < 75:
                    raise ValidationError(_(
                        'El porcentaje del SMMLV para etapa lectiva no puede ser '
                        'menor al 75%% según la Ley 2466 de 2025.'
                    ))
                if record.apprentice_wage_pct_productiva < 100:
                    raise ValidationError(_(
                        'El porcentaje del SMMLV para etapa productiva no puede ser '
                        'menor al 100%% según la Ley 2466 de 2025.'
                    ))

    # =========================================================================
    # ONCHANGE
    # =========================================================================

    @api.onchange('contract_category')
    def _onchange_contract_category(self):
        """Configura valores por defecto según la categoría."""
        defaults = {
            'fijo': {
                'requires_end_date': True,
                'max_duration_months': 48,
                'max_renewals': 3,
                'auto_convert_indefinite': True,
                'auto_renewal': True,
                'has_prima': True,
                'has_cesantias': True,
                'has_vacaciones': True,
                'indemnization_type': 'dias_faltantes',
            },
            'indefinido': {
                'requires_end_date': False,
                'max_duration_months': 0,
                'max_renewals': 0,
                'auto_convert_indefinite': False,
                'has_prima': True,
                'has_cesantias': True,
                'has_vacaciones': True,
                'indemnization_type': 'tabla_antiguedad',
            },
            'obra': {
                'requires_end_date': False,
                'max_duration_months': 0,
                'max_renewals': 0,
                'auto_convert_indefinite': False,
                'has_prima': True,
                'has_cesantias': True,
                'has_vacaciones': True,
                'indemnization_type': 'dias_faltantes',
                'indemnization_min_days': 15,
            },
            'aprendizaje': {
                'requires_end_date': True,
                'max_duration_months': 24,
                'is_apprenticeship': True,
                'apprentice_wage_pct_lectiva': 75.0,
                'apprentice_wage_pct_productiva': 100.0,
                'has_prima': True,  # Ley 2466
                'has_cesantias': True,  # Ley 2466
                'has_vacaciones': True,  # Ley 2466
                'has_pension': True,  # Ley 2466
                'has_union_rights': True,  # Ley 2466
                'indemnization_type': 'no_aplica',
            },
            'ocasional': {
                'requires_end_date': True,
                'max_duration_days': 30,
                'max_duration_months': 0,
                'has_prima': False,
                'has_cesantias': False,
                'has_vacaciones': False,
                'indemnization_type': 'no_aplica',
            },
            'agropecuario': {
                'requires_end_date': False,
                'is_agricultural': True,
                'agricultural_special_rules': True,
                'has_prima': True,
                'has_cesantias': True,
                'has_vacaciones': True,
                'indemnization_type': 'tabla_antiguedad',
            },
        }

        if self.contract_category and self.contract_category in defaults:
            for field, value in defaults[self.contract_category].items():
                setattr(self, field, value)

    # =========================================================================
    # MÉTODOS DE UTILIDAD
    # =========================================================================

    def get_applicable_benefits(self):
        """Retorna un diccionario con las prestaciones aplicables."""
        self.ensure_one()
        return {
            'prima': self.has_prima,
            'cesantias': self.has_cesantias,
            'intereses_cesantias': self.has_intereses_cesantias,
            'vacaciones': self.has_vacaciones,
            'dotacion': self.has_dotacion,
            'auxilio_transporte': self.has_auxilio_transporte,
            'salud': self.has_salud,
            'pension': self.has_pension,
            'riesgos': self.has_riesgos,
            'caja_compensacion': self.has_caja_compensacion,
            'parafiscales': self.has_parafiscales,
        }

    def calculate_indemnization(self, contract, termination_date):
        """
        Delegado a la lógica de indemnización en reglas.
        """
        self.ensure_one()
        return self.env['hr.salary.rule']._calculate_indemnization_data(
            contract, termination_date, self
        )

    # =========================================================================
    # MÉTODOS PARA CONTROL DE CONCEPTOS Y NOVEDADES
    # =========================================================================

    # Mapeo de prestaciones a códigos de reglas salariales
    PRESTACIONES_RULES_MAP = {
        'prima': {
            'provision': 'PRV_PRIM',
            'liquidacion': 'PRST_PRI',
            'base_field': 'base_prima',
        },
        'cesantias': {
            'provision': 'PRV_CES',
            'liquidacion': 'PRST_CES',
            'base_field': 'base_cesantias',
        },
        'intereses_cesantias': {
            'provision': 'PRV_ICES',
            'liquidacion': 'PRST_INTCES',
            'base_field': 'base_intereses_cesantias',
        },
        'vacaciones': {
            'provision': 'PRV_VAC',
            'liquidacion': 'PRST_VAC',
            'base_field': 'base_vacaciones',
        },
        'auxilio_transporte': {
            'concepto': 'AUX000',
            'base_field': 'base_auxtransporte_tope',
        },
        'dotacion': {
            'concepto': 'DOT000',
        },
    }

    # Mapeo de seguridad social a códigos de reglas
    SEGURIDAD_SOCIAL_RULES_MAP = {
        'salud': {
            'empleado': 'SS_SALUD_EMP',
            'empleador': 'SS_SALUD_CIA',
        },
        'pension': {
            'empleado': 'SS_PENSION_EMP',
            'empleador': 'SS_PENSION_CIA',
        },
        'riesgos': {
            'empleador': 'SS_ARL_CIA',
        },
        'caja_compensacion': {
            'empleador': 'PF_CAJA',
        },
        'parafiscales': {
            'sena': 'PF_SENA',
            'icbf': 'PF_ICBF',
        },
    }

    def get_applicable_salary_rules(self, include_provisions=True, include_liquidaciones=True):
        """
        Retorna las reglas salariales aplicables según las prestaciones habilitadas.

        Este método permite que el tipo de contrato controle qué conceptos se
        calculan en la nómina, basándose en los campos has_* del tipo de contrato.

        Args:
            include_provisions: Si incluir reglas de provisión (PRV_*)
            include_liquidaciones: Si incluir reglas de liquidación (PRST_*)

        Returns:
            dict: {
                'rule_codes': Lista de códigos de reglas aplicables,
                'excluded_codes': Lista de códigos excluidos,
                'domain': Dominio para buscar reglas,
                'benefits_config': Configuración de prestaciones activas
            }
        """
        self.ensure_one()

        applicable_codes = []
        excluded_codes = []
        benefits = self.get_applicable_benefits()

        # Procesar prestaciones
        for benefit_key, is_active in benefits.items():
            if benefit_key in self.PRESTACIONES_RULES_MAP:
                rules_config = self.PRESTACIONES_RULES_MAP[benefit_key]

                if is_active:
                    # Agregar códigos de reglas activas
                    if include_provisions and 'provision' in rules_config:
                        applicable_codes.append(rules_config['provision'])
                    if include_liquidaciones and 'liquidacion' in rules_config:
                        applicable_codes.append(rules_config['liquidacion'])
                    if 'concepto' in rules_config:
                        applicable_codes.append(rules_config['concepto'])
                else:
                    # Agregar a excluidos si no aplica
                    if 'provision' in rules_config:
                        excluded_codes.append(rules_config['provision'])
                    if 'liquidacion' in rules_config:
                        excluded_codes.append(rules_config['liquidacion'])
                    if 'concepto' in rules_config:
                        excluded_codes.append(rules_config['concepto'])

        # Procesar seguridad social
        for ss_key, rules_config in self.SEGURIDAD_SOCIAL_RULES_MAP.items():
            is_active = benefits.get(ss_key, True)

            for rule_type, code in rules_config.items():
                if is_active:
                    applicable_codes.append(code)
                else:
                    excluded_codes.append(code)

        # Construir dominio para buscar reglas
        domain = [('code', 'in', applicable_codes)] if applicable_codes else []

        return {
            'rule_codes': applicable_codes,
            'excluded_codes': excluded_codes,
            'domain': domain,
            'benefits_config': benefits,
        }

