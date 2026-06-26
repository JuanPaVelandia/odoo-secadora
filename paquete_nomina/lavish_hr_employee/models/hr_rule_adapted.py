# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.safe_eval import safe_eval
from odoo.addons.lavish_hr_employee.models.hr_slip_data_structures import CategoryCollection
from odoo.addons.lavish_hr_employee.models.hr_slip_utils import (
    DAYS_YEAR, DAYS_YEAR_NATURAL, DAYS_MONTH, days360, round_1_decimal, PeriodoAnterior
)
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
from decimal import Decimal, getcontext, ROUND_HALF_UP
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from collections import defaultdict
import calendar
import time
import logging
# PeriodoAnterior ya importado desde hr_slip_utils

_logger = logging.getLogger(__name__)
getcontext().prec = 10


# ══════════════════════════════════════════════════════════════════════════
# FUNCIONES HELPER
# ══════════════════════════════════════════════════════════════════════════

def monthrange(year=None, month=None):
    """Obtiene el rango de días de un mes"""
    today = datetime.today()
    y = year or today.year
    m = month or today.month
    return y, m, calendar.monthrange(y, m)[1]




class HrSalaryRuleAdapted(models.Model):
    """
    Modelo de reglas salariales adaptado para Colombia.

    Esta clase hereda de múltiples mixins que organizan los métodos de cálculo por categoría:
    - hr.salary.rule.basic: Calculo de salario basico y variantes
    - hr.salary.rule.aux: Auxilios de transporte y conectividad
    - hr.salary.rule.ibd.sss: IBD (Ingreso Base de Cotizacion)
    - hr.salary.rule.ss: Seguridad social (Salud, Pension, Fondos)
    - hr.salary.rule.prestaciones: Prestaciones sociales y provisiones
    - hr.salary.rule.retenciones: Retenciones en la fuente
    - hr.salary.rule.indem: Indemnización por terminación
    - hr.salary.rule.horas.extras: Horas extras y recargos
    - hr.salary.rule.otros: Métodos auxiliares y totales
    """
    _name = 'hr.salary.rule'
    _inherit = [
        'hr.salary.rule',
        'mail.thread',
        'mail.activity.mixin',
        'hr.salary.rule.basic',
        'hr.salary.rule.aux',
        'hr.salary.rule.ibd.sss',
        'hr.salary.rule.ss',  # Seguridad social (separado de IBD)
        'hr.salary.rule.prestaciones',
        'hr.salary.rule.retenciones',
        'hr.salary.rule.indem',
        'hr.salary.rule.horas.extras',
        'hr.salary.rule.otros',
    ]
    _AFECTA_TOTALES_DEV_CATS = [
        'DEV_SALARIAL',
        'DEV_NO_SALARIAL',
        'PRESTACIONES_SOCIALES',
        'PRIMA',
        'AUX',
        'IND',
    ]
    _AFECTA_TOTALES_DED_CATS = [
        'DED',
        'DEDUCCIONES',
        'SSOCIAL',   # salud, pensión, fondos de solidaridad/subsistencia (deducciones del empleado)
        'EM',        # embargos
    ]
    _SPLIT_PRESTACION_FIELDS = {
        'base_prima': ('base_prima_provision', 'base_prima_liquidacion'),
        'base_cesantias': ('base_cesantias_provision', 'base_cesantias_liquidacion'),
        'base_intereses_cesantias': ('base_intereses_cesantias_provision', 'base_intereses_cesantias_liquidacion'),
        'base_vacaciones': ('base_vacaciones_provision', 'base_vacaciones_liquidacion'),
        'base_vacaciones_dinero': ('base_vacaciones_dinero_provision', 'base_vacaciones_dinero_liquidacion'),
    }

    # ══════════════════════════════════════════════════════════════════════════
    # CAMPOS PERSONALIZADOS
    # ══════════════════════════════════════════════════════════════════════════

    struct_id = fields.Many2one(
        tracking=True,
        help='Estructura salarial a la que pertenece esta regla'
    )
    active = fields.Boolean(
        tracking=True,
        help='Indica si la regla está activa y se aplicará en los cálculos de nómina'
    )
    sequence = fields.Integer(
        tracking=True,
        help='Orden de ejecución de la regla dentro de la estructura salarial'
    )
    condition_select = fields.Selection(
        tracking=True,
        help='Tipo de condición para aplicar la regla'
    )
    amount_select = fields.Selection(
        selection_add=[('concept', 'Concept Code')],
        ondelete={'concept': 'set default'},
        tracking=True,
        help='Método de cálculo del monto: fijo, porcentaje, código Python o concepto'
    )
    amount_python_compute = fields.Text(
        tracking=True,
        help='Código Python para calcular el monto de la regla. Debe definir la variable "result"'
    )
    appears_on_payslip = fields.Boolean(
        tracking=True,
        help='Indica si esta regla debe aparecer visible en el recibo de nómina del empleado'
    )
    proyectar_nom = fields.Boolean(
        'Proyectar en nomina',
        help='Si está marcado, este concepto se proyectará en las proyecciones de nómina'
    )
    proyectar_ret = fields.Boolean(
        'Proyectar en Retencion',
        help='Si está marcado, este concepto se proyectará en las proyecciones de retención en la fuente'
    )

    # Campos lavish - Tipos de empleado usando employee_type nativo de Odoo
    employee_type_domain = fields.Char(
        string='Tipos de Empleado (Dominio)',
        tracking=True,
        help='Lista de tipos de empleado separados por coma para los cuales aplica esta regla. '
             'Valores validos: employee, student, trainee, contractor, freelance. '
             'Ejemplo: "employee,contractor" - Dejar vacio para aplicar a todos.'
    )
    dev_or_ded = fields.Selection([
        ('devengo', 'Devengo'),
        ('deduccion', 'Deducción')
    ], 'Naturaleza', tracking=True,
        help='Indica si la regla es un devengo (ingreso) o una deducción (descuento)'
    )
    afecta_totales = fields.Selection([
        ('devengo', 'Afecta Devengos'),
        ('deduccion', 'Afecta Deducciones'),
        ('ninguno', 'No Afecta Totales'),
    ], string='Afecta Totales', tracking=True,
        help='Define si este concepto participa en TOTALDEV/TOTALDED. '
             'Si no se configura, se infiere por categoría para mantener compatibilidad.'
    )
    type_concepts = fields.Selection([
        ('sueldo', 'Sueldo / Salario'),
        ('contrato', 'Fijo de contrato'),
        ('ley', 'Por ley (ausencias)'),
        ('novedad', 'Novedad variable'),
        ('prestacion', 'Prestacion social'),
        ('provision', 'Provision periodica'),
        ('consolidacion', 'Totalizador / Consolidacion'),
        ('tributaria', 'Deduccion tributaria'),
        ('seguridad_social', 'Seguridad social'),
        ('parafiscal', 'Aportes parafiscales'),
    ], 'Tipo de concepto', required=True, default='contrato', tracking=True,
        help='Clasificacion del concepto segun su naturaleza y origen'
    )

    def _rule_in_categories(self, rule, category_codes):
        """Valida si la regla pertenece a alguna de las categorías dadas (incluye padre)."""
        if not rule or not rule.category_id:
            return False
        cat = rule.category_id
        if cat.code in category_codes:
            return True
        return bool(cat.parent_id and cat.parent_id.code in category_codes)

    def _get_afecta_totales_effective(self, dev_categories=None, ded_categories=None):
        """
        Retorna la clasificación efectiva para TOTALDEV/TOTALDED.
        Si afecta_totales está configurado, se usa ese valor.
        Si no, se infiere por categoría para mantener el comportamiento actual.
        """
        self.ensure_one()
        if self.afecta_totales:
            return self.afecta_totales
        dev_categories = dev_categories or self._AFECTA_TOTALES_DEV_CATS
        ded_categories = ded_categories or self._AFECTA_TOTALES_DED_CATS
        if self._rule_in_categories(self, dev_categories):
            return 'devengo'
        if self._rule_in_categories(self, ded_categories):
            return 'deduccion'
        return 'ninguno'
    aplicar_cobro = fields.Selection([
        ('15', 'Primera quincena'),
        ('30', 'Segunda quincena'),
        ('0', 'Siempre')
    ], 'Aplicar cobro', tracking=True,
        help='Define en qué quincena del mes se aplica el cobro o pago de esta regla'
    )
    modality_value = fields.Selection([
        ('fijo', 'Valor fijo'),
        ('diario', 'Valor diario'),
        ('diario_efectivo', 'Valor diario del día efectivamente laborado')
    ], 'Modalidad de valor', tracking=True,
        help='Modalidad de cálculo del valor: fijo, diario o diario efectivo (solo días trabajados)'
    )
    deduction_applies_bonus = fields.Boolean(
        'Aplicar deducción en Prima',
        tracking=True,
        help='Si está marcado, esta deducción se aplicará también en el cálculo de la prima'
    )
    account_tax_id = fields.Many2one(
        "account.tax",
        "Impuesto de Retefuente Laboral",
        help='Impuesto de retención en la fuente laboral asociado a esta regla'
    )

    # Es incapacidad / deducciones
    is_leave = fields.Boolean(
        'Es Ausencia',
        tracking=True,
        help='Indica si esta regla está relacionada con ausencias o licencias del empleado'
    )
    is_recargo = fields.Boolean(
        'Es Recargos',
        tracking=True,
        help='Indica si esta regla corresponde a recargos (horas extras nocturnas, dominicales, etc.)'
    )
    deduct_deductions = fields.Selection([
        ('all', 'Todas las deducciones'),
        ('law', 'Solo las deducciones de ley')
    ], 'Tener en cuenta al descontar', default='all', tracking=True,
        help='Define qué deducciones se tienen en cuenta al calcular descuentos por ausencias'
    )
    rounding_method = fields.Selection([
        ('no_round', 'Sin redondeo'),
        ('round1', 'Redondear a entero'),
        ('round100', 'Redondear al 100 más cercano'),
        ('round1000', 'Redondear al 1000 más cercano'),
        ('round2d', 'Redondear a 2 decimales')
    ], string='Método de redondeo', default='no_round',
       help="Método de redondeo aplicado al resultado final de esta regla. "
            "Ejemplos con valor $1,234,567.89: "
            "Sin redondeo = $1,234,567.89 | "
            "Entero = $1,234,568 | "
            "Al 100 = $1,234,600 | "
            "Al 1000 = $1,235,000 | "
            "2 decimales = $1,234,567.89")

    liquidar_con_base = fields.Boolean(
        'Liquidar con IBC mes anterior',
        tracking=True,
        help='USA IBC DEL MES ANTERIOR PARA LIQUIDAR\n'
             '------------------------------------------------------------\n'
             'Si esta marcado:\n'
             '  + Usa el IBC del mes anterior como base de calculo\n'
             '  + Aplica para incapacidades (Art. 40 D.1406/99)\n'
             '  + El valor PAGADO puede ser diferente al IBC cotizado\n'
             '------------------------------------------------------------\n'
             'EJEMPLO - Incapacidad:\n'
             '  . IBC mes anterior: $3.000.000\n'
             '  . Porcentaje EPS: 66.67%\n'
             '  . Valor pagado: $2.000.100\n'
             '  . IBC para SS: $3.000.000 (no $2.000.100)'
    )
    aplicar_limite_minimo_ibc = fields.Boolean(
        'Aplicar limite minimo IBC',
        default=False,
        tracking=True,
        help='GARANTIZAR IBC MINIMO LEGAL (SMMLV/30)\n'
             '------------------------------------------------------------\n'
             'Si esta marcado:\n'
             '  + El IBC diario nunca sera menor a SMMLV/30\n'
             '  + Protege al empleado en ausencias de bajo valor\n'
             '------------------------------------------------------------\n'
             'EJEMPLO - SMMLV $1.300.000:\n'
             '  . IBC minimo diario: $1.300.000 / 30 = $43.333\n'
             '  . Si IBC calculado < $43.333, se ajusta al minimo\n'
             '------------------------------------------------------------\n'
             'IMPORTANTE: Este campo es independiente de liquidar_con_base.\n'
             'Puede usarse solo o en combinacion.'
    )
    base_prima = fields.Boolean(
        'Para prima',
        tracking=True,
        help='Incluye este concepto en la base de prima de servicios (Art. 306-307 CST). '
             'Ejemplo: Salario $3M + Comisiones $500K. Con marca: Base prima = $3.5M, Prima semestral = $3.5M/2 = $1.75M'
    )
    base_prima_provision = fields.Boolean(
        'Base Prima Provision',
        tracking=True,
        help='Incluye este concepto en la base de provisión de prima.'
    )
    base_prima_liquidacion = fields.Boolean(
        'Base Prima Liquidacion',
        tracking=True,
        help='Incluye este concepto en la base de liquidación/pago de prima.'
    )
    base_cesantias = fields.Boolean(
        'Para cesantías',
        tracking=True,
        help='Incluye este concepto en la base de cesantías (Art. 249 CST). '
        'Ejemplo: Salario $3M + Horas extras promedio $200K. Con marca: Base cesantías = $3.2M, '
        'Cesantías anuales = $3.2M x dias/360'
    )
    base_cesantias_provision = fields.Boolean(
        'Base Cesantias Provision',
        tracking=True,
        help='Incluye este concepto en la base de provisión de cesantías.'
    )
    base_cesantias_liquidacion = fields.Boolean(
        'Base Cesantias Liquidacion',
        tracking=True,
        help='Incluye este concepto en la base de liquidación/pago de cesantías.'
    )
    base_vacaciones = fields.Boolean(
        'Para vacaciones tomadas',
        tracking=True,
        help='Incluye este concepto en la base de vacaciones disfrutadas (Art. 186 CST). '
        'Se usa para calcular el valor diario cuando el empleado toma días de vacaciones. '
        'Ejemplo: Salario $3M. Base vacaciones = $3M, Valor día = $3M/30 = $100K'
    )
    base_vacaciones_provision = fields.Boolean(
        'Base Vacaciones Provision',
        tracking=True,
        help='Incluye este concepto en la base de provisión de vacaciones.'
    )
    base_vacaciones_liquidacion = fields.Boolean(
        'Base Vacaciones Liquidacion',
        tracking=True,
        help='Incluye este concepto en la base de liquidación/pago de vacaciones.'
    )
    base_vacaciones_dinero = fields.Boolean(
        'Para vacaciones dinero',
        tracking=True,
        help='Incluye este concepto en la base de vacaciones compensadas en dinero (Art. 189 CST). '
        'Se usa al liquidar vacaciones no disfrutadas. '
        'Ejemplo: Salario $3M + Aux. extralegal $300K. Con marca: Base = $3.3M, 15 días = $3.3M x 15/30'
    )
    base_vacaciones_dinero_provision = fields.Boolean(
        'Base Vacaciones Dinero Provision',
        tracking=True,
        help='Incluye este concepto en la base de provisión de vacaciones compensadas en dinero.'
    )
    base_vacaciones_dinero_liquidacion = fields.Boolean(
        'Base Vacaciones Dinero Liquidacion',
        tracking=True,
        help='Incluye este concepto en la base de liquidación/pago de vacaciones en dinero.'
    )
    base_intereses_cesantias = fields.Boolean(
        'Para intereses de cesantías',
        tracking=True,
        help='Incluye este concepto en la base de intereses sobre cesantías (Ley 52/1975). '
        'Tasa: 12% anual sobre cesantías acumuladas. '
        'Ejemplo: Cesantías $3.6M, Intereses = $3.6M x 12% x días/360'
    )
    base_intereses_cesantias_provision = fields.Boolean(
        'Base Intereses Cesantias Provision',
        tracking=True,
        help='Incluye este concepto en la base de provisión de intereses de cesantías.'
    )
    base_intereses_cesantias_liquidacion = fields.Boolean(
        'Base Intereses Cesantias Liquidacion',
        tracking=True,
        help='Incluye este concepto en la base de liquidación/pago de intereses de cesantías.'
    )
    base_auxtransporte_tope = fields.Boolean(
        'Incluir en Base Tope Auxilio',
        tracking=True,
        help='''Incluye este concepto en la base para validar el tope de auxilio de transporte.

CUANDO SE USA:
- Contrato configurado con only_wage = "Salario + Devengos Marcados" (wage_dev_exc)
- Solo las reglas con este campo marcado se sumaran al salario

EJEMPLO:
- Salario contrato: $1.800.000
- Bonificacion Productividad (marcada): $400.000
- Comision (NO marcada): $300.000
- Base para tope = $1.800.000 + $400.000 = $2.200.000
- La comision NO se incluye porque no esta marcada

LOGICA DE INCLUSION:
1. Si only_wage = "wage": Solo salario (ignora este campo)
2. Si only_wage = "wage_dev": Categoria DEV_SALARIAL + este campo
3. Si only_wage = "wage_dev_exc": SOLO reglas con este campo = True

NOTA: excluir_auxtransporte_tope tiene prioridad sobre este campo.'''
    )
    excluir_auxtransporte_tope = fields.Boolean(
        'Excluir de Base Tope Auxilio',
        default=False,
        tracking=True,
        help='''EXCLUYE este concepto del calculo de base para validar tope de auxilio de transporte.

CUANDO SE USA:
- Contrato configurado con only_wage = "Salario + Devengos" (wage_dev)
- La regla es DEV_SALARIAL pero NO debe sumarse al tope

EJEMPLO:
- Regla "Bonificacion No Salarial" con categoria DEV_SALARIAL
- Con wage_dev se incluiria automaticamente
- Marcar este campo para EXCLUIRLA del tope

PRIORIDAD:
Este campo tiene PRIORIDAD sobre base_auxtransporte_tope.
Si ambos estan marcados, se EXCLUYE.'''
    )
    es_auxilio_transporte = fields.Boolean(
        'Es Auxilio de Transporte',
        default=False,
        tracking=True,
        help='Marca esta regla como concepto de auxilio de transporte. '
             'Las reglas con esta marca seran tratadas de forma especial en prestaciones: '
             'cuando modality_aux=variable, se promediaran como conceptos variables (igual que comisiones). '
             'Usar para AUX000, AUX00C u otros conceptos que representen auxilio de transporte.'
    )
    base_compensation = fields.Boolean(
        'Para liquidación de indemnización',
        tracking=True,
        help='Incluye este concepto en la base de indemnización por despido sin justa causa (Art. 64 CST). '
             'Ejemplo: Salario $4M + Comisiones promedio $1M. Con marca: Base indemnización = $5M. '
             'Contrato indefinido >1 año: 30 días + 20 días por año adicional.'
    )

    # Base de Seguridad Social
    base_seguridad_social = fields.Boolean(
        'Para seguridad social',
        tracking=True,
        help='Incluye este concepto en el IBC (Ingreso Base de Cotización) para salud y pensión. '
             'Aportes: Salud 12.5% (8.5% empresa + 4% empleado), Pensión 16% (12% empresa + 4% empleado). '
             'Ejemplo: Salario $4M + Bonificación $500K. Con marca: IBC = $4.5M, Aporte salud = $562.5K'
    )
    base_arl = fields.Boolean(
        'Para ARL',
        tracking=True,
        help='Incluye este concepto en la base de ARL (Riesgos Laborales). '
             'Tarifa según nivel de riesgo: I=0.522%, II=1.044%, III=2.436%, IV=4.350%, V=6.960%. '
             'Ejemplo: IBC $4M, Riesgo III: Aporte ARL = $4M x 2.436% = $97.440 (100% empresa)'
    )
    has_priority_flow = fields.Boolean(
        string='Activar Configuraciones Contables',
        default=False,
        help='Si está activo, permite configurar múltiples prioridades contables para esta regla'
    )
    accounting_priority_ids = fields.One2many(
        'hr.salary.rule.accounting.priority',
        'salary_rule_id',
        string='Prioridades Contables',
        help='Configuraciones de prioridad contable para esta regla'
    )
    base_parafiscales = fields.Boolean(
        'Para parafiscales',
        tracking=True,
        help='Incluye este concepto en la base de aportes parafiscales. '
             'SENA 2%, ICBF 3%, Caja Compensación 4% (total 9% sobre nómina). '
             'Exoneración Ley 1607: Empresas con empleados < 10 SMMLV no pagan SENA/ICBF. '
             'Ejemplo: IBC $4M. Sin exoneración: Parafiscales = $4M x 9% = $360K'
    )
    base_horas_extras = fields.Boolean(
        'Para base horas extras',
        default=False,
        tracking=True,
        help='Incluye este concepto en la base para el cálculo del valor hora extra. '
             'Según Ley 2101/2021 y Ley 2466/2025, el valor hora se calcula como: '
             'Salario Base / Horas Mes (según reducción gradual de jornada). '
             'Ejemplo: Salario $1.8M, Horas mes 230. Valor hora = $7,826.09'
    )
    excluir_seguridad_social = fields.Boolean(
        'Excluir de seguridad social',
        default=False,
        tracking=True,
        help='Si está marcado, este concepto se EXCLUIRÁ completamente del cálculo de seguridad social (salud, pensión, ARL, parafiscales). '
             'Ejemplo: Concepto de $500K. Sin marcar: se incluye en IBC y se calculan aportes. Con marcar: excluido, no genera aportes de SS.'
    )
    excluir_ret = fields.Boolean(
        'Excluir de Calculo retefuente',
        tracking=True,
        help='Excluye este concepto del cálculo de retención en la fuente (Art. 383 ET). '
             'Útil para pagos no constitutivos de ingreso laboral. '
             'Ejemplo: Viáticos permanentes, reembolso de gastos. Sin marca: se suma a base gravable.'
    )
    excluir_40_porciento_ss = fields.Boolean(
        'Excluir del límite 40% en IBC',
        default=False,
        tracking=True,
        help='Excluye este concepto del cálculo del límite 40% no salarial (Art. 30 Ley 1393/2010). '
             'Los pagos no salariales que excedan el 40% del total devengado deben incluirse en IBC. '
             'Ejemplo: Salario $5M + Bonificación no salarial $3M (60%). Exceso 20% ($1M) se suma al IBC.'
    )
    aplica_factor_integral = fields.Boolean(
        'Aplica Factor 70% (Sal. Integral)',
        default=False,
        tracking=True,
        help='En contratos de SALARIO INTEGRAL, aplica el factor del 70% a este concepto para IBC (Art. 132 CST). '
             'MARCAR para: Salario básico integral. '
             'NO MARCAR para: Comisiones, bonificaciones, horas extras u otros devengos adicionales. '
             'Ejemplo: Sal. Integral $10M (marca) + Comisiones $2M (sin marca). '
             'IBC = ($10M × 70%) + ($2M × 100%) = $7M + $2M = $9M'
    )
    is_projectable_rtf = fields.Boolean(
        string='Proyectable para Retención / Fondos',
        default=False,
        help='Indica si este concepto se proyecta anualmente para calcular retención en la fuente. '
             'Procedimiento 2 (Art. 386 ET): Se proyectan ingresos anuales para determinar tarifa. '
             'Marcar para conceptos fijos mensuales como salario, aux. transporte, bonificaciones fijas.'
    )

    descontar_suspensiones = fields.Boolean(
        'Descontar Licencia No remuneradas',
        tracking=True,
        help='Descuenta proporcionalmente los días de licencia no remunerada o suspensión. '
             'Ejemplo: Salario $3M, 5 días de licencia no remunerada. '
             'Con marca: Salario = $3M x 25/30 = $2.5M. Sin marca: Se paga salario completo.'
    )
    salary_rule_accounting = fields.One2many(
        'hr.salary.rule.accounting',
        'salary_rule',
        string="Contabilización",
        tracking=True,
        help='Configuración contable para esta regla salarial (cuentas de débito y crédito)'
    )

    # Reportes
    display_days_worked = fields.Boolean(
        string='Mostrar la cantidad de días trabajados en los formatos de impresión',
        tracking=True,
        help='Si está marcado, se mostrará la cantidad de días trabajados en los formatos de impresión de nómina'
    )
    short_name = fields.Char(
        string='Nombre corto/reportes',
        help='Nombre abreviado de la regla para usar en reportes y formatos de impresión'
    )
    process = fields.Selection([
        ('nomina', 'Nónima'),
        ('vacaciones', 'Vacaciones'),
        ('prima', 'Prima'),
        ('cesantias', 'Cesantías'),
        ('intereses_cesantias', 'Intereses de cesantías'),
        ('contrato', 'Liq. de Contrato'),
        ('otro', 'Otro')
    ], string='Proceso',
        help='Tipo de proceso de nómina en el que aplica esta regla'
    )
    novedad_ded = fields.Selection([
        ('cont', 'Contrato'),
        ('Noved', 'Novedad'),
        ('0', 'No'),
    ], 'Opcion de Novedad', tracking=True,
        help='Indica si este concepto es parte del contrato, una novedad variable o no aplica'
    )
    not_include_flat_payment_file = fields.Boolean(
        string='No incluir en archivo plano de pagos',
        help='Si está marcado, este concepto no se incluirá en el archivo plano de pagos bancarios'
    )


    # ══════════════════════════════════════════════════════════════════════════
    # MÉTODOS DE VALIDACION POR TIPO DE EMPLEADO
    # ══════════════════════════════════════════════════════════════════════════

    def applies_to_employee_type(self, employee_type):
        """
        Verifica si esta regla salarial aplica para el tipo de empleado dado.

        Args:
            employee_type: Valor del campo employee_type del empleado
                          (ej: 'employee', 'student', 'trainee', 'contractor', 'freelance')

        Returns:
            bool: True si la regla aplica, False en caso contrario
        """
        self.ensure_one()

        # Si no hay dominio definido, la regla aplica a todos
        if not self.employee_type_domain:
            return True

        # Parsear el dominio (lista separada por comas)
        allowed_types = [t.strip().lower() for t in self.employee_type_domain.split(',') if t.strip()]

        # Si la lista esta vacia, aplica a todos
        if not allowed_types:
            return True

        # Verificar si el tipo de empleado esta en la lista
        return (employee_type or '').lower() in allowed_types

    @classmethod
    def _sync_split_base_fields_in_vals(cls, vals):
        """Sincroniza checks legacy -> checks separados cuando no vienen explícitos."""
        vals = dict(vals)
        for legacy_field, split_fields in cls._SPLIT_PRESTACION_FIELDS.items():
            if legacy_field not in vals:
                continue
            for split_field in split_fields:
                if split_field not in vals:
                    vals[split_field] = vals[legacy_field]
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._sync_split_base_fields_in_vals(vals) for vals in vals_list]
        return super().create(vals_list)

    def write(self, vals):
        vals = self._sync_split_base_fields_in_vals(vals)
        return super().write(vals)

    def get_applicable_rules_for_employee(self, employee):
        """
        Filtra las reglas que aplican para un empleado especifico segun su employee_type.

        Args:
            employee: Registro hr.employee

        Returns:
            recordset: Reglas salariales que aplican al empleado
        """
        applicable_rules = self.env['hr.salary.rule']
        employee_type = employee.employee_type or 'employee'

        for rule in self:
            if rule.applies_to_employee_type(employee_type):
                applicable_rules |= rule

        return applicable_rules

    # ══════════════════════════════════════════════════════════════════════════
    # MÉTODOS COMUNES (usados por múltiples mixins)
    # ══════════════════════════════════════════════════════════════════════════

    def _get_totalizar_reglas(
        self,
        liquidacion_data,
        codigos_regla=None,
        filtros=None,
        incluir_current=True,  # Obsoleto - se mantiene por compatibilidad
        incluir_before=False,  # Obsoleto - se mantiene por compatibilidad
        incluir_multi=True,  # Obsoleto - se mantiene por compatibilidad
        devolver_cantidad=False,
        ):
        """
        Totaliza reglas de nómina en Odoo 19.

        Args:
            liquidacion_data: Diccionario con datos de liquidación
            codigos_regla: Códigos de reglas a totalizar (None = todas)
            filtros: Diccionario con funciones de filtrado
            devolver_cantidad: Si se devuelve la cantidad en lugar del valor

        Returns:
            float o int: Total acumulado
        """
        if codigos_regla is None:
            codigos = list(liquidacion_data.get('rules', {}).keys())
        else:
            codigos = codigos_regla if isinstance(codigos_regla, list) else [codigos_regla]

        filtros = filtros or {}
        def pasa_filter(obj):
            cond = filtros.get('object')
            return cond(obj) if cond else True

        entradas = []

        # ODOO 18 NATIVO: Usar estructura 'rules'
        for code in codigos:
            rule_data = liquidacion_data.get('rules', {}).get(code)
            if rule_data:
                rule_obj = rule_data.rule
                if rule_obj:
                    entradas.append({
                        'object': rule_obj,
                        'total': rule_data.total,
                        'quantity': rule_data.quantity,
                    })

        total_valor = 0.0
        total_entradas = 0
        for item in entradas:
            obj = item.get('object')
            if not obj or not pasa_filter(obj):
                continue

            if devolver_cantidad:
                total_entradas += item.get('quantity', 0)
            else:
                total_valor += item.get('total', 0.0)

        return total_entradas if devolver_cantidad else total_valor


    def _get_totalizar_categorias(
        self,
        localdict,
        categorias=None,
        categorias_excluir=None,
        filtros=None,
        incluir_current=True,  # Obsoleto - se mantiene por compatibilidad
        incluir_before=False,  # Obsoleto - se mantiene por compatibilidad
        incluir_multi=True,  # Obsoleto - se mantiene por compatibilidad
        incluir_subcategorias=True,
        ):
        """
        Totaliza categorías de nómina en Odoo 19.

        Args:
            localdict: Diccionario local con datos de nómina
            categorias: Categorías a incluir (None = todas)
            categorias_excluir: Categorías a excluir
            filtros: Diccionario con funciones de filtrado
            incluir_subcategorias: Si se incluyen subcategorías

        Returns:
            Tuple[float, float]: (total_valor, total_entradas)
        """
        def _to_list(x):
            if x is None:
                return None
            return x if isinstance(x, list) else [x]

        categorias = _to_list(categorias)
        categorias_excluir = _to_list(categorias_excluir)
        filtros = filtros or {}

        def _pasa_filtros(obj):
            for clave, cond in filtros.items():
                if clave == 'object':
                    if not cond(obj):
                        return False
                else:
                    val = getattr(obj, clave, None)
                    if callable(cond):
                        if not cond(val):
                            return False
                    else:
                        if bool(val) != bool(cond):
                            return False
            return True

        fuente = []

        # ODOO 18 NATIVO: Usar RulesCollection
        rules = localdict.get('rules')
        if rules:
            for code, rule_data in rules.items():
                if rule_data.rule:
                    # Excluir si tiene excluir_ret marcado (para cálculos de retención)
                    if rule_data.rule.excluir_ret:
                        continue
                    fuente.append({
                        'code': code,
                        'object': rule_data.rule,
                        'total': rule_data.total,
                        'quantity': rule_data.quantity,
                    })

        reglas_por_cat = {} # construir mapeos categoría ← reglas y padre ← hijo
        padres = {}
        for item in fuente:
            obj = item['object']
            if not obj.category_id:
                continue
            cat = obj.category_id.code
            reglas_por_cat.setdefault(cat, set()).add(item['code'])
            if obj.category_id.parent_id:
                padres.setdefault(cat, obj.category_id.parent_id.code)

        hijos = {}
        for cat, p in padres.items():
            hijos.setdefault(p, set()).add(cat)

        if categorias is None:
            cats = set(reglas_por_cat)
        else:
            cats = set(categorias)
            if incluir_subcategorias:
                cola = list(cats)
                while cola:
                    c = cola.pop()
                    for h in hijos.get(c, ()):
                        if h not in cats:
                            cats.add(h)
                            cola.append(h)

        if categorias_excluir:
            ex = set(categorias_excluir)
            if incluir_subcategorias:
                cola = list(ex)
                while cola:
                    c = cola.pop()
                    for h in hijos.get(c, ()):
                        if h not in ex:
                            ex.add(h)
                            cola.append(h)
            cats -= ex
        total_valor = 0.0
        total_entradas = 0
        for item in fuente:
            obj = item['object']
            cat = obj.category_id.code if obj.category_id else None
            if cat not in cats or not _pasa_filtros(obj):
                continue

            total_valor += item.get('total', 0.0)
            total_entradas += item.get('quantity', 0)

        return total_valor, total_entradas
    


    # ══════════════════════════════════════════════════════════════════════════
    # MÉTODOS COPIADOS DE HR_RULE.PY - NO PRESENTES EN VERSIÓN ADAPTADA
    # ══════════════════════════════════════════════════════════════════════════
    # NOTA: Estos métodos fueron copiados desde hr_rule.py porque NO estaban
    # implementados en la versión adaptada. Se necesitan para completar la
    # funcionalidad de cálculo de prestaciones, retenciones y provisiones.
    # ══════════════════════════════════════════════════════════════════════════

    def _get_current_period_data(self, localdict, filters=None):
        """
        Obtiene datos del período ACTUAL (mes en proceso) desde localdict['rules'].
        Compatible con Odoo 19 - usa estructura nativa.

        Args:
            localdict: Diccionario de contexto de nómina
            filters: Dict con filtros a aplicar
                {
                    'rules': ['BASIC', 'HE001'],           # Códigos de reglas específicas
                    'categories': ['BASIC', 'DEV_SALARIAL'],  # Códigos de categorías
                    'exclude_rules': ['BASIC'],            # Excluir reglas
                    'exclude_categories': ['DED'],         # Excluir categorías
                    'base_prima': True,                    # Solo reglas con base_prima=True
                    'base_cesantias': True,                # Solo reglas con base_cesantias=True
                    'base_ss': True,                       # Solo reglas con base_seguridad_social=True
                    'base_vacaciones': True,               # Solo reglas con base_vacaciones=True
                    'min_amount': 1000,                    # Monto mínimo
                    'conditions': lambda rule: rule.code.startswith('HE')  # Condición custom
                }

        Returns:
            dict: {
                'total': float,
                'quantity': float,
                'by_rule': {code: {'total': X, 'quantity': Y, 'rule': obj}},
                'by_category': {code: {'total': X, 'quantity': Y}}
            }
        """
        filters = filters or {}

        # Inicializar resultado
        result = {
            'total': 0.0,
            'quantity': 0.0,
            'by_rule': {},
            'by_category': {}
        }

        # Obtener rules desde localdict (Odoo 19 nativo)
        rules = localdict.get('rules', {})

        if not rules:
            return result

        # Procesar cada regla
        for code, rule_data in rules.items():
            rule_obj = rule_data.rule
            total = rule_data.total
            quantity = rule_data.quantity

            if not rule_obj:
                continue

            # Aplicar filtros
            if not self._passes_current_period_filters(rule_obj, filters):
                continue

            # Agregar a totales
            result['total'] += total
            result['quantity'] += quantity

            # Agregar por regla
            result['by_rule'][code] = {
                'total': total,
                'quantity': quantity,
                'rule': rule_obj
            }

            # Agregar por categoría
            if rule_obj.category_id:
                cat_code = rule_obj.category_id.code
                if cat_code not in result['by_category']:
                    result['by_category'][cat_code] = {'total': 0.0, 'quantity': 0.0}

                result['by_category'][cat_code]['total'] += total
                result['by_category'][cat_code]['quantity'] += quantity

        return result


    def _passes_current_period_filters(self, rule_obj, filters):
        """
        Verifica si una regla pasa todos los filtros especificados.

        Args:
            rule_obj: Objeto hr.salary.rule
            filters: Dict con filtros

        Returns:
            bool: True si pasa todos los filtros
        """
        if not filters:
            return True

        # Filtro de reglas específicas
        if 'rules' in filters:
            rules_filter = filters['rules'] if isinstance(filters['rules'], list) else [filters['rules']]
            if rule_obj.code not in rules_filter:
                return False

        # Filtro de reglas excluidas
        if 'exclude_rules' in filters:
            excluded = filters['exclude_rules'] if isinstance(filters['exclude_rules'], list) else [filters['exclude_rules']]
            if rule_obj.code in excluded:
                return False

        # Filtro de categorías
        if 'categories' in filters and rule_obj.category_id:
            categories = filters['categories'] if isinstance(filters['categories'], list) else [filters['categories']]
            cat_code = rule_obj.category_id.code
            parent_code = rule_obj.category_id.parent_id.code if rule_obj.category_id.parent_id else None

            if not (cat_code in categories or parent_code in categories):
                return False

        # Filtro de categorías excluidas
        if 'exclude_categories' in filters and rule_obj.category_id:
            excluded = filters['exclude_categories'] if isinstance(filters['exclude_categories'], list) else [filters['exclude_categories']]
            cat_code = rule_obj.category_id.code
            parent_code = rule_obj.category_id.parent_id.code if rule_obj.category_id.parent_id else None

            if cat_code in excluded or parent_code in excluded:
                return False

        # Filtros de base
        if 'base_prima' in filters and filters['base_prima']:
            if not rule_obj.base_prima:
                return False

        if 'base_cesantias' in filters and filters['base_cesantias']:
            if not rule_obj.base_cesantias:
                return False

        if 'base_ss' in filters and filters['base_ss']:
            if not rule_obj.base_seguridad_social:
                return False

        if 'base_vacaciones' in filters and filters['base_vacaciones']:
            if not rule_obj.base_vacaciones:
                return False

        # Filtro de condiciones custom
        if 'conditions' in filters and callable(filters['conditions']):
            if not filters['conditions'](rule_obj):
                return False

        return True

    # ══════════════════════════════════════════════════════════════════════════
    # MÉTODOS DE PRESTACIONES SOCIALES
    # ══════════════════════════════════════════════════════════════════════════



    # ══════════════════════════════════════════════════════════════════════════
    # MÉTODOS DE TOTALES
    # ══════════════════════════════════════════════════════════════════════════


    def _calculate_total_from_categories(self, localdict, category_codes):
        """
        Calcula totales desde localdict['categories'] directamente.
        Más eficiente - usa totales ya acumulados en vez de iterar reglas.

        Args:
            localdict: Diccionario de contexto
            category_codes: Lista de códigos de categorías a sumar

        Returns:
            tuple: (total, 1, 100, False, category_totals, details)
        """
        categories = localdict.get('categories', {})

        total = 0
        category_totals = {}
        details = {}

        # Iterar por los códigos de categoría solicitados
        for cat_code in category_codes:
            cat_data = categories.get(cat_code)

            # Verificar si la categoría existe y tiene datos
            if cat_data:
                cat_total = cat_data.total
                total += cat_total
                category_totals[cat_code] = cat_total

                # Agregar detalles de reglas que contribuyeron
                rules = localdict.get('rules')
                for rule_code in cat_data.rule_codes:
                    if rules and rule_code in rules:
                        rule_data = rules.get(rule_code)
                        details[rule_code] = rule_data.total if rule_data else 0

        return total, 1, 100, False, category_totals, details


    def _calculate_total_from_rules(self, localdict, categories, exclude_not_in_net=True):
        """
        MÉTODO ANTIGUO - Mantener para compatibilidad.
        Usa _calculate_total_from_categories() que es más eficiente.

        Calcula totales desde localdict['rules'] por categorías.
        Compatible con Odoo 19 - usa estructura nativa.

        Args:
            localdict: Diccionario de contexto
            categories: Lista de códigos de categorías a sumar
            exclude_not_in_net: Si True, excluye reglas con not_computed_in_net=True

        Returns:
            tuple: (total, 1, 100, False, category_totals, details)
        """
        # Usar el método más eficiente que lee directamente de categories
        return self._calculate_total_from_categories(localdict, categories)

    # Implementación de los métodos principales




    def _rt_met_01(self, localdict):
        """
        Retención en la fuente - Método ordinario (procedimiento 1).
        Usa el método genérico _calculate_retention_generic.
        """
        return self._calculate_retention_generic(localdict, tipo='nomina')

    def _embargo001(self, localdict):
        """
        Calcula el embargo aplicable según la ley (CST Art. 154 y siguientes).
        Prioriza embargos por alimentos y respeta límites legales.

        ADAPTADO - Sin HTML, usa CategoryCollection y RulesCollection
        """
        slip = localdict['slip']
        employee = localdict['employee']
        contract = localdict['contract']
        categories = localdict.get('categories') 
        rules = localdict.get('rules') 
        annual_parameters = localdict.get('annual_parameters')

        # Obtener regla y concepto
        rule = self.get_salary_rule('EMBARGO001', employee.employee_type)
        # Buscar concepto de embargo aprobado en el contrato
        concept = None
        if rule and hasattr(contract, 'concepts_ids'):
            concepts = contract.concepts_ids.filtered(
                lambda c: c.input_id.id == rule.id and
                          c.state == 'done' and
                          c.type_deduction == 'E'
            )
            concept = concepts[0] if concepts else None
        elif rule:
            # Fallback: buscar en el modelo directamente
            ConceptModel = self.env['hr.contract.concepts']
            concepts = ConceptModel.search([
                ('contract_id', '=', contract.id),
                ('input_id', '=', rule.id),
                ('state', '=', 'done'),
                ('type_deduction', '=', 'E')
            ], limit=1)
            concept = concepts[0] if concepts else None

        data_result = {
            'valor_embargo': 0.0,
            'tipo_embargo': '',
            'limite_legal': 0.0,
            'base_calculo': 0.0,
            'otros_embargos': 0.0,
            'limite_disponible': 0.0,
            'es_alimentario': False,
            'context_name': '',
            'status': 'no_concept'
        }

        if not concept:
            return 0.0, 1, 0.0, 'EMBARGO - Sin concepto', False, data_result

        # Nombre contextual
        context_name = f"EMBARGO - {concept.name}" if hasattr(concept, 'name') else 'EMBARGO'
        data_result['context_name'] = context_name
        name = context_name

        if hasattr(concept, 'embargo_judged') and concept.embargo_judged:
            name += f" - Juzgado: {concept.embargo_judged}"
        if hasattr(concept, 'embargo_process') and concept.embargo_process:
            name += f" - Proceso: {concept.embargo_process}"

        tipo_emb = getattr(concept, 'type_emb', 'OTRO') or 'OTRO'
        data_result['tipo_embargo'] = tipo_emb
        data_result['es_alimentario'] = (tipo_emb == 'ECA')

        # Validar aplicación según quincena
        day = slip.date_from.day
        aplicar = getattr(concept, 'aplicar', '0')
        if (day < 15 and aplicar == '30') or (day >= 15 and aplicar == '15'):
            data_result['status'] = 'no_aplica_quincena'
            return 0.0, 0, 0.0, name, False, data_result

        # Obtener categorías y reglas para descontar
        cat_codes = []
        rule_codes = []

        if hasattr(concept, 'discount_categoria'):
            cat_codes = [c.code for c in concept.discount_categoria]
        if hasattr(concept, 'discount_rule'):
            rule_codes = [r.code for r in concept.discount_rule]

        if not cat_codes and not rule_codes:
            cat_codes = ['BASIC']

        # Calcular base
        base = 0.0
        if cat_codes and categories:
            # get_total() espera lista de códigos como kwarg 'category_codes'
            base += categories.get_total(category_codes=cat_codes)

        if rule_codes and rules:
            for rule_code in rule_codes:
                rule_data = rules.get(rule_code)
                if rule_data:
                    base += rule_data.total

        data_result['base_calculo'] = base

        # SMMLV
        smmlv = annual_parameters.smmlv_monthly if annual_parameters else 0.0

        # Obtener otros embargos activos usando RulesCollection
        otros_embargos = []
        otros_embargos_total = 0.0
        otros_embargos_alimentos = 0.0

        if rules:
            # Buscar todas las reglas de embargo activas (EMBARGO002, EMBARGO003, etc.)
            for rule_code in rules.get_codes():
                if rule_code.startswith('EMBARGO') and rule_code != 'EMBARGO001':
                    rule_data = rules.get(rule_code)
                    if rule_data:
                        total = rule_data.total
                        if total > 0:
                            # Determinar tipo de embargo de data extra si existe
                            extra_data = rule_data.extra_data
                            tipo = extra_data.get('tipo_embargo', 'OTRO')

                            embargo_info = {
                                'name': rule_code,
                                'valor': total,
                                'type': tipo,
                                'priority': 1 if tipo == 'ECA' else 2
                            }
                            otros_embargos.append(embargo_info)
                            otros_embargos_total += total
                            if tipo == 'ECA':
                                otros_embargos_alimentos += total

        data_result['otros_embargos'] = otros_embargos_total

        # Calcular límites según tipo de embargo
        if data_result['es_alimentario']:
            # Embargo por alimentos: hasta 50% del salario
            limite_maximo = base * 0.5
            limite_disponible = limite_maximo - otros_embargos_alimentos
        else:
            # Embargo general: 20% del excedente sobre SMMLV
            excedente = max(0.0, base - smmlv)
            limite_maximo = excedente * 0.2
            limite_disponible = limite_maximo - (otros_embargos_total - otros_embargos_alimentos)

        data_result['limite_legal'] = limite_maximo
        data_result['limite_disponible'] = limite_disponible

        if limite_disponible <= 0:
            data_result['status'] = 'sin_limite_disponible'
            return 0.0, 0, 0.0, name, False, data_result

        # Calcular embargo según tipo de configuración
        amount_select = getattr(concept, 'amount_select', 'fix')
        amount = getattr(concept, 'amount', 0.0)
        pct = 0.0

        if amount_select == 'percentage':
            pct = amount
            if data_result['es_alimentario']:
                embargoable_raw = base * (pct / 100.0)
            else:
                excedente = max(0.0, base - smmlv)
                embargoable_raw = excedente * (pct / 100.0)
        elif amount_select == 'fix':
            pct = 100.0
            embargoable_raw = amount
        else:  # 'min' o cualquier otro
            pct = amount / 100.0 if amount else 0.0
            embargoable_raw = base * (pct / 100.0)

        # Ajustar al límite disponible
        embargoable = min(embargoable_raw, limite_disponible)
        data_result['valor_embargo'] = embargoable
        data_result['status'] = 'aplicado'
        data_result['otros_embargos_list'] = otros_embargos

        return -embargoable, 1, pct, name, False, data_result

    def _embargo002(self, localdict):
        """Embargo 2 - Reutiliza logica de _embargo001 con diferente rule_code"""
        return self._calculate_embargo_generic(localdict, 'EMBARGO002')

    def _embargo003(self, localdict):
        """Embargo 3 - Reutiliza logica de _embargo001 con diferente rule_code"""
        return self._calculate_embargo_generic(localdict, 'EMBARGO003')

    def _embargo004(self, localdict):
        """Embargo 4 - Reutiliza logica de _embargo001 con diferente rule_code"""
        return self._calculate_embargo_generic(localdict, 'EMBARGO004')

    def _embargo005(self, localdict):
        """Embargo 5 - Reutiliza logica de _embargo001 con diferente rule_code"""
        return self._calculate_embargo_generic(localdict, 'EMBARGO005')

    def _embargo009(self, localdict):
        """
        Embargo salarial fijo basado en concepto de contrato (EMBARGO009).

        Usa la lógica de cálculo del concepto (amount_select, modality_value, etc.)
        y respeta vigencia/quincena a través de get_computed_amount_for_payslip().
        """
        slip = localdict['slip']
        employee = localdict['employee']
        contract = localdict['contract']

        rule = self.get_salary_rule('EMBARGO009', employee.employee_type)

        concept = None
        if rule and hasattr(contract, 'concepts_ids'):
            concepts = contract.concepts_ids.filtered(
                lambda c: c.input_id.id == rule.id and
                          c.state == 'done' and
                          c.active and
                          c.type_deduction == 'E'
            )
            concept = concepts[0] if concepts else None
        elif rule:
            ConceptModel = self.env['hr.contract.concepts']
            concepts = ConceptModel.search([
                ('contract_id', '=', contract.id),
                ('input_id', '=', rule.id),
                ('state', '=', 'done'),
                ('active', '=', True),
                ('type_deduction', '=', 'E')
            ], limit=1)
            concept = concepts[0] if concepts else None

        data_result = {
            'valor_embargo': 0.0,
            'tipo_embargo': '',
            'context_name': '',
            'status': 'no_concept'
        }

        if not concept:
            return 0.0, 1, 0.0, 'EMBARGO - Sin concepto', False, data_result

        context_name = f"EMBARGO - {concept.name}" if hasattr(concept, 'name') else 'EMBARGO'
        data_result['context_name'] = context_name
        name = context_name

        if hasattr(concept, 'embargo_judged') and concept.embargo_judged:
            name += f" - Juzgado: {concept.embargo_judged}"
        if hasattr(concept, 'embargo_process') and concept.embargo_process:
            name += f" - Proceso: {concept.embargo_process}"

        tipo_emb = getattr(concept, 'type_emb', 'OTRO') or 'OTRO'
        data_result['tipo_embargo'] = tipo_emb

        concept_result = concept.get_computed_amount_for_payslip(
            payslip=slip,
            date_from=slip.date_from,
            date_to=slip.date_to,
            localdict=localdict
        )

        if not concept_result or not concept_result.get('create_line', False):
            data_result['status'] = 'no_aplica'
            return 0.0, 0, 0.0, name, False, data_result

        line_vals = concept_result.get('values', {}) or {}
        amount = line_vals.get('amount', 0.0)
        qty = line_vals.get('quantity', 1.0)
        rate = line_vals.get('rate', 100.0)
        name = line_vals.get('name', name)

        data_result['valor_embargo'] = abs(amount)
        data_result['status'] = 'ok'

        return amount, qty, rate, name, False, data_result

    def _calculate_embargo_generic(self, localdict, rule_code):
        """
        Metodo generico para calcular embargos (EMBARGO002 - EMBARGO005).
        Replica la logica de _embargo001 pero con rule_code dinamico.
        """
        slip = localdict['slip']
        employee = localdict['employee']
        contract = localdict['contract']
        categories = localdict.get('categories')
        rules = localdict.get('rules')
        annual_parameters = localdict.get('annual_parameters')

        # Obtener regla y concepto
        rule = self.get_salary_rule(rule_code, employee.employee_type)
        # Buscar concepto de embargo aprobado en el contrato
        concept = None
        if rule and hasattr(contract, 'concepts_ids'):
            concepts = contract.concepts_ids.filtered(
                lambda c: c.input_id.id == rule.id and
                          c.state == 'done' and
                          c.type_deduction == 'E'
            )
            concept = concepts[0] if concepts else None
        elif rule:
            # Fallback: buscar en el modelo directamente
            ConceptModel = self.env['hr.contract.concepts']
            concepts = ConceptModel.search([
                ('contract_id', '=', contract.id),
                ('input_id', '=', rule.id),
                ('state', '=', 'done'),
                ('type_deduction', '=', 'E')
            ], limit=1)
            concept = concepts[0] if concepts else None

        data_result = {
            'valor_embargo': 0.0,
            'tipo_embargo': '',
            'limite_legal': 0.0,
            'base_calculo': 0.0,
            'otros_embargos': 0.0,
            'limite_disponible': 0.0,
            'es_alimentario': False,
            'context_name': '',
            'status': 'no_concept'
        }

        if not concept:
            return 0.0, 1, 0.0, f'{rule_code} - Sin concepto', False, data_result

        # Nombre contextual
        context_name = f"EMBARGO - {concept.name}" if concept.name else rule_code
        data_result['context_name'] = context_name
        name = context_name

        tipo_emb = getattr(concept, 'type_emb', 'OTRO') or 'OTRO'
        data_result['tipo_embargo'] = tipo_emb
        data_result['es_alimentario'] = (tipo_emb == 'ECA')

        # Validar aplicacion segun quincena
        day = slip.date_from.day
        aplicar = getattr(concept, 'aplicar', '0')
        if (day < 15 and aplicar == '30') or (day >= 15 and aplicar == '15'):
            data_result['status'] = 'no_aplica_quincena'
            return 0.0, 0, 0.0, name, False, data_result

        # Obtener categorias y reglas para descontar
        cat_codes = []
        rule_codes = []
        if hasattr(concept, 'discount_categoria'):
            cat_codes = [c.code for c in concept.discount_categoria]
        if hasattr(concept, 'discount_rule'):
            rule_codes = [r.code for r in concept.discount_rule]
        if not cat_codes and not rule_codes:
            cat_codes = ['BASIC']

        # Calcular base
        base = 0.0
        if cat_codes and categories:
            # get_total() espera lista de códigos como kwarg 'category_codes'
            base += categories.get_total(category_codes=cat_codes)
        if rule_codes and rules:
            for rc in rule_codes:
                rule_data = rules.get(rc)
                if rule_data:
                    base += rule_data.total

        data_result['base_calculo'] = base
        smmlv = annual_parameters.smmlv_monthly if annual_parameters else 0.0

        # Obtener otros embargos activos
        otros_embargos_total = 0.0
        otros_embargos_alimentos = 0.0

        if rules:
            for rc in rules.get_codes():
                if rc.startswith('EMBARGO') and rc != rule_code:
                    rule_data = rules.get(rc)
                    if rule_data and rule_data.total > 0:
                        otros_embargos_total += rule_data.total
                        extra_data = rule_data.extra_data
                        if extra_data.get('tipo_embargo') == 'ECA':
                            otros_embargos_alimentos += rule_data.total

        data_result['otros_embargos'] = otros_embargos_total

        # Calcular limites segun tipo de embargo
        if data_result['es_alimentario']:
            limite_maximo = base * 0.5
            limite_disponible = limite_maximo - otros_embargos_alimentos
        else:
            excedente = max(0.0, base - smmlv)
            limite_maximo = excedente * 0.2
            limite_disponible = limite_maximo - (otros_embargos_total - otros_embargos_alimentos)

        data_result['limite_legal'] = limite_maximo
        data_result['limite_disponible'] = limite_disponible

        if limite_disponible <= 0:
            data_result['status'] = 'sin_limite'
            return 0.0, 1, 0.0, f'{name} - Sin limite disponible', False, data_result

        # Calcular monto segun tipo de calculo del concepto
        amount_select = getattr(concept, 'amount_select', 'fix')
        amount = getattr(concept, 'amount', 0.0) or 0.0

        if amount_select == 'percentage':
            pct = amount
            if data_result['es_alimentario']:
                embargoable_raw = base * (pct / 100.0)
            else:
                excedente = max(0.0, base - smmlv)
                embargoable_raw = excedente * (pct / 100.0)
        elif amount_select == 'fix':
            embargoable_raw = amount
            pct = (amount / base * 100.0) if base > 0 else 0.0
        else:
            pct = amount / 100.0 if amount else 0.0
            embargoable_raw = base * (pct / 100.0)

        # Ajustar al limite disponible
        embargoable = min(embargoable_raw, limite_disponible)
        data_result['valor_embargo'] = embargoable
        data_result['status'] = 'aplicado'

        return -embargoable, 1, pct, name, False, data_result

    # ══════════════════════════════════════════════════════════════════════════
    # MÉTODOS CONSOLIDADOS DE hr_rule.py
    # ══════════════════════════════════════════════════════════════════════════
    # Los siguientes métodos fueron copiados de hr_rule.py para consolidar toda
    # la lógica en un solo archivo.
    # ══════════════════════════════════════════════════════════════════════════


    def _compute_rule(self, localdict):
        """
        :param localdict: dictionary containing the current computation environment
        :return: returns a tuple (amount, qty, rate)
        :rtype: (float, float, float)
        """
        self.ensure_one()
        res = 0,0,0,0,0,[]#monto:float, cantidad:float, tasa:float, nombre:str, log:Xml, data:dict
        if self.amount_select == 'fix':
            try:
                return
            except Exception as e:
                self._raise_error(localdict, _("Wrong quantity defined for:"), e)
        if self.amount_select == 'percentage':
            try:
                return (float(safe_eval(self.amount_percentage_base, localdict)),
                        float(safe_eval(self.quantity, localdict)),
                        self.amount_percentage or 0.0, self.name,False,False)
            except Exception as e:
                self._raise_error(localdict, _("Wrong percentage base or quantity defined for:"), e)
        if self.amount_select == 'code':
            try:
                safe_eval(self.amount_python_compute or 0.0, localdict, mode='exec')
                return float(localdict['result']), localdict.get('result_qty', 1.0), localdict.get('result_rate', 100.0), self.name,False,False
            except Exception as e:
                self._raise_error(localdict, _("Wrong python code defined for:"), e)
        if self.amount_select == 'concept':
            try:
                method = getattr(self, '_' + str(self.code).lower(), None)
                if method:
                    res = method(localdict)
                    return float(res[0]), res[1], res[2], res[3],res[4],res[5]
                return float(res[0]), res[1], res[2] , res[3],res[4],res[5]
            except Exception as e:
                self._raise_error(localdict, _("Wrong python code defined for:"), e)




    def _compute_rule_lavish(self, localdict):
        """
        :param localdict: dictionary containing the current computation environment
        :return: returns a tuple (amount, qty, rate)
        :rtype: (float, float, float)
        """
        self.ensure_one()
        res = 0,0,0,0,0,[]
        try:
            if self.amount_select == 'fix':
                try:
                    return self.amount_fix or 0.0, float(safe_eval(self.quantity, localdict)), 100.0,False,False,False
                except Exception as e:
                    self._raise_error(localdict, _("Wrong quantity defined for:"), e, "amount_fix calculation")
                    
            if self.amount_select == 'percentage':
                try:
                    return (float(safe_eval(self.amount_percentage_base, localdict)),
                            float(safe_eval(self.quantity, localdict)),
                            self.amount_percentage or 0.0,False,False,False)
                except Exception as e:
                    self._raise_error(localdict, _("Wrong percentage base or quantity defined for:"), e, "percentage calculation")
                    
            if self.amount_select == 'code':
                try:
                    safe_eval(self.amount_python_compute or 0.0, localdict, mode='exec')
                    return float(localdict['result']), localdict.get('result_qty', 1.0), localdict.get('result_rate', 100.0),False,False,False
                except Exception as e:
                    error_context = {
                        'code': self.amount_python_compute,
                        'location': 'Python code evaluation'
                    }
                    self._raise_error(localdict, _("Wrong python code defined for:"), e, "code evaluation", error_context)
                    
            if self.amount_select == 'concept':                    
                code_lower = str(self.code).lower()
                method_name = f'_{code_lower}'
                try:
                    # OPTIMIZACIÓN: Ejecutar directamente el método del concepto sin evaluación previa
                    # La lógica de si debe ejecutarse está dentro del método del concepto mismo
                    method = getattr(self, method_name, None)
                    
                    if method:
                        # Ejecutar método del concepto directamente
                        res = method(localdict)
                        def _na_float(v):
                            # Los métodos de concepto devuelven el centinela 'na' (no aplica)
                            # cuando la regla no debe generar valor. Se trata como 0.0 -> sin línea.
                            try:
                                return float(v)
                            except (TypeError, ValueError):
                                return 0.0
                        # Validar que el resultado tenga la estructura correcta
                        if res and isinstance(res, (tuple, list)) and len(res) >= 6:
                            return _na_float(res[0]), res[1], res[2], res[3], res[4], res[5]
                        elif res and isinstance(res, (tuple, list)) and len(res) >= 3:
                            # Compatibilidad con tuplas de 3 elementos (amount, qty, rate)
                            return _na_float(res[0]), res[1], res[2], self.name, False, {}
                        else:
                            # Si el método no devuelve un formato válido, retornar valores por defecto
                            return 0.0, 1.0, 100.0, self.name, False, {}
                    else:
                        # Si no existe el método, retornar valores por defecto sin error
                        # Esto permite que reglas tipo 'concept' puedan no tener método definido
                        # y simplemente retornar 0 (útil para reglas condicionales)
                        return 0.0, 1.0, 100.0, self.name, False, {}
                except Exception as e:
                    error_context = {
                        'method_name': method_name,
                        'rule_code': self.code,
                        'location': 'Concept method execution'
                    }
                    self._raise_error(localdict, _("Error executing concept method:"), e, "concept execution", error_context)
                    
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
            localdict['payslip'].name,
            self.name,
            self.code,
            type(e).__name__,
            str(e),
            error_details,
            code_context,
            trace_details)
        
        raise UserError(error_message)



    # ══════════════════════════════════════════════════════════════════════════
    # MÉTODOS PARA OBTENER DATOS DEL PERÍODO ACTUAL (MES EN PROCESO)
    # ══════════════════════════════════════════════════════════════════════════


    def _format_money(self, value):
        """
        Formatea un valor numérico como moneda con punto como separador de miles
        y coma como separador decimal, siempre con 2 decimales.
        """
        if value is None:
            return "$0,00"
        # Formatear con punto como separador de miles y coma como decimal
        return f"${value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')


    def _format_number(self, value):
        """
        Formatea un valor numérico con punto como separador de miles
        y coma como separador decimal, siempre con 2 decimales.
        """
        if value is None:
            return "0,00"
        # Formatear con punto como separador de miles y coma como decimal
        return f"{value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')


    def _get_context_name(self, concept, payslip):
        """
        Obtiene el nombre contextual del concepto según la nómina actual.
        Si el concepto ya tiene context_name, lo devuelve; de lo contrario, lo calcula.
        """
        base_parts = []
        if concept.input_id:
            base_parts.append(concept.input_id.name)
        
        if payslip:
            date_to = payslip.date_to
            fortnight = "1Q" if date_to.day <= 15 else "2Q"
            month_year = f"{date_to.strftime('%b').upper()}/{date_to.year}"
            base_parts.append(f"{fortnight} {month_year}")
        
        if concept.is_deduction and concept.is_earning:
            tipo = "D" if concept.is_deduction else "I" if concept.is_earning else "C"
            base_parts.append(f"[{tipo}]")
        
        return " - ".join(base_parts) if base_parts else ""


    def _get_tipo_ausencia(self, tipo_novedad):
        """Retorna el nombre legible del tipo de ausencia según el código"""
        tipos = {
            'vac': 'VACACIONES',
            'ige': 'Incapacidad EPS',
            'irl': 'Incapacidad ARL',
            'lnr': 'Licencia no Remunerada',
            'lma': 'Licencia de Maternidad',
            'lpa': 'Licencia de Paternidad',
            'vdi': 'Vacaciones Disfrutadas',
            'p': 'Permisos no remunerados D/H (No se envia en pila)',
            'sln': 'Suspensión',
        }
        return tipos.get(tipo_novedad, tipo_novedad.upper() if tipo_novedad else 'OTRO')
    
    










    # ======================================================================
    # FUNCIONES ÚNICAS DE hr_rule.py (MIGRADAS)
    # ======================================================================

    def need_compute_salary_average(self, contract, date_from, date_to):
        date_3_months_before = date_to - relativedelta(months=3)
        if date_from > date_3_months_before:
            date_3_months_before = date_from
        return contract.has_change_salary(date_3_months_before, date_to)
    


    def _get_periodo(self, slip) -> str:
        """
        Devuelve la etiqueta de periodo basada en payslip:
          - "Vacaciones MM-YY" para struct_process='vacaciones'
          - "Primera Q1 MM-YY" o "Segunda Q2 MM-YY" en nóminas ordinarias
        """
        date_to = slip.date_to
        etiqueta_fecha = date_to.strftime('%m-%y')
        tipo = slip.struct_process
        if tipo == 'vacaciones':
            label = 'Vacaciones'
        else:
            label = 'Q1' if date_to.day <= 15 else 'Q2'
        return f"{self.name} {label} {etiqueta_fecha}".capitalize()


    def compute_payslip_2_values(self, localdict, exclude_leaves=False):
        """
        - Incluye reglas DEV_SALARIAL y DEV_NO_SALARIAL.
        - Para DEV_SALARIAL exige base_seguridad_social=True.
        - Para DEV_NO_SALARIAL considera excluir_40_porciento_ss=False (incluido en límite 40%).
        - Si exclude_leaves=True, ignora líneas de ausencia (is_leave o has_leave).
        - Extrae montos de localdict['rules'] para el payslip actual (ODOO 18).
        - Agrupa por categoría padre (si existe) o categoría.
        - Mantiene rest_of_period calculado por línea.

        Args:
            localdict: Diccionario de contexto con rules, categories, etc.
            exclude_leaves: Si True, excluye reglas de ausencia del total_salary.
                           Las ausencias tienen su propio IBC del mes anterior.
        """
        data_ibc = {
            'rest_of_period': {
                'year_month': False,
                'total_salary': 0.0,
                'total_no_salary': 0.0,
            },
            'current_slip': {
                'year_month': False,
                'total_salary': 0.0,
                'total_no_salary': 0.0,
            },
            'grand_totals': {
                'total_salary': 0.0,
                'total_no_salary': 0.0,
            },
            'events': [],
            'line_ids': [],  # IDs de líneas de nómina consultadas
        }
        slip = localdict['slip']
        contract = localdict.get('contract', slip.contract_id)

        # Usar método de acumulación para obtener datos del mes hasta el slip anterior
        start_date = slip.date_from.replace(day=1)
        end_date = slip.date_from - timedelta(days=1)

        # Usar servicio centralizado de consultas para IBD
        query_service = self.env['period.payslip.query.service']
        ibd_result = query_service.get_ibd_data(
            contract_id=contract.id,
            date_from=start_date,
            date_to=end_date,
            exclude_payslip_id=slip.id,
            states=('done', 'paid'),
        )

        # Procesar resultados del servicio (ya filtrados por base_seguridad_social)
        for line_detail in ibd_result.get('list', []):
            data_type = line_detail.get('data_type', 'other')
            
            if data_type == 'salary':
                # DEV_SALARIAL con base_seguridad_social (ya filtrado por el servicio)
                data_ibc['rest_of_period']['total_salary'] += line_detail.get('total', 0.0)
                data_ibc['line_ids'].append(line_detail['line_id'])
                data_ibc['events'].append({
                    'date': line_detail.get('date_to'),
                    'origin': 'MES ACTUAL',
                    'foce_min': '',
                    'sequence': 0,  # Se puede obtener de la línea si es necesario
                    'factor': line_detail.get('quantity', 1.0),
                    'days': line_detail.get('quantity', 0.0),
                    'base_daily': 0.0,
                    'calc_value': line_detail.get('amount', 0.0),
                    'slip_value': line_detail.get('total', 0.0),
                    'rule_id': None,  # Se puede obtener de la línea si es necesario
                    'novelty': 'NOM-ANT',
                })
            elif data_type == 'no_salary':
                # DEV_NO_SALARIAL (ya filtrado por el servicio)
                category_code = line_detail.get('category_code', '')
                if category_code != 'AUX':  # Excluir auxilios
                    data_ibc['rest_of_period']['total_no_salary'] += line_detail.get('total', 0.0)
                    data_ibc['line_ids'].append(line_detail['line_id'])
                    data_ibc['events'].append({
                        'date': line_detail.get('date_to'),
                        'origin': 'MES ACTUAL',
                        'foce_min': '',
                        'sequence': 0,
                        'factor': line_detail.get('quantity', 1.0),
                        'days': line_detail.get('quantity', 0.0),
                        'base_daily': 0.0,
                        'calc_value': line_detail.get('amount', 0.0),
                        'slip_value': line_detail.get('total', 0.0),
                        'rule_id': None,
                        'novelty': 'NOM-ANT',
                    })

        # Mantener compatibilidad: también obtener categorías acumuladas (para otros usos)
        accumulated_cats = slip._get_categories_accumulated_by_payslip(start_date, end_date)
        data_ibc['rest_of_period_categories'] = accumulated_cats
        # Usar estructura Odoo 19 nativa localdict['rules'] en lugar de rules_multi
        rules = localdict.get('rules', {})
        for code, rule_data in rules.items():
            rule = rule_data.rule
            if not rule:
                continue

            cat = rule.category_id
            amount = rule_data.total
            unitario = rule_data.amount
            cantidad = rule_data.quantity
            porcentaje = rule_data.rate

            # Verificar si es ausencia o auxilio
            # Si exclude_leaves=True, excluir reglas de ausencia (tienen su propio IBC)
            if amount == 0.0 or rule.category_id.code in ('AUX'):
                continue
            if exclude_leaves:
                has_leave = getattr(rule_data, 'has_leave', False)
                if rule.is_leave or has_leave:
                    continue

            # Ingresos salariales: cualquier regla con base_seguridad_social=True
            # (excluir auxilios y ausencias ya filtradas arriba).
            # Si el valor viene negativo (p.ej. sanciones/deducciones configuradas
            # para IBC), se toma en absoluto para que incremente la base.
            if rule.base_seguridad_social:
                if amount < 0:
                    amount = abs(amount)
                    unitario = abs(unitario or 0.0)
                data_ibc['current_slip']['total_salary'] += amount
            # Ingresos no salariales (para regla 40%): solo DEV_NO_SALARIAL si aplica
            elif cat.code == 'DEV_NO_SALARIAL' or (cat.parent_id and cat.parent_id.code == 'DEV_NO_SALARIAL'):
                if rule.excluir_40_porciento_ss:
                    continue
                data_ibc['current_slip']['total_no_salary'] += amount
            else:
                continue

            data_ibc['events'].append({
                'date':       slip.date_to,
                'origin':     'NOM ACTUAL',
                'foce_min':  '',
                'sequence':   rule.sequence,
                'factor':     porcentaje,
                'days':       cantidad,
                'base_daily': 0.0,
                'calc_value': unitario,
                'slip_value': amount,
                'rule_id':    rule,
                'novelty':    'NOM',
            })

        data_ibc['grand_totals']['total_salary'] += data_ibc['current_slip']['total_salary'] + data_ibc['rest_of_period']['total_salary']
        data_ibc['grand_totals']['total_no_salary'] += data_ibc['current_slip']['total_no_salary'] + data_ibc['rest_of_period']['total_no_salary']

        return data_ibc


    def compute_absences(self, localdict):
        """
        1) Toma de localdict:
           - slip            : hr.payslip actual
           - before_month    : "YYYY-MM" del mes anterior
           - current_month   : "YYYY-MM" del mes en curso
           - payslip_data    : {
                 'before_month': [ { 'payslip_ids': [...], ... }, ... ],
                 'current_month': [ { 'payslip_ids': [...], ... }, ... ]
             }
           - previous_ibc    : IBC calculado del mes anterior (float)
           - use_previous_ibc: bool, si debe usar ibc anterior
           - year_avg        : promedio anual (float, opcional)
        2) Extrae **todos** los payslip_ids de cada lista.
        3) Divide en previous_ids, rest_ids y current_id.
        4) Para cada grupo acumula líneas de hr.leave.line según la lógica descrita.
        """
        slip           = localdict['slip']
        before_month   = localdict.get('before_month', [])
        current_month  = localdict.get('current_month', [])
        annual_params = localdict['annual_parameters']
        prev_ids = []
        for rec in before_month:
            prev_ids.extend(rec.get('payslip_ids', []))
        curr_ids = []
        for rec in current_month:
            curr_ids.extend(rec.get('payslip_ids', []))

        rest_ids = [pid for pid in curr_ids if pid != slip.id]

        Line = self.env['hr.leave.line']
        groups = {
            'previous': Line.search([('payslip_id', 'in', prev_ids)]),
            'rest':     Line.search([('payslip_id', 'in', rest_ids)]),
            'current':  Line.search([('payslip_id', '=', slip.id)]),
        }
        def _dias_in(d):
            return slip.date_from.year  == d.year and slip.date_to.month == d.month
        
        def _accumulate(lines, origin, slip_ids, period):
            data = {
                'year_month':  period,
                'slip_ids':    slip_ids,
                'total_days':  0.0,
                'total_value': 0.0,
                'events':      [],
            }
            for ln in lines.filtered(lambda ln: ln.rule_id.base_seguridad_social):
                lt = ln.leave_id
                leave_type = lt.holiday_status_id
                typ = leave_type.novelty
                factor, _ = leave_type.get_rate_concept_id(ln.sequence)
                dias_en_periodo = ln.days_payslip
                if not _dias_in(ln.date) and origin != 'previous' and typ != 'vdi':
                    continue
                if ln.date.day == 31:
                    continue
                if origin == 'previous' and not typ == 'vdi':
                    continue
                is_unpaid = bool(getattr(leave_type, 'unpaid_absences', False)) or typ in ('lnr', 'p', 'sln')
                ibc_diario_anterior = None
                base_daily = 0.0
                calc_value = 0.0

                if is_unpaid:
                    origen_base = 'SIN_PAGO'
                elif ln.rule_id.liquidar_con_base:
                    ibc_diario_anterior = self._obtener_ibc_diario_previo(
                        slip.contract_id,
                        slip.date_from,
                        usar_valor_pagado=False,
                        rule=ln.rule_id  # Pasar regla para usar aplicar_limite_minimo_ibc
                    )
                    base_daily = ibc_diario_anterior
                    calc_value = base_daily * factor * ln.days_payslip
                    origen_base = 'IBC_MES_ANTERIOR'
                else:
                    calc_value = ln.amount
                    base_daily = (ln.amount / ln.days_payslip) if ln.days_payslip else 0.0
                    origen_base = 'VALOR_AUSENCIA'

                valor_smlv_diario = annual_params.smmlv_monthly / 30
                valor_smlv_total = valor_smlv_diario * ln.days_payslip

                # aplicar_limite_minimo_ibc: campo separado para garantizar IBC minimo
                if ln.rule_id.aplicar_limite_minimo_ibc and not is_unpaid:
                    slip_val = self._set_limits_ibc(calc_value, valor_minimo=valor_smlv_total)
                else:
                    slip_val = 0.0 if is_unpaid else ln.amount
                
                # ══════════════════════════════════════════════════════════════════════════
                # VALIDACIÓN DEL TOTAL DE LÍNEA
                # ══════════════════════════════════════════════════════════════════════════
                # Verificar si el total de la línea (ln.amount) es consistente con
                # el valor calculado (calc_value). Si hay discrepancia significativa,
                # se registra para análisis.
                # ══════════════════════════════════════════════════════════════════════════
                discrepancia = abs(ln.amount - calc_value) if ln.amount > 0 else 0.0
                tiene_discrepancia = discrepancia > 1.0  # Tolerancia de 1 peso

                if not is_unpaid:
                    data['total_days']  += ln.days_payslip
                    data['total_value'] += slip_val
                data['events'].append({
                    'date':       ln.date,
                    'origin':     origin,
                    'usa_ibc_anterior': ln.rule_id.liquidar_con_base,  # Usa IBC mes anterior
                    'aplica_minimo': ln.rule_id.aplicar_limite_minimo_ibc,  # Aplica limite minimo
                    'sequence':   ln.sequence,
                    'factor':     factor,
                    'days':       dias_en_periodo,
                    'base_daily': base_daily,
                    'calc_value': calc_value,
                    'slip_value': slip_val,
                    'rule_id':    ln.rule_id,
                    'novelty':    typ,
                    'origen_base': origen_base,
                    'valor_diario_usado': ibc_diario_anterior if origen_base == 'IBC_MES_ANTERIOR' else None,
                    # ✅ NUEVO: Validación del total de línea
                    'ln_amount': ln.amount,  # Valor original de la línea
                    'discrepancia': discrepancia,  # Diferencia entre ln.amount y calc_value
                    'tiene_discrepancia': tiene_discrepancia,  # Flag para análisis
                })
            return data

        prev_data = _accumulate(groups['previous'], 'previous', prev_ids, before_month)
        rest_data = _accumulate(groups['rest'],     'rest',     rest_ids, current_month)
        curr_data = _accumulate(groups['current'],  'current',  [slip.id], current_month)

        return {
            'previous_period': prev_data,
            'rest_of_period': rest_data,
            'current_slip': curr_data,
            'total_days': rest_data['total_days'] + curr_data['total_days'] + prev_data['total_days'],
            'total_value': rest_data['total_value'] + curr_data['total_value'] + prev_data['total_value'],
        }
        

    def category_code(self,rule):
        cat = rule.category_id
        while cat:
            if cat.code in ('DEV_SALARIAL', 'DEV_NO_SALARIAL'):
                return cat.code
            if cat.code in ('INDEM', 'PRESTACIONES_SOCIALES', 'AUX'):
                return None
            cat = cat.parent_id
        return None
    

    def _get_totalizar_other_reglas(
        self,
        liquidacion_data: Dict[str, Any],
        codigos_regla: Optional[Union[str, List[str]]] = None,
        filtros: Optional[Dict[str, Callable[[Any], bool]]] = None,
        incluir_current: bool = True,
        incluir_before: bool = False,
        incluir_multi: bool = True,  # Obsoleto - se mantiene por compatibilidad
        devolver_cantidad: bool = False,
        solo_con_ausencias: bool = False,
        excluir_con_ausencias: bool = False
        ) -> Union[float, int]:
        """
        Totaliza reglas de nómina según los criterios especificados.

        Args:
            liquidacion_data: Diccionario con datos de liquidación
            codigos_regla: Códigos de reglas a totalizar (None = todas)
            filtros: Diccionario con funciones de filtrado
            incluir_current: No usado en Odoo 19 (se mantiene por compatibilidad)
            incluir_before: No usado en Odoo 19 (se mantiene por compatibilidad)
            incluir_multi: Obsoleto en Odoo 19 (se mantiene por compatibilidad)
            devolver_cantidad: Si se devuelve la cantidad en lugar del valor
            solo_con_ausencias: Si se incluyen solo las reglas con ausencias
            excluir_con_ausencias: Si se excluyen las reglas con ausencias

        Returns:
            float o int: Total acumulado según los criterios
        """
        # Validamos que los parámetros de ausencia no sean contradictorios
        if solo_con_ausencias and excluir_con_ausencias:
            raise ValueError("No se pueden activar solo_con_ausencias y excluir_con_ausencias simultáneamente")

        if codigos_regla is None:
            codigos = list(liquidacion_data.get('rules', {}).keys())
        else:
            codigos = codigos_regla if isinstance(codigos_regla, list) else [codigos_regla]

        filtros = filtros or {}
        def pasa_filter(obj: Any):
            """Evalúa si un objeto pasa todos los filtros especificados"""
            for attr_name, condition_func in filtros.items():
                if attr_name == 'object':
                    if not condition_func(obj):
                        return False
                else:
                    attr_value = getattr(obj, attr_name, None)
                    if callable(condition_func):
                        if not condition_func(attr_value):
                            return False
                    else:
                        if bool(attr_value) != bool(condition_func):
                            return False
            return True

        entradas: List[Dict[str, Any]] = []

        # ODOO 18 NATIVO: Usar estructura 'rules'
        for code in codigos:
            rule_data = liquidacion_data.get('rules', {}).get(code)
            if rule_data:
                rule_obj = rule_data.rule
                if rule_obj:
                    entradas.append({
                        'object': rule_obj,
                        'total': rule_data.total,
                        'quantity': rule_data.quantity,
                        'leave': {},
                    })

        total_valor = 0.0
        total_entradas = 0
        for item in entradas:
            obj = item.get('object')
            if not obj or not pasa_filter(obj):
                continue

            # Filtramos por ausencias
            tiene_ausencias = bool(item.get('leave', {}))
            if solo_con_ausencias and not tiene_ausencias:
                continue
            if excluir_con_ausencias and tiene_ausencias:
                continue

            if devolver_cantidad:
                total_entradas += item.get('quantity', 0)
            else:
                total_valor += item.get('total', 0.0)

        return total_entradas if devolver_cantidad else total_valor


    def _trae_totalizar_categorias(
        self,
        localdict: Dict[str, Any],
        categorias: Optional[Union[List[str], str]] = None,
        categorias_excluir: Optional[Union[List[str], str]] = None,
        filtros: Optional[Dict[str, Callable[[Any], bool]]] = None,
        incluir_current: bool = True,  # Obsoleto - se mantiene por compatibilidad
        incluir_before: bool = False,  # Obsoleto - se mantiene por compatibilidad
        incluir_multi: bool = True,  # Obsoleto - se mantiene por compatibilidad
        incluir_subcategorias: bool = True,
        solo_con_ausencias: bool = False,
        excluir_con_ausencias: bool = False
        ) -> Tuple[float, float]:
        """
        Totaliza categorías de nómina en Odoo 19.

        Args:
            localdict: Diccionario local con datos de nómina
            categorias: Categorías a incluir (None = todas)
            categorias_excluir: Categorías a excluir
            filtros: Diccionario con funciones de filtrado
            incluir_subcategorias: Si se incluyen subcategorías
            solo_con_ausencias: Si se incluyen solo las reglas con ausencias
            excluir_con_ausencias: Si se excluyen las reglas con ausencias

        Returns:
            Tuple[float, float]: (valor total, total de entradas)
        """
        # Validamos que los parámetros de ausencia no sean contradictorios
        if solo_con_ausencias and excluir_con_ausencias:
            raise ValueError("No se pueden activar solo_con_ausencias y excluir_con_ausencias simultáneamente")
        
        def _to_list(x: Optional[Union[List[str], str]]) -> Optional[List[str]]:
            if x is None:
                return None
            return x if isinstance(x, list) else [x]

        categorias = _to_list(categorias)
        categorias_excluir = _to_list(categorias_excluir)
        filtros = filtros or {}

        def _pasa_filtros(obj: Any):
            """Evalúa si un objeto pasa todos los filtros especificados"""
            for attr_name, condition_func in filtros.items():
                if attr_name == 'object':
                    if not condition_func(obj):
                        return False
                else:
                    attr_value = getattr(obj, attr_name, None)
                    if callable(condition_func):
                        if not condition_func(attr_value):
                            return False
                    else:
                        if bool(attr_value) != bool(condition_func):
                            return False
            return True

        fuente: List[Dict[str, Any]] = []
        # ODOO 18: Usar estructura nativa 'rules'
        for code, rule_data in localdict.get('rules', {}).items():
            rule_obj = rule_data.rule
            if rule_obj:
                fuente.append({
                    'code': code,
                    'object': rule_obj,
                    'total': rule_data.total,
                    'quantity': rule_data.quantity,
                    'leave': {},
                })

        reglas_por_cat: Dict[str, set] = {} 
        padres: Dict[str, str] = {}
        for item in fuente:
            obj = item['object']
            if not obj.category_id:
                continue
            cat = obj.category_id.code
            reglas_por_cat.setdefault(cat, set()).add(item['code'])
            if obj.category_id.parent_id:
                padres.setdefault(cat, obj.category_id.parent_id.code)

        hijos: Dict[str, set] = {}
        for cat, p in padres.items():
            hijos.setdefault(p, set()).add(cat)

        if categorias is None:
            cats = set(reglas_por_cat)
        else:
            cats = set(categorias)
            if incluir_subcategorias:
                cola = list(cats)
                while cola:
                    c = cola.pop()
                    for h in hijos.get(c, ()):
                        if h not in cats:
                            cats.add(h)
                            cola.append(h)

        if categorias_excluir:
            ex = set(categorias_excluir)
            if incluir_subcategorias:
                cola = list(ex)
                while cola:
                    c = cola.pop()
                    for h in hijos.get(c, ()):
                        if h not in ex:
                            ex.add(h)
                            cola.append(h)
            cats -= ex
            
        total_valor = 0.0
        total_entradas = 0
        for item in fuente:
            obj = item['object']
            cat = obj.category_id.code if obj.category_id else None
            if cat not in cats or not _pasa_filtros(obj):
                continue
                
            # Filtramos por ausencias
            tiene_ausencias = bool(item.get('leave', {}))
            if solo_con_ausencias and not tiene_ausencias:
                continue
            if excluir_con_ausencias and tiene_ausencias:
                continue
            valor = item.get('total', 0.0)
            total_valor += item.get('total', 0.0)
            total_entradas += item.get('quantity', 0)

        return total_valor, total_entradas

    

    def get_holiday_book(self, contract, date_from=False, date_ref=False):
        """
        Calcula los días de vacaciones acumulados y disponibles para un empleado
        
        Args:
            contract: Contrato del empleado
            date_ref: Fecha de referencia para el cálculo (por defecto, fecha actual)
            
        Returns:
            dict: Diccionario con información de días trabajados, disponibles, disfrutados, etc.
        """
        date_ref = date_ref or contract.date_ref_holiday_book or datetime.now()
        worked_days = days360(date_from, date_ref)
        
        days_enjoyed, days_paid, days_suspension = 0, 0, 0
        
        for holiday_book in contract.vacaciones_ids:
            days_enjoyed += holiday_book.business_units
        
        leave_domain = [
            ("leave_id.employee_id", "=", contract.employee_id.id),
            ("leave_id.state", "=", "validate"),
            ("leave_id.unpaid_absences", "=", True),
            ("date", ">=", date_from),
            ("date", "<=", date_ref),
        ]
        grouped = self.env["hr.leave.line"]._read_group(
            leave_domain,
            groupby=[],
            aggregates=["days_payslip:sum"],
        )
        days_suspension = float(grouped[0][0] or 0.0) if grouped else 0.0

        worked_days_adjusted = worked_days - days_suspension

        days_left = (worked_days_adjusted * 15 / DAYS_YEAR) #- days_enjoyed
        return {
            'worked_days': round_1_decimal(worked_days),
            'worked_days_adjusted': round_1_decimal(worked_days_adjusted),
            'days_left': round_1_decimal(days_left),
            'days_enjoyed': round_1_decimal(days_enjoyed),
            'days_paid': round_1_decimal(days_paid),
            'days_suspension': round_1_decimal(days_suspension),
        }


    def _round1(self, amount: Decimal | float) -> Decimal:
        """Redondea al entero más cercano (sin decimales) usando Decimal."""
       
        if not isinstance(amount, Decimal):
            amount = Decimal(str(amount))
        return amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


    def _label_vac_liq(
        self,
        days_pending: Decimal | float,
        days_enjoyed: Decimal | float,
        ) -> str:
        """Construye la etiqueta *VACACIONES LIQ.* con acrónimos y emojis. 
        """
        icon_pending = '$' 
        icon_enjoyed = "" 
        dpp = f"D.P.P=({icon_pending} {round(days_pending,2)})"
        ddf = f"D.D.F=({icon_enjoyed} {round(days_enjoyed,2)})"
        return f"VACACIONES LIQ. DE CONTRATO {dpp} {ddf}"


    def get_last_year(self, data_payslip, date_to):
        date_from = date_to - relativedelta(years=1)
        if date_from < data_payslip['contract'].date_start:
            date_from = data_payslip['contract'].date_start
        days = days360(date_from, date_to)
        leave_domain = [
            ('date', '>=', data_payslip['slip'].date_vacaciones),
            ('date', '<=', data_payslip['slip'].date_liquidacion),
            ('state', 'in', ['paid', 'validate', 'validated']),
            ('leave_id.contract_id', '=', data_payslip['contract'].id),
            ('leave_id.employee_id', '=', data_payslip['slip'].employee_id.id),
            ('leave_id.holiday_status_id.unpaid_absences', '=', True),
        ]
        grouped = self.env['hr.leave.line']._read_group(
            leave_domain,
            groupby=[],
            aggregates=['days_payslip:sum'],
        )
        dias_ausencias = float(grouped[0][0] or 0.0) if grouped else 0.0
        dias_ausencias += sum([i.days for i in self.env['hr.absence.history'].search([('star_date', '>=', data_payslip['slip'].date_vacaciones), ('end_date', '<=', data_payslip['slip'].date_liquidacion),('employee_id', '=', data_payslip['slip'].employee_id.id), ('leave_type_id.unpaid_absences', '=', True)])])
        wd = days - dias_ausencias
        data = {}
        values_base_compensation = 0.0
        rules = data_payslip.get('rules', {})
        for rule_code, rule_data in rules.items():
            total = rule_data.get('total', 0)
            rule_obj = rule_data.get('rule')
            # Acceder a base_prima desde el objeto regla
            if rule_code != 'BASIC' and rule_code != 'AUX000' and rule_obj and getattr(rule_obj, 'base_prima', False):
                values_base_compensation += total
        acumulatdo = self.get_accumulated_compensation(data_payslip, date_from, date_to, values_base_compensation)
        return acumulatdo# / 30
    

    def get_accumulated_compensation(self, data_payslip, date_start, date_end, values_base_compensation):
        """
        Obtiene la compensación acumulada para el cálculo de prestaciones.

        También incluye registros de hr.accumulated.payroll.
        """
        date_start = date_end-relativedelta(years=1)
        date_start = data_payslip['contract'].date_start if date_start <= data_payslip['contract'].date_start else date_start
        dias_trabajados = days360(date_start, date_end)

        contract = data_payslip['contract']
        employee = contract.employee_id

        # Usar servicio centralizado para obtener datos de nómina
        # Nota: base_compensation no está directamente soportado en el servicio,
        # pero podemos filtrar después o extender el servicio
        query_service = self.env['period.payslip.query.service']
        
        # Obtener todas las líneas de prestaciones (que incluyen base_compensation)
        result = query_service.get_period_payslip_data(
            contract_id=contract.id,
            date_from=date_start,
            date_to=date_end,
            calculation_type='prestaciones',
            exclude_payslip_id=None,
            states=('done', 'paid'),
        )

        # Filtrar por base_compensation=True y categoría (excluir BASIC excepto BASICTURNOS)
        accumulated_payslip = 0.0
        for line in result.get('list', []):
            # Necesitamos verificar base_compensation en la regla
            line_obj = self.env['hr.payslip.line'].browse(line['line_id'])
            if line_obj.exists():
                rule = line_obj.salary_rule_id
                if rule and rule.base_compensation:
                    category_code = line.get('category_code', '')
                    rule_code = line.get('rule_code', '')
                    # Excluir BASIC excepto BASICTURNOS
                    if category_code != 'BASIC' or rule_code == 'BASICTURNOS':
                        accumulated_payslip += line.get('total', 0.0)

        # Consultar hr.accumulated.payroll (no está en el servicio aún)
        accumulated_payroll = 0.0
        HrAccumulatedPayroll = self.env['hr.accumulated.payroll']
        domain = [
            ('employee_id', '=', employee.id),
            ('date', '>=', date_start),
            ('date', '<=', date_end),
            ('contract_id', '=', contract.id),
        ]
        accumulated_records = HrAccumulatedPayroll.search(domain)
        for record in accumulated_records:
            rule = record.salary_rule_id
            if rule and rule.base_compensation:
                category = rule.category_id
                if category and (category.code != 'BASIC' or rule.code == 'BASICTURNOS'):
                    accumulated_payroll += record.amount or 0.0

        total_accumulated = accumulated_payslip + accumulated_payroll
        
        if dias_trabajados > 0:
            return ((total_accumulated + values_base_compensation) / dias_trabajados) * DAYS_YEAR
        else:
            return 0.0
        


class HrTypesFaults(models.Model):
    _name = 'hr.types.faults'
    _description = 'Tipos de faltas'

    name = fields.Char(
        'Nombre',
        required=True,
        help='Nombre del tipo de falta'
    )
    description = fields.Text(
        'Descripción',
        help='Descripción detallada del tipo de falta y sus implicaciones'
    )
