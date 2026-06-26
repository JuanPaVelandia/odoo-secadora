# -*- coding: utf-8 -*-
from datetime import date

from odoo import _, api, fields, models
from odoo.addons.lavish_erp.utils.name_parser import split_nombre_completo
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain as expression


class HrTipoCotizante(models.Model):
    _name = 'hr.tipo.cotizante'
    _description = 'Tipos de cotizante'
    _order = 'code,name'

    code = fields.Char('Codigo', required=True)
    name = fields.Char('Nombre', required=True)
    description = fields.Text('Descripcion', help='Descripcion segun normativa PILA')
    aplicacion_practica = fields.Text('Aplicacion Practica', help='Ejemplos de uso practico')
    referencia_normativa = fields.Char('Referencia Normativa', help='Decreto o Ley de referencia')
    active = fields.Boolean('Activo', default=True)

    _code_uniq = models.Constraint('unique(code)', 'El codigo del tipo de cotizante debe ser unico')

    #Tabla de cotizante 51
    #Documentación - http://aportesenlinea.custhelp.com/app/answers/detail/a_id/464/~/condiciones-cotizante-51
    
    def get_value_cotizante_51(self,year,number_of_days):
        value_return = 0
        number_of_days = round(number_of_days)
        if self.code == '51':
            annual_parameters = self.env['hr.annual.parameters'].get_for_year(
                year,
                company_id=self.env.company.id,
                raise_if_not_found=False,
            )
            if number_of_days >= 1 and number_of_days <= 7:
                value_return = (annual_parameters.smmlv_monthly / 4) * 1
            elif number_of_days >= 8 and number_of_days <= 14:
                value_return = (annual_parameters.smmlv_monthly / 4) * 2
            elif number_of_days >= 15 and number_of_days <= 21:
                value_return = (annual_parameters.smmlv_monthly / 4) * 3
            elif number_of_days >= 22 and number_of_days <= 30:
                value_return = annual_parameters.smmlv_monthly
        return value_return

class HrSubtipoCotizante(models.Model):
    _name = 'hr.subtipo.cotizante'
    _description = 'Subtipos de cotizante'
    _order = 'code,name'

    code = fields.Char('Codigo', required=True)
    name = fields.Char('Novedad', required=True)
    description = fields.Text('Descripcion', help='Descripcion segun normativa PILA')
    aplicacion_practica = fields.Text('Aplicacion Practica', help='Ejemplos de uso practico')
    referencia_normativa = fields.Char('Referencia Normativa', help='Decreto o Ley de referencia')
    not_contribute_pension = fields.Boolean('No aporta pension')
    not_contribute_eps = fields.Boolean('No aporta salud')
    active = fields.Boolean('Activo', default=True)

    _code_uniq = models.Constraint('unique(code)', 'El codigo del subtipo de cotizante debe ser unico')

class HrParameterizationOfContributors(models.Model):
    _name = 'hr.parameterization.of.contributors'
    _description = 'Parametrizacion Cotizantes'

    type_of_contributor = fields.Many2one('hr.tipo.cotizante', string='Tipo de cotizante')
    contributor_subtype = fields.Many2one('hr.subtipo.cotizante', string='Subtipos de cotizante')
    liquidated_eps_employee = fields.Boolean('Liquida EPS Empleado')
    liquidate_employee_pension = fields.Boolean('Liquida Pensión Empleado')
    liquidated_aux_transport = fields.Boolean('Liquida Auxilio de Transporte')
    liquidates_solidarity_fund = fields.Boolean('Liquida Fondo de Solidaridad')
    liquidates_eps_company = fields.Boolean('Liquida EPS Empresa')
    liquidated_company_pension = fields.Boolean('Liquida Pensión Empresa')
    liquidated_arl = fields.Boolean('Liquida ARL')
    liquidated_sena = fields.Boolean('Liquida SENA')
    liquidated_icbf = fields.Boolean('Liquida ICBF')
    liquidated_compensation_fund = fields.Boolean('Liquida Caja de Compensación')
    # Tarifas especiales PILA
    tarifa_especial_pension = fields.Selection([
        ('normal', 'Tarifa Normal (16%)'),
        ('alto_riesgo', 'Alto Riesgo (26%) - Dec. 2090/2003'),
        ('congresista', 'Congresistas (25.5%)'),
        ('cti', 'CTI (35%)'),
        ('aviador', 'Aviadores Civiles (21%)'),
        ('psap', 'PSAP - Subsidio Pensional'),
    ], string='Tarifa Especial Pensión', default='normal',
       help="Tarifa especial de pensión según tipo de cotizante (Res. 2388/2016)")
    tarifa_especial_salud = fields.Selection([
        ('normal', 'Tarifa Normal (12.5%)'),
        ('pensionado_1smmlv', 'Pensionado <= 1 SMMLV (4%)'),
        ('pensionado_3smmlv', 'Pensionado 1-3 SMMLV (10%)'),
        ('pensionado_mas3smmlv', 'Pensionado > 3 SMMLV (12%)'),
    ], string='Tarifa Especial Salud', default='normal',
       help="Tarifa especial de salud según tipo de cotizante")
    porc_subsidio_pension = fields.Float(
        'Porcentaje Subsidio Pensión',
        help="Para cotizantes PSAP: porcentaje que paga el beneficiario (ej: 4% para Madres Comunitarias)"
    )

    _parameterization_type_of_contributor_uniq = models.Constraint('unique(type_of_contributor,contributor_subtype)', 'Ya existe esta parametrizacion de tipo de cotizante y subtipo de cotizante, por favor verficar.')

    @api.depends('type_of_contributor', 'type_of_contributor.name', 'contributor_subtype', 'contributor_subtype.name')
    def _compute_display_name(self):
        for record in self:
            contributor_name = record.type_of_contributor.name if record.type_of_contributor else ''
            subtype_name = record.contributor_subtype.name if record.contributor_subtype else ''
            record.display_name = "Parametrización {} | {}".format(contributor_name, subtype_name)

class HrIndicadorEspecialPila(models.Model):
    _name = 'hr.indicador.especial.pila'
    _description = 'Indicadores especiales para PILA'
    _order = 'code'

    name = fields.Char("Nombre", required=True)
    code = fields.Char('Codigo', required=True)
    active = fields.Boolean('Activo', default=True)

    # Tarifas de Pension
    porc_pension_total = fields.Float(
        'Tarifa Total Pension (%)',
        default=16.0,
        help="Tarifa total de pension (empleado + empresa). Ej: Alto Riesgo=26%, CTI=35%"
    )
    porc_pension_empleado = fields.Float(
        'Tarifa Empleado Pension (%)',
        default=4.0,
        help="Porcentaje que aporta el empleado a pension"
    )
    porc_pension_empresa = fields.Float(
        'Tarifa Empresa Pension (%)',
        compute='_compute_porc_pension_empresa',
        store=True,
        help="Porcentaje que aporta la empresa (calculado automaticamente)"
    )
    porc_pension_adicional = fields.Float(
        'Aporte Adicional Empresa (%)',
        default=0.0,
        help="Porcentaje adicional que paga la empresa (ej: 10% en Alto Riesgo)"
    )

    # Tarifas de Salud
    porc_salud_total = fields.Float(
        'Tarifa Total Salud (%)',
        default=12.5,
        help="Tarifa total de salud"
    )
    porc_salud_empleado = fields.Float(
        'Tarifa Empleado Salud (%)',
        default=4.0,
        help="Porcentaje que aporta el empleado a salud"
    )
    porc_salud_empresa = fields.Float(
        'Tarifa Empresa Salud (%)',
        default=8.5,
        help="Porcentaje que aporta la empresa a salud"
    )

    # Configuracion especial
    aplica_fsp = fields.Boolean(
        'Aplica FSP',
        default=True,
        help="Indica si aplica Fondo de Solidaridad Pensional"
    )
    es_subsidiado = fields.Boolean(
        'Es Subsidiado (PSAP)',
        default=False,
        help="Indica si es un regimen subsidiado (PSAP - Madres Comunitarias, etc.)"
    )
    porc_subsidio = fields.Float(
        'Porcentaje Subsidio (%)',
        default=0.0,
        help="Para PSAP: porcentaje que cubre el Estado"
    )

    # Normativa
    normativa = fields.Char(
        'Normativa',
        help="Decreto o resolucion que establece esta tarifa"
    )
    descripcion = fields.Text('Descripcion')

    # Configuracion de Prestaciones Sociales
    base_dias_prestaciones = fields.Selection([
        ('360', '360 dias'),
        ('365', '365 dias'),
        ('320', '320 dias'),
        ('300', '300 dias'),
    ], string='Base Dias Prestaciones', default='360',
       help="Base de dias para calculo de prestaciones sociales")

    # Vacaciones
    dias_vacaciones = fields.Float(
        'Dias de Vacaciones por Ano',
        default=15.0,
        help="Dias de vacaciones que se pagan por ano trabajado"
    )
    base_dias_vacaciones = fields.Selection([
        ('360', '360 dias'),
        ('365', '365 dias'),
        ('320', '320 dias'),
        ('300', '300 dias'),
    ], string='Base Dias Vacaciones', default='360',
       help="Base de dias para calculo de vacaciones")
    paga_vacaciones = fields.Boolean(
        'Paga Vacaciones',
        default=True,
        help="Indica si este tipo de cotizante tiene derecho a vacaciones"
    )
    dias_vacaciones_proporcional = fields.Float(
        'Dias Vacaciones Proporcional',
        compute='_compute_dias_proporcionales',
        store=True,
        help="Dias de vacaciones ajustados proporcionalmente segun dias trabajados"
    )

    # Prima de Servicios
    dias_prima = fields.Float(
        'Dias de Prima por Semestre',
        default=15.0,
        help="Dias de prima que se pagan por semestre trabajado"
    )
    base_dias_prima = fields.Selection([
        ('360', '360 dias'),
        ('365', '365 dias'),
        ('320', '320 dias'),
        ('300', '300 dias'),
    ], string='Base Dias Prima', default='360',
       help="Base de dias para calculo de prima")
    paga_prima = fields.Boolean(
        'Paga Prima',
        default=True,
        help="Indica si este tipo de cotizante tiene derecho a prima"
    )
    dias_prima_proporcional = fields.Float(
        'Dias Prima Proporcional',
        compute='_compute_dias_proporcionales',
        store=True,
        help="Dias de prima ajustados proporcionalmente segun dias trabajados"
    )

    # Cesantias
    dias_cesantias = fields.Float(
        'Dias de Cesantias por Ano',
        default=30.0,
        help="Dias de cesantias que se pagan por ano trabajado"
    )
    base_dias_cesantias = fields.Selection([
        ('360', '360 dias'),
        ('365', '365 dias'),
        ('320', '320 dias'),
        ('300', '300 dias'),
    ], string='Base Dias Cesantias', default='360',
       help="Base de dias para calculo de cesantias")
    paga_cesantias = fields.Boolean(
        'Paga Cesantias',
        default=True,
        help="Indica si este tipo de cotizante tiene derecho a cesantias"
    )
    dias_cesantias_proporcional = fields.Float(
        'Dias Cesantias Proporcional',
        compute='_compute_dias_proporcionales',
        store=True,
        help="Dias de cesantias ajustados proporcionalmente segun dias trabajados"
    )

    # Intereses de Cesantias
    porc_intereses_cesantias = fields.Float(
        'Porcentaje Intereses Cesantias (%)',
        default=12.0,
        help="Porcentaje de intereses sobre cesantias (12% anual)"
    )
    paga_intereses_cesantias = fields.Boolean(
        'Paga Intereses Cesantias',
        default=True,
        help="Indica si este tipo de cotizante tiene derecho a intereses de cesantias"
    )
    porc_intereses_proporcional = fields.Float(
        'Intereses Proporcional (%)',
        compute='_compute_dias_proporcionales',
        store=True,
        help="Porcentaje de intereses ajustado proporcionalmente"
    )

    # Auxilio de Transporte
    paga_auxilio_transporte = fields.Boolean(
        'Paga Auxilio de Transporte',
        default=True,
        help="Indica si este tipo de cotizante tiene derecho a auxilio de transporte"
    )
    incluye_aux_transporte_prestaciones = fields.Boolean(
        'Incluye Aux. Transporte en Prestaciones',
        default=True,
        help="Incluye el auxilio de transporte en la base de prestaciones sociales"
    )

    # Configuracion de uso
    solo_prestaciones = fields.Boolean(
        'Solo para Prestaciones Sociales',
        default=False,
        help="Si esta marcado, este indicador NO se usa en PILA. "
             "Solo aplica para calculos de prestaciones sociales (prima, cesantias, vacaciones, etc.)"
    )
    no_usar_en_pila = fields.Boolean(
        'No Usar en PILA',
        default=False,
        help="Excluye este indicador del proceso PILA. "
             "Util cuando la configuracion es solo para prestaciones sociales."
    )

    # Dias manuales para proporcionalidad
    usar_dias_manuales = fields.Boolean(
        'Usar Dias Manuales',
        default=False,
        help="Permite especificar dias manualmente para calcular porcentajes proporcionales"
    )
    dias_manuales = fields.Float(
        'Dias Manuales',
        default=30.0,
        help="Dias a usar para calculo proporcional cuando usar_dias_manuales=True"
    )
    dias_base_proporcion = fields.Float(
        'Dias Base Proporcion',
        default=30.0,
        help="Dias base para calcular la proporcion (normalmente 30)"
    )

    # Campos computados para porcentajes proporcionales
    porc_pension_proporcional = fields.Float(
        'Pension Proporcional (%)',
        compute='_compute_porcentajes_proporcionales',
        store=True,
        help="Porcentaje de pension ajustado proporcionalmente segun dias"
    )
    porc_salud_proporcional = fields.Float(
        'Salud Proporcional (%)',
        compute='_compute_porcentajes_proporcionales',
        store=True,
        help="Porcentaje de salud ajustado proporcionalmente segun dias"
    )
    factor_proporcion = fields.Float(
        'Factor Proporcion',
        compute='_compute_porcentajes_proporcionales',
        store=True,
        digits=(16, 6),
        help="Factor de proporcion: dias_manuales / dias_base_proporcion"
    )

    @api.depends('porc_pension_total', 'porc_pension_empleado')
    def _compute_porc_pension_empresa(self):
        for rec in self:
            rec.porc_pension_empresa = rec.porc_pension_total - rec.porc_pension_empleado

    @api.depends('usar_dias_manuales', 'dias_manuales', 'dias_base_proporcion',
                 'porc_pension_total', 'porc_salud_total')
    def _compute_porcentajes_proporcionales(self):
        for rec in self:
            if rec.usar_dias_manuales and rec.dias_base_proporcion > 0:
                factor = rec.dias_manuales / rec.dias_base_proporcion
                rec.factor_proporcion = factor
                rec.porc_pension_proporcional = rec.porc_pension_total * factor
                rec.porc_salud_proporcional = rec.porc_salud_total * factor
            else:
                rec.factor_proporcion = 1.0
                rec.porc_pension_proporcional = rec.porc_pension_total
                rec.porc_salud_proporcional = rec.porc_salud_total

    @api.depends('usar_dias_manuales', 'dias_manuales', 'dias_base_proporcion',
                 'dias_vacaciones', 'dias_prima', 'dias_cesantias', 'porc_intereses_cesantias')
    def _compute_dias_proporcionales(self):
        """
        Calcula los dias de prestaciones de forma proporcional segun los dias manuales.

        Ejemplo:
        - dias_vacaciones = 15 (dias por ano completo)
        - dias_manuales = 20 (dias trabajados)
        - dias_base_proporcion = 30 (dias del mes)
        - Factor = 20/30 = 0.6667
        - dias_vacaciones_proporcional = 15 * 0.6667 = 10 dias
        """
        for rec in self:
            if rec.usar_dias_manuales and rec.dias_base_proporcion > 0:
                factor = rec.dias_manuales / rec.dias_base_proporcion
                rec.dias_vacaciones_proporcional = rec.dias_vacaciones * factor
                rec.dias_prima_proporcional = rec.dias_prima * factor
                rec.dias_cesantias_proporcional = rec.dias_cesantias * factor
                rec.porc_intereses_proporcional = rec.porc_intereses_cesantias * factor
            else:
                rec.dias_vacaciones_proporcional = rec.dias_vacaciones
                rec.dias_prima_proporcional = rec.dias_prima
                rec.dias_cesantias_proporcional = rec.dias_cesantias
                rec.porc_intereses_proporcional = rec.porc_intereses_cesantias

    def get_dias_prestacion(self, tipo_prestacion, dias_trabajados=None, usar_proporcional=None):
        """
        Obtiene los dias a usar para una prestacion especifica.

        Args:
            tipo_prestacion: 'prima', 'cesantias', 'vacaciones', 'intereses'
            dias_trabajados: Dias trabajados (opcional, para proporcion adicional)
            usar_proporcional: Forzar uso de campos proporcionales (None=usar configuracion)

        Returns:
            dict: {
                'dias': float - Dias de la prestacion,
                'dias_base': float - Dias originales (sin proporcion),
                'base_dias': int - Base de dias (360, 365, etc.),
                'paga': bool - Si paga la prestacion,
                'factor': float - Factor de proporcion si aplica,
                'usar_proporcional': bool - Si se usaron valores proporcionales
            }
        """
        self.ensure_one()

        # Determinar si usar proporcional
        if usar_proporcional is None:
            usar_proporcional = self.usar_dias_manuales

        resultado = {
            'dias': 0.0,
            'dias_base': 0.0,
            'base_dias': 360,
            'paga': False,
            'factor': 1.0,
            'usar_proporcional': usar_proporcional,
        }

        if tipo_prestacion == 'prima':
            resultado['dias_base'] = self.dias_prima
            resultado['dias'] = self.dias_prima_proporcional if usar_proporcional else self.dias_prima
            resultado['base_dias'] = int(self.base_dias_prima or '360')
            resultado['paga'] = self.paga_prima
        elif tipo_prestacion == 'cesantias':
            resultado['dias_base'] = self.dias_cesantias
            resultado['dias'] = self.dias_cesantias_proporcional if usar_proporcional else self.dias_cesantias
            resultado['base_dias'] = int(self.base_dias_cesantias or '360')
            resultado['paga'] = self.paga_cesantias
        elif tipo_prestacion == 'vacaciones':
            resultado['dias_base'] = self.dias_vacaciones
            resultado['dias'] = self.dias_vacaciones_proporcional if usar_proporcional else self.dias_vacaciones
            resultado['base_dias'] = int(self.base_dias_vacaciones or '360')
            resultado['paga'] = self.paga_vacaciones
        elif tipo_prestacion == 'intereses':
            resultado['dias_base'] = self.dias_cesantias
            resultado['dias'] = self.dias_cesantias_proporcional if usar_proporcional else self.dias_cesantias
            resultado['base_dias'] = int(self.base_dias_cesantias or '360')
            resultado['paga'] = self.paga_intereses_cesantias
            resultado['porc_intereses'] = self.porc_intereses_proporcional if usar_proporcional else self.porc_intereses_cesantias

        # Calcular factor adicional si hay dias trabajados
        if dias_trabajados is not None and resultado['base_dias'] > 0:
            resultado['factor'] = dias_trabajados / resultado['base_dias']

        return resultado

    def get_porcentaje_proporcional(self, tipo_aporte, dias=None):
        """
        Obtiene el porcentaje proporcional para un tipo de aporte.

        Args:
            tipo_aporte: 'pension', 'salud', 'pension_empleado', 'pension_empresa', etc.
            dias: Dias a usar (opcional, usa dias_manuales si usar_dias_manuales=True)

        Returns:
            float: Porcentaje proporcional
        """
        self.ensure_one()

        # Determinar dias a usar
        if dias is not None:
            dias_usar = dias
        elif self.usar_dias_manuales:
            dias_usar = self.dias_manuales
        else:
            dias_usar = self.dias_base_proporcion

        # Calcular factor
        factor = dias_usar / self.dias_base_proporcion if self.dias_base_proporcion > 0 else 1.0

        # Obtener porcentaje base segun tipo
        porcentaje_map = {
            'pension': self.porc_pension_total,
            'pension_total': self.porc_pension_total,
            'pension_empleado': self.porc_pension_empleado,
            'pension_empresa': self.porc_pension_empresa,
            'pension_adicional': self.porc_pension_adicional,
            'salud': self.porc_salud_total,
            'salud_total': self.porc_salud_total,
            'salud_empleado': self.porc_salud_empleado,
            'salud_empresa': self.porc_salud_empresa,
            'intereses_cesantias': self.porc_intereses_cesantias,
        }

        porcentaje_base = porcentaje_map.get(tipo_aporte, 0.0)
        return porcentaje_base * factor

    _code_unique = models.Constraint('UNIQUE(code)', 'El codigo debe ser unico')

class HrContractSetting(models.Model):
    _name = 'hr.contract.setting'
    _description = 'Configuracion nomina entidades'

    contrib_id = fields.Many2one('hr.contribution.register', 'Tipo Entidad', help='Concepto de aporte', required=True)
    partner_id = fields.Many2one('hr.employee.entities', 'Entidad', help='Entidad relacionada', domain="[('types_entities','in',[contrib_id])]", required=True)
    date_change = fields.Date(string='Fecha de ingreso')
    is_transfer = fields.Boolean(string='Es un Traslado', default=False)
    employee_id = fields.Many2one('hr.employee', 'Empleado', required=True, ondelete='cascade')
    partner_id = fields.Many2one('hr.employee.entities', 'Entidad', help='Entidad relacionada', domain="[('types_entities','in',[contrib_id])]", required=True)

    _emp_type_entity_uniq = models.Constraint('unique(employee_id,contrib_id)', 'El empleado ya tiene una entidad de este tipo, por favor verifique.')

    @api.constrains('employee_id','contrib_id')
    def _check_duplicate_entitites(self):
        for record in self:
            obj_duplicate = self.env['hr.contract.setting'].search([('id','!=',record.id),('employee_id','=',record.employee_id.id),('contrib_id','=',record.contrib_id.id)])

            if len(obj_duplicate) > 0:
                raise ValidationError(_('El empleado ya tiene una entidad de este tipo, por favor verifique.'))

    def write(self, vals):
        for record in self:
            vals_history = {
                'contrib_id': record.contrib_id.id,
                'partner_id': record.partner_id.id,
                'date_change': record.date_change,
                'employee_id': record.employee_id.id,
                'is_transfer': vals.get('is_transfer',False),
                'date_history': vals.get('date_change',fields.Date.today())
            }
            res = super(HrContractSetting, self).write(vals)
            self.env['hr.contract.setting.history'].create(vals_history)
            return res

class HrContractSettingHistory(models.Model):
    _name = 'hr.contract.setting.history'
    _description = 'Configuracion nomina entidades historico'

    contrib_id = fields.Many2one('hr.contribution.register', 'Tipo Entidad', help='Concepto de aporte')
    partner_id = fields.Many2one('hr.employee.entities', 'Entidad', help='Entidad relacionada', domain="[('types_entities','in',[contrib_id])]")
    date_change = fields.Date(string='Fecha de ingreso')
    is_transfer = fields.Boolean(string='Es un Traslado')
    employee_id = fields.Many2one('hr.employee', 'Empleado', required=True, ondelete='cascade')

    date_history = fields.Date(string='Fecha historico')

class HrEmployeeDependents(models.Model):
    _name = 'hr.employee.dependents'
    _description = 'Dependientes de los empleados'

    employee_id = fields.Many2one('hr.employee', 'Empleado', required=True, ondelete='cascade')
    name = fields.Char('Nombre completo', required=True)
    genero = fields.Selection([('masculino', 'Masculino'),
                               ('femenino', 'Femenino'),
                               ('otro', 'Otro')],'Genero')
    date_birthday = fields.Date('Fecha de nacimiento')
    dependents_type = fields.Selection([('hijo', 'Hijo(a)'),
                                        ('padre', 'Padre'),
                                        ('madre', 'Madre'),
                                        ('conyuge', 'Cónyuge'),
                                        ('hermano', 'Hermano(a)'),
                                        ('otro', 'Otro')], 'Tipo')
    document_type = fields.Selection([
        ('11', 'Registro civil de nacimiento'),
        ('12', 'Tarjeta de identidad'),
        ('13', 'Cédula de ciudadanía'),
        ('21', 'Tarjeta de extranjería'),
        ('22', 'Cedula de extranjería'),
        ('31', 'NIT'),
        ('41', 'Pasaporte'),
        ('42', 'Tipo de documento extranjero'),
        ('43', 'Sin identificación del exterior o para uso definido por la DIAN'),
        ('44', 'Documento de identificación extranjero persona jurídica'),
        ('PE', 'Permiso especial de permanencia'),
        ('PT', 'Permiso por Protección Temporal')
    ], string='Tipo de documento',default='13')
    vat = fields.Char(string='Número de documento')
    phone = fields.Integer(string='Teléfono')
    address = fields.Char(string='Dirección')
    report_income_and_withholdings = fields.Boolean(string='Reportar en Certificado ingresos y retenciones')

class HrEmployeeLaborUnion(models.Model):
    _name = 'hr.employee.labor.union'
    _description = 'Sindicato de empleados'
    
    employee_id = fields.Many2one('hr.employee', 'Empleado', required=True, ondelete='cascade')
    name_labor_union = fields.Char('Nombre del sindicato', required=True)
    afiliado = fields.Boolean('Afiliado', help='Indica si el empelado esta afiliado a un sindicato')
    fuero = fields.Boolean('Fuero sindical', help='Indica si el empelado cuenta con un fuero sindical')
    cargo_sindicato = fields.Char('Cargo dentro del sindicato')

class HrEmployeeDocuments(models.Model):
    _name = 'hr.employee.documents'
    _description = 'Documentos del empleado'

    employee_id = fields.Many2one('hr.employee','Empleado', required=True, ondelete='cascade')
    name = fields.Char('Descripción', required=True)
    expiration_date = fields.Date('Fecha de vencimiento')
    document = fields.Many2one('documents.document', string='Documento', required=True)

    def unlink(self):
        obj_document = self.document
        obj = super(HrEmployeeDocuments, self).unlink()
        obj_document.unlink()
        return obj

class HrCostDistributionEmployee(models.Model):
    _name = 'hr.cost.distribution.employee'
    _description = 'Distribucion de costos empleados'

    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True)
    analytic_account_id = fields.Many2one('account.analytic.account', string='Cuenta analítica', required=True)
    porcentage = fields.Float(string='Porcentaje', required=True)

    _change_distribution_analytic_uniq = models.Constraint('unique(employee_id,analytic_account_id)',
                                                           'Ya existe una cuenta analítica asignada, por favor verificar')

class HrEmployeeSanctions(models.Model):
    _name = 'hr.employee.sanctions'
    _description = 'Sanciones'

    employee_id = fields.Many2one('hr.employee', string='Empleado')
    company_id = fields.Many2one(related='employee_id.company_id', string='Compañía', store=True)
    work_contact_id = fields.Many2one(related='employee_id.work_contact_id', string='Tercero asociado', store=True)
    document_id = fields.Many2one('documents.document', string='Documento')
    absence_id = fields.Many2one('hr.leave', string='Ausencia')
    registration_date = fields.Date(string='Fecha de registro')
    type_fault_id = fields.Many2one('hr.types.faults', string='Tipo de falta')
    name = fields.Char(string='Observación')
    stage = fields.Selection([('1', 'Comunicación'),
                              ('2', 'Descargos'),
                              ('3', 'Pronunciamiento'),
                              ('4', 'Sanción'),
                              ('5', 'Cancelar'),
                              ], string='Estado')


class HrEmployee(models.Model):
    _inherit = 'hr.employee'
    show_in_portal = fields.Boolean('Mostrar en Portal', default=True)
    portal_access_token = fields.Char('Token de Acceso Portal', copy=False)
    
    #Trazabilidad
    work_email = fields.Char(tracking=True)
    company_id = fields.Many2one('res.company', tracking=True)
    department_id = fields.Many2one('hr.department', tracking=True)
    job_id = fields.Many2one('hr.job', tracking=True)
    parent_id = fields.Many2one('hr.employee', tracking=True)
    address_id = fields.Many2one('res.partner', tracking=True)
    resource_calendar_id = fields.Many2one('resource.calendar',
                                           domain="[('type_working_schedule', '=', 'employees'),'|', ('company_id', '=', False), ('company_id', '=', company_id)]",tracking=True)
    #Asignación
    analytic_account_id = fields.Many2one('account.analytic.account', 'Cuenta analítica', tracking=True)
    front_back = fields.Selection([('front','Front office'),('back','Back office')],'Area laboral', tracking=True)
    confianza_manejo = fields.Boolean('Confianza y manejo', tracking=True)
    info_project = fields.Char(string='Proyecto')
    #Evaluación de desempeño
    ed_qualification = fields.Float(string='Calificación', tracking=True)
    ed_observation = fields.Text(string='Observaciones', tracking=True)
    #General
    partner_encab_id = fields.Many2one('res.partner', 'Tercero', help='Tercero equivalente a el empleado')
    # Usar employee_type nativo de Odoo (Selection: employee, student, trainee, contractor, freelance)
    sabado = fields.Boolean('Sábado día hábil', help='Indica si el día sábado se incluye como día hábil', tracking=True)

    # Campo para ocultar secciones especificas de Colombia
    is_colombian_company = fields.Boolean(
        string='Empresa Colombiana',
        compute='_compute_is_colombian_company',
        store=False,
        help='Indica si la empresa es colombiana para mostrar/ocultar campos especificos'
    )

    @api.depends('company_id', 'company_id.country_id')
    def _compute_is_colombian_company(self):
        for employee in self:
            country = employee.company_id.country_id or self.env.company.country_id
            employee.is_colombian_company = country.code == 'CO' if country else False

    # Campos relacionados del contrato actual para mostrar en vista empleado
    contract_type_rel = fields.Many2one(
        'hr.contract.type',
        string='Tipo de Contrato',
        related='contract_id.contract_type_id',
        store=True,
        help='Tipo de contrato del empleado'
    )
    risk_level_rel = fields.Many2one(
        'hr.contract.risk',
        string='Nivel de Riesgo ARL',
        related='contract_id.risk_id',
        store=True,
        help='Nivel de riesgo profesional del contrato'
    )
    economic_activity_rel = fields.Many2one(
        'lavish.economic.activity.level.risk',
        string='Actividad Economica',
        related='contract_id.economic_activity_level_risk_id',
        store=True,
        help='Actividad economica por nivel de riesgo'
    )

    # Horario semanal asociado
    working_hours_id = fields.Many2one(
        'hr.company.working.hours',
        string='Horario Laboral',
        tracking=True,
        help='Horario laboral asociado al empleado'
    )

    # Campos computados desde el horario
    auto_works_saturday = fields.Boolean(
        string='Trabaja Sábados (Automático)',
        compute='_compute_auto_works_saturday',
        store=True,
        help='Se activa automáticamente según el horario laboral configurado'
    )

    @api.model
    def _get_certificate_selection_lavish(self):
        base_selection = list(self._get_certificate_selection() or [])
        extra_selection = [
            ('primary', 'Primaria'),
            ('academic_bachelor', 'Bachiller'),
            ('technical', 'Técnico'),
            ('technologist', 'Tecnólogo'),
            ('academic', 'Profesional Universitario'),
            ('specialist', 'Especialista'),
            ('magister', 'Magister'),
            ('doctor', 'Doctor'),
            ('graduate', 'Licenciado'),
            ('bachelor', 'Graduado'),
            ('master', 'Maestro'),
            ('other', 'Otro'),
        ]
        existing_keys = {key for key, _label in base_selection}
        for option in extra_selection:
            if option[0] not in existing_keys:
                base_selection.append(option)
        return base_selection

    certificate = fields.Selection(
        selection='_get_certificate_selection_lavish',
        string='Nivel de certificado',
        default='primary',
        tracking=True,
    )
    social_security_entities  = fields.One2many('hr.contract.setting', 'employee_id', string = 'Entidades', tracking=True)
    dependents_information = fields.One2many('hr.employee.dependents', 'employee_id', string = 'Dependientes', tracking=True)
    labor_union_information = fields.One2many('hr.employee.labor.union', 'employee_id', string = 'Sindicato', tracking=True)
    personal_email = fields.Char(string='Correo-e personal', tracking=True)
    personal_mobile = fields.Char(string='Móvil', tracking=True)
    type_job = fields.Selection([('clave', 'Cargo Clave'),
                                    ('critico', 'Cargo Crítico'),
                                    ('cc', 'Cargo CC')], 'Tipo de cargo', tracking=True)
    emergency_relationship = fields.Char(string='Parentesco contacto')
    documents_ids = fields.One2many('hr.employee.documents', 'employee_id', 'Documentos')
    distribution_cost_information = fields.One2many('hr.cost.distribution.employee', 'employee_id', string='Distribución de costos empleado')
    #PILA
    extranjero = fields.Boolean('Extranjero', help='Extranjero no obligado a cotizar a pensión', tracking=True)
    residente = fields.Boolean('Residente en el Exterior', help='Colombiano residente en el exterior', tracking=True)
    date_of_residence_abroad = fields.Date(string='Fecha radicación en el exterior', tracking=True)
    tipo_coti_id = fields.Many2one('hr.tipo.cotizante', string='Tipo de cotizante', tracking=True)
    subtipo_coti_id = fields.Many2one('hr.subtipo.cotizante', string='Subtipo de cotizante', tracking=True)

    def should_contribute_social_security(self, contribution_type='all'):
        """
        Método centralizado para validar si el empleado debe cotizar a seguridad social.

        Combina validaciones de:
        - Tipo y subtipo de cotizante
        - Parametrización de cotizantes (hr.parameterization.of.contributors)
        - Tipo de contrato

        Args:
            contribution_type (str): 'salud', 'pension', o 'all'

        Returns:
            dict o bool:
                - Si contribution_type='all': {'salud': bool, 'pension': bool}
                - Si contribution_type='salud' o 'pension': bool
        """
        self.ensure_one()

        if not self.tipo_coti_id or not self.subtipo_coti_id:
            result = {'salud': True, 'pension': True, 'parameterization': None}
            return result if contribution_type == 'all' else result.get(contribution_type, True)

        parameterization = self.env['hr.parameterization.of.contributors'].search([
            ('type_of_contributor', '=', self.tipo_coti_id.id),
            ('contributor_subtype', '=', self.subtipo_coti_id.id)
        ], limit=1)

        contribuye_salud = True

        if self.subtipo_coti_id.not_contribute_eps:
            contribuye_salud = False
        elif parameterization:
            if not parameterization.liquidated_eps_employee:
                contribuye_salud = False

        contribuye_pension = True

        if self.subtipo_coti_id.not_contribute_pension:
            contribuye_pension = False
        elif parameterization:
            if not (parameterization.liquidate_employee_pension or
                    parameterization.liquidated_company_pension or
                    parameterization.liquidates_solidarity_fund):
                contribuye_pension = False

        result = {
            'salud': contribuye_salud,
            'pension': contribuye_pension,
            'parameterization': parameterization if parameterization else None
        }

        if contribution_type == 'all':
            return result
        else:
            return result.get(contribution_type, True)

    type_identification = fields.Selection([('CC', 'Cédula de ciudadanía'),
                                            ('CE', 'Cédula de extranjería'),
                                            ('TI', 'Tarjeta de identidad'),
                                            ('RC', 'Registro civil'),
                                            ('PA', 'Pasaporte')], 'Tipo de identificación', tracking=True)
    indicador_especial_id = fields.Many2one('hr.indicador.especial.pila','Indicador tarifa especial pensiones', tracking=True)
    cost_assumed_by  = fields.Selection([('partner', 'Cliente'),
                                        ('company', 'Compañía')], 'Costo asumido por', tracking=True)
    #Licencia de conducción
    licencia_rh = fields.Selection([('op','O+'),('ap','A+'),('bp','B+'),('abp','AB+'),('on','O-'),('an','A-'),('bn','B-'),('abn','AB-')],'Tipo de sangre', tracking=True)
    licencia_categoria = fields.Selection([('a1','A1'),('a2','A2'),('b1','B1'),('b2','B2'),('b3','B3'),('c1','C1'),('c2','C2'),('c3','C3')],'Categoria', tracking=True)
    licencia_vigencia = fields.Date('Vigencia', tracking=True)
    licencia_restricciones = fields.Char('Restricciones', size=255, tracking=True)
    operacion_retirar = fields.Boolean('Retirar de la operacion', tracking=True)
    operacion_reemplazo = fields.Many2one('hr.employee','Reemplazo', tracking=True)
    #Estado civil
    type_identification_spouse = fields.Selection([('CC', 'Cédula de ciudadanía'),
                                            ('CE', 'Cédula de extranjería'),
                                            ('TI', 'Tarjeta de identidad'),
                                            ('RC', 'Registro civil'),
                                            ('PA', 'Pasaporte')], 'Tipo de identificación cónyuge', tracking=True)
    num_identification_spouse = fields.Char('Número de identificación cónyuge', tracking=True)
    spouse_phone= fields.Char('Teléfono del cónyuge', tracking=True)
    #Sanciones
    employee_sanctions_ids = fields.One2many('hr.employee.sanctions', 'employee_id', string='Sanciones')
    #Edad
    employee_age = fields.Integer(string='Edad', compute='_get_employee_age', store=True)
    # Campos Caracterizacion
    stratum = fields.Selection([('1', '1'),
                                  ('2', '2'),
                                  ('3', '3'),
                                  ('4', '4'),
                                  ('5', '5'),
                                  ('6', '6')], string='Estrato', tracking=True)
    sexual_orientation = fields.Selection([('heterosexual', 'Heterosexual'),
                                             ('bisexual', 'Bisexual'),
                                             ('homosexual', 'Homosexual'),
                                             ('pansexual', 'Pansexual'),
                                             ('asexual', 'Asexual'),
                                             ('other', 'Otro')], string='Orientación Sexual', tracking=True)
    sexual_orientation_other = fields.Char(string="¿Cual?", tracking=True)
    ethnic_group = fields.Selection([('none', 'Ninguno'),
                                       ('indigenous', 'Indígena'),
                                       ('afrocolombian', 'Afrocolombiano'),
                                       ('gypsy', 'Gitano'),
                                       ('raizal', 'Raizal')], string='Grupo étnico', tracking=True)
    housing_area = fields.Selection([('rural', 'Rural'),
                                       ('urban', 'Urbana')], string='Zona de Vivienda', tracking=True)
    health_risk_factors = fields.Char(string="Factores de riesgo en salud", tracking=True)
    religion = fields.Char(string="Religión", tracking=True)
    victim_armed_conflict = fields.Selection([('yes', 'Si'),
                                                ('not', 'No')], string='Victima del conflicto armado', tracking=True)
    academic_data= fields.Char(string="Datos académicos", tracking=True)
    city_birth_id = fields.Many2one('res.city',string="Ciudad de nacimiento",domain="[('state_id', '=', department_birth_id)]", tracking=True)
    department_birth_id = fields.Many2one('res.country.state',string="Departamento de nacimiento", domain="[('country_id', '=', country_id)]", tracking=True)
    military_passbook = fields.Boolean('Libreta militar', tracking=True)
    identification_id = fields.Char(string='CC / PT/ ID', compute="_compute_cc",store=True, readonly=False)

    # Tipo de documento por defecto: Cedula de Ciudadania (CC) para Colombia
    l10n_latam_identification_type_id = fields.Many2one('l10n_latam.identification.type',
        string="Tipo documento", index='btree_not_null',
        default=lambda self: self._get_default_identification_type(),
        help="Tipo de documento de identificacion",
        tracking=True)

    # Pais por defecto: Colombia o el pais de la empresa
    country_id = fields.Many2one(
        'res.country',
        string='Pais',
        default=lambda self: self._get_default_country(),
        help='Pais de residencia del empleado',
        tracking=True
    )

    @api.model
    def _get_default_identification_type(self):
        """Obtiene el tipo de documento por defecto: CC para Colombia"""
        # Primero intentar CC de Colombia
        cc_ref = self.env.ref('l10n_co.national_citizen_id', raise_if_not_found=False)
        if cc_ref:
            return cc_ref
        # Fallback a VAT generico
        return self.env.ref('l10n_latam_base.it_vat', raise_if_not_found=False)

    @api.model
    def _get_default_country(self):
        """Obtiene el pais por defecto: pais de la empresa o Colombia"""
        if self.env.company.country_id:
            return self.env.company.country_id
        return self.env.ref('base.co', raise_if_not_found=False)

    # Campos sincronizados bidireccionales con work_contact_id (res.partner)
    # Si se llena desde empleado → actualiza contacto
    # Si contacto está vacío → toma del empleado
    # Si empleado está vacío → toma del contacto
    first_name = fields.Char(
        string='Primer Nombre',
        compute='_compute_partner_name_fields',
        inverse='_inverse_first_name',
        store=True,
        tracking=True
    )
    middle_name = fields.Char(
        string='Segundo Nombre',
        compute='_compute_partner_name_fields',
        inverse='_inverse_middle_name',
        store=True,
        tracking=True
    )
    surname = fields.Char(
        string='Primer Apellido',
        compute='_compute_partner_name_fields',
        inverse='_inverse_surname',
        store=True,
        tracking=True
    )
    mother_name = fields.Char(
        string='Segundo Apellido',
        compute='_compute_partner_name_fields',
        inverse='_inverse_mother_name',
        store=True,
        tracking=True
    )
    commercial_name = fields.Char(
        string='Nombre Comercial',
        compute='_compute_partner_name_fields',
        inverse='_inverse_commercial_name',
        store=True,
        tracking=True
    )

    # ========== CAMPOS DE DIRECCION PRIVADA SINCRONIZADOS CON WORK_CONTACT_ID ==========
    # Estos campos extienden los private_* nativos de Odoo
    # Se sincronizan bidirecccionalmente con el res.partner asociado (work_contact_id)
    # Usan la logica de lavish_erp para barrios y direcciones estructuradas colombianas

    # Ciudad como Many2one (extiende private_city nativo que es Char)
    private_city_id = fields.Many2one(
        comodel_name='res.city',
        string='Ciudad',
        compute='_compute_private_address_fields',
        inverse='_inverse_private_city_id',
        store=True,
        tracking=True,
        groups="hr.group_hr_user",
        domain="[('country_id', '=?', private_country_id)]",
        help='Ciudad de residencia privada del empleado'
    )

    # Barrio - sincronizado con partner (campo Many2one de lavish_erp)
    private_neighborhood_id = fields.Many2one(
        comodel_name='res.city.neighborhood',
        string='Barrio',
        compute='_compute_private_address_fields',
        inverse='_inverse_private_neighborhood_id',
        store=True,
        tracking=True,
        groups="hr.group_hr_user",
        domain="[('city_id', '=', private_city_id)]",
        help='Barrio de residencia del empleado'
    )

    # Nombre del barrio - texto libre sincronizado con partner
    private_barrio = fields.Char(
        string='Nombre Barrio',
        compute='_compute_private_address_fields',
        inverse='_inverse_private_barrio',
        store=True,
        tracking=True,
        groups="hr.group_hr_user",
        help='Nombre del barrio (texto libre)'
    )

    # Codigo postal como Many2one (extiende private_zip nativo que es Char)
    private_postal_code_id = fields.Many2one(
        comodel_name='res.city.postal',
        string='Codigo Postal',
        compute='_compute_private_address_fields',
        inverse='_inverse_private_postal_code_id',
        store=True,
        tracking=True,
        groups="hr.group_hr_user",
        domain="[('city_id', '=', private_city_id)]",
        help='Codigo postal de residencia'
    )

    # Direccion completa (solo lectura - computada)
    private_full_address = fields.Char(
        string='Direccion Completa',
        compute='_compute_private_full_address',
        store=True,
        groups="hr.group_hr_user",
        help='Direccion completa incluyendo ciudad y pais'
    )

    _emp_identification_uniq = models.Constraint('unique(company_id,identification_id)', 'La cédula debe ser unica. La cédula ingresada ya existe en esta compañía')

    def _compute_partner_name_fields(self):
        """Obtiene valores del contacto si existen, sino mantiene los del empleado"""
        for employee in self:
            # Verificar si el campo work_contact_id existe (depende del módulo hr_contract)
            if hasattr(employee, 'work_contact_id') and employee.work_contact_id:
                # Usar campos reales de res.partner: first_name, second_name, first_lastname, second_lastname, business_name
                if hasattr(employee.work_contact_id, 'first_name') and employee.work_contact_id.first_name:
                    employee.first_name = employee.work_contact_id.first_name
                if hasattr(employee.work_contact_id, 'second_name') and employee.work_contact_id.second_name:
                    employee.middle_name = employee.work_contact_id.second_name
                if hasattr(employee.work_contact_id, 'first_lastname') and employee.work_contact_id.first_lastname:
                    employee.surname = employee.work_contact_id.first_lastname
                if hasattr(employee.work_contact_id, 'second_lastname') and employee.work_contact_id.second_lastname:
                    employee.mother_name = employee.work_contact_id.second_lastname
                if hasattr(employee.work_contact_id, 'business_name') and employee.work_contact_id.business_name:
                    employee.commercial_name = employee.work_contact_id.business_name

    def _inverse_first_name(self):
        """Actualiza el contacto cuando se modifica desde el empleado"""
        for employee in self:
            if hasattr(employee, 'work_contact_id') and employee.work_contact_id:
                if hasattr(employee.work_contact_id, 'first_name'):
                    employee.work_contact_id.first_name = employee.first_name

    def _inverse_middle_name(self):
        """Actualiza el contacto cuando se modifica desde el empleado"""
        for employee in self:
            if hasattr(employee, 'work_contact_id') and employee.work_contact_id:
                if hasattr(employee.work_contact_id, 'second_name'):
                    employee.work_contact_id.second_name = employee.middle_name

    def _inverse_surname(self):
        """Actualiza el contacto cuando se modifica desde el empleado"""
        for employee in self:
            if hasattr(employee, 'work_contact_id') and employee.work_contact_id:
                if hasattr(employee.work_contact_id, 'first_lastname'):
                    employee.work_contact_id.first_lastname = employee.surname

    def _inverse_mother_name(self):
        """Actualiza el contacto cuando se modifica desde el empleado"""
        for employee in self:
            if hasattr(employee, 'work_contact_id') and employee.work_contact_id:
                if hasattr(employee.work_contact_id, 'second_lastname'):
                    employee.work_contact_id.second_lastname = employee.mother_name

    def _inverse_commercial_name(self):
        """Actualiza el contacto cuando se modifica desde el empleado"""
        for employee in self:
            if hasattr(employee, 'work_contact_id') and employee.work_contact_id:
                if hasattr(employee.work_contact_id, 'business_name'):
                    employee.work_contact_id.business_name = employee.commercial_name

    # ========== METODOS COMPUTE/INVERSE PARA DIRECCIONES PRIVADAS ==========

    @api.depends(
        'work_contact_id',
        'work_contact_id.city_id',
        'work_contact_id.state_id',
        'work_contact_id.neighborhood_id',
        'work_contact_id.barrio',
        'work_contact_id.postal_code_id'
    )
    def _compute_private_address_fields(self):
        """Obtiene valores de direccion del contacto si existen y los sincroniza con campos private_"""
        for employee in self:
            if hasattr(employee, 'work_contact_id') and employee.work_contact_id:
                partner = employee.work_contact_id
                # Ciudad (Many2one)
                if hasattr(partner, 'city_id') and partner.city_id:
                    employee.private_city_id = partner.city_id
                    # Sincronizar tambien con private_city nativo (Char)
                    employee.private_city = partner.city_id.name
                # Departamento - sincronizar con private_state_id nativo
                if hasattr(partner, 'state_id') and partner.state_id:
                    employee.private_state_id = partner.state_id
                # Pais - sincronizar con private_country_id nativo
                if hasattr(partner, 'country_id') and partner.country_id:
                    employee.private_country_id = partner.country_id
                # Barrio (Many2one)
                if hasattr(partner, 'neighborhood_id') and partner.neighborhood_id:
                    employee.private_neighborhood_id = partner.neighborhood_id
                # Barrio (texto)
                if hasattr(partner, 'barrio') and partner.barrio:
                    employee.private_barrio = partner.barrio
                # Codigo postal (Many2one)
                if hasattr(partner, 'postal_code_id') and partner.postal_code_id:
                    employee.private_postal_code_id = partner.postal_code_id
                    # Sincronizar tambien con private_zip nativo (Char)
                    employee.private_zip = partner.postal_code_id.postal_code
                # Direccion - sincronizar con private_street nativo
                if hasattr(partner, 'street') and partner.street:
                    employee.private_street = partner.street

    @api.depends(
        'work_contact_id',
        'work_contact_id.full_address',
        'private_city_id',
        'private_state_id',
        'private_street',
        'private_country_id',
        'private_barrio'
    )
    def _compute_private_full_address(self):
        """Computa la direccion privada completa del empleado"""
        for employee in self:
            # Intentar obtener del partner primero
            if hasattr(employee, 'work_contact_id') and employee.work_contact_id:
                if hasattr(employee.work_contact_id, 'full_address') and employee.work_contact_id.full_address:
                    employee.private_full_address = employee.work_contact_id.full_address
                    continue

            # Si no hay full_address en partner, construir manualmente
            parts = []
            if employee.private_street:
                parts.append(employee.private_street)
            if employee.private_barrio:
                parts.append(f"Barrio {employee.private_barrio}")
            if employee.private_city_id:
                parts.append(employee.private_city_id.name)
            elif employee.private_city:
                parts.append(employee.private_city)
            if employee.private_state_id:
                parts.append(employee.private_state_id.name)
            if employee.private_country_id:
                parts.append(employee.private_country_id.name)

            employee.private_full_address = ', '.join(filter(None, parts))

    def _inverse_private_city_id(self):
        """Actualiza la ciudad en el contacto y sincroniza campos nativos"""
        for employee in self:
            # Sincronizar con private_city nativo
            if employee.private_city_id:
                employee.private_city = employee.private_city_id.name
            # Actualizar partner
            if hasattr(employee, 'work_contact_id') and employee.work_contact_id:
                if hasattr(employee.work_contact_id, 'city_id'):
                    employee.work_contact_id.city_id = employee.private_city_id
                if hasattr(employee.work_contact_id, 'city') and employee.private_city_id:
                    employee.work_contact_id.city = employee.private_city_id.name

    def _inverse_private_neighborhood_id(self):
        """Actualiza el barrio (Many2one) en el contacto"""
        for employee in self:
            if hasattr(employee, 'work_contact_id') and employee.work_contact_id:
                if hasattr(employee.work_contact_id, 'neighborhood_id'):
                    employee.work_contact_id.neighborhood_id = employee.private_neighborhood_id
                    # Si el barrio tiene codigo postal, actualizarlo
                    if employee.private_neighborhood_id and employee.private_neighborhood_id.postal_code_id:
                        employee.private_postal_code_id = employee.private_neighborhood_id.postal_code_id

    def _inverse_private_barrio(self):
        """Actualiza el nombre del barrio (texto) en el contacto"""
        for employee in self:
            if hasattr(employee, 'work_contact_id') and employee.work_contact_id:
                if hasattr(employee.work_contact_id, 'barrio'):
                    employee.work_contact_id.barrio = employee.private_barrio

    def _inverse_private_postal_code_id(self):
        """Actualiza el codigo postal en el contacto y sincroniza con private_zip"""
        for employee in self:
            # Sincronizar con private_zip nativo
            if employee.private_postal_code_id:
                employee.private_zip = employee.private_postal_code_id.postal_code
            # Actualizar partner
            if hasattr(employee, 'work_contact_id') and employee.work_contact_id:
                if hasattr(employee.work_contact_id, 'postal_code_id'):
                    employee.work_contact_id.postal_code_id = employee.private_postal_code_id
                if hasattr(employee.work_contact_id, 'zip') and employee.private_postal_code_id:
                    employee.work_contact_id.zip = employee.private_postal_code_id.postal_code

    @api.onchange('private_city_id')
    def _onchange_private_city_id(self):
        """Al cambiar la ciudad, actualizar el departamento automaticamente"""
        for employee in self:
            if employee.private_city_id:
                employee.private_state_id = employee.private_city_id.state_id
                employee.private_country_id = employee.private_city_id.country_id
                employee.private_city = employee.private_city_id.name
                # Limpiar barrio si no corresponde a la ciudad
                if employee.private_neighborhood_id and employee.private_neighborhood_id.city_id != employee.private_city_id:
                    employee.private_neighborhood_id = False
                # Limpiar codigo postal si no corresponde a la ciudad
                if employee.private_postal_code_id and employee.private_postal_code_id.city_id != employee.private_city_id:
                    employee.private_postal_code_id = False

    @api.onchange('private_neighborhood_id')
    def _onchange_private_neighborhood_id(self):
        """Al seleccionar barrio, actualizar ciudad y codigo postal"""
        for employee in self:
            if employee.private_neighborhood_id:
                if employee.private_neighborhood_id.city_id:
                    employee.private_city_id = employee.private_neighborhood_id.city_id
                if employee.private_neighborhood_id.postal_code_id:
                    employee.private_postal_code_id = employee.private_neighborhood_id.postal_code_id
                # Actualizar nombre de barrio si esta vacio
                if not employee.private_barrio and employee.private_neighborhood_id.name:
                    employee.private_barrio = employee.private_neighborhood_id.name

    def action_open_partner_address_builder(self):
        """Abre el formulario del partner asociado para usar el constructor de direcciones"""
        self.ensure_one()
        if not self.work_contact_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Sin tercero asociado',
                    'message': 'Debe asociar un tercero (work_contact_id) antes de construir la direccion.',
                    'type': 'warning',
                    'sticky': False,
                }
            }
        return {
            'type': 'ir.actions.act_window',
            'name': 'Editar Direccion del Tercero',
            'res_model': 'res.partner',
            'res_id': self.work_contact_id.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'form_view_initial_mode': 'edit',
                'default_type': 'private',
            },
        }

    def _get_contracts(self, date_from, date_to, states=['open','finished'], kanban_state=False):
        """
        Returns the contracts of the employee between date_from and date_to
        """
        state_domain = [('state', 'in', states)]
        if kanban_state:
            state_domain = expression.AND([state_domain, [('kanban_state', 'in', kanban_state)]])

        return self.env['hr.contract'].search(
            expression.AND([[('employee_id', 'in', self.ids)],
            state_domain,
            [('date_start', '<=', date_to),
                '|',
                    ('date_end', '=', False),
                    ('date_end', '>=', date_from)]]))

    @api.depends('work_contact_id', 'work_contact_id.vat_co')
    def _compute_cc(self):
        for record in self:
            if record.work_contact_id and record.work_contact_id.vat_co:
                record.identification_id = record.work_contact_id.vat_co
            else:
                record.identification_id = False

    @api.onchange('dependents_information')
    def _onchange_partner_dependents(self):
        for record in self:
            if record.contract_id:
                if  record.dependents_information.filtered(lambda line: line.report_income_and_withholdings):
                    record.contract_id.ded_dependents = True
                else:
                    record.contract_id.ded_dependents = False


    @api.onchange('partner_encab_id')
    def _onchange_partner_encab(self):
        for record in self:
            for partner in record.partner_encab_id:
                self.work_contact_id = partner.id
    @api.model
    def _name_search(self, name, args=None, operator='ilike',
                     limit=100, name_get_uid=None,order=None):
        args = args or []
        if operator == 'ilike' and not (name or '').strip():
            domain = []
        else:
            domain = ['|', ('name', 'ilike', name),
                      ('identification_id', 'ilike', name)]
        return self._search(expression.AND([domain, args]),
                            limit=limit, order=order,
                            access_rights_uid=name_get_uid)

    def get_selection_label(self, field_name):
        """
        Obtiene la etiqueta en español de un campo Selection usando _description_selection().

        Args:
            field_name (str): Nombre del campo Selection

        Returns:
            str: Etiqueta del valor actual del campo en español, o '' si no existe

        Ejemplo:
            employee.get_selection_label('type_identification')  # Retorna 'Cédula de ciudadanía'
        """
        if field_name not in self._fields:
            return ''
        field = self._fields[field_name]
        if field.type != 'selection':
            return ''
        field_value = getattr(self, field_name, False)
        if not field_value:
            return ''
        selection_list = field._description_selection(self.env)
        selection_dict = dict(selection_list)
        return selection_dict.get(field_value, '')

    def _create_work_contacts(self):
        if any(employee.work_contact_id for employee in self):
            raise UserError(_('Some employee already have a work contact'))
        work_contacts = self.env['res.partner'].create([{
            'l10n_latam_identification_type_id': employee.l10n_latam_identification_type_id.id,
            'email': employee.work_email,
            'mobile': employee.mobile_phone,
            'phone': employee.private_phone,
            'name': employee.name,
            'image_1920': employee.image_1920,
            'company_id': employee.company_id.id,
            'street': employee.private_street,
            'street2': employee.private_street2,
            'city': employee.private_city,
            'city_id': employee.private_city_id.id if employee.private_city_id else False,
            'state_id': employee.private_state_id.id,
            'zip': employee.private_zip,
            'country_id': employee.country_id.id,
            'vat': employee.identification_id,
        } for employee in self])
        for employee, work_contact in zip(self, work_contacts):
            employee.work_contact_id = work_contact

    @api.onchange('work_contact_id', 'private_city_id', 'l10n_latam_identification_type_id',
                  'work_email','private_street','private_street2','mobile_phone','name','country_id',
                  'private_phone','private_state_id','private_city','identification_id')
    def _onchange_work_contact(self):
        if self.work_contact_id:
            self._inverse_work_contact_details()

    @api.onchange('first_name', 'middle_name', 'surname', 'mother_name')
    def _onchange_person_names(self):
        partner = self.work_contact_id
        if partner and partner.company_type == 'person':
            names = [name for name in [self.first_name, self.middle_name, self.surname, self.mother_name] if name]
            self.name = u' '.join(names)


    def _inverse_work_contact_details(self):
        employees_without_work_contact = self.env['hr.employee']
        for employee in self:
            if not employee.work_contact_id:
                employees_without_work_contact += employee
            else:
                employee.work_contact_id.sudo().write({
                    'l10n_latam_identification_type_id': employee.l10n_latam_identification_type_id.id,
                    'email': employee.work_email,
                    'mobile': employee.mobile_phone,
                    'phone': employee.private_phone,
                    'name': employee.name,
                    'street': employee.private_street,
                    'street2': employee.private_street2,
                    'city': employee.private_city,
                    'city_id': employee.private_city_id.id if employee.private_city_id else False,
                    'state_id': employee.private_state_id.id,
                    'zip': employee.private_zip,
                    'country_id': employee.country_id.id,
                    'vat': employee.identification_id,
                    'vat_co': employee.identification_id,
                })
        if employees_without_work_contact:
            employees_without_work_contact.sudo()._create_work_contacts()

    @api.onchange('work_contact_id')
    def _onchange_tercero_asociado(self):
        for record in self:
            for partner in record.work_contact_id:
                if record.work_contact_id.id != record.partner_encab_id.id:
                    record.partner_encab_id = partner.id
                record.l10n_latam_identification_type_id = partner.l10n_latam_identification_type_id.id,
                record.private_street = partner.street
                record.private_street2 = partner.street2
                record.private_city = partner.city
                record.private_city_id = partner.city_id
                record.private_zip = partner.zip
                record.private_state_id = partner.state_id.id
                record.name = partner.name
                record.private_country_id = partner.country_id.id
                record.identification_id = partner.vat
                record.private_email = partner.email
                record.work_email = partner.email
                record.private_phone = partner.phone
                # Sincronizar campos de nombres desde el tercero
                if hasattr(partner, 'first_name') and partner.first_name:
                    record.first_name = partner.first_name
                if hasattr(partner, 'second_name') and partner.second_name:
                    record.middle_name = partner.second_name
                if hasattr(partner, 'first_lastname') and partner.first_lastname:
                    record.surname = partner.first_lastname
                if hasattr(partner, 'second_lastname') and partner.second_lastname:
                    record.mother_name = partner.second_lastname
                # Si el tercero no tiene nombres divididos, dividir desde el nombre completo
                if not partner.first_name and partner.name:
                    record.split_full_name(partner.name)

    def split_full_name(self, full_name=None):
        """
        Divide un nombre completo en sus componentes y los asigna a los campos.
        Usa la logica de lavish_erp para nombres hispanos.
        """
        self.ensure_one()
        name_to_split = full_name or self.name
        if not name_to_split and self.work_contact_id:
            name_to_split = self.work_contact_id.name

        if not name_to_split:
            return {}

        name_parts = split_nombre_completo(name_to_split)

        self.first_name = name_parts.get('first_name', '')
        self.middle_name = name_parts.get('second_name', '')
        self.surname = name_parts.get('first_lastname', '')
        self.mother_name = name_parts.get('second_lastname', '')

        # Recalcular el nombre completo segun el orden actual usado en empleado
        names = [n for n in [self.first_name, self.middle_name, self.surname, self.mother_name] if n]
        self.name = " ".join(names)

        return name_parts

    def action_split_name(self):
        """Accion para dividir el nombre desde la vista."""
        for employee in self:
            if employee.name or (employee.work_contact_id and employee.work_contact_id.name):
                employee.split_full_name()
        return True

    @api.depends('birthday')
    def _get_employee_age(self):
        for record in self:
            if record.birthday:
                record.employee_age = (date.today() - record.birthday).days // 365

    @api.depends('working_hours_id', 'working_hours_id.works_saturday')
    def _compute_auto_works_saturday(self):
        """Actualiza automáticamente el campo sabado según el horario laboral"""
        for record in self:
            if record.working_hours_id and record.working_hours_id.works_saturday:
                record.auto_works_saturday = True
                record.sabado = True  # Actualiza también el campo manual
            else:
                record.auto_works_saturday = False

    @api.constrains('distribution_cost_information')
    def _check_porcentage_distribution_cost(self):
        for record in self:
            if len(record.distribution_cost_information) > 0:
                porc_total = 0
                for distribution in record.distribution_cost_information:
                    porc_total += distribution.porcentage
                if porc_total != 100:
                    raise UserError(_('Los porcentajes de la distribución de costos no suman un 100%, por favor verificar.'))

    # @api.constrains('identification_id')
    # def _check_identification(self):
    #     for record in self:
    #         if record.identification_id != record.work_contact_id.vat:
    #             raise UserError(_('El número de identificación debe ser igual al tercero seleccionado.'))
    #         if record.identification_id != record.partner_encab_id.vat:
    #             raise UserError(_('El número de identificación debe ser igual al tercero seleccionado.'))

    # @api.constrains('tipo_coti_id','social_security_entities','subtipo_coti_id')
    # def _check_social_security_entities(self):
    #     for record in self:
    #         if record.tipo_coti_id or record.subtipo_coti_id:
    #             #Obtener parametriazación de cotizantes
    #             obj_parameterization_contributors = self.env['hr.parameterization.of.contributors'].search(
    #                 [('type_of_contributor', '=', record.tipo_coti_id.id),
    #                  ('contributor_subtype', '=', record.subtipo_coti_id.id)],limit=1)
    #             if len(obj_parameterization_contributors) == 0:
    #                 raise ValidationError(_('No existe parametrización para este tipo de cotizante / subtipo de cotizante, por favor verificar.'))
    #             #Obtener las entidades seleccionadas del empleado
    #             qty_eps, qty_pension, qty_riesgo, qty_caja = 0, 0, 0, 0
    #             for entity in record.social_security_entities:
    #                 if entity.contrib_id.type_entities == 'eps':  # SALUD
    #                     qty_eps += 1
    #                 if entity.contrib_id.type_entities == 'pension':  # PENSION
    #                     qty_pension += 1
    #                 if entity.contrib_id.type_entities == 'riesgo':  # ARP
    #                     qty_riesgo += 1
    #                 if entity.contrib_id.type_entities == 'caja':  # CAJA DE COMPENSACIÓN
    #                     qty_caja += 1

    #             #Validar EPS
    #             if obj_parameterization_contributors.liquidates_eps_company or obj_parameterization_contributors.liquidated_eps_employee:
    #                 if qty_eps == 0:
    #                     raise ValidationError(_('El empleado no tiene entidad EPS asignada, por favor verificar.'))
    #                 if qty_eps > 1:
    #                     raise ValidationError(_('El empleado tiene más de una entidad EPS asignada, por favor verificar.'))

    #             # Validar PENSIÓN
    #             if obj_parameterization_contributors.liquidated_company_pension or obj_parameterization_contributors.liquidate_employee_pension or obj_parameterization_contributors.liquidates_solidarity_fund:
    #                 if qty_pension == 0:
    #                     raise ValidationError(_('El empleado no tiene entidad Pensión asignada, por favor verificar.'))
    #                 if qty_pension > 1:
    #                     raise ValidationError(_('El empleado tiene más de una entidad Pensión asignada, por favor verificar.'))

    #             # Validar ARL/ARP - Se comenta debido a que se maneja por compañia
    #             #if obj_parameterization_contributors.liquidated_arl:
    #             #    if qty_riesgo == 0:
    #             #        raise ValidationError(_('El empleado no tiene entidad ARL asignada, por favor verificar.'))
    #             #    if qty_riesgo > 1:
    #             #        raise ValidationError(_('El empleado tiene más de una entidad ARL asignada, por favor verificar.'))

    #             # Validar CAJA DE COMPENSACIÓN
    #             if obj_parameterization_contributors.liquidated_compensation_fund:
    #                 if qty_caja == 0:
    #                     raise ValidationError(_('El empleado no tiene entidad Caja de compensación asignada, por favor verificar.'))
    #                 if qty_caja > 1:
    #                     raise ValidationError(_('El empleado tiene más de una entidad Caja de compensación asignada, por favor verificar.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name'):
                parts = [
                    vals.get('first_name'),
                    vals.get('middle_name'),
                    vals.get('surname'),
                    vals.get('mother_name'),
                ]
                name = ' '.join(part for part in parts if part)
                if name:
                    vals['name'] = name
            if vals.get('work_contact_id') and not vals.get('partner_encab_id'):
                vals['partner_encab_id'] = vals.get('work_contact_id')
            if not vals.get('work_contact_id') and vals.get('partner_encab_id'):
                vals['work_contact_id'] = vals.get('partner_encab_id')

        return super().create(vals_list)

    def get_info_contract(self):
        for record in self:
            obj_contract = self.env['hr.contract'].search([('employee_id','=',record.id),('state','=','open')],limit=1)
            if len(obj_contract) == 0:
                obj_contract += self.env['hr.contract'].search([('employee_id', '=', record.id), ('state', '=', 'close')],limit=1)
            if len(obj_contract) == 0:
                obj_contract += self.env['hr.contract'].search([('employee_id', '=', record.id), ('state', '=', 'finished')], limit=1)
            return obj_contract

    def get_age_for_date(self, o_date):
        if o_date:
            today = date.today()
            return today.year - o_date.year - ((today.month, today.day) < (o_date.month, o_date.day))
        else:
            return 0

    # Metodos reportes
    def get_report_print_badge_template(self):
        obj = self.env['report.print.badge.template'].search([('company_id','=',self.company_id.id)])
        if len(obj) == 0:
            raise ValidationError(_('No tiene configurada plantilla de identificación. Por favor verifique!'))
        return obj

    def get_name_rh(self):
        rh = dict(self._fields['licencia_rh'].selection).get(self.licencia_rh,'')
        return rh
    # Campos EPP y Dotación
    shirt_size = fields.Selection([
        ('xs', 'XS'),
        ('s', 'S'),
        ('m', 'M'),
        ('l', 'L'),
        ('xl', 'XL'),
        ('xxl', 'XXL'),
        ('xxxl', 'XXXL')
    ], string='Talla Camisa')

    pants_size = fields.Selection([
        ('28', '28'),
        ('30', '30'),
        ('32', '32'),
        ('34', '34'),
        ('36', '36'),
        ('38', '38'),
        ('40', '40'),
        ('42', '42')
    ], string='Talla Pantalón')

    shoe_size = fields.Selection([
        ('35', '35'),
        ('36', '36'),
        ('37', '37'),
        ('38', '38'),
        ('39', '39'),
        ('40', '40'),
        ('41', '41'),
        ('42', '42'),
        ('43', '43'),
        ('44', '44'),
        ('45', '45')
    ], string='Talla Zapato')

    # Productos por defecto para dotación
    default_shirt_product_id = fields.Many2one('product.product', string='Producto Camisa por Defecto',
                                                help='Producto que se usará por defecto en solicitudes de camisas')
    default_pants_product_id = fields.Many2one('product.product', string='Producto Pantalón por Defecto',
                                                help='Producto que se usará por defecto en solicitudes de pantalones')
    default_shoes_product_id = fields.Many2one('product.product', string='Producto Zapatos por Defecto',
                                                help='Producto que se usará por defecto en solicitudes de zapatos')

    # EPP/Dotación
    epp_request_ids = fields.One2many('hr.epp.request', 'employee_id', string='Solicitudes EPP/Dotación')
    epp_request_count = fields.Integer('Solicitudes EPP', compute='_compute_epp_request_count')

    # Certificados Médicos
    medical_certificate_ids = fields.One2many('hr.medical.certificate', 'employee_id', string='Certificados Médicos')
    medical_certificate_count = fields.Integer('Certificados Médicos (cantidad)', compute='_compute_medical_certificate_count')
    last_dotacion_date = fields.Date('Última Dotación', compute='_compute_last_dotacion_date')
    has_valid_medical = fields.Boolean('Tiene Certificado Vigente', compute='_compute_has_valid_medical')

    def _compute_epp_request_count(self):
        for employee in self:
            employee.epp_request_count = self.env['hr.epp.request'].search_count([
                ('employee_id', '=', employee.id)
            ])

    def _compute_medical_certificate_count(self):
        for employee in self:
            employee.medical_certificate_count = self.env['hr.medical.certificate'].search_count([
                ('employee_id', '=', employee.id)
            ])

    def _compute_last_dotacion_date(self):
        for employee in self:
            last_request = self.env['hr.epp.request'].search([
                ('employee_id', '=', employee.id),
                ('type', '=', 'dotacion'),
                ('state', '=', 'delivered')
            ], order='delivered_date desc', limit=1)
            employee.last_dotacion_date = last_request.delivered_date if last_request else False

    def _compute_has_valid_medical(self):
        for employee in self:
            valid_cert = self.env['hr.medical.certificate'].search([
                ('employee_id', '=', employee.id),
                ('state', '=', 'valid')
            ], limit=1)
            employee.has_valid_medical = bool(valid_cert)

    def action_view_epp_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Solicitudes EPP/Dotación',
            'res_model': 'hr.epp.request',
            'domain': [('employee_id', '=', self.id)],
            'view_mode': 'list,form',
            'context': {'default_employee_id': self.id}
        }

    def action_view_medical_certificates(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Certificados Médicos',
            'res_model': 'hr.medical.certificate',
            'domain': [('employee_id', '=', self.id)],
            'view_mode': 'list,form',
            'context': {'default_employee_id': self.id}
        }

    def get_name_type_document(self):
        obj_partner = self.env['res.partner']
        type_documet = self.work_contact_id.l10n_latam_identification_type_id.dian_code
        return type_documet
        
class ReportPrintBadgeTemplate(models.Model):
    _name = 'report.print.badge.template'
    _description = 'Imprimir Identificación'

    company_id = fields.Many2one('res.company', string='Compañía', default=lambda self: self.env.company)
    with_extra_space = fields.Boolean('Con espacio extra')
    img_header_file = fields.Binary('Plantilla del identificación')
    img_header_filename = fields.Char('Plantilla del identificación filename')
    imgback_header_file = fields.Binary('Plantilla del identificación respaldo')
    imgback_header_filename = fields.Char('Plantilla del identificación filename respaldo')
    orientation = fields.Selection([('horizontal', 'Horizontal'),
                                    ('vertical', 'Vertical')], string='Orientación', default="horizontal")

    _company_report_print_badge_template = models.Constraint('UNIQUE (company_id)', 'Ya existe una configuración de plantilla de identificación para esta compañía, por favor verificar')


        


class hr_employeePublic(models.Model):
    _inherit = 'hr.employee.public'

    # ========== CAMPOS DE DIRECCION PRIVADA EXTENDIDOS ==========
    # Estos campos reflejan la estructura de hr.employee para la vista publica
    # Usan prefijo private_ para consistencia con el esquema nativo de Odoo
    private_city_id = fields.Many2one(comodel_name='res.city', string='Ciudad', readonly=True)
    private_neighborhood_id = fields.Many2one(comodel_name='res.city.neighborhood', string='Barrio', readonly=True)
    private_barrio = fields.Char(string='Nombre Barrio', readonly=True)
    private_postal_code_id = fields.Many2one(comodel_name='res.city.postal', string='Codigo Postal', readonly=True)
    private_full_address = fields.Char(string='Direccion Completa', readonly=True)

    # ========== CAMPOS NOMBRES SINCRONIZADOS ==========
    first_name = fields.Char(string='Primer Nombre', readonly=True)
    middle_name = fields.Char(string='Segundo Nombre', readonly=True)
    surname = fields.Char(string='Primer Apellido', readonly=True)
    mother_name = fields.Char(string='Segundo Apellido', readonly=True)
    commercial_name = fields.Char(string='Nombre Comercial', readonly=True)

    work_email = fields.Char()
    company_id = fields.Many2one('res.company')
    department_id = fields.Many2one('hr.department')
    job_id = fields.Many2one('hr.job')
    parent_id = fields.Many2one('hr.employee')
    address_id = fields.Many2one('res.partner')
    resource_calendar_id = fields.Many2one('resource.calendar',
                                           domain="[('type_working_schedule', '=', 'employees'),'|', ('company_id', '=', False), ('company_id', '=', company_id)]",)
    #Asignacion
    analytic_account_id = fields.Many2one('account.analytic.account', 'Cuenta analitica', )
    front_back = fields.Selection([('front','Front office'),('back','Back office')],'Area laboral', )
    confianza_manejo = fields.Boolean('Confianza y manejo', )
    info_project = fields.Char(string='Proyecto')
    #Evaluacion de desempeno
    ed_qualification = fields.Float(string='Calificacion', )
    ed_observation = fields.Text(string='Observaciones', )
    #General
    partner_encab_id = fields.Many2one('res.partner', 'Tercero', help='Tercero equivalente a el empleado')
    # Usar employee_type nativo de Odoo
    sabado = fields.Boolean('Sabado dia habil', help='Indica si el dia sabado se incluye como dia habil', )
    certificate = fields.Selection(selection=[('primary', 'Primaria'),
                                    ('academic_bachelor', 'Bachiller'),
                                    ('technical', 'Técnico'),
                                    ('technologist', 'Tecnólogo'),
                                    ('academic', 'Profesional Universitario'),
                                    ('specialist', 'Especialista'),
                                    ('magister', 'Magister'),
                                    ('doctor', 'Doctor'),
                                    ('graduate', 'Licenciado'),
                                    ('bachelor', 'Graduado'),
                                    ('master', 'Maestro'),
                                    ('other', 'Otro')],
                                    string='Nivel de certificado', default='primary',)
    social_security_entities  = fields.One2many('hr.contract.setting', 'employee_id', string = 'Entidades', )
    dependents_information = fields.One2many('hr.employee.dependents', 'employee_id', string = 'Dependientes', )
    labor_union_information = fields.One2many('hr.employee.labor.union', 'employee_id', string = 'Sindicato', )
    personal_email = fields.Char(string='Correo-e personal', )
    personal_mobile = fields.Char(string='Móvil', )
    type_job = fields.Selection([('clave', 'Cargo Clave'),
                                    ('critico', 'Cargo Crítico'),
                                    ('cc', 'Cargo CC')], 'Tipo de cargo', )
    emergency_relationship = fields.Char(string='Parentesco contacto')
    documents_ids = fields.One2many('hr.employee.documents', 'employee_id', 'Documentos')
    distribution_cost_information = fields.One2many('hr.cost.distribution.employee', 'employee_id', string='Distribución de costos empleado')
    #PILA
    extranjero = fields.Boolean('Extranjero', help='Extranjero no obligado a cotizar a pensión', )
    residente = fields.Boolean('Residente en el Exterior', help='Colombiano residente en el exterior', )
    date_of_residence_abroad = fields.Date(string='Fecha radicación en el exterior', )
    tipo_coti_id = fields.Many2one('hr.tipo.cotizante', string='Tipo de cotizante', )
    subtipo_coti_id = fields.Many2one('hr.subtipo.cotizante', string='Subtipo de cotizante', )
    type_identification = fields.Selection([('CC', 'Cédula de ciudadanía'),
                                            ('CE', 'Cédula de extranjería'),
                                            ('TI', 'Tarjeta de identidad'),
                                            ('RC', 'Registro civil'),
                                            ('PA', 'Pasaporte')], 'Tipo de identificación', )
    indicador_especial_id = fields.Many2one('hr.indicador.especial.pila','Indicador tarifa especial pensiones', )
    cost_assumed_by  = fields.Selection([('partner', 'Cliente'),
                                        ('company', 'Compañía')], 'Costo asumido por', )
    #Licencia de conducción
    licencia_rh = fields.Selection([('op','O+'),('ap','A+'),('bp','B+'),('abp','AB+'),('on','O-'),('an','A-'),('bn','B-'),('abn','AB-')],'Tipo de sangre', )
    licencia_categoria = fields.Selection([('a1','A1'),('a2','A2'),('b1','B1'),('b2','B2'),('b3','B3'),('c1','C1'),('c2','C2'),('c3','C3')],'Categoria', )
    licencia_vigencia = fields.Date('Vigencia', )
    licencia_restricciones = fields.Char('Restricciones', size=255, )
    operacion_retirar = fields.Boolean('Retirar de la operacion', )
    operacion_reemplazo = fields.Many2one('hr.employee','Reemplazo', )
    #Estado civil
    type_identification_spouse = fields.Selection([('CC', 'Cédula de ciudadanía'),
                                            ('CE', 'Cédula de extranjería'),
                                            ('TI', 'Tarjeta de identidad'),
                                            ('RC', 'Registro civil'),
                                            ('PA', 'Pasaporte')], 'Tipo de identificación cónyuge', )
    num_identification_spouse = fields.Char('Número de identificación cónyuge', )
    spouse_phone= fields.Char('Teléfono del cónyuge', )
    #Sanciones
    employee_sanctions_ids = fields.One2many('hr.employee.sanctions', 'employee_id', string='Sanciones')
    #Edad
    employee_age = fields.Integer(string='Edad', compute='_get_employee_age', store=True)
    # Campos Caracterizacion
    stratum = fields.Selection([('1', '1'),
                                  ('2', '2'),
                                  ('3', '3'),
                                  ('4', '4'),
                                  ('5', '5'),
                                  ('6', '6')], string='Estrato', )
    sexual_orientation = fields.Selection([('heterosexual', 'Heterosexual'),
                                             ('bisexual', 'Bisexual'),
                                             ('homosexual', 'Homosexual'),
                                             ('pansexual', 'Pansexual'),
                                             ('asexual', 'Asexual'),
                                             ('other', 'Otro')], string='Orientación Sexual', )
    sexual_orientation_other = fields.Char(string="¿Cual?", )
    ethnic_group = fields.Selection([('none', 'Ninguno'),
                                       ('indigenous', 'Indígena'),
                                       ('afrocolombian', 'Afrocolombiano'),
                                       ('gypsy', 'Gitano'),
                                       ('raizal', 'Raizal')], string='Grupo étnico', )
    housing_area = fields.Selection([('rural', 'Rural'),
                                       ('urban', 'Urbana')], string='Zona de Vivienda', )
    health_risk_factors = fields.Char(string="Factores de riesgo en salud", )
    religion = fields.Char(string="Religión", )
    victim_armed_conflict = fields.Selection([('yes', 'Si'),
                                                ('not', 'No')], string='Victima del conflicto armado', )
    academic_data= fields.Char(string="Datos académicos", )
    city_birth_id = fields.Many2one('res.city',string="Ciudad de nacimiento",domain="[('state_id', '=', department_birth_id)]", )
    department_birth_id = fields.Many2one('res.country.state',string="Departamento de nacimiento", domain="[('country_id', '=', country_id)]", )
    military_passbook = fields.Boolean('Libreta militar', )
    identification_id = fields.Char(string='CC / PT/ ID')
    l10n_latam_identification_type_id = fields.Many2one('l10n_latam.identification.type',
        string="Tipo documento", index='btree_not_null',
        default=lambda self: self.env.ref('l10n_latam_base.it_vat', raise_if_not_found=False),
        help="The type of identification")


#     @api.onchange('partner_encab_id')
#     def _onchange_partner_encab(self):
#         for record in self:
#             for partner in record.partner_encab_id:
#                 self.work_contact_id = partner.id


#     @api.constrains('distribution_cost_information')
#     def _check_porcentage_distribution_cost(self):
#         for record in self:
#             if len(record.distribution_cost_information) > 0:
#                 porc_total = 0
#                 for distribution in record.distribution_cost_information:
#                     porc_total += distribution.porcentage
#                 if porc_total != 100:
#                     raise UserError(_('Los porcentajes de la distribución de costos no suman un 100%, por favor verificar.'))

#     @api.constrains('identification_id')
#     def _check_identification(self):
#         for record in self:
#             if record.identification_id != record.work_contact_id.vat:
#                 raise UserError(_('El número de identificación debe ser igual al tercero seleccionado.'))
#             if record.identification_id != record.partner_encab_id.vat:
#                 raise UserError(_('El número de identificación debe ser igual al tercero seleccionado.'))
