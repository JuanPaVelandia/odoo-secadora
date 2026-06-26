from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import math
import logging
import pytz

_logger = logging.getLogger(__name__)
UTC = pytz.UTC

# -------------------------------------------------------------------------
# Importar constantes globales desde hr_payslip_constants (mismo módulo)
# -------------------------------------------------------------------------
from odoo.addons.lavish_hr_employee.models.payroll.hr_payslip_constants import (
    NOVELTY_TYPE_SELECTION,
    LIQUIDATION_VALUE_SELECTION,
    NOVELTY_TYPES_CONFIG,
    get_novelty_config,
)



class HrWorkEntryType(models.Model):
    _inherit = "hr.work.entry.type"

    deduct_deductions = fields.Selection(
        selection=[
            ('all', 'Todas las deducciones'),
            ('law', 'Solo las deducciones de ley')
        ],
        string='Tener en cuenta al descontar',
        default='all',
        help='DEDUCCIONES A CONSIDERAR EN AUSENCIAS\n'
             '------------------------------------------------------------\n'
             'OPCIONES:\n'
             '  + all ... Aplica TODAS las deducciones del empleado\n'
             '  + law ... Solo aplica deducciones de LEY (salud, pension)\n'
             '------------------------------------------------------------\n'
             'EJEMPLO - Empleado con deducciones:\n'
             '  . Salud: $120.000\n'
             '  . Pension: $160.000\n'
             '  . Libranza: $200.000\n'
             '  . Cooperativa: $50.000\n'
             '------------------------------------------------------------\n'
             '  + all --> Deduce $530.000 total\n'
             '  + law --> Deduce $280.000 (solo salud + pension)'
    )
    not_contribution_base = fields.Boolean(
        string='No es base de aportes',
        help='EXCLUIR DE BASE DE SEGURIDAD SOCIAL\n'
             '------------------------------------------------------------\n'
             'Si esta marcado:\n'
             '  + Esta ausencia NO es base para aportes\n'
             '  + NO afecta el IBC del empleado\n'
             '------------------------------------------------------------\n'
             'EJEMPLO - IBC de $3.000.000:\n'
             '  + Con marca: IBC se mantiene en $3.000.000\n'
             '  + Sin marca: IBC puede reducirse por la ausencia'
    )
    short_name = fields.Char(
        string='Nombre corto/reportes',
        help='NOMBRE ABREVIADO PARA REPORTES\n'
             '------------------------------------------------------------\n'
             'Texto corto que aparece en reportes y listados\n'
             'donde el espacio es limitado.\n'
             '------------------------------------------------------------\n'
             'EJEMPLO:\n'
             '  + Nombre: "Incapacidad por Enfermedad General"\n'
             '  + Corto:  "Inc.EG"'
    )
    pay_transport_allowance = fields.Boolean(
        string='Paga auxilio de transporte',
        default=True,
        help='PAGAR AUXILIO DURANTE ESTA ENTRADA DE TRABAJO\n'
             '------------------------------------------------------------\n'
             'Si esta marcado:\n'
             '  + Se paga auxilio de transporte proporcional\n'
             'Si NO esta marcado:\n'
             '  + NO se paga auxilio por estos dias\n'
             '------------------------------------------------------------\n'
             'EJEMPLO - Empleado con aux. transporte $162.000/mes:\n'
             '  + 5 dias ausencia con marca: Paga $27.000\n'
             '  + 5 dias ausencia sin marca: Paga $0'
    )

class HrLeaveType(models.Model):
    _inherit = 'hr.leave.type'
    
    # -------------------------------------------------------------------------
    # IDENTIFICACION
    # -------------------------------------------------------------------------
    code = fields.Char(
        string='Codigo',
        help='CODIGO UNICO DEL TIPO DE AUSENCIA\n'
             '------------------------------------------------------------\n'
             'Identificador unico usado en:\n'
             '  + Reportes de nomina\n'
             '  + Integraciones con otros sistemas\n'
             '  + Busquedas rapidas\n'
             '------------------------------------------------------------\n'
             'EJEMPLOS:\n'
             '  + VAC ........ Vacaciones\n'
             '  + INC_EPS .... Incapacidad EPS\n'
             '  + LIC_MAT .... Licencia Maternidad\n'
             '  + LNR ........ Licencia No Remunerada'
    )
    is_vacation = fields.Boolean(
        string='Tipo de ausencia para vacaciones disfrutadas',
        help='MARCAR COMO VACACIONES DISFRUTADAS\n'
             '------------------------------------------------------------\n'
             'Si esta marcado:\n'
             '  + Se descuentan dias del saldo de vacaciones\n'
             '  + Aplica calculo especial de vacaciones\n'
             '  + Se registra en historico de vacaciones\n'
             '------------------------------------------------------------\n'
             'EJEMPLO:\n'
             '  Empleado con 15 dias acumulados toma 5 dias\n'
             '  --> Saldo queda en 10 dias'
    )
    is_vacation_money = fields.Boolean(
        string='Vacaciones disfrutadas En Dinero',
        help='VACACIONES COMPENSADAS EN DINERO\n'
             '------------------------------------------------------------\n'
             'Si esta marcado:\n'
             '  + Se pagan vacaciones sin disfrutarlas\n'
             '  + El empleado NO descansa, recibe pago\n'
             '  + Se descuentan del saldo de vacaciones\n'
             '------------------------------------------------------------\n'
             'BASE LEGAL: Art. 189 CST - Maximo 50% en dinero\n'
             '------------------------------------------------------------\n'
             'EJEMPLO:\n'
             '  Empleado con 15 dias, pide 7 en dinero\n'
             '  --> Recibe pago de 7 dias\n'
             '  --> Saldo queda en 8 dias'
    )
    
    # -------------------------------------------------------------------------
    # VALIDACION
    # -------------------------------------------------------------------------
    obligatory_attachment = fields.Boolean(
        string='Obligar adjunto',
        help='REQUERIR DOCUMENTO ADJUNTO\n'
             '------------------------------------------------------------\n'
             'Si esta marcado:\n'
             '  + No se puede aprobar sin adjunto\n'
             '  + El sistema bloquea la validacion\n'
             '------------------------------------------------------------\n'
             'USO TIPICO:\n'
             '  + Incapacidades: Requiere certificado medico\n'
             '  + Luto: Requiere certificado de defuncion\n'
             '  + Calamidad: Requiere soporte'
    )
    
    # -------------------------------------------------------------------------
    # CONFIGURACION EPS/ARL
    # Define como la EPS o ARL paga la incapacidad
    # -------------------------------------------------------------------------
    num_days_no_assume = fields.Integer(
        string='Numero de dias que no asume',
        help='DIAS QUE PAGA LA EMPRESA (NO LA EPS/ARL)\n'
             '------------------------------------------------------------\n'
             'Numero de dias iniciales que paga la empresa.\n'
             'A partir del dia siguiente, paga la EPS/ARL.\n'
             '------------------------------------------------------------\n'
             'VALORES TIPICOS:\n'
             '  + Incapacidad EPS: 2 dias (empresa paga 1-2)\n'
             '  + Incapacidad ARL: 1 dia (empresa paga dia 1)\n'
             '------------------------------------------------------------\n'
             'EJEMPLO - Incapacidad de 10 dias:\n'
             '  + Dias 1-2: Empresa paga 100%\n'
             '  + Dias 3-10: EPS paga 66.67%'
    )
    recognizing_factor_eps_arl = fields.Float(
        string='Factor que reconoce la EPS/ARL',
        digits=(25, 5),
        help='PORCENTAJE QUE PAGA LA EPS/ARL\n'
             '------------------------------------------------------------\n'
             'Porcentaje del salario que reconoce la entidad.\n'
             'Valor entre 0 y 100.\n'
             '------------------------------------------------------------\n'
             'VALORES SEGUN LEY:\n'
             '  + Incap. EPS (dias 3-90): 66.67%\n'
             '  + Incap. EPS (dias 91-180): 50%\n'
             '  + Incap. ARL: 100%\n'
             '  + Maternidad: 100%\n'
             '------------------------------------------------------------\n'
             'EJEMPLO - Salario $3.000.000, 10 dias, factor 66.67%:\n'
             '  Pago EPS = $3.000.000 / 30 * 8 * 0.6667 = $533.360'
    )
    periods_calculations_ibl = fields.Integer(
        string='Periodos para calculo de IBL',
        help='MESES PARA CALCULAR IBL DE EPS/ARL\n'
             '------------------------------------------------------------\n'
             'Numero de meses a promediar para obtener el IBL.\n'
             'Se toman los meses anteriores a la ausencia.\n'
             '------------------------------------------------------------\n'
             'VALORES TIPICOS:\n'
             '  + Incapacidad corta: 1 mes\n'
             '  + Licencia maternidad: 12 meses\n'
             '------------------------------------------------------------\n'
             'EJEMPLO - Periodos = 3:\n'
             '  . Octubre: IBC $3.000.000\n'
             '  . Noviembre: IBC $3.200.000\n'
             '  . Diciembre: IBC $3.100.000\n'
             '  --> IBL = ($3M + $3.2M + $3.1M) / 3 = $3.100.000'
    )
    eps_arl_input_id = fields.Many2one(
        comodel_name='hr.salary.rule',
        string='Regla de la incapacidad',
        help='REGLA SALARIAL PARA PAGO EPS/ARL\n'
             '------------------------------------------------------------\n'
             'Regla que se ejecuta para calcular el pago.\n'
             'Debe estar configurada en la estructura de nomina.\n'
             '------------------------------------------------------------\n'
             'EJEMPLOS DE REGLAS:\n'
             '  + INC_EPS_001: Incapacidad EPS dias 3-90\n'
             '  + INC_ARL_001: Incapacidad ARL\n'
             '  + LIC_MAT_001: Licencia Maternidad'
    )
    
    # -------------------------------------------------------------------------
    # CONFIGURACION EMPRESA
    # Define como la empresa paga los primeros dias
    # -------------------------------------------------------------------------
    recognizing_factor_company = fields.Float(
        string='Factor que reconoce la empresa',
        digits=(25, 5),
        help='PORCENTAJE QUE PAGA LA EMPRESA\n'
             '------------------------------------------------------------\n'
             'Porcentaje del salario que paga la empresa\n'
             'en los primeros dias de incapacidad.\n'
             '------------------------------------------------------------\n'
             'VALOR TIPICO: 100% (empresa paga salario completo)\n'
             '------------------------------------------------------------\n'
             'EJEMPLO - Salario $3.000.000, 2 dias, factor 100%:\n'
             '  Pago empresa = $3.000.000 / 30 * 2 * 1.0 = $200.000'
    )
    periods_calculations_ibl_company = fields.Integer(
        string='Periodos para calculo de IBL Empresa',
        help='MESES PARA CALCULAR IBL DE EMPRESA\n'
             '------------------------------------------------------------\n'
             'Numero de meses a promediar para los dias\n'
             'que paga la empresa.\n'
             '------------------------------------------------------------\n'
             'VALOR TIPICO: 1 (mes anterior)\n'
             'Si es 0: Usa el salario actual del contrato'
    )
    company_input_id = fields.Many2one(
        comodel_name='hr.salary.rule',
        string='Regla de la incapacidad empresa',
        help='REGLA SALARIAL PARA PAGO EMPRESA\n'
             '------------------------------------------------------------\n'
             'Regla que se ejecuta para calcular el pago\n'
             'de los dias que asume la empresa.\n'
             '------------------------------------------------------------\n'
             'EJEMPLO:\n'
             '  INC_EMP_001: Pago dias 1-2 incapacidad'
    )
    # -------------------------------------------------------------------------
    # CONFIGURACION DE COMPORTAMIENTO
    # Estos valores se heredan como DEFAULT en cada ausencia individual
    # El usuario puede sobrescribirlos en la ausencia si es necesario
    # -------------------------------------------------------------------------
    unpaid_absences = fields.Boolean(
        string='Ausencia no remunerada',
        help='AUSENCIA SIN PAGO DE SALARIO\n'
             '------------------------------------------------------------\n'
             'Si esta marcado:\n'
             '  + NO paga salario al empleado\n'
             '  + NO suma al IBC de seguridad social\n'
             '  + Resta dias trabajados del periodo\n'
             '------------------------------------------------------------\n'
             'Tipos tipicos: lnr (licencia no remunerada), sln, p'
    )
    discounting_bonus_days = fields.Boolean(
        string='Descontar en Prima/Cesantias',
        help='DESCUENTA DIAS PARA CALCULO DE PRIMA\n'
             '------------------------------------------------------------\n'
             'Si esta marcado:\n'
             '  + Los dias de esta ausencia se restan del calculo de prima\n'
             '  + Afecta proporcionalidad de la prima semestral\n'
             '------------------------------------------------------------\n'
             'Tipos tipicos que descuentan: lnr, sln'
    )
    # -------------------------------------------------------------------------
    # FESTIVOS - Campo principal para control de dias festivos
    # -------------------------------------------------------------------------
    evaluates_day_off = fields.Boolean(
        string='Pagar dias festivos',
        help='PAGAR FESTIVOS DENTRO DEL PERIODO DE AUSENCIA\n'
             '------------------------------------------------------------\n'
             'COMPORTAMIENTO:\n'
             '  [x] Marcado:\n'
             '      + Los festivos dentro del periodo SE PAGAN\n'
             '      + Se incluyen en el calculo de dias\n'
             '      + Aparecen como dias pagados en la nomina\n'
             '  [ ] Desmarcado:\n'
             '      + Los festivos SE SALTAN (no se pagan)\n'
             '      + Solo se pagan dias laborales\n'
             '------------------------------------------------------------\n'
             'EJEMPLO - Ausencia 1-10 enero (festivo el 6):\n'
             '  + Con marca: 10 dias pagados\n'
             '  + Sin marca: 9 dias pagados (festivo se salta)\n'
             '------------------------------------------------------------\n'
             'USO TIPICO:\n'
             '  + Vacaciones: SI pagar festivos (dias corridos)\n'
             '  + Incapacidad: SI pagar festivos (calendario)\n'
             '  + Permiso: NO pagar festivos (solo laborales)'
    )
    sub_wd = fields.Boolean(
        string='Resta en dias Trabajados',
        default=True,
        help='RESTAR DIAS DE LOS DIAS TRABAJADOS\n'
             '------------------------------------------------------------\n'
             'Si esta marcado:\n'
             '  + Los dias de ausencia se restan de dias trabajados\n'
             '  + Afecta calculo de conceptos proporcionales\n'
             '------------------------------------------------------------\n'
             'Ejemplo: 30 dias - 5 ausencia = 25 dias trabajados'
    )
    pay_transport_allowance = fields.Boolean(
        string='Paga auxilio de transporte',
        default=False,
        help='PAGAR AUXILIO DE TRANSPORTE DURANTE AUSENCIA\n'
             '------------------------------------------------------------\n'
             'Si esta marcado:\n'
             '  + El empleado recibe auxilio de transporte\n'
             '  + Proporcional a los dias de ausencia\n'
             '------------------------------------------------------------\n'
             'Tipos que SI pagan: lr (licencia remunerada), lt (luto)\n'
             'Tipos que NO pagan: vacaciones, incapacidades'
    )
    apply_day_31 = fields.Boolean(
        string='Aplica dia 31',
        help='DEFAULT para ausencias - Incluir dia 31\n'
             '------------------------------------------------------------\n'
             'Si esta marcado:\n'
             '  + El dia 31 se cuenta y paga normalmente\n'
             '  + El mes se trata de 31 dias\n'
             'Si NO esta marcado:\n'
             '  + El dia 31 NO se paga (mes de 30 dias)\n'
             '------------------------------------------------------------\n'
             'BASE LEGAL: Mes nomina Colombia = 30 dias\n'
             'Este valor se copia a cada ausencia como default.'
    )
    group_leave = fields.Boolean(
        string='Agrupar ausencias',
        help='AGRUPAR AUSENCIAS CONSECUTIVAS\n'
             '------------------------------------------------------------\n'
             'Si esta marcado:\n'
             '  + Ausencias consecutivas del mismo tipo se agrupan\n'
             '  + Se procesan como una sola ausencia en nomina'
    )
    discount_rest_day = fields.Boolean(
        string='Descontar dia de descanso',
        help='DEFAULT para ausencias - Descontar domingos/festivos\n'
             '------------------------------------------------------------\n'
             'Si esta marcado:\n'
             '  + Los dias de descanso NO se pagan\n'
             '  + Solo se pagan dias laborales\n'
             'Si NO esta marcado:\n'
             '  + Se pagan todos los dias corridos\n'
             '------------------------------------------------------------\n'
             'Uso tipico:\n'
             '  + Vacaciones: NO descuenta (dias corridos)\n'
             '  + Licencia no remunerada: SI descuenta\n'
             'Este valor se copia a cada ausencia como default.'
    )
    published_portal = fields.Boolean(
        string='Permitir uso en portal de autogestion',
        help='DISPONIBLE EN PORTAL DEL EMPLEADO\n'
             '------------------------------------------------------------\n'
             'Si esta marcado:\n'
             '  + El empleado puede solicitar esta ausencia\n'
             '  + Aparece en el portal de autogestion\n'
             'Si NO esta marcado:\n'
             '  + Solo RRHH puede crear esta ausencia\n'
             '------------------------------------------------------------\n'
             'USO TIPICO:\n'
             '  + Vacaciones: SI publicar\n'
             '  + Incapacidades: NO publicar (requiere validacion)'
    )
    type_of_entity_association = fields.Many2one(
        comodel_name='hr.contribution.register',
        string='Tipo de entidad asociada',
        help='ENTIDAD QUE PAGA LA AUSENCIA\n'
             '------------------------------------------------------------\n'
             'Tipo de entidad responsable del pago.\n'
             'Se usa para asociar automaticamente la entidad\n'
             'del empleado al crear la ausencia.\n'
             '------------------------------------------------------------\n'
             'EJEMPLOS:\n'
             '  + Incapacidad EPS: Tipo = EPS\n'
             '  + Incapacidad ARL: Tipo = ARL\n'
             '  + Maternidad: Tipo = EPS'
    )
    
    # -------------------------------------------------------------------------
    # TIPO DE NOVEDAD PILA
    # Usa constantes globales desde hr_slip_constante.py
    # -------------------------------------------------------------------------
    novelty = fields.Selection(
        string="Tipo de Ausencia (PILA)",
        selection=NOVELTY_TYPE_SELECTION,
        help='TIPO DE NOVEDAD PILA - Codigo para reporte de seguridad social\n'
             '------------------------------------------------------------\n'
             'COMPORTAMIENTO SEGUN TIPO:\n'
             '  + sln, lnr, p ... NO suma al IBC, NO paga salario\n'
             '  + ige, irl ...... Mantiene IBC, paga segun tramos\n'
             '  + lma, lpa ...... Mantiene IBC, paga 100%\n'
             '  + vdi, vco, vre . Mantiene IBC, paga vacaciones\n'
             '  + lr, lt ........ Mantiene IBC, paga salario\n'
             '------------------------------------------------------------\n'
             'IMPORTANTE: Este campo define como afecta la ausencia\n'
             'al calculo del IBC para seguridad social (PILA).'
    )
    liquidacion_value = fields.Selection(
        string="Tipo de liquidacion de valores",
        selection=LIQUIDATION_VALUE_SELECTION,
        default='WAGE',
        help='BASE PARA LIQUIDAR VALOR DE LA AUSENCIA\n'
             '------------------------------------------------------------\n'
             'OPCIONES:\n'
             '  + IBC .... Usa IBC del mes anterior (incapacidades)\n'
             '  + YEAR ... Usa promedio del año anterior\n'
             '  + WAGE ... Usa sueldo actual del contrato\n'
             '  + MIN .... Usa salario minimo legal vigente\n'
             '------------------------------------------------------------\n'
             'EJEMPLO - Empleado con salario $3.000.000:\n'
             '  . WAGE: Base = $3.000.000 / 30 = $100.000/dia\n'
             '  . MIN:  Base = SMMLV / 30 (ej: $1.300.000/30)\n'
             '  . IBC:  Base = IBC mes anterior / 30'
    )

    # -------------------------------------------------------------------------
    # RANGOS DE ENFERMEDAD (Incapacidades largas)
    # Permite configurar diferentes porcentajes segun duracion
    # -------------------------------------------------------------------------
    rango_adicionales_enfermedad = fields.Boolean(
        string='Mostrar Rango Adicionales Enfermedad',
        help='HABILITAR RANGOS POR DURACION\n'
             '------------------------------------------------------------\n'
             'Si esta marcado:\n'
             '  + Se muestran campos para configurar porcentajes\n'
             '    segun la duracion de la incapacidad\n'
             '  + Permite diferentes pagos por tramos\n'
             '------------------------------------------------------------\n'
             'TRAMOS SEGUN LEY (Art. 227 CST):\n'
             '  + Dias 1-2: Empresa 100%\n'
             '  + Dias 3-90: EPS 66.67%\n'
             '  + Dias 91-180: EPS 50%\n'
             '  + Dias 181+: EPS 50%'
    )
    gi_b2 = fields.Float(
        string='Porcentaje dias 1-2',
        default=100,
        help='PORCENTAJE PARA DIAS 1 Y 2\n'
             '------------------------------------------------------------\n'
             'Porcentaje que paga la empresa en primeros dias.\n'
             '------------------------------------------------------------\n'
             'VALOR LEGAL: 100%\n'
             '------------------------------------------------------------\n'
             'EJEMPLO - Salario $3.000.000:\n'
             '  Pago dia = $3.000.000 / 30 * 1.0 = $100.000/dia'
    )
    gi_b90 = fields.Float(
        string='Porcentaje dias 3-90',
        default=66.67,
        help='PORCENTAJE PARA DIAS 3 A 90\n'
             '------------------------------------------------------------\n'
             'Porcentaje que paga la EPS despues de los\n'
             'primeros dias hasta el dia 90.\n'
             '------------------------------------------------------------\n'
             'VALOR LEGAL: 66.67% (2/3 del salario)\n'
             '------------------------------------------------------------\n'
             'EJEMPLO - Salario $3.000.000:\n'
             '  Pago dia = $3.000.000 / 30 * 0.6667 = $66.670/dia'
    )
    gi_b180 = fields.Float(
        string='Porcentaje dias 91-180',
        default=50,
        help='PORCENTAJE PARA DIAS 91 A 180\n'
             '------------------------------------------------------------\n'
             'Porcentaje que paga la EPS despues del dia 90\n'
             'hasta el dia 180.\n'
             '------------------------------------------------------------\n'
             'VALOR LEGAL: 50%\n'
             '------------------------------------------------------------\n'
             'EJEMPLO - Salario $3.000.000:\n'
             '  Pago dia = $3.000.000 / 30 * 0.50 = $50.000/dia'
    )
    gi_a180 = fields.Float(
        string='Porcentaje dias 181+',
        default=50,
        help='PORCENTAJE PARA DIAS MAYORES A 180\n'
             '------------------------------------------------------------\n'
             'Porcentaje que paga la EPS despues del dia 180.\n'
             'Requiere proceso especial de pension por invalidez.\n'
             '------------------------------------------------------------\n'
             'VALOR LEGAL: 50%\n'
             'NOTA: Despues de 540 dias se debe tramitar pension'
    )
    gi_b180_eps_arl_input_id = fields.Many2one(
        comodel_name='hr.salary.rule',
        string='Regla incapacidad 91-180 dias',
        help='REGLA SALARIAL PARA DIAS 91 A 180\n'
             '------------------------------------------------------------\n'
             'Regla especifica para el tramo de dias 91-180.\n'
             'Normalmente aplica el 50% del salario.'
    )
    gi_a180_eps_arl_input_id = fields.Many2one(
        comodel_name='hr.salary.rule',
        string='Regla incapacidad 181+ dias',
        help='REGLA SALARIAL PARA DIAS MAYORES A 180\n'
             '------------------------------------------------------------\n'
             'Regla especifica para el tramo de dias 181+.\n'
             'Normalmente aplica el 50% del salario.'
    )
    # -------------------------------------------------------------------------
    # COMPLEMENTO DE SALARIO POR INCAPACIDAD
    # Cuando la EPS paga menos del 100%, empresa puede completar
    # -------------------------------------------------------------------------
    completar_salario = fields.Boolean(
        string='Completar salario',
        help='EMPRESA COMPLETA DIFERENCIA DE SALARIO\n'
             '------------------------------------------------------------\n'
             'Si esta marcado:\n'
             '  + La empresa paga la diferencia entre el\n'
             '    porcentaje de la EPS y el 100%\n'
             '  + El empleado recibe su salario completo\n'
             '  + Se genera LINEA SEPARADA en nomina\n'
             '------------------------------------------------------------\n'
             'IMPORTANTE PARA CONTABILIDAD:\n'
             '  + Valor EPS: Se registra como cuenta por cobrar\n'
             '  + Valor complemento: Gasto directo de empresa\n'
             '  + Ambos valores se muestran por separado\n'
             '    para facilitar depuracion y conciliacion\n'
             '------------------------------------------------------------\n'
             'EJEMPLO - Salario $3.000.000, 8 dias EPS (66.67%):\n'
             '  . Valor dia = $3M / 30 = $100.000\n'
             '  . EPS paga (66.67%): $100.000 * 0.6667 * 8 = $533.360\n'
             '  . Diferencia (33.33%): $100.000 * 0.3333 * 8 = $266.640\n'
             '------------------------------------------------------------\n'
             'EN NOMINA SE VERAN 2 LINEAS:\n'
             '  1. [Regla EPS] Incapacidad EPS: $533.360\n'
             '  2. [Regla Complemento] Complemento Inc.: $266.640\n'
             '  --> Total empleado: $800.000'
    )
    company_complement_input_id = fields.Many2one(
        comodel_name='hr.salary.rule',
        string='Regla complemento salario',
        help='REGLA PARA PAGO COMPLEMENTO DE INCAPACIDAD\n'
             '------------------------------------------------------------\n'
             'Regla salarial que genera la linea de complemento.\n'
             'Se ejecuta SOLO cuando "Completar salario" esta activo.\n'
             '------------------------------------------------------------\n'
             'REQUISITOS DE LA REGLA:\n'
             '  + Debe ser categoria DEVENGO\n'
             '  + liquidar_con_base = False (usa salario actual)\n'
             '  + NO debe afectar cuenta por cobrar EPS\n'
             '  + Debe ir a cuenta de GASTO de empresa\n'
             '------------------------------------------------------------\n'
             'IMPORTANTE - Campo "Liquidar con IBC mes anterior":\n'
             '  + Esta regla debe tener liquidar_con_base = FALSE\n'
             '  + El complemento se calcula sobre salario ACTUAL\n'
             '  + La diferencia = Salario actual - Valor EPS\n'
             '------------------------------------------------------------\n'
             'EJEMPLO DE CONFIGURACION:\n'
             '  . Codigo: COMP_INC_EPS\n'
             '  . Nombre: Complemento Incapacidad\n'
             '  . Liquidar con IBC: NO (False)\n'
             '  . Cuenta debito: 5105xx (Gasto nomina)\n'
             '  . Cuenta credito: 2505xx (Por pagar)\n'
             '------------------------------------------------------------\n'
             'FLUJO EN NOMINA:\n'
             '  1. Regla EPS: liquidar_con_base=True -> IBC mes anterior\n'
             '  2. Regla complemento: liquidar_con_base=False -> Salario\n'
             '  3. Diferencia = Salario/30*dias - Valor_EPS\n'
             '  4. Se genera linea separada en nomina'
    )
    allow_interruption = fields.Boolean(
        string='Permitir interrupcion',
        default=False,
        help='PERMITIR INTERRUMPIR ESTA AUSENCIA\n'
             '------------------------------------------------------------\n'
             'Si esta marcado:\n'
             '  + Se puede interrumpir la ausencia antes de terminar\n'
             '  + Los dias no disfrutados se devuelven\n'
             '------------------------------------------------------------\n'
             'USO TIPICO: Vacaciones\n'
             '  El empleado puede ser llamado a trabajar\n'
             '  durante sus vacaciones por necesidad.\n'
             '------------------------------------------------------------\n'
             'EJEMPLO:\n'
             '  Vacaciones 10 dias, interrumpe dia 5\n'
             '  --> Se devuelven 5 dias al saldo'
    )

    # -------------------------------------------------------------------------
    # CONFIGURACION IBC SEGUN LEY
    # Parametros para calculo de Ingreso Base de Cotizacion
    # -------------------------------------------------------------------------
    valida_minimo = fields.Boolean(
        string='Validar minimo legal',
        default=True,
        help='VALIDAR QUE IBC NO SEA MENOR AL SMMLV\n'
             '------------------------------------------------------------\n'
             'Si esta marcado:\n'
             '  + El sistema valida que el pago diario no sea\n'
             '    menor al salario minimo diario\n'
             '  + Si es menor, se ajusta al minimo\n'
             '------------------------------------------------------------\n'
             'BASE LEGAL: Art. 18 Ley 100/1993\n'
             '  IBC no puede ser inferior a 1 SMMLV\n'
             '------------------------------------------------------------\n'
             'EJEMPLO - SMMLV $1.300.000:\n'
             '  . Minimo diario = $1.300.000 / 30 = $43.333\n'
             '  . Si pago calculado < $43.333, usa $43.333'
    )
    use_ibl_as_ibc = fields.Boolean(
        string='Usar IBL como IBC',
        default=False,
        help='USAR IBL DEL MES ANTERIOR COMO BASE DE COTIZACION\n'
             '------------------------------------------------------------\n'
             'Si esta marcado:\n'
             '  + El IBC para seguridad social se toma del mes anterior\n'
             '  + NO usa el salario actual del contrato\n'
             '------------------------------------------------------------\n'
             'BASE LEGAL: Art. 3.2.1.10 Decreto 780/2016\n'
             '  Para licencias remuneradas (luto, paternidad, etc.)\n'
             '  el IBC debe ser el del mes anterior.\n'
             '------------------------------------------------------------\n'
             'EJEMPLO:\n'
             '  . Salario actual: $4.000.000\n'
             '  . IBC mes anterior: $3.500.000\n'
             '  . Con marca: IBC = $3.500.000\n'
             '  . Sin marca: IBC = $4.000.000'
    )
    ibc_tope_maximo = fields.Boolean(
        string='Aplicar tope maximo IBC',
        default=True,
        help='APLICAR TOPE DE 25 SMMLV AL IBC\n'
             '------------------------------------------------------------\n'
             'Si esta marcado:\n'
             '  + El IBC no puede superar 25 SMMLV\n'
             '  + Se ajusta automaticamente si lo excede\n'
             '------------------------------------------------------------\n'
             'BASE LEGAL: Art. 18 Ley 100/1993\n'
             '------------------------------------------------------------\n'
             'EJEMPLO - SMMLV $1.300.000:\n'
             '  . Tope = 25 * $1.300.000 = $32.500.000\n'
             '  . Si IBC = $40.000.000, se ajusta a $32.500.000'
    )
    use_calendar_days = fields.Boolean(
        string='Usar dias calendario',
        default=False,
        help='CONTAR TODOS LOS DIAS CALENDARIO\n'
             '------------------------------------------------------------\n'
             'Si esta marcado:\n'
             '  + Se cuentan TODOS los dias (lun-dom)\n'
             '  + Ignora el calendario laboral del empleado\n'
             'Si NO esta marcado:\n'
             '  + Solo cuenta dias habiles segun calendario\n'
             '------------------------------------------------------------\n'
             'USO TIPICO:\n'
             '  + Incapacidades: SI (dias calendario)\n'
             '  + Vacaciones: Segun empresa\n'
             '  + Permisos: NO (solo dias habiles)\n'
             '------------------------------------------------------------\n'
             'EJEMPLO - Ausencia lunes a domingo:\n'
             '  . Calendario: 5 dias (lun-vie)\n'
             '  . Dias calendario: 7 dias (lun-dom)'
    )

    @api.model
    def get_rate_concept_id(self, sequence):
        def check_rule(rule_field, rule_name):
            if not rule_field:
                raise UserError(f"Regla no configurada: {rule_name}")
            return rule_field.id

        # Para novelties que NO son incapacidades (ige/irl), usar company_input_id
        if self.novelty not in ['ige', 'irl']:
            # Usar company_input_id para licencias, vacaciones, suspensiones, etc.
            if self.company_input_id:
                return 1, self.company_input_id.id
            # Fallback a eps_arl_input_id si existe
            elif self.eps_arl_input_id:
                return 1, self.eps_arl_input_id.id
            else:
                raise UserError(f"Regla no configurada para tipo de ausencia: {self.name}")

        if self.rango_adicionales_enfermedad:
            if sequence <= self.num_days_no_assume:
                if self.gi_b2 == 0:
                    raise UserError("No se pudo determinar la regla aplicable para la secuencia dada.")
                else:
                    return self.gi_b2 / 100, check_rule(self.company_input_id, "Compañía (primeros días)")
            elif self.num_days_no_assume < sequence <= 90:
                return self.gi_b90 / 100, check_rule(self.eps_arl_input_id, "EPS/ARL (hasta 90 días)")
            elif 91 <= sequence <= 180:
                return self.gi_b180 / 100, check_rule(self.gi_b180_eps_arl_input_id, "EPS/ARL (91-180 días)")
            elif 181 <= sequence:
                return self.gi_a180 / 100, check_rule(self.gi_a180_eps_arl_input_id, "EPS/ARL (más de 180 días)")
        else:
            if sequence <= self.num_days_no_assume:
                # Convertir porcentaje a decimal (100 -> 1.0, 66.67 -> 0.6667)
                rate = self.recognizing_factor_company / 100 if self.recognizing_factor_company else 1.0
                return rate, check_rule(self.company_input_id, "Compañía")
            else:
                # Convertir porcentaje a decimal (100 -> 1.0, 66.67 -> 0.6667)
                rate = self.recognizing_factor_eps_arl / 100 if self.recognizing_factor_eps_arl else 1.0
                return rate, check_rule(self.eps_arl_input_id, "EPS/ARL")

        raise UserError("No se pudo determinar la regla aplicable para la secuencia dada.")

    _hr_leave_type_code_uniq = models.Constraint('unique(code)',
                                                 'Ya existe este código de nómina, por favor verficar.')
    

    
