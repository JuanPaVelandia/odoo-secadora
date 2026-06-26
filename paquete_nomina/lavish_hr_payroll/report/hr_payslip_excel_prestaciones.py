# -*- coding: utf-8 -*-
"""
Módulo de exportación Excel para Prestaciones Sociales
=======================================================

Extensión de hr.payslip para generar reportes Excel de prestaciones
sociales (cesantías, intereses, primas, vacaciones).
"""

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta, date
import json
import base64
import io
import math
import xlsxwriter


class HrPayslipExcelPrestaciones(models.Model):
    _inherit = 'hr.payslip'

    # ══════════════════════════════════════════════════════════════════════════
    # NORMALIZADOR DE DATOS PARA PRESTACIONES
    # ══════════════════════════════════════════════════════════════════════════

    def _normalize_prestaciones_data(self, raw_data):
        """
        Normaliza los datos de prestaciones de la nueva estructura al formato esperado por el Excel.

        Nueva estructura (datos de _compute_social_benefits):
        - data_kpi: {base_diaria, base_mensual, days_worked, days_no_pay, salary_base, salary_variable, subsidy, ...}
        - trazabilidad: {reglas_usadas, valores_anteriores, diferencia, porcentaje_cambio}
        - ids_by_type: {basic_current, basic_accumulated, variable_current, variable_accumulated}
        - fecha_inicio, fecha_fin, monto_total

        Formato esperado por Excel:
        - meta_info: {plain_days, susp, wage, auxtransporte, total_variable, amount_base, valor_primas, fecha_inicio, fecha_fin}
        - provisiones: {valor_anterior, valor_actual, diferencia}
        - novedades_promedio: {entradas: [...], totales: {...}}
        """
        if isinstance(raw_data, list):
            data = raw_data[0] if raw_data else {}
        else:
            data = raw_data

        # Si ya tiene el formato antiguo, devolverlo tal cual
        if 'meta_info' in data and 'plain_days' in data.get('meta_info', {}):
            return data

        # Extraer datos de la nueva estructura
        data_kpi = data.get('data_kpi', {})
        trazabilidad = data.get('trazabilidad', {})
        ids_by_type = data.get('ids_by_type', {})

        # Calcular valores
        days_worked = data_kpi.get('days_worked', 0)
        days_no_pay = data_kpi.get('days_no_pay', 0)
        salary_base = data_kpi.get('salary_base', 0)
        salary_variable = data_kpi.get('salary_variable', 0)
        subsidy = data_kpi.get('subsidy', 0)
        base_mensual = data_kpi.get('base_mensual', 0)
        base_diaria = data_kpi.get('base_diaria', 0)

        # Calcular valor final
        monto_total = data.get('monto_total', 0)
        if monto_total == 0 and base_diaria > 0:
            monto_total = base_diaria * days_worked

        # Construir meta_info
        fecha_inicio = data.get('fecha_inicio', '')
        fecha_fin = data.get('fecha_fin', '')
        if fecha_inicio and hasattr(fecha_inicio, 'strftime'):
            fecha_inicio = fecha_inicio.strftime('%Y-%m-%d')
        if fecha_fin and hasattr(fecha_fin, 'strftime'):
            fecha_fin = fecha_fin.strftime('%Y-%m-%d')

        meta_info = {
            'plain_days': days_worked + days_no_pay,  # Dias totales antes de descontar
            'susp': days_no_pay,  # Dias de suspension/no pagados
            'wage': salary_base,  # Salario base
            'auxtransporte': subsidy,  # Auxilio de transporte
            'total_variable': salary_variable,  # Total devengos variables
            'amount_base': base_mensual,  # Base de calculo mensual
            'valor_primas': monto_total,  # Valor final calculado
            'fecha_inicio': fecha_inicio,
            'fecha_fin': fecha_fin,
            'contract_modality': 'fijo',  # Por defecto
            'base_diaria': base_diaria,
        }

        # Datos especificos para intereses de cesantias
        if 'cesantias_proporcionales' in data_kpi:
            meta_info['base_cesantias'] = data_kpi.get('cesantias_proporcionales', 0) / 0.12 if data_kpi.get('cesantias_proporcionales', 0) > 0 else base_mensual
            meta_info['tasa_interes'] = data_kpi.get('tasa_interes', 12.0)

        # Construir provisiones desde valores_anteriores
        valores_anteriores = trazabilidad.get('valores_anteriores', {})
        diferencia = trazabilidad.get('diferencia', 0)

        provisiones = {
            'valor_anterior': valores_anteriores.get('valor_anterior', 0),
            'valor_actual': monto_total,
            'diferencia': diferencia if diferencia != 0 else monto_total - valores_anteriores.get('valor_anterior', 0),
        }

        # Construir novedades_promedio desde reglas_usadas
        reglas_usadas = trazabilidad.get('reglas_usadas', [])
        entradas = []
        payslip_total = 0
        accumulated_total = 0

        for regla in reglas_usadas:
            entrada = {
                'fecha': regla.get('fecha_nomina', ''),
                'nombre_regla': regla.get('nombre', ''),
                'regla_salarial': regla.get('codigo', ''),
                'origen': 'Nomina actual' if 'current' in regla.get('tipo', '') else 'Acumulado',
                'monto': regla.get('total', 0),
            }
            if hasattr(entrada['fecha'], 'strftime'):
                entrada['fecha'] = entrada['fecha'].strftime('%Y-%m-%d')
            entradas.append(entrada)

            if 'current' in regla.get('tipo', ''):
                payslip_total += regla.get('total', 0)
            else:
                accumulated_total += regla.get('total', 0)

        novedades_promedio = {
            'entradas': entradas,
            'totales': {
                'payslip_total': payslip_total,
                'accumulated_total': accumulated_total,
                'grand_total': payslip_total + accumulated_total,
            }
        }

        # Construir estructura normalizada
        normalized = {
            'meta_info': meta_info,
            'provisiones': provisiones,
            'novedades_promedio': novedades_promedio,
            'variaciones_salario': [],
            'licencias_no_remuneradas': [],
            # Mantener datos originales para referencia
            '_raw_data_kpi': data_kpi,
            '_raw_trazabilidad': trazabilidad,
        }

        return normalized

    # ══════════════════════════════════════════════════════════════════════════
    # ACCION DE GENERAR EXCEL PRESTACIONES
    # ══════════════════════════════════════════════════════════════════════════

    def generate_prestaciones_excel(self):
        """
        Genera un reporte Excel para las prestaciones sociales.
        """
        for payslip in self:
            prestaciones_lines = payslip.line_ids.filtered(
                lambda line: line.computation and line.salary_rule_id.code not in ('IBD', 'IBC_R', 'RT_MET_01')
            )

            if not prestaciones_lines:
                raise UserError('No hay datos de prestaciones sociales disponibles para generar el reporte Excel.')

            valid_lines = []
            for line in prestaciones_lines:
                try:
                    json.loads(line.computation)
                    valid_lines.append(line)
                except json.JSONDecodeError:
                    continue

            if not valid_lines:
                raise UserError('No se encontraron líneas con datos JSON válidos para generar el reporte.')

            file_data = self._create_prestaciones_excel(valid_lines)

            payslip.write({
                'excel_lines': file_data,
                'excel_lines_filename':  f'prestaciones_{payslip.number}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
            })
            action = {
                'name': 'Export prestaciones sociales',
                'type': 'ir.actions.act_url',
                'url': "web/content/?model=hr.payslip&id=" + str(
                    self.id) + "&filename_field=excel_lines_filename&field=excel_lines&download=true&filename=" + self.excel_lines_filename,
                'target': 'self',
            }

            return action

    # ══════════════════════════════════════════════════════════════════════════
    # GENERADOR EXCEL PRESTACIONES
    # ══════════════════════════════════════════════════════════════════════════

    def _create_prestaciones_excel(self, prestaciones_lines):
        """
        Crea el archivo Excel con los datos de prestaciones sociales.

        Args:
            prestaciones_lines: Líneas de prestaciones con datos JSON

        Returns:
            Excel codificado en base64
        """
        output = io.BytesIO()

        workbook = xlsxwriter.Workbook(output, {'in_memory': True})

        # Formatos para el Excel
        header_format = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'fg_color': '#1e88e5',
            'color': 'white',
            'border': 1
        })

        subheader_format = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'fg_color': '#64b5f6',
            'color': 'white',
            'border': 1
        })

        company_header_format = workbook.add_format({
            'bold': True,
            'align': 'left',
            'valign': 'vcenter',
            'fg_color': '#f0f0f0',
            'color': '#333333',
            'border': 1,
            'font_size': 12
        })

        date_format = workbook.add_format({
            'num_format': 'dd/mm/yyyy',
            'align': 'center',
            'border': 1
        })

        currency_format = workbook.add_format({
            'num_format': '#,##0.00',
            'align': 'right',
            'border': 1
        })

        formula_format = workbook.add_format({
            'num_format': '#,##0.00',
            'align': 'right',
            'border': 1,
            'italic': True,
            'fg_color': '#e3f2fd'
        })

        formula_text_format = workbook.add_format({
            'align': 'right',
            'border': 1,
            'italic': True,
            'fg_color': '#e3f2fd'
        })

        text_format = workbook.add_format({
            'align': 'left',
            'border': 1
        })

        cell_label_format = workbook.add_format({
            'align': 'left',
            'border': 1,
            'bold': True
        })

        step_title_format = workbook.add_format({
            'align': 'left',
            'border': 1,
            'bold': True,
            'fg_color': '#e8eaf6'
        })

        calculation_format = workbook.add_format({
            'align': 'left',
            'border': 1,
            'font_size': 11,
            'font_color': '#1565c0'
        })

        porcent_format = workbook.add_format({
            'num_format': '0.00%',
            'align': 'right',
            'border': 1
        })

        # Obtener datos de la empresa
        company = self.env.company
        company_name = company.name
        company_vat = company.vat or 'N/A'
        payslip = prestaciones_lines[0].slip_id if prestaciones_lines else None
        payslip_number = payslip.number if payslip else 'N/A'
        payslip_date = payslip.date_to if payslip else datetime.now()
        employee_name = payslip.employee_id.name if payslip and payslip.employee_id else 'N/A'

        # Procesar cada linea de prestacion
        for line in prestaciones_lines:
            # Cargar los datos JSON
            raw_data = json.loads(line.computation)

            # Normalizar datos al formato esperado por el Excel
            computation_data = self._normalize_prestaciones_data(raw_data)

            # Nombre de la hoja (limitar longitud para evitar errores)
            sheet_name = line.salary_rule_id.code[:10] if line.salary_rule_id.code else f'Prestacion_{line.id}'

            # Crear hoja para cada tipo de prestación
            worksheet = workbook.add_worksheet(sheet_name)

            # Configurar ancho de columnas
            worksheet.set_column('A:A', 20)
            worksheet.set_column('B:B', 40)
            worksheet.set_column('C:C', 20)
            worksheet.set_column('D:D', 20)
            worksheet.set_column('E:E', 20)

            # Encabezado con datos de la empresa
            worksheet.merge_range('A1:E1', 'REPORTE DE PRESTACIONES SOCIALES', header_format)
            worksheet.merge_range('A2:C2', f'EMPRESA: {company_name}', company_header_format)
            worksheet.merge_range('D2:E2', f'NIT: {company_vat}', company_header_format)
            worksheet.merge_range('A3:C3', f'COMPROBANTE: {payslip_number}', company_header_format)
            worksheet.merge_range('D3:E3', f'FECHA: {payslip_date.strftime("%d/%m/%Y")}', company_header_format)
            worksheet.merge_range('A4:E4', f'EMPLEADO: {employee_name}', company_header_format)

            # Datos de la prestación
            worksheet.write('A6', 'Prestación:', cell_label_format)
            worksheet.write('B6', line.name, text_format)
            worksheet.write('C6', 'Código:', cell_label_format)
            worksheet.write('D6', line.salary_rule_id.code if line.salary_rule_id else 'N/A', text_format)

            # Extraer los datos principales
            meta_info = computation_data.get('meta_info', {})
            plain_days = meta_info.get('plain_days', 0)
            susp = meta_info.get('susp', 0)
            wage = meta_info.get('wage', 0)
            auxtransporte = meta_info.get('auxtransporte', 0)
            total_variable = meta_info.get('total_variable', 0)
            amount_base = meta_info.get('amount_base', 0)
            valor_primas = meta_info.get('valor_primas', 0)

            provisiones = computation_data.get('provisiones', {})
            provision_anterior = provisiones.get('valor_anterior', 0)
            provision_actual = provisiones.get('valor_actual', 0)
            diferencia_provision = provisiones.get('diferencia', 0)

            code = line.salary_rule_id.code
            es_cesantias = code in ("CESANTIAS", "PRV_CES", "CES_YEAR")
            es_intereses = code in ("INTCESANTIAS", "PRV_ICES", "INTCES_YEAR")
            es_vacaciones = code in ("VACATIONS_MONEY", "PRV_VAC", "VACCONTRATO")
            es_prima = code in ("prima", "PRV_PRIM", "primaextralegal")
            es_provision = code.startswith("PRV_")

            contract_modality = meta_info.get('contract_modality', 'fijo')  # 'fijo' por defecto
            es_salario_variable = contract_modality == 'variable'

            fecha_inicio = ''
            fecha_fin = ''

            if 'fecha_inicio' in meta_info and meta_info['fecha_inicio']:
                try:
                    fecha_inicio = datetime.strptime(meta_info['fecha_inicio'], '%Y-%m-%d').date()
                except ValueError:
                    fecha_inicio = ''

            if 'fecha_fin' in meta_info and meta_info['fecha_fin']:
                try:
                    fecha_fin = datetime.strptime(meta_info['fecha_fin'], '%Y-%m-%d').date()
                except ValueError:
                    fecha_fin = ''

            # ----------------------------------
            # 1. INFORMACIÓN GENERAL
            # ----------------------------------

            # Determinar filas y referencias exactas
            info_header_row = 8
            fecha_inicio_row = 9
            num_comprobante_row = 10
            dias_totales_row = 11
            dias_susp_row = 12
            salario_row = 13
            auxilio_row = 13  # Misma fila, columna diferente

            dias_totales_cell = f'B{dias_totales_row}'
            dias_suspension_cell = f'B{dias_susp_row}'
            dias_liquidados_cell = f'D{dias_totales_row}'
            porcentaje_cell = f'D{dias_susp_row}'
            salario_cell = f'B{salario_row}'
            auxilio_cell = f'D{auxilio_row}'

            worksheet.merge_range(f'A{info_header_row}:E{info_header_row}', 'INFORMACIÓN GENERAL', header_format)

            worksheet.write(f'A{fecha_inicio_row}', 'Fecha Inicio:', cell_label_format)
            worksheet.write(f'B{fecha_inicio_row}', fecha_inicio, date_format if fecha_inicio else text_format)
            worksheet.write(f'C{fecha_inicio_row}', 'Fecha Fin:', cell_label_format)
            worksheet.write(f'D{fecha_inicio_row}', fecha_fin, date_format if fecha_fin else text_format)

            worksheet.write(f'A{num_comprobante_row}', 'Número Comprobante:', cell_label_format)
            worksheet.write(f'B{num_comprobante_row}', payslip_number, text_format)

            worksheet.write(f'A{dias_totales_row}', 'Días Totales:', cell_label_format)
            worksheet.write(f'B{dias_totales_row}', plain_days, text_format)
            worksheet.write(f'C{dias_totales_row}', 'Días Liquidados:', cell_label_format)
            worksheet.write_formula(f'D{dias_totales_row}', f'={dias_totales_cell}-{dias_suspension_cell}', formula_format, plain_days - susp)

            worksheet.write(f'A{dias_susp_row}', 'Días Suspensión:', cell_label_format)
            worksheet.write(f'B{dias_susp_row}', susp, text_format)
            worksheet.write(f'C{dias_susp_row}', 'Porcentaje Liquidado:', cell_label_format)

            if es_intereses:
                # Caso especial para intereses de cesantías
                porcentaje = (plain_days - susp) / 360 if plain_days > 0 else 0
                worksheet.write_formula(
                    f'D{dias_susp_row}',
                    f'={dias_liquidados_cell}/360',
                    porcent_format,
                    porcentaje
                )
            else:
                # Para otras prestaciones, mantener la fórmula original
                porcentaje = min((plain_days - susp) / 360, 1)
                worksheet.write_formula(f'D{dias_susp_row}', f'=MIN({dias_liquidados_cell}/360, 1)', porcent_format, porcentaje)

            worksheet.write(f'A{salario_row}', 'Salario Base:', cell_label_format)
            worksheet.write(f'B{salario_row}', wage, currency_format)
            worksheet.write(f'C{salario_row}', 'Auxilio Transporte:', cell_label_format)
            worksheet.write(f'D{salario_row}', auxtransporte, currency_format)

            # ----------------------------------
            # 2. DETALLE DE CÁLCULOS
            # ----------------------------------
            calculo_header_row = 17
            promedio_dia_row = 18
            factor_dia_row = 19

            worksheet.merge_range(f'A{calculo_header_row}:E{calculo_header_row}', 'DETALLE DE CÁLCULOS', header_format)

            worksheet.write(f'A{promedio_dia_row}', 'Promedio diario:', cell_label_format)
            diario_salario = wage / 30
            worksheet.write_formula(f'B{promedio_dia_row}', f'={salario_cell}/30', formula_format, diario_salario)
            worksheet.write(f'C{promedio_dia_row}', 'Promedio día variable:', cell_label_format)

            # Promedio diario variable
            if plain_days > 0:
                if plain_days <= 30 and es_salario_variable:
                    diario_variable = total_variable / plain_days
                    worksheet.write(f'D{promedio_dia_row}', diario_variable, currency_format)
                else:
                    # Cálculo normal
                    diario_variable = total_variable / plain_days
                    worksheet.write_formula(f'D{promedio_dia_row}', f'=E31/{dias_totales_cell}', formula_format, diario_variable)
            else:
                worksheet.write(f'D{promedio_dia_row}', 0, currency_format)

            worksheet.write(f'A{factor_dia_row}', 'Factor día (360):', cell_label_format)
            worksheet.write_formula(f'B{factor_dia_row}', '=1/360', formula_format, 1/360)
            worksheet.write(f'C{factor_dia_row}', 'Total días liquidados:', cell_label_format)
            worksheet.write(f'D{factor_dia_row}', plain_days - susp, text_format)

            # ----------------------------------
            # 4. NOVEDADES EN ORDEN CRONOLÓGICO
            # ----------------------------------
            novedades_header_row = 21
            novedades_columns_row = 22
            first_entry_row = 23

            worksheet.merge_range(f'A{novedades_header_row}:E{novedades_header_row}', 'NOVEDADES ORDENADAS POR FECHA', header_format)

            worksheet.write(f'A{novedades_columns_row}', 'Fecha', subheader_format)
            worksheet.write(f'B{novedades_columns_row}', 'Descripción', subheader_format)
            worksheet.write(f'C{novedades_columns_row}', 'Código', subheader_format)
            worksheet.write(f'D{novedades_columns_row}', 'Origen', subheader_format)
            worksheet.write(f'E{novedades_columns_row}', 'Monto', subheader_format)

            all_entries = []

            entradas_nomina = computation_data.get('novedades_promedio', {}).get('entradas', [])
            filtered_entries = [
                entry for entry in entradas_nomina
                if entry.get('regla_salarial', '') not in ['VARIACION', 'LICENCIA']
            ]
            all_entries.extend(filtered_entries)

            # Función para convertir fecha a objeto datetime para ordenamiento
            def get_fecha_for_sorting(entry):
                fecha = entry.get('fecha', '1900-01-01')
                if isinstance(fecha, str):
                    try:
                        return datetime.strptime(fecha, '%Y-%m-%d')
                    except ValueError:
                        return datetime(1900, 1, 1)
                return fecha or datetime(1900, 1, 1)

            # Ordenar por fecha
            sorted_entries = sorted(all_entries, key=get_fecha_for_sorting)

            # Escribir entradas ordenadas
            current_row = first_entry_row
            for entry in sorted_entries:
                try:
                    fecha = entry.get('fecha', '')
                    if isinstance(fecha, str) and fecha:
                        try:
                            fecha = datetime.strptime(fecha, '%Y-%m-%d').date()
                        except ValueError:
                            fecha = ''

                    worksheet.write(f'A{current_row}', fecha, date_format if fecha else text_format)
                    worksheet.write(f'B{current_row}', entry.get('nombre_regla', ''), text_format)
                    worksheet.write(f'C{current_row}', entry.get('regla_salarial', ''), text_format)
                    worksheet.write(f'D{current_row}', entry.get('origen', ''), text_format)
                    worksheet.write(f'E{current_row}', entry.get('monto', 0), currency_format)
                    current_row += 1
                except Exception as e:
                    worksheet.write(f'A{current_row}', "Error en entrada", text_format)
                    worksheet.write(f'B{current_row}', str(e), text_format)
                    current_row += 1

            last_entry_row = current_row - 1

            if last_entry_row >= first_entry_row:
                worksheet.write(f'D{current_row}', 'TOTAL NOVEDADES:', cell_label_format)
                total_novedades_cell = f'E{current_row}'
                worksheet.write_formula(total_novedades_cell, f'=SUM(E{first_entry_row}:E{last_entry_row})', formula_format, total_variable)
                workbook.define_name('TOTAL_NOVEDADES', f'={sheet_name}!{total_novedades_cell}')
                current_row += 1
            else:
                total_novedades_cell = f'E{current_row}'
                worksheet.write(f'D{current_row}', 'TOTAL NOVEDADES:', cell_label_format)
                worksheet.write(total_novedades_cell, total_variable, currency_format)
                current_row += 1

            promedio_variable_row = current_row
            worksheet.write(f'A{current_row}', 'Promedio Variable:', cell_label_format)
            if plain_days > 0:
                if plain_days <= 30:
                    promedio_variable = total_variable
                    worksheet.write(
                        f'B{current_row}',
                        promedio_variable,
                        currency_format
                    )
                else:
                    promedio_variable = total_variable / plain_days * 30
                    worksheet.write_formula(
                        f'B{current_row}',
                        f'=({total_novedades_cell}/{plain_days})*30',
                        formula_format,
                        promedio_variable
                    )
            else:
                worksheet.write(f'B{current_row}', 0, currency_format)
            promedio_variable_cell = f'B{current_row}'
            current_row += 1

            # Base de cálculo con fórmula
            base_calculo_row = current_row
            worksheet.write(f'A{current_row}', 'Base de Cálculo:', cell_label_format)
            if plain_days > 0:
                worksheet.write_formula(f'B{current_row}', f'={salario_cell}+{auxilio_cell}+{promedio_variable_cell}', formula_format, amount_base)
            else:
                worksheet.write(f'B{current_row}', amount_base, currency_format)
            base_calculo_cell = f'B{current_row}'
            current_row += 1

            # ----------------------------------
            # 3. PROVISIONES
            # ----------------------------------
            provisiones_header_row = current_row + 1
            provisiones_anterior_row = provisiones_header_row + 1
            provisiones_actual_row = provisiones_anterior_row + 1
            provisiones_diferencia_row = provisiones_actual_row + 1
            provisiones_estado_row = provisiones_diferencia_row + 1
            provisiones_contabilizar_row = provisiones_estado_row + 1

            worksheet.merge_range(f'A{provisiones_header_row}:E{provisiones_header_row}', 'PROVISIONES', header_format)

            provision_anterior_cell = f'B{provisiones_anterior_row}'
            worksheet.write(f'A{provisiones_anterior_row}', 'Provisión Anterior:', cell_label_format)
            worksheet.write(provision_anterior_cell, abs(provision_anterior), currency_format)

            provision_actual_cell = f'B{provisiones_actual_row}'
            worksheet.write(f'A{provisiones_actual_row}', 'Provisión Actual:', cell_label_format)

            if es_intereses:
                base_cesantias = meta_info.get('base_cesantias', amount_base)
                base_cesantias_cell = f'B{base_calculo_row + 1}'
                worksheet.write(f'A{base_calculo_row + 1}', 'Base Cesantías:', cell_label_format)
                worksheet.write(base_cesantias_cell, base_cesantias, currency_format)

                worksheet.write_formula(
                    provision_actual_cell,
                    f'=({base_cesantias_cell}/ {360})*{dias_liquidados_cell} *(12% * {dias_liquidados_cell})/360',
                    formula_format,
                    valor_primas
                )
            else:
                # Caso estándar: otras prestaciones
                valor_base_diario = amount_base / 360
                worksheet.write_formula(provision_actual_cell, f'={base_calculo_cell}/360*{dias_liquidados_cell}', formula_format, valor_primas)

            diferencia_cell = f'B{provisiones_diferencia_row}'
            worksheet.write(f'A{provisiones_diferencia_row}', 'Diferencia:', cell_label_format)
            worksheet.write_formula(diferencia_cell, f'={provision_actual_cell}-{provision_anterior_cell}', formula_format, diferencia_provision)

            worksheet.write(f'A{provisiones_estado_row}', 'Estado:', cell_label_format)
            worksheet.write_formula(f'B{provisiones_estado_row}', f'=IF({diferencia_cell}>0,"Por provisionar","Ajustar provisión")', formula_text_format,
                                    "Por provisionar" if diferencia_provision > 0 else "Ajustar provisión")

            worksheet.write(f'A{provisiones_contabilizar_row}', 'Valor a Contabilizar:', cell_label_format)
            worksheet.write_formula(f'B{provisiones_contabilizar_row}', f'=ABS({diferencia_cell})', formula_format, abs(diferencia_provision))

            # ----------------------------------
            # 5. RESUMEN DE TOTALES
            # ----------------------------------
            current_row = provisiones_contabilizar_row + 2
            totales_header_row = current_row
            totales_columns_row = totales_header_row + 1
            total_nomina_row = totales_columns_row + 1
            total_acumulado_row = total_nomina_row + 1
            total_novedades_row = total_acumulado_row + 1
            valor_base_diario_row = total_novedades_row + 1
            valor_final_row = valor_base_diario_row + 1
            valor_redondeado_row = valor_final_row + 1
            numero_nomina_row = valor_redondeado_row + 1

            worksheet.merge_range(f'A{totales_header_row}:E{totales_header_row}', 'RESUMEN DE TOTALES', header_format)

            worksheet.write(f'A{totales_columns_row}', 'Concepto', subheader_format)
            worksheet.write(f'B{totales_columns_row}', 'Valor', subheader_format)
            worksheet.write(f'C{totales_columns_row}', 'Fórmula/Origen', subheader_format)

            totales = computation_data.get('novedades_promedio', {}).get('totales', {})
            payslip_total_cell = f'B{total_nomina_row}'
            worksheet.write(f'A{total_nomina_row}', 'Total Nómina:', cell_label_format)
            total_nomina = totales.get('payslip_total', 0)
            worksheet.write(payslip_total_cell, total_nomina, currency_format)
            worksheet.write(f'C{total_nomina_row}', 'Suma de entradas de nómina', formula_text_format)

            acumulado_total_cell = f'B{total_acumulado_row}'
            worksheet.write(f'A{total_acumulado_row}', 'Total Acumulado:', cell_label_format)
            total_acumulado = totales.get('accumulated_total', 0)
            worksheet.write(acumulado_total_cell, total_acumulado, currency_format)
            worksheet.write(f'C{total_acumulado_row}', 'Suma de acumulados previos', formula_text_format)

            total_novedades_valor_cell = f'B{total_novedades_row}'
            worksheet.write(f'A{total_novedades_row}', 'Total Novedades:', cell_label_format)
            if 'total_novedades_cell' in locals():
                worksheet.write_formula(total_novedades_valor_cell, f'={total_novedades_cell}', formula_format, total_variable)
            else:
                worksheet.write(total_novedades_valor_cell, total_variable, currency_format)
            # En la columna de fórmula, mostrar el valor del total de nómina
            worksheet.write_formula(f'C{total_novedades_row}', f'={payslip_total_cell}', formula_format, total_nomina)

            valor_base_diario_cell = f'B{valor_base_diario_row}'
            worksheet.write(f'A{valor_base_diario_row}', 'Valor Base Diario:', cell_label_format)
            valor_base_diario = amount_base / 360
            worksheet.write_formula(valor_base_diario_cell, f'={base_calculo_cell}/360', formula_format, valor_base_diario)
            worksheet.write(f'C{valor_base_diario_row}', 'Base Cálculo / 360', formula_text_format)

            # Valor final con la fórmula corregida para intereses
            valor_final_cell = f'B{valor_final_row}'
            worksheet.write(f'A{valor_final_row}', 'Valor Final:', cell_label_format)
            if es_intereses:
                # Nueva fórmula para intereses: Base * (12% / (días/360) / 100)
                base_cesantias = meta_info.get('base_cesantias', amount_base)

                # Verificar si ya existe la celda de base_cesantias
                if 'base_cesantias_cell' not in locals():
                    base_cesantias_cell = f'B{base_calculo_row + 1}'

                # Aplicar la nueva fórmula de intereses
                worksheet.write_formula(
                    valor_final_cell,
                    f'=({base_cesantias_cell} / {360})* {dias_liquidados_cell} *((0.12*{dias_liquidados_cell})/360)',
                    formula_format,
                    valor_primas
                )
                worksheet.write(f'C{valor_final_row}', 'Base Cesantías * (12% / (Días/360) / 100)', formula_text_format)
            else:
                worksheet.write_formula(valor_final_cell, f'={valor_base_diario_cell}*{dias_liquidados_cell}', formula_format, valor_primas)
                worksheet.write(f'C{valor_final_row}', 'Valor Base Diario * Días Efectivos', formula_text_format)

            # Redondeo
            worksheet.write(f'A{valor_redondeado_row}', 'Valor Redondeado:', cell_label_format)
            worksheet.write_formula(f'B{valor_redondeado_row}', f'=ROUNDUP({valor_final_cell},0)', formula_format, math.ceil(valor_primas))
            worksheet.write(f'C{valor_redondeado_row}', 'Redondeo al entero superior', formula_text_format)

            worksheet.write(f'A{numero_nomina_row}', 'Número de Nómina:', cell_label_format)
            worksheet.write(f'B{numero_nomina_row}', payslip_number, text_format)

            # ----------------------------------
            # 6. TABLA PARA VARIACIONES DE SALARIO Y AUSENCIAS
            # ----------------------------------
            variaciones_header_row = numero_nomina_row + 2
            worksheet.merge_range(f'A{variaciones_header_row}:E{variaciones_header_row}', 'VARIACIONES DE SALARIO Y AUSENCIAS', header_format)

            variaciones_columns_row = variaciones_header_row + 1
            worksheet.write(f'A{variaciones_columns_row}', 'Fecha', subheader_format)
            worksheet.write(f'B{variaciones_columns_row}', 'Tipo', subheader_format)
            worksheet.write(f'C{variaciones_columns_row}', 'Valor Anterior', subheader_format)
            worksheet.write(f'D{variaciones_columns_row}', 'Valor Nuevo', subheader_format)
            worksheet.write(f'E{variaciones_columns_row}', 'Diferencia', subheader_format)

            # Escribir variaciones de salario
            current_row = variaciones_columns_row + 1
            variaciones = computation_data.get('variaciones_salario', [])

            # Si no hay explícitamente variaciones en el formato deseado, buscar en novedades
            if not variaciones:
                for entry in entradas_nomina:
                    if entry.get('regla_salarial') == 'VARIACION':
                        variaciones.append({
                            'fecha': entry.get('fecha', ''),
                            'salario_anterior': 0,  # No tenemos este dato en las novedades
                            'salario': entry.get('monto', 0)
                        })

            for variacion in variaciones:
                try:
                    fecha = variacion.get('fecha', '')
                    if isinstance(fecha, str) and fecha:
                        try:
                            fecha = datetime.strptime(fecha, '%Y-%m-%d').date()
                        except ValueError:
                            fecha = ''

                    salario_anterior = variacion.get('salario_anterior', 0)
                    salario_nuevo = variacion.get('salario', 0)

                    worksheet.write(f'A{current_row}', fecha, date_format if fecha else text_format)
                    worksheet.write(f'B{current_row}', 'Variación Salarial', text_format)
                    worksheet.write(f'C{current_row}', salario_anterior, currency_format)
                    worksheet.write(f'D{current_row}', salario_nuevo, currency_format)
                    worksheet.write_formula(f'E{current_row}', f'=D{current_row}-C{current_row}', formula_format, salario_nuevo - salario_anterior)
                    current_row += 1
                except Exception as e:
                    worksheet.write(f'A{current_row}', "Error en variación", text_format)
                    worksheet.write(f'B{current_row}', str(e), text_format)
                    current_row += 1

            # Escribir ausencias/licencias
            licencias = computation_data.get('licencias_no_remuneradas', [])
            for licencia in licencias:
                try:
                    fecha_inicio = licencia.get('fecha_inicio', '')
                    if isinstance(fecha_inicio, str) and fecha_inicio:
                        try:
                            fecha_inicio = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
                        except ValueError:
                            fecha_inicio = ''

                    tipo_licencia = licencia.get('tipo_licencia', 'Sin tipo')
                    dias = licencia.get('dias', 0)

                    worksheet.write(f'A{current_row}', fecha_inicio, date_format if fecha_inicio else text_format)
                    worksheet.write(f'B{current_row}', f'Licencia: {tipo_licencia}', text_format)
                    worksheet.write(f'C{current_row}', 'N/A', text_format)
                    worksheet.write(f'D{current_row}', f'{dias} días', text_format)
                    worksheet.write(f'E{current_row}', 0, currency_format)
                    current_row += 1
                except Exception as e:
                    worksheet.write(f'A{current_row}', "Error en licencia", text_format)
                    worksheet.write(f'B{current_row}', str(e), text_format)
                    current_row += 1

        # Crear una hoja de resumen si no hay ninguna hoja
        if not workbook.worksheets_objs:
            resumen_sheet = workbook.add_worksheet('Resumen')
            resumen_sheet.write('A1', 'No se encontraron datos para generar el reporte', header_format)

        # Cerrar el libro y obtener los datos
        workbook.close()
        output.seek(0)
        return base64.b64encode(output.read()).decode('utf-8')
