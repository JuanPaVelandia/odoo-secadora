# -*- coding: utf-8 -*-

"""
REGLAS SALARIALES - AUXILIOS
=============================

Métodos para cálculo de auxilios de transporte y conectividad
"""

import logging
from odoo import models

from datetime import timedelta
from .config_reglas import (
    crear_log_data, crear_resultado_regla, crear_resultado_vacio,
    crear_computation_estandar, crear_indicador, crear_paso_calculo
)

_logger = logging.getLogger(__name__)


class HrSalaryRuleAux(models.AbstractModel):
    """Mixin para reglas de auxilios (transporte/conectividad)."""


    _name = 'hr.salary.rule.aux'
    _description = 'Métodos para Reglas de Auxilios'

    def _get_auxilio_config(self, tipo_auxilio, annual_parameters, is_devolucion=False):
        """Obtiene la configuración del auxilio según su tipo"""
        auxilio_configs = {
            'transporte': {
                'name': 'DEVOLUCION AUXILIO DE TRANSPORTE' if is_devolucion else 'AUXILIO DE TRANSPORTE',
                'monthly_value': annual_parameters.transportation_assistance_monthly if annual_parameters else 0,
                'salary_limit': 2 * annual_parameters.smmlv_monthly if annual_parameters else 0,
            },
            'conectividad': {
                'name': 'DEVOLUCION AUXILIO DE CONECTIVIDAD' if is_devolucion else 'AUXILIO DE CONECTIVIDAD',
                'monthly_value': annual_parameters.value_auxilio_conectividad if annual_parameters else 0,
                'salary_limit': annual_parameters.top_max_auxilio_conectividad if annual_parameters else 0,
            }
        }
        return auxilio_configs.get(tipo_auxilio, auxilio_configs['transporte'])

    def _get_auxilio_previo(self, localdict, codigo_auxilio):
        """Obtiene el valor del auxilio pagado en la primera quincena del mes"""
        slip = localdict['slip']
        start_date = slip.date_from.replace(day=1)
        end_date = slip.date_from - timedelta(days=1)

        accumulated = slip._get_concepts_accumulated_by_payslip(start_date, end_date, concept_codes=[codigo_auxilio])

        if codigo_auxilio in accumulated:
            concept_data = accumulated[codigo_auxilio]
            return {
                'encontrado': True,
                'valor': concept_data.get('total', 0),
                'dias': concept_data.get('quantity', 0)
            }

        return {'encontrado': False, 'valor': 0, 'dias': 0}

    def _obtener_auxilio_linea_nomina(self, slip, dias_periodo=30):
        """
        Obtiene el auxilio de transporte desde las lineas de nomina.

        Busca lineas de categoria AUX o con campo es_auxilio_transporte=True.
        También busca por nombre de la línea que contenga "AUXILIO DE TRANSPORTE".

        Args:
            slip: Objeto hr.payslip
            dias_periodo: Dias del periodo (para calcular proporcion)

        Returns:
            dict: {
                'auxilio': float - Valor del auxilio de la linea,
                'auxilio_mensual': float - Valor mensual estimado,
                'dias_auxilio': float - Dias de auxilio pagados (quantity de la linea),
                'encontrado': bool - Si se encontro linea de auxilio,
                'codigo': str - Codigo de la linea encontrada
            }
        """
        auxilio_total = 0.0
        dias_auxilio = 0.0
        codigo_encontrado = None
        razon = ''

        for line in slip.line_ids:
            es_auxilio = False

            if line.category_id:
                cat = line.category_id
                if cat.code == 'AUX':
                    es_auxilio = True
                    razon = f'categoria AUX (code={cat.code})'
                elif cat.parent_id and cat.parent_id.code == 'AUX':
                    es_auxilio = True
                    razon = f'categoria padre AUX (parent={cat.parent_id.code})'

            if not es_auxilio and line.salary_rule_id and line.salary_rule_id.es_auxilio_transporte:
                es_auxilio = True
                razon = 'es_auxilio_transporte=True'

            if es_auxilio:
                auxilio_total += abs(line.total or 0)
                dias_auxilio += abs(line.quantity or 0)
                codigo_encontrado = line.code

        if auxilio_total > 0:
            auxilio_mensual = (auxilio_total / dias_auxilio * 30) if 0 < dias_auxilio < 30 else auxilio_total
            return {
                'auxilio': auxilio_total,
                'auxilio_mensual': auxilio_mensual,
                'dias_auxilio': dias_auxilio,
                'encontrado': True,
                'codigo': codigo_encontrado,
                'razon': razon,
            }
        return {
            'auxilio': 0,
            'auxilio_mensual': 0,
            'dias_auxilio': 0,
            'encontrado': False,
            'codigo': '',
            'razon': razon,
        }



    def compute_auxilio(self, metodo_auxilio, annual_parameters, contract, dias_pagados, dias_periodo=30,
                        dias_ausencias_no_justificadas=0, date_from=None, date_to=None,
                        exclude_payslip_id=None, es_provision_simple=False, slip=None):
        """Calcula auxilio según método (nómina o días trabajados)."""
        metodo = metodo_auxilio or 'dias_trabajados'
        return self._calcular_auxilio_provision(
            annual_parameters,
            contract,
            dias_pagados,
            dias_periodo=dias_periodo,
            dias_ausencias_no_justificadas=dias_ausencias_no_justificadas,
            date_from=date_from,
            date_to=date_to,
            exclude_payslip_id=exclude_payslip_id,
            es_provision_simple=es_provision_simple,
            metodo_auxilio=metodo,
            slip=slip,
        )

    def _calcular_auxilio_provision(self, annual_parameters, contract, dias_pagados, dias_periodo=30,
                                       dias_ausencias_no_justificadas=0, date_from=None, date_to=None,
                                       exclude_payslip_id=None, es_provision_simple=False,
                                       metodo_auxilio=None, slip=None):
        """Calcula auxilio de transporte según modalidad y método."""
        if not annual_parameters:
            return {
                'auxilio': 0, 'auxilio_mensual': 0, 'modality_aux': 'no',
                'proporcion': 0, 'dias_usados': 0, 'dias_descontados': 0
            }


        auxilio_mensual = annual_parameters.transportation_assistance_monthly or 0
        modality_aux = contract.modality_aux or 'basico'
        if metodo_auxilio is None:
            metodo_auxilio = 'dias_trabajados'

        if modality_aux == 'no':
            return {
                'auxilio': 0, 'auxilio_mensual': auxilio_mensual, 'modality_aux': 'no',
                'proporcion': 0, 'dias_usados': 0, 'dias_descontados': 0
            }

        if metodo_auxilio == 'nomina':
            auxilio_linea = None
            if slip:
                auxilio_linea = self._obtener_auxilio_linea_nomina(slip, dias_periodo)
                if auxilio_linea.get('encontrado'):
                    dias_usados = auxilio_linea.get('dias_auxilio', dias_pagados)
                    auxilio_mensual_linea = auxilio_linea.get('auxilio_mensual', 0) or auxilio_mensual
                    proporcion = (
                        auxilio_linea['auxilio'] / auxilio_mensual_linea
                        if auxilio_mensual_linea > 0 else 0
                    )
                    dias_descontados = max(0, dias_periodo - dias_usados)
                    return {
                        'auxilio': auxilio_linea['auxilio'],
                        'auxilio_mensual': auxilio_mensual_linea,
                        'modality_aux': modality_aux,
                        'proporcion': proporcion,
                        'dias_usados': dias_usados,
                        'dias_descontados': dias_descontados,
                        'metodo': 'nomina_linea',
                        'fuente': 'linea_nomina',
                        'codigo_linea': auxilio_linea.get('codigo', '')
                    }

            promedio_auxilio = 0.0
            periodos_consultados = 0
            promedio_dias_auxilio = 0.0
            if date_from and date_to:
                query_service = self.env['period.payslip.query.service']
                result = query_service.get_auxilio_transporte_pagado(
                    contract_id=contract.id,
                    date_from=date_from,
                    date_to=date_to,
                    exclude_payslip_id=exclude_payslip_id,
                    states=('done', 'paid'),
                )
                promedio_auxilio = result.get('promedio_auxilio', 0.0)
                periodos_consultados = result.get('count_periods', 0)
                promedio_dias_auxilio = result.get('promedio_dias_auxilio', 0.0)

            if promedio_auxilio > 0:
                auxilio = min(promedio_auxilio, auxilio_mensual)
                proporcion = auxilio / auxilio_mensual if auxilio_mensual > 0 else 0
                dias_usados = promedio_dias_auxilio or dias_pagados
                dias_descontados = max(0, dias_periodo - dias_usados)
                return {
                    'auxilio': auxilio,
                    'auxilio_mensual': auxilio_mensual,
                    'modality_aux': modality_aux,
                    'proporcion': proporcion,
                    'dias_usados': dias_usados,
                    'dias_descontados': dias_descontados,
                    'promedio_variable': promedio_auxilio,
                    'periodos_consultados': periodos_consultados,
                    'metodo': 'nomina_promedio',
                    'fuente': 'nomina_periodo'
                }

            return {
                'auxilio': 0,
                'auxilio_mensual': auxilio_mensual,
                'modality_aux': modality_aux,
                'proporcion': 0,
                'dias_usados': 0,
                'dias_descontados': 0,
                'metodo': 'nomina_sin_datos',
                'fuente': 'nomina'
            }

        if metodo_auxilio == 'dias_trabajados':
            es_provision_simple = True

        # Logica segun modality_aux
        if modality_aux == 'variable':
            # PROVISION SIMPLE: Solo proporcionar segun dias pagados del periodo (NO promediar)
            if es_provision_simple:
                dias_usados = min(dias_pagados, 30)
                proporcion = dias_usados / 30.0 if dias_usados > 0 else 0
                auxilio = auxilio_mensual * proporcion
                dias_descontados = max(0, dias_periodo - dias_pagados)

                return {
                    'auxilio': auxilio,
                    'auxilio_mensual': auxilio_mensual,
                    'modality_aux': modality_aux,
                    'proporcion': proporcion,
                    'dias_usados': dias_usados,
                    'dias_descontados': dias_descontados,
                    'metodo': 'simple_proporcional'
                }

            # PROVISION CON ACUMULACION: Promediar el auxilio pagado en el periodo
            promedio_auxilio = 0.0
            periodos_consultados = 0

            if date_from and date_to:
                query_service = self.env['period.payslip.query.service']
                result = query_service.get_auxilio_transporte_pagado(
                    contract_id=contract.id,
                    date_from=date_from,
                    date_to=date_to,
                    exclude_payslip_id=exclude_payslip_id,
                    states=('done', 'paid'),
                )
                promedio_auxilio = result.get('promedio_auxilio', 0.0)
                periodos_consultados = result.get('count_periods', 0)

            # Si no hay datos historicos, usar calculo proporcional como fallback
            if periodos_consultados == 0:
                dias_usados = min(dias_pagados, 30)
                proporcion = dias_usados / 30.0 if dias_usados > 0 else 0
                auxilio = auxilio_mensual * proporcion
            else:
                # Usar promedio del periodo
                # TOPE: El promedio no puede superar el auxilio mensual
                auxilio = min(promedio_auxilio, auxilio_mensual)
                proporcion = auxilio / auxilio_mensual if auxilio_mensual > 0 else 0
                dias_usados = dias_pagados

            dias_descontados = max(0, dias_periodo - dias_pagados)

            return {
                'auxilio': auxilio,
                'auxilio_mensual': auxilio_mensual,
                'modality_aux': modality_aux,
                'proporcion': proporcion,
                'dias_usados': dias_usados,
                'dias_descontados': dias_descontados,
                'promedio_variable': promedio_auxilio,
                'periodos_consultados': periodos_consultados,
                'metodo': 'promedio_acumulacion'
            }
        else:
            # basico: valor fijo; si es_provision_simple usa días pagados
            if es_provision_simple:
                dias_usados = min(dias_pagados, 30)
                proporcion = dias_usados / 30.0 if dias_usados > 0 else 0
                auxilio = auxilio_mensual * proporcion
                dias_descontados = max(0, dias_periodo - dias_pagados)
            else:
                if dias_ausencias_no_justificadas > 0:
                    dias_usados = max(0, 30 - dias_ausencias_no_justificadas)
                    proporcion = dias_usados / 30.0 if dias_usados > 0 else 0
                    auxilio = auxilio_mensual * proporcion
                    dias_descontados = dias_ausencias_no_justificadas
                else:
                    auxilio = auxilio_mensual
                    proporcion = 1.0
                    dias_usados = 30
                    dias_descontados = 0

            return {
                'auxilio': auxilio,
                'auxilio_mensual': auxilio_mensual,
                'modality_aux': modality_aux,
                'proporcion': proporcion,
                'dias_usados': dias_usados,
                'dias_descontados': dias_descontados,
                'metodo': 'basico_fijo'
            }

    def _calcular_base_validacion_tope(self, only_wage, salario_base, salario_variable, variable_tope=None):
        """
        Calcula la base para validar tope de auxilio segun only_wage.

        CENTRALIZADO: Usar este metodo para evitar logica duplicada.

        Args:
            only_wage: 'wage', 'wage_dev', 'wage_dev_exc'
            salario_base: Salario base del contrato
            salario_variable: Devengos salariales (DEV_SALARIAL)
            variable_tope: Devengos marcados con base_auxtransporte_tope (para wage_dev_exc)

        Returns:
            float: Base para validar tope de auxilio

        Logica:
            - wage: Solo salario base
            - wage_dev: Salario base + todos los devengos salariales
            - wage_dev_exc: Salario base + solo devengos marcados (base_auxtransporte_tope)
        """
        if only_wage == 'wage':
            return salario_base
        elif only_wage == 'wage_dev':
            return salario_base + salario_variable
        elif only_wage == 'wage_dev_exc':
            # Usa variable_tope si existe, sino usa salario_variable
            marcados = variable_tope if variable_tope is not None else salario_variable
            return salario_base + marcados
        else:
            return salario_base

    def _get_salary_base_for_tope(self, localdict, return_detail=False):
        """
        Calcula base salarial para validacion de tope de auxilios.

        Considera:
        - tope_aux_method: 'mes_completo' o 'proporcional'
        - only_wage: 'wage', 'wage_dev', 'wage_dev_exc'
        - Devengos con base_auxtransporte_tope=True
        - Ausencias que no aplican auxilio
        - Primera quincena: usa acumulados del mes

        Args:
            localdict: Diccionario de contexto
            return_detail: Si True, retorna dict con detalle de calculo

        Returns:
            float o dict: Base salarial para validacion o detalle completo
        """
        contract = localdict['contract']
        slip = localdict['slip']
        worked_days = localdict.get('worked_days', {})

        # Configuracion del contrato
        only_wage = contract.only_wage or 'wage'
        tope_method = contract.tope_aux_method or 'mes_completo'

        # Obtener dias del periodo y ausencias
        work100 = worked_days.get('WORK100')
        dias_periodo = work100.number_of_days if work100 else 30
        dias_ausencia = 0
        solo_marcadas = only_wage == 'wage_dev_exc'

        # Calcular dias de ausencia que NO aplican auxilio
        for code, wd in worked_days.items():
            if code != 'WORK100' and wd.work_entry_type_id:
                work_type = wd.work_entry_type_id
                # Si la ausencia no paga auxilio de transporte, contar los dias
                if work_type and not work_type.pay_transport_allowance:
                    dias_ausencia += wd.number_of_days or 0

        # Calcular base segun only_wage
        base_resultado = 0.0
        detalle = {
            'only_wage': only_wage,
            'tope_method': tope_method,
            'dias_periodo': dias_periodo,
            'dias_ausencia': dias_ausencia,
            'salario_base': contract.wage,
            'devengos_base_tope': 0.0,
            'acumulado_primera_quincena': 0.0,
        }

        if only_wage == 'wage':
            # Solo salario base del contrato
            base_resultado = contract.wage

        elif only_wage == 'wage_dev':
            # Salario + devengos salariales (categoria DEV_SALARIAL o base_auxtransporte_tope)
            devengos_base_tope = self._get_devengos_base_auxilio_tope(localdict, solo_marcadas=solo_marcadas)
            detalle['devengos_base_tope'] = devengos_base_tope

            base_resultado = contract.wage + devengos_base_tope

        elif only_wage == 'wage_dev_exc':
            # Salario base + devengos marcados (base_auxtransporte_tope=True)
            devengos_base_tope = self._get_devengos_base_auxilio_tope(localdict, solo_marcadas=True)
            detalle['devengos_base_tope'] = devengos_base_tope

            base_resultado = contract.wage + devengos_base_tope

            # Para segunda quincena, considerar acumulados de primera quincena
            if slip.date_from.day >= 15:
                acumulado_primera = self._get_acumulado_primera_quincena_tope(localdict, solo_marcadas=solo_marcadas)
                detalle['acumulado_primera_quincena'] = acumulado_primera

                # Sumar devengos de primera quincena que afectan tope
                base_resultado += acumulado_primera

        else:
            # Default: solo salario base
            base_resultado = contract.wage

        # Aplicar metodo de validacion
        if tope_method == 'proporcional':
            # Proporcional al periodo: base * (dias_periodo / 30)
            dias_efectivos = dias_periodo - dias_ausencia
            if dias_efectivos < 0:
                dias_efectivos = 0
            factor = dias_efectivos / 30.0 if dias_efectivos > 0 else 0
            base_resultado = base_resultado * factor
            detalle['dias_efectivos'] = dias_efectivos
            detalle['factor_proporcional'] = factor

        elif tope_method == 'mes_completo':
            # Mes completo: base mensual descontando dias de ausencia que no aplican
            # Formula: base_mensual - (base_mensual / 30 * dias_ausencia)
            if dias_ausencia > 0:
                descuento_ausencia = (base_resultado / 30.0) * dias_ausencia
                base_resultado = base_resultado - descuento_ausencia
                detalle['descuento_ausencia'] = descuento_ausencia
            detalle['dias_efectivos'] = 30 - dias_ausencia

        detalle['base_final'] = base_resultado

        if return_detail:
            return detalle

        return base_resultado

    def _get_devengos_base_auxilio_tope(self, localdict, solo_marcadas=False):
        """
        Obtiene el total de devengos salariales que hacen base para el tope de auxilio.

        Logica de inclusion:
        1. DEV_SALARIAL: Se incluye por DEFECTO (categoria padre o directa) si solo_marcadas=False
        2. base_auxtransporte_tope=True: Para reglas marcadas explicitamente
        3. excluir_auxtransporte_tope=True: EXCLUYE (tiene PRIORIDAD sobre todo)

        Args:
            localdict: Diccionario de contexto

        Returns:
            float: Total de devengos que hacen base para tope
        """
        rules = localdict.get('rules', {})
        total = 0.0

        for code, rule_data in rules.items():
            if code == 'BASIC':
                continue  # Saltar basico, ya se cuenta en salario contrato

            rule = rule_data.rule
            if not rule:
                continue

            # 1. excluir_auxtransporte_tope tiene MAXIMA PRIORIDAD
            if rule.excluir_auxtransporte_tope:
                continue

            # 2. Verificar si es DEV_SALARIAL (por defecto se incluye)
            es_dev_salarial = False
            if rule.category_id:
                cat = rule.category_id
                # Verificar categoria directa o padre
                if cat.code == 'DEV_SALARIAL':
                    es_dev_salarial = True
                elif cat.parent_id and cat.parent_id.code == 'DEV_SALARIAL':
                    es_dev_salarial = True

            # 3. Incluir segun modo:
            # - solo_marcadas=True: SOLO reglas con base_auxtransporte_tope=True
            # - solo_marcadas=False: DEV_SALARIAL o base_auxtransporte_tope=True
            incluir = rule.base_auxtransporte_tope if solo_marcadas else (es_dev_salarial or rule.base_auxtransporte_tope)
            if incluir:
                total += rule_data.total or 0

        return total

    def _get_acumulado_primera_quincena_tope(self, localdict, solo_marcadas=False):
        """
        Obtiene los devengos acumulados de la primera quincena que afectan el tope.

        Se usa cuando estamos en la segunda quincena para considerar novedades
        de la primera quincena en la validacion del tope.

        Usa el servicio centralizado de consultas con SQL optimizado.

        Logica de inclusion:
        1. DEV_SALARIAL: Se incluye por DEFECTO
        2. base_auxtransporte_tope=True: Para otras reglas que quieran agregarse
        3. excluir_auxtransporte_tope=True: EXCLUYE (tiene PRIORIDAD)

        Args:
            localdict: Diccionario de contexto

        Returns:
            float: Total acumulado de primera quincena que afecta tope
        """
        slip = localdict['slip']
        contract = localdict['contract']

        # Solo aplica si estamos en segunda quincena
        if slip.date_from.day < 15:
            return 0.0

        from datetime import timedelta

        # Fechas de primera quincena
        start_date = slip.date_from.replace(day=1)
        end_date = slip.date_from - timedelta(days=1)

        # Usar servicio centralizado de consultas
        query_service = self.env['period.payslip.query.service']
        result = query_service.get_devengos_tope_auxilio(
            contract_id=contract.id,
            date_from=start_date,
            date_to=end_date,
            exclude_payslip_id=slip.id,
            states=('done', 'paid'),
            solo_marcadas=solo_marcadas,
        )

        return result.get('total', 0.0)


    def _calculate_auxilio_days(self, localdict):
        """Calcula días para el auxilio de transporte.

        Usa number_of_days_aux que considera:
        - Ausencias con pay_transport_allowance=True: NO restan días de auxilio
        - Ausencias con pay_transport_allowance=False: SÍ restan días de auxilio
        """
        slip = localdict['slip']
        worked_days = localdict['worked_days']
        work100 = worked_days.get('WORK100')
        # Usar días específicos para auxilio (number_of_days_aux)
        if work100:
            dias = work100.number_of_days_aux or work100.number_of_days
        else:
            dias = 0
        dias_primera = 0
        if slip.use_manual_days and slip.manual_days > 0:
            dias = float(slip.manual_days)
        start_date = slip.date_from.replace(day=1)
        end_date = slip.date_from - timedelta(days=1)

        accumulated = slip._get_categories_accumulated_by_payslip(start_date, end_date)
        if 'BASIC' in accumulated:
            basic_category = accumulated['BASIC']
            basic_line_ids = basic_category.line_ids or []
            if basic_line_ids:
                lines = self.env['hr.payslip.line'].browse(basic_line_ids)
                dias_primera = sum(line.quantity for line in lines)

        return dias, dias_primera


    def _validate_auxilio(self, tipo_auxilio, context, localdict=None, contract=None, employee=None, slip=None,
                          annual_parameters=None, config_params=None, provision_type=None, salario_base=0,
                          salario_minimo=0, salario_variable=0, flags=None):
        """Valida auxilio por contexto"""
        localdict = localdict or {}
        contract = contract or localdict.get('contract')
        employee = employee or localdict.get('employee')
        slip = slip or localdict.get('slip')
        annual_parameters = annual_parameters or localdict.get('annual_parameters')
        config_params = config_params or {}
        flags = flags or {}

        if not contract:
            return {
                'aplica': False,
                'razon': 'Sin contrato',
                'only_wage': 'wage',
                'base_validacion_tope': 0,
                'dos_smmlv': 2 * (salario_minimo or 0),
                'supera_tope': False,
            }

        if context == 'prestacion' and tipo_auxilio == 'conectividad':
            return {
                'aplica': False,
                'razon': 'Prestacion no aplica a conectividad',
                'only_wage': contract.only_wage or 'wage',
                'base_validacion_tope': 0,
                'dos_smmlv': 2 * (salario_minimo or 0),
                'supera_tope': False,
            }

        if not annual_parameters:
            return {'aplica': False, 'razon': 'No hay parámetros anuales configurados'}

        if context in ('nomina', 'provision'):
            aplica, razon = self._validate_auxilio_nomina(
                tipo_auxilio,
                contract,
                employee,
                slip,
                annual_parameters,
                flags,
                context,
            )
            return {'aplica': aplica, 'razon': razon}

        return self._validate_auxilio_prestacion(
            contract,
            employee,
            annual_parameters,
            config_params,
            provision_type,
            salario_base,
            salario_minimo,
            salario_variable,
            flags,
            slip=slip,
        )

    def _validate_auxilio_nomina(self, tipo_auxilio, contract, employee, slip, annual_parameters, flags, context):
        """Valida auxilio para nómina/provisión"""
        if tipo_auxilio == 'conectividad':
            if not contract.remote_work_allowance:
                return False, 'No aplica auxilio de conectividad'
            return True, ''

        if contract.not_pay_auxtransportation:
            return False, 'Auxilio desactivado en contrato'

        if contract.modality_salary == 'integral':
            return False, 'Salario integral no recibe auxilio'

        if contract.modality_salary == 'sostenimiento':
            if not self._is_apprenticeship_contract(contract):
                return False, 'Modalidad sostenimiento solo para aprendices'

        if employee and not self._validate_aprendiz_auxilio(employee, contract, annual_parameters, slip=slip):
            return False, 'Aprendiz sin auxilio según parámetros anuales'

        if employee and not self._validate_distancia_trabajo(employee, flags):
            return False, 'Distancia insuficiente para auxilio de transporte'

        validate_quincena = flags.get('validate_quincena', context == 'nomina')
        if validate_quincena and contract.pay_auxtransportation and slip and slip.date_from.day < 15:
            return False, 'Se paga solo en segunda quincena'

        return True, ''

    def _validate_auxilio_prestacion(self, contract, employee, annual_parameters, config_params, provision_type,
                                     salario_base, salario_minimo, salario_variable, flags, slip=None):
        """Valida auxilio para prestaciones"""
        resultado = {
            'aplica': False,
            'razon': '',
            'only_wage': contract.only_wage or 'wage',
            'base_validacion_tope': 0,
            'dos_smmlv': 2 * (salario_minimo or 0),
            'supera_tope': False,
        }

        if provision_type == 'intereses':
            resultado['razon'] = 'Intereses se calcula sobre cesantias (que ya incluye auxilio si aplica)'
            return resultado

        if contract.contract_type_id and not contract.contract_type_id.has_auxilio_transporte:
            resultado['razon'] = 'Tipo de contrato no tiene derecho a auxilio de transporte'
            return resultado

        if contract.not_pay_auxtransportation:
            resultado['razon'] = 'Contrato marcado como "No liquidar auxilio de transporte"'
            return resultado

        if contract.modality_aux == 'no':
            resultado['razon'] = 'Modalidad de auxilio configurada como "Sin auxilio"'
            return resultado

        if contract.modality_salary == 'integral':
            resultado['razon'] = 'Salario integral no recibe auxilio'
            return resultado

        if contract.modality_salary == 'sostenimiento':
            if not self._is_apprenticeship_contract(contract):
                resultado['razon'] = 'Modalidad sostenimiento solo para aprendices'
                return resultado

        if employee and annual_parameters:
            if not self._validate_aprendiz_auxilio(employee, contract, annual_parameters, slip=slip):
                resultado['razon'] = 'Aprendiz sin auxilio según parámetros anuales'
                return resultado

        if employee and not self._validate_distancia_trabajo(employee, flags):
            resultado['razon'] = 'Distancia insuficiente para auxilio de transporte'
            return resultado

        config_field_map = {
            'prima': 'prima_incluye_auxilio',
            'cesantias': 'cesantias_incluye_auxilio',
            'vacaciones': 'vacaciones_incluye_auxilio',
        }
        config_field = config_field_map.get(provision_type, 'prima_incluye_auxilio')
        if not config_params.get(config_field, False):
            resultado['razon'] = f'Configuracion global: {provision_type} no incluye auxilio'
            return resultado

        only_wage = resultado['only_wage']
        base_validacion = self._calcular_base_validacion_tope(
            only_wage, salario_base, salario_variable
        )
        resultado['base_validacion_tope'] = base_validacion

        if not (config_params.get('aux_prst') or contract.not_validate_top_auxtransportation):
            resultado['supera_tope'] = base_validacion >= resultado['dos_smmlv']
            if resultado['supera_tope']:
                resultado['razon'] = (
                    f'Salario ({base_validacion:,.0f}) supera 2 SMMLV ({resultado["dos_smmlv"]:,.0f})'
                )
                return resultado

        resultado['aplica'] = True
        return resultado

    def _is_apprenticeship_contract(self, contract):
        """Indica si el contrato es de aprendizaje segun su tipo."""
        if not contract or not contract.contract_type_id:
            return False
        contract_type = contract.contract_type_id
        return bool(contract_type.is_apprenticeship or contract_type.contract_category == 'aprendizaje')

    def _get_apprentice_stage(self, contract, employee, slip=None):
        """Obtiene la etapa del aprendiz según el período del slip (no el estado actual).
        Usa apr_prod_date vs slip.date_to para determinar la etapa efectiva del período."""
        if contract:
            apr_prod_date = getattr(contract, 'apr_prod_date', False)
            if apr_prod_date and slip:
                return 'lectiva' if slip.date_to < apr_prod_date else 'productiva'
            # Sin fecha de productiva o sin slip: fallback al campo computado
            if contract.apprentice_stage:
                return contract.apprentice_stage
        if employee and employee.tipo_coti_id:
            if employee.tipo_coti_id.code == '12':
                return 'lectiva'
            if employee.tipo_coti_id.code == '19':
                return 'productiva'
        return False

    def _validate_aprendiz_auxilio(self, employee, contract, annual_parameters, slip=None):
        """Valida auxilio para aprendices según la etapa efectiva del período del slip."""
        if not self._is_apprenticeship_contract(contract):
            return True

        stage = self._get_apprentice_stage(contract, employee, slip=slip)
        if stage == 'lectiva':
            # Regla de negocio: etapa lectiva no recibe auxilio de transporte.
            return False
        if stage == 'productiva':
            return bool(annual_parameters and annual_parameters.aux_apr_prod)
        return True

    def _validate_distancia_trabajo(self, employee, flags):
        """Valida distancia al trabajo (Decreto 1258/1959)"""
        validate_distance = flags.get('validate_distance')
        if validate_distance is None:
            validate_distance = self.env['ir.config_parameter'].sudo().get_param(
                'lavish_hr_payroll.validate_distance_aux_transport', 'False'
            )
        if validate_distance != 'True':
            return True

        if employee.lives_near_work:
            return False

        distance_km = employee.km_home_work or employee.distance_to_work_km or 0
        distance_threshold = flags.get('distance_threshold')
        if distance_threshold is None:
            distance_threshold = float(self.env['ir.config_parameter'].sudo().get_param(
                'lavish_hr_payroll.distance_threshold_km', '1.0'
            ))

        return distance_km == 0 or distance_km >= float(distance_threshold)



    def _calculate_auxilio_generic(self, localdict, tipo_auxilio, codigo_auxilio):
        """Metodo generico para calcular auxilios - solo construccion de datos"""
        contract = localdict['contract']
        annual_parameters = localdict.get('annual_parameters')

        config = self._get_auxilio_config(tipo_auxilio, annual_parameters, is_devolucion=False)

        validation = self._validate_auxilio(tipo_auxilio, context='nomina', localdict=localdict)
        if not validation.get('aplica'):
            return crear_resultado_vacio(config['name'], validation.get('razon', ''), tipo_auxilio)


        dias_total, dias_primera_quincena = self._calculate_auxilio_days(localdict)

        if dias_total <= 0:
            return crear_resultado_vacio(config['name'], 'Sin dias trabajados', tipo_auxilio)

        valor_diario = float(config['monthly_value']) / 30.0

        # Calcular salary_base con detalle de validacion
        salary_base = 0
        salary_limit = config['salary_limit']
        validaciones_aplicadas = []
        tope_detalle = {}

        if not contract.not_validate_top_auxtransportation:
            # Obtener detalle completo de validacion de tope
            tope_detalle = self._get_salary_base_for_tope(localdict, return_detail=True)
            salary_base = tope_detalle.get('base_final', 0)
            validaciones_aplicadas.append('tope_salarial')
            validaciones_aplicadas.append(f"metodo_{tope_detalle.get('tope_method', 'mes_completo')}")
            validaciones_aplicadas.append(f"only_wage_{tope_detalle.get('only_wage', 'wage')}")

            # Validar si excede el tope salarial
            if salary_base > config['salary_limit']:
                localdict['auxilio_info'] = {
                    'codigo': codigo_auxilio,
                    'salary_base': salary_base,
                    'salary_limit': config['salary_limit'],
                    'requires_devolution': True,
                    'tope_detalle': tope_detalle,
                }

                log_data = crear_log_data(
                    'rejected', tipo_auxilio,
                    reason='salary_exceeds_limit',
                    salary_base=float(salary_base),
                    salary_limit=float(config['salary_limit']),
                    tope_detalle=tope_detalle,
                )
                return (0, 0, 0, config['name'], '', log_data)
        else:
            validaciones_aplicadas.append('sin_validacion_tope')

        if contract.pay_auxtransportation:
            validaciones_aplicadas.append('segunda_quincena')

        if contract.modality_salary != 'integral':
            validaciones_aplicadas.append('no_integral')

        log_data = crear_log_data(
            'success', tipo_auxilio,
            daily_value=float(valor_diario),
            days=float(dias_total),
            total=float(valor_diario * dias_total),
            monthly_value=float(config['monthly_value']),
            codigo=codigo_auxilio,
            validaciones=validaciones_aplicadas,
            salary_base=float(salary_base) if salary_base else 0,
            salary_limit=float(salary_limit),
            dentro_tope=salary_base <= salary_limit if salary_base else True,
            dias_primera_quincena=float(dias_primera_quincena),
            dias_segunda_quincena=float(dias_total - dias_primera_quincena) if dias_primera_quincena else float(dias_total),
            tope_detalle=tope_detalle,
        )

        localdict['auxilio_info'] = {
            'codigo': codigo_auxilio,
            'valor_diario': float(valor_diario),
            'dias': dias_total,
            'requires_devolution': False,
            'tope_detalle': tope_detalle,
        }

        # Crear computation estandarizada para el widget
        indicadores = [
            crear_indicador('Dias', float(dias_total), 'info', 'number'),
        ]
        if salary_base > 0:
            dentro_tope = 'Si' if salary_base <= salary_limit else 'No'
            indicadores.append(crear_indicador('Dentro Tope', dentro_tope, 'success' if salary_base <= salary_limit else 'danger', 'text'))
            # Agregar indicador de metodo de validacion
            tope_method_label = 'Mes Completo' if tope_detalle.get('tope_method') == 'mes_completo' else 'Proporcional'
            indicadores.append(crear_indicador('Metodo Tope', tope_method_label, 'info', 'text'))

        pasos = [
            crear_paso_calculo('Valor Mensual', float(config['monthly_value']), 'currency'),
            crear_paso_calculo('Valor Diario', float(valor_diario), 'currency'),
            crear_paso_calculo('Dias Trabajados', float(dias_total), 'number'),
            crear_paso_calculo('Total', float(valor_diario * dias_total), 'currency', highlight=True),
        ]

        # Agregar pasos de validacion de tope si aplica
        if tope_detalle:
            pasos.append(crear_paso_calculo('Salario Base Contrato', float(tope_detalle.get('salario_base', 0)), 'currency'))
            if tope_detalle.get('devengos_base_tope', 0) > 0:
                pasos.append(crear_paso_calculo('Devengos Base Tope', float(tope_detalle.get('devengos_base_tope', 0)), 'currency'))
            if tope_detalle.get('acumulado_primera_quincena', 0) > 0:
                pasos.append(crear_paso_calculo('Acumulado 1ra Quincena', float(tope_detalle.get('acumulado_primera_quincena', 0)), 'currency'))
            pasos.append(crear_paso_calculo('Base Final Tope', float(tope_detalle.get('base_final', 0)), 'currency'))
            pasos.append(crear_paso_calculo('Tope 2 SMMLV', float(salary_limit), 'currency'))

        computation = crear_computation_estandar(
            'auxilio',
            titulo=config['name'],
            formula='Auxilio Mensual / 30 x Dias',
            indicadores=indicadores,
            pasos=pasos,
            base_legal='Ley 15 de 1959, Art. 4',
            elemento_ley='Trabajadores que devenguen hasta 2 SMMLV tienen derecho al auxilio de transporte',
            datos=log_data,
        )

        return crear_resultado_regla(float(valor_diario), dias_total, 100.0, config['name'], log_data=log_data, data_kpi=computation)


    def _calculate_devolucion_generic(self, localdict, tipo_auxilio, codigo_auxilio):
        """Método genérico para devoluciones de auxilios - solo construcción de datos.

        La validación toma TODOS los valores del mes:
        - Salario base del contrato
        - Devengos de primera quincena con base_auxtransporte_tope=True
        - Devengos de segunda quincena con base_auxtransporte_tope=True
        - Aplica método de tope (mes_completo o proporcional)
        - Descuenta días de ausencia según método
        """
        contract = localdict['contract']
        annual_parameters = localdict.get('annual_parameters')
        nombre_devolucion = f'DEVOLUCION {tipo_auxilio.upper()}'

        if not contract.dev_aux:
            return crear_resultado_vacio(nombre_devolucion, 'Devolucion desactivada en contrato', tipo_auxilio)

        auxilio_previo_info = self._get_auxilio_previo(localdict, codigo_auxilio)

        if not auxilio_previo_info['encontrado'] or auxilio_previo_info['valor'] <= 0:
            return crear_resultado_vacio(nombre_devolucion, 'Sin auxilio previo a devolver', tipo_auxilio)

        config = self._get_auxilio_config(tipo_auxilio, annual_parameters, is_devolucion=True)

        # Obtener detalle completo de validación de tope (todos los valores del mes)
        tope_detalle = self._get_salary_base_for_tope(localdict, return_detail=True)
        salary_base = tope_detalle.get('base_final', 0)

        if salary_base <= config['salary_limit']:
            log_data = crear_log_data(
                'no_devolution', tipo_auxilio,
                reason='salary_within_limit',
                salary_base=float(salary_base),
                salary_limit=float(config['salary_limit']),
                tope_detalle=tope_detalle,
                validacion='Salario dentro del tope - No requiere devolucion',
            )
            return (0, 0, 0, config['name'], '', log_data)

        # Calcular devolución - salario excede tope
        valor_diario = float(config['monthly_value']) / 30.0
        dias_pagados = auxilio_previo_info['dias']
        valor_devolucion = auxilio_previo_info['valor']

        log_data = crear_log_data(
            'devolution', tipo_auxilio,
            daily_value=float(valor_diario),
            days_returned=float(dias_pagados),
            amount_returned=float(valor_devolucion),
            salary_base=float(salary_base),
            salary_limit=float(config['salary_limit']),
            reason='salary_exceeds_limit',
            tope_detalle=tope_detalle,
            desglose_validacion={
                'salario_contrato': float(tope_detalle.get('salario_base', 0)),
                'devengos_base_tope': float(tope_detalle.get('devengos_base_tope', 0)),
                'acumulado_primera_quincena': float(tope_detalle.get('acumulado_primera_quincena', 0)),
                'metodo_tope': tope_detalle.get('tope_method', 'mes_completo'),
                'dias_ausencia': float(tope_detalle.get('dias_ausencia', 0)),
                'base_final': float(salary_base),
                'excede_tope': salary_base > config['salary_limit'],
            }
        )

        # Crear computation para widget
        indicadores = [
            crear_indicador('Dias Devueltos', float(dias_pagados), 'warning', 'number'),
            crear_indicador('Excede Tope', 'Si', 'danger', 'text'),
        ]

        tope_method_label = 'Mes Completo' if tope_detalle.get('tope_method') == 'mes_completo' else 'Proporcional'
        indicadores.append(crear_indicador('Metodo Tope', tope_method_label, 'info', 'text'))

        pasos = [
            crear_paso_calculo('Salario Contrato', float(tope_detalle.get('salario_base', 0)), 'currency'),
        ]

        if tope_detalle.get('devengos_base_tope', 0) > 0:
            pasos.append(crear_paso_calculo('Devengos Base Tope (2da Qna)', float(tope_detalle.get('devengos_base_tope', 0)), 'currency'))

        if tope_detalle.get('acumulado_primera_quincena', 0) > 0:
            pasos.append(crear_paso_calculo('Acumulado 1ra Quincena', float(tope_detalle.get('acumulado_primera_quincena', 0)), 'currency'))

        if tope_detalle.get('dias_ausencia', 0) > 0:
            pasos.append(crear_paso_calculo('Dias Ausencia Sin Auxilio', float(tope_detalle.get('dias_ausencia', 0)), 'number'))
            if tope_detalle.get('descuento_ausencia'):
                pasos.append(crear_paso_calculo('Descuento Ausencias', float(tope_detalle.get('descuento_ausencia', 0)), 'currency'))

        pasos.extend([
            crear_paso_calculo('Base Final Validacion', float(salary_base), 'currency', highlight=True),
            crear_paso_calculo('Tope 2 SMMLV', float(config['salary_limit']), 'currency'),
            crear_paso_calculo('Auxilio Pagado 1ra Qna', float(valor_devolucion), 'currency'),
            crear_paso_calculo('Valor a Devolver', float(-valor_devolucion), 'currency', highlight=True),
        ])

        computation = crear_computation_estandar(
            'devolucion_auxilio',
            titulo=config['name'],
            formula='Devolucion cuando Salario > 2 SMMLV',
            indicadores=indicadores,
            pasos=pasos,
            base_legal='Ley 15 de 1959, Art. 4',
            elemento_ley='Si el salario mensual (incluyendo devengos) excede 2 SMMLV, se devuelve el auxilio',
            datos=log_data,
        )

        return crear_resultado_regla(-float(valor_diario), dias_pagados, 100.0, config['name'], log_data=log_data, data_kpi=computation)


    def _aux000(self, localdict):
        """Calcula auxilio de transporte"""
        return self._calculate_auxilio_generic(localdict, tipo_auxilio='transporte', codigo_auxilio='AUX000')

    def _aux00c(self, localdict):
        """Calcula auxilio de conectividad"""
        return self._calculate_auxilio_generic(localdict, tipo_auxilio='conectividad', codigo_auxilio='AUX00C')

    def _dev_aux000(self, localdict):
        """Devolución de auxilio de transporte"""
        return self._calculate_devolucion_generic(localdict, tipo_auxilio='transporte', codigo_auxilio='AUX000')

    def _dev_aux00c(self, localdict):
        """Devolución de auxilio de conectividad"""
        return self._calculate_devolucion_generic(localdict, tipo_auxilio='conectividad', codigo_auxilio='AUX00C')
