# -*- coding: utf-8 -*-

"""
PRESTACIONES SOCIALES - PROVISIONES
===================================
Cálculo de provisiones y saldos contables.
"""

import logging
from odoo import models
from datetime import date, timedelta
from odoo.addons.lavish_hr_employee.models.hr_slip_utils import days360
from .config_reglas import (
    PRESTACIONES_CONFIG,
    get_contextual_base_field,
    validar_aplica_auxilio_transporte,
    calcular_auxilio_transporte_periodo,
)

_logger = logging.getLogger(__name__)


class HrSalaryRulePrestacionesProvisiones(models.AbstractModel):
    _name = 'hr.salary.rule.prestaciones.provisiones'
    _inherit = 'hr.salary.rule.prestaciones'

    def _get_biweekly_context(self, slip):
        """
        Determina si la nómina es quincenal y si corresponde a primera/segunda quincena.
        Prioriza period_id y usa fechas como fallback.
        """
        period = slip.period_id
        if period and period.type_period == 'bi-monthly':
            return True, period.type_biweekly or ''

        if not slip.date_from or not slip.date_to:
            return False, ''

        days = (slip.date_to - slip.date_from).days + 1
        if days <= 16:
            if slip.date_from.day <= 15:
                return True, 'first'
            return True, 'second'

        return False, ''

    def _get_selection_label(self, model_name, field_name, value):
        """
        Obtiene la etiqueta de un campo selection dinamicamente desde el modelo.

        Args:
            model_name: Nombre del modelo (ej: 'hr.contract')
            field_name: Nombre del campo selection (ej: 'modality_aux')
            value: Valor actual del campo

        Returns:
            str: Etiqueta del valor o el valor mismo si no se encuentra
        """
        if not value:
            return ''
        try:
            Model = self.env[model_name]
            if field_name in Model._fields:
                field = Model._fields[field_name]
                if field.type == 'selection':
                    selection = field._description_selection(self.env)
                    selection_dict = dict(selection)
                    return selection_dict.get(value, value)
        except Exception:  # noqa: BLE001 – campo de selección de display, retorna valor raw
            _logger.debug("Error obteniendo etiqueta de selección para %s.%s=%s", model_name, field_name, value, exc_info=True)
        return value

    def _get_contract_labels(self, contract):
        """
        Obtiene las etiquetas de configuracion del contrato para display.

        Args:
            contract: Objeto hr.contract

        Returns:
            dict: Diccionario con las etiquetas
        """
        return {
            'modality_aux_label': self._get_selection_label(
                'hr.contract', 'modality_aux', contract.modality_aux or 'basico'
            ),
            'only_wage_label': self._get_selection_label(
                'hr.contract', 'only_wage', contract.only_wage or 'wage'
            ),
        }

    def _get_provision_config_params(self, annual_parameters=None):
        """
        Obtiene todos los parametros de configuracion para provisiones.

        Fuentes:
        1. ir.config_parameter (lavish_hr_payroll.*) - Configuracion global
        2. hr.annual.parameters - Parametros anuales
        3. res.company - Configuracion de compania

        Returns:
            dict: Diccionario con todos los parametros de configuracion
        """
        get_param = self.env['ir.config_parameter'].sudo().get_param
        company = self.env.company

        # Parametros de ir.config_parameter con defaults
        def str_to_bool(val, default=False):
            if isinstance(val, bool):
                return val
            if isinstance(val, str):
                return val.lower() in ('true', '1', 'yes')
            return default

        config = {
            # Auxilio por tipo de provision
            'prima_incluye_auxilio': str_to_bool(
                get_param('lavish_hr_payroll.prima_incluye_auxilio', 'True'), True
            ),
            'cesantias_incluye_auxilio': str_to_bool(
                get_param('lavish_hr_payroll.cesantias_incluye_auxilio', 'True'), True
            ),
            'vacaciones_incluye_auxilio': str_to_bool(
                get_param('lavish_hr_payroll.vacaciones_incluye_auxilio', 'False'), False
            ),
            'auxilio_prestaciones_metodo': get_param(
                'lavish_hr_payroll.auxilio_prestaciones_metodo', 'dias_trabajados'
            ),
            # Deteccion de cambios de salario
            'promedio_detectar_cambios': str_to_bool(
                get_param('lavish_hr_payroll.promedio_detectar_cambios', 'True'), True
            ),
            # No descontar suspensiones de prima (global)
            'prst_wo_susp_global': str_to_bool(
                get_param('lavish_hr_payroll.prst_wo_susp', 'False'), False
            ),
            # No descontar ausencias en provisiones (global)
            'prst_wo_absences_global': str_to_bool(
                get_param('lavish_hr_payroll.prst_wo_absences', 'True'), True
            ),
            # Metodo simple/complejo (de compania)
            'simple_provisions': company.simple_provisions,
            # No descontar suspensiones (de compania)
            'prst_wo_susp_company': company.prst_wo_susp,
        }

        # Parametros de hr.annual.parameters
        if annual_parameters:
            config.update({
                'aux_prst': annual_parameters.aux_prst,
                'prst_wo_susp_annual': annual_parameters.prst_wo_susp,
            })
        else:
            config.update({
                'aux_prst': False,
                'prst_wo_susp_annual': False,
            })

        # Consolidar prst_wo_susp (cualquiera de las fuentes)
        config['prst_wo_susp'] = (
            config['prst_wo_susp_global'] or
            config['prst_wo_susp_company'] or
            config['prst_wo_susp_annual']
        )
        # Consolidar prst_wo_absences (solo global por ahora)
        config['prst_wo_absences'] = config['prst_wo_absences_global']

        return config

    def _provision_incluye_auxilio(self, provision_type, config_params, contract, salario_base, salario_minimo,
                                      salario_variable=0.0, employee=None, annual_parameters=None,
                                      return_detail=False):
        """
        Determina si una provision especifica debe incluir auxilio de transporte.

        Considera:
        - contract.not_pay_auxtransportation: No liquidar auxilio
        - contract.modality_aux: 'basico'/'variable'/'no'
        - contract.only_wage: 'wage'/'wage_dev'/'wage_dev_exc' para validacion de tope
        - config_params: Configuracion global por tipo de provision

        Args:
            provision_type: Tipo de provision (prima, cesantias, vacaciones, intereses)
            config_params: Diccionario de configuracion
            contract: Contrato del empleado
            salario_base: Salario base mensual
            salario_minimo: SMMLV
            salario_variable: Devengos variables (para only_wage='wage_dev')
            employee: hr.employee (opcional)
            annual_parameters: hr.annual.parameters (opcional)
            return_detail: True para retornar dict con detalle y razon

        Returns:
            bool o dict: True si debe incluir auxilio o detalle si return_detail=True
        """
        detalle = self.env['hr.salary.rule.aux']._validate_auxilio(
            tipo_auxilio='transporte',
            context='prestacion',
            contract=contract,
            employee=employee,
            annual_parameters=annual_parameters,
            config_params=config_params,
            provision_type=provision_type,
            salario_base=salario_base,
            salario_minimo=salario_minimo,
            salario_variable=salario_variable,
        )
        if return_detail:
            return detalle
        return detalle.get('aplica', False)

    def _obtener_parametros_indicador_especial(self, employee, provision_type):
        """
        Obtiene los parametros de prestaciones desde el indicador especial PILA del empleado.

        Si el empleado tiene indicador_especial_id configurado y no tiene no_usar_en_pila,
        retorna los parametros especificos para la prestacion.

        Args:
            employee: hr.employee
            provision_type: 'prima', 'cesantias', 'vacaciones', 'intereses'

        Returns:
            dict: {
                'usar_indicador': bool,
                'dias': float - Dias de la prestacion,
                'base_dias': int - Base de dias (360, 365, etc.),
                'paga': bool - Si paga la prestacion,
                'tasa': float - Tasa calculada (dias / base_dias * 100),
                'incluye_auxilio': bool - Si incluye auxilio en prestaciones,
                'indicador_codigo': str - Codigo del indicador
            }
        """
        resultado = {
            'usar_indicador': False,
            'dias': 0.0,
            'base_dias': 360,
            'paga': True,
            'tasa': 0.0,
            'incluye_auxilio': True,
            'indicador_codigo': '',
        }

        if not employee or not employee.indicador_especial_id:
            return resultado

        indicador = employee.indicador_especial_id


        resultado['usar_indicador'] = True
        resultado['indicador_codigo'] = indicador.code
        resultado['incluye_auxilio'] = indicador.incluye_aux_transporte_prestaciones

        # Obtener parametros segun tipo de prestacion
        info = indicador.get_dias_prestacion(provision_type)
        resultado['dias'] = info.get('dias', 0.0)
        resultado['base_dias'] = info.get('base_dias', 360)
        resultado['paga'] = info.get('paga', True)

        # Calcular tasa: dias / base_dias * 100
        # Ejemplo: 15 dias / 360 = 0.0417 -> 4.17%
        if resultado['base_dias'] > 0:
            resultado['tasa'] = (resultado['dias'] / resultado['base_dias']) * 100

        return resultado

    def _validar_condiciones_prestacion(self, provision_type, employee, contract, slip, annual_parameters=None):
        """
        Valida todas las condiciones para calcular una prestacion.

        Acumula todas las validaciones en un solo lugar para ser llamado desde diferentes metodos.

        Args:
            provision_type: 'prima', 'cesantias', 'vacaciones', 'intereses'
            employee: hr.employee
            contract: hr.contract
            slip: hr.payslip
            annual_parameters: hr.annual.parameters (opcional)

        Returns:
            dict: {
                'aplica': bool - Si aplica la prestacion,
                'motivo': str - Motivo si no aplica,
                'validaciones': list - Lista de validaciones realizadas,
                'indicador_params': dict - Parametros del indicador especial si aplica,
                'config_override': dict - Configuracion a sobrescribir,
                'warnings': list - Advertencias (no bloquean pero son importantes)
            }
        """
        resultado = {
            'aplica': True,
            'motivo': '',
            'validaciones': [],
            'indicador_params': {},
            'config_override': {},
            'warnings': [],
        }

        def agregar_validacion(nombre, aplica, detalle=''):
            resultado['validaciones'].append({
                'nombre': nombre,
                'aplica': aplica,
                'detalle': detalle,
            })
            return aplica

        # ========== 1. VALIDAR EMPLEADO ==========
        if not employee:
            resultado['aplica'] = False
            resultado['motivo'] = 'Sin empleado asociado'
            agregar_validacion('Empleado', False, 'No hay empleado')
            return resultado
        agregar_validacion('Empleado', True, f'{employee.name}')

        # ========== 2. VALIDAR CONTRATO ==========
        if not contract:
            resultado['aplica'] = False
            resultado['motivo'] = 'Sin contrato asociado'
            agregar_validacion('Contrato', False, 'No hay contrato')
            return resultado
        agregar_validacion('Contrato', True, f'{contract.name}')

        # ========== 3. VALIDAR INDICADOR ESPECIAL PILA ==========
        indicador_params = self._obtener_parametros_indicador_especial(employee, provision_type)
        resultado['indicador_params'] = indicador_params

        if indicador_params.get('usar_indicador'):
            codigo = indicador_params.get('indicador_codigo', '')
            # Verificar si paga esta prestacion
            if not indicador_params.get('paga', True):
                resultado['aplica'] = False
                resultado['motivo'] = f'Indicador especial {codigo} no paga {provision_type}'
                agregar_validacion('Indicador Especial', False, f'{codigo} no paga {provision_type}')
                return resultado

            agregar_validacion('Indicador Especial', True, f'{codigo} (tasa={indicador_params.get("tasa", 0):.2f}%)')

            # Guardar override de configuracion
            tasa_indicador = indicador_params.get('tasa', 0.0)
            if tasa_indicador > 0:
                resultado['config_override']['tasa'] = tasa_indicador
                resultado['config_override']['tasa_indicador'] = True
                resultado['config_override']['dias_indicador'] = indicador_params.get('dias', 0.0)
                resultado['config_override']['base_dias_indicador'] = indicador_params.get('base_dias', 360)
                resultado['config_override']['incluye_auxilio_indicador'] = indicador_params.get('incluye_auxilio', True)
        else:
            agregar_validacion('Indicador Especial', True, 'No configurado (usa valores estandar)')

        # ========== 4. VALIDAR TIPO DE COTIZANTE (APRENDICES) ==========
        # Se determina la etapa efectiva del PERIODO del slip usando apr_prod_date,
        # igual que en seguridad_social.py. Esto evita que el campo computado
        # apprentice_stage (que refleja el estado actual) afecte nóminas históricas.
        is_apprentice = (
            contract.contract_type_id
            and getattr(contract.contract_type_id, 'contract_category', False) == 'aprendizaje'
        )
        if is_apprentice and contract.contract_type_id:
            apr_prod_date = getattr(contract, 'apr_prod_date', False)
            slip_date_to = slip.date_to if slip else False
            if apr_prod_date and slip_date_to:
                stage_periodo = 'lectiva' if slip_date_to < apr_prod_date else 'productiva'
            else:
                # Sin fecha de productiva o sin slip: usar tipo cotizante actual como fallback
                tipo_coti_code = employee.tipo_coti_id.code if employee.tipo_coti_id else False
                stage_periodo = 'lectiva' if tipo_coti_code == '12' else (
                    getattr(contract, 'apprentice_stage', 'lectiva') or 'lectiva'
                )

            if stage_periodo == 'lectiva':
                if not contract.contract_type_id.has_social_benefits_aprendiz:
                    resultado['aplica'] = False
                    resultado['motivo'] = 'Aprendiz etapa lectiva sin prestaciones (período)'
                    agregar_validacion('Tipo Cotizante', False, 'Aprendiz lectiva sin prestaciones')
                    return resultado
                else:
                    agregar_validacion('Tipo Cotizante', True, 'Aprendiz lectiva con prestaciones por tipo contrato')
            else:
                # Etapa productiva: siempre aplican provisiones
                agregar_validacion('Tipo Cotizante', True, 'Aprendiz etapa productiva')
        elif employee.tipo_coti_id:
            agregar_validacion('Tipo Cotizante', True, f'{employee.tipo_coti_id.name}')
        else:
            agregar_validacion('Tipo Cotizante', True, 'No especificado (aplica estandar)')

        # ========== 5. VALIDAR TIPO DE CONTRATO ==========
        if contract.contract_type_id:
            tipo_contrato = contract.contract_type_id

            # Verificar si el tipo de contrato paga esta prestacion
            paga_prestacion = True
            if provision_type == 'prima' and not tipo_contrato.has_prima:
                paga_prestacion = False
            elif provision_type == 'cesantias' and not tipo_contrato.has_cesantias:
                paga_prestacion = False
            elif provision_type == 'vacaciones' and not tipo_contrato.has_vacaciones:
                paga_prestacion = False
            elif provision_type == 'intereses' and not tipo_contrato.has_intereses_cesantias:
                paga_prestacion = False

            if not paga_prestacion:
                resultado['aplica'] = False
                resultado['motivo'] = f'Tipo contrato {tipo_contrato.name} no paga {provision_type}'
                agregar_validacion('Tipo Contrato', False, f'{tipo_contrato.name} no paga {provision_type}')
                return resultado

            agregar_validacion('Tipo Contrato', True, f'{tipo_contrato.name}')
        else:
            agregar_validacion('Tipo Contrato', True, 'No especificado (aplica estandar)')

        # ========== 6. VALIDAR MODALIDAD SALARIO INTEGRAL ==========
        if provision_type != 'vacaciones' and contract.modality_salary == 'integral':
            resultado['aplica'] = False
            resultado['motivo'] = 'Salario integral no aplica para esta prestacion'
            agregar_validacion('Modalidad Salario', False, 'Integral - no aplica')
            return resultado

        if contract.modality_salary == 'integral':
            agregar_validacion('Modalidad Salario', True, 'Integral (solo vacaciones)')
        else:
            agregar_validacion('Modalidad Salario', True, contract.modality_salary or 'Normal')

        # ========== 7. VALIDAR VIGENCIA DEL CONTRATO ==========
        if slip:
            period_start = slip.date_from
            period_end = slip.date_to

            # Si el contrato termino ANTES del inicio del periodo
            if contract.date_end and contract.date_end < period_start:
                resultado['aplica'] = False
                resultado['motivo'] = f'Contrato termino el {contract.date_end} antes del periodo'
                agregar_validacion('Vigencia Contrato', False, f'Termino {contract.date_end} < {period_start}')
                return resultado

            # Si el contrato inicia DESPUES del fin del periodo
            if contract.date_start > period_end:
                resultado['aplica'] = False
                resultado['motivo'] = f'Contrato inicia el {contract.date_start} despues del periodo'
                agregar_validacion('Vigencia Contrato', False, f'Inicia {contract.date_start} > {period_end}')
                return resultado

            agregar_validacion('Vigencia Contrato', True, f'{contract.date_start} - {contract.date_end or "Indefinido"}')

        # ========== 8. VALIDAR ESTRUCTURA DE PROCESO ==========
        if slip:
            struct_process = slip.struct_process
            if struct_process == 'contrato':
                agregar_validacion('Tipo Proceso', True, 'Liquidacion de contrato')
            elif struct_process == 'nomina':
                agregar_validacion('Tipo Proceso', True, 'Provision mensual')
            else:
                agregar_validacion('Tipo Proceso', True, f'{struct_process}')

        # ========== 9. ADVERTENCIAS (no bloquean) ==========
        # Verificar si hay novedades especiales
        if contract.modality_aux == 'variable':
            resultado['warnings'].append(f'Auxilio variable: se promediara en calculo')

        if contract.only_wage in ('wage_dev', 'wage_dev_exc'):
            resultado['warnings'].append(f'Base incluye devengos salariales (only_wage={contract.only_wage})')

        return resultado

    def _obtener_auxilio_linea_nomina(self, slip, dias_periodo=30):
        """Delegado al método centralizado en hr.salary.rule.aux."""
        return self.env['hr.salary.rule.aux']._obtener_auxilio_linea_nomina(
            slip, dias_periodo=dias_periodo
        )

    def _calcular_auxilio_provision(self, annual_parameters, contract, dias_pagados, dias_periodo=30,
                                      dias_ausencias_no_justificadas=0, date_from=None, date_to=None,
                                      exclude_payslip_id=None, es_provision_simple=False,
                                      metodo_auxilio=None, slip=None):
        """Delegado al método centralizado en hr.salary.rule.aux."""
        return self.env['hr.salary.rule.aux']._calcular_auxilio_provision(
            annual_parameters,
            contract,
            dias_pagados,
            dias_periodo=dias_periodo,
            dias_ausencias_no_justificadas=dias_ausencias_no_justificadas,
            date_from=date_from,
            date_to=date_to,
            exclude_payslip_id=exclude_payslip_id,
            es_provision_simple=es_provision_simple,
            metodo_auxilio=metodo_auxilio,
            slip=slip,
        )

    def _calculate_provision(self, data_payslip, provision_type):
        """
        Función centralizada para calcular provisiones (vacaciones, prima, cesantías, intereses)

        SOPORTA DOS MÉTODOS:
        1. SIMPLE: Cálculo directo con días del período (company.simple_provisions = True)
        2. COMPLEJO: Usa _compute_social_benefits con acumulación (default)

        Args:
            data_payslip (dict): Diccionario con datos de liquidación (localdict)
            provision_type (str): Tipo de provisión ('vacaciones', 'prima', 'cesantias', 'intereses')

        Returns:
            tuple: (base, días, tasa, nombre, False, datos_visuales)
        """
        employee = data_payslip['employee']
        contract = data_payslip['contract']
        slip = data_payslip['slip']
        annual_parameters = data_payslip.get('annual_parameters')
        log_provisions_ctx = self.env.context.get('log_provisions')
        log_provisions = True if log_provisions_ctx is None else bool(log_provisions_ctx)

        if log_provisions:
            _logger.info(
                "PRV[%s] start slip=%s employee=%s contract=%s process=%s simple=%s struct_id=%s struct_name=%s period=%s..%s",
                provision_type,
                slip.id,
                employee.id,
                contract.id,
                slip.struct_process,
                self.env.company.simple_provisions,
                slip.struct_id.id if slip.struct_id else None,
                slip.struct_id.name if slip.struct_id else '',
                slip.date_from,
                slip.date_to,
            )

        # ========== VALIDACION CENTRALIZADA ==========
        # Usa el metodo que acumula todas las condiciones
        validacion = self._validar_condiciones_prestacion(
            provision_type, employee, contract, slip, annual_parameters
        )

        if log_provisions:
            _logger.info(
                "PRV[%s] validacion: aplica=%s motivo=%s validaciones=%d warnings=%d",
                provision_type,
                validacion['aplica'],
                validacion.get('motivo', ''),
                len(validacion.get('validaciones', [])),
                len(validacion.get('warnings', [])),
            )
            # Log detalle de validaciones
            for v in validacion.get('validaciones', []):
                _logger.info(
                    "PRV[%s]   -> %s: %s (%s)",
                    provision_type,
                    v['nombre'],
                    'OK' if v['aplica'] else 'NO',
                    v.get('detalle', ''),
                )

        # Si no aplica, retornar temprano
        if not validacion['aplica']:
            return 0, 0, 0, f'NO APLICA - {validacion.get("motivo", "Ver validacion")}', False, {
                'motivo': validacion.get('motivo', ''),
                'validaciones': validacion.get('validaciones', []),
            }

        # Guardar config_override para usar mas adelante
        config_override = validacion.get('config_override', {})

        # ========== VALIDACION POR TIPO DE CONTRATO ==========
        # El tipo de contrato controla que prestaciones aplican
        if contract.contract_type_id:
            benefits = contract.contract_type_id.get_applicable_benefits()
            # Mapeo de provision_type a campo de beneficio
            benefit_map = {
                'prima': 'prima',
                'cesantias': 'cesantias',
                'intereses': 'intereses_cesantias',
                'vacaciones': 'vacaciones',
            }
            benefit_field = benefit_map.get(provision_type)
            if benefit_field and not benefits.get(benefit_field, True):
                # El tipo de contrato no tiene derecho a esta prestacion
                if log_provisions:
                    _logger.info(
                        "PRV[%s] skipped by contract type=%s benefit=%s",
                        provision_type,
                        contract.contract_type_id.name,
                        benefit_field,
                    )
                return 0, 0, 0, f'NO APLICA ({provision_type})', False, {
                    'motivo': f'Tipo de contrato {contract.contract_type_id.name} no tiene derecho a {provision_type}'
                }

        # Validaciones iniciales legacy - ACTUALIZADO Ley 2466/2025
        # Usa metodo centralizado en prestaciones_helpers.py
        aplica_aprendiz, motivo_aprendiz = self._aprendiz_tiene_prestaciones(
            employee, contract, provision_type
        )
        if not aplica_aprendiz:
            if log_provisions:
                _logger.info(
                    "PRV[%s] skipped: %s",
                    provision_type,
                    motivo_aprendiz,
                )
            return 0, 0, 0, 0, False, {'motivo': motivo_aprendiz}
        elif log_provisions and employee.tipo_coti_id and employee.tipo_coti_id.code in ['12', '19']:
            _logger.info(
                "PRV[%s] aprendiz SENA con prestaciones segun tipo contrato=%s",
                provision_type,
                contract.contract_type_id.name if contract.contract_type_id else 'N/A',
            )

        if provision_type != 'vacaciones' and contract.modality_salary == 'integral':
            if log_provisions:
                _logger.info(
                    "PRV[%s] skipped by integral salary",
                    provision_type,
                )
            return 0, 0, 0, 0, False, {}

        # ========== VALIDACION DE VIGENCIA DEL CONTRATO EN EL PERIODO ==========
        # Solo bloquear si el contrato NO tiene interseccion con el periodo
        # Si hay interseccion parcial, el calculo de dias se ajustara automaticamente
        period_start = slip.date_from
        period_end = slip.date_to

        # Si el contrato termino ANTES del inicio del periodo, no aplica
        if contract.date_end and contract.date_end < period_start:
            if log_provisions:
                _logger.info(
                    "PRV[%s] skipped by contract end %s < %s",
                    provision_type,
                    contract.date_end,
                    period_start,
                )
            return 0, 0, 0, f'NO APLICA - Contrato terminado', False, {
                'motivo': f'Contrato terminó el {contract.date_end}, antes del período {period_start}'
            }

        # Si el contrato inicia DESPUES del fin del periodo, no aplica
        if contract.date_start > period_end:
            if log_provisions:
                _logger.info(
                    "PRV[%s] skipped by contract start %s > %s",
                    provision_type,
                    contract.date_start,
                    period_end,
                )
            return 0, 0, 0, f'NO APLICA - Contrato no iniciado', False, {
                'motivo': f'Contrato inicia el {contract.date_start}, después del período {period_end}'
            }

        # NOTA: Si el contrato termina DENTRO del periodo o inicia DENTRO del periodo,
        # el calculo de dias trabajados ya se ajusta proporcionalmente en WORK100

        # Configuración por tipo - usar PRESTACIONES_CONFIG de config_reglas.py
        # Determinar si es consolidación ANTES de definir config para usar códigos correctos
        es_consolidacion = slip.struct_process == 'consolidacion'
        # Prima NO se consolida, siempre mantiene su código y nombre normal
        # Solo cesantías, intereses y vacaciones tienen códigos de consolidación
        codigo_suffix = '_CONS' if es_consolidacion and provision_type != 'prima' else ''

        # Obtener configuración base desde config_reglas.py
        config_base = PRESTACIONES_CONFIG.get(provision_type, {})
        required_keys = ('campo_base', 'tasa', 'nombre', 'codigo', 'tipo_prest')
        missing_keys = [key for key in required_keys if key not in config_base]
        if not config_base:
            _logger.warning(
                "PRV[%s] PRESTACIONES_CONFIG missing, using defaults.",
                provision_type,
            )
        elif missing_keys:
            _logger.warning(
                "PRV[%s] PRESTACIONES_CONFIG missing keys=%s config=%s",
                provision_type,
                ",".join(missing_keys),
                config_base,
            )

        # Extender con campos específicos para provisiones
        campo_base_legacy = config_base.get('campo_base', 'base_prima')
        config = {
            'campo_base': get_contextual_base_field(campo_base_legacy, contexto='provision'),
            'tasa': config_base.get('tasa', 8.33),
            'nombre': config_base.get('nombre', provision_type.upper()),
            'codigo': f"{config_base.get('codigo', 'PRV')}{codigo_suffix}" if codigo_suffix else config_base.get('codigo', 'PRV'),
            'codigo_base': config_base.get('codigo', 'PRV'),
            'tipo_prest': config_base.get('tipo_prest', provision_type)
        }

        # ========== APLICAR CONFIG_OVERRIDE DE VALIDACION CENTRALIZADA ==========
        # Usa valores del indicador especial si estan disponibles
        if config_override:
            config.update(config_override)
            if log_provisions:
                _logger.info(
                    "PRV[%s] config_override applied: tasa=%.4f%% dias=%.1f base=%d",
                    provision_type,
                    config_override.get('tasa', 0.0),
                    config_override.get('dias_indicador', 0.0),
                    config_override.get('base_dias_indicador', 360),
                )

        if log_provisions:
            _logger.info(
                "PRV[%s] config codigo=%s tasa=%s campo_base=%s tipo_prest=%s",
                provision_type,
                config['codigo'],
                config['tasa'],
                config['campo_base'],
                config['tipo_prest'],
            )

        # ========== OBTENER PARAMETROS DE CONFIGURACION ==========
        config_params = self._get_provision_config_params(annual_parameters)

        # Determinar si descontar suspensiones
        # Para prima: usar prst_wo_susp si esta activo
        descontar_suspensiones = self.descontar_suspensiones
        if provision_type == 'prima' and config_params.get('prst_wo_susp'):
            descontar_suspensiones = False

        # En algunos entornos struct_process no viene poblado en el slip,
        # así que hacemos fallback a la estructura.
        struct_process = slip.struct_process or (slip.struct_id.process if slip.struct_id else '')
        es_liquidacion = struct_process == 'contrato'
        es_provision_mensual = struct_process == 'nomina'

        if log_provisions:
            _logger.info(
                "PRV[%s] config_params=%s descontar_suspensiones=%s",
                provision_type,
                {k: v for k, v in config_params.items() if 'auxilio' in k or 'prst' in k},
                descontar_suspensiones,
            )
            _logger.info(
                "PRV[%s] contract_config modality_aux=%s only_wage=%s not_pay_aux=%s",
                provision_type,
                contract.modality_aux,
                contract.only_wage,
                contract.not_pay_auxtransportation,
            )

        # ========== MÉTODO SIMPLE (RÁPIDO) ==========
        if config_params.get('simple_provisions', self.env.company.simple_provisions):
            # MÉTODO SIMPLE: Usa salario REAL del contrato y devengos del período actual
            # Solo calcula sobre la nómina actual, sin acumulación de períodos anteriores
            is_biweekly, biweekly_part = self._get_biweekly_context(slip)
            force_monthly_days = bool(es_provision_mensual and is_biweekly and biweekly_part == 'second')
            provision_days_method = (
                annual_parameters.provision_days_method
                if annual_parameters and hasattr(annual_parameters, 'provision_days_method')
                else None
            ) or 'periodo'
            provision_quincenal_mode = (
                annual_parameters.provision_quincenal_mode
                if annual_parameters and hasattr(annual_parameters, 'provision_quincenal_mode')
                else None
            ) or 'second_only'
            if provision_days_method == 'worked_days':
                # Si se usan días trabajados, no forzar corte mensual completo.
                force_monthly_days = False

            # Regla negocio: en quincenal, provisiones sólo en segunda quincena.
            if (
                es_provision_mensual
                and is_biweekly
                and biweekly_part == 'first'
                and provision_quincenal_mode == 'second_only'
            ):
                return 0, 0, 0, 'NO APLICA - Primera quincena', False, {
                    'motivo': 'Provisión quincenal configurada para segunda quincena',
                    'quincena': 'first',
                    'regla_aplicada': 'skip_q1_provisions',
                }

            provision_date_from = slip.date_from
            provision_date_to = slip.date_to
            if force_monthly_days:
                # Segunda quincena: calcular todas las provisiones con corte mensual
                # completo para mantener comportamiento uniforme (prima, cesantías,
                # intereses y vacaciones) y evitar diferencias de base por tipo.
                provision_date_from = slip.date_to.replace(day=1)

            # Ajustar fechas de cálculo según vigencia del contrato
            calc_date_from = provision_date_from
            calc_date_to = provision_date_to
            if contract.date_start and contract.date_start > calc_date_from:
                calc_date_from = contract.date_start
            if contract.date_end and contract.date_end < calc_date_to:
                calc_date_to = contract.date_end

            # Calcular días del período (360) y ausencias según configuración
            dias_periodo = days360(calc_date_from, calc_date_to)
            force_monthly_full = force_monthly_days and calc_date_from == provision_date_from and calc_date_to == provision_date_to
            if force_monthly_full:
                dias_periodo = 30
            metodo_dias = 'days360'
            dias_base = dias_periodo
            if log_provisions:
                _logger.info(
                    "PRV[%s] dias_periodo=%s metodo_dias=%s provision_days_method=%s manual_days=%s manual_vac_days=%s quincenal=%s parte=%s",
                    provision_type,
                    dias_periodo,
                    metodo_dias,
                    provision_days_method,
                    slip.manual_days if slip.use_manual_days else None,
                    slip.manual_vacation_days if slip.use_manual_vacation_days else None,
                    is_biweekly,
                    biweekly_part,
                )
            # En quincenal "solo segunda", varias validaciones (dias trabajados/ausencias)
            # deben contemplar también la primera quincena del mismo mes.
            other_slip = False
            if (
                is_biweekly
                and biweekly_part == 'second'
                and provision_quincenal_mode == 'second_only'
            ):
                month_start = slip.date_to.replace(day=1)
                month_mid = slip.date_to.replace(day=15)
                other_slip = self.env['hr.payslip'].search([
                    ('employee_id', '=', employee.id),
                    ('contract_id', '=', contract.id),
                    ('state', '!=', 'cancel'),
                    ('date_from', '>=', month_start),
                    ('date_to', '<=', month_mid),
                    ('id', '!=', slip.id),
                ], limit=1)

            if slip.use_manual_vacation_days and slip.manual_vacation_days and not es_liquidacion:
                dias_base = slip.manual_vacation_days * 24
                metodo_dias = 'manual_vacation_days'
            if slip.use_manual_days and slip.manual_days > 0:
                dias_base = float(slip.manual_days)
                metodo_dias = 'manual_days'
            elif provision_days_method == 'worked_days':
                worked_days = 0.0
                if slip.worked_days_line_ids:
                    # Evitar doble conteo si existen WORK100 y WORK_D en el mismo slip.
                    has_work100 = any(wd.code == 'WORK100' for wd in slip.worked_days_line_ids)
                    preferred_code = 'WORK100' if has_work100 else 'WORK_D'
                    for wd in slip.worked_days_line_ids:
                        if wd.code == preferred_code:
                            worked_days += float(wd.number_of_days or 0.0)
                if (
                    is_biweekly
                    and biweekly_part == 'second'
                    and provision_quincenal_mode == 'second_only'
                ):
                    # En modo "solo segunda quincena", sumar días trabajados de la primera quincena
                    if other_slip:
                        other_worked = self.env['hr.payslip.worked_days'].search([
                            ('payslip_id', '=', other_slip.id),
                            ('code', 'in', ('WORK100', 'WORK_D')),
                        ])
                        other_has_work100 = any(wd.code == 'WORK100' for wd in other_worked)
                        other_preferred = 'WORK100' if other_has_work100 else 'WORK_D'
                        worked_days += sum(
                            float(wd.number_of_days or 0.0)
                            for wd in other_worked
                            if wd.code == other_preferred
                        )
                if worked_days > 0:
                    dias_base = worked_days
                    metodo_dias = 'worked_days'
                else:
                    metodo_dias = 'worked_days_fallback_periodo'
            elif force_monthly_days:
                dias_base = 30.0
                metodo_dias = 'quincenal_second_forzado_30'

            dias_ausencias_pagadas = 0.0
            dias_ausencias_no_remu_descuento = 0.0
            dias_ausencias_no_remu_no_descuento = 0.0
            dias_ausencias_sin_auxilio = 0.0  # Días que NO pagan auxilio de transporte
            slips_for_absences = [slip]
            if other_slip and force_monthly_days:
                slips_for_absences.append(other_slip)

            # Primero intentar con leave_days_ids (método tradicional)
            leave_days_to_scan = []
            for slip_abs in slips_for_absences:
                if slip_abs.leave_days_ids:
                    leave_days_to_scan.extend(slip_abs.leave_days_ids)
            if leave_days_to_scan:
                for ld in leave_days_to_scan:
                    leave = ld.leave_id
                    leave_type = leave.holiday_status_id if leave else None
                    if not leave_type:
                        continue

                    # El work_entry_type_id está en el tipo de ausencia (holiday_status_id)
                    work_entry_type = leave_type.work_entry_type_id if leave_type else None
                    dias = float(ld.days_payslip or 0.0)

                    # Verificar si paga auxilio de transporte
                    paga_auxilio = work_entry_type.pay_transport_allowance if work_entry_type else True
                    if not paga_auxilio:
                        dias_ausencias_sin_auxilio += dias

                    if leave_type.unpaid_absences:
                        descuenta = bool(leave_type.sub_wd) if leave_type.sub_wd is not None else True
                        if provision_type == 'prima' and not leave_type.discounting_bonus_days:
                            descuenta = False
                        if descuenta:
                            dias_ausencias_no_remu_descuento += dias
                        else:
                            dias_ausencias_no_remu_no_descuento += dias
                    else:
                        dias_ausencias_pagadas += dias
            else:
                # Fallback: usar worked_days cuando leave_days_ids está vacío
                # Buscar ausencias en worked_days por código de work_entry_type
                LeaveType = self.env['hr.leave.type']
                for slip_abs in slips_for_absences:
                    for wd in slip_abs.worked_days_line_ids:
                        if wd.code == 'WORK100' or wd.code == 'WORK_D':
                            continue  # Ignorar días trabajados
                        if not wd.work_entry_type_id:
                            continue

                        # Verificar si paga auxilio de transporte
                        paga_auxilio = wd.work_entry_type_id.pay_transport_allowance if wd.work_entry_type_id else True
                        dias = float(wd.number_of_days or 0.0)
                        if not paga_auxilio:
                            dias_ausencias_sin_auxilio += dias

                        # Resolver tipo de ausencia de forma robusta:
                        # 1) vínculo directo en worked_days, 2) código almacenado,
                        # 3) work_entry_type asociado, 4) fallback por código visible.
                        leave_type = False
                        if getattr(wd, 'leave_type_id', False):
                            leave_type = wd.leave_type_id
                        if not leave_type and getattr(wd, 'leave_type_code', False):
                            leave_type = LeaveType.search([('code', '=', wd.leave_type_code)], limit=1)
                        if not leave_type and wd.work_entry_type_id:
                            leave_type = LeaveType.search([('work_entry_type_id', '=', wd.work_entry_type_id.id)], limit=1)
                        if not leave_type and getattr(wd, 'code', False):
                            leave_type = LeaveType.search([('code', '=', wd.code)], limit=1)
                        if not leave_type:
                            continue
                        if leave_type.unpaid_absences:
                            descuenta = bool(leave_type.sub_wd) if leave_type.sub_wd is not None else True
                            if provision_type == 'prima' and not leave_type.discounting_bonus_days:
                                descuenta = False
                            if descuenta:
                                dias_ausencias_no_remu_descuento += dias
                            else:
                                dias_ausencias_no_remu_no_descuento += dias
                        else:
                            dias_ausencias_pagadas += dias

            # LOGICA CORREGIDA:
            # Dias pagados = Periodo - Ausencias no pagadas que descuentan (si config activo)
            # Las ausencias PAGADAS no afectan porque ya estan remuneradas
            # Las ausencias NO PAGADAS que NO descuentan tampoco afectan

            # ========== CALCULAR SALARIO CONSIDERANDO CAMBIOS Y AUSENCIAS ==========
            # Usa el metodo que calcula por franjas si hubo cambio de salario
            # Solo detectar cambios si promedio_detectar_cambios esta activo
            detectar_cambios = config_params.get('promedio_detectar_cambios', True)
            ignorar_ausencias = config_params.get('prst_wo_absences', False)
            dias_ausencias_no_remu_descuento_calc = 0.0 if ignorar_ausencias else dias_ausencias_no_remu_descuento

            resultado_salario = self.env['hr.salary.rule.basic']._calcular_salario_periodo_con_cambios(
                contract, slip,
                calc_date_from, calc_date_to,
                dias_ausencias_no_pagadas=dias_ausencias_no_remu_descuento_calc,
                descontar_suspensiones=descontar_suspensiones,
                detectar_cambios_salario=detectar_cambios,
                annual_parameters=annual_parameters
            )

            salario_periodo = resultado_salario['salario_total']
            dias_pagados = resultado_salario['dias_pagados']
            salario_base_mensual = resultado_salario['salario_mensual_actual']
            franjas_salario = resultado_salario.get('franjas', [])
            hubo_cambio_salario = resultado_salario.get('hubo_cambio_salario', False)

            if log_provisions:
                _logger.info(
                    "PRV[%s] salario_periodo=%s salario_base_mensual=%s dias_pagados=%s hubo_cambio=%s",
                    provision_type,
                    salario_periodo,
                    salario_base_mensual,
                    dias_pagados,
                    hubo_cambio_salario,
                )

            # IMPORTANTE: Cuando se usan dias manuales, usar el salario BASE del contrato
            # (sin factores de subcontrato/parcial) proporcionalizado por los dias manuales.
            # Esto asegura que las provisiones sean consistentes con el sueldo pagado (BASIC005).
            # Formula: wage / 30 * manual_days (igual que BASIC005 en basic.py)
            if slip.use_manual_days and slip.manual_days > 0:
                wage_base = contract.wage or 0
                salario_manual_calculado = (wage_base / 30.0) * float(slip.manual_days)
                if log_provisions:
                    _logger.info(
                        "PRV[%s] Dias manuales: wage=%s / 30 * %s = %s",
                        provision_type, wage_base, slip.manual_days, salario_manual_calculado
                    )
                salario_periodo = salario_manual_calculado
                salario_base_mensual = wage_base

            if dias_pagados <= 0 and slip.struct_process in ['vacaciones', 'ausencias']:
                dias_pagados = dias_periodo
                salario_periodo = (salario_base_mensual / 30.0) * dias_pagados
            if force_monthly_full:
                # En segunda quincena quincenal usamos 30 dias solo cuando no hay
                # descuento efectivo de ausencias no pagadas por configuracion de regla.
                # Si la regla descuenta suspensiones y hay dias a descontar,
                # se conserva el resultado proporcional calculado previamente.
                if not (descontar_suspensiones and dias_ausencias_no_remu_descuento_calc > 0):
                    dias_pagados = 30.0
                    salario_periodo = salario_base_mensual
            dias_pagados = max(dias_pagados, 0)

            # dias_computables se mantiene para compatibilidad pero ahora es dias_pagados
            dias_computables = dias_pagados
            if provision_days_method == 'worked_days' and dias_base > 0:
                # Consistencia: cuando se usan días trabajados, la base y los días deben
                # reflejar los días trabajados reales (del mes si aplica).
                dias_pagados = float(dias_base)
                dias_computables = dias_pagados
                if salario_base_mensual:
                    salario_periodo = (salario_base_mensual / 30.0) * dias_pagados
                # En modo "solo segunda quincena", mostrar periodo mensual completo
                if is_biweekly and provision_quincenal_mode == 'second_only':
                    dias_periodo = 30

            # ========== PARAMETROS ADICIONALES ==========
            salario_minimo_mensual = annual_parameters.smmlv_monthly if annual_parameters else 0
            auxilio_transporte_mensual = annual_parameters.transportation_assistance_monthly if annual_parameters else 0
            if not annual_parameters:
                _logger.warning(
                    "PRV[%s] annual_parameters missing; smmlv/transport set to 0",
                    provision_type,
                )

            # ========== SUMAR DEVENGOS DEL PERIODO SEGUN CAMPO BASE ==========
            # Separar salario del período y variables marcadas como base
            base_salario_total = 0.0
            variable_total = 0.0
            variable_mensual = 0.0
            variable_total_tope = 0.0
            variable_mensual_tope = 0.0
            devengos_ausencias = 0.0
            variable_leave_total = 0.0
            conceptos_incluidos = []

            campo_base = config.get('campo_base') or 'base_prima'

            # Categorías incluidas forzadamente (excepción a los flags base_*)
            # COMISIONES y HEYREC siempre se incluyen en la base.
            categorias_incluidas = {'COMISIONES', 'HEYREC'}

            # MÉTODO 1: Iterar sobre localdict['rules'] (YA CONTIENE ACUMULADOS)
            # Patrón tomado de ibd_sss.py líneas 736-843
            rules = data_payslip.get('rules', {})

            for _, rule_data in rules.items():
                rule = rule_data.rule
                if not rule:
                    continue

                # Obtener monto y categoría
                amount = rule_data.total
                cat = rule.category_id

                # Para prima/vacaciones, permitir ausencias/deducciones negativas
                # marcadas en base de provisión (se toman en valor absoluto).
                incluir_ausencia_negativa = (
                    amount < 0
                    and provision_type in ('prima', 'vacaciones')
                    and bool(getattr(rule, 'is_leave', False))
                )

                # Excluir reglas sin monto positivo salvo la excepción anterior.
                if amount <= 0 and not incluir_ausencia_negativa:
                    if log_provisions:
                        _logger.info(
                            "PRV[%s] excluida code=%s total=%s motivo=total_no_positivo",
                            provision_type,
                            rule.code,
                            amount,
                        )
                    continue

                # ==== Excluir BASIC y AUX ====
                es_basic = cat and cat.code == 'BASIC'
                es_aux = cat and (cat.code == 'AUX' or (cat.parent_id and cat.parent_id.code == 'AUX'))
                if es_basic or es_aux:
                    if log_provisions:
                        _logger.info(
                            "PRV[%s] excluida code=%s total=%s motivo=categoria_%s",
                            provision_type,
                            rule.code,
                            amount,
                            'BASIC' if es_basic else 'AUX',
                        )
                    continue

                # ==== Verificar si aplica para el campo_base o categoría ====
                aplica_base = False
                try:
                    if campo_base in rule._fields:
                        aplica_base = getattr(rule, campo_base)
                except (AttributeError, KeyError):
                    aplica_base = False

                if not aplica_base and cat and cat.code in categorias_incluidas:
                    aplica_base = True
                    if log_provisions:
                        _logger.info(
                            "PRV[%s] incluida por categoria: code=%s total=%s categoria=%s",
                            provision_type,
                            rule.code,
                            amount,
                            cat.code,
                        )

                if not aplica_base:
                    if log_provisions:
                        _logger.info(
                            "PRV[%s] excluida code=%s total=%s motivo=no_campo_base campo_base=%s",
                            provision_type,
                            rule.code,
                            amount,
                            campo_base,
                        )
                    continue

                variable_total += abs(amount)
                if getattr(rule, 'is_leave', False):
                    variable_leave_total += abs(amount)
                conceptos_incluidos.append({
                    'codigo': rule.code,
                    'nombre': rule.name,
                    'valor': abs(amount),
                    'campo_base': campo_base,
                    'categoria': cat.code if cat else '',
                    'es_ausencia': bool(getattr(rule, 'is_leave', False)),
                })

                if log_provisions:
                    _logger.info(
                        "PRV[%s] incluida code=%s total=%s categoria=%s campo_base=%s",
                        provision_type,
                        rule.code,
                        amount,
                        cat.code if cat else '',
                        campo_base,
                    )

            # Si es quincenal y en segunda quincena (modo second_only), sumar variables de otros slips del mes
            # para evitar perder devengos de la primera quincena en la base mensual.
            if is_biweekly and biweekly_part == 'second' and provision_quincenal_mode == 'second_only':
                month_start = slip.date_to.replace(day=1)
                otros_slips_domain = [
                    ('employee_id', '=', employee.id),
                    ('contract_id', '=', contract.id),
                    ('id', '!=', slip.id),
                    ('state', 'in', ['done', 'paid', 'verify']),
                    ('date_from', '>=', month_start),
                    ('date_to', '<=', slip.date_to),
                ]
                otros_slips = self.env['hr.payslip'].search(otros_slips_domain)
                otros_vars_total = 0.0

                for other_slip in otros_slips:
                    for line in other_slip.line_ids:
                        rule = line.salary_rule_id
                        if not rule:
                            continue

                        amount = line.total
                        incluir_ausencia_negativa = (
                            amount < 0
                            and provision_type in ('prima', 'vacaciones')
                            and bool(getattr(rule, 'is_leave', False))
                        )
                        if amount <= 0 and not incluir_ausencia_negativa:
                            continue

                        cat = line.category_id
                        es_basic = cat and cat.code == 'BASIC'
                        es_aux = cat and (cat.code == 'AUX' or (cat.parent_id and cat.parent_id.code == 'AUX'))
                        if es_basic or es_aux:
                            continue

                        aplica_base = False
                        try:
                            if campo_base in rule._fields:
                                aplica_base = getattr(rule, campo_base)
                        except (AttributeError, KeyError):
                            aplica_base = False

                        if not aplica_base and cat and cat.code in categorias_incluidas:
                            aplica_base = True

                        if not aplica_base:
                            continue

                        otros_vars_total += abs(amount)
                        if getattr(rule, 'is_leave', False):
                            variable_leave_total += abs(amount)
                        conceptos_incluidos.append({
                            'codigo': rule.code,
                            'nombre': rule.name,
                            'valor': abs(amount),
                            'campo_base': campo_base,
                            'categoria': cat.code if cat else '',
                            'es_ausencia': bool(getattr(rule, 'is_leave', False)),
                            'origen': f"slip:{other_slip.id}",
                        })

                if otros_vars_total:
                    variable_total += otros_vars_total
                    if log_provisions:
                        _logger.info(
                            "PRV[%s] variables otros slips mes=%s total=%s ids=%s",
                            provision_type,
                            month_start,
                            otros_vars_total,
                            otros_slips.ids,
                        )

            if dias_computables:
                variable_mensual = (variable_total / dias_computables) * 30.0
                variable_mensual_tope = (variable_total_tope / dias_computables) * 30.0

            # PRV_VAC incluye conceptos marcados con base_vacaciones.
            # Esto permite que reglas de incapacidad configuradas como base
            # sumen a la provisión de vacaciones.

            if log_provisions:
                _logger.info(
                    "PRV[%s] variables total=%s mensual=%s tope=%s conceptos=%s",
                    provision_type,
                    variable_total,
                    variable_mensual,
                    variable_total_tope,
                    len(conceptos_incluidos),
                )

            # Si se usan dias manuales, proporcionalizar las variables tambien
            # Las variables (comisiones, etc.) se calculan sobre el periodo completo
            # pero deben proporcionalizarse segun dias_pagados/dias_periodo
            variable_proporcionalizada = variable_total
            if slip.use_manual_days and slip.manual_days > 0 and dias_periodo > 0:
                factor_proporcion = float(dias_pagados) / float(dias_periodo)
                variable_proporcionalizada = variable_total * factor_proporcion
                if log_provisions and variable_total > 0:
                    _logger.info(
                        "PRV[%s] Variables proporcionalizadas: %s * %s = %s",
                        provision_type, variable_total, factor_proporcion, variable_proporcionalizada
                    )
            elif provision_days_method == 'worked_days':
                # Con días trabajados, usar variables reales del periodo/mes sin escalar.
                variable_proporcionalizada = variable_total

            # En provisión mensual quincenal (segunda quincena), cuando prima/vacaciones
            # incluyen novedades de ausencia en variables, se evita doble conteo:
            # salario_base_del_mes - ausencias_en_variables + variables.
            salario_periodo_base = salario_periodo
            if (
                provision_type in ('prima', 'vacaciones')
                and es_provision_mensual
                and force_monthly_days
                and provision_days_method != 'worked_days'
                and variable_leave_total > 0
            ):
                salario_periodo_base = max(0.0, salario_periodo - variable_leave_total)
                if log_provisions:
                    _logger.info(
                        "PRV[%s] ajuste_no_doble_conteo salario=%s leave_vars=%s salario_base=%s",
                        provision_type,
                        salario_periodo,
                        variable_leave_total,
                        salario_periodo_base,
                    )

            # Mantener consistencia en fórmulas/visualización con la base realmente usada.
            salario_periodo = salario_periodo_base
            base_salario_total = salario_periodo_base + variable_proporcionalizada

            # ========== AUXILIO TRANSPORTE SEGUN TIPO DE PROVISION ==========
            # Usa configuracion de res.config.settings para cada tipo:
            # - prima_incluye_auxilio (default True)
            # - cesantias_incluye_auxilio (default True)
            # - vacaciones_incluye_auxilio (default False)
            # Y respeta contract.modality_aux:
            # - 'basico': Sin variacion (valor completo si trabajo todos los dias)
            # - 'variable': Proporcionar segun dias pagados
            # - 'no': Sin auxilio
            auxilio_transporte = 0.0
            auxilio_info = {'auxilio': 0, 'auxilio_mensual': 0, 'modality_aux': 'no', 'proporcion': 0}
            aplica_auxilio = False
            auxilio_validacion = {}
            auxilio_desde_slips_mes = False

            if annual_parameters:
                # Validar con tope de 2 SMMLV considerando only_wage del contrato
                salario_variable_tope = variable_mensual
                if contract.only_wage == 'wage_dev_exc':
                    salario_variable_tope = variable_mensual_tope

                auxilio_validacion = self._provision_incluye_auxilio(
                    provision_type,
                    config_params,
                    contract,
                    salario_base_mensual,
                    salario_minimo_mensual,
                    salario_variable=float(salario_variable_tope),  # Para validacion con only_wage
                    employee=employee,
                    annual_parameters=annual_parameters,
                    return_detail=True
                )
                aplica_auxilio = auxilio_validacion.get('aplica', False)
                if log_provisions:
                    _logger.info(
                        "PRV[%s] aplica_auxilio=%s salario_base=%s salario_min=%s variable=%s only_wage=%s",
                        provision_type,
                        aplica_auxilio,
                        salario_base_mensual,
                        salario_minimo_mensual,
                        salario_variable_tope,
                        contract.only_wage
                    )
                    if aplica_auxilio:
                        # MÉTODO SIMPLE: Extraer auxilio directamente de localdict['rules']
                        # Buscar reglas de categoría AUX o con es_auxilio_transporte=True
                        rules = data_payslip.get('rules', {})
                        auxilio_transporte = 0.0
                        dias_auxilio = 0.0
                        codigo_auxilio = None
                        razon_auxilio = None

                        for _, rule_data in rules.items():
                            rule = rule_data.rule
                            if not rule:
                                continue

                            es_auxilio = False
                            razon = ''

                            # Verificar por categoría AUX
                            if rule.category_id:
                                cat = rule.category_id
                                if cat.code == 'AUX':
                                    es_auxilio = True
                                    razon = f'categoria AUX'
                                elif cat.parent_id and cat.parent_id.code == 'AUX':
                                    es_auxilio = True
                                    razon = f'subcategoria de AUX'

                            # Verificar por campo es_auxilio_transporte
                            if not es_auxilio and hasattr(rule, 'es_auxilio_transporte') and rule.es_auxilio_transporte:
                                es_auxilio = True
                                razon = 'es_auxilio_transporte=True'

                            if es_auxilio:
                                auxilio_transporte += abs(rule_data.total or 0)
                                dias_auxilio += abs(rule_data.quantity or 0)
                                if not codigo_auxilio:
                                    codigo_auxilio = rule.code
                                    razon_auxilio = razon

                        if auxilio_transporte > 0:
                            auxilio_mensual_calc = (auxilio_transporte / dias_auxilio * 30) if 0 < dias_auxilio < 30 else auxilio_transporte

                            # En quincenal (solo segunda), usar el AUX real acumulado del mes
                            # (1Q + 2Q) para evitar mensualización forzada que confunde al cliente.
                            if (
                                force_monthly_days
                                and is_biweekly
                                and biweekly_part == 'second'
                                and provision_quincenal_mode == 'second_only'
                            ):
                                aux_mes_acumulado = auxilio_transporte
                                if other_slip:
                                    for pl in other_slip.line_ids:
                                        if not pl.salary_rule_id:
                                            continue
                                        rule_prev = pl.salary_rule_id
                                        cat_prev = rule_prev.category_id
                                        es_aux_prev = False
                                        if cat_prev and (
                                            cat_prev.code == 'AUX'
                                            or (cat_prev.parent_id and cat_prev.parent_id.code == 'AUX')
                                        ):
                                            es_aux_prev = True
                                        if not es_aux_prev and getattr(rule_prev, 'es_auxilio_transporte', False):
                                            es_aux_prev = True
                                        if es_aux_prev and pl.total:
                                            aux_mes_acumulado += abs(float(pl.total or 0.0))

                                if aux_mes_acumulado > 0:
                                    auxilio_transporte = aux_mes_acumulado
                                    auxilio_mensual_calc = aux_mes_acumulado
                                    # Mostrar días reales de referencia del mes (trabajados acumulados)
                                    if dias_base > 0:
                                        dias_auxilio = dias_base
                                    auxilio_desde_slips_mes = True

                            # En quincenal segunda, usar auxilio proporcional al periodo completo.
                            # Si la regla descuenta suspensiones y hubo ausencias no pagadas
                            # efectivas, prorratear por dias_pagados (no por 30 fijos).
                            if force_monthly_days and not auxilio_desde_slips_mes:
                                dias_aux_periodo = dias_periodo
                                if descontar_suspensiones and dias_ausencias_no_remu_descuento_calc > 0:
                                    dias_aux_periodo = dias_pagados
                                if dias_periodo < 30:
                                    auxilio_transporte = auxilio_mensual_calc * (dias_aux_periodo / 30.0)
                                else:
                                    auxilio_transporte = (
                                        auxilio_mensual_calc
                                        if dias_aux_periodo >= 30
                                        else auxilio_mensual_calc * (dias_aux_periodo / 30.0)
                                    )

                            # Si el método es por días trabajados, usar los días computables reales del mes
                            # Solo en segunda quincena cuando la provisión es "solo segunda 15na"
                            if (
                                provision_days_method == 'worked_days'
                                and dias_base > 0
                                and is_biweekly
                                and biweekly_part == 'second'
                                and provision_quincenal_mode == 'second_only'
                                and not auxilio_desde_slips_mes
                            ):
                                auxilio_transporte = auxilio_mensual_calc * (dias_base / 30.0)
                                dias_auxilio = dias_base

                            proporcion = (auxilio_transporte / auxilio_transporte_mensual) if auxilio_transporte_mensual > 0 else 0
                            auxilio_info = {
                                'auxilio': auxilio_transporte,
                                'auxilio_mensual': auxilio_mensual_calc,
                                'modality_aux': contract.modality_aux or 'basico',
                                'proporcion': proporcion,
                                'dias_usados': dias_auxilio,
                                'metodo': 'rules_dict_worked_days' if provision_days_method == 'worked_days' else ('rules_dict_monthly' if force_monthly_days else 'rules_dict'),
                                'fuente': 'localdict_rules'
                            }

                        if log_provisions:
                            _logger.info(
                                "PRV[%s] auxilio desde rules: codigo=%s monto=%s dias=%s razon=%s",
                                provision_type,
                                codigo_auxilio,
                                auxilio_transporte,
                                dias_auxilio,
                                razon_auxilio
                            )
                    else:
                        # No se encontró auxilio en rules
                        auxilio_transporte = 0.0
                        auxilio_info = {
                            'auxilio': 0.0,
                            'auxilio_mensual': auxilio_transporte_mensual,
                            'modality_aux': contract.modality_aux or 'basico',
                            'proporcion': 0,
                            'dias_usados': 0,
                            'metodo': 'rules_no_encontrado',
                            'fuente': 'localdict_rules'
                        }
                        if log_provisions:
                            _logger.warning(
                                "PRV[%s] NO se encontró auxilio en rules dict para slip %s",
                                provision_type,
                                slip.id
                            )

                if (
                    aplica_auxilio
                    and contract.full_auxtransportation_settlement
                    and slip.struct_id.process == 'contrato'
                    and auxilio_transporte_mensual > 0
                ):
                    # En liquidación, usar valor mensual completo del auxilio
                    auxilio_transporte = auxilio_transporte_mensual
                    auxilio_info.update({
                        'auxilio': auxilio_transporte,
                        'auxilio_mensual': auxilio_transporte_mensual,
                        'modality_aux': contract.modality_aux or 'basico',
                        'proporcion': 1,
                        'dias_usados': 30,
                        'fuente': 'full_settlement',
                    })


            # Base total = Salario proporcional + Variables + Auxilio transporte
            base_total = base_salario_total + auxilio_transporte

            if log_provisions:
                # Detectar si hay otras nominas en el mismo periodo (posible nomina adicional)
                adicional_domain = [
                    ('employee_id', '=', employee.id),
                    ('contract_id', '=', contract.id),
                    ('id', '!=', slip.id),
                    ('state', 'in', ['done', 'paid']),
                    ('date_from', '>=', slip.date_from),
                    ('date_to', '<=', slip.date_to),
                ]
                otros_slips = self.env['hr.payslip'].search(adicional_domain)
                _logger.info(
                    "PRV[%s] otros_slips_periodo=%s ids=%s",
                    provision_type,
                    len(otros_slips),
                    otros_slips.ids,
                )

            if log_provisions:
                _logger.info(
                    "PRV[%s] auxilio=%s base_salario_total=%s base_total=%s",
                    provision_type,
                    auxilio_transporte,
                    base_salario_total,
                    base_total,
                )

            totaldev_line = 0.0
            for line in slip.line_ids:
                if (line.code or '').upper() == 'TOTALDEV':
                    totaldev_line += line.total or 0.0
            if totaldev_line and base_salario_total > totaldev_line * 1.05:
                _logger.warning(
                    "PRV[%s] base_salario_total=%s > TOTALDEV=%s (check base flags)",
                    provision_type,
                    base_salario_total,
                    totaldev_line,
                )
            if log_provisions:
                _logger.info(
                    "PRV[%s] simple base_total=%s base_salario_total=%s salario_periodo=%s variable=%s aux=%s dias=%s totaldev=%s conceptos=%s",
                    provision_type,
                    base_total,
                    base_salario_total,
                    salario_periodo,
                    variable_total,
                    auxilio_transporte,
                    dias_computables,
                    totaldev_line,
                    len(conceptos_incluidos),
                )
                _logger.info(
                    "PRV[%s] resumen_lineas slip=%s total_lineas=%s",
                    provision_type,
                    slip.id,
                    len(slip.line_ids),
                )

            # Calcular provisión según tipo usando PORCENTAJES DE LEY
            # IMPORTANTE: Método SIMPLE usa porcentajes fijos según legislación colombiana:
            # - Prima: 8.33% (1 mes por año = 1/12 = 8.33%)
            # - Cesantías: 8.33% (1 mes por año)
            # - Vacaciones: 4.17% (15 días hábiles por año = 15/360 = 4.17%)
            # - Intereses: 12% sobre el valor de cesantías
            #
            # base_total ya está proporcionalizado a los días trabajados del período,
            # por lo que aplicamos el porcentaje directo sin usar días.
            base_cesantias = 0
            cesantias_proporcionales = 0

            # Obtener tasas desde configuracion PRESTACIONES_CONFIG
            tasa_provision = config['tasa']  # Tasa especifica para este tipo
            # Obtener las otras tasas para mostrar en data_visual
            tasas_legales = {
                'prima': PRESTACIONES_CONFIG['prima']['tasa'],
                'cesantias': PRESTACIONES_CONFIG['cesantias']['tasa'],
                'vacaciones': PRESTACIONES_CONFIG['vacaciones']['tasa'],
                'intereses': PRESTACIONES_CONFIG['intereses']['tasa'],
            }

            if provision_type == 'intereses':
                # CORRECCIÓN: Usar PRV_ICES_DATA de localdict que ya fue calculado por _prv_ces
                # valor_cesantias YA es el valor proporcional de cesantías del período
                # NO se debe proporcionalizar de nuevo
                prv_ices_data = data_payslip.get('PRV_ICES_DATA', {})
                cesantias_proporcionales = prv_ices_data.get('valor_cesantias', 0)

                # Si no hay datos de PRV_ICES_DATA, intentar buscar en rules como fallback
                if not cesantias_proporcionales:
                    rules = data_payslip.get('rules')
                    prv_ces_rule = rules.get('PRV_CES') if rules else None
                    if prv_ces_rule:
                        # PRV_CES.total ya es el valor proporcional de cesantías
                        cesantias_proporcionales = abs(prv_ces_rule.total)

                # Intereses = cesantías × 12%
                # Retornamos cesantias_proporcionales como amount y rate=12 para que Odoo aplique el 12%
                valor_provision = cesantias_proporcionales
                base_total = cesantias_proporcionales  # Para mostrar en el display
            elif provision_type == 'prima':
                # Prima: 8.33% del salario base
                # Legislación colombiana: 1 mes de salario por año = 8.33% mensual
                valor_provision = base_total * (tasa_provision / 100)
            elif provision_type == 'cesantias':
                # Cesantías: 8.33% del salario base
                # Legislación colombiana: 1 mes de salario por año = 8.33% mensual
                valor_provision = base_total * (tasa_provision / 100)
            elif provision_type == 'vacaciones':
                # Vacaciones: 4.17% del salario base
                # Legislación colombiana: 15 días hábiles por año = 4.17% mensual
                valor_provision = base_total * (tasa_provision / 100)
            else:
                # Por defecto: aplicar tasa de configuración
                valor_provision = base_total * (config['tasa'] / 100)

            # Saldo contable y liquidación
            # Para consolidación, usar código base para buscar saldo contable
            codigo_saldo = config['codigo_base'] if es_consolidacion else config['codigo']
            saldo_contable = self._obtener_saldo_contable_provision(data_payslip, codigo_saldo) or 0.0
            es_liquidacion = slip.struct_process == 'contrato'
            valor_liquidacion = None
            if es_liquidacion:
                valor_liquidacion = self._obtener_valor_liquidacion(data_payslip, provision_type)
                # Asegurar que valor_liquidacion sea un número
                if valor_liquidacion is None:
                    valor_liquidacion = 0.0

            # ========== DATOS DE VISUALIZACION DETALLADOS ==========
            # Estructura mejorada para mostrar informacion completa en widget

            # Seccion 1: Resumen ejecutivo
            resumen = {
                'tipo_provision': provision_type.upper(),
                'metodo_calculo': 'SIMPLE',
                'periodo': f"{slip.date_from} al {slip.date_to}",
                'empleado': slip.employee_id.name if slip.employee_id else '',
                'contrato': contract.sequence if contract else '',
                'base_total': base_total,
                'valor_provision': valor_provision,
                'tasa_aplicada': tasa_provision,
                'provision_acumulada': 0.0,
                'saldo_contable': saldo_contable,
                'saldo_anterior': saldo_contable,
                'ajuste': 0.0,
                'es_liquidacion': es_liquidacion,
            }

            # Seccion 2: Desglose de salario
            # Para visualización siempre mostrar el salario realmente usado en la base del período.
            # El salario mensual de referencia se conserva en `salario_base_mensual_real`.
            salario_base_display = salario_periodo
            desglose_salario = {
                'salario_base_mensual': salario_base_display,
                'salario_base_mensual_real': salario_base_mensual,
                'salario_periodo': salario_periodo,
                'dias_periodo': dias_periodo,
                'dias_pagados': dias_pagados,
                'variable_total': variable_total,
                'variable_mensual': variable_mensual,
                'hubo_cambio_salario': hubo_cambio_salario,
                'detalle_franjas': franjas_salario if hubo_cambio_salario else [],
            }

            # Seccion 3: Configuracion de auxilio transporte
            # Obtener etiquetas dinamicamente desde las opciones del modelo
            contract_labels = self._get_contract_labels(contract)
            # Determinar base para validacion de tope segun only_wage (logica centralizada)
            only_wage = contract.only_wage or 'wage'
            base_validacion_tope = self.env['hr.salary.rule.aux']._calcular_base_validacion_tope(
                only_wage, salario_base_mensual, variable_mensual,
                variable_tope=variable_mensual_tope
            )

            config_auxilio = {
                'aplica': aplica_auxilio,
                'razon_no_aplica': '',
                'modality_aux': contract.modality_aux or 'basico',
                'modality_aux_label': contract_labels['modality_aux_label'],
                'only_wage': only_wage,
                'only_wage_label': contract_labels['only_wage_label'],
                'not_pay_auxtransportation': contract.not_pay_auxtransportation,
                'not_validate_top_auxtransportation': contract.not_validate_top_auxtransportation,
                'auxilio_mensual_legal': auxilio_transporte_mensual,
                'auxilio_aplicado': auxilio_transporte,
                'smmlv': salario_minimo_mensual,
                'dos_smmlv': 2 * salario_minimo_mensual,
                'base_validacion_tope': base_validacion_tope,
                'supera_tope': base_validacion_tope >= 2 * salario_minimo_mensual,
                # Detalle del calculo de auxilio
                'calculo_detalle': auxilio_info,
            }

            # Determinar razon por la que no aplica auxilio
            if not aplica_auxilio:
                if auxilio_validacion.get('razon'):
                    config_auxilio['razon_no_aplica'] = auxilio_validacion['razon']
                elif provision_type == 'intereses':
                    config_auxilio['razon_no_aplica'] = 'Intereses se calcula sobre cesantias (que ya incluye auxilio si aplica)'
                elif contract.not_pay_auxtransportation:
                    config_auxilio['razon_no_aplica'] = 'Contrato marcado como "No liquidar auxilio de transporte"'
                elif contract.modality_aux == 'no':
                    config_auxilio['razon_no_aplica'] = 'Modalidad de auxilio configurada como "Sin auxilio"'
                elif not config_params.get(f'{provision_type}_incluye_auxilio', False):
                    config_auxilio['razon_no_aplica'] = f'Configuracion global: {provision_type} no incluye auxilio'
                elif config_auxilio['supera_tope']:
                    config_auxilio['razon_no_aplica'] = (
                        f'Salario ({config_auxilio["base_validacion_tope"]:,.0f}) '
                        f'supera 2 SMMLV ({config_auxilio["dos_smmlv"]:,.0f})'
                    )

            # Seccion 4: Configuracion de parametros globales
            config_global = {
                'metodo_simple_activo': True,
                'descontar_suspensiones': descontar_suspensiones,
                'descontar_suspensiones_original': self.descontar_suspensiones,
                'prst_wo_susp_activo': config_params.get('prst_wo_susp', False),
                'prst_wo_absences_activo': config_params.get('prst_wo_absences', False),
                'promedio_detectar_cambios': config_params.get('promedio_detectar_cambios', True),
                # Configuracion por tipo de provision
                'prima_incluye_auxilio': config_params.get('prima_incluye_auxilio', True),
                'cesantias_incluye_auxilio': config_params.get('cesantias_incluye_auxilio', True),
                'vacaciones_incluye_auxilio': config_params.get('vacaciones_incluye_auxilio', False),
                'aux_prst': config_params.get('aux_prst', False),
                # Tasas legales desde configuracion
                'tasa_prima': tasas_legales['prima'],
                'tasa_cesantias': tasas_legales['cesantias'],
                'tasa_vacaciones': tasas_legales['vacaciones'],
                'tasa_intereses': tasas_legales['intereses'],
            }

            # Seccion 5: Desglose de ausencias
            desglose_ausencias = {
                'dias_ausencias_pagadas': dias_ausencias_pagadas,
                'dias_ausencias_no_pagadas': dias_ausencias_no_remu_descuento,
                'dias_ausencias_no_descuentan': dias_ausencias_no_remu_no_descuento,
                'total_ausencias': dias_ausencias_pagadas + dias_ausencias_no_remu_descuento + dias_ausencias_no_remu_no_descuento,
                'efecto_en_calculo': (
                    'Ausencias ignoradas por configuración'
                    if ignorar_ausencias
                    else (
                        f'Se descuentan {dias_ausencias_no_remu_descuento:.0f} dias no pagados'
                        if dias_ausencias_no_remu_descuento > 0 else 'Sin ausencias que afecten'
                    )
                ),
            }

            # Seccion 6: Conceptos variables incluidos
            tabla_conceptos = []
            for concepto in conceptos_incluidos:
                tabla_conceptos.append({
                    'codigo': concepto.get('codigo', ''),
                    'nombre': concepto.get('nombre', ''),
                    'valor': concepto.get('valor', 0),
                    'campo_base': concepto.get('campo_base', campo_base),
                    'es_ausencia': concepto.get('es_ausencia', False),
                    'categoria': concepto.get('categoria', ''),
                })

            # Datos de visualización - estructura principal
            data_visual = {
                'metodo': 'simple',
                # Valores principales (compatibilidad)
                'base_total': base_total,
                'base_salario_total': base_salario_total,
                'salario_base_mensual': salario_base_display,
                'salario_periodo': salario_periodo,
                'variable_total': variable_total,
                'variable_mensual': variable_mensual,
                'devengos_ausencias': devengos_ausencias,
                'salario_minimo_mensual': salario_minimo_mensual,
                'auxilio_transporte_mensual': auxilio_info.get('auxilio_mensual', auxilio_transporte_mensual),
                'auxilio_transporte_periodo': auxilio_transporte,
                'aplica_auxilio_transporte': aplica_auxilio,
                # Informacion detallada del auxilio segun modality_aux
                'auxilio_modality': auxilio_info.get('modality_aux', 'basico'),
                'auxilio_proporcion': auxilio_info.get('proporcion', 0),
                'auxilio_dias_usados': auxilio_info.get('dias_usados', 0),
                'auxilio_dias_descontados': auxilio_info.get('dias_descontados', 0),
                # Campos explícitos para UI/JSON legible
                'salario_dias_display': dias_pagados,
                'auxilio_dias_display': auxilio_info.get('dias_usados', dias_pagados),
                'dias_periodo': dias_periodo,
                'dias_base': dias_base,
                'dias_pagados': dias_pagados,
                'dias_ausencias_pagadas': dias_ausencias_pagadas,
                'dias_ausencias_no_pagadas': dias_ausencias_no_remu_descuento,
                'dias_ausencias_no_descuentan': dias_ausencias_no_remu_no_descuento,
                'dias_computables': dias_computables,
                'metodo_dias': metodo_dias,
                'conceptos_incluidos': conceptos_incluidos,
                'saldo_contable': saldo_contable,
                'saldo_anterior': saldo_contable,
                'provision_acumulada': 0.0,
                'ajuste': 0.0,
                'es_liquidacion': es_liquidacion,
                'valor_liquidacion': valor_liquidacion or 0.0,
                'descontar_suspensiones': descontar_suspensiones,
                'campo_base_filtro': campo_base,
                'hubo_cambio_salario': hubo_cambio_salario,
                'franjas_salario': franjas_salario,
                # ========== SECCIONES DETALLADAS PARA WIDGET ==========
                'resumen': resumen,
                'desglose_salario': desglose_salario,
                'config_auxilio': config_auxilio,
                'config_global': config_global,
                'desglose_ausencias': desglose_ausencias,
                'tabla_conceptos': tabla_conceptos,
                # ========== VALIDACIONES Y CONFIGURACION ==========
                'validaciones': validacion.get('validaciones', []),
                'warnings': validacion.get('warnings', []),
                'indicador_params': validacion.get('indicador_params', {}),
                'config_override': config_override,
                # Informacion del indicador especial si aplica
                'usa_indicador_especial': bool(config_override.get('tasa_indicador')),
                'tasa_indicador': config_override.get('tasa', config['tasa']),
                'dias_indicador': config_override.get('dias_indicador', 0),
                'base_dias_indicador': config_override.get('base_dias_indicador', 360),
                # Configuracion de la prestacion
                'config_prestacion': {
                    'tipo': provision_type,
                    'tasa': config['tasa'],
                    'campo_base': config['campo_base'],
                    'codigo': config['codigo'],
                    'nombre': config['nombre'],
                },
            }

            # ========== CONSTRUIR FORMULA DETALLADA ==========
            # Formula: (Salario/30 x Dias) + Variables + Auxilio = Base x Tasa% = Provision
            formula_componentes = []
            formula_pasos = []  # Lista estructurada para widget

            # Paso 1: Salario
            if hubo_cambio_salario and len(franjas_salario) > 1:
                formula_componentes.append('Salario por franjas:')
                formula_pasos.append({
                    'paso': 1,
                    'concepto': 'Salario (con cambio)',
                    'tipo': 'salario_franjas',
                    'detalle': []
                })
                for i, franja in enumerate(franjas_salario, 1):
                    dias_f = franja.get('dias_despues_descuento', franja['dias'])
                    sal_f = franja.get('salario_despues_descuento', franja['salario_proporcional'])
                    formula_componentes.append(
                        f'  Franja {i}: ${franja["salario_mensual"]:,.0f}/30 x {dias_f:.0f} dias = ${sal_f:,.0f}'
                    )
                    formula_pasos[0]['detalle'].append({
                        'franja': i,
                        'salario_mensual': franja['salario_mensual'],
                        'dias': dias_f,
                        'resultado': sal_f,
                        'fecha_inicio': str(franja.get('fecha_inicio', '')),
                        'fecha_fin': str(franja.get('fecha_fin', '')),
                    })
                formula_componentes.append(f'Total Salario: ${salario_periodo:,.0f}')
                formula_pasos[0]['resultado'] = salario_periodo
            else:
                formula_componentes.append(f'Salario: ${salario_base_mensual:,.0f}/30 x {dias_pagados:.0f} dias = ${salario_periodo:,.0f}')
                formula_pasos.append({
                    'paso': 1,
                    'concepto': 'Salario Proporcional',
                    'tipo': 'salario_simple',
                    'salario_mensual': salario_base_mensual,
                    'dias': dias_pagados,
                    'resultado': salario_periodo,
                    'formula_texto': f'${salario_base_mensual:,.0f} / 30 x {dias_pagados:.0f} = ${salario_periodo:,.0f}'
                })

            # Paso 2: Variables
            if variable_total > 0:
                formula_componentes.append(f'Variables ({campo_base}): ${variable_total:,.0f}')
                formula_pasos.append({
                    'paso': 2,
                    'concepto': f'Devengos Variables ({campo_base})',
                    'tipo': 'variables',
                    'resultado': variable_total,
                    'cantidad_conceptos': len(conceptos_incluidos),
                    'formula_texto': f'Suma de {len(conceptos_incluidos)} conceptos = ${variable_total:,.0f}'
                })

            # Paso 3: Auxilio Transporte
            modality_label = contract_labels['modality_aux_label']
            aux_prop = auxilio_info.get('proporcion', 1) * 100

            if auxilio_transporte > 0:
                if auxilio_info.get('modality_aux') == 'basico' and aux_prop >= 100:
                    formula_componentes.append(f'Aux. Transporte ({modality_label}): ${auxilio_transporte:,.0f}')
                    formula_texto_aux = f'Valor fijo completo = ${auxilio_transporte:,.0f}'
                else:
                    formula_componentes.append(
                        f'Aux. Transporte ({modality_label}): ${auxilio_info.get("auxilio_mensual", 0):,.0f} x {aux_prop:.0f}% = ${auxilio_transporte:,.0f}'
                    )
                    formula_texto_aux = f'${auxilio_info.get("auxilio_mensual", 0):,.0f} x {aux_prop:.0f}% = ${auxilio_transporte:,.0f}'

                formula_pasos.append({
                    'paso': 3,
                    'concepto': f'Auxilio Transporte ({modality_label})',
                    'tipo': 'auxilio',
                    'resultado': auxilio_transporte,
                    'auxilio_mensual': auxilio_info.get('auxilio_mensual', 0),
                    'proporcion': aux_prop,
                    'modality_aux': auxilio_info.get('modality_aux', 'basico'),
                    'fuente': auxilio_info.get('fuente', 'calculado'),
                    'formula_texto': formula_texto_aux
                })
            elif not aplica_auxilio:
                formula_componentes.append(f'Aux. Transporte: No aplica - {config_auxilio.get("razon_no_aplica", "Ver configuracion")}')
                formula_pasos.append({
                    'paso': 3,
                    'concepto': 'Auxilio Transporte',
                    'tipo': 'auxilio_no_aplica',
                    'resultado': 0,
                    'razon': config_auxilio.get('razon_no_aplica', 'No aplica para este tipo'),
                    'formula_texto': 'No aplica'
                })

            # Paso 4: Base Total
            formula_pasos.append({
                'paso': 4,
                'concepto': 'Base Total',
                'tipo': 'base_total',
                'resultado': base_total,
                'componentes': {
                    'salario': salario_periodo,
                    'variables': variable_total,
                    'auxilio': auxilio_transporte
                },
                'formula_texto': f'${salario_periodo:,.0f} + ${variable_total:,.0f} + ${auxilio_transporte:,.0f} = ${base_total:,.0f}'
            })

            data_visual['formula_componentes'] = formula_componentes
            data_visual['formula_pasos'] = formula_pasos
            data_visual['nota'] = (
                f'Base = Salario componente + Variables marcadas como {campo_base} + Aux. Transporte. '
                'Cuando el período se liquida sobre 30 días, el salario componente puede verse ajustado '
                'para evitar doble conteo de novedades incluidas en Variables.'
            )

            # ========== INDICADORES VISUALES ==========
            # Iconos y colores para el widget
            indicadores = []

            # Indicador de metodo
            indicadores.append({
                'tipo': 'metodo',
                'icono': 'fa-bolt',
                'color': 'success',
                'texto': 'Metodo Simple',
                'descripcion': 'Calculo rapido sobre periodo actual'
            })

            # Indicador de auxilio
            if aplica_auxilio:
                indicadores.append({
                    'tipo': 'auxilio',
                    'icono': 'fa-bus',
                    'color': 'primary',
                    'texto': f'Auxilio {modality_label}',
                    'descripcion': f'${auxilio_transporte:,.0f}'
                })
            else:
                indicadores.append({
                    'tipo': 'auxilio',
                    'icono': 'fa-ban',
                    'color': 'muted',
                    'texto': 'Sin Auxilio',
                    'descripcion': config_auxilio.get('razon_no_aplica', 'No aplica')
                })

            # Indicador de cambio salarial
            if hubo_cambio_salario:
                indicadores.append({
                    'tipo': 'cambio_salario',
                    'icono': 'fa-exchange',
                    'color': 'warning',
                    'texto': 'Cambio Salarial',
                    'descripcion': f'{len(franjas_salario)} franjas detectadas'
                })

            # Indicador de ausencias
            if desglose_ausencias['total_ausencias'] > 0:
                indicadores.append({
                    'tipo': 'ausencias',
                    'icono': 'fa-calendar-times-o',
                    'color': 'info',
                    'texto': f'{desglose_ausencias["total_ausencias"]:.0f} dias ausencia',
                    'descripcion': desglose_ausencias['efecto_en_calculo']
                })

            # Indicador de suspensiones
            if config_params.get('prst_wo_susp') and provision_type == 'prima':
                indicadores.append({
                    'tipo': 'prst_wo_susp',
                    'icono': 'fa-shield',
                    'color': 'success',
                    'texto': 'Sin Descuento Susp.',
                    'descripcion': 'Prima no descuenta suspensiones'
                })

            data_visual['indicadores'] = indicadores

            # ========== CONFIGURACION LEGACY (compatibilidad) ==========
            data_visual['configuracion'] = {
                'metodo': 'simple',
                'descontar_suspensiones': descontar_suspensiones,
                'prst_wo_susp': config_params.get('prst_wo_susp', False),
                'promedio_detectar_cambios': config_params.get('promedio_detectar_cambios', True),
                # Auxilio por tipo de provision
                'prima_incluye_auxilio': config_params.get('prima_incluye_auxilio', True),
                'cesantias_incluye_auxilio': config_params.get('cesantias_incluye_auxilio', True),
                'vacaciones_incluye_auxilio': config_params.get('vacaciones_incluye_auxilio', False),
                'aux_prst': config_params.get('aux_prst', False),
                # Tasas legales desde configuracion
                'tasa_prima': tasas_legales['prima'],
                'tasa_cesantias': tasas_legales['cesantias'],
                'tasa_vacaciones': tasas_legales['vacaciones'],
                'tasa_intereses': tasas_legales['intereses'],
            }
            # Indicar si auxilio aplica para este tipo especifico
            data_visual['configuracion'][f'{provision_type}_incluye_auxilio'] = aplica_auxilio

            # ========== TABLA DE FRANJAS SALARIO ==========
            if hubo_cambio_salario and franjas_salario:
                tabla_franjas = []
                for i, franja in enumerate(franjas_salario, 1):
                    tabla_franjas.append({
                        'numero': i,
                        'fecha_inicio': str(franja['fecha_inicio']),
                        'fecha_fin': str(franja['fecha_fin']),
                        'salario_mensual': franja['salario_mensual'],
                        'dias': franja.get('dias_despues_descuento', franja['dias']),
                        'salario_proporcional': franja.get('salario_despues_descuento', franja['salario_proporcional']),
                    })
                data_visual['tabla_franjas_salario'] = tabla_franjas

            # Tabla de conceptos incluidos en la base (variables)
            if conceptos_incluidos:
                data_visual['tabla_conceptos_base'] = conceptos_incluidos

            # ========== INFORMACION ESPECIFICA POR TIPO ==========
            # tasa_provision ya viene de config['tasa'] definida arriba
            aux_text = f' + Aux ${auxilio_transporte:,.0f}' if auxilio_transporte > 0 else ''
            var_text = f' + Var ${variable_total:,.0f}' if variable_total > 0 else ''

            if provision_type == 'intereses':
                tasa_interes = tasas_legales['intereses']
                valor_intereses_final = cesantias_proporcionales * (tasa_interes / 100)
                data_visual.update({
                    'cesantias_proporcionales': cesantias_proporcionales,
                    'tasa_interes': tasa_interes,
                    'valor_intereses': valor_intereses_final,
                    'formula': f'Cesantias ${cesantias_proporcionales:,.0f} x {tasa_interes}% = ${valor_intereses_final:,.0f}',
                    'formula_final': {
                        'base': cesantias_proporcionales,
                        'tasa': tasa_interes,
                        'resultado': valor_intereses_final,
                        'texto': f'Cesantias x {tasa_interes}% = Intereses'
                    }
                })
            elif provision_type == 'prima':
                data_visual.update({
                    'tasa': tasa_provision,
                    'formula': f'(Sal ${salario_periodo:,.0f}{var_text}{aux_text}) x {tasa_provision}% = ${valor_provision:,.0f}',
                    'formula_detalle': f'Base ${base_total:,.0f} x {tasa_provision}% = ${valor_provision:,.0f}',
                    'formula_final': {
                        'base': base_total,
                        'tasa': tasa_provision,
                        'resultado': valor_provision,
                        'texto': f'Base x {tasa_provision}% = Prima'
                    }
                })
            elif provision_type == 'cesantias':
                data_visual.update({
                    'tasa': tasa_provision,
                    'formula': f'(Sal ${salario_periodo:,.0f}{var_text}{aux_text}) x {tasa_provision}% = ${valor_provision:,.0f}',
                    'formula_detalle': f'Base ${base_total:,.0f} x {tasa_provision}% = ${valor_provision:,.0f}',
                    'formula_final': {
                        'base': base_total,
                        'tasa': tasa_provision,
                        'resultado': valor_provision,
                        'texto': f'Base x {tasa_provision}% = Cesantias'
                    }
                })
            elif provision_type == 'vacaciones':
                data_visual.update({
                    'tasa': tasa_provision,
                    'formula': f'(Sal ${salario_periodo:,.0f}{var_text}{aux_text}) x {tasa_provision}% = ${valor_provision:,.0f}',
                    'formula_detalle': f'Base ${base_total:,.0f} x {tasa_provision}% = ${valor_provision:,.0f}',
                    'formula_final': {
                        'base': base_total,
                        'tasa': tasa_provision,
                        'resultado': valor_provision,
                        'texto': f'Base x {tasa_provision}% = Vacaciones'
                    }
                })

            # Retorno según liquidación, consolidación o provisión
            # IMPORTANTE: Retornamos valor_provision como amount y rate=100 para que Odoo no aplique tasa doble
            # El valor_provision ya tiene la fórmula proporcional aplicada
            if es_liquidacion:
                valor_liquidacion = valor_liquidacion or 0.0
                data_visual['valor_liquidacion'] = valor_liquidacion
                data_visual['es_liquidacion'] = True
                data_visual['ajuste'] = 0.0
                data_visual['resumen']['valor_liquidacion'] = valor_liquidacion
                if provision_type == 'vacaciones':
                    # Vacaciones: VACCONTRATO ya paga el total acumulado de vacaciones.
                    # PRV_VAC en liquidación debe ser solo la provisión del período (4.17% de la base),
                    # no el total de VACCONTRATO (que acumula múltiples años).
                    valor_ret = valor_provision
                else:
                    valor_ret = valor_liquidacion
                nombre = f"PROVISIÓN {config['nombre']} - A PAGAR: ${valor_ret:,.2f}"
                return valor_ret, 1, 100, nombre, False, data_visual
            elif es_consolidacion and provision_type != 'prima':
                # Para consolidación (excepto prima), retornamos el valor de provisión del período
                # que será consolidado con otros períodos
                # Prima NO se consolida, mantiene nombre normal
                nombre = f"CONSOLIDADO {config['nombre']} SIMPLE"
                data_visual['es_consolidacion'] = True
                data_visual['metodo'] = 'simple_rapido_consolidacion'
                data_visual['codigo_regla'] = config['codigo']  # PRV_XXX_CONS
                data_visual['codigo_base'] = config['codigo_base']  # PRV_XXX
                if provision_type == 'intereses':
                    # Para intereses, retornamos cesantias_proporcionales y rate=12 para aplicar el 12%
                    return cesantias_proporcionales, 1, 12.0, nombre, False, data_visual
                else:
                    # Para cesantías y vacaciones, retornamos el valor completo con rate=100
                    return valor_provision, 1, 100.0, nombre, False, data_visual
            else:
                nombre = f"{config['nombre']} SIMPLE"
                # Retornar valor_provision con rate=100 porque ya tiene la fórmula completa aplicada
                # Odoo calculará: valor_provision * 1 * 100 / 100 = valor_provision
                if provision_type == 'intereses':
                    # Para intereses, retornamos cesantias_proporcionales y rate=12 para aplicar el 12%
                    return cesantias_proporcionales, 1, 12.0, nombre, False, data_visual
                else:
                    # Para prima, cesantías y vacaciones, retornamos el valor completo con rate=100
                    return valor_provision, 1, 100.0, nombre, False, data_visual

        # ========== MÉTODO COMPLEJO (con _compute_social_benefits) ==========
        # Determinar período según tipo
        date_to = slip.date_to

        # PROVISIONES MENSUALES: calcular causado desde fecha de corte hasta date_to
        if es_provision_mensual:
            date_from, date_to = self._get_provision_period(slip, contract, provision_type)
        elif provision_type in ['cesantias', 'intereses']:
            # LIQUIDACIÓN: Año completo
            date_from = date(date_to.year, 1, 1)
            if contract.date_start and contract.date_start > date_from:
                date_from = contract.date_start
        elif provision_type == 'prima':
            # LIQUIDACIÓN: Semestre completo
            if date_to.month <= 6:
                date_from = date(date_to.year, 1, 1)
            else:
                date_from = date(date_to.year, 7, 1)
            if contract.date_start and contract.date_start > date_from:
                date_from = contract.date_start
        else:  # vacaciones
            date_from = slip.date_from

        # Calcular con _compute_social_benefits
        base_diaria, dias_efectivos, porcentaje, nombre_calc, html_log, datos = self._compute_social_benefits(
            data_payslip,
            date_from,
            date_to,
            config['tipo_prest'],
            descontar_suspensiones
        )
        if log_provisions:
            _logger.info(
                "PRV[%s] complex base_diaria=%s dias=%s tasa=%s period=%s-%s",
                provision_type,
                base_diaria,
                dias_efectivos,
                config['tasa'],
                date_from,
                date_to,
            )

        # ──────────────────────────────────────────────────────────────────────
        # OPCION: provision sobre DIAS TRABAJADOS (WORK100)
        # Si hr_annual_parameters.provision_days_method == 'worked_days',
        # ajustar dias_efectivos a los dias realmente trabajados del recibo
        # (WORK100, que ya descuenta ausencias e incapacidades).
        # Por defecto ('periodo'), mantiene los dias del periodo.
        # ──────────────────────────────────────────────────────────────────────
        provision_days_method_cfg = getattr(annual_parameters, 'provision_days_method', 'periodo') if annual_parameters else 'periodo'
        if provision_days_method_cfg == 'worked_days' and not es_liquidacion:
            work100_line = next(
                (wd for wd in slip.worked_days_line_ids if wd.code == 'WORK100'),
                None,
            )
            if work100_line and work100_line.number_of_days:
                dias_trabajados = float(work100_line.number_of_days)
                if log_provisions:
                    _logger.info(
                        "PRV[%s] override por worked_days: dias %s -> %s (WORK100)",
                        provision_type, dias_efectivos, dias_trabajados,
                    )
                dias_efectivos = dias_trabajados
                if datos and 'data_kpi' in datos:
                    datos['data_kpi']['days_worked'] = dias_efectivos
                    datos['data_kpi']['metodo_dias'] = 'worked_days_WORK100'

        # Si hay días manuales y NO es liquidación, ajustar días efectivos
        if slip.use_manual_vacation_days and slip.manual_vacation_days and not es_liquidacion:
            dias_efectivos = slip.manual_vacation_days * 24

            # Actualizar datos para reflejar el cambio
            if datos and 'data_kpi' in datos:
                datos['data_kpi']['days_worked'] = dias_efectivos
                datos['data_kpi']['metodo_dias'] = 'manual_provision'

        # Calcular valor de provisión
        cesantias_proporcionales = 0  # Inicializar para uso en consolidación
        if provision_type == 'intereses':
            # CORRECCIÓN: Usar PRV_ICES_DATA de localdict que ya fue calculado por _prv_ces
            prv_ices_data = data_payslip.get('PRV_ICES_DATA', {})
            cesantias_acumuladas = prv_ices_data.get('valor_cesantias', 0)

            # Si no hay datos de PRV_ICES_DATA, intentar buscar en rules como fallback
            if not cesantias_acumuladas:
                rules = data_payslip.get('rules')
                prv_ces_rule = rules.get('PRV_CES') if rules else None
                if prv_ces_rule and prv_ces_rule.total > 0:
                    cesantias_acumuladas = abs(prv_ces_rule.total)

            # Si aún no hay cesantías, calcular como último fallback
            if not cesantias_acumuladas:
                salary_base = base_diaria * dias_efectivos
                cesantias_acumuladas = salary_base * 0.0833

            # CORRECCIÓN: Intereses sobre CESANTÍAS TOTALES, no proporcionales
            # Art. 99 Ley 50/1990: 12% anual sobre el saldo de cesantías
            # Fórmula: cesantias_acumuladas * 12%
            # NO se proporcionaliza por días, se calcula sobre el total acumulado
            valor_provision = cesantias_acumuladas * 0.12
            base_total = cesantias_acumuladas
        else:
            base_total = base_diaria * dias_efectivos
            # NO aplicar tasa aquí, Odoo la aplica en el return
            valor_provision = base_total

        # Saldo contable y liquidación
        # Para consolidación, usar código base para buscar saldo contable
        codigo_saldo = config['codigo_base'] if es_consolidacion else config['codigo']
        saldo_contable = self._obtener_saldo_contable_provision(data_payslip, codigo_saldo) or 0.0

        # OBTENER PROVISIÓN YA CONTABILIZADA (de nóminas anteriores del período)
        provision_acumulada = 0.0
        fecha_corte_descuento = None

        _logger.warning(f"PRV ACUM CHECK: slip={slip.id} struct_process={slip.struct_process} es_provision_mensual={es_provision_mensual} provision_type={provision_type}")

        if es_provision_mensual:
            # Buscar provisiones anteriores del mismo período (año/semestre/ultimo corte)
            fecha_corte_descuento = slip.date_from - timedelta(days=1)
            _logger.warning(f"PRV DATES: date_from={date_from} fecha_corte={fecha_corte_descuento} check={fecha_corte_descuento >= date_from}")
            if fecha_corte_descuento >= date_from:
                provision_acumulada, _ = self._get_total_previous_provision(
                    data_payslip,
                    date_from,
                    fecha_corte_descuento,  # Hasta el dia antes del periodo actual
                    config['codigo']
                )

        valor_liquidacion = None
        if es_liquidacion:
            valor_liquidacion = self._obtener_valor_liquidacion(data_payslip, provision_type)
            # Asegurar que valor_liquidacion sea un número
            if valor_liquidacion is None:
                valor_liquidacion = 0.0

        # ========== DATOS DE VISUALIZACION DETALLADOS (METODO COMPLEJO) ==========
        data_visual = datos.copy() if datos else {}
        data_visual['metodo'] = 'complejo'
        data_visual['saldo_contable'] = saldo_contable
        data_visual['provision_acumulada'] = provision_acumulada
        data_visual['provision_type'] = provision_type
        data_visual['fecha_inicio'] = date_from
        data_visual['fecha_corte'] = date_to
        data_visual['fecha_corte_descuento'] = fecha_corte_descuento
        data_visual['valor_acumulado_corte'] = provision_acumulada
        data_visual['base_diaria'] = base_diaria
        data_visual['dias_efectivos'] = dias_efectivos
        data_visual['base_total'] = base_total

        # Calcular total causado para mostrar en todos los casos
        total_causado_base = base_diaria * dias_efectivos
        if provision_type == 'intereses':
            total_causado_con_tasa = base_total * 0.12  # cesantias * 12%
        else:
            total_causado_con_tasa = total_causado_base * config['tasa'] / 100

        data_visual['total_causado_base'] = total_causado_base
        data_visual['total_causado_con_tasa'] = total_causado_con_tasa
        data_visual['tasa'] = config['tasa']

        # ========== OBTENER CONFIGURACION DE AUXILIO TRANSPORTE ==========
        # IMPORTANTE: No sobrescribir config_auxilio si ya viene en datos (metodo complejo)
        # El metodo _compute_social_benefits ya calculo correctamente el config_auxilio
        contract_labels = self._get_contract_labels(contract)
        if datos and 'config_auxilio' in datos:
            # Usar el config_auxilio correcto que ya fue calculado
            config_auxilio = datos['config_auxilio']
            aplica_auxilio = config_auxilio.get('aplica', False)
            data_visual['config_auxilio'] = config_auxilio
        else:
            # Fallback si no hay datos (no deberia pasar en metodo complejo)
            salario_minimo_mensual = annual_parameters.smmlv_monthly if annual_parameters else 0
            auxilio_transporte_mensual = annual_parameters.transportation_assistance_monthly if annual_parameters else 0
            salario_base_mensual = base_diaria * 30

            # Validar si aplica auxilio
            auxilio_validacion = self._provision_incluye_auxilio(
                provision_type,
                config_params,
                contract,
                salario_base_mensual,
                salario_minimo_mensual,
                employee=employee,
                annual_parameters=annual_parameters,
                return_detail=True
            )
            aplica_auxilio = auxilio_validacion.get('aplica', False)

            # Configuracion de auxilio
            config_auxilio = {
                'aplica': aplica_auxilio,
                'razon_no_aplica': '',
                'modality_aux': contract.modality_aux or 'basico',
                'modality_aux_label': contract_labels['modality_aux_label'],
                'only_wage': contract.only_wage or 'wage',
                'only_wage_label': contract_labels['only_wage_label'],
                'not_pay_auxtransportation': contract.not_pay_auxtransportation,
                'not_validate_top_auxtransportation': contract.not_validate_top_auxtransportation,
                'auxilio_mensual_legal': auxilio_transporte_mensual,
                'auxilio_aplicado': datos.get('data_kpi', {}).get('subsidy', 0) if datos else 0,
                'smmlv': salario_minimo_mensual,
                'dos_smmlv': 2 * salario_minimo_mensual,
                'base_validacion_tope': salario_base_mensual,
                'supera_tope': salario_base_mensual >= 2 * salario_minimo_mensual,
            }

            # Determinar razon si no aplica auxilio
            if not aplica_auxilio:
                if auxilio_validacion.get('razon'):
                    config_auxilio['razon_no_aplica'] = auxilio_validacion['razon']
                elif provision_type == 'intereses':
                    config_auxilio['razon_no_aplica'] = 'Intereses se calcula sobre cesantias (que ya incluye auxilio si aplica)'
                elif contract.not_pay_auxtransportation:
                    config_auxilio['razon_no_aplica'] = 'Contrato marcado como "No liquidar auxilio de transporte"'
                elif contract.modality_aux == 'no':
                    config_auxilio['razon_no_aplica'] = 'Modalidad de auxilio configurada como "Sin auxilio"'
                elif not config_params.get(f'{provision_type}_incluye_auxilio', False):
                    config_auxilio['razon_no_aplica'] = f'Configuracion global: {provision_type} no incluye auxilio'
                elif config_auxilio['supera_tope']:
                    config_auxilio['razon_no_aplica'] = (
                        f'Salario ({config_auxilio["base_validacion_tope"]:,.0f}) '
                        f'supera 2 SMMLV ({config_auxilio["dos_smmlv"]:,.0f})'
                    )

            data_visual['config_auxilio'] = config_auxilio

        # ========== CONFIGURACION GLOBAL ==========
        config_global = {
            'metodo_simple_activo': False,
            'descontar_suspensiones': descontar_suspensiones,
            'prst_wo_susp_activo': config_params.get('prst_wo_susp', False),
            'promedio_detectar_cambios': config_params.get('promedio_detectar_cambios', True),
            'prima_incluye_auxilio': config_params.get('prima_incluye_auxilio', True),
            'cesantias_incluye_auxilio': config_params.get('cesantias_incluye_auxilio', True),
            'vacaciones_incluye_auxilio': config_params.get('vacaciones_incluye_auxilio', False),
            'aux_prst': config_params.get('aux_prst', False),
            # Tasas legales desde configuracion
            'tasa_prima': PRESTACIONES_CONFIG['prima']['tasa'],
            'tasa_cesantias': PRESTACIONES_CONFIG['cesantias']['tasa'],
            'tasa_vacaciones': PRESTACIONES_CONFIG['vacaciones']['tasa'],
            'tasa_intereses': PRESTACIONES_CONFIG['intereses']['tasa'],
        }
        data_visual['config_global'] = config_global

        # ========== VALIDACIONES Y CONFIGURACION ==========
        data_visual['validaciones'] = validacion.get('validaciones', [])
        data_visual['warnings'] = validacion.get('warnings', [])
        data_visual['indicador_params'] = validacion.get('indicador_params', {})
        data_visual['config_override'] = config_override
        # Informacion del indicador especial si aplica
        data_visual['usa_indicador_especial'] = bool(config_override.get('tasa_indicador'))
        data_visual['tasa_indicador'] = config_override.get('tasa', config['tasa'])
        data_visual['dias_indicador'] = config_override.get('dias_indicador', 0)
        data_visual['base_dias_indicador'] = config_override.get('base_dias_indicador', 360)
        # Configuracion de la prestacion
        data_visual['config_prestacion'] = {
            'tipo': provision_type,
            'tasa': config['tasa'],
            'campo_base': config['campo_base'],
            'codigo': config['codigo'],
            'nombre': config['nombre'],
        }

        # ========== RESUMEN EJECUTIVO ==========
        resumen = {
            'tipo_provision': provision_type.upper(),
            'metodo_calculo': 'COMPLEJO (Acumulativo)',
            'periodo': f"{date_from} al {date_to}",
            'empleado': slip.employee_id.name if slip.employee_id else '',
            'contrato': contract.sequence if contract else '',
            'base_total': base_total,
            'valor_provision': total_causado_con_tasa,
            'tasa_aplicada': config['tasa'],
            'provision_acumulada': provision_acumulada,
            'saldo_contable': saldo_contable,
            'saldo_anterior': saldo_contable,
            'ajuste': 0.0,
            'es_liquidacion': es_liquidacion,
        }
        data_visual['resumen'] = resumen
        data_visual['saldo_anterior'] = saldo_contable
        data_visual['ajuste'] = 0.0
        data_visual['valor_liquidacion'] = valor_liquidacion or 0.0

        # ========== INDICADORES VISUALES ==========
        indicadores = []

        indicadores.append({
            'tipo': 'metodo',
            'icono': 'fa-calculator',
            'color': 'info',
            'texto': 'Metodo Complejo',
            'descripcion': 'Calculo con acumulacion de periodos'
        })

        modality_label = contract_labels['modality_aux_label']
        if aplica_auxilio:
            indicadores.append({
                'tipo': 'auxilio',
                'icono': 'fa-bus',
                'color': 'primary',
                'texto': f'Auxilio {modality_label}',
                'descripcion': f'${config_auxilio["auxilio_aplicado"]:,.0f}'
            })
        else:
            indicadores.append({
                'tipo': 'auxilio',
                'icono': 'fa-ban',
                'color': 'muted',
                'texto': 'Sin Auxilio',
                'descripcion': config_auxilio.get('razon_no_aplica', 'No aplica')
            })

        if es_liquidacion:
            indicadores.append({
                'tipo': 'liquidacion',
                'icono': 'fa-file-text-o',
                'color': 'danger',
                'texto': 'Liquidacion',
                'descripcion': f'A pagar: ${valor_liquidacion or 0:,.0f}'
            })

        if config_params.get('prst_wo_susp') and provision_type == 'prima':
            indicadores.append({
                'tipo': 'prst_wo_susp',
                'icono': 'fa-shield',
                'color': 'success',
                'texto': 'Sin Descuento Susp.',
                'descripcion': 'Prima no descuenta suspensiones'
            })

        data_visual['indicadores'] = indicadores

        # ========== FORMULA PASOS ESTRUCTURADOS ==========
        formula_pasos = []

        # Paso 1: Periodo
        formula_pasos.append({
            'paso': 1,
            'concepto': 'Periodo de Causacion',
            'tipo': 'periodo',
            'resultado': f'{date_from} a {date_to}',
            'formula_texto': f'{dias_efectivos} dias efectivos'
        })

        # Paso 2: Base diaria
        formula_pasos.append({
            'paso': 2,
            'concepto': 'Base Diaria',
            'tipo': 'base_diaria',
            'resultado': base_diaria,
            'formula_texto': f'Promedio salarios del periodo = ${base_diaria:,.0f}'
        })

        # Paso 3: Base total
        formula_pasos.append({
            'paso': 3,
            'concepto': 'Base Total (Sal x Dias)',
            'tipo': 'base_total',
            'resultado': total_causado_base,
            'formula_texto': f'${base_diaria:,.0f} x {dias_efectivos} = ${total_causado_base:,.0f}'
        })

        # Paso 4: Aplicar tasa
        formula_pasos.append({
            'paso': 4,
            'concepto': f'Causado ({config["tasa"]}%)',
            'tipo': 'causado',
            'resultado': total_causado_con_tasa,
            'formula_texto': f'${total_causado_base:,.0f} x {config["tasa"]}% = ${total_causado_con_tasa:,.0f}'
        })

        # Paso 5: Descuento provisionado (si aplica)
        if provision_acumulada > 0:
            incremento = total_causado_con_tasa - provision_acumulada
            formula_pasos.append({
                'paso': 5,
                'concepto': 'Ya Provisionado',
                'tipo': 'descuento',
                'resultado': -provision_acumulada,
                'formula_texto': f'Provisionado anteriormente: ${provision_acumulada:,.0f}'
            })
            formula_pasos.append({
                'paso': 6,
                'concepto': 'Incremento Neto',
                'tipo': 'resultado_final',
                'resultado': incremento,
                'formula_texto': f'${total_causado_con_tasa:,.0f} - ${provision_acumulada:,.0f} = ${incremento:,.0f}'
            })

        data_visual['formula_pasos'] = formula_pasos

        # ========== FORMULA COMPONENTES LEGACY ==========
        formula_componentes = []
        formula_componentes.append(f'Periodo: {date_from} a {date_to}')
        formula_componentes.append(f'Base diaria: ${base_diaria:,.0f}')
        formula_componentes.append(f'Dias efectivos: {dias_efectivos}')
        formula_componentes.append(f'Base total: ${total_causado_base:,.0f}')
        formula_componentes.append(f'Causado ({config["tasa"]}%): ${total_causado_con_tasa:,.0f}')
        if provision_acumulada > 0:
            formula_componentes.append(f'Ya provisionado: ${provision_acumulada:,.0f}')
            formula_componentes.append(f'Incremento: ${total_causado_con_tasa - provision_acumulada:,.0f}')
        data_visual['formula_componentes'] = formula_componentes

        # ========== FORMULA FINAL ==========
        if provision_type == 'intereses':
            data_visual['formula_final'] = {
                'base': base_total,
                'tasa': 12.0,
                'resultado': total_causado_con_tasa,
                'texto': f'Cesantias x 12% = Intereses'
            }
        else:
            data_visual['formula_final'] = {
                'base': total_causado_base,
                'tasa': config['tasa'],
                'resultado': total_causado_con_tasa,
                'texto': f'Base x {config["tasa"]}% = {provision_type.capitalize()}'
            }

        # Retorno según liquidación, consolidación o provisión
        if es_liquidacion:
            valor_liquidacion = valor_liquidacion or 0.0
            data_visual['valor_liquidacion'] = valor_liquidacion
            data_visual['es_liquidacion'] = True
            data_visual['ajuste'] = 0.0
            data_visual['resumen']['valor_liquidacion'] = valor_liquidacion
            if provision_type == 'vacaciones':
                # Vacaciones: VACCONTRATO ya paga el total acumulado de vacaciones.
                # PRV_VAC en liquidación debe ser solo la provisión del período (4.17% de la base),
                # no el total de VACCONTRATO (que acumula múltiples años).
                valor_ret = valor_provision
            else:
                valor_ret = valor_liquidacion
            nombre = f"PROVISIÓN {config['nombre']} - A PAGAR: ${valor_ret:,.2f}"
            return valor_ret, 1, 100, nombre, False, data_visual
        elif es_consolidacion and provision_type != 'prima':
            # Para consolidación (excepto prima), retornamos el valor de provisión del período
            # que será consolidado con otros períodos
            # Prima NO se consolida, mantiene nombre normal
            nombre = f"CONSOLIDADO {config['nombre']}"
            data_visual['es_consolidacion'] = True
            data_visual['metodo'] = 'complejo_consolidacion'
            data_visual['codigo_regla'] = config['codigo']  # PRV_XXX_CONS
            data_visual['codigo_base'] = config['codigo_base']  # PRV_XXX
            if provision_type == 'intereses':
                # Para intereses, cesantias_proporcionales ya se calculó arriba
                # Retornamos cesantias_proporcionales y rate=12 para aplicar el 12%
                return cesantias_proporcionales, 1, 12.0, nombre, False, data_visual
            else:
                # Para cesantías y vacaciones, retornamos el valor con rate=100
                return valor_provision, 1, 100.0, nombre, False, data_visual
        else:
            # PROVISIÓN MENSUAL NORMAL
            # Calcular: Total causado hasta fecha - Total ya provisionado

            # Total causado hasta la fecha (base_diaria * dias_efectivos)
            total_causado = base_diaria * dias_efectivos

            # Aplicar tasa según tipo
            if provision_type == 'intereses':
                # Intereses: ya calculado con 12%
                total_causado_con_tasa = valor_provision
            else:
                # Otras provisiones: aplicar tasa
                total_causado_con_tasa = total_causado * config['tasa'] / 100

            # Restar lo ya provisionado en meses anteriores
            incremento_mes = total_causado_con_tasa - provision_acumulada

            # Actualizar datos visuales
            data_visual['total_causado'] = total_causado_con_tasa
            data_visual['incremento_mes'] = incremento_mes

            nombre = f"PROVISIÓN {config['nombre']}"

            # CORRECCIÓN: Retornar incremento con rate=100 (como método simple)
            # Esto evita bases proporcionales astronómicas y mantiene coherencia
            # Total calculado por Odoo: incremento_mes * 1 * 100 / 100 = incremento_mes
            # Similar a línea 1759 del método simple
            if provision_acumulada > 0 and total_causado > 0:
                # Hay acumulado: retornar solo el incremento con rate=100
                data_visual['metodo_calculo'] = 'complejo_incremental'
                return incremento_mes, 1, 100.0, nombre, False, data_visual
            else:
                # Sin acumulado: retornar base_diaria y días (como método simple)
                # Para que Odoo calcule: base_diaria × dias × tasa / 100
                if provision_type == 'intereses':
                    # Intereses: cesantías con rate=12
                    return base_total, 1, config['tasa'], nombre, False, data_visual
                else:
                    # CORRECCIÓN: Retornar base_diaria y días, no total_causado
                    # total_causado ya tiene base_diaria × dias, causaba duplicación
                    return base_diaria, dias_efectivos, config['tasa'], nombre, False, data_visual


    def _get_provision_period(self, slip, contract, provision_type):
        """
        Determina el rango de causacion para provisiones.

        - LIQUIDACION (struct_process == 'contrato'): usa fechas manuales del
          recibo (date_prima/date_cesantias/date_vacaciones) o, si no estan,
          inicio del semestre/anno/contrato.
        - NOMINA REGULAR (provision mensual): usa el periodo del recibo
          (slip.date_from a slip.date_to). Esto da una provision PURA del
          mes actual, equivalente al comportamiento de v18.
        """
        date_to = slip.date_to
        date_from = slip.date_from  # Default: periodo del recibo
        es_liquidacion = slip.struct_process == 'contrato'

        if es_liquidacion:
            if provision_type == 'prima':
                if slip.date_prima:
                    date_from = slip.date_prima
                elif date_to.month <= 6:
                    date_from = date(date_to.year, 1, 1)
                else:
                    date_from = date(date_to.year, 7, 1)
            elif provision_type in ['cesantias', 'intereses']:
                if slip.date_cesantias:
                    date_from = slip.date_cesantias
                else:
                    date_from = date(date_to.year, 1, 1)
            elif provision_type == 'vacaciones':
                if slip.date_vacaciones:
                    date_from = slip.date_vacaciones
                elif contract.date_start:
                    date_from = contract.date_start
        # NOMINA REGULAR: date_from = slip.date_from (ya asignado al inicio).
        # Esto produce provisiones del mes actual y evita inflar dias cuando el
        # contrato empieza dias antes del inicio del periodo del recibo.

        if contract.date_start and date_from and date_from < contract.date_start:
            date_from = contract.date_start

        if date_from and date_to and date_from > date_to:
            date_from = date_to

        return date_from, date_to



    def _obtener_saldo_contable_provision(self, data_payslip, codigo_regla):
        """
        Obtiene el saldo contable de la provisión usando las cuentas contables

        Args:
            data_payslip (dict): Diccionario con datos de liquidación
            codigo_regla (str): Código de la regla salarial de provisión

        Returns:
            float: Saldo contable de la provisión
        """
        employee = data_payslip['employee']
        slip = data_payslip['slip']
        log_provisions = bool(self.env.context.get('log_provisions'))

        AccountMove = self.env['account.move.line']
        account_ids = self.salary_rule_accounting.mapped('credit_account').ids
        if not account_ids:
            if log_provisions:
                _logger.warning(
                    "PRV saldo: no credit_account configured for rule=%s slip=%s employee=%s",
                    codigo_regla,
                    slip.id,
                    employee.id,
                )
            return 0.0

        partner = self._get_employee_address_id(employee)
        if not partner:
            if log_provisions:
                _logger.warning(
                    "PRV saldo: employee has no work_contact_id rule=%s slip=%s employee=%s",
                    codigo_regla,
                    slip.id,
                    employee.id,
                )
            return 0.0

        # Filtrar solo por la vigencia (año) del periodo de nómina actual.
        # Los saldos contables de vigencias anteriores son resultado histórico
        # y NO deben afectar el cálculo de la provisión del periodo actual.
        year_start = slip.date_from.replace(month=1, day=1)
        year_end = slip.date_from.replace(month=12, day=31)

        domain = [
            ('account_id', 'in', account_ids),
            ('move_id.state', '=', 'posted'),
            ('partner_id', '=', partner.id),
            ('date', '>=', year_start),
            ('date', '<=', year_end),
        ]

        # Odoo 19: Usar _read_group
        result = AccountMove._read_group(
            domain=domain,
            groupby=[],
            aggregates=['credit:sum', 'debit:sum'],
        )
        return (result[0][0] or 0.0) - (result[0][1] or 0.0) if result else 0.0



    def _get_employee_address_id(self, employee):
        """
        Obtiene el ID de dirección del empleado

        Args:
            employee (hr.employee): Objeto empleado

        Returns:
            res.partner: Partner del empleado
        """
        if employee.work_contact_id:
            return employee.work_contact_id
        return False



    def _obtener_valor_liquidacion(self, data_payslip, provision_type):
        """
        Obtiene el valor a pagar en liquidación (ODOO 18)

        Args:
            data_payslip (dict): Diccionario con datos de liquidación
            provision_type (str): Tipo de provisión

        Returns:
            float: Valor a pagar en liquidación
        """
        # Usar los códigos de regla definidos
        rule_code_map = {
            'vacaciones': 'VACCONTRATO',
            'prima': 'PRIMA',
            'cesantias': 'CESANTIAS',
            'intereses': 'INTCESANTIAS'
        }

        codigo_liquidacion = rule_code_map.get(provision_type)
        if not codigo_liquidacion:
            return 0

        # ODOO 18: Buscar en rules
        rules = data_payslip.get('rules', {})
        rule_data = rules.get(codigo_liquidacion)
        if rule_data:
            return rule_data.total

        return 0


    # ══════════════════════════════════════════════════════════════════════════
    # MÉTODOS DE PROVISIONES
    # ══════════════════════════════════════════════════════════════════════════


    def _prv_prim(self, localdict):
        """
        PROVISIÓN PRIMA - Usa método centralizado _calculate_provision
        """
        return self._calculate_provision(localdict, 'prima')



    def _prv_ces(self, localdict):
        """
        PROVISIÓN CESANTÍAS - Usa método centralizado _calculate_provision
        También inicializa PRV_ICES_DATA para provisión de intereses
        """
        slip = localdict['slip']
        contract = localdict['contract']

        # Inicializar PRV_ICES_DATA con valores predeterminados
        # Esto debe ocurrir ANTES de cualquier retorno temprano para que _prv_ices siempre encuentre los datos
        date_from = slip.date_to.replace(month=1, day=1)
        date_to = slip.date_to.replace(month=12, day=31)

        if slip.struct_process == 'contrato' and slip.date_liquidacion:
            date_to = slip.date_liquidacion

        if date_from < contract.date_start:
            date_from = contract.date_start

        localdict['PRV_ICES_DATA'] = {
            'interest': 0,
            'date_from': date_from,
            'date_to': date_to,
            'rate_worked_days': 0,
            'valor_cesantias': 0,
        }

        # Calcular provisión usando método centralizado
        result = self._calculate_provision(localdict, 'cesantias')

        # Actualizar PRV_ICES_DATA con valores reales si la provisión se calculó
        # CORRECCIÓN: El return de _calculate_provision puede ser:
        # - Método simple: (valor_provision, 1, 100, ...) donde valor_provision ya tiene la fórmula aplicada
        # - Método complejo: (base_total, 1, tasa, ...) donde tasa=8.33 para cesantías
        # El total real de cesantías = amount * qty * rate / 100
        if result and len(result) >= 3:
            # result = (amount, qty, rate, name, False, data_visual)
            amount = result[0] if result[0] else 0
            qty = result[1] if result[1] else 1
            rate = result[2] if result[2] else 100

            # Calcular el valor real de cesantías: amount * qty * rate / 100
            # Para método simple: valor_provision * 1 * 100 / 100 = valor_provision
            # Para método complejo: base_total * 1 * 8.33 / 100 = cesantías proporcionales
            valor_cesantias = amount * qty * rate / 100
            intereses = valor_cesantias * 0.12

            datos = result[5] if len(result) > 5 and isinstance(result[5], dict) else {}
            days_worked = datos.get('dias_computables', 0)
            rate_worked_days = days_worked / 360 if days_worked else 0

            localdict['PRV_ICES_DATA'].update({
                'interest': intereses,
                'valor_cesantias': valor_cesantias,
                'rate_worked_days': rate_worked_days,
            })

        return result



    def _prv_ices(self, localdict):
        """
        PROVISIÓN INTERESES CESANTÍAS - Usa método centralizado _calculate_provision
        Depende de PRV_CES (debe ejecutarse después)
        """
        return self._calculate_provision(localdict, 'intereses')



    def _prv_vac(self, localdict):
        """
        PROVISIÓN VACACIONES - Usa método centralizado _calculate_provision
        Calcula desde fecha de inicio de contrato hasta fecha de corte
        """
        return self._calculate_provision(localdict, 'vacaciones')


    # ══════════════════════════════════════════════════════════════════════════
    # MÉTODOS DE ACUMULACIÓN Y CONSULTA
    # ══════════════════════════════════════════════════════════════════════════


    def _get_total_previous_provision(self, localdict, date_from, date_to, code_regla):
        """
        Obtiene el saldo contable de provisión anterior para una regla específica
        Adaptado de _obtener_saldo_contable_provision en hr_rule.py

        Este método es MÁS PRECISO que consultar nóminas porque:
        - Refleja la realidad contable actual
        - Incluye ajustes manuales que no están en nóminas
        - Compatible con datos migrados de otros sistemas
        - Ideal para auditorías y conciliaciones

        IMPORTANTE: Toma TODO EL MES COMPLETO (date_from hasta date_to)
        para incluir todas las provisiones del período.

        Lógica:
        1. Busca la regla salarial por código (PRV_PRIM, PRV_CES, etc.)
        2. Obtiene las cuentas contables configuradas (credit_account)
        3. Busca movimientos contables (account.move.line) del MES COMPLETO
        4. Guarda los IDs de las líneas encontradas
        5. Suma créditos - débitos de esas líneas

        Args:
            localdict: Diccionario de contexto
            date_from: Fecha inicio del período (inicio del mes/semestre/año)
            date_to: Fecha fin del período (fin del mes/semestre/año)
            code_regla: Código de la regla de provisión (PRV_CES, PRV_PRIM, etc.)

        Returns:
            tuple: (saldo_total, lista_ids_lineas)
                - saldo_total: float - Crédito - Débito
                - lista_ids_lineas: list - IDs de account.move.line encontradas
        """
        slip = localdict['slip']
        employee = localdict['employee']

        _logger.warning(f"=== CALL _get_total_previous_provision: code={code_regla} emp={employee.id} slip={slip.id} dates={date_from} to {date_to}")

        HrSalaryRule = self.env['hr.salary.rule']
        salary_rule = HrSalaryRule.search([('code', '=', code_regla)], limit=1)

        def _fallback_from_payslips(reason):
            if self.env.context.get('log_provisions'):
                _logger.warning(
                    "PRV prev: fallback to payslip lines reason=%s code=%s",
                    reason,
                    code_regla,
                )
            domain = [
                ('code', '=', code_regla),
                ('slip_id.employee_id', '=', employee.id),
                ('slip_id.state', 'in', ['done', 'paid']),
                ('slip_id.date_from', '>=', date_from),
                ('slip_id.date_from', '<', slip.date_from),
            ]
            provision_lines = self.env['hr.payslip.line'].search_read(
                domain=domain,
                fields=['id', 'total'],
                order='id asc',
            )

            _logger.warning(
                f"PRV SEARCH: emp={employee.id} code={code_regla} "
                f"date_from={date_from} slip.date_from={slip.date_from} "
                f"found={len(provision_lines)} lines"
            )

            if not provision_lines:
                return 0, []

            saldo_total = sum(line['total'] for line in provision_lines)
            _logger.warning(f"PRV TOTAL: code={code_regla} saldo={saldo_total} lines={[l['id'] for l in provision_lines]}")
            ids_lineas = [line['id'] for line in provision_lines]
            localdict[f'{code_regla}_LINES'] = {
                'saldo': saldo_total,
                'line_ids': ids_lineas,
                'count': len(ids_lineas),
                'date_from': date_from,
                'date_to': date_to,
                'source': 'payslip_line',
                'reason': reason,
            }
            return saldo_total, ids_lineas

        if not salary_rule:
            if self.env.context.get('log_provisions'):
                _logger.warning("PRV prev: rule not found code=%s", code_regla)
            return _fallback_from_payslips('rule_not_found')

        if not salary_rule.salary_rule_accounting:
            if self.env.context.get('log_provisions'):
                _logger.warning("PRV prev: rule has no accounting code=%s", code_regla)
            return _fallback_from_payslips('no_accounting')

        AccountMoveLine = self.env['account.move.line']
        account_ids = salary_rule.salary_rule_accounting.mapped('credit_account').ids

        if not account_ids:
            if self.env.context.get('log_provisions'):
                _logger.warning("PRV prev: rule has no credit_account code=%s", code_regla)
            return _fallback_from_payslips('no_credit_account')

        partner_id = self._get_employee_partner_id(employee)
        if not partner_id:
            if self.env.context.get('log_provisions'):
                _logger.warning(
                    "PRV prev: employee has no partner code=%s employee=%s",
                    code_regla,
                    employee.id,
                )
            return _fallback_from_payslips('no_partner')

        domain = [
            ('account_id', 'in', account_ids),
            ('move_id.state', '=', 'posted'),
            ('partner_id', '=', partner_id),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
        ]

        provision_data = AccountMoveLine.search_read(
            domain=domain,
            fields=['id', 'credit', 'debit'],
            order='date asc'
        )

        if not provision_data:
            return _fallback_from_payslips('no_account_moves')

        saldo_total = sum(line['credit'] - line['debit'] for line in provision_data)
        ids_lineas = [line['id'] for line in provision_data]

        localdict[f'{code_regla}_LINES'] = {
            'saldo': saldo_total,
            'line_ids': ids_lineas,
            'count': len(ids_lineas),
            'date_from': date_from,
            'date_to': date_to,
        }

        return saldo_total, ids_lineas


    # ══════════════════════════════════════════════════════════════════════════
    # MÉTODOS DE SALARIO CON CAMBIOS Y AUSENCIAS
    # ══════════════════════════════════════════════════════════════════════════

    def _obtener_salario_efectivo_contrato(self, contract, wage_base=None, annual_parameters=None):
        """Delegado al método centralizado en hr.salary.rule.basic."""
        return self.env['hr.salary.rule.basic']._obtener_salario_efectivo_contrato(
            contract, wage_base=wage_base, annual_parameters=annual_parameters
        )

    def _calcular_salario_periodo_con_cambios(self, contract, slip, date_from, date_to,
                                               dias_ausencias_no_pagadas=0, descontar_suspensiones=True,
                                               detectar_cambios_salario=True, annual_parameters=None):
        """Delegado al método centralizado en hr.salary.rule.basic."""
        return self.env['hr.salary.rule.basic']._calcular_salario_periodo_con_cambios(
            contract, slip, date_from, date_to,
            dias_ausencias_no_pagadas=dias_ausencias_no_pagadas,
            descontar_suspensiones=descontar_suspensiones,
            detectar_cambios_salario=detectar_cambios_salario,
            annual_parameters=annual_parameters
        )


    # ══════════════════════════════════════════════════════════════════════════
    # MÉTODOS DE CONTADOR
    # ══════════════════════════════════════════════════════════════════════════
