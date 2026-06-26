# -*- coding: utf-8 -*-

"""
PRESTACIONES SOCIALES - VACACIONES
==================================
Cálculo de vacaciones en liquidación de contrato.
"""

from odoo import models
from datetime import timedelta
from dateutil.relativedelta import relativedelta
from odoo.addons.lavish_hr_employee.models.hr_slip_utils import days360


class HrSalaryRulePrestacionesVacaciones(models.AbstractModel):
    _inherit = 'hr.salary.rule.prestaciones'

    def _vaccontrato(self, localdict):
        """
        VACACIONES DE CONTRATO - Terminación de Contrato
        Calcula vacaciones proporcionales al terminar el contrato

        FLUJO:
        1. date_from = date_vacaciones (campo manual) o buscar último corte automático
        2. date_to = date_liquidacion (fecha de terminación del contrato)
        3. Calcular días hábiles y festivos en el período
        4. Aplicar lógica de inclusión de festivos si está habilitado
        """
        slip = localdict['slip']
        contract = localdict['contract']

        if not slip.date_liquidacion:
            return 0, 0, 0, "VACACIONES - Requiere fecha de liquidación", "", {}

        date_to = slip.date_liquidacion

        # ══════════════════════════════════════════════════════════════════════
        # DETERMINAR FECHA DE INICIO SEGÚN MODO
        # ══════════════════════════════════════════════════════════════════════

        usar_dias_manuales = slip.use_manual_vacation_days

        if usar_dias_manuales and slip.manual_vacation_days:
            dias_vac_manuales = slip.manual_vacation_days

            if slip.date_vacaciones:
                date_from = slip.date_vacaciones
                origen_fecha = f"Manual: {dias_vac_manuales} días vac (desde {date_from.strftime('%d/%m/%Y')})"
            else:
                days_needed = dias_vac_manuales * 24

                meses = int(days_needed // 30)
                dias_restantes = int(days_needed % 30)

                date_from = date_to
                if meses > 0:
                    date_from = date_from - relativedelta(months=meses)
                if dias_restantes > 0:
                    date_from = date_from - relativedelta(days=dias_restantes)

                origen_fecha = f"Calculado: {dias_vac_manuales} días vac × 24 = {int(days_needed)} días → desde {date_from.strftime('%d/%m/%Y')}"

        else:
            if slip.date_vacaciones:
                date_from = slip.date_vacaciones
                origen_fecha = f"Fecha manual: {slip.date_vacaciones.strftime('%d/%m/%Y')}"
            else:
                last_vacation = self.env['hr.vacation'].search([
                    ('employee_id', '=', contract.employee_id.id),
                    ('contract_id', '=', contract.id),
                    ('final_accrual_date', '!=', False),
                    ('final_accrual_date', '<', slip.date_liquidacion)
                ], order='final_accrual_date desc', limit=1)

                if last_vacation:
                    date_from = last_vacation.final_accrual_date + timedelta(days=1)
                    origen_fecha = f"Último corte: {last_vacation.final_accrual_date.strftime('%d/%m/%Y')}"
                else:
                    date_from = contract.date_start
                    origen_fecha = f"Inicio contrato: {contract.date_start.strftime('%d/%m/%Y')}"

        # ══════════════════════════════════════════════════════════════════════
        # CALCULAR DÍAS DEL PERÍODO TRABAJADO
        # ══════════════════════════════════════════════════════════════════════

        dias_periodo_360 = days360(date_from, date_to)

        # ══════════════════════════════════════════════════════════════════════
        # LÓGICA DE FESTIVOS (HACIA EL FUTURO)
        # ══════════════════════════════════════════════════════════════════════

        dias_festivos_futuro = 0
        festivos_lista = []
        incluir_festivos = slip.include_holidays_in_vacation_settlement

        if incluir_festivos:
            # Los festivos se calculan HACIA EL FUTURO desde la fecha de liquidación
            # iterando día por día hasta completar los días de vacaciones que debe tomar

            # Calcular días de vacaciones que le corresponden
            if usar_dias_manuales and slip.manual_vacation_days:
                dias_vac_a_tomar = slip.manual_vacation_days
            else:
                # Fórmula: días_vacaciones = días_trabajados / 24
                dias_vac_a_tomar = dias_periodo_360 / 24

            # Validar si se trabaja el sábado (campo en employee)
            trabaja_sabado = contract.employee_id.sabado if contract.employee_id else False

            # Iterar día por día hasta completar días de vacaciones
            # NO usar while - usar for con límite
            max_dias_iterar = 90  # Límite de seguridad (3 meses)
            dias_vac_contados = 0

            for i in range(max_dias_iterar):
                if dias_vac_contados >= dias_vac_a_tomar:
                    break

                fecha_actual = date_to + timedelta(days=i)
                dia_semana = fecha_actual.weekday()  # 0=Lun, 6=Dom

                # DOMINGO: siempre es festivo (no cuenta como día de vacación)
                if dia_semana == 6:
                    dias_festivos_futuro += 1
                    festivos_lista.append(f"{fecha_actual.strftime('%d/%m/%Y')} (Domingo)")
                    continue

                # SÁBADO: validar si se trabaja o no
                if dia_semana == 5:
                    if not trabaja_sabado:
                        dias_festivos_futuro += 1
                        festivos_lista.append(f"{fecha_actual.strftime('%d/%m/%Y')} (Sábado)")
                        continue

                # FESTIVO DEL CALENDARIO: usar ensure_holidays
                es_festivo = self.env['lavish.holidays'].ensure_holidays(fecha_actual)

                if es_festivo:
                    # Obtener nombre del festivo para el detalle
                    festivo_obj = self.env['lavish.holidays'].search([
                        ('date', '=', fecha_actual),
                    ], limit=1)
                    nombre_festivo = festivo_obj.name if festivo_obj else 'Festivo'
                    dias_festivos_futuro += 1
                    festivos_lista.append(f"{fecha_actual.strftime('%d/%m/%Y')} ({nombre_festivo})")
                    continue

                # Si llegamos aquí, es un día hábil que cuenta como día de vacación
                dias_vac_contados += 1

            # IMPORTANTE: Los festivos futuros se CONVIERTEN a sistema 360
            # Factor de conversión: 0.417
            # Estos festivos convertidos se suman a los días trabajados para el cálculo del valor
            dias_festivos_futuro_360 = dias_festivos_futuro / 0.417
            dias_a_liquidar = dias_periodo_360 + dias_festivos_futuro_360
        else:
            dias_a_liquidar = dias_periodo_360

        # ══════════════════════════════════════════════════════════════════════
        # VARIABLES PARA TRACKING
        # ══════════════════════════════════════════════════════════════════════

        dias_vac_manuales = slip.manual_vacation_days if usar_dias_manuales else 0

        # ══════════════════════════════════════════════════════════════════════
        # DATOS ADICIONALES PARA EL REPORTE
        # ══════════════════════════════════════════════════════════════════════

        # Inicializar trabaja_sabado para evitar NameError
        trabaja_sabado = contract.employee_id.sabado if contract.employee_id else False

        # Calcular festivos_360 para el reporte (si aplica)
        festivos_360_para_reporte = round(dias_festivos_futuro / 0.417, 2) if incluir_festivos and dias_festivos_futuro > 0 else 0

        datos_detalle = {
            'origen_fecha': origen_fecha,
            'fecha_desde': date_from.strftime('%d/%m/%Y'),
            'fecha_hasta': date_to.strftime('%d/%m/%Y'),
            'dias_periodo_360': dias_periodo_360,
            'dias_festivos_calendario': dias_festivos_futuro,
            'dias_festivos_360': festivos_360_para_reporte,
            'festivos_incluidos': incluir_festivos,
            'festivos_lista': festivos_lista,
            'festivos_detalle': f'Iteración día por día: Domingos siempre festivos, Sábados según calendario, Festivos del calendario. {dias_festivos_futuro} festivos calendario = {festivos_360_para_reporte} días 360 (÷0.417)' if incluir_festivos else None,
            'trabaja_sabado': trabaja_sabado,
            'dias_totales_liquidar': round(dias_a_liquidar, 2),
            'metodo_calculo': 'Manual: Días especificados' if usar_dias_manuales else ('Días 360 + Festivos futuros 360 (iteración día por día)' if incluir_festivos else 'Días 360'),
            'formula': f"({dias_periodo_360} días período + {festivos_360_para_reporte} festivos 360) = {dias_a_liquidar:.2f} días" if incluir_festivos else f"{dias_periodo_360} días período",
            'usar_dias_manuales': usar_dias_manuales,
            'dias_vacaciones_manuales': dias_vac_manuales,
        }

        # Descripción mejorada
        if usar_dias_manuales and dias_vac_manuales > 0:
            descripcion = f"VACACIONES CONTRATO - {dias_vac_manuales} días vac ({date_from.strftime('%d/%m/%Y')} a {date_to.strftime('%d/%m/%Y')})"
            if incluir_festivos and dias_festivos_futuro > 0:
                descripcion += f" + {dias_festivos_futuro} festivos ({festivos_360_para_reporte} días 360)"
        else:
            descripcion = f"VACACIONES CONTRATO - {origen_fecha}"
            if incluir_festivos and dias_festivos_futuro > 0:
                descripcion += f" (Incluye {dias_festivos_futuro} festivos = {festivos_360_para_reporte} días 360)"

        # ══════════════════════════════════════════════════════════════════════
        # CALCULAR PRESTACIÓN SOCIAL
        # ══════════════════════════════════════════════════════════════════════

        resultado = self._compute_social_benefits(
            localdict,
            date_from,
            date_to,
            'vacaciones',
            self.descontar_suspensiones
        )

        if isinstance(resultado, tuple):
            base_diaria, days_worked, rate, nombre, vacio, datos_original = resultado

            if slip.struct_process == 'contrato' and slip.date_liquidacion:
                rules = localdict.get('rules')
                if rules:
                    basic005 = rules.get('BASIC005')
                    if basic005 and basic005.quantity:
                        days_worked = basic005.quantity

                        if datos_original and 'data_kpi' in datos_original:
                            datos_original['data_kpi']['days_worked'] = days_worked
                            datos_original['data_kpi']['metodo_dias'] = 'desde_basic005'
                            datos_original['data_kpi']['basic005_quantity'] = basic005.quantity

            elif usar_dias_manuales and slip.manual_vacation_days:
                days_worked = slip.manual_vacation_days

                if datos_original and 'data_kpi' in datos_original:
                    datos_original['data_kpi']['days_worked'] = days_worked
                    datos_original['data_kpi']['metodo_dias'] = 'manual_forzado'

            # ══════════════════════════════════════════════════════════════════════
            # AJUSTE FINAL DE DÍAS
            # ══════════════════════════════════════════════════════════════════════

            if usar_dias_manuales and dias_vac_manuales > 0:
                # ══════════════════════════════════════════════════════════════════════
                # FÓRMULA EXACTA DE VACACIONES CON DÍAS MANUALES
                # ══════════════════════════════════════════════════════════════════════
                #
                # Fórmula legal en Colombia:
                # valor_vacaciones = (salario_base / 30) × días_trabajados / 2
                #
                # En términos del sistema:
                # total = base_mensual × days_worked / 720
                #
                # Cantidad de días de vacaciones:
                # días_vacaciones = días_trabajados / 24
                # (porque 360 días trabajados generan 15 días de vacaciones: 360/15 = 24)
                #
                # Invertir la fórmula para días manuales:
                # días_trabajados = días_vacaciones × 24
                # ══════════════════════════════════════════════════════════════════════

                # Calcular días trabajados equivalentes para generar los días de vacaciones manuales
                days_worked_para_manual = dias_vac_manuales * 24

                # Incluir festivos si está activado (usar días 360, no calendario)
                if incluir_festivos:
                    days_worked_ajustado = days_worked_para_manual + dias_festivos_futuro_360
                else:
                    days_worked_ajustado = days_worked_para_manual

                # Calcular valor esperado para validación
                valor_vacaciones_esperado = base_diaria * days_worked_ajustado / 2

                # Metadata detallada con fórmula exacta
                datos_detalle['metodo_calculo'] = 'Manual: Días vacaciones especificados'
                datos_detalle['formula_legal'] = 'días_vacaciones = (15/360) × días_trabajados'
                datos_detalle['formula_base'] = 'días_trabajados = días_vacaciones × 24'
                datos_detalle['formula_base_detallada'] = 'días_trabajados = días_vacaciones × (360/15)'
                datos_detalle['formula_aplicada'] = f"{dias_vac_manuales} × (360/15) = {dias_vac_manuales} × 24 = {days_worked_para_manual} días"
                datos_detalle['formula_valor'] = 'valor = base_diaria × days_worked ÷ 2'
                datos_detalle['formula_valor_aplicada'] = f"${base_diaria:,.0f} × {days_worked_ajustado} ÷ 2 = ${valor_vacaciones_esperado:,.0f}"
                datos_detalle['calculo_detallado'] = {
                    'dias_vacaciones_solicitados': dias_vac_manuales,
                    'factor_legal': '15/360',
                    'factor_conversion': 24,
                    'dias_trabajados_calculados': days_worked_para_manual,
                    'dias_festivos_calendario': dias_festivos_futuro if incluir_festivos else 0,
                    'dias_festivos_360': round(dias_festivos_futuro_360, 2) if incluir_festivos else 0,
                    'dias_festivos_sumados': round(dias_festivos_futuro_360, 2) if incluir_festivos else 0,
                    'dias_trabajados_finales': round(days_worked_ajustado, 2),
                    'base_diaria': base_diaria,
                    'divisor_vacaciones': 2,
                    'valor_total_esperado': valor_vacaciones_esperado,
                    'formula_completa_paso_a_paso': [
                        f"Paso 1: Convertir días vacaciones a días trabajados",
                        f"  {dias_vac_manuales} días vac × (360 ÷ 15) = {days_worked_para_manual} días trabajados",
                        f"Paso 2: {'Sumar festivos convertidos a 360' if incluir_festivos else 'Sin festivos'}",
                        f"  {days_worked_para_manual} + ({dias_festivos_futuro if incluir_festivos else 0} festivos × {360/365:.4f} = {dias_festivos_futuro_360:.2f}) = {days_worked_ajustado:.2f} días" if incluir_festivos else f"  {days_worked_para_manual} + 0 = {days_worked_ajustado:.2f} días",
                        f"Paso 3: Calcular valor",
                        f"  ${base_diaria:,.0f} × {days_worked_ajustado:.2f} ÷ 2 = ${valor_vacaciones_esperado:,.0f}"
                    ]
                }

                if incluir_festivos:
                    datos_detalle['formula_completa'] = f"{dias_vac_manuales} días vac × 24 = {days_worked_para_manual} + {dias_festivos_futuro} festivos = {days_worked_ajustado} días → ${valor_vacaciones_esperado:,.0f}"
                else:
                    datos_detalle['formula_completa'] = f"{dias_vac_manuales} días vac × 24 = {days_worked_ajustado} días → ${valor_vacaciones_esperado:,.0f}"

            elif incluir_festivos:
                # Solo incluir festivos (sin días manuales)
                days_worked_ajustado = days_worked + dias_festivos_futuro_360
            else:
                # Cálculo normal sin ajustes
                days_worked_ajustado = days_worked

            # ══════════════════════════════════════════════════════════════════════
            # CONSTANTES Y CÁLCULOS PRINCIPALES
            # ══════════════════════════════════════════════════════════════════════

            FACTOR_VACACIONES = 24

            # 1. Calcular días de vacaciones (en sistema 360, SIN festivos)
            dias_vacaciones = round(days_worked / FACTOR_VACACIONES, 2)

            # 2. Calcular valor total de vacaciones (CON festivos si aplica)
            # Fórmula Bitákora: base_diaria × días_liquidados
            # Equivalente: base_diaria × (days_worked + festivos_360) / 24
            valor_total_vacaciones = (base_diaria * days_worked_ajustado) / FACTOR_VACACIONES


            departure_date = date_to  # date_liquidacion

            # Fecha de regreso: último día hábil de las vacaciones
            # Iterar desde date_liquidacion contando días de vacaciones, excluyendo festivos
            trabaja_sabado = contract.employee_id.sabado if contract.employee_id else False
            max_dias_calcular_regreso = 60  # Límite de seguridad
            dias_vac_contados_regreso = 0
            fecha_regreso = departure_date

            for i in range(max_dias_calcular_regreso):
                if dias_vac_contados_regreso >= dias_vacaciones:
                    break

                fecha_actual = departure_date + timedelta(days=i)
                dia_semana = fecha_actual.weekday()

                # Validar si es día festivo
                es_festivo = False

                # Domingo: siempre festivo
                if dia_semana == 6:
                    es_festivo = True
                # Sábado: según si trabaja o no
                elif dia_semana == 5 and not trabaja_sabado:
                    es_festivo = True
                # Festivo del calendario
                elif self.env['lavish.holidays'].ensure_holidays(fecha_actual):
                    es_festivo = True

                # Si NO es festivo, contar como día de vacación
                if not es_festivo:
                    dias_vac_contados_regreso += 1
                    fecha_regreso = fecha_actual  # Actualizar fecha de regreso

            # ══════════════════════════════════════════════════════════════════════
            # CONSTRUIR DATOS COMBINADOS CON DETALLE COMPLETO
            # ══════════════════════════════════════════════════════════════════════

            # Información del contexto (localdict)
            detalle_linea = {
                # Información de la nómina
                'payslip_id': slip.id,
                'payslip_number': slip.number or 'Borrador',
                'payslip_name': slip.name,
                'payslip_date_from': slip.date_from.strftime('%d/%m/%Y'),
                'payslip_date_to': slip.date_to.strftime('%d/%m/%Y'),
                'payslip_date_liquidacion': slip.date_liquidacion.strftime('%d/%m/%Y') if slip.date_liquidacion else None,
                'payslip_struct': slip.struct_id.name,
                'payslip_process': slip.struct_id.process,

                # Información del empleado
                'employee_id': contract.employee_id.id,
                'employee_name': contract.employee_id.name,
                'employee_identification': contract.employee_id.identification_id,
                'employee_trabaja_sabado': contract.employee_id.sabado,
                'employee_tipo_coti': contract.employee_id.tipo_coti_id.name if contract.employee_id.tipo_coti_id else None,

                # Información del contrato
                'contract_id': contract.id,
                'contract_name': contract.name,
                'contract_date_start': contract.date_start.strftime('%d/%m/%Y'),
                'contract_date_end': contract.date_end.strftime('%d/%m/%Y') if contract.date_end else None,
                'contract_wage': contract.wage,
                'contract_modality_salary': contract.modality_salary,

                # Configuración de vacaciones
                'config_use_manual_vacation_days': slip.use_manual_vacation_days,
                'config_manual_vacation_days': slip.manual_vacation_days if slip.use_manual_vacation_days else None,
                'config_date_vacaciones': slip.date_vacaciones.strftime('%d/%m/%Y') if slip.date_vacaciones else None,
                'config_include_holidays': slip.include_holidays_in_vacation_settlement,
            }

            # Información detallada del cálculo de vacaciones
            detalle_vacaciones = {
                # Factores y constantes
                'factor_vacaciones': FACTOR_VACACIONES,
                'factor_festivos': 0.417,
                'formula_factor_vacaciones': '360 días/año ÷ 15 días vac/año = 24',

                # Días de vacaciones
                'dias_vacaciones_calculados': dias_vacaciones,
                'formula_dias_vacaciones': f'{days_worked} días trabajados ÷ {FACTOR_VACACIONES} = {dias_vacaciones} días',

                # Festivos
                'festivos_calendario': dias_festivos_futuro if incluir_festivos else 0,
                'festivos_360': festivos_360_para_reporte if incluir_festivos else 0,
                'formula_festivos': f'{dias_festivos_futuro} festivos ÷ 0.417 = {festivos_360_para_reporte:.2f} días 360' if incluir_festivos else 'Sin festivos',

                # Días ajustados
                'dias_trabajados_base': days_worked,
                'dias_ajustados_con_festivos': days_worked_ajustado,
                'formula_dias_ajustados': f'{days_worked} + {festivos_360_para_reporte:.2f} = {days_worked_ajustado:.2f}' if incluir_festivos else f'{days_worked}',

                'base_diaria_usada': base_diaria,
                'valor_total_vacaciones': valor_total_vacaciones,
                'formula_valor': f'({base_diaria:.2f} × {days_worked_ajustado:.2f}) ÷ {FACTOR_VACACIONES} = {valor_total_vacaciones:.2f}',
                'formula_valor_bitakora': f'base_diaria × días_liquidados = base_diaria × ((días_trabajados + festivos_360) ÷ 24)',

                # Fechas
                'fecha_salida': departure_date.strftime('%d/%m/%Y'),
                'fecha_regreso': fecha_regreso.strftime('%d/%m/%Y'),

                'calculo_paso_a_paso': [
                    f'PASO 1: Calcular días de vacaciones (SIN festivos)',
                    f'  Fórmula: días_trabajados ÷ 24',
                    f'  Cálculo: {days_worked} ÷ {FACTOR_VACACIONES} = {dias_vacaciones} días',
                    f'',
                    f'PASO 2: Convertir festivos a sistema 360 (si aplica)',
                    f'  Festivos calendario: {dias_festivos_futuro if incluir_festivos else 0}',
                    f'  Fórmula conversión: festivos ÷ 0.417',
                    f'  Festivos 360: {festivos_360_para_reporte:.2f} días' if incluir_festivos else '  Sin festivos incluidos',
                    f'',
                    f'PASO 3: Calcular días ajustados para valor',
                    f'  Fórmula: días_trabajados + festivos_360',
                    f'  Cálculo: {days_worked} + {festivos_360_para_reporte:.2f} = {days_worked_ajustado:.2f}' if incluir_festivos else f'  Cálculo: {days_worked} (sin festivos)',
                    f'',
                    f'PASO 4: Calcular valor total',
                    f'  Fórmula Bitákora: base_diaria × días_liquidados',
                    f'  Equivalente: (base_diaria × días_ajustados) ÷ 24',
                    f'  Cálculo: ({base_diaria:.2f} × {days_worked_ajustado:.2f}) ÷ {FACTOR_VACACIONES}',
                    f'  Resultado: ${valor_total_vacaciones:,.2f}',
                    f'',
                    f'PASO 5: Calcular fechas',
                    f'  Fecha salida (liquidación): {departure_date.strftime("%d/%m/%Y")}',
                    f'  Fecha regreso (último día hábil): {fecha_regreso.strftime("%d/%m/%Y")}',
                    f'  Días de vacaciones: {dias_vacaciones} días',
                ],

                # Configuración
                'usa_dias_manuales': usar_dias_manuales,
                'incluye_festivos': incluir_festivos,
                'trabaja_sabado': trabaja_sabado,
            }

            # Combinar todos los datos
            datos_combinados = {
                # Datos originales del cálculo base
                **(datos_original or {}),
                # Datos de configuración del período
                **datos_detalle,
                # Información del contexto (nómina, empleado, contrato)
                **detalle_linea,
                # Detalle completo del cálculo de vacaciones
                **detalle_vacaciones,
                # Compatibilidad
                'days_worked_original': days_worked,
                'days_worked_ajustado': days_worked_ajustado,
            }

            # ══════════════════════════════════════════════════════════════════════

            # Crear/actualizar historial usando helper
            self._create_update_history(
                slip, contract,
                'hr.vacation',
                {
                    'units_of_money': dias_vacaciones,
                    'money_value': valor_total_vacaciones,
                    'total': valor_total_vacaciones,
                    'departure_date': departure_date,  # Fecha de salida de la empresa
                    'return_date': fecha_regreso,  # Último día hábil de vacaciones
                    'type': 'settlement',
                    'description': descripcion,
                },
                date_from, date_to,
                search_fields={
                    'initial_accrual_date': date_from,
                    'final_accrual_date': date_to,
                }
            )

            return base_diaria, days_worked_ajustado, rate, descripcion, "", datos_combinados

        return resultado


