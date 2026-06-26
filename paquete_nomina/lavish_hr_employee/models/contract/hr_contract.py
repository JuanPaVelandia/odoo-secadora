# -*- coding: utf-8 -*-
"""
Modelo hr.contract - Extension del contrato de empleado.
Incluye campos para nomina colombiana, tipos de contrato, aprendizaje, etc.
"""
from datetime import date, datetime

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

try:
    from odoo.addons.hr_holidays_contract.models.hr_contract import \
        HrContract as HrHolidaysContract
except ModuleNotFoundError:
    HrHolidaysContract = None

from ._contract_utils import (CONTRACT_EXTENSION_MAX_WARN,
                              CONTRACT_EXTENSION_NO_RECORD_WARN, LAST_ONE,
                              _logger, days360)


class HrContract(models.Model):
    _inherit = 'hr.contract'

    def _sync_employee_version_contract_fields(self):
        """
        Sincroniza fechas contractuales del hr.contract hacia hr.version.

        En Odoo enterprise payroll varios warnings y cálculos del recibo usan
        `version_id.contract_date_start/contract_date_end` en lugar de leer
        directamente `hr.contract`. Si estos campos quedan vacíos, el recibo
        muestra falsos positivos de "sin contrato activo".
        """
        for contract in self.filtered(lambda c: c.employee_id and c.date_start):
            employee = contract.employee_id.sudo()
            version = False

            if hasattr(employee, '_get_version'):
                version = employee._get_version(date=contract.date_start)

            version = version or employee.current_version_id or employee.version_id
            if not version:
                continue

            vals = {
                'contract_date_start': contract.date_start,
                'contract_date_end': contract.date_end or False,
            }

            if 'trial_date_end' in version._fields:
                vals['trial_date_end'] = contract.trial_date_end or False
            if 'structure_type_id' in version._fields and contract.structure_type_id:
                vals['structure_type_id'] = contract.structure_type_id.id
            if 'contract_type_id' in version._fields and contract.contract_type_id:
                vals['contract_type_id'] = contract.contract_type_id.id
            if 'schedule_pay' in version._fields:
                schedule_pay = getattr(contract, 'method_schedule_pay', False)
                if schedule_pay:
                    vals['schedule_pay'] = schedule_pay

            version.sudo().write(vals)

    def _super_write_contract(self, vals):
        if HrHolidaysContract:
            return super(HrHolidaysContract, self).write(vals)
        return super(HrContract, self).write(vals)
    
    @api.model
    def _get_default_deductions_rtf_ids(self):
        salary_rules_rtf = self.env['hr.salary.rule'].search([('type_concepts', '=', 'tributaria')])
        data = []
        for rule in salary_rules_rtf:
            info = (0,0,{'input_id':rule.id})
            data.append(info)

        return data

    state = fields.Selection(selection_add=[('finished', 'Finalizado Por Liquidar'),
                                        ('close', 'Vencido'),
                                        ], ondelete={'finished': 'set default'} )
    analytic_account_id = fields.Many2one('account.analytic.account', tracking=True)
    job_id = fields.Many2one('hr.job', tracking=True)
    company_id = fields.Many2one('res.company', tracking=True)
    company_country_id = fields.Many2one(
        'res.country',
        related='company_id.country_id',
        string='Pais de la Empresa',
        store=True
    )
    country_code = fields.Char(
        related='company_country_id.code',
        string='Codigo Pais',
        store=True
    )
    sequence = fields.Char(string="Secuencia", default="/", readonly=True)
    retirement_date = fields.Date('Fecha retiro', tracking=True)
    change_wage_ids = fields.One2many('hr.contract.change.wage', 'contract_id', 'Cambios salario')
    concepts_ids = fields.One2many('hr.contract.concepts', 'contract_id', 'Devengos & Deducciones', domain=[('state', '!=', 'cancel')])
    contract_modification_history = fields.One2many('hr.contractual.modifications', 'contract_id','Modificaciones contractuales')
    deductions_rtf_ids = fields.One2many('hr.contract.deductions.rtf', 'contract_id', 'Deducciones retención en la fuente', default=_get_default_deductions_rtf_ids, tracking=True)
    risk_id = fields.Many2one('hr.contract.risk', string='Riesgo profesional', tracking=True)
    economic_activity_level_risk_id = fields.Many2one('lavish.economic.activity.level.risk', string='Actividad económica por nivel de riesgo', tracking=True)
    # Campo related para usar en expresiones de vistas (required, invisible, etc.)
    # En Odoo 19 las expresiones no pueden acceder a campos relacionados via Many2one
    contract_category = fields.Selection(
        related='contract_type_id.contract_category',
        string='Categoria de Contrato',
        store=True,
        readonly=True,
        help='Categoria legal del contrato. Campo related para uso en vistas.'
    )

    # Campo contract_type computado para mantener compatibilidad con vistas existentes
    # El valor real se obtiene de contract_type_id.contract_category
    contract_type = fields.Selection([
        ('obra', 'Contrato por Obra o Labor'),
        ('fijo', 'Contrato de Trabajo a Termino Fijo'),
        ('fijo_parcial', 'Contrato de Trabajo a Termino Fijo Tiempo Parcial'),
        ('indefinido', 'Contrato de Trabajo a Termino Indefinido'),
        ('aprendizaje', 'Contrato de Aprendizaje'),
        ('temporal', 'Contrato Temporal, Ocasional o Accidental'),
        ('agropecuario', 'Contrato Agropecuario'),
    ], string='Tipo de Contrato (Legacy)', compute='_compute_contract_type',
       store=True, help='Campo computado desde contract_type_id para compatibilidad')

    @api.depends('contract_type_id', 'contract_type_id.contract_category')
    def _compute_contract_type(self):
        """Computa contract_type desde contract_type_id.contract_category para compatibilidad."""
        # Mapeo de categorias a valores del selection original
        category_map = {
            'obra': 'obra',
            'fijo': 'fijo',
            'indefinido': 'indefinido',
            'aprendizaje': 'aprendizaje',
            'ocasional': 'temporal',
            'agropecuario': 'agropecuario',
        }
        for record in self:
            if record.contract_type_id and record.contract_type_id.contract_category:
                category = record.contract_type_id.contract_category
                # Mapear la categoria al valor del selection
                record.contract_type = category_map.get(category, 'indefinido')
            else:
                record.contract_type = 'indefinido'

    def write(self, vals):
        # v19: hr_holidays_contract was replaced by hr.version-based leave splitting
        # (see odoo/addons/hr_holidays/models/hr_version.py). hr.contract no longer
        # exposes _get_leaves(), so we just delegate to super and let hr.version handle it.
        res = super().write(vals)
        fields_to_sync = {'date_start', 'date_end', 'trial_date_end', 'structure_type_id', 'contract_type_id', 'method_schedule_pay', 'employee_id', 'state'}
        if fields_to_sync.intersection(vals.keys()):
            self._sync_employee_version_contract_fields()
        return res

    subcontract_type = fields.Selection([('obra_parcial', 'Parcial'),
                                         ('obra_integral', 'Parcial Integral')], 'SubTipo de Contrato', tracking=True)
    modality_salary = fields.Selection([
        ('basico', 'Básico'), 
        ('sostenimiento', 'Cuota de sostenimiento'), 
        ('integral', 'Integral'),
        ('especie', 'En especie'), 
        ('variable', 'Variable')
    ], string='Modalidad de salario', required=True, default='basico', tracking=True,
       help='''Modalidad de pago del salario segun tipo de contrato.

OPCIONES:

1. BASICO:
   - Salario ordinario mensual fijo
   - Ejemplo: $3.000.000 mensuales
   - Aplica: Prestaciones completas, auxilio transporte si < 2 SMMLV

2. CUOTA DE SOSTENIMIENTO (sostenimiento):
   - Para contratos de aprendizaje SENA
   - Etapa lectiva: 75% SMMLV ($1.067.625 en 2025)
   - Etapa productiva: 100% SMMLV ($1.423.500 en 2025)
   - NO genera prestaciones sociales tradicionales

3. INTEGRAL:
   - Salario >= 13 SMMLV (incluye factor prestacional 30%)
   - Ejemplo: $18.505.500 minimo 2025
   - Factor prestacional: 30% no hace base para prestaciones
   - Base prestaciones: 70% del salario integral

4. EN ESPECIE:
   - Parte del salario se paga en especie (vivienda, alimentacion)
   - Maximo 50% del salario puede ser en especie
   - Ejemplo: Salario $2.000.000, especie $600.000
   - Base para aportes: salario total $2.600.000

5. VARIABLE:
   - Salario depende de productividad (comisiones, destajo)
   - Ejemplo: Vendedor con comisiones variables
   - Base prestaciones: promedio de los ultimos meses''')

    modality_aux = fields.Selection([
        ('basico', 'Sin variación'), 
        ('variable', 'Variable'),
        ('no', 'Sin aux')
    ], string='Auxilio Transporte en Prestaciones', default='basico', tracking=True,
       help='''Como se incluye el auxilio de transporte en el calculo de prestaciones sociales.

OPCIONES:

1. SIN VARIACION (basico):
   - Usa el valor fijo del auxilio de transporte vigente
   - Ejemplo 2025: Auxilio $200.000 mensual fijo
   - Prima = (Salario + $200.000) * dias/360
   - Usar cuando: Empleado siempre tiene derecho al auxilio

2. VARIABLE:
   - Promedia el auxilio de los meses del periodo
   - Ejemplo: Enero auxilio $200.000, Febrero $0, Marzo $200.000
     Promedio = ($200.000 + $0 + $200.000) / 3 = $133.333
   - Usar cuando: Empleado a veces supera 2 SMMLV

3. SIN AUXILIO (no):
   - No incluye auxilio en calculo de prestaciones
   - Usar cuando: Empleado nunca tiene derecho (salario > 2 SMMLV)''')
    code_sena = fields.Char('Código SENA')                                
    view_inherit_employee = fields.Boolean('Viene de empleado')    
    # Usar employee_type nativo de Odoo (employee, student, trainee, contractor, freelance)
    employee_type = fields.Selection(string='Tipo de empleado', store=True, readonly=True, related='employee_id.employee_type')
    not_validate_top_auxtransportation = fields.Boolean(
        string='No validar tope de auxilio de transporte', 
        tracking=True,
        help='''Desactiva la validacion del tope de 2 SMMLV para auxilio de transporte.

CUANDO USAR:
- Empleado tiene derecho a auxilio por convencion colectiva
- Empleado tiene derecho sin importar el salario

EJEMPLO:
- Salario $3.000.000 (supera 2 SMMLV)
- Normalmente NO tendria derecho a auxilio
- Con este campo marcado: SI recibe auxilio

PRECAUCION: Solo usar cuando hay respaldo legal o contractual.''')

    not_pay_overtime = fields.Boolean(
        string='No liquidarle horas extras', 
        tracking=True,
        help='''Excluye al empleado del calculo de horas extras.

CUANDO USAR:
- Empleados de direccion, confianza o manejo
- Trabajadores que no tienen control de horario
- Salario integral (ya incluye recargos)

EJEMPLO:
- Gerente comercial con horario flexible
- Aunque registre horas adicionales, no se liquidan HE

ARTICULO: Art. 162 CST - Exclusiones jornada maxima.''')

    pay_auxtransportation = fields.Boolean(
        string='Liquidar auxilio de transporte a fin de mes', 
        tracking=True,
        help='''Paga el auxilio de transporte SOLO en la segunda quincena.

CUANDO USAR:
- Pago quincenal donde se consolida auxilio al final del mes
- Evitar pagar auxilio fraccionado

EJEMPLO:
- Primera quincena: Salario $1.500.000, Auxilio $0
- Segunda quincena: Salario $1.500.000, Auxilio $200.000 (mes completo)

NOTA: El auxilio se paga completo, no fraccionado por quincena.''')

    full_auxtransportation_settlement = fields.Boolean(
        string='Auxilio de transporte completo en liquidación',
        tracking=True,
        help='''En liquidaciones de contrato, pagar el valor mensual completo
del auxilio de transporte, sin prorratear por días.

CUANDO USAR:
- Contratos donde el auxilio debe mantenerse fijo al liquidar
- Casos en los que el cliente exige el valor legal completo

NOTA: Solo aplica en liquidaciones (proceso contrato).'''
    )

    not_pay_auxtransportation = fields.Boolean(
        string='No liquidar auxilio de transporte', 
        tracking=True,
        help='''Desactiva completamente el pago de auxilio de transporte.

CUANDO USAR:
- Empleado con salario >= 2 SMMLV (sin derecho legal)
- Empleado con vehiculo de la empresa
- Empleado que trabaja 100% remoto
- Empleado con auxilio de conectividad en lugar de transporte

EJEMPLO:
- Salario $4.000.000 + Vehiculo asignado
- Marcar este campo para que no se liquide auxilio

NOTA: Si aplica auxilio de conectividad, usar campo remote_work_allowance.''')
    info_project = fields.Char(related='employee_id.info_project', store=True)
    emp_work_address_id = fields.Many2one(related='employee_id.address_id',string="Ubicación laboral", store=True)
    emp_identification_id = fields.Char(related='employee_id.identification_id',string="Número de identificación", store=True)
    fecha_ibc = fields.Date('Fecha IBC Anterior')
    u_ibc = fields.Float('IBC Anterior')
    factor = fields.Float(
        string='Factor salarial',
        help='''Factor proporcional para contratos de tiempo parcial.

VALORES COMUNES:
- 1.0 = Tiempo completo (48 horas/semana)
- 0.5 = Medio tiempo (24 horas/semana)
- 0.25 = Cuarto de tiempo (12 horas/semana)

EJEMPLO:
- Salario base completo: $3.000.000
- Factor 0.5: Salario proporcional = $1.500.000
- Factor 0.25: Salario proporcional = $750.000

AFECTA:
- Calculo de salario basico
- Aportes a seguridad social
- Base de prestaciones''')

    proyectar_fondos = fields.Boolean(
        string='Proyectar Fondos',
        help='''Proyecta valores de fondos de pensiones y cesantias.

CUANDO USAR:
- Para estimar aportes futuros
- Simulaciones de costos laborales

EJEMPLO:
- Salario $3.000.000
- Proyeccion pension empleador: $360.000 (12%%)
- Proyeccion cesantias: $250.000 mensual''')

    proyectar_ret = fields.Boolean(
        string='Proyectar Retenciones',
        help='''Proyecta retenciones en la fuente.

CUANDO USAR:
- Estimar retencion anual
- Planeacion tributaria del empleado

EJEMPLO:
- Ingreso mensual proyectado: $8.000.000
- Retencion mensual estimada: $500.000
- Retencion anual proyectada: $6.000.000''')

    parcial = fields.Boolean(
        string='Tiempo parcial',
        help='''Marca el contrato como tiempo parcial.

EFECTOS:
1. Activa tipo cotizante 51 (tiempo parcial)
2. Habilita campos de dias manuales
3. Activa factor salarial
4. IBC proporcional a horas trabajadas

EJEMPLO:
- Jornada 24 horas/semana (50%%)
- Salario $1.500.000 (50%% de $3.000.000)
- IBC para seguridad social: proporcional

REQUISITO MINIMO:
- Minimo 24 horas semanales para tipo 51
- Menos de 24 horas: revisar tipo cotizante''')

    pensionado = fields.Boolean(
        string='Pensionado',
        compute='_compute_pensionado',
        store=True,
        readonly=False,
        help='''Indica que el empleado ya es pensionado.

CAMPO COMPUTADO desde subtipo de cotizante del empleado.
Se detecta automaticamente segun los siguientes subtipos:

SUBTIPOS DETECTADOS:
- 01: Pensionado vejez activo dependiente
- 02: Pensionado vejez activo independiente
- 04: Requisitos cumplidos pension

EFECTOS:
1. No aporta a pension (ya tiene pension)
2. Solo aporta a salud y riesgos
3. Tipo cotizante especial

EJEMPLO:
- Pensionado que trabaja medio tiempo
- Aportes: Salud 12.5%%, ARL segun riesgo
- NO aporta: Pension (4%% + 12%%)

NOTA: Puede sobrescribirse manualmente si es necesario.''')
    date_to = fields.Date('Finalización contrato fijo')
    sena_code = fields.Char('SENA code')
    date_prima = fields.Date(
        string='Ultima Fecha de liquidación de prima',
        help='''Fecha hasta la cual se han liquidado primas de servicios.

USO:
- El sistema calcula prima desde esta fecha hasta la actual
- Se actualiza automaticamente al liquidar prima

EJEMPLO:
- date_prima = 30/06/2024 (ultimo pago prima)
- Periodo calculo: 01/07/2024 a 31/12/2024
- Prima = (Salario + Auxilio) * dias/360

NOTA: Si no tiene fecha, calcula desde inicio de contrato.''')

    u_prima = fields.Float(
        string='Ultima Prov. Prima',
        help='''Valor de la ultima provision de prima liquidada.

USO:
- Para control y trazabilidad de provisiones
- Se actualiza al calcular provision mensual

EJEMPLO:
- Salario $3.000.000
- Provision mensual prima = $3.000.000 / 12 = $250.000
- u_prima = $250.000 (ultimo valor provisionado)''')

    date_cesantias = fields.Date(
        string='Ultima Fecha de liquidación de cesantías',
        help='''Fecha hasta la cual se han liquidado cesantias.

USO:
- Calculo de cesantias desde esta fecha
- Se actualiza al liquidar o consignar cesantias

EJEMPLO:
- date_cesantias = 14/02/2024 (consignacion a fondo)
- Periodo calculo: 15/02/2024 a 31/12/2024
- Cesantias = (Salario + Auxilio) * dias/360

NOTA: Cesantias se consignan a fondo antes del 14 de febrero.''')

    u_cesantias = fields.Float(
        string='Ultima Prov. Cesantía',
        help='''Valor de la ultima provision de cesantias liquidada.

USO:
- Control de provisiones mensuales
- Base para consignacion anual a fondo

EJEMPLO:
- Salario $3.000.000 + Auxilio $200.000
- Provision mensual = $3.200.000 / 12 = $266.667
- u_cesantias = $266.667''')

    date_vacaciones = fields.Date(
        string='Ultima Fecha de liquidación de vacaciones',
        help='''Fecha hasta la cual se han liquidado vacaciones.

USO:
- Calculo de dias de vacaciones pendientes
- Se actualiza al disfrutar o compensar vacaciones

EJEMPLO:
- date_vacaciones = 15/03/2024 (ultima vacacion)
- Periodo: 16/03/2024 a fecha actual
- Dias acumulados = dias_periodo / 24 (15 dias/anio)

NOTA: Art. 186 CST - 15 dias habiles por anio trabajado.''')

    u_vacaciones = fields.Float(
        string='Ultima Prov. Vacaciones',
        help='''Valor de la ultima provision de vacaciones liquidada.

USO:
- Control de provision mensual
- Base para liquidacion de vacaciones

EJEMPLO:
- Salario $3.000.000
- Provision mensual = $3.000.000 * 15/360 = $125.000
- u_vacaciones = $125.000''')
    retention_procedure = fields.Selection([
        ('100', 'Procedimiento 1'),
        ('102', 'Procedimiento 2'),
        ('extranjero_no_residente', 'Extranjero No Residente'),
        ('fixed', 'Valor fijo')
    ], string='Procedimiento retención', default='100', tracking=True,
       help='''Metodo para calcular la retencion en la fuente.

OPCIONES:

1. PROCEDIMIENTO 1 (100):
   - Calculo mensual sobre ingresos del periodo
   - Aplica tabla de retencion vigente
   - Ejemplo: Salario $8.000.000, deducciones $1.500.000
     Base gravable = $6.500.000
     Retencion segun tabla Art. 383 ET

2. PROCEDIMIENTO 2 (102):
   - Promedio de ingresos de ultimos 12 meses
   - Mas estable para ingresos variables
   - Ejemplo: Promedio 12 meses = $7.000.000
     Retencion sobre promedio mensual
   - Requiere: Historial de 12 meses minimo

3. EXTRANJERO NO RESIDENTE:
   - Tarifa fija del 35%% sobre pagos
   - Aplica a extranjeros sin residencia fiscal
   - Art. 406-408 ET

4. VALOR FIJO (fixed):
   - Retencion fija mensual
   - Usar campo fixed_value_retention_procedure
   - Ejemplo: Retencion fija $500.000/mes''')

    fixed_value_retention_procedure = fields.Float(
        string='Valor fijo retención', 
        tracking=True,
        help='''Valor fijo de retencion mensual cuando procedimiento = "Valor fijo".

EJEMPLO:
- retention_procedure = "fixed"
- fixed_value_retention_procedure = 500000
- Cada mes se descuenta $500.000 por retencion

CUANDO USAR:
- Acuerdo con el empleado para retencion fija
- Empleados con ingresos muy variables''')

    method_schedule_pay = fields.Selection([
        ('bi-weekly', 'Quincenal'),
        ('monthly', 'Mensual')
    ], string='Frecuencia de Pago', tracking=True,
       help='''Frecuencia de pago del salario.

OPCIONES:

1. QUINCENAL (bi-weekly):
   - Pago cada 15 dias (1-15 y 16-30/31)
   - Primera quincena: dias 1-15
   - Segunda quincena: dias 16-fin de mes
   - Ejemplo: Salario $3.000.000
     Quincena 1: $1.500.000
     Quincena 2: $1.500.000

2. MENSUAL (monthly):
   - Pago unico al fin del mes
   - Dias 1-30/31 del mes
   - Ejemplo: Salario $3.000.000
     Pago mes: $3.000.000

NOTA: Afecta calculo de auxilio, provisiones y retenciones.''')
    apr_prod_date = fields.Date('Fecha de cambio a etapa productiva',
                                help="Marcar unicamente cuando el aprendiz pase a etapa productiva")

    # =========================================================================
    # CAMPOS PARA APRENDIZAJE Y TIPO COTIZANTE 51 (Ley 2466/2025)
    # =========================================================================
    apprentice_stage = fields.Selection([
        ('lectiva', 'Etapa Lectiva'),
        ('productiva', 'Etapa Productiva'),
    ], string='Etapa de Aprendizaje', tracking=True,
       compute='_compute_apprentice_stage', store=True, readonly=False,
       help='Etapa actual del aprendiz. Lectiva: 75% SMMLV, Productiva: 100% SMMLV')

    apprentice_wage = fields.Float(
        string='Cuota Sostenimiento Calculada',
        compute='_compute_apprentice_wage', store=True,
        help='Cuota de sostenimiento calculada segun etapa y SMMLV vigente'
    )

    tipo_cotizante_id = fields.Many2one(
        related='employee_id.tipo_coti_id',
        tracking=True,
        help='Tipo de cotizante para PILA. Se configura automaticamente segun tipo de contrato'
    )
    # Campo related para usar en expresiones de vistas (invisible, required, etc.)
    tipo_cotizante_code = fields.Char(
        related='tipo_cotizante_id.code',
        string='Codigo Tipo Cotizante',
        store=True,
        readonly=True,
    )

    partial_hours_weekly = fields.Float(
        string='Horas Semanales',
        default=48.0,
        help='Horas semanales trabajadas. Para tiempo parcial (tipo 51) minimo 24 horas'
    )

    partial_wage_computed = fields.Float(
        string='Salario Proporcional',
        compute='_compute_partial_wage', store=True,
        help='Salario calculado proporcionalmente para tiempo parcial (tipo 51)'
    )

    @api.depends('apr_prod_date', 'contract_type_id', 'contract_type_id.is_apprenticeship')
    def _compute_apprentice_stage(self):
        """Determina la etapa del aprendiz basado en la fecha de cambio a productiva."""
        today = fields.Date.today()
        for record in self:
            if record.contract_type_id and record.contract_type_id.is_apprenticeship:
                if record.apr_prod_date and record.apr_prod_date <= today:
                    record.apprentice_stage = 'productiva'
                else:
                    record.apprentice_stage = 'lectiva'
            else:
                record.apprentice_stage = False

    @api.depends('apprentice_stage', 'contract_type_id', 'contract_type_id.is_apprenticeship',
                 'contract_type_id.apprentice_wage_pct_lectiva', 'contract_type_id.apprentice_wage_pct_productiva')
    def _compute_apprentice_wage(self):
        """Calcula la cuota de sostenimiento segun la etapa del aprendiz."""
        for record in self:
            if not record.contract_type_id or not record.contract_type_id.is_apprenticeship:
                record.apprentice_wage = 0.0
                continue

            # Obtener SMMLV del anio actual
            current_year = fields.Date.today().year
            annual_params = self.env['hr.annual.parameters'].get_for_year(
                current_year,
                company_id=(record.company_id.id if record.company_id else self.env.company.id),
                raise_if_not_found=False,
            )

            smmlv = annual_params.smmlv_monthly if annual_params else 1423500  # Default 2025

            # Calcular segun etapa
            if record.apprentice_stage == 'productiva':
                pct = record.contract_type_id.apprentice_wage_pct_productiva or 100.0
            else:
                pct = record.contract_type_id.apprentice_wage_pct_lectiva or 75.0

            record.apprentice_wage = smmlv * (pct / 100.0)

    @api.depends('parcial', 'partial_hours_weekly', 'wage', 'tipo_cotizante_id')
    def _compute_partial_wage(self):
        """Calcula el salario proporcional para contratos de tiempo parcial (tipo 51)."""
        for record in self:
            # Solo aplica para tiempo parcial o tipo cotizante 51
            is_partial = record.parcial or (record.tipo_cotizante_id and record.tipo_cotizante_id.code == '51')

            if not is_partial or not record.wage:
                record.partial_wage_computed = record.wage or 0.0
                continue

            # Calcular proporcion basado en horas (48 horas = jornada completa)
            full_hours = 48.0
            hours = record.partial_hours_weekly or full_hours
            proportion = hours / full_hours

            record.partial_wage_computed = record.wage * proportion

    @api.depends('employee_id', 'employee_id.subtipo_coti_id', 'employee_id.subtipo_coti_id.code')
    def _compute_pensionado(self):
        """
        Determina si el empleado es pensionado basado en subtipo de cotizante.
        
        Subtipos de pensionado:
        - 01: Pensionado vejez activo dependiente
        - 02: Pensionado vejez activo independiente
        - 04: Requisitos cumplidos pension
        """
        SUBTIPOS_PENSIONADO = ['01', '02', '04']
        
        for record in self:
            es_pensionado = False
            
            if record.employee_id and record.employee_id.subtipo_coti_id:
                subtipo_code = record.employee_id.subtipo_coti_id.code
                if subtipo_code in SUBTIPOS_PENSIONADO:
                    es_pensionado = True
            
            record.pensionado = es_pensionado

    @api.onchange('contract_type_id')
    def _onchange_contract_type_id_cotizante(self):
        """Configura automaticamente el tipo de cotizante segun el tipo de contrato."""
        if not self.contract_type_id:
            return

        category = self.contract_type_id.contract_category
        TipoCotizante = self.env['hr.tipo.cotizante']

        # Mapeo de categoria de contrato a tipo de cotizante
        cotizante_map = {
            'aprendizaje': '19',  # Aprendiz SENA etapa productiva (o 12 para lectiva)
            'ocasional': '01',    # Dependiente
            'indefinido': '01',   # Dependiente
            'fijo': '01',         # Dependiente
            'obra': '01',         # Dependiente
            'agropecuario': '01', # Dependiente
        }

        # Para aprendizaje, verificar la etapa
        if category == 'aprendizaje':
            if self.apprentice_stage == 'lectiva':
                cotizante_code = '12'  # Aprendiz SENA etapa lectiva
            else:
                cotizante_code = '19'  # Aprendiz SENA etapa productiva
        else:
            cotizante_code = cotizante_map.get(category, '01')

        tipo = TipoCotizante.search([('code', '=', cotizante_code)], limit=1)
        if tipo:
            self.tipo_cotizante_id = tipo.id

    @api.onchange('apprentice_stage')
    def _onchange_apprentice_stage(self):
        """Actualiza tipo cotizante y salario cuando cambia la etapa del aprendiz."""
        if not self.contract_type_id or not self.contract_type_id.is_apprenticeship:
            return

        TipoCotizante = self.env['hr.tipo.cotizante']

        if self.apprentice_stage == 'lectiva':
            # Etapa lectiva: tipo 12, 75% SMMLV
            tipo = TipoCotizante.search([('code', '=', '12')], limit=1)
            self.modality_salary = 'sostenimiento'
        else:
            # Etapa productiva: tipo 19, 100% SMMLV
            tipo = TipoCotizante.search([('code', '=', '19')], limit=1)
            self.modality_salary = 'sostenimiento'

        if tipo:
            self.tipo_cotizante_id = tipo.id

    @api.onchange('parcial')
    def _onchange_parcial_cotizante(self):
        """Configura tipo cotizante 51 cuando se marca tiempo parcial."""
        if self.parcial:
            TipoCotizante = self.env['hr.tipo.cotizante']
            tipo_51 = TipoCotizante.search([('code', '=', '51')], limit=1)
            if tipo_51:
                self.tipo_cotizante_id = tipo_51.id
        elif self.contract_type_id:
            # Si se desmarca, volver al tipo por defecto segun contrato
            self._onchange_contract_type_id_cotizante()

    only_wage = fields.Selection([
        ('wage', 'Solo Salario Base'),
        ('wage_dev', 'Salario + Devengos Salariales'),
        ('wage_dev_exc', 'Salario + Devengos Marcados')
    ], string='Base para Validar Tope Auxilio', default='wage',
       help='''Define qué conceptos se incluyen para validar el tope del auxilio de transporte (2 SMMLV).

OPCIONES:

1. SOLO SALARIO BASE (wage):
   - Usa UNICAMENTE el salario del contrato
   - Ejemplo: Salario $2.000.000 = Base $2.000.000
   - Usar cuando: El empleado solo tiene salario fijo

2. SALARIO + DEVENGOS SALARIALES (wage_dev):
   - Salario + reglas con categoria DEV_SALARIAL
   - Incluye automaticamente: comisiones, bonificaciones salariales, recargos
   - Ejemplo: Salario $1.500.000 + Comisiones $800.000 = Base $2.300.000
   - Usar cuando: Empleado con ingresos variables que son salario

3. SALARIO + DEVENGOS MARCADOS (wage_dev_exc):
   - Salario + reglas con campo "base_auxtransporte_tope" = True
   - Solo incluye reglas ESPECIFICAMENTE marcadas
   - Ejemplo: Salario $1.800.000 + Bono Productividad (marcado) $400.000 = Base $2.200.000
   - Usar cuando: Se requiere control fino de que conceptos incluir

CAMPOS RELACIONADOS EN REGLAS SALARIALES:
- base_auxtransporte_tope: Incluye la regla en el calculo
- excluir_auxtransporte_tope: Excluye la regla (tiene prioridad)

NOTA: Si Base >= 2 SMMLV, el empleado NO tiene derecho a auxilio de transporte.''')
    tope_aux_method = fields.Selection([
        ('mes_completo', 'Mes Completo (valida en cierre)'),
        ('proporcional', 'Proporcional al Periodo'),
    ], string='Metodo Validacion Tope Auxilio', default='mes_completo',
       help='''Metodo para validar si el empleado tiene derecho al auxilio de transporte.

OPCIONES:

1. MES COMPLETO (mes_completo):
   - SOLO se valida en la SEGUNDA QUINCENA (cierre de mes)
   - En primera quincena: se paga auxilio sin validar
   - En segunda quincena: valida ingresos del MES COMPLETO
   - Si excede 2 SMMLV: activa DEVOLUCION del auxilio pagado
   
   FLUJO:
   - Quincena 1 (dias 1-15): Paga auxilio $100.000
   - Quincena 2 (dias 16-30): Valida mes completo
     - Si mes >= 2 SMMLV: Genera devolucion (DEVAUX000)
   
   EJEMPLO CON DEVOLUCION:
   - SMMLV 2025: $1.423.500, Tope = $2.847.000
   - Quincena 1: Salario $1.250.000 + Auxilio $100.000
   - Quincena 2: Salario $1.250.000 + Comision $500.000
   - Total mes: $3.000.000 > $2.847.000
   - Resultado: Devolucion auxilio Q1 ($100.000) + No paga Q2
   
   EJEMPLO SIN DEVOLUCION:
   - Quincena 1: Salario $1.250.000 + Auxilio $100.000
   - Quincena 2: Salario $1.250.000 + Auxilio $100.000
   - Total mes: $2.500.000 < $2.847.000
   - Resultado: Mantiene auxilio de ambas quincenas

2. PROPORCIONAL AL PERIODO (proporcional):
   - Valida el tope en CADA QUINCENA de forma proporcional
   - El tope de 2 SMMLV se divide proporcionalmente (mes = 30 dias)
   - NO genera devoluciones, valida antes de pagar
   
   FORMULA:
   - Tope proporcional = (2 SMMLV / 30) * dias_periodo
   - Base periodo = (Salario / 30) * dias + Variables del periodo
   
   EJEMPLO QUINCENA (15 dias):
   - Tope quincena = $2.847.000 * 15/30 = $1.423.500
   - Salario quincena: $1.250.000
   - Comisiones quincena: $300.000
   - Base = $1.550.000 > $1.423.500 = NO paga auxilio
   
   FLUJO:
   - Quincena 1: Valida, si pasa = paga auxilio
   - Quincena 2: Valida, si pasa = paga auxilio
   - Cada quincena es independiente

CUANDO USAR CADA UNO:
- mes_completo: Ingresos variables pero se prefiere pagar auxilio
  y devolver al cierre si corresponde (mas favorable al empleado)
- proporcional: Ingresos muy variables, validar cada quincena
  antes de pagar (evita devoluciones)

CAMPO RELACIONADO:
- dev_aux: Debe estar activo para generar devoluciones con mes_completo''')

    dev_aux = fields.Boolean(
        string="Devolver Auxilio Transporte",
        help='''Activa la devolucion automatica del auxilio de transporte.

CUANDO SE USA:
- El empleado tenia auxilio pero en el mes sus ingresos superaron 2 SMMLV
- Se debe devolver el auxilio pagado indebidamente

EJEMPLO:
- Enero: Salario $2.000.000 + Auxilio $140.000
- Febrero: Salario $2.000.000 + Comisiones $800.000 = $2.800.000
- Febrero supera 2 SMMLV ($2.600.000 en 2024)
- Se genera regla DEVAUX000 para devolver auxilio

LOGICA:
1. Calcula ingresos del periodo
2. Si ingresos >= 2 SMMLV y se pago auxilio
3. Genera concepto de devolucion (DEVAUX000)
4. Descuenta el auxilio pagado indebidamente''')
    type_of_jurisdiction = fields.Many2one('hr.type.of.jurisdiction', string ='Tipo de Fuero')                             
    date_i = fields.Date('Fecha Inicial')
    date_f = fields.Date('Fecha Final')
    relocated = fields.Char('Reubicados')
    previous_positions = fields.Char('Cargo anterior')
    new_positions = fields.Char('Cargo nuevo')
    time_with_the_state = fields.Char('Tiempo que lleva con el estado')
    date_last_wage = fields.Date('Fecha Ultimo sueldo')
    wage_old = fields.Float('Salario basico', help='Seguimento de los cambios en el salario basico')
    remote_work_allowance = fields.Boolean(
        string='Aplica Auxilio de Conectividad',
        help='''Paga auxilio de conectividad en lugar de auxilio de transporte.

CUANDO USAR:
- Empleado en modalidad de trabajo remoto/teletrabajo
- Reemplaza el auxilio de transporte

EJEMPLO:
- Empleado 100% remoto
- En lugar de auxilio transporte $200.000
- Recibe auxilio conectividad $200.000 (para internet, energia)

LEY: Ley 2121/2021 - Trabajo remoto.
NOTA: Tiene mismas reglas de tope (2 SMMLV) que auxilio transporte.''')

    minimum_wage = fields.Boolean(
        string='Devenga Salario Mínimo',
        help='''Indica que el empleado devenga exactamente el salario minimo.

CUANDO USAR:
- Para calculos automaticos con SMMLV vigente
- Actualizacion automatica cuando cambia el minimo

EJEMPLO:
- Contrato con salario = SMMLV
- 2024: $1.300.000 automaticamente
- 2025: $1.423.500 automaticamente

NOTA: El campo wage debe tener el valor del SMMLV.''')

    ley_2101 = fields.Boolean(
        string='Disminucion Jornada Laboral (Ley 2101)',
        help='''Aplica la reduccion gradual de jornada laboral segun Ley 2101/2021.

CRONOGRAMA:
- Julio 2023: 47 horas semanales
- Julio 2024: 46 horas semanales
- Julio 2025: 44 horas semanales
- Julio 2026: 42 horas semanales

EFECTO:
- Recargos nocturnos, dominicales y festivos se calculan con jornada reducida
- Horas extra se cuentan desde el limite reducido

EJEMPLO:
- 2025: Jornada maxima 44 horas/semana
- Hora 45+ = Hora extra''')

    limit_deductions = fields.Boolean(
        string='Limitar Deducciones al 50% de Devengos',
        help='''Limita las deducciones al 50%% de TOTALDEV (Art. 149 CST).

FUNCIONAMIENTO:

1. Se calcula TOTALDEV (total devengos)
2. Limite = TOTALDEV * 50%%
3. Se procesan deducciones por orden de secuencia (200+)
4. Las que excedan el limite quedan en cero

CATEGORIAS OBLIGATORIAS (siempre se descuentan):
- Seguridad Social (SSOCIAL): Salud, Pension
- Retencion en la Fuente (RETENCION)
- IBC (BASE_SEC)

CATEGORIAS LIMITABLES (en orden de secuencia):
- Prestamos (secuencia 210+)
- Embargos (secuencia 220+)
- Otras deducciones (secuencia 230+)

EJEMPLO DE CALCULO:
1. TOTALDEV = $3.000.000
2. Limite 50%% = $1.500.000

3. Deducciones ordenadas por secuencia:
   - SSOCIAL001 (seq 200): $120.000 - OBLIGATORIA
   - SSOCIAL002 (seq 201): $200.000 - OBLIGATORIA
   - RETENCION (seq 205): $300.000 - OBLIGATORIA
   - PRESTAMO1 (seq 210): $400.000 - limitable
   - PRESTAMO2 (seq 215): $600.000 - limitable
   - EMBARGO (seq 220): $300.000 - limitable

4. Total obligatorias: $620.000
5. Disponible para limitables: $1.500.000 - $620.000 = $880.000

6. Aplicar en orden de secuencia:
   - PRESTAMO1: $400.000 (acum: $400.000) = OK
   - PRESTAMO2: $600.000 > $480.000 disponible = PARCIAL o CERO
   - EMBARGO: $0 (excede limite)

7. TOTALDED final = $1.500.000 (limitado)

TRAZABILIDAD:
La informacion de deducciones limitadas se guarda en:
- localdict['LIMIT_DEDUCTIONS_INFO']
  - deducciones_completas: lista de aplicadas
  - deducciones_parciales: lista de reducidas
  - deducciones_cero: lista de excluidas

NOTA: Las deducciones que quedan en cero se deben reprogramar
para el siguiente periodo de nomina.''')
    #Pestaña de dotacion
    employee_endowment_ids = fields.One2many('hr.employee.endowment', 'contract_id', 'Dotación')
    progress = fields.Float('Progreso', compute='_compute_progress')
    paysplip_ids = fields.One2many(
        string='Historial de Nominas', comodel_name='hr.payslip',
        inverse_name='contract_id')
    trial_date_start = fields.Date("Inicio Periodo de Prueba", compute="_compute_periodo_prueba", store=True, readonly=False)
    trial_date_end = fields.Date("Fin Periodo de Prueba", compute="_compute_periodo_prueba", store=True, readonly=False)

    # Campos para días manuales
    use_manual_days = fields.Boolean(
        string='Usar días manuales por defecto',
        default=False,
        help='''Activa el uso de dias manuales en lugar de dias calculados.

CUANDO USAR:
- Contratos de tiempo parcial
- Empleados con jornadas especiales
- Cuando se requiere control manual de dias

EJEMPLO:
- Contrato medio tiempo: 15 dias/mes
- Contrato 3 dias/semana: 12 dias/mes
- Nomina usara estos dias en lugar de calcular

AFECTA:
- Calculo de salario basico (BASIC)
- Proporciones para prestaciones
- Aportes a seguridad social''')

    manual_days = fields.Float(
        string='Días manuales por defecto',
        help='''Numero de dias a usar cuando use_manual_days esta activo.

EJEMPLOS:
- Tiempo completo: 30 dias
- Medio tiempo: 15 dias
- 3 dias/semana: 12 dias
- 4 dias/semana: 16 dias

CALCULO BASICO:
- Salario = (wage / 30) * manual_days
- Ejemplo: $3.000.000 / 30 * 15 = $1.500.000

NOTA: Si es 0 y use_manual_days=True, usara 30 dias.''')
    contract_type_icon_html = fields.Html(
        string='Icono',
        compute='_compute_contract_type_icon',
        help='Icono Font Awesome según el tipo de contrato'
    )

    @api.depends('contract_type_id', 'subcontract_type', 'modality_salary')
    def _compute_contract_type_icon(self):
        """Asigna icono Font Awesome segun el tipo de contrato."""
        for record in self:
            # Iconos por categoria de contrato (contract_category en hr.contract.type)
            icons = {
                'obra': ('fa-briefcase', 'Obra o Labor'),
                'fijo': ('fa-calendar-check-o', 'Termino Fijo'),
                'indefinido': ('fa-infinity', 'Indefinido'),
                'aprendizaje': ('fa-graduation-cap', 'Aprendizaje'),
                'ocasional': ('fa-clock-o', 'Ocasional'),
                'agropecuario': ('fa-leaf', 'Agropecuario'),
            }

            # Determinar icono y titulo
            if record.subcontract_type:
                icon_class = 'fa-puzzle-piece'
                title = 'Subcontrato'
            elif record.modality_salary == 'integral':
                icon_class = 'fa-star'
                title = 'Salario Integral'
            elif record.modality_salary == 'sostenimiento':
                icon_class = 'fa-graduation-cap'
                title = 'Sostenimiento'
            elif record.contract_type_id and record.contract_type_id.contract_category:
                icon_class, title = icons.get(
                    record.contract_type_id.contract_category,
                    ('fa-file-text-o', record.contract_type_id.name or 'Contrato')
                )
            else:
                icon_class, title = ('fa-file-text-o', 'Contrato')

            # Generar HTML del icono
            record.contract_type_icon_html = f'<i class="fa {icon_class}" style="font-size: 18px; color: #007bff;" title="{title}"></i>'

    @api.onchange('parcial')
    def _onchange_parcial(self):
        """Cuando se activa 'parcial', establece valores por defecto."""
        if self.parcial:
            if not self.factor or self.factor == 0:
                self.factor = 0.5
            if not self.use_manual_days:
                self.use_manual_days = True
        else:
            # Al desactivar, limpiar los campos relacionados
            self.factor = 0.0
            self.use_manual_days = False
            self.manual_days = 0.0

    @api.depends('date_start')
    def _compute_periodo_prueba(self):
        for record in self:
            if record.date_start:
                start_dt = record.date_start
                date_end = start_dt - relativedelta(days=1) + relativedelta(months=2)
                record.trial_date_start = record.date_start
                record.trial_date_end = date_end
            else:
                record.trial_date_start = False
                record.trial_date_end = False

    #@api.depends('date_start', 'date_end')
    def _compute_progress(self):
        for record in self:
            if record.date_start and record.date_end:
                total_days = (record.date_end - record.date_start).days
                elapsed_days = (datetime.now().date() - record.date_start).days
                record.progress = (elapsed_days / total_days) * 100 if total_days > 0 else 0
            else:
                record.progress = 0 

    @api.depends('sequence', 'employee_id', 'employee_id.name')
    def _compute_display_name(self):
        for record in self:
            record.display_name = "{} | {}".format(record.sequence,record.employee_id.name)

    def get_selection_label(self, field_name):
        """
        Obtiene la etiqueta en español de un campo Selection usando _description_selection().

        Args:
            field_name (str): Nombre del campo Selection

        Returns:
            str: Etiqueta del valor actual del campo en español, o '' si no existe

        Ejemplo:
            contract.get_selection_label('contract_type')  # Retorna 'Contrato por Obra o Labor'
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

    def extend_contract(self):
        """Extend contract end date"""
        max_extensions, min_days = 3, 360
        for contract in self:
            if not contract.contract_modification_history:
                raise ValidationError(CONTRACT_EXTENSION_NO_RECORD_WARN)
            last_extension = contract.contract_modification_history.sorted(key=lambda r: r.sequence and r.prorroga)[LAST_ONE]
            contract.date_end = last_extension.date_to
            contract.state = 'open'
            if len(contract.contract_modification_history.filtered(lambda r: r.prorroga)) <= max_extensions:
                continue
            extension_span_days = self.dias360(
                last_extension.date_from, last_extension.date_to)                
            if extension_span_days < min_days:
                raise ValidationError(CONTRACT_EXTENSION_MAX_WARN)

    @api.model
    def update_state(self):
        contracts = self.search([
            ('state', '=', 'open'), ('kanban_state', '!=', 'blocked'),
            '|',
            '&',
            ('date_end', '<=', fields.Date.to_string(date.today() + relativedelta(days=7))),
            ('date_end', '>=', fields.Date.to_string(date.today() + relativedelta(days=1))),
            '&',
            ('visa_expire', '<=', fields.Date.to_string(date.today() + relativedelta(days=60))),
            ('visa_expire', '>=', fields.Date.to_string(date.today() + relativedelta(days=1))),
        ])

        for contract in contracts:
            contract.activity_schedule(
                'mail.mail_activity_data_todo', contract.date_end,
                _("The contract of %s is about to expire.", contract.employee_id.name),
                user_id=contract.hr_responsible_id.id or self.env.uid)

        contracts.write({'kanban_state': 'blocked'})

        self.search([
            ('state', '=', 'open'),
            '|',
            ('date_end', '<=', fields.Date.to_string(date.today() + relativedelta(days=1))),
            ('visa_expire', '<=', fields.Date.to_string(date.today() + relativedelta(days=1))),
        ]).write({
            'state': 'finished'
        })

        self.search([('state', '=', 'draft'), ('kanban_state', '=', 'done'),
                     ('date_start', '<=', fields.Date.to_string(date.today())), ]).write({
            'state': 'open'
        })

        contract_ids = self.search([('date_end', '=', False), ('state', '=', 'finished'), ('employee_id', '!=', False)])
        # Ensure all finished contract followed by a new contract have a end date.
        # If finished contract has no finished date, the work entries will be generated for an unlimited period.
        for contract in contract_ids:
            next_contract = self.search([
                ('employee_id', '=', contract.employee_id.id),
                ('state', 'not in', ['cancel', 'new']),
                ('date_start', '>', contract.date_start)
            ], order="date_start asc", limit=1)
            if next_contract:
                contract.date_end = next_contract.date_start - relativedelta(days=1)
                continue
            next_contract = self.search([
                ('employee_id', '=', contract.employee_id.id),
                ('date_start', '>', contract.date_start)
            ], order="date_start asc", limit=1)
            if next_contract:
                contract.date_end = next_contract.date_start - relativedelta(days=1)

        return True

    def action_state_open(self):
        self.write({'state':'open'})
        self._sync_employee_version_contract_fields()

    def action_state_cancel(self):
        self.write({'state':'cancel'})

    def action_state_finished(self):
        self.write({'state':'finished'})

    @api.depends('change_wage_ids')
    @api.onchange('change_wage_ids')
    def change_wage(self):
        for record in self:
            for change in sorted(record.change_wage_ids, key=lambda x: x.date_start):
                record.wage = change.wage
                record.job_id = change.job_id
                record.wage_old = change.wage
                record.date_last_wage = change.date_start

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['sequence'] = self.env['ir.sequence'].next_by_code('hr.contract.seq') or ' '
        obj_contract = super().create(vals_list)
        obj_contract._sync_employee_version_contract_fields()
        return obj_contract
    
    def get_wage_in_date(self,process_date):
        wage_in_date = self.wage
        for change in sorted(self.change_wage_ids, key=lambda x: x.date_start):
            if process_date >= change.date_start:
                wage_in_date = change.wage
        return wage_in_date


    def generate_labor_certificate(self):
        ctx = self.env.context.copy()
        ctx.update({'default_contract_id': self.id, 'default_date_generation': fields.Date.today()})

        return {
            'type': 'ir.actions.act_window',
            'name': 'Certificado laboral',
            'res_model': 'hr.labor.certificate.history',
            'domain': [],
            'view_mode': 'form',
            'target':'new',
            'context': ctx
        }

    def get_contract_type(self):
        """Obtiene el nombre del tipo de contrato desde contract_type_id."""
        if self.contract_type_id:
            return self.contract_type_id.name.upper() if self.contract_type_id.name else ''
        return ''

    def get_date_text(self,date,calculated_week=0):
        #Mes
        month = ''
        month = 'Enero' if date.month == 1 else month
        month = 'Febrero' if date.month == 2 else month
        month = 'Marzo' if date.month == 3 else month
        month = 'Abril' if date.month == 4 else month
        month = 'Mayo' if date.month == 5 else month
        month = 'Junio' if date.month == 6 else month
        month = 'Julio' if date.month == 7 else month
        month = 'Agosto' if date.month == 8 else month
        month = 'Septiembre' if date.month == 9 else month
        month = 'Octubre' if date.month == 10 else month
        month = 'Noviembre' if date.month == 11 else month
        month = 'Diciembre' if date.month == 12 else month
        #Dia de la semana
        week = ''
        week = 'Lunes' if date.weekday() == 0 else week
        week = 'Martes' if date.weekday() == 1 else week
        week = 'Miercoles' if date.weekday() == 2 else week
        week = 'Jueves' if date.weekday() == 3 else week
        week = 'Viernes' if date.weekday() == 4 else week
        week = 'Sábado' if date.weekday() == 5 else week
        week = 'Domingo' if date.weekday() == 6 else week
        
        if calculated_week == 0:
            date_text = date.strftime('%d de '+month+' del %Y')
        else:
            date_text = date.strftime(week+', %d de '+month+' del %Y')

        return date_text

    def get_amount_text(self, valor):
        letter_amount = self.numero_to_letras(float(valor))         
        return letter_amount.upper()

    def get_average_concept_heyrec(self): #Promedio horas extra
        promedio = False
        model_payslip = self.env['hr.payslip']
        model_payslip_line = self.env['hr.payslip.line']
        today = datetime.today()
        date_start =  today + relativedelta(months=-3)
        today_str = today.strftime("%Y-%m-01")
        date_start_str = date_start.strftime("%Y-%m-01")
        slips_ids = model_payslip.search([('date_from','>=',date_start_str),('date_to','<=',today_str),('contract_id','=',self.id),('state','=','done')])
        if slips_ids:
            grouped = model_payslip_line._read_group(
                [('slip_id', 'in', slips_ids.ids), ('category_id.code', '=', 'HEYREC')],
                groupby=[],
                aggregates=['total:sum'],
            )
            total = grouped[0][0] or 0.0 if grouped else 0.0
            if len(slips_ids)/2 > 0:
                promedio = total/(len(slips_ids)/2)                            
        return promedio

    def get_average_concept_certificate(self,salary_rule_id,last,average,value_contract,payment_frequency): #Promedio horas extra
        model_payslip = self.env['hr.payslip']
        model_payslip_line = self.env['hr.payslip.line']
        today = datetime.today()
        if last == True:
            total = False
            date_start = today + relativedelta(months=-1)
            today_str = today.strftime("%Y-%m-01")
            date_start_str = date_start.strftime("%Y-%m-01")
            slips_ids = model_payslip.search([('date_from','>=',date_start_str),('date_to','<=',today_str), ('contract_id', '=', self.id),('state', '=', 'done')])
            if slips_ids:
                grouped = model_payslip_line._read_group(
                    [('slip_id', 'in', slips_ids.ids), ('salary_rule_id', '=', salary_rule_id.id)],
                    groupby=[],
                    aggregates=['total:sum'],
                )
                total = grouped[0][0] or 0.0 if grouped else 0.0
            return total
        if average == True:
            promedio = False
            date_start =  today + relativedelta(months=-3)
            today_str = today.strftime("%Y-%m-01")
            date_start_str = date_start.strftime("%Y-%m-01")
            slips_ids = model_payslip.search([('date_from','>=',date_start_str),('date_to','<=',today_str),('contract_id','=',self.id),('state','in',['done','paid'])])
            if slips_ids:
                grouped = model_payslip_line._read_group(
                    [('slip_id', 'in', slips_ids.ids), ('salary_rule_id', '=', salary_rule_id.id)],
                    groupby=[],
                    aggregates=['total:sum'],
                )
                total = grouped[0][0] or 0.0 if grouped else 0.0
                if payment_frequency == 'biweekly':
                    if len(slips_ids)/2 > 0:
                        promedio = total/(len(slips_ids)/2)
                else:
                    if len(slips_ids) > 0:
                        promedio = total/(len(slips_ids))
            return promedio
        if value_contract == True:
            obj_concept = self.concepts_ids.filtered(lambda x: x.input_id.id == salary_rule_id.id)
            if len(obj_concept) == 1:
                rule_value = sum([i.amount for i in obj_concept])
                if obj_concept.aplicar == '0':
                    rule_value = rule_value * 2
                if obj_concept.input_id.modality_value == 'diario':
                    rule_value = rule_value * 30
                return rule_value
            else:
                return 0
        return 0

    def get_signature_certification(self):
        res = {'nombre':'NO AUTORIZADO', 'cargo':'NO AUTORIZADO','firma':''}
        obj_user = self.env['res.users'].search([('signature_certification_laboral','=',True)])
        for user in obj_user:
            res['nombre'] = user.name
            res['cargo'] = 'Dirección Nacional de Talento Humano'
            res['firma'] = user.signature_documents

        return res
    def generate_report_severance(self):
        ctx = self.env.context.copy()
        ctx.update({'default_contract_id': self.id})

        return {
            'type': 'ir.actions.act_window',
            'name': 'Carta para retiro de cesantías',
            'res_model': 'lavish.retirement.severance.pay',
            'domain': [],
            'view_mode': 'form',
            'target':'new',
            'context': ctx
        }
    
    def has_change_salary(self, date_from, date_to):
        wages_in_period = filter(
            lambda x: date_from <= x.date_start <= date_to, self.change_wage_ids)
        return len(list(wages_in_period)) >= 1 

    def get_pend_vac(self, date_calc=None, sus=0):
        """
        Calcula días pendientes de vacaciones.
        Considera días disfrutados, compensados en dinero, interrupciones e incapacidades.
        """
        if date_calc:
            date_calc = date_calc
        else:
            date_calc = datetime.now()

        # Consulta corregida SIN GROUP BY para evitar duplicados
        vac_book_q = """
            SELECT
                COALESCE(SUM(vb.business_units), 0) as total_business,
                COALESCE(SUM(vb.holiday_value), 0) as total_holiday,
                COALESCE(SUM(vb.units_of_money), 0) as total_money,
                COALESCE(SUM(vb.days_returned), 0) as total_returned,
                COALESCE(SUM(vb.disability_days), 0) as total_disability
            FROM hr_vacation vb
            INNER JOIN hr_contract hc ON hc.id = vb.contract_id
            LEFT JOIN hr_payslip hp ON hp.id = vb.payslip
            WHERE hc.id = %s
            AND (hp.date_liquidacion <= %s OR vb.payslip IS NULL)
        """

        self._cr.execute(vac_book_q, (self.id, date_calc))
        result = self._cr.fetchone()

        # Procesar resultados
        lic = sus  # Licencias no remuneradas
        if result:
            total_business = result[0] or 0
            total_holiday = result[1] or 0
            total_money = result[2] or 0
            total_returned = result[3] or 0
            total_disability = result[4] or 0

            # Sumar festivos a licencias
            lic += total_holiday

            # Días tomados = días hábiles + días en dinero - días devueltos - días de incapacidad
            taken = total_business + total_money - total_returned - total_disability
        else:
            taken = 0

        # Calcular días trabajados
        k_dt_start = self.date_start
        init_date = self.env.company.init_vac_date
        if init_date and k_dt_start < init_date:
            k_dt_start = self.env.company.init_vac_date
        dt_end = date_calc
        days = days360(k_dt_start, dt_end)
        days_wo_lic = days - lic

        # Calcular días causados según tipo de empleado
        if not self.employee_id.indicador_especial_id.code == '1':
            dv_total = float(days_wo_lic) * 15 / 360
        else:
            dv_total = float(days_wo_lic) * 30 / 360

        # Días pendientes
        dv_pend = dv_total - taken
        return dv_pend

#Historico generación de certificados laborales
