# -*- coding: utf-8 -*-
from odoo import models, api
from datetime import date, timedelta
import logging

from .config_reglas import days360
from .basic import PrestacionesSueldoComputer, PrestacionesAusenciaComputer

_logger = logging.getLogger(__name__)


def _result_no_aplica(motivo, warnings=None, extra_keys=None):
    """Retorna resultado estandar cuando una prestacion no aplica."""
    result = {
        'aplica': False,
        'motivo': motivo,
        'warnings': warnings or [],
    }
    if extra_keys:
        result.update(extra_keys)
    return result


# =========================================================================
# CLASE BASE Y MIXINS COMPARTIDOS
# =========================================================================

class PrestacionesEnvBase:
    """
    Clase base para servicios que requieren acceso al entorno Odoo (env).

    Centraliza:
    - Inicialización de self.env
    - Lectura de parámetros del sistema (ir.config_parameter)
    - Conversión de string a bool para parámetros de configuración
    """

    def __init__(self, env):
        self.env = env

    def _get_param(self, key, default='False'):
        """Lee un parámetro del sistema (ir.config_parameter)."""
        return self.env['ir.config_parameter'].sudo().get_param(key, default)

    @staticmethod
    def _str_to_bool(value):
        """Convierte string de parámetro a bool ('true', '1', 'yes' → True)."""
        return str(value).lower() in ('true', '1', 'yes')

    def _get_param_bool(self, key, default='False'):
        """Lee un parámetro del sistema y lo convierte a bool."""
        return self._str_to_bool(self._get_param(key, default))

class PromedioComputeMixin:
    """
    Mixin para combinar promedios históricos con datos de la nómina actual.

    Centraliza la lógica idéntica de:
    - PrestacionesDevengosQueryComputer.compute_promedio_con_actual()
    - PrestacionesAuxilioQueryComputer.compute_promedio_con_actual()
    """

    @staticmethod
    def _combine_historico_actual(historico, total_actual, detalle_actual=None):
        """
        Combina resultado histórico SQL con valores de la nómina actual.

        Args:
            historico: dict resultado de compute_promedio()
            total_actual: float - total de la nómina actual
            detalle_actual: dict opcional - detalle por categoría de la nómina actual

        Returns:
            dict: {promedio_mensual, total_acumulado, meses_consultados,
                   tiene_datos, historico, actual}
        """
        total_combinado = historico['total_acumulado'] + total_actual
        meses_combinados = historico['meses_consultados'] + 1
        promedio_combinado = total_combinado / meses_combinados if meses_combinados > 0 else 0.0

        result = {
            'promedio_mensual': promedio_combinado,
            'total_acumulado': total_combinado,
            'meses_consultados': meses_combinados,
            'tiene_datos': meses_combinados > 0,
            'historico': historico,
            'actual': total_actual,
        }

        # Combinar detalle por categoría si se proporcionó
        if detalle_actual is not None:
            detalle_combinado = dict(historico.get('detalle_por_categoria', {}))
            for cat, val in detalle_actual.items():
                detalle_combinado[cat] = detalle_combinado.get(cat, 0.0) + val
            result['detalle_por_categoria'] = detalle_combinado
            result['actual'] = {
                'total': total_actual,
                'detalle': detalle_actual,
            }

        return result

# =========================================================================
# HELPER DE FECHAS PARA PRESTACIONES SOCIALES
# =========================================================================

class PrestacionesDateHelper:
    """
    Helper para computar fechas de periodos de prestaciones sociales.

    Separa la logica de fechas del servicio principal para reutilizacion.

    Metodos:
    - compute_period_dates(): Fechas segun tipo (prima semestral, cesantias anual, etc.)
    - compute_vacation_dates(): Fechas especificas para vacaciones (720 divisor, corte, historial)
    - _adjust_date_to(): Ajusta fecha fin si contrato termina antes del periodo
    """

    @staticmethod
    def _adjust_date_to(date_to, contract):
        """
        Ajusta la fecha de fin si el contrato termina antes del periodo.

        Args:
            date_to: Fecha fin del periodo
            contract: Contrato del empleado

        Returns:
            date: date_to ajustada (la menor entre date_to y contract.date_end)
        """
        if contract.date_end and contract.date_end < date_to:
            return contract.date_end
        return date_to

    @staticmethod
    def compute_period_dates(tipo_prestacion, date_to, contract, slip=None):
        """
        Computa las fechas del periodo segun el tipo de prestacion.

        Periodos:
        - prima: Semestral (Ene-Jun o Jul-Dic)
        - cesantias/intereses: Anual (Ene 1 a fecha corte)
        - vacaciones: Especial (ver compute_vacation_dates)

        Args:
            tipo_prestacion: 'prima', 'cesantias', 'intereses', 'vacaciones'
            date_to: Fecha de corte (slip.date_to o contract.date_end)
            contract: Contrato del empleado
            slip: Nómina (opcional, usado para obtener fechas de liquidación ajustadas)

        Returns:
            dict: {date_from, date_to, tipo_periodo, ...}
        """
        if tipo_prestacion == 'vacaciones':
            return PrestacionesDateHelper.compute_vacation_dates(date_to, contract, slip=slip)

        if tipo_prestacion == 'prima':
            # Semestral: Ene-Jun o Jul-Dic
            if date_to.month <= 6:
                date_from = date(date_to.year, 1, 1)
            else:
                date_from = date(date_to.year, 7, 1)
            tipo_periodo = 'semestral'

        elif tipo_prestacion in ('cesantias', 'intereses'):
            # Anual: Ene 1 a fecha corte
            date_from = date(date_to.year, 1, 1)
            tipo_periodo = 'anual'

        else:
            # Default: anual
            date_from = date(date_to.year, 1, 1)
            tipo_periodo = 'anual'

        # Ajustar si contrato inicio despues del inicio del periodo
        if contract.date_start and contract.date_start > date_from:
            date_from = contract.date_start

        return {
            'date_from': date_from,
            'date_to': PrestacionesDateHelper._adjust_date_to(date_to, contract),
            'tipo_periodo': tipo_periodo,
        }

    @staticmethod
    def compute_vacation_dates(date_to, contract, company=None, slip=None):
        """
        CORREGIDO Bug #7: Computa fechas especificas para provision de vacaciones.

        PRIORIDAD DE FECHAS:
        1. slip.date_vacaciones (fecha de liquidación ajustada/calculada desde históricos) - SIEMPRE SI EXISTE
        2. contract.date_vacaciones (último corte en el contrato) - SI EXISTE
        3. contract.date_start (inicio de contrato)
        4. Enero del año anterior (fallback mínimo)

        IMPORTANTE: La fecha del slip tiene prioridad porque:
        - Puede estar ajustada manualmente por el usuario
        - Se calcula desde históricos (hr.vacation.final_accrual_date + 1 día)
        - Es más confiable para liquidaciones de contrato

        Vacaciones tienen logica diferente al resto de prestaciones:
        - Divisor: 720 (15 dias habiles por año: 360*2)
        - Periodo: Desde inicio contrato o ultimo corte de vacaciones
        - Considerar historial de vacaciones disfrutadas/pagadas
        - Fecha de corte por compañía (si existe configurada)

        Args:
            date_to: Fecha de corte (slip.date_to)
            contract: Contrato del empleado
            company: Compania (opcional, para fecha corte vacaciones)
            slip: Nómina (opcional, para obtener fecha de liquidación ajustada)

        Returns:
            dict: {date_from, date_to, tipo_periodo, vacation_cutoff, date_start_contract}
        """
        vacation_cutoff = None

        # PRIORIDAD 1: Usar fecha de vacaciones del slip si existe (ajustada o desde históricos)
        if slip and slip.date_vacaciones:
            vacation_cutoff = slip.date_vacaciones
            date_from = slip.date_vacaciones

            # Validación: fecha de corte no puede ser posterior a fecha de cálculo
            if slip.date_vacaciones > date_to:
                raise ValueError(
                    f"Fecha corte vacaciones del slip ({slip.date_vacaciones}) "
                    f"no puede ser posterior a fecha de cálculo ({date_to})"
                )
        # PRIORIDAD 2: Usar fecha de vacaciones del contrato si existe
        elif contract.date_vacaciones:
            # Si existe fecha de corte en contrato, USAR (es el último corte legítimo)
            vacation_cutoff = contract.date_vacaciones
            date_from = contract.date_vacaciones

            # Validación: fecha de corte no puede ser posterior a fecha de cálculo
            if contract.date_vacaciones > date_to:
                raise ValueError(
                    f"Fecha corte vacaciones del contrato ({contract.date_vacaciones}) "
                    f"no puede ser posterior a fecha de cálculo ({date_to})"
                )
        # PRIORIDAD 3: Usar inicio de contrato
        elif contract.date_start:
            date_from = contract.date_start
        # PRIORIDAD 4: Fallback - año anterior a la fecha de cálculo
        else:
            # CORREGIDO: NO usar año actual (date_to.year) porque puede dar período muy corto
            date_from = date(date_to.year - 1, 1, 1)

        return {
            'date_from': date_from,
            'date_to': PrestacionesDateHelper._adjust_date_to(date_to, contract),
            'tipo_periodo': 'vacaciones',
            'vacation_cutoff': vacation_cutoff,
            'date_start_contract': contract.date_start,
        }

# =========================================================================
# VALIDADOR DE CONTRATO PARA PRESTACIONES
# =========================================================================

class PrestacionesContratoValidator:
    """
    Valida condiciones del contrato para el calculo de prestaciones.

    Validaciones:
    1. Contrato existe y estado valido
    2. Tipo de contrato tiene la prestacion (has_prima, has_cesantias, etc.)
    3. Aprendiz: has_social_benefits_aprendiz (Ley 2466/2025)
    4. Modalidad salario (basico, integral, sostenimiento, variable)
    5. Salario > 0
    6. Factor integral, fechas, subcontrato, tiempo parcial
    """

    @staticmethod
    def validate(localdict, tipo_prestacion, context='provision', aplicar_factor_integral=False):
        """
        Args:
            localdict: dict con contract, employee, slip, annual_parameters
            tipo_prestacion: 'prima', 'cesantias', 'intereses', 'vacaciones'
            context: 'liquidacion', 'provision', 'consolidacion'
            aplicar_factor_integral: bool - True: aplica 70% (Art. 132 CST), False: 100%

        Returns:
            dict: {aplica, motivo, warnings, contrato_info}
        """
        contract = localdict.get('contract')
        warnings = []

        _extra = {'contrato_info': {}}

        # 1. Contrato existe
        if not contract:
            return _result_no_aplica('Sin contrato', extra_keys=_extra)

        # 2. Estado del contrato segun contexto
        valid_states = ('open', 'close', 'finished')
        if context == 'provision':
            valid_states = ('open',)

        if contract.state not in valid_states:
            return _result_no_aplica(
                f"Contrato en estado '{contract.state}' (validos: {valid_states})",
                extra_keys=_extra,
            )

        # 3. Tipo de contrato - tiene la prestacion
        has_field_map = {
            'prima': 'has_prima',
            'cesantias': 'has_cesantias',
            'intereses': 'has_intereses_cesantias',
            'vacaciones': 'has_vacaciones',
        }
        contract_type = contract.contract_type_id
        if contract_type:
            has_field = has_field_map.get(tipo_prestacion, 'has_prima')
            if not getattr(contract_type, has_field, True):
                return _result_no_aplica(
                    f"Tipo de contrato '{contract_type.name}' no incluye {tipo_prestacion}",
                    extra_keys=_extra,
                )

            # 4. Aprendiz
            if contract_type.is_apprenticeship:
                if not contract_type.has_social_benefits_aprendiz:
                    return _result_no_aplica(
                        'Contrato aprendizaje sin prestaciones sociales',
                        extra_keys=_extra,
                    )
                warnings.append('Contrato de aprendizaje con prestaciones (Ley 2466/2025)')

        # 5. Modalidad de salario
        modality_salary = contract.modality_salary or 'basico'
        es_integral = modality_salary == 'integral'
        es_sostenimiento = modality_salary == 'sostenimiento'

        if es_integral:
            warnings.append('Salario integral: base = 70% del salario')
        if es_sostenimiento:
            warnings.append('Sostenimiento: aprendiz, base segun etapa')

        # 6. Salario > 0
        wage = contract.wage or 0
        if wage <= 0:
            return _result_no_aplica(
                f"Salario del contrato={wage} invalido",
                warnings=warnings, extra_keys=_extra,
            )

        # 7. Factor integral (controlado por bool aplicar_factor_integral)
        factor_integral = 1.0
        if es_integral and aplicar_factor_integral:
            factor_integral = 0.7  # Default: 70% salarial (Art. 132 CST)
            annual_params = localdict.get('annual_parameters')
            if annual_params and annual_params.porc_integral_salary:
                factor_integral = annual_params.porc_integral_salary / 100.0

        # 8. Fechas de contrato
        if not contract.date_start:
            warnings.append('Contrato sin fecha de inicio')
        if context == 'liquidacion' and not contract.date_end:
            warnings.append('Liquidacion: contrato sin fecha de fin')

        # 9. Subcontrato
        subcontract_type = contract.subcontract_type
        if subcontract_type:
            warnings.append(f'Subcontrato tipo: {subcontract_type}')

        # 10. Tiempo parcial
        es_parcial = contract.parcial
        parcial_factor = 1.0
        if es_parcial:
            parcial_factor = contract.factor or 0.5
            warnings.append(f'Tiempo parcial: factor={parcial_factor}')

        contrato_info = {
            'wage': wage,
            'modality_salary': modality_salary,
            'es_integral': es_integral,
            'es_sostenimiento': es_sostenimiento,
            'factor_integral': factor_integral,
            'es_parcial': es_parcial,
            'parcial_factor': parcial_factor,
            'subcontract_type': subcontract_type,
            'date_start': contract.date_start,
            'date_end': contract.date_end,
            'contract_state': contract.state,
        }

        return {
            'aplica': True, 'motivo': '',
            'warnings': warnings, 'contrato_info': contrato_info,
        }

# =========================================================================
# VALIDADOR DE AUXILIO DE TRANSPORTE PARA PRESTACIONES
# =========================================================================

class PrestacionesAuxilioValidator(PrestacionesEnvBase):
    """
    Valida si el auxilio de transporte aplica para la prestacion.

    Campos del contrato evaluados:
    - modality_aux: basico | variable | variable_sin_tope | no
    - not_pay_auxtransportation: bool - desactiva auxilio completamente
    - not_validate_top_auxtransportation: bool - salta validacion tope 2 SMMLV
    - only_wage: wage | wage_dev | wage_dev_exc - base para validar tope
        * wage: Solo salario base del contrato
        * wage_dev: Salario + categoría DEV_SALARIAL
        * wage_dev_exc: Salario + reglas con base_auxtransporte_tope=True
    - tope_aux_method: mes_completo | proporcional - metodo de validacion tope
    - pay_auxtransportation: bool - pagar solo en 2da quincena
    - dev_aux: bool - devolver auxilio si supera tope
    - remote_work_allowance: bool - auxilio de conectividad

    IMPORTANTE - Campos booleanos de hr.salary.rule:
    - es_auxilio_transporte: Marca regla como auxilio (para PROMEDIO prestaciones)
    - base_auxtransporte_tope: INCLUIR regla en VALIDACIÓN TOPE (con only_wage='wage_dev_exc')
    - excluir_auxtransporte_tope: EXCLUIR regla de VALIDACIÓN TOPE (por defecto se usa)

    USO DE CAMPOS SEGÚN CONTEXTO:
    1. Para PROMEDIO en prestaciones:
       - Usar SOLO: categoria AUX + es_auxilio_transporte=True
       - NO usar: base_auxtransporte_tope, excluir_auxtransporte_tope

    2. Para VALIDACIÓN TOPE auxilio (2 SMMLV):
       - excluir_auxtransporte_tope=True → EXCLUIR del cálculo tope
       - base_auxtransporte_tope=True → INCLUIR (solo con only_wage='wage_dev_exc')
       - Categoría DEV_SALARIAL → INCLUIR (solo con only_wage='wage_dev')

    Logica por tipo de prestacion:
    - Prima: incluye auxilio (configurable)
    - Cesantias: incluye auxilio (configurable)
    - Intereses: incluye auxilio (se calcula sobre cesantias que lo incluye)
    - Vacaciones: NO (Art. 186 CST, configurable)

    Logica por modality_aux:
    - basico: Usa valor fijo mensual, valida tope 2 SMMLV
    - variable: Usa lo ya liquidado (promedio periodo), valida tope 2 SMMLV
    - variable_sin_tope: Usa lo ya liquidado, NO valida tope
    - no: No incluye auxilio en prestaciones

    Hereda de PrestacionesEnvBase para acceso a env, _get_param, _str_to_bool.
    """

    def validate(self, localdict, tipo_prestacion, params=None):
        """
        Args:
            localdict: dict con contract, employee, annual_parameters
            tipo_prestacion: 'prima', 'cesantias', 'intereses', 'vacaciones'
            params: dict con parametros ya cargados (incluye_auxilio, etc.)

        Returns:
            dict: {aplica, motivo, warnings, auxilio_info}
        """
        contract = localdict.get('contract')
        employee = localdict.get('employee')
        annual_params = localdict.get('annual_parameters')
        warnings = []
        params = params or {}
        _extra = {'auxilio_info': {}}

        # 1. Vacaciones no lleva auxilio (Art. 186 CST, configurable en paso 2)
        #    Intereses SI aplica auxilio (se calcula sobre cesantias que incluye auxilio)
        if tipo_prestacion == 'vacaciones':
            vac_incluye = self._get_param_bool('lavish_hr_payroll.vacaciones_incluye_auxilio', 'False')
            if not vac_incluye:
                return _result_no_aplica(
                    'Vacaciones no incluye auxilio de transporte (Art. 186 CST)',
                    extra_keys=_extra,
                )

        incluye_auxilio = params.get('incluye_auxilio', False)
        if not incluye_auxilio:
            incluye_map = {
                'prima': 'lavish_hr_payroll.prima_incluye_auxilio',
                'cesantias': 'lavish_hr_payroll.cesantias_incluye_auxilio',
                'intereses': 'lavish_hr_payroll.intereses_incluye_auxilio',
                'vacaciones': 'lavish_hr_payroll.vacaciones_incluye_auxilio',
            }
            defaults = {'prima': True, 'cesantias': True, 'intereses': True, 'vacaciones': False}
            param_key = incluye_map.get(tipo_prestacion, '')
            default_val = defaults.get(tipo_prestacion, False)
            incluye_auxilio = self._get_param_bool(param_key, str(default_val))

        if not incluye_auxilio:
            return _result_no_aplica(
                f'Configuracion: {tipo_prestacion} no incluye auxilio de transporte',
                extra_keys=_extra,
            )

        # 3. Tipo de contrato tiene derecho a auxilio
        if contract.contract_type_id and not contract.contract_type_id.has_auxilio_transporte:
            return _result_no_aplica('Tipo de contrato sin derecho a auxilio de transporte', extra_keys=_extra)

        # 4. Contrato excluye auxilio completamente
        if contract.not_pay_auxtransportation:
            return _result_no_aplica('Contrato marcado: no liquidar auxilio de transporte', extra_keys=_extra)

        # 5. Modalidad auxilio y flags derivados
        modality_aux = contract.modality_aux or 'basico'
        if modality_aux == 'no':
            return _result_no_aplica('Modalidad auxilio configurada como "Sin auxilio"', extra_keys=_extra)

        usar_liquidado = modality_aux in ('variable', 'variable_sin_tope')
        saltar_tope = modality_aux == 'variable_sin_tope'

        if usar_liquidado:
            warnings.append(
                f'Modalidad auxilio={modality_aux}: usa auxilio ya liquidado (promedio periodo)'
            )

        # 6. Salario integral no recibe auxilio
        if (contract.modality_salary or 'basico') == 'integral':
            return _result_no_aplica('Salario integral no recibe auxilio de transporte', extra_keys=_extra)

        # 7. Parametros anuales
        if not annual_params:
            return _result_no_aplica('Sin parametros anuales para calcular auxilio', extra_keys=_extra)

        auxilio_mensual = annual_params.transportation_assistance_monthly or 0
        if auxilio_mensual <= 0:
            return _result_no_aplica('Valor auxilio de transporte mensual=0 en parametros anuales', extra_keys=_extra)

        # 8. Tope 2 SMMLV
        #    Se salta si: variable_sin_tope o not_validate_top_auxtransportation
        smmlv = annual_params.smmlv_monthly or 0
        tope_2smmlv = 2 * smmlv
        wage = contract.wage or 0
        supera_tope = False
        only_wage = contract.only_wage or 'wage'
        tope_aux_method = contract.tope_aux_method or 'mes_completo'

        if saltar_tope:
            warnings.append('variable_sin_tope: no se valida tope 2 SMMLV')
        elif contract.not_validate_top_auxtransportation:
            warnings.append('Contrato excluye validacion de tope 2 SMMLV')
        else:
            if wage >= tope_2smmlv and tope_2smmlv > 0:
                supera_tope = True
                aux_prst = self._get_param_bool('lavish_hr_payroll.aux_prst', 'False')
                if not aux_prst:
                    return _result_no_aplica(
                        f'Salario ({wage:,.0f}) >= 2 SMMLV ({tope_2smmlv:,.0f})',
                        extra_keys=_extra,
                    )
                warnings.append(
                    'Supera 2 SMMLV pero config permite auxilio en prestaciones'
                )

        # 9. Aprendiz: verificar parametros anuales
        if contract.contract_type_id and contract.contract_type_id.is_apprenticeship:
            stage = contract.apprentice_stage
            if not stage and employee and employee.tipo_coti_id:
                stage = 'lectiva' if employee.tipo_coti_id.code == '12' else 'productiva'
            if stage == 'lectiva' and not (annual_params and annual_params.aux_apr_lectiva):
                return _result_no_aplica('Aprendiz lectivo sin auxilio segun parametros anuales', extra_keys=_extra)
            if stage == 'productiva' and not (annual_params and annual_params.aux_apr_prod):
                return _result_no_aplica('Aprendiz productivo sin auxilio segun parametros anuales', extra_keys=_extra)

        # 10. Auxilio de conectividad (informativo)
        es_conectividad = contract.remote_work_allowance
        if es_conectividad:
            warnings.append('Auxilio de conectividad (Ley 2121/2021) en lugar de transporte')

        auxilio_info = {
            'auxilio_mensual': auxilio_mensual,
            'modality_aux': modality_aux,
            'usar_liquidado': usar_liquidado,
            'smmlv': smmlv,
            'tope_2smmlv': tope_2smmlv,
            'supera_tope': supera_tope,
            'only_wage': only_wage,
            'tope_aux_method': tope_aux_method,
            'pay_auxtransportation': contract.pay_auxtransportation,
            'dev_aux': contract.dev_aux,
            'not_validate_top': contract.not_validate_top_auxtransportation,
            'es_conectividad': es_conectividad,
            'metodo_auxilio': params.get('auxilio_metodo', 'dias_trabajados'),
        }

        return {
            'aplica': True, 'motivo': '',
            'warnings': warnings, 'auxilio_info': auxilio_info,
        }

class HrSalaryRulePrestacionesUnified(models.AbstractModel):
    """
    Servicio unificado para calculo de prestaciones sociales.

    Metodos principales:
    - calculate_prestacion(): Calculo unificado para cualquier prestacion
    - get_period(): Obtiene fechas de periodo segun tipo
    - calculate_days(): Calcula dias trabajados menos ausencias
    - calculate_value(): Aplica formula de prestacion
    """
    _name = 'hr.salary.rule.prestaciones'
    _description = 'Prestaciones Sociales'

    def calculate_prestacion(self, localdict, tipo_prestacion, context='provision', provision_type='simple'):
        """
        Calcula la obligacion real de una prestacion al corte.

        Usado por _calculate_consolidacion para obtener el monto que la empresa
        realmente debe al empleado por la prestacion a la fecha de corte.

        Args:
            localdict: Diccionario de contexto (slip, contract, employee, etc.)
            tipo_prestacion: 'prima', 'cesantias', 'intereses', 'vacaciones'
            context: Contexto del calculo ('consolidacion', 'provision', etc.)
            provision_type: 'simple' o 'completa'

        Returns:
            tuple: (base_diaria, dias, porcentaje, nombre, log, detail)
                   detail contiene {'metricas': {'valor_total': X, 'base_mensual': Y, ...}}
        """
        sueldo_info = self._get_sueldo_dias_a_pagar(localdict, tipo_prestacion)
        variable_base = self._get_variable_base(localdict, tipo_prestacion)
        promedio = self._compute_promedio(localdict, sueldo_info, variable_base, context)
        auxilio = self._get_auxilio(localdict, tipo_prestacion, promedio, sueldo_info)
        auxilio_valor = auxilio.get('promedio_auxilio', 0) if auxilio.get('aplica') else 0

        sueldo = sueldo_info.get('sueldo', 0)
        base_mensual = sueldo + promedio + auxilio_valor
        dias_a_pagar = sueldo_info.get('dias_a_pagar', 0)

        divisores = {'prima': 360, 'cesantias': 360, 'intereses': 360, 'vacaciones': 720}
        divisor = divisores.get(tipo_prestacion, 360)

        if tipo_prestacion == 'intereses':
            cesantias_valor = (base_mensual * dias_a_pagar) / 360 if dias_a_pagar else 0
            valor_total = (cesantias_valor * 0.12 * dias_a_pagar) / 360 if dias_a_pagar else 0
        else:
            valor_total = (base_mensual * dias_a_pagar) / divisor if divisor else 0

        base_diaria = base_mensual / 30.0 if base_mensual > 0 else 0

        detail = {
            'aplica': True,
            'metricas': {
                'valor_total': valor_total,
                'base_mensual': base_mensual,
                'base_diaria': base_diaria,
                'dias_trabajados': dias_a_pagar,
                'sueldo': sueldo,
                'promedio': promedio,
                'auxilio': auxilio_valor,
            },
        }

        return (base_diaria, dias_a_pagar, 100, tipo_prestacion, '', detail)

    def _get_sueldo_dias_a_pagar(self, localdict, tipo_prestacion):
        """
        Obtiene sueldo base (contract.wage) y dias a pagar para una prestacion.

        Usa PrestacionesAusenciaComputer para calcular ausencias que descuentan
        y PrestacionesDateHelper para obtener fechas del periodo.

        Args:
            localdict: Diccionario de contexto (slip, contract, employee, etc.)
            tipo_prestacion: 'prima', 'cesantias', 'intereses', 'vacaciones'

        Returns:
            dict: {
                sueldo, dias_a_pagar, dias_periodo,
                dias_ausencias_no_pago, dias_descuento_bonus,
                dias_ausencias_general (informativo),
                detalle_ausencias, date_from, date_to
            }
        """
        slip = localdict['slip']
        contract = localdict['contract']

        sueldo = contract.wage or 0.0

        # Fechas del periodo segun tipo de prestacion
        period = PrestacionesDateHelper.compute_period_dates(
            tipo_prestacion, slip.date_to, contract, slip=slip
        )
        date_from = period.get('date_from', slip.date_from)
        date_to = period.get('date_to', slip.date_to)

        # Dias del periodo (metodo comercial 360)
        dias_periodo = days360(date_from, date_to)

        # Ausencias que descuentan (no pago + bonus)
        ausencia_computer = PrestacionesAusenciaComputer(self.env)
        ausencias = ausencia_computer.compute(
            slip, contract, date_from, date_to, tipo_prestacion
        )

        dias_ausencias_no_pago = ausencias.get('dias_ausencias_no_pago', 0)
        dias_descuento_bonus = ausencias.get('dias_descuento_bonus', 0)
        dias_ausencias_total = ausencias.get('dias_ausencias_total', 0)
        detalle_ausencias = ausencias.get('detalle_ausencias', [])

        # Ausencias generales (informativo - todas las validadas del periodo)
        dias_ausencias_general = self._get_dias_ausencias_general(
            contract, date_from, date_to
        )

        # Dias a pagar = periodo - ausencias que descuentan
        dias_a_pagar = max(0, dias_periodo - dias_ausencias_total)

        return {
            'sueldo': sueldo,
            'dias_a_pagar': dias_a_pagar,
            'dias_periodo': dias_periodo,
            'dias_ausencias_no_pago': dias_ausencias_no_pago,
            'dias_descuento_bonus': dias_descuento_bonus,
            'dias_ausencias_general': dias_ausencias_general,
            'detalle_ausencias': detalle_ausencias,
            'date_from': date_from,
            'date_to': date_to,
        }

    def _get_dias_ausencias_general(self, contract, date_from, date_to):
        try:
            _sp = self.env.cr.savepoint(flush=False)
            try:
                result = self.env['hr.leave.line'].search_count([
                    ('payslip_id.contract_id', '=', contract.id),
                    ('date', '>=', date_from),
                    ('date', '<=', date_to),
                    ('leave_id.state', '=', 'validate'),
                    ('leave_id.holiday_status_id.unpaid_absences', '=', False),
                    ('leave_id.holiday_status_id.discounting_bonus_days', '=', False),
                ])
            except Exception:
                try:
                    _sp.rollback()
                except Exception:
                    pass
                _sp.closed = True
                raise
            else:
                try:
                    _sp.close(rollback=False)
                except Exception:
                    _sp.closed = True
                return result
        except Exception as e:
            _logger.warning(f"_get_dias_ausencias_general: error: {e}")
            return 0

    def _get_variable_base(self, localdict, tipo_prestacion, date_from=None, date_to=None):
        """
        Obtiene lineas de nomina y acumulados que hacen base para la prestacion.

        Filtra por el campo booleano de hr.salary.rule segun tipo
        (base_prima, base_cesantias, base_intereses_cesantias, base_vacaciones).

        No promedia ni calcula, solo devuelve las lineas tal cual.

        Args:
            localdict: Diccionario de contexto (slip, contract, etc.)
            tipo_prestacion: 'prima', 'cesantias', 'intereses', 'vacaciones'
            date_from: Fecha inicio (opcional, si no se pasa usa PrestacionesDateHelper)
            date_to: Fecha fin (opcional, si no se pasa usa PrestacionesDateHelper)

        Returns:
            dict: {
                total_amount: float,
                details: list[dict] con codigo, cantidad, total, id, _name, nombre,
                warnings: list
            }
        """
        slip = localdict['slip']
        contract = localdict['contract']

        # Campo booleano segun tipo
        FIELD_MAP = {
            'prima': 'base_prima',
            'cesantias': 'base_cesantias',
            'intereses': 'base_intereses_cesantias',
            'vacaciones': 'base_vacaciones',
        }
        field_bool = FIELD_MAP.get(tipo_prestacion)
        if not field_bool:
            return {'total_amount': 0.0, 'details': [], 'warnings': []}

        # Fechas del periodo (usar las pasadas o calcular)
        if not date_from or not date_to:
            period = PrestacionesDateHelper.compute_period_dates(
                tipo_prestacion, slip.date_to, contract, slip=slip
            )
            date_from = date_from or period.get('date_from', slip.date_from)
            date_to = date_to or period.get('date_to', slip.date_to)

        details = []

        # 1. Lineas de nomina del periodo (hr.payslip.line) - excluir slip actual
        payslip_lines = self.env['hr.payslip.line'].search([
            ('slip_id.contract_id', '=', contract.id),
            ('slip_id.date_from', '>=', date_from),
            ('slip_id.date_to', '<=', date_to),
            ('slip_id.state', 'in', ['done', 'paid']),
            ('slip_id', '!=', slip.id),
            (field_bool, '=', True),
            ('total', '!=', 0),
        ])
        for line in payslip_lines:
            details.append({
                'codigo': line.salary_rule_id.code if line.salary_rule_id else '',
                'categoria': line.category_id.code if line.category_id else '',
                'cantidad': line.quantity or 1,
                'total': line.total or 0,
                'id': line.id,
                '_name': 'hr.payslip.line',
                'nombre': line.salary_rule_id.name if line.salary_rule_id else '',
                'fuente': 'historico',
            })

        # 2. Nomina actual: reglas ya computadas en localdict['rules']
        #    Filtrar por campo base correspondiente, ignorar novedades (has_leave)
        rules_current = localdict.get('rules', {})
        for code, rule_data in (rules_current.items() if hasattr(rules_current, 'items') else []):
            rule = rule_data.rule if hasattr(rule_data, 'rule') else None
            if not rule:
                continue
            # Ignorar novedades/ausencias
            has_leave = getattr(rule_data, 'has_leave', False)
            if has_leave:
                continue
            # Verificar campo base (base_prima, base_cesantias, etc.)
            if not getattr(rule, field_bool, False):
                continue
            rule_total = rule_data.total if hasattr(rule_data, 'total') else 0
            if rule_total == 0:
                continue
            cat_code = ''
            if rule.category_id:
                cat_code = rule.category_id.code
            details.append({
                'codigo': code,
                'categoria': cat_code,
                'cantidad': getattr(rule_data, 'quantity', 1) or 1,
                'total': rule_total,
                'id': None,
                '_name': 'hr.payslip.line.current',
                'nombre': rule.name or '',
                'fuente': 'nomina_actual',
            })

        # 3. Acumulados del periodo (hr.accumulated.payroll)
        accumulated = self.env['hr.accumulated.payroll'].search([
            ('contract_id', '=', contract.id),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('amount', '!=', 0),
            ('salary_rule_id.' + field_bool, '=', True),
        ])
        for acc in accumulated:
            details.append({
                'codigo': acc.salary_rule_id.code if acc.salary_rule_id else '',
                'categoria': acc.salary_rule_id.category_id.code if acc.salary_rule_id and acc.salary_rule_id.category_id else '',
                'cantidad': acc.quantity if acc.quantity else 1,
                'total': acc.amount or 0,
                'id': acc.id,
                '_name': 'hr.accumulated.payroll',
                'nombre': acc.salary_rule_id.name if acc.salary_rule_id else '',
                'fuente': 'acumulado',
            })

        total_amount = sum(d.get('total', 0) for d in details)

        # Promediar: (total / dias_trabajados) * 30
        dias_trabajados = days360(date_from, date_to)
        if dias_trabajados > 0:
            promedio_mensual = (total_amount / dias_trabajados) * 30
        else:
            promedio_mensual = 0.0

        return {
            'total_amount': total_amount,
            'promedio_mensual': promedio_mensual,
            'dias_trabajados': dias_trabajados,
            'details': details,
            'warnings': [],
        }

    def _get_auxilio(self, localdict, tipo_prestacion, promedio, sueldo_info):
        """
        Valida condiciones de auxilio de transporte para prestaciones.

        Usa PrestacionesAuxilioValidator para validar todas las condiciones:
        - Config (prima_incluye_auxilio, cesantias_incluye_auxilio, etc.)
        - Tipo de contrato, modalidad auxilio, salario integral
        - Tope 2 SMMLV segun only_wage:
            * wage: solo sueldo
            * wage_dev: sueldo + promedio (variable_base general)
            * wage_dev_exc: sueldo + promedio de reglas con base_auxtransporte_tope=True
        - Parametros anuales (transportation_assistance_monthly)

        Para modality_aux='variable' o 'variable_sin_tope', consulta:
        - Lineas historicas de auxilio (hr.payslip.line done/paid)
        - Lineas de auxilio de la nomina actual (localdict['rules'])

        Args:
            localdict: Diccionario de contexto (slip, contract, employee, annual_parameters, rules)
            tipo_prestacion: 'prima', 'cesantias', 'intereses', 'vacaciones'
            promedio: float - promedio mensual (variable_base.total_amount / dias) * 30
            sueldo_info: dict - resultado de _get_sueldo_dias_a_pagar con:
                sueldo, dias_a_pagar, dias_periodo, date_from, date_to, etc.

        Returns:
            dict: {
                aplica: bool,
                motivo: str (razon si no aplica),
                warnings: list,
                auxilio_info: dict con smmlv, tope_2smmlv, auxilio_mensual, base_tope, etc.,
                lineas_auxilio: list[dict] con historico + nomina actual de lineas de auxilio,
                total_auxilio: float - total auxilio del periodo,
                promedio_auxilio: float - promedio mensual del auxilio,
            }
        """
        _empty_auxilio = {'lineas_auxilio': [], 'total_auxilio': 0.0, 'promedio_auxilio': 0.0}

        validator = PrestacionesAuxilioValidator(self.env)
        result = validator.validate(localdict, tipo_prestacion)

        if not result.get('aplica'):
            result.update(_empty_auxilio)
            return result

        # Extraer datos de sueldo_info
        sueldo = sueldo_info.get('sueldo', 0)
        dias_trabajados = sueldo_info.get('dias_a_pagar', 0)

        contract = localdict['contract']
        auxilio_info = result.get('auxilio_info', {})
        tope_2smmlv = auxilio_info.get('tope_2smmlv', 0)
        only_wage = auxilio_info.get('only_wage', 'wage')
        modality_aux = auxilio_info.get('modality_aux', 'basico')
        saltar_tope = auxilio_info.get('not_validate_top', False)

        # =====================================================================
        # CALCULAR BASE TOPE segun only_wage
        # =====================================================================
        # wage: solo sueldo
        # wage_dev: sueldo + promedio general (variable_base)
        # wage_dev_exc: sueldo + promedio solo de reglas con base_auxtransporte_tope=True
        if only_wage == 'wage':
            base_tope = sueldo
        elif only_wage == 'wage_dev':
            base_tope = sueldo + promedio
        elif only_wage == 'wage_dev_exc':
            # Promedio solo de reglas marcadas con base_auxtransporte_tope=True
            promedio_marcadas = self._get_promedio_reglas_tope(localdict, sueldo_info)
            base_tope = sueldo + promedio_marcadas
        else:
            base_tope = sueldo

        # Aplicar tope_aux_method para liquidacion de contrato
        # mes_completo: usa base_tope completa (incluso si < 30 dias en liquidacion)
        # proporcional: ajusta base_tope segun dias trabajados / 30
        tope_aux_method = auxilio_info.get('tope_aux_method', 'mes_completo')
        base_tope_original = base_tope

        if tope_aux_method == 'proporcional' and dias_trabajados < 30 and dias_trabajados > 0:
            base_tope = base_tope * (dias_trabajados / 30.0)

        auxilio_info['base_tope'] = base_tope
        auxilio_info['base_tope_original'] = base_tope_original
        auxilio_info['only_wage_usado'] = only_wage
        auxilio_info['tope_aux_method_usado'] = tope_aux_method

        # =====================================================================
        # VALIDAR TOPE 2 SMMLV
        # =====================================================================
        if tope_2smmlv > 0 and base_tope >= tope_2smmlv:
            if modality_aux == 'variable_sin_tope' or saltar_tope:
                result.setdefault('warnings', []).append(
                    f'Base tope ({base_tope:,.0f}) >= 2 SMMLV ({tope_2smmlv:,.0f}) '
                    f'pero se salta tope (only_wage={only_wage})'
                )
            else:
                aux_prst = self.env['ir.config_parameter'].sudo().get_param(
                    'lavish_hr_payroll.aux_prst', 'False'
                )
                if str(aux_prst).lower() not in ('true', '1', 'yes'):
                    no_aplica = _result_no_aplica(
                        f'Base tope ({base_tope:,.0f}) >= 2 SMMLV ({tope_2smmlv:,.0f}) '
                        f'[only_wage={only_wage}, metodo={tope_aux_method}, '
                        f'sueldo={sueldo:,.0f}, promedio={promedio:,.0f}]',
                        extra_keys={'auxilio_info': auxilio_info},
                    )
                    no_aplica.update(_empty_auxilio)
                    return no_aplica
                result.setdefault('warnings', []).append(
                    f'Base tope supera 2 SMMLV pero config permite auxilio en prestaciones'
                )

        # Agregar datos al auxilio_info
        auxilio_info['sueldo'] = sueldo
        auxilio_info['promedio'] = promedio
        auxilio_info['dias_trabajados'] = dias_trabajados
        auxilio_info['base_tope_supera'] = base_tope >= tope_2smmlv if tope_2smmlv > 0 else False

        # =====================================================================
        # CONSULTAR LINEAS DE AUXILIO: HISTORICO + NOMINA ACTUAL
        # =====================================================================
        slip = localdict['slip']
        period = PrestacionesDateHelper.compute_period_dates(
            tipo_prestacion, slip.date_to, contract, slip=slip
        )
        date_from = period.get('date_from', slip.date_from)
        date_to = period.get('date_to', slip.date_to)

        lineas_auxilio = []
        total_auxilio = 0.0

        force_full_aux = bool(getattr(slip, 'force_auxilio_full_days', False)) and tipo_prestacion in ('prima', 'cesantias')
        if force_full_aux:
            _ap_cache = {}

            def _get_auxilio_mensual_for_date(dt):
                if not dt:
                    return 0.0
                key = (dt.year, contract.company_id.id if contract and contract.company_id else None)
                if key in _ap_cache:
                    return _ap_cache[key]
                ap = self.env['hr.annual.parameters'].get_for_year(
                    dt.year,
                    company_id=key[1],
                    raise_if_not_found=False,
                )
                val = ap.transportation_assistance_monthly if ap else 0.0
                _ap_cache[key] = val
                return val

        # 1. Historico: lineas de auxilio de nominas confirmadas (done/paid)
        aux_lines = self.env['hr.payslip.line'].search([
            ('slip_id.contract_id', '=', contract.id),
            ('slip_id.date_from', '>=', date_from),
            ('slip_id.date_to', '<=', date_to),
            ('slip_id.state', 'in', ['done', 'paid']),
            ('slip_id', '!=', slip.id),
            ('total', '!=', 0),
            '|',
            ('salary_rule_id.es_auxilio_transporte', '=', True),
            ('category_id.code', '=', 'AUX'),
        ])
        vac_slip_ids = set()
        if force_full_aux:
            aux_line_slip_ids = {line.slip_id.id for line in aux_lines if line.slip_id}
            if aux_line_slip_ids:
                vac_worked = self.env['hr.payslip.worked_days'].search_read(
                    [
                        ('payslip_id', 'in', list(aux_line_slip_ids)),
                        ('code', '=', 'VACDISFRUTADAS'),
                        ('number_of_days', '>', 0),
                    ],
                    ['payslip_id'],
                )
                vac_slip_ids = {l['payslip_id'][0] for l in vac_worked if l.get('payslip_id')}
        for line in aux_lines:
            force_line = force_full_aux and (line.slip_id.id in vac_slip_ids)
            if force_line:
                aux_mensual = _get_auxilio_mensual_for_date(line.slip_id.date_from)
                line_total = aux_mensual if aux_mensual else (line.total or 0)
                line_qty = 30
            else:
                line_total = line.total or 0
                line_qty = line.quantity or 1
            lineas_auxilio.append({
                'codigo': line.salary_rule_id.code if line.salary_rule_id else '',
                'nombre': line.salary_rule_id.name if line.salary_rule_id else '',
                'cantidad': line_qty,
                'total': line_total,
                'id': line.id,
                '_name': 'hr.payslip.line',
                'slip_id': line.slip_id.id,
                'slip_number': line.slip_id.number or '',
                'date_from': str(line.slip_id.date_from) if line.slip_id.date_from else '',
                'fuente': 'historico',
            })
            total_auxilio += line_total

        # 2. Nomina actual: lineas de auxilio del slip actual (rules en localdict)
        rules_current = localdict.get('rules', {})
        has_vac_current = False
        if force_full_aux:
            worked_days = localdict.get('worked_days', {}) or {}
            wd = worked_days.get('VACDISFRUTADAS')
            if wd and getattr(wd, 'number_of_days', 0):
                has_vac_current = True
        for code, rule_data in rules_current.items():
            rule = rule_data.rule if hasattr(rule_data, 'rule') else None
            if not rule:
                continue
            es_auxilio = False
            if rule.es_auxilio_transporte:
                es_auxilio = True
            elif rule.category_id:
                cat = rule.category_id
                if cat.code == 'AUX' or (cat.parent_id and cat.parent_id.code == 'AUX'):
                    es_auxilio = True
            if es_auxilio and (rule_data.total or 0) != 0:
                if force_full_aux and has_vac_current:
                    aux_mensual = _get_auxilio_mensual_for_date(slip.date_from)
                    rule_total = aux_mensual if aux_mensual else (rule_data.total or 0)
                    rule_qty = 30
                else:
                    rule_total = rule_data.total or 0
                    rule_qty = rule_data.quantity or 1
                lineas_auxilio.append({
                    'codigo': code,
                    'nombre': rule.name or '',
                    'cantidad': rule_qty,
                    'total': rule_total,
                    'id': None,
                    '_name': 'hr.payslip.line.current',
                    'slip_id': slip.id,
                    'slip_number': slip.number or '',
                    'date_from': str(slip.date_from) if slip.date_from else '',
                    'fuente': 'nomina_actual',
                })
                total_auxilio += rule_total

        # Promedio mensual del auxilio
        if dias_trabajados > 0:
            promedio_auxilio = (total_auxilio / dias_trabajados) * 30
        else:
            promedio_auxilio = 0.0

        result['auxilio_info'] = auxilio_info
        result['lineas_auxilio'] = lineas_auxilio
        result['total_auxilio'] = total_auxilio
        result['promedio_auxilio'] = promedio_auxilio

        return result

    def _get_promedio_reglas_tope(self, localdict, sueldo_info):
        """
        Calcula promedio mensual solo de reglas marcadas con base_auxtransporte_tope=True.

        Se usa cuando only_wage='wage_dev_exc' para la validacion del tope 2 SMMLV.
        Busca en historico (hr.payslip.line) + nomina actual (localdict['rules']).

        Args:
            localdict: Diccionario de contexto
            sueldo_info: dict con date_from, date_to, dias_a_pagar

        Returns:
            float: promedio mensual de reglas marcadas
        """
        slip = localdict['slip']
        contract = localdict['contract']
        dias_trabajados = sueldo_info.get('dias_a_pagar', 0)
        date_from = sueldo_info.get('date_from', slip.date_from)
        date_to = sueldo_info.get('date_to', slip.date_to)

        total_marcadas = 0.0

        # 1. Historico: lineas con base_auxtransporte_tope=True (done/paid)
        marcadas_lines = self.env['hr.payslip.line'].search([
            ('slip_id.contract_id', '=', contract.id),
            ('slip_id.date_from', '>=', date_from),
            ('slip_id.date_to', '<=', date_to),
            ('slip_id.state', 'in', ['done', 'paid']),
            ('slip_id', '!=', slip.id),
            ('salary_rule_id.base_auxtransporte_tope', '=', True),
            ('total', '!=', 0),
        ])
        for line in marcadas_lines:
            total_marcadas += line.total or 0

        # 2. Nomina actual: reglas con base_auxtransporte_tope=True
        rules_current = localdict.get('rules', {})
        for code, rule_data in rules_current.items():
            rule = rule_data.rule if hasattr(rule_data, 'rule') else None
            if rule and rule.base_auxtransporte_tope and (rule_data.total or 0) != 0:
                total_marcadas += rule_data.total or 0

        # Promediar: (total / dias) * 30
        if dias_trabajados > 0:
            return (total_marcadas / dias_trabajados) * 30
        return 0.0

    def _compute_promedio(self, localdict, sueldo_info, variable_base, context):
        """
        Promedio mensual de devengos variables para prestaciones.

        Siempre excluye BASIC y AUX porque:
        - BASIC (sueldo) se suma por separado en _build_calculo
        - AUX (auxilio) se suma por separado en _build_calculo
        Solo promedia componentes variables (comisiones, extras, bonos, etc.)
        """
        dias = sueldo_info.get('dias_a_pagar', 0)
        if dias <= 0:
            return 0.0

        variable_only = sum(
            d.get('total', 0) for d in variable_base.get('details', [])
            if d.get('categoria') not in ('BASIC', 'AUX')
        )
        return (variable_only / dias) * 30
