# -*- coding: utf-8 -*-
"""
PRESTACIONES - LIQUIDACION Y PAGOS
==================================
Metodos de pago para reglas salariales de prestaciones sociales.

Codigos de reglas salariales que usan estos metodos:
- PRIMA: _prima()
- CESANTIAS: _cesantias()
- INTCESANTIAS: _intcesantias()
- CES_YEAR: _ces_year()
- INTCES_YEAR: _intces_year()

Configuracion:
- cesantias_salary_take: Promediar salario ultimos 3 meses en cesantias
- prima_salary_take: Promediar salario ultimos 6 meses en prima
"""
from odoo import models, api
from datetime import date
from dateutil.relativedelta import relativedelta
import logging

from .basic import get_wage_changes_in_period
from .config_reglas import (
    crear_log_data, crear_resultado_regla, crear_computation_estandar,
    crear_indicador, crear_paso_calculo
)

_logger = logging.getLogger(__name__)


class HrSalaryRulePrestacionesLiquidacion(models.AbstractModel):
    """
    Servicio para liquidacion de prestaciones sociales.

    Metodos de pago (llamados por reglas con amount_select='concept'):
    - _prima(): Codigo PRIMA
    - _cesantias(): Codigo CESANTIAS
    - _intcesantias(): Codigo INTCESANTIAS
    - _ces_year(): Codigo CES_YEAR (cesantias año anterior)
    - _intces_year(): Codigo INTCES_YEAR (intereses año anterior)
    """
    _name = 'hr.salary.rule.prestaciones.liquidacion'
    _description = 'Liquidacion de Prestaciones Sociales'

    # =========================================================================
    # METODOS DE PAGO - Llamados por reglas salariales (amount_select='concept')
    # =========================================================================

    def _prima(self, localdict):
        """
        PRIMA DE SERVICIOS - Codigo regla: PRIMA

        Formula: (Base * Dias Trabajados) / 180
        Periodo: Semestre actual (Ene-Jun o Jul-Dic)
        Config: prima_salary_take (promediar salario ultimos 6 meses)

        CORREGIDO Bug #8: En liquidaciones, calcula ajuste (total - provisiones - pagos).

        Returns:
            tuple: (amount, qty, rate, name, log, data)
        """
        slip = localdict['slip']

        # Parametros del concepto PRIMA
        promedio_info = self._get_mesesapromediar(localdict, 'prima')
        params_prestacion = {
            'diasperiodo': 360,
            'diasapagar': 30,
            'mesesapromediar': promedio_info['mesesapromediar'],
            'promediar_salario': promedio_info['promediar_salario'],
            'cambio_salario': promedio_info['cambio_salario'],
            'codigo_provision': 'PRV_PRIM',
            'codigo_regla': 'PRIMA',
        }
        params_prestacion.update(self._get_cuentas_contables('PRIMA', 'PRV_PRIM'))

        # Determinar contexto segun estructura
        struct_process = slip.struct_id.process if slip.struct_id else 'nomina'
        context = 'liquidacion' if struct_process == 'contrato' else 'pago'

        # Sueldo y dias a pagar
        prestaciones_svc = self.env['hr.salary.rule.prestaciones']
        sueldo_info = prestaciones_svc._get_sueldo_dias_a_pagar(localdict, 'prima')
        variable_base = prestaciones_svc._get_variable_base(localdict, 'prima')

        # Promedio (considera no_promediar_sueldo_prestaciones)
        promedio = prestaciones_svc._compute_promedio(localdict, sueldo_info, variable_base, context)

        # Auxilio de transporte
        auxilio = prestaciones_svc._get_auxilio(localdict, 'prima', promedio, sueldo_info)

        return self._build_calculo(
            localdict, 'prima', params_prestacion,
            sueldo_info, variable_base, promedio, auxilio, context
        )

    def _cesantias(self, localdict):
        """
        CESANTIAS - Codigo regla: CESANTIAS

        Formula: (Base * Dias Trabajados) / 360
        Periodo: Ano actual (1 Ene - Fecha corte/terminacion)
        Config: cesantias_salary_take (promediar salario ultimos 3 meses)

        CORREGIDO Bug #4: En liquidaciones, calcula ajuste (total - provisiones - pagos).

        Returns:
            tuple: (amount, qty, rate, name, log, data)
        """
        slip = localdict['slip']

        # Parametros del concepto CESANTIAS
        promedio_info = self._get_mesesapromediar(localdict, 'cesantias')
        params_prestacion = {
            'diasperiodo': 360,
            'diasapagar': 30,
            'mesesapromediar': promedio_info['mesesapromediar'],
            'promediar_salario': promedio_info['promediar_salario'],
            'cambio_salario': promedio_info['cambio_salario'],
            'codigo_provision': 'PRV_CES',
            'codigo_regla': 'CESANTIAS',
        }
        params_prestacion.update(self._get_cuentas_contables('CESANTIAS', 'PRV_CES'))

        # Determinar contexto segun estructura
        struct_process = slip.struct_id.process if slip.struct_id else 'nomina'
        context = 'liquidacion' if struct_process == 'contrato' else 'pago'

        # Sueldo y dias a pagar
        prestaciones_svc = self.env['hr.salary.rule.prestaciones']
        sueldo_info = prestaciones_svc._get_sueldo_dias_a_pagar(localdict, 'cesantias')
        variable_base = prestaciones_svc._get_variable_base(localdict, 'cesantias')

        # Promedio (considera no_promediar_sueldo_prestaciones)
        promedio = prestaciones_svc._compute_promedio(localdict, sueldo_info, variable_base, context)

        # Auxilio de transporte
        auxilio = prestaciones_svc._get_auxilio(localdict, 'cesantias', promedio, sueldo_info)

        return self._build_calculo(
            localdict, 'cesantias', params_prestacion,
            sueldo_info, variable_base, promedio, auxilio, context
        )

    def _intcesantias(self, localdict):
        """
        INTERESES DE CESANTIAS - Codigo regla: INTCESANTIAS

        Formula: Cesantias * 12% (CORREGIDO Bug #5)
        IMPORTANTE: Tasa FIJA 12% en liquidacion (Art. 99 Ley 50/1990)

        CORREGIDO Bug #4: En liquidaciones, calcula ajuste (total - provisiones - pagos).

        Returns:
            tuple: (amount, qty, rate, name, log, data)
        """
        slip = localdict['slip']

        # Parametros del concepto INTCESANTIAS (mismo promedio que cesantias)
        promedio_info = self._get_mesesapromediar(localdict, 'intereses')
        params_prestacion = {
            'diasperiodo': 360,
            'diasapagar': 30,
            'mesesapromediar': promedio_info['mesesapromediar'],
            'promediar_salario': promedio_info['promediar_salario'],
            'cambio_salario': promedio_info['cambio_salario'],
            'codigo_provision': 'PRV_ICES',
            'codigo_regla': 'INTCESANTIAS',
        }
        params_prestacion.update(self._get_cuentas_contables('INTCESANTIAS', 'PRV_ICES'))

        # Determinar contexto segun estructura
        struct_process = slip.struct_id.process if slip.struct_id else 'nomina'
        context = 'liquidacion' if struct_process == 'contrato' else 'pago'

        # Sueldo y dias a pagar
        prestaciones_svc = self.env['hr.salary.rule.prestaciones']
        sueldo_info = prestaciones_svc._get_sueldo_dias_a_pagar(localdict, 'intereses')
        variable_base = prestaciones_svc._get_variable_base(localdict, 'intereses')

        # Promedio (considera no_promediar_sueldo_prestaciones)
        promedio = prestaciones_svc._compute_promedio(localdict, sueldo_info, variable_base, context)

        # Auxilio de transporte
        auxilio = prestaciones_svc._get_auxilio(localdict, 'intereses', promedio, sueldo_info)

        return self._build_calculo(
            localdict, 'intereses', params_prestacion,
            sueldo_info, variable_base, promedio, auxilio, context
        )

    def _ces_year(self, localdict):
        """
        CESANTIAS AÑO ANTERIOR - Codigo regla: CES_YEAR

        Liquida cesantias del año anterior cuando no se consignaron al fondo.
        Solo aplica en liquidacion de contrato en enero/febrero.

        Returns:
            tuple: (amount, qty, rate, name, log, data)
        """
        slip = localdict['slip']
        contract = localdict['contract']
        employee = localdict.get('employee')

        # Parametros del concepto CES_YEAR (ano anterior)
        promedio_info = self._get_mesesapromediar(localdict, 'cesantias', ano_anterior=True)
        params_prestacion = {
            'diasperiodo': 360,
            'diasapagar': 30,
            'mesesapromediar': promedio_info['mesesapromediar'],
            'promediar_salario': promedio_info['promediar_salario'],
            'cambio_salario': promedio_info['cambio_salario'],
            'date_from_promedio': str(promedio_info['date_from_promedio']),
            'date_to_promedio': str(promedio_info['date_to_promedio']),
            'codigo_provision': 'PRV_CES',
            'codigo_regla': 'CES_YEAR',
        }
        params_prestacion.update(self._get_cuentas_contables('CES_YEAR', 'PRV_CES'))

        # Solo aplica en liquidacion de contrato
        struct_process = slip.struct_id.process if slip.struct_id else ''
        is_liquidation = struct_process == 'contrato'

        if not is_liquidation:
            return (0, 0, 0, 'No aplica', '', {'aplica': False})

        # Solo en enero/febrero
        is_jan_feb = slip.date_to.month in [1, 2]
        pagar_ano_anterior = getattr(slip, 'pagar_cesantias_ano_anterior', False)

        if not (is_jan_feb and pagar_ano_anterior):
            return (0, 0, 0, 'No aplica', '', {'aplica': False})

        # Fechas del ano anterior
        previous_year = slip.date_to.year - 1
        prev_date_from = date(previous_year, 1, 1)
        prev_date_to = date(previous_year, 12, 31)
        if contract.date_start and contract.date_start > prev_date_from:
            prev_date_from = contract.date_start

        # Sueldo y dias a pagar
        prestaciones_svc = self.env['hr.salary.rule.prestaciones']
        sueldo_info = prestaciones_svc._get_sueldo_dias_a_pagar(localdict, 'cesantias')
        variable_base = prestaciones_svc._get_variable_base(
            localdict, 'cesantias', date_from=prev_date_from, date_to=prev_date_to
        )

        # Promedio (considera no_promediar_sueldo_prestaciones)
        promedio = prestaciones_svc._compute_promedio(localdict, sueldo_info, variable_base, 'liquidacion')

        # Auxilio de transporte
        auxilio = prestaciones_svc._get_auxilio(localdict, 'cesantias', promedio, sueldo_info)

        return self._build_calculo(
            localdict, 'cesantias', params_prestacion,
            sueldo_info, variable_base, promedio, auxilio, 'liquidacion'
        )

    def _intces_year(self, localdict):
        """
        INTERESES CESANTIAS ANO ANTERIOR - Codigo regla: INTCES_YEAR

        Paga intereses sobre cesantias del año anterior.
        Normalmente se pagan antes del 31 de enero.

        Returns:
            tuple: (amount, qty, rate, name, log, data)
        """
        slip = localdict['slip']
        contract = localdict['contract']
        employee = localdict.get('employee')

        # Parametros del concepto INTCES_YEAR (ano anterior)
        promedio_info = self._get_mesesapromediar(localdict, 'intereses', ano_anterior=True)
        params_prestacion = {
            'diasperiodo': 360,
            'diasapagar': 30,
            'mesesapromediar': promedio_info['mesesapromediar'],
            'promediar_salario': promedio_info['promediar_salario'],
            'cambio_salario': promedio_info['cambio_salario'],
            'date_from_promedio': str(promedio_info['date_from_promedio']),
            'date_to_promedio': str(promedio_info['date_to_promedio']),
            'codigo_provision': 'PRV_ICES',
            'codigo_regla': 'INTCES_YEAR',
        }
        params_prestacion.update(self._get_cuentas_contables('INTCES_YEAR', 'PRV_ICES'))

        if contract.modality_salary == 'integral':
            return (0, 0, 0, 'Salario integral', '', {'aplica': False})

        if contract.date_start.year == slip.date_to.year:
            return (0, 0, 0, 'Contrato inicio este año', '', {'aplica': False})

        # Verificar si debe pagarse en nomina
        pay_in_payroll = slip.pay_cesantias_in_payroll
        if not pay_in_payroll:
            return (0, 0, 0, 'No pagar en nomina', '', {'aplica': False})

        # Fechas del ano anterior
        previous_year = slip.date_to.year - 1
        prev_date_from = date(previous_year, 1, 1)
        prev_date_to = date(previous_year, 12, 31)
        if contract.date_start and contract.date_start > prev_date_from:
            prev_date_from = contract.date_start

        # Sueldo y dias a pagar
        prestaciones_svc = self.env['hr.salary.rule.prestaciones']
        sueldo_info = prestaciones_svc._get_sueldo_dias_a_pagar(localdict, 'intereses')
        variable_base = prestaciones_svc._get_variable_base(
            localdict, 'intereses', date_from=prev_date_from, date_to=prev_date_to
        )

        # Promedio (considera no_promediar_sueldo_prestaciones)
        promedio = prestaciones_svc._compute_promedio(localdict, sueldo_info, variable_base, 'liquidacion')

        # Auxilio de transporte
        auxilio = prestaciones_svc._get_auxilio(localdict, 'intereses', promedio, sueldo_info)

        return self._build_calculo(
            localdict, 'intereses', params_prestacion,
            sueldo_info, variable_base, promedio, auxilio, 'liquidacion'
        )

    # =========================================================================
    # DIAS A PROMEDIAR SEGUN CONFIG Y CAMBIOS DE SALARIO
    # =========================================================================

    def _get_mesesapromediar(self, localdict, tipo_prestacion, ano_anterior=False):
        """
        Determina meses a promediar segun tipo, config y cambios de salario.

        Logica:
        - Prima: 6 si prima_salary_take, sino 1 (sueldo actual)
        - Cesantias/Intereses: 3 si cesantias_salary_take, sino 1.
          Si hubo cambio de salario en los ultimos 3 meses, promedia
          todo el año (o desde inicio contrato si empezo en el año).
        - Vacaciones: 12 (ultimo año)
        - ano_anterior=True: calcula sobre el año previo (para CES_YEAR/INTCES_YEAR)

        Args:
            localdict: Diccionario de contexto
            tipo_prestacion: 'prima', 'cesantias', 'intereses', 'vacaciones'
            ano_anterior: Si True, calcula sobre el año anterior

        Returns:
            dict: {mesesapromediar, promediar_salario, cambio_salario,
                   date_from_promedio, date_to_promedio}
        """
        get_param = self.env['ir.config_parameter'].sudo().get_param
        slip = localdict['slip']
        contract = localdict['contract']

        date_ref = slip.date_to
        if ano_anterior:
            # Para ano anterior: diciembre del ano previo
            prev_year = date_ref.year - 1
            date_ref = date(prev_year, 12, 31)

        result = {
            'mesesapromediar': 1,
            'promediar_salario': False,
            'cambio_salario': False,
            'date_from_promedio': date_ref,
            'date_to_promedio': date_ref,
        }

        if tipo_prestacion == 'prima':
            prima_take = str(get_param('lavish_hr_payroll.prima_salary_take', 'False')).lower() in ('true', '1', 'yes')
            if prima_take:
                result['mesesapromediar'] = 6
                result['promediar_salario'] = True
            return result

        if tipo_prestacion in ('cesantias', 'intereses'):
            ces_take = str(get_param('lavish_hr_payroll.cesantias_salary_take', 'False')).lower() in ('true', '1', 'yes')
            if not ces_take:
                return result

            result['promediar_salario'] = True

            # Verificar si hubo cambio de salario en los ultimos 3 meses
            cambio = self._hubo_cambio_salario(contract, date_ref, meses=3)
            result['cambio_salario'] = cambio

            if cambio:
                # Promediar todo el ano (o desde inicio contrato)
                meses = self._meses_en_periodo(contract, date_ref)
                result['mesesapromediar'] = max(meses, 1)
                year = date_ref.year
                inicio_ano = date(year, 1, 1)
                if contract.date_start and contract.date_start > inicio_ano:
                    result['date_from_promedio'] = contract.date_start
                else:
                    result['date_from_promedio'] = inicio_ano
                result['date_to_promedio'] = date_ref
            else:
                result['mesesapromediar'] = 3

            return result

        if tipo_prestacion == 'vacaciones':
            result['mesesapromediar'] = 12
            result['promediar_salario'] = True
            return result

        return result

    def _hubo_cambio_salario(self, contract, date_ref, meses=3):
        """
        Detecta si hubo cambio de salario en los ultimos N meses.

        Usa get_wage_changes_in_period de basic.py que consulta
        contract.change_wage_ids (historial oficial de cambios).

        Args:
            contract: Contrato del empleado
            date_ref: Fecha de referencia
            meses: Cantidad de meses a revisar

        Returns:
            bool: True si hubo cambio de salario
        """
        date_from = date_ref - relativedelta(months=meses)
        cambios = get_wage_changes_in_period(contract, date_from, date_ref)
        return len(cambios) > 0

    def _meses_en_periodo(self, contract, date_ref):
        """
        Calcula meses desde inicio del año (o inicio contrato) hasta date_ref.

        Args:
            contract: Contrato
            date_ref: Fecha de referencia

        Returns:
            int: Meses en el periodo
        """
        year = date_ref.year
        inicio_ano = date(year, 1, 1)

        if contract.date_start and contract.date_start > inicio_ano:
            fecha_inicio = contract.date_start
        else:
            fecha_inicio = inicio_ano

        meses = (date_ref.year - fecha_inicio.year) * 12 + (date_ref.month - fecha_inicio.month) + 1
        return max(meses, 1)

    # =========================================================================
    # CUENTAS CONTABLES
    # =========================================================================

    def _get_cuentas_contables(self, codigo_regla, codigo_provision):
        """
        Obtiene cuenta debito de la regla de prestacion y cuenta credito de la provision.

        Busca en hr.salary.rule.accounting la primera linea contable de cada regla.

        Args:
            codigo_regla: Codigo de la regla salarial (ej: 'PRIMA', 'CESANTIAS')
            codigo_provision: Codigo de la provision (ej: 'PRV_PRIM', 'PRV_CES')

        Returns:
            dict: {cuenta_debito, cuenta_credito, cuenta_debito_code, cuenta_credito_code}
        """
        result = {
            'cuenta_debito': False,
            'cuenta_credito': False,
            'cuenta_debito_code': '',
            'cuenta_credito_code': '',
        }
        SalaryRule = self.env['hr.salary.rule']

        # Cuenta debito: de la regla de prestacion
        regla = SalaryRule.search([('code', '=', codigo_regla)], limit=1)
        if regla and regla.salary_rule_accounting:
            for acc in regla.salary_rule_accounting:
                if acc.debit_account:
                    result['cuenta_debito'] = acc.debit_account.id
                    result['cuenta_debito_code'] = acc.debit_account.code
                    break

        # Cuenta credito: de la regla de provision
        provision = SalaryRule.search([('code', '=', codigo_provision)], limit=1)
        if provision and provision.salary_rule_accounting:
            for acc in provision.salary_rule_accounting:
                if acc.credit_account:
                    result['cuenta_credito'] = acc.credit_account.id
                    result['cuenta_credito_code'] = acc.credit_account.code
                    break

        return result

    # =========================================================================
    # METODOS AUXILIARES PARA PAGOS
    # =========================================================================

    def _build_calculo(self, localdict, tipo_prestacion, params_prestacion,
                       sueldo_info, variable_base, promedio, auxilio, context):
        """
        Devuelve el resultado basado en dias.

        base_mensual = sueldo + promedio + auxilio
        amount = (base_mensual * dias_a_pagar) / dias_periodo

        Args:
            localdict: Diccionario con slip, contract, employee
            tipo_prestacion: 'prima', 'cesantias', 'intereses', 'vacaciones'
            params_prestacion: Dict con diasperiodo, diasapagar, codigo_regla, etc.
            sueldo_info: Dict de _get_sueldo_dias_a_pagar
            variable_base: Dict de _get_variable_base
            promedio: float - promedio de devengos variables (ya excluye BASIC y AUX)
            auxilio: Dict de _get_auxilio
            context: 'liquidacion' | 'pago'

        Returns:
            tuple: (amount, quantity, rate, nombre, '', data)
        """
        # Componentes de la base
        sueldo = sueldo_info.get('sueldo', 0)
        auxilio_valor = auxilio.get('promedio_auxilio', 0) if auxilio.get('aplica') else 0

        # Base = sueldo + promedio + auxilio
        base_mensual = sueldo + promedio + auxilio_valor

        # Dias
        dias_a_pagar = sueldo_info.get('dias_a_pagar', 0)
        dias_periodo = params_prestacion.get('diasperiodo', 360)
        codigo_regla = params_prestacion.get('codigo_regla', '')

        diasapagar_param = params_prestacion.get('diasapagar', 30)

        regla = localdict.get('rule')
        if not regla:
            regla = self.env['hr.salary.rule'].search([('code', '=', codigo_regla)], limit=1)
        if codigo_regla == 'VACCONTRATO' and regla and regla.vaccontrato_sin_factor_15:
            diasapagar_param = 30

        # Formula segun tipo y descomposicion Bitakora para visualizacion
        if tipo_prestacion == 'intereses':
            cesantias_valor = (base_mensual * dias_a_pagar) / 360 if dias_a_pagar else 0
            total = (cesantias_valor * 0.12 * dias_a_pagar) / 360 if dias_a_pagar else 0
            # Descomponer intereses: cesantias × dias × tasa_diaria
            amount_display = cesantias_valor
            qty_display = dias_a_pagar
            rate_display = (total * 100.0) / (cesantias_valor * dias_a_pagar) if cesantias_valor > 0 and dias_a_pagar > 0 else 0
        else:
            total = (base_mensual * dias_a_pagar) / dias_periodo if dias_periodo else 0
            # Descomposicion Bitakora:
            # Salario base diario = base_mensual / 30
            # Dias liquidados = dias_laborados × diasapagar / diasperiodo
            # Total = salario_base_diario × dias_liquidados
            salario_base_diario = base_mensual / 30.0 if base_mensual > 0 else 0
            dias_liquidados = (dias_a_pagar * diasapagar_param) / dias_periodo if dias_periodo > 0 else 0
            amount_display = salario_base_diario
            qty_display = dias_liquidados
            rate_display = 100

        # Nombre descriptivo para la linea de nomina
        _TIPO_NOMBRES = {
            'prima': 'Prima de Servicios',
            'cesantias': 'Cesantías',
            'intereses': 'Int. Cesantías',
            'vacaciones': 'Vacaciones',
        }
        _MESES = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']
        nombre_tipo = _TIPO_NOMBRES.get(tipo_prestacion, tipo_prestacion.upper())
        df = sueldo_info.get('date_from')
        dt = sueldo_info.get('date_to')
        periodo_str = ''
        if df and dt:
            periodo_str = f" {_MESES[df.month - 1]}-{_MESES[dt.month - 1]} {dt.year}"
        if total < 0:
            nombre_linea = f"Ajuste {nombre_tipo}{periodo_str}"
        elif context == 'liquidacion':
            nombre_linea = f"Liquidación {nombre_tipo}{periodo_str}"
        else:
            nombre_linea = f"{nombre_tipo}{periodo_str}"

        # Data para la respuesta
        log_data = crear_log_data(
            'success', 'prestacion',
            tipo_prestacion=tipo_prestacion,
            context=context,
            sueldo=sueldo,
            promedio=promedio,
            auxilio=auxilio_valor,
            base_mensual=base_mensual,
            dias_a_pagar=dias_a_pagar,
            dias_periodo=dias_periodo,
        )

        indicadores = [
            crear_indicador('Sueldo', sueldo, 'primary', 'currency'),
            crear_indicador('Promedio', promedio, 'info', 'currency'),
            crear_indicador('Auxilio', auxilio_valor, 'secondary', 'currency'),
            crear_indicador('Base', base_mensual, 'success', 'currency'),
            crear_indicador('Dias', dias_a_pagar, 'warning', 'number'),
        ]

        pasos = [
            crear_paso_calculo('Sueldo empleado', sueldo),
            crear_paso_calculo('Promedio devengos', promedio),
            crear_paso_calculo('Auxilio transporte', auxilio_valor),
            crear_paso_calculo(
                'Base mensual', base_mensual, highlight=True,
                formula=f'{sueldo:,.0f} + {promedio:,.0f} + {auxilio_valor:,.0f}',
            ),
        ]

        if tipo_prestacion == 'intereses':
            ces_val = (base_mensual * dias_a_pagar) / 360 if dias_a_pagar else 0
            pasos.extend([
                crear_paso_calculo(
                    'Cesantias base', ces_val,
                    formula=f'({base_mensual:,.0f} x {dias_a_pagar}) / 360',
                ),
                crear_paso_calculo(
                    'Intereses (12%)', total, highlight=True,
                    formula=f'({ces_val:,.0f} x 12% x {dias_a_pagar}) / 360',
                    base_legal='Art. 99 Ley 50/1990',
                ),
            ])
        else:
            pasos.extend([
                crear_paso_calculo(
                    'Salario base diario', amount_display,
                    formula=f'{base_mensual:,.0f} / 30',
                ),
                crear_paso_calculo(
                    'Dias liquidados', qty_display,
                    formula=f'{dias_a_pagar} x {diasapagar_param} / {dias_periodo}',
                ),
                crear_paso_calculo(
                    'Total prestacion', total, highlight=True,
                    formula=f'{amount_display:,.2f} x {qty_display:,.4f}',
                ),
            ])

        computation = crear_computation_estandar(
            'prestacion',
            titulo=codigo_regla,
            indicadores=indicadores,
            pasos=pasos,
            datos={
                'sueldo_info': sueldo_info,
                'variable_base': variable_base,
                'auxilio': auxilio,
                'params_prestacion': params_prestacion,
            },
        )

        # data_kpi con keys esperados por el widget JS
        # (PayslipLinePrestacion y PayslipLineProvision)
        slip = localdict['slip']
        variable_details = variable_base.get('details', []) if variable_base else []

        # Enriquecer lineas variable con info de nomina (payslip_id, slip_number, fecha, periodo)
        historic_ids = [
            vl['id'] for vl in variable_details
            if vl.get('id') and vl.get('_name') == 'hr.payslip.line'
        ]
        payslip_map = {}
        if historic_ids:
            try:
                psl_lines = self.env['hr.payslip.line'].browse(historic_ids).exists()
                for psl in psl_lines:
                    if psl.slip_id:
                        df = psl.slip_id.date_from
                        payslip_map[psl.id] = {
                            'payslip_id': psl.slip_id.id,
                            'slip_number': psl.slip_id.number or '',
                            'fecha': str(df) if df else '',
                            'periodo': f"{df.year}-{df.month:02d}" if df else '',
                        }
            except Exception:
                pass

        lineas_base_variable = []
        for vl in variable_details:
            cat_code = (vl.get('categoria', '') or '').upper()
            if cat_code in ('BASIC', 'AUX'):
                continue
            psl_info = payslip_map.get(vl.get('id')) or {}
            es_actual = vl.get('fuente') == 'nomina_actual'
            lineas_base_variable.append({
                'codigo': vl.get('codigo', ''),
                'nombre': vl.get('nombre', ''),
                'total': vl.get('total', 0),
                'valor_usado': vl.get('total', 0),
                'categoria': vl.get('categoria', ''),
                'tipo': vl.get('fuente', 'variable'),
                'quantity': vl.get('cantidad', 0),
                'payslip_id': psl_info.get('payslip_id') or (slip.id if es_actual else None),
                'slip_number': psl_info.get('slip_number') or (slip.number if es_actual else ''),
                'fecha': psl_info.get('fecha') or (str(slip.date_from) if es_actual and slip.date_from else ''),
                'periodo': psl_info.get('periodo') or (
                    f"{slip.date_from.year}-{slip.date_from.month:02d}" if es_actual and slip.date_from else ''
                ),
            })

        # Generar detalle completo para widget (cambios_auxilio, cambios_salario, resumen_dias, etc.)
        detail = {}
        try:
            auxilio_info = auxilio.get('auxilio_info', {}) if auxilio else {}
            modality_aux = auxilio_info.get('modality_aux', 'basico')
            en_variable = modality_aux in ('variable', 'variable_sin_tope')
            calculo_data = {
                'sueldo_info': sueldo_info,
                'variable_base': variable_base,
                'auxilio': auxilio,
                'base_mensual': base_mensual,
                'sueldo': sueldo,
                'promedio': promedio,
                'auxilio_valor': auxilio_valor,
                'context': context,
                'dias_periodo': dias_periodo,
                'dias_a_pagar': dias_a_pagar,
                'amount': total,
                'modality_aux': modality_aux,
                'auxilio_en_variable': en_variable,
                'auxilio_method': 'promedio_variable' if en_variable else 'basico_fijo',
            }
            detail_svc = self.env['hr.salary.rule.prestaciones.detail']
            detail = detail_svc.build_detail_from_calculo(localdict, tipo_prestacion, calculo_data)
            # Usar lineas_base_variable enriquecidas en vez de las del detail
            detail['lineas_base_variable'] = lineas_base_variable
        except Exception as e:
            _logger.warning(f"_build_calculo: Error generando detail: {e}")

        data_kpi = {
            # Keys esperados por el JS (salary_base, salary_variable, subsidy)
            'salary_base': sueldo,
            'salary_variable': promedio,
            'subsidy': auxilio_valor,
            'base_mensual': base_mensual,
            'days_worked': dias_a_pagar,
            'dias_periodo': dias_periodo,
            'dias_pagados': dias_a_pagar,
            'dias_computables': dias_a_pagar,
            # Keys originales (compatibilidad)
            'sueldo': sueldo,
            'promedio': promedio,
            'auxilio': auxilio_valor,
            'tipo_prestacion': tipo_prestacion,
            'context': context,
            # Lineas variables para tabla de conceptos
            'lineas_base_variable': lineas_base_variable,
        }

        # ─── Ajuste por saldo contable en liquidaciones ─────────────────
        # Usa el saldo ya calculado por la regla de provisión (cached en
        # localdict) o hace la consulta contable como fallback.
        if context == 'liquidacion':
            try:
                # 1. Intentar leer saldo cacheado por la regla de provisión
                saldo_contable = localdict.get('_prov_saldos', {}).get(tipo_prestacion)

                # 2. Fallback: consultar contabilidad directamente
                if saldo_contable is None:
                    prov_svc = self.env['hr.salary.rule.prestaciones.provisiones']
                    cuentas_regla = prov_svc._get_cuentas_provision_contables(tipo_prestacion)
                    cuentas_config = prov_svc.CUENTAS_PRESTACIONES.get(tipo_prestacion, {})
                    employee = localdict.get('employee')
                    saldo_contable = prov_svc._get_saldo_cuenta_provision(
                        cuentas_regla, cuentas_config, slip.date_to, employee
                    ) or 0
                    # Cachear para la regla de provisión
                    localdict.setdefault('_prov_saldos', {})[tipo_prestacion] = saldo_contable

                if saldo_contable:
                    total_obligacion = total
                    total = total_obligacion - saldo_contable

                    # Recalcular display: amount * qty * rate / 100 = total
                    if tipo_prestacion == 'intereses':
                        if qty_display and rate_display:
                            amount_display = total * 100.0 / (qty_display * rate_display)
                        else:
                            amount_display, qty_display, rate_display = total, 1, 100
                    else:
                        if qty_display:
                            amount_display = total / qty_display
                        else:
                            amount_display, qty_display, rate_display = total, 1, 100

                    data_kpi['saldo_contable'] = saldo_contable
                    data_kpi['total_obligacion'] = total_obligacion

                    _logger.info(
                        f"[LIQ] {codigo_regla}: obligacion={total_obligacion:,.0f}, "
                        f"saldo_cta={saldo_contable:,.0f}, ajuste={total:,.0f}"
                    )
            except Exception as e:
                _logger.warning(f"[LIQ] Error saldo contable {codigo_regla}: {e}")

        return crear_resultado_regla(
            amount_display, qty_display, rate_display, nombre_linea,
            log_data=log_data,
            data_kpi=data_kpi,
            computation=computation,
            detail=detail,
            aplica=True,
            total=total,
        )

    # =========================================================================
    # VALIDACIONES ESPECIFICAS DE LIQUIDACION
    # =========================================================================

    def _validar_liquidacion(self, localdict):
        """
        Valida que el contexto sea valido para liquidacion.

        Returns:
            dict: {aplica: bool, motivo: str, warnings: list}
        """
        contract = localdict['contract']
        slip = localdict['slip']
        warnings = []

        # Verificar que sea nomina de liquidacion
        # Verificar tipo de proceso desde estructura salarial
        struct_process = slip.struct_id.process if slip.struct_id else ''
        if struct_process != 'contrato':
            warnings.append('Nomina no es de tipo liquidacion (contrato)')

        # Verificar fecha de terminacion
        if not contract.date_end:
            return {
                'aplica': False,
                'motivo': 'Contrato sin fecha de terminacion',
                'warnings': warnings,
            }

        # Verificar estado del contrato
        # Estados validos: open, close, finished (Finalizado Por Liquidar)
        if contract.state not in ('open', 'close', 'finished'):
            return {
                'aplica': False,
                'motivo': f"Contrato en estado '{contract.state}'",
                'warnings': warnings,
            }

        return {'aplica': True, 'motivo': '', 'warnings': warnings}

    def _resultado_no_aplica(self, motivo):
        """
        Retorna resultado vacio con motivo.

        Args:
            motivo: Razon por la que no aplica

        Returns:
            tuple: Resultado con valores en cero
        """
        return (0, 0, 0, motivo, "", {'aplica': False, 'motivo': motivo})
