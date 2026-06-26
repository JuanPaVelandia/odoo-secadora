# -*- coding: utf-8 -*-

"""
PRESTACIONES SOCIALES - MÉTODOS AUXILIARES
===========================================

Métodos de soporte para cálculos de prestaciones sociales.
Incluye: historial, acumulados, reglas usadas, períodos.
"""

from odoo import models, api
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from odoo.addons.lavish_hr_employee.models.hr_slip_utils import days360
from .config_reglas import PRESTACIONES_CONFIG, CODIGOS_LIQUIDACION, get_prestacion_base_field


class HrSalaryRulePrestacionesHelpers(models.AbstractModel):
    """Mixin con métodos auxiliares para prestaciones sociales"""

    _name = 'hr.salary.rule.prestaciones.helpers'
    _description = 'Métodos Auxiliares para Prestaciones Sociales'

    # =========================================================================
    # METODOS DE VALIDACION CENTRALIZADOS (Ley 2466/2025)
    # =========================================================================

    def _aprendiz_tiene_prestaciones(self, employee, contract, tipo_prestacion):
        """
        Valida si un empleado tiene derecho a una prestacion especifica segun tipo de contrato.

        ACTUALIZADO Ley 2466/2025: Los aprendices SENA ahora pueden tener
        derecho a prestaciones sociales si su tipo de contrato lo define.

        Enfoque directo similar a auxilios.py: valida tipo de contrato y parametros de configuracion.

        Args:
            employee: hr.employee
            contract: hr.contract
            tipo_prestacion: 'prima', 'cesantias', 'intereses', 'vacaciones'

        Returns:
            tuple: (aplica: bool, motivo: str)
                - aplica=True: Continuar con calculo
                - aplica=False: Retornar 0 con motivo indicado
        """
        # Mapeo de prestacion a campo has_* del tipo de contrato
        benefit_map = {
            'prima': 'has_prima',
            'cesantias': 'has_cesantias',
            'intereses': 'has_intereses_cesantias',
            'vacaciones': 'has_vacaciones',
        }

        benefit_field = benefit_map.get(tipo_prestacion)
        if not benefit_field:
            return False, f'{tipo_prestacion.upper()} - Tipo de prestacion no reconocido'

        # Validar tipo de contrato (similar a auxilios.py _validate_auxilio_prestacion)
        if contract.contract_type_id:
            # Verificar si el tipo de contrato tiene la prestacion habilitada
            has_benefit = getattr(contract.contract_type_id, benefit_field, False)
            if not has_benefit:
                tipo_nombre = contract.contract_type_id.name or 'Sin nombre'
                return False, f'{tipo_prestacion.upper()} - Tipo contrato {tipo_nombre} no tiene {tipo_prestacion} habilitada'

        # Si no hay tipo de contrato, aplicar por defecto (comportamiento legacy)
        # excepto para aprendices SENA que requieren tipo de contrato
        if not contract.contract_type_id:
            if employee.tipo_coti_id and employee.tipo_coti_id.code in ['12', '19']:
                return False, f'{tipo_prestacion.upper()} - Aprendiz requiere tipo de contrato configurado'


        return True, ''

    def _descuenta_ausencias_prestacion(self, contract, tipo_prestacion):
        """
        Determina si se deben descontar ausencias para una prestacion especifica.

        El tipo de contrato puede definir comportamientos especiales:
        - Sin tipo de contrato: usar regla por defecto (si descuenta)
        - Con tipo de contrato: respetar configuracion especifica si existe

        Args:
            contract: hr.contract
            tipo_prestacion: 'prima', 'cesantias', 'intereses', 'vacaciones'

        Returns:
            bool: True si se deben descontar ausencias
        """
        # Por defecto, las prestaciones descuentan ausencias no pagadas
        descuenta_default = True

        # Si el tipo de contrato tiene configuracion especifica, usarla
        if contract.contract_type_id:
            # Campos opcionales para configuracion por tipo de contrato
            # Ej: no_descontar_ausencias_prima, no_descontar_ausencias_cesantias
            campo_no_descuenta = f'no_descontar_ausencias_{tipo_prestacion}'
            try:
                if campo_no_descuenta in contract.contract_type_id._fields:
                    return not getattr(contract.contract_type_id, campo_no_descuenta)
            except (AttributeError, KeyError):
                pass

        return descuenta_default

    # =========================================================================
    # TABLA DE REGLAS BASE MARCADAS
    # =========================================================================

    def _get_reglas_base_prestacion(self, localdict, tipo_prestacion):
        """
        Obtiene tabla de reglas que hacen base para una prestacion especifica.
        
        Muestra las reglas marcadas con el campo base_* correspondiente
        y su valor en la nomina actual.
        
        Args:
            localdict: Diccionario con rules, slip, contract
            tipo_prestacion: 'prima', 'cesantias', 'intereses', 'vacaciones', 'auxilio'
            
        Returns:
            dict: {
                'reglas': [
                    {
                        'codigo': str,
                        'nombre': str,
                        'valor': float,
                        'cantidad': float,
                        'campo_base': str,
                        'categoria': str,
                    }
                ],
                'total_base': float,
                'tipo_prestacion': str,
                'campo_filtro': str,
            }
        """
        rules = localdict.get('rules', {})
        
        # Mapeo de tipo de prestacion a campo de filtro
        campo_map = {
            'prima': get_prestacion_base_field('prima', contexto='liquidacion'),
            'cesantias': get_prestacion_base_field('cesantias', contexto='liquidacion'),
            'intereses': get_prestacion_base_field('intereses', contexto='liquidacion'),
            'vacaciones': get_prestacion_base_field('vacaciones', contexto='liquidacion'),
            'vacaciones_dinero': get_prestacion_base_field('vacaciones_dinero', contexto='liquidacion'),
            'auxilio': 'base_auxtransporte_tope',
            'seguridad_social': 'base_seguridad_social',
        }

        campo_filtro = campo_map.get(tipo_prestacion, f'base_{tipo_prestacion}')
        
        reglas_base = []
        total_base = 0.0
        
        for code, rule_data in rules.items():
            if not rule_data or code == 'BASIC':
                continue
            
            rule_obj = rule_data.rule
            if not rule_obj:
                continue
            
            # Verificar si tiene el campo marcado
            tiene_base = getattr(rule_obj, campo_filtro, False)
            if not tiene_base:
                continue
            
            valor = rule_data.total
            cantidad = rule_data.quantity
            
            # Obtener categoria
            categoria = ''
            if rule_obj.category_id:
                categoria = rule_obj.category_id.code or rule_obj.category_id.name
            
            reglas_base.append({
                'codigo': code,
                'nombre': rule_obj.name or code,
                'valor': valor,
                'cantidad': cantidad,
                'campo_base': campo_filtro,
                'categoria': categoria,
            })
            
            total_base += valor
        
        # Ordenar por valor descendente
        reglas_base.sort(key=lambda x: x['valor'], reverse=True)
        
        return {
            'reglas': reglas_base,
            'total_base': total_base,
            'tipo_prestacion': tipo_prestacion,
            'campo_filtro': campo_filtro,
            'cantidad_reglas': len(reglas_base),
        }

    def _get_tabla_reglas_base_todas(self, localdict):
        """
        Obtiene tabla completa de reglas base para TODAS las prestaciones.
        
        Util para mostrar en trazabilidad o reportes de nomina.
        
        Args:
            localdict: Diccionario con rules, slip, contract
            
        Returns:
            dict: {
                'prima': {...},
                'cesantias': {...},
                'vacaciones': {...},
                'auxilio': {...},
                'resumen': [
                    {'tipo': str, 'cantidad': int, 'total': float}
                ]
            }
        """
        tipos = ['prima', 'cesantias', 'vacaciones', 'vacaciones_dinero', 'auxilio', 'seguridad_social']
        
        resultado = {}
        resumen = []
        
        for tipo in tipos:
            info = self._get_reglas_base_prestacion(localdict, tipo)
            resultado[tipo] = info
            resumen.append({
                'tipo': tipo,
                'cantidad': info['cantidad_reglas'],
                'total': info['total_base'],
                'campo': info['campo_filtro'],
            })
        
        resultado['resumen'] = resumen
        return resultado

    def _format_tabla_reglas_base(self, reglas_info):
        """
        Formatea la tabla de reglas base para mostrar en log o interfaz.
        
        Args:
            reglas_info: Resultado de _get_reglas_base_prestacion
            
        Returns:
            str: Tabla formateada
        """
        if not reglas_info or not reglas_info.get('reglas'):
            return f"No hay reglas marcadas con {reglas_info.get('campo_filtro', '')}"
        
        lineas = []
        lineas.append(f"\n{'='*70}")
        lineas.append(f"REGLAS BASE PARA {reglas_info['tipo_prestacion'].upper()}")
        lineas.append(f"Campo filtro: {reglas_info['campo_filtro']}")
        lineas.append(f"{'='*70}")
        lineas.append(f"{'Codigo':<15} {'Nombre':<30} {'Valor':>15} {'Cat':>8}")
        lineas.append(f"{'-'*70}")
        
        for regla in reglas_info['reglas']:
            lineas.append(
                f"{regla['codigo']:<15} "
                f"{regla['nombre'][:30]:<30} "
                f"{regla['valor']:>15,.2f} "
                f"{regla['categoria']:>8}"
            )
        
        lineas.append(f"{'-'*70}")
        lineas.append(f"{'TOTAL BASE':<46} {reglas_info['total_base']:>15,.2f}")
        lineas.append(f"Cantidad de reglas: {reglas_info['cantidad_reglas']}")
        lineas.append(f"{'='*70}\n")
        
        return '\n'.join(lineas)

    def _get_conceptos_adicionales_prestacion(self, contract, slip, tipo_prestacion, date_from=None, date_to=None, es_provision_simple=False):
        """
        Obtiene los conceptos del contrato con proyectar_prestaciones=True que afectan la base de prestaciones.

        IMPORTANTE: Solo busca conceptos proyectados del contrato. Los valores de nómina ya están en rules.

        Args:
            contract: hr.contract
            slip: hr.payslip
            tipo_prestacion: 'prima', 'cesantias', 'intereses', 'vacaciones'
            date_from: Fecha inicio del período de prestación
            date_to: Fecha fin del período de prestación
            es_provision_simple: Si True, retorna vacío (los conceptos ya están en rules)

        Returns:
            dict: {
                'conceptos_sumar': [{'id', 'nombre', 'valor', 'tipo'}],
                'conceptos_restar': [{'id', 'nombre', 'valor', 'tipo'}],
                'total_sumar': float,
                'total_restar': float,
                'neto': float - (total_sumar - total_restar)
            }
        """
        resultado = {
            'conceptos_sumar': [],
            'conceptos_restar': [],
            'total_sumar': 0.0,
            'total_restar': 0.0,
            'neto': 0.0
        }

        if not contract:
            return resultado

        # Si es provisión simple, retornar vacío (los conceptos ya están en rules)
        if es_provision_simple:
            return resultado

        # Usar fechas del período de prestación
        if not date_from or not date_to:
            if slip:
                date_from = slip.date_from
                date_to = slip.date_to
            else:
                return resultado

        # Buscar solo conceptos con proyectar_prestaciones=True del contrato
        domain = [
            ('contract_id', '=', contract.id),
            ('proyectar_prestaciones', '=', True),
            ('state', '=', 'done'),
            '|',
            ('date_start', '=', False),
            ('date_start', '<=', date_to),
            '|',
            ('date_end', '=', False),
            ('date_end', '>=', date_from),
        ]

        ConceptModel = self.env.get('hr.contract.concepts')
        if ConceptModel is None:
            return resultado

        conceptos = ConceptModel.search(domain)

        for concepto in conceptos:
            valor = concepto.amount or 0.0
            if valor == 0:
                continue

            info_concepto = {
                'id': concepto.id,
                'nombre': concepto.input_id.name if concepto.input_id else f'Concepto #{concepto.id}',
                'valor': abs(valor),
                'tipo': concepto.type_deduction or 'fijo',
                'dev_or_ded': 'devengo' if not concepto.type_deduction else 'deduccion',
            }

            if not concepto.type_deduction:
                resultado['conceptos_sumar'].append(info_concepto)
                resultado['total_sumar'] += abs(valor)
            else:
                resultado['conceptos_restar'].append(info_concepto)
                resultado['total_restar'] += abs(valor)

        resultado['neto'] = resultado['total_sumar'] - resultado['total_restar']

        return resultado

    def _validar_base_auxilio_prestacion(self, contract, salario_base, salario_variable, smmlv, tipo_prestacion, config_params, employee=None, annual_parameters=None):
        """
        Valida si el auxilio de transporte aplica para una prestacion considerando
        el campo only_wage del contrato para determinar la base de validacion del tope.

        Args:
            contract: hr.contract
            salario_base: float - Salario base mensual
            salario_variable: float - Devengos salariales variables
            smmlv: float - Salario minimo legal vigente
            tipo_prestacion: 'prima', 'cesantias', 'intereses', 'vacaciones'
            config_params: dict - Parametros de configuracion
            employee: hr.employee (opcional) - Para validacion de aprendices
            annual_parameters: hr.annual.parameters (opcional) - Para validacion de aprendices

        Returns:
            dict: {
                'aplica': bool,
                'razon': str,
                'base_validacion': float,
                'tope': float,
                'only_wage_usado': str
            }
        """
        resultado = {
            'aplica': False,
            'razon': '',
            'base_validacion': 0.0,
            'tope': 2 * smmlv if smmlv else 0.0,
            'only_wage_usado': 'wage'
        }

        # 1. Validar tipo de contrato (has_auxilio_transporte)
        if contract.contract_type_id:
            if not contract.contract_type_id.has_auxilio_transporte:
                resultado['razon'] = 'Tipo de contrato no tiene derecho a auxilio de transporte'
                return resultado

        # 2. Validar configuracion del contrato
        if contract.not_pay_auxtransportation:
            resultado['razon'] = 'Contrato marcado como no liquidar auxilio'
            return resultado

        modality_aux = contract.modality_aux or 'basico'
        if modality_aux == 'no':
            resultado['razon'] = 'Modalidad de auxilio: No aplica'
            return resultado

        # 3. Validar aprendices usando parametros anuales
        if employee and annual_parameters and not contract.not_validate_top_auxtransportation:
            if employee.tipo_coti_id:
                tipo_coti = employee.tipo_coti_id.code
                # Tipo cotizante 12 = Aprendiz etapa lectiva
                if tipo_coti == '12' and not annual_parameters.aux_apr_lectiva:
                    resultado['razon'] = 'Aprendiz etapa lectiva sin auxilio (param anual)'
                    return resultado
                # Tipo cotizante 19 = Aprendiz etapa productiva
                elif tipo_coti == '19' and not annual_parameters.aux_apr_prod:
                    resultado['razon'] = 'Aprendiz etapa productiva sin auxilio (param anual)'
                    return resultado

        # 4. Intereses NUNCA incluye auxilio directamente
        # (se calcula sobre el valor de cesantias que ya incluye auxilio si aplica)
        if tipo_prestacion == 'intereses':
            resultado['razon'] = 'Intereses se calcula sobre cesantias (que ya incluye auxilio)'
            return resultado

        # 5. Validar configuracion por tipo de prestacion
        config_field_map = {
            'prima': 'prima_incluye_auxilio',
            'cesantias': 'cesantias_incluye_auxilio',
            'vacaciones': 'vacaciones_incluye_auxilio',
        }
        config_field = config_field_map.get(tipo_prestacion, 'prima_incluye_auxilio')
        if not config_params.get(config_field, False):
            resultado['razon'] = f'Configuracion: {tipo_prestacion} no incluye auxilio'
            return resultado

        # 6. Validar tope salarial si no esta exento
        if config_params.get('aux_prst') or contract.not_validate_top_auxtransportation:
            resultado['aplica'] = True
            resultado['razon'] = 'Exento de validacion de tope'
            return resultado

        # 7. Determinar base de validacion segun only_wage del contrato (logica centralizada)
        only_wage = contract.only_wage or 'wage'
        resultado['only_wage_usado'] = only_wage

        base_validacion = self.env['hr.salary.rule.aux']._calcular_base_validacion_tope(
            only_wage, salario_base, salario_variable
        )
        resultado['base_validacion'] = base_validacion

        # 8. Validar tope de 2 SMMLV
        if base_validacion >= resultado['tope']:
            resultado['razon'] = f'Salario ${base_validacion:,.0f} supera tope 2 SMMLV ${resultado["tope"]:,.0f}'
            return resultado

        resultado['aplica'] = True
        resultado['razon'] = 'Dentro del tope legal'
        return resultado

    def _calcular_dias_adicionales_prestacion(self, contract, slip, tipo_prestacion, dias_base):
        """
        Calcula dias adicionales a agregar o restar del calculo de prestaciones.

        Considera:
        - Dias adicionales configurados en el contrato
        - Cuotas especiales o procesos especiales
        - Ajustes manuales

        Args:
            contract: hr.contract
            slip: hr.payslip
            tipo_prestacion: 'prima', 'cesantias', 'intereses', 'vacaciones'
            dias_base: int - Dias calculados por el periodo

        Returns:
            dict: {
                'dias_base': int,
                'dias_adicionales': int,
                'dias_descuento': int,
                'dias_total': int,
                'motivo_adicional': str,
                'motivo_descuento': str
            }
        """
        resultado = {
            'dias_base': dias_base,
            'dias_adicionales': 0,
            'dias_descuento': 0,
            'dias_total': dias_base,
            'motivo_adicional': '',
            'motivo_descuento': ''
        }

        if not contract:
            return resultado

        # 1. Verificar dias manuales del slip
        if slip and slip.use_manual_days and slip.manual_days:
            dias_manual = slip.manual_days
            diferencia = dias_manual - dias_base
            if diferencia > 0:
                resultado['dias_adicionales'] = diferencia
                resultado['motivo_adicional'] = f'Dias manuales configurados: {dias_manual}'
            elif diferencia < 0:
                resultado['dias_descuento'] = abs(diferencia)
                resultado['motivo_descuento'] = f'Dias manuales configurados: {dias_manual}'
            resultado['dias_total'] = dias_manual
            return resultado

        # 2. Verificar dias adicionales en contrato (si existe el campo)
        campo_dias_adicionales = f'dias_adicionales_{tipo_prestacion}'
        try:
            if campo_dias_adicionales in contract._fields:
                dias_adicionales_contrato = contract[campo_dias_adicionales] or 0
                if dias_adicionales_contrato != 0:
                    if dias_adicionales_contrato > 0:
                        resultado['dias_adicionales'] = dias_adicionales_contrato
                        resultado['motivo_adicional'] = f'Configuracion contrato: +{dias_adicionales_contrato} dias'
                    else:
                        resultado['dias_descuento'] = abs(dias_adicionales_contrato)
                        resultado['motivo_descuento'] = f'Configuracion contrato: {dias_adicionales_contrato} dias'
        except (AttributeError, KeyError):
            pass

        # 3. Verificar cuotas especiales en el tipo de contrato (si existe)
        if contract.contract_type_id:
            campo_cuota_especial = f'cuota_especial_{tipo_prestacion}'
            try:
                cuota_especial = contract.contract_type_id[campo_cuota_especial] or 0
                if cuota_especial != 0:
                    if cuota_especial > 0:
                        resultado['dias_adicionales'] += cuota_especial
                        motivo = resultado['motivo_adicional']
                        resultado['motivo_adicional'] = f"{motivo}, Cuota especial: +{cuota_especial}" if motivo else f"Cuota especial: +{cuota_especial}"
                    else:
                        resultado['dias_descuento'] += abs(cuota_especial)
                        motivo = resultado['motivo_descuento']
                        resultado['motivo_descuento'] = f"{motivo}, Cuota especial: {cuota_especial}" if motivo else f"Cuota especial: {cuota_especial}"
            except (AttributeError, KeyError):
                pass

        # Calcular total final
        resultado['dias_total'] = dias_base + resultado['dias_adicionales'] - resultado['dias_descuento']

        # Asegurar que no sea negativo
        if resultado['dias_total'] < 0:
            resultado['dias_total'] = 0

        return resultado

    # =========================================================================
    # METODOS LEGACY
    # =========================================================================

    def _create_update_history(self, slip, contract, history_model, history_vals, date_from, date_to, search_fields=None):
        """
        Crea o actualiza registro de historial para prestaciones sociales.

        SE EJECUTA SOLO SI:
        - Es liquidación de contrato (slip.struct_process == 'contrato' and slip.date_liquidacion)
        - NO es provisión
        - NO es reversión

        Args:
            slip: Registro de hr.payslip
            contract: Registro de hr.contract
            history_model: Nombre del modelo ('hr.vacation', 'hr.history.prima', 'hr.history.cesantias')
            history_vals: Diccionario con valores específicos del modelo
            date_from: Fecha inicio del período
            date_to: Fecha fin del período
            search_fields: Dict adicional para identificar el tipo específico

        Returns:
            created_record: Registro creado/actualizado o False
        """
        is_liquidacion = slip.struct_process == 'contrato' and slip.date_liquidacion
        is_provision = slip.is_provision if 'is_provision' in slip._fields else False
        is_reversion = slip.state == 'cancel' or (slip.is_reversal if 'is_reversal' in slip._fields else False)

        if not is_liquidacion or is_provision or is_reversion:
            return False

        search_domain = [
            ('payslip', '=', slip.id),
            ('employee_id', '=', contract.employee_id.id),
            ('contract_id', '=', contract.id),
        ]

        if search_fields:
            for field, value in search_fields.items():
                search_domain.append((field, '=', value))

        existing_record = self.env[history_model].search(search_domain, limit=1)

        common_vals = {
            'employee_id': contract.employee_id.id,
            'contract_id': contract.id,
            'initial_accrual_date': date_from,
            'final_accrual_date': date_to,
            'payslip': slip.id,
        }

        final_vals = {**common_vals, **history_vals}

        if existing_record:
            existing_record.write(final_vals)
            return existing_record
        else:
            return self.env[history_model].create(final_vals)

    def _get_prestacion_previous_values(self, contract, code_regla, date_from, date_to):
        """
        Obtiene valores anteriores de una prestación para comparación.

        Args:
            contract: Contrato del empleado
            code_regla: Código de la regla (PRIMA, CESANTIAS, etc.)
            date_from: Fecha inicio período actual
            date_to: Fecha fin período actual

        Returns:
            dict: {
                'valor_anterior': float,
                'payslip_lines': list,
                'fecha_ultimo_calculo': date,
                'payslip_id_anterior': int,
                'cantidad_calculos_anteriores': int
            }
        """
        resultado = {
            'valor_anterior': 0,
            'payslip_lines': [],
            'fecha_ultimo_calculo': None,
            'payslip_id_anterior': None,
            'cantidad_calculos_anteriores': 0
        }

        if not contract or not code_regla:
            return resultado

        # Buscar líneas anteriores de la misma prestación
        domain = [
            ('slip_id.contract_id', '=', contract.id),
            ('code', '=', code_regla),
            ('state_slip', 'in', ['done', 'paid']),
            ('date_from', '<', date_from),
        ]

        previous_lines = self.env['hr.payslip.line'].search(
            domain,
            order='date_to desc',
            limit=5
        )

        summary = self._build_payslip_lines_summary(
            previous_lines,
            include_total=True,
            include_amount=True,
            include_quantity=True,
        )
        resultado.update({
            'valor_anterior': summary['total'],
            'payslip_lines': summary['payslip_lines'],
            'fecha_ultimo_calculo': summary['fecha_ultimo_calculo'],
            'payslip_id_anterior': summary['payslip_id_anterior'],
            'cantidad_calculos_anteriores': summary['count'],
        })

        return resultado

    def _get_reglas_usadas_prestacion(self, localdict, tipo_prestacion, ids_by_type):
        """
        Obtiene las reglas salariales usadas para el cálculo de una prestación.

        Args:
            localdict: Diccionario de contexto con rules, categories, etc.
            tipo_prestacion: 'prima', 'cesantias', 'intereses', 'vacaciones'
            ids_by_type: Diccionario con IDs agrupados por tipo

        Returns:
            dict: {
                'detalle': [{rule_id, codigo, nombre, valor, categoria}],
                'rule_ids': [int] - Lista de IDs de reglas salariales usadas
            }
        """
        reglas_usadas = []
        rule_ids_set = set()

        campo_base_map = {
            'prima': get_prestacion_base_field('prima', contexto='liquidacion'),
            'cesantias': get_prestacion_base_field('cesantias', contexto='liquidacion'),
            'intereses': get_prestacion_base_field('intereses', contexto='liquidacion'),
            'vacaciones': get_prestacion_base_field('vacaciones', contexto='liquidacion'),
        }

        campo_base = campo_base_map.get(
            tipo_prestacion,
            get_prestacion_base_field('prima', contexto='liquidacion'),
        )
        rules = localdict.get('rules', {})

        if not rules:
            return {'detalle': reglas_usadas, 'rule_ids': list(rule_ids_set)}

        for code, rule_data in rules.items():
            try:
                rule = rule_data.rule
            except (AttributeError, KeyError):
                rule = None
            if not rule:
                continue

            try:
                if campo_base in rule._fields:
                    tiene_base = getattr(rule, campo_base)
                else:
                    tiene_base = False
            except (AttributeError, KeyError):
                tiene_base = False

            if tiene_base and rule_data.total != 0:
                rule_ids_set.add(rule.id)
                reglas_usadas.append({
                    'rule_id': rule.id,
                    'codigo': code,
                    'nombre': rule.name,
                    'valor': rule_data.total,
                    'categoria': rule_data.category_code if rule_data.category_code else ''
                })

        return {
            'detalle': reglas_usadas,
            'rule_ids': list(rule_ids_set)
        }

    def _get_periodo_prestacion(self, slip, contract, tipo_prestacion):
        """
        Determina el período de cálculo según tipo de prestación.

        IMPORTANTE: Si es liquidación de prima en nómina (pay_primas_in_payroll) y se liquida
        dentro de una quincena, usa date_prima si existe para determinar el período correcto.

        Args:
            slip: Nómina actual
            contract: Contrato del empleado
            tipo_prestacion: 'prima', 'cesantias', 'intereses', 'vacaciones'

        Returns:
            dict: {
                'date_from': fecha_inicio,
                'date_to': fecha_fin,
                'dias': días del período,
                'origen': descripción del origen de fechas
            }
        """
        date_to = slip.date_to
        es_liquidacion = slip.struct_process == 'contrato' and slip.date_liquidacion
        es_prima_en_nomina = slip.pay_primas_in_payroll and tipo_prestacion == 'prima'
        es_estructura_prima = slip.struct_process == 'prima'

        if es_liquidacion:
            date_to = slip.date_liquidacion

        if tipo_prestacion in ['cesantias', 'intereses']:
            date_from = date(date_to.year, 1, 1)
            origen = 'Año completo'
        elif tipo_prestacion == 'prima':
            # Si es liquidación de prima en nómina o estructura de primas, validar fecha de quincena
            if (es_prima_en_nomina or es_estructura_prima) and slip.date_prima and slip.date_to.day == 15:
                # Usar date_prima para determinar el semestre, pero calcular desde el inicio del semestre
                fecha_referencia = slip.date_prima
                if fecha_referencia.month <= 6:
                    date_from = date(fecha_referencia.year, 1, 1)
                    origen = f'Primer semestre - Desde {date_from.strftime("%d/%m/%Y")}'
                else:
                    date_from = date(fecha_referencia.year, 7, 1)
                    origen = f'Segundo semestre - Desde {date_from.strftime("%d/%m/%Y")}'
            else:
                # Lógica estándar: inicio del semestre
                if date_to.month <= 6:
                    date_from = date(date_to.year, 1, 1)
                    origen = 'Primer semestre'
                else:
                    date_from = date(date_to.year, 7, 1)
                    origen = 'Segundo semestre'
        else:  # vacaciones
            date_from = contract.date_start if contract.date_start else slip.date_from
            origen = 'Desde inicio contrato'

        # Ajustar si contrato inició después del date_from calculado
        if contract.date_start and contract.date_start > date_from:
            date_from = contract.date_start
            if tipo_prestacion == 'vacaciones':
                origen = f'Desde inicio contrato ({contract.date_start})'
            else:
                origen = f'{origen} - Ajustado desde inicio contrato ({contract.date_start})'

        dias = days360(date_from, date_to)

        return {
            'date_from': date_from,
            'date_to': date_to,
            'dias': dias,
            'origen': origen
        }

    def _obtener_saldo_contable_provision(self, data_payslip, codigo_regla):
        """
        Obtiene el saldo contable actual de una provisión.

        Args:
            data_payslip: Diccionario con datos de liquidación
            codigo_regla: Código de la regla (PRV_VAC, PRV_CES, etc.)

        Returns:
            float: Saldo contable de la provisión
        """
        contract = data_payslip.get('contract')
        if not contract:
            return 0.0

        # Buscar última línea de provisión confirmada
        domain = [
            ('code', '=', codigo_regla),
            ('slip_id.contract_id', '=', contract.id),
            ('slip_id.state', '=', 'done'),
        ]

        last_provision = self.env['hr.payslip.line'].search(
            domain,
            order='slip_id desc',
            limit=1
        )

        if last_provision:
            return last_provision.total

        return 0.0

    def _get_employee_address_id(self, employee):
        """
        Obtiene el ID de dirección del empleado.

        Args:
            employee: Registro hr.employee

        Returns:
            int: ID del partner de dirección
        """
        if employee.work_contact_id:
            return employee.work_contact_id.id
        elif employee.partner_id:
            return employee.partner_id.id
        return False

    def _get_prestacion_accumulated(self, localdict, date_from, date_to, code_regla):
        """
        Obtiene el total acumulado de una prestación en un período.

        Args:
            localdict: Diccionario de contexto
            date_from: Fecha inicio
            date_to: Fecha fin
            code_regla: Código de la regla

        Returns:
            dict: {
                'total': float,
                'lines': list,
                'count': int
            }
        """
        contract = localdict.get('contract')
        slip = localdict.get('slip')
        if not contract:
            return {'total': 0, 'lines': [], 'count': 0}

        # Determinar tipo de prestación según código de regla
        tipo_map = {
            'PRIMA': 'prima',
            'CESANTIAS': 'cesantias',
            'VACCONTRATO': 'vacaciones',
            'VACACIONES': 'vacaciones',
            'INTCESANTIAS': 'intereses_cesantias',
        }
        tipo_prestacion = tipo_map.get(code_regla, 'all')

        # Usar servicio centralizado de consultas
        query_service = self.env['period.payslip.query.service']
        result = query_service.get_prestaciones_data(
            contract_id=contract.id,
            date_from=date_from,
            date_to=date_to,
            tipo_prestacion=tipo_prestacion,
            exclude_payslip_id=slip.id if slip else None,
            states=('done', 'paid'),
        )

        # Filtrar por código de regla específico
        filtered_lines = [
            line for line in result.get('list', [])
            if line.get('rule_code') == code_regla
        ]

        total = sum(line.get('total', 0.0) for line in filtered_lines)

        return {
            'total': total,
            'lines': [
                {
                    'id': line['line_id'],
                    'total': line.get('total', 0.0),
                    'date': line.get('date_to')
                }
                for line in filtered_lines
            ],
            'count': len(filtered_lines)
        }

    def _get_prestacion_pagada_periodo(self, localdict, date_from, date_to, code_regla, states=None):
        """
        Obtiene el total pagado en el período para una prestación específica.

        Args:
            localdict: Diccionario de contexto
            date_from: Fecha inicio
            date_to: Fecha fin
            code_regla: Código de la regla (PRIMA, CESANTIAS, INTCESANTIAS, VACCONTRATO)
            states: Estados a incluir (default: done, paid)

        Returns:
            dict: {'total': float, 'line_ids': list, 'count': int}
        """
        contract = localdict.get('contract')
        slip = localdict.get('slip')
        if not contract:
            return {'total': 0.0, 'line_ids': [], 'count': 0}

        normalized_states = states or ('done', 'paid')

        tipo_map = {
            'PRIMA': 'prima',
            'CESANTIAS': 'cesantias',
            'VACCONTRATO': 'vacaciones',
            'VACACIONES': 'vacaciones',
            'INTCESANTIAS': 'intereses_cesantias',
        }
        tipo_prestacion = tipo_map.get(code_regla, 'all')

        query_service = self.env['period.payslip.query.service']
        result = query_service.get_prestaciones_data(
            contract_id=contract.id,
            date_from=date_from,
            date_to=date_to,
            tipo_prestacion=tipo_prestacion,
            exclude_payslip_id=slip.id if slip else None,
            states=normalized_states,
        )

        filtered_lines = [
            line for line in result.get('list', [])
            if line.get('rule_code') == code_regla
        ]

        total_pagado = sum(line.get('total', 0.0) for line in filtered_lines)
        line_ids = [line.get('line_id') for line in filtered_lines if line.get('line_id')]

        return {
            'total': total_pagado,
            'line_ids': line_ids,
            'count': len(line_ids),
        }

    def _restar_pagado_periodo(self, localdict, date_from, date_to, code_regla, total_actual,
                               tipo='prestacion', states=None):
        """
        Resta valores ya pagados en el período para evitar duplicidades.

        Returns:
            dict: {
                'total_ajustado': float,
                'total_pagado': float,
                'ajuste': float,
                'line_ids': list,
                'tipo': str
            }
        """
        total_pagado = 0.0
        line_ids = []

        if tipo == 'provision':
            total_pagado = self._get_total_previous_provision(localdict, date_from, date_to, code_regla) or 0.0
        else:
            data_pagado = self._get_prestacion_pagada_periodo(
                localdict, date_from, date_to, code_regla, states=states
            )
            total_pagado = data_pagado.get('total', 0.0)
            line_ids = data_pagado.get('line_ids', [])

        total_actual = total_actual or 0.0
        total_pagado = total_pagado or 0.0
        total_ajustado = total_actual - total_pagado

        return {
            'total_ajustado': total_ajustado,
            'total_pagado': total_pagado,
            'ajuste': -total_pagado,
            'line_ids': line_ids,
            'tipo': tipo,
        }

    def _restar_pagado_prestacion(self, localdict, date_from, date_to, code_regla, total_actual, states=None):
        return self._restar_pagado_periodo(
            localdict, date_from, date_to, code_regla, total_actual,
            tipo='prestacion', states=states
        )

    def _restar_pagado_provision(self, localdict, date_from, date_to, code_regla, total_actual, states=None):
        return self._restar_pagado_periodo(
            localdict, date_from, date_to, code_regla, total_actual,
            tipo='provision', states=states
        )

    def _restar_pagado_vacaciones(self, localdict, date_from, date_to, code_regla, total_actual, states=None):
        return self._restar_pagado_periodo(
            localdict, date_from, date_to, code_regla, total_actual,
            tipo='vacaciones', states=states
        )

    def _get_accumulated_payroll_records(self, localdict, date_from, date_to, code_regla):
        """
        Obtiene registros de nómina acumulados para una prestación.

        Args:
            localdict: Diccionario de contexto
            date_from: Fecha inicio
            date_to: Fecha fin
            code_regla: Código de la regla

        Returns:
            recordset: hr.accumulated.payroll records
        """
        contract = localdict.get('contract')
        if not contract:
            return self.env['hr.accumulated.payroll'].browse()

        domain = [
            ('contract_id', '=', contract.id),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
        ]

        return self.env['hr.accumulated.payroll'].search(domain)

    def _get_total_previous_provision(self, localdict, date_from, date_to, code_regla):
        """
        Obtiene el total de provisiones anteriores en el período.

        Args:
            localdict: Diccionario de contexto
            date_from: Fecha inicio período
            date_to: Fecha fin período
            code_regla: Código de la regla

        Returns:
            float: Total de provisiones anteriores
        """
        contract = localdict.get('contract')
        slip = localdict.get('slip')

        if not contract or not slip:
            return 0.0

        domain = [
            ('code', '=', code_regla),
            ('slip_id.contract_id', '=', contract.id),
            ('slip_id.state', '=', 'done'),
            ('slip_id.date_from', '>=', date_from),
            ('slip_id.date_from', '<', slip.date_to),
        ]

        grouped = self.env['hr.payslip.line']._read_group(
            domain,
            groupby=[],
            aggregates=['total:sum'],
        )
        return float(grouped[0][0] or 0.0) if grouped else 0.0

    @api.depends('category_id')
    def _compute_prestaciones_counts(self):
        """Calcula el número de reglas marcadas para prima, cesantías y vacaciones"""
        for rule in self:
            if rule.category_id:
                all_rules = self.search([('category_id', '=', rule.category_id.id)])
                rule.prima_rules_count = len(all_rules.filtered(lambda r: r.base_prima))
                rule.cesantias_rules_count = len(all_rules.filtered(lambda r: r.base_cesantias))
                rule.vacaciones_rules_count = len(all_rules.filtered(
                    lambda r: r.base_vacaciones or r.base_vacaciones_dinero
                ))
            else:
                rule.prima_rules_count = 0
                rule.cesantias_rules_count = 0
                rule.vacaciones_rules_count = 0

    def _get_consolidado_ano_anterior(self, employee, contract, year, provision_type):
        """
        Busca el consolidado de provisiones del año anterior.
        PRIMERA OPCION para recuperar cesantías e intereses del año pasado.

        Busca en hr_executing_provisions_details el último registro del año
        especificado para el empleado/contrato y tipo de provisión.

        Args:
            employee: Registro hr.employee
            contract: Registro hr.contract
            year: Año a buscar (ej: 2025 para buscar provisiones de diciembre 2025)
            provision_type: Tipo de provisión ('cesantias', 'intcesantias', 'prima', 'vacaciones')

        Returns:
            dict: {
                'provision_id': int,
                'employee_id': int,
                'contract_id': int,
                'year': int,
                'month': int,
                'value_wage': float,      # Salario base
                'value_base': float,      # Base de cálculo
                'amount': float,          # Valor acumulado
                'value_payments': float,  # Pagos realizados
                'current_payable_value': float,  # Valor neto a pagar (lo que usaremos)
                'value_balance': float,   # Saldo
            }
            o None si no existe consolidado
        """
        if not employee or not contract or not year or not provision_type:
            return None

        # Buscar provisión del año especificado, preferentemente diciembre
        # pero si no existe, buscar el último mes disponible
        query = """
            SELECT
                pd.id as provision_id,
                pd.employee_id,
                pd.contract_id,
                p.year,
                p.month,
                COALESCE(pd.value_wage, 0) as value_wage,
                COALESCE(pd.value_base, 0) as value_base,
                COALESCE(pd.amount, 0) as amount,
                COALESCE(pd.value_payments, 0) as value_payments,
                COALESCE(pd.current_payable_value, 0) as current_payable_value,
                COALESCE(pd.value_balance, 0) as value_balance
            FROM hr_executing_provisions_details pd
            INNER JOIN hr_executing_provisions p ON p.id = pd.executing_provisions_id
            WHERE
                pd.employee_id = %(employee_id)s
                AND pd.contract_id = %(contract_id)s
                AND p.year = %(year)s
                AND pd.provision = %(provision_type)s
            ORDER BY p.month DESC
            LIMIT 1
        """

        try:
            self.env.cr.execute(query, {
                'employee_id': employee.id,
                'contract_id': contract.id,
                'year': year,
                'provision_type': provision_type
            })
            result = self.env.cr.dictfetchone()

            if result:
                return {
                    'provision_id': result['provision_id'],
                    'employee_id': result['employee_id'],
                    'contract_id': result['contract_id'],
                    'year': result['year'],
                    'month': result['month'],
                    'value_wage': float(result['value_wage'] or 0),
                    'value_base': float(result['value_base'] or 0),
                    'amount': float(result['amount'] or 0),
                    'value_payments': float(result['value_payments'] or 0),
                    'current_payable_value': float(result['current_payable_value'] or 0),
                    'value_balance': float(result['value_balance'] or 0),
                }

        except Exception as e:
            # Log error pero no fallar - el fallback calculará manualmente
            import logging
            _logger = logging.getLogger(__name__)
            _logger.warning(
                f"Error buscando consolidado año anterior: {e}. "
                f"Empleado: {employee.id}, Contrato: {contract.id}, "
                f"Año: {year}, Tipo: {provision_type}"
            )

        return None
