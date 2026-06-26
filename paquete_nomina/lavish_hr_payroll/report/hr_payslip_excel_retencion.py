# -*- coding: utf-8 -*-
"""
Módulo de exportación Excel para Retención en la Fuente
========================================================

Extensión de hr.payslip para generar reportes Excel de retención
en la fuente según el Art. 383 del E.T.
"""

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta, date
import json
import base64
import io
import xlsxwriter


class HrPayslipExcelRetencion(models.Model):
    _inherit = 'hr.payslip'

    # ══════════════════════════════════════════════════════════════════════════
    # NORMALIZADOR DE DATOS PARA RETENCION
    # ══════════════════════════════════════════════════════════════════════════

    def _normalize_retention_data(self, raw_data):
        """
        Normaliza los datos de retencion de la nueva estructura al formato esperado por el Excel.

        Nueva estructura (retention_data/retention_kpi):
        - ingresos: {salario, devengados, total, lineas_detalle}
        - aportes: {salud, pension, solidaridad, subsistencia, total}
        - beneficios: {deducciones, ded_dependientes, ded_prepagada, ded_vivienda, rentas_exentas, renta_exenta_25}
        - base_gravable: {ibr3_final, ibr_uvts, ...}
        - retencion: {calculada, anterior, definitiva, tarifa_porcentaje}
        - parametros: {valor_uvt, dias_trabajados, debe_proyectar}
        - pasos_normativos: [lista de pasos con detalle]

        Formato esperado por Excel:
        - salario, comisiones, dev_salarial, dev_no_salarial, total_ing_base
        - salud, pension, solidaridad, subsistencia, total_pension, ing_no_gravados
        - ded_vivienda, ded_dependientes, ded_salud, total_deducciones
        - re_afc, renta_exenta_25, total_re
        - subtotal_ibr1, ibr_uvts, rate, retencion, retencion_anterior, retencion_def
        """
        if isinstance(raw_data, list):
            data = raw_data[0] if raw_data else {}
        else:
            data = raw_data

        # Si ya tiene el formato antiguo, devolverlo tal cual
        if 'salario' in data and 'total_ing_base' in data:
            return data

        # Extraer datos de la nueva estructura
        ingresos = data.get('ingresos', {})
        aportes = data.get('aportes', {})
        beneficios = data.get('beneficios', {})
        base_gravable = data.get('base_gravable', {})
        retencion = data.get('retencion', {})
        parametros = data.get('parametros', {})
        pasos = data.get('pasos_normativos', [])

        # Si tiene estructura de retention_data (completa con pasos_aplicados)
        if 'pasos_aplicados' in data:
            ingresos_paso = next((p.get('detalle', {}) for p in data.get('pasos_aplicados', []) if p.get('paso') == 1), {})
            aportes_paso = next((p.get('detalle', {}) for p in data.get('pasos_aplicados', []) if p.get('paso') == 2), {})
            deducciones_paso = next((p.get('detalle', {}) for p in data.get('pasos_aplicados', []) if p.get('paso') == 3), {})
            rentas_paso = next((p.get('detalle', {}) for p in data.get('pasos_aplicados', []) if p.get('paso') == 4), {})
            renta25_paso = next((p.get('detalle', {}) for p in data.get('pasos_aplicados', []) if p.get('paso') == 5), {})
            limite_paso = next((p.get('detalle', {}) for p in data.get('pasos_aplicados', []) if p.get('paso') == 6), {})
            tabla_paso = next((p.get('detalle', {}) for p in data.get('pasos_aplicados', []) if p.get('paso') == 7), {})
            final_paso = next((p.get('detalle', {}) for p in data.get('pasos_aplicados', []) if p.get('paso') == 8), {})

            # Extraer ingresos
            salario = ingresos_paso.get('salario', 0) or ingresos.get('salario', 0)
            comisiones = 0  # Buscar en lineas_detalle
            dev_salarial = ingresos_paso.get('devengados', 0) or ingresos.get('devengados', 0)
            dev_no_salarial = ingresos_paso.get('dev_no_salarial', 0)
            proyectados = ingresos_paso.get('proyectados', 0)
            total_ing = ingresos_paso.get('total', 0) or ingresos.get('total', 0)

            # Buscar comisiones en lineas_detalle
            lineas_detalle = ingresos_paso.get('lineas_detalle', [])
            for linea in lineas_detalle:
                if linea.get('category_code') == 'COMISIONES':
                    comisiones += linea.get('total', 0)

            # Extraer aportes
            salud = aportes_paso.get('salud', 0) or aportes.get('salud', 0)
            pension = aportes_paso.get('pension', 0) or aportes.get('pension', 0)
            solidaridad = aportes_paso.get('solidaridad', 0) or aportes.get('solidaridad', 0)
            subsistencia = aportes_paso.get('subsistencia', 0) or aportes.get('subsistencia', 0)
            total_pension = pension + solidaridad + subsistencia
            ing_no_gravados = aportes_paso.get('total', 0) or aportes.get('total', 0)

            # Extraer deducciones
            ded_vivienda = deducciones_paso.get('vivienda', 0) or beneficios.get('ded_vivienda', 0)
            ded_dependientes = deducciones_paso.get('dependientes', 0) or beneficios.get('ded_dependientes', 0)
            ded_salud = deducciones_paso.get('prepagada', 0) or beneficios.get('ded_prepagada', 0)
            total_deducciones = deducciones_paso.get('total', 0) or beneficios.get('deducciones', 0)

            # Extraer rentas exentas
            re_afc = rentas_paso.get('total_aceptado', 0) or beneficios.get('rentas_exentas', 0)
            renta_exenta_25 = renta25_paso.get('valor_aplicado', 0) or beneficios.get('renta_exenta_25', 0)
            total_re = re_afc

            # Extraer base gravable y subtotales
            subtotales = data.get('subtotales', {})
            subtotal_ibr1 = subtotales.get('subtotal_1', 0) or base_gravable.get('ibr1_antes_deducciones', 0)
            ibr_uvts = subtotales.get('base_gravable_uvt', 0) or base_gravable.get('ibr_uvts', 0)

            # Extraer retencion
            rate = data.get('tarifa', 0) or retencion.get('tarifa_porcentaje', 0)
            retencion_calc = data.get('retencion_calculada', 0) or retencion.get('calculada', 0)
            retencion_anterior = data.get('retencion_anterior', 0) or retencion.get('anterior', 0)
            retencion_def = data.get('retencion_definitiva', 0) or retencion.get('definitiva', 0)

            # Extraer parametros
            uvt = parametros.get('valor_uvt', 0)
            dias_trabajados = data.get('dias_trabajados', 30) or parametros.get('dias_trabajados', 30)
            es_proyectado = data.get('es_proyectado', False) or parametros.get('debe_proyectar', False)

        else:
            # Formato de retention_kpi
            salario = ingresos.get('salario', 0)
            comisiones = 0
            dev_salarial = ingresos.get('devengados', 0)
            dev_no_salarial = 0
            proyectados = 0
            total_ing = ingresos.get('total', 0)

            salud = aportes.get('salud', 0)
            pension = aportes.get('pension', 0)
            solidaridad = aportes.get('solidaridad', 0)
            subsistencia = aportes.get('subsistencia', 0)
            total_pension = aportes.get('total_pension', 0)
            ing_no_gravados = aportes.get('total', 0)

            ded_vivienda = beneficios.get('ded_vivienda', 0)
            ded_dependientes = beneficios.get('ded_dependientes', 0)
            ded_salud = beneficios.get('ded_prepagada', 0)
            total_deducciones = beneficios.get('deducciones', 0)

            re_afc = beneficios.get('rentas_exentas', 0)
            renta_exenta_25 = beneficios.get('renta_exenta_25', 0)
            total_re = re_afc

            subtotal_ibr1 = base_gravable.get('ibr1_antes_deducciones', 0)
            ibr_uvts = base_gravable.get('ibr_uvts', 0)

            rate = retencion.get('tarifa_porcentaje', 0)
            retencion_calc = retencion.get('calculada', 0)
            retencion_anterior = retencion.get('anterior', 0)
            retencion_def = retencion.get('definitiva', 0)

            uvt = parametros.get('valor_uvt', 0)
            dias_trabajados = parametros.get('dias_trabajados', 30)
            es_proyectado = parametros.get('debe_proyectar', False)

        # Construir estructura normalizada para Excel
        normalized = {
            # Tipo de calculo
            'tipo': data.get('tipo', 'normal'),
            'valor': data.get('valor', 0),  # Para monto fijo

            # Ingresos
            'salario': salario,
            'comisiones': comisiones,
            'dev_salarial': dev_salarial,
            'dev_no_salarial': dev_no_salarial,
            'proyectados': proyectados,
            'total_ing_base': total_ing,

            # Aportes (INCR)
            'salud': salud,
            'pension': pension,
            'solidaridad': solidaridad,
            'subsistencia': subsistencia,
            'total_pension': total_pension,
            'ing_no_gravados': ing_no_gravados,

            # Deducciones
            'ded_vales': 0,  # No implementado
            'ded_vivienda': ded_vivienda,
            'ded_dependientes': ded_dependientes,
            'ded_salud': ded_salud,
            'total_deducciones': total_deducciones,

            # Rentas exentas
            're_afc': re_afc,
            'renta_exenta_25': renta_exenta_25,
            'total_re': total_re,

            # Base gravable
            'subtotal_ibr1': subtotal_ibr1,
            'ibr_uvts': ibr_uvts,

            # Retencion
            'rate': rate,
            'retencion': retencion_calc,
            'retencion_anterior': retencion_anterior,
            'retencion_def': retencion_def,

            # Parametros
            'uvt': uvt,
            'dias_trabajados': dias_trabajados,
            'es_proyectado': es_proyectado,

            # Datos adicionales para proyeccion
            'pasos': pasos,
            'valores_sin_proyectar': data.get('valores_sin_proyectar', {}),
            'aportes_sin_proyectar': data.get('aportes_sin_proyectar', {}),
            'desglose_pension': {
                'pension': pension,
                'solidaridad': solidaridad,
                'subsistencia': subsistencia,
            },
        }

        return normalized

    # ══════════════════════════════════════════════════════════════════════════
    # ACCION DE EXPORTAR EXCEL RETENCION
    # ══════════════════════════════════════════════════════════════════════════

    def action_exportar_excel_retencion(self):
        """
        Acción para exportar el reporte Excel de retención en la fuente.
        """
        self.ensure_one()
        linea_retencion = False
        for rec in self.line_ids.filtered(lambda l: l.code == 'RT_MET_01'):
            linea_retencion = rec
            break
        if not linea_retencion or not linea_retencion.computation:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Advertencia'),
                    'message': _('No hay datos de retención para exportar.'),
                    'sticky': False,
                    'type': 'warning',
                }
            }

        log_data = linea_retencion.computation
        if isinstance(log_data, str):
            try:
                log_data = json.loads(log_data)
            except (KeyError, AttributeError):
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Error'),
                        'message': _('El formato de los datos de retencion no es valido.'),
                        'sticky': False,
                        'type': 'danger',
                    }
                }

        # Normalizar datos al formato esperado por el Excel
        log_data = self._normalize_retention_data(log_data)

        company = self.company_id
        company_info = {
            'name': company.name,
            'vat': company.vat or '',
            'street': company.street or '',
            'phone': company.phone or '',
            'email': company.email or '',
        }
        payslip_info = {
            'employee_name': self.employee_id.name,
            'employee_identification': self.employee_id.identification_id or '',
            'number': self.number or '',
            'date': self.date_to.strftime('%d/%m/%Y') if self.date_to else '',
            'date_from': self.date_from.strftime('%d/%m/%Y') if self.date_from else '',
            'date_to': self.date_to.strftime('%d/%m/%Y') if self.date_to else '',
        }
        excel_base64 = self._generar_excel_retencion(
            log_data,
            company_info=company_info,
            payslip_info=payslip_info
        )
        if not excel_base64:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('No se pudo generar el Excel.'),
                    'sticky': False,
                    'type': 'danger',
                }
            }
        filename = f'retencion_{self.employee_id.name}_{self.date_to.strftime("%Y%m%d")}.xlsx'
        self.write({
            'excel_lines': excel_base64,
            'excel_lines_filename': filename
        })
        action = {
            'name': 'Export Excel Retención en la Fuente',
            'type': 'ir.actions.act_url',
            'url': "web/content/?model=hr.payslip&id=" + str(
                self.id) + "&filename_field=excel_lines_filename&field=excel_lines&download=true&filename=" + self.excel_lines_filename,
            'target': 'self',
        }

        return action

    # ══════════════════════════════════════════════════════════════════════════
    # GENERADOR EXCEL RETENCION
    # ══════════════════════════════════════════════════════════════════════════

    def _generar_excel_retencion(self, log_data, company_info=None, payslip_info=None):
        """
        Genera un reporte Excel para la retención en la fuente.

        El cálculo se basa en el artículo 383 del Estatuto Tributario,
        modificado por el artículo 42 de la Ley 2010 de 2019.

        Args:
            log_data: Datos de cálculo de retención
            company_info: Información de la empresa
            payslip_info: Información de la nómina

        Returns:
            Excel codificado en base64
        """
        # Normalizar los datos de entrada
        if isinstance(log_data, list):
            data = log_data[0] if log_data else {}
        else:
            data = log_data

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet('Retención en la Fuente')

        # Definición de colores y formatos
        azul_oscuro = '#0A3D62'
        azul_claro = '#2980B9'
        gris_claro = '#F5F5F5'
        verde_claro = '#d1e7dd'  # Color verde suave para valores proyectados
        naranja_claro = '#fff3cd'  # Color naranja suave para advertencias

        titulo_formato = workbook.add_format({
            'font_name': 'Arial', 'font_size': 14, 'bold': True,
            'font_color': 'white', 'bg_color': azul_oscuro,
            'align': 'center', 'valign': 'vcenter'
        })
        subtitulo_formato = workbook.add_format({
            'font_name': 'Arial', 'font_size': 12, 'bold': True,
            'font_color': 'white', 'bg_color': azul_oscuro,
            'align': 'left', 'valign': 'vcenter'
        })
        texto_normal = workbook.add_format({
            'font_name': 'Arial', 'font_size': 10,
            'align': 'left', 'valign': 'vcenter', 'border': 1
        })
        texto_normal_alt = workbook.add_format({
            'font_name': 'Arial', 'font_size': 10,
            'align': 'left', 'valign': 'vcenter', 'border': 1,
            'bg_color': gris_claro
        })
        texto_bold = workbook.add_format({
            'font_name': 'Arial', 'font_size': 10, 'bold': True,
            'align': 'right', 'valign': 'vcenter', 'border': 1
        })
        texto_bold_alt = workbook.add_format({
            'font_name': 'Arial', 'font_size': 10, 'bold': True,
            'align': 'right', 'valign': 'vcenter', 'border': 1,
            'bg_color': gris_claro
        })
        retención_formato = workbook.add_format({
            'font_name': 'Arial', 'font_size': 10, 'bold': True,
            'align': 'right', 'valign': 'vcenter', 'border': 1,
            'bg_color': azul_claro, 'font_color': 'white'
        })

        # Nuevos formatos para proyección
        proyeccion_titulo = workbook.add_format({
            'font_name': 'Arial', 'font_size': 12, 'bold': True,
            'font_color': 'white', 'bg_color': '#28a745',  # Verde oscuro
            'align': 'left', 'valign': 'vcenter'
        })

        texto_proyectado = workbook.add_format({
            'font_name': 'Arial', 'font_size': 10, 'bold': True,
            'align': 'right', 'valign': 'vcenter', 'border': 1,
            'bg_color': verde_claro, 'font_color': '#0f5132'  # Verde oscuro
        })

        header_format = workbook.add_format({
            'font_name': 'Arial', 'font_size': 11, 'bold': True,
            'bg_color': '#F2F2F2', 'border': 1,
            'align': 'right', 'valign': 'vcenter'
        })

        data_format = workbook.add_format({
            'font_name': 'Arial', 'font_size': 11,
            'bg_color': '#F2F2F2', 'border': 1,
            'align': 'left', 'valign': 'vcenter'
        })

        nota_formato = workbook.add_format({
            'font_name': 'Arial', 'font_size': 9,
            'font_color': '#0A3D62', 'align': 'center', 'valign': 'vcenter'
        })

        alerta_formato = workbook.add_format({
            'font_name': 'Arial', 'font_size': 10,
            'bg_color': naranja_claro, 'border': 1,
            'align': 'left', 'valign': 'vcenter', 'text_wrap': True
        })

        referencia_legal_formato = workbook.add_format({
            'font_name': 'Arial', 'font_size': 9, 'italic': True,
            'font_color': '#666666', 'align': 'left', 'valign': 'vcenter',
        })

        encabezado_proyeccion = workbook.add_format({
            'font_name': 'Arial', 'font_size': 10, 'bold': True,
            'align': 'center', 'valign': 'vcenter', 'border': 1,
            'bg_color': azul_oscuro, 'font_color': 'white'
        })

        # Configuración de columnas
        worksheet.set_column('A:A', 5)
        worksheet.set_column('B:B', 40)
        worksheet.set_column('C:C', 15)
        worksheet.set_column('D:D', 15)
        worksheet.set_column('E:E', 15)
        worksheet.set_column('F:F', 15)  # Para proyección

        fila_actual = 0

        # Información de empresa
        if company_info:
            worksheet.merge_range(fila_actual, 1, fila_actual, 4, company_info.get('name', 'EMPRESA'), workbook.add_format({
                'font_name': 'Arial', 'font_size': 14, 'bold': True,
                'align': 'center', 'valign': 'vcenter'
            }))
            fila_actual += 1
            worksheet.write(fila_actual, 1, "NIT:", header_format)
            worksheet.write(fila_actual, 2, company_info.get('vat', ''), data_format)
            worksheet.write(fila_actual, 3, "Dirección:", header_format)
            worksheet.write(fila_actual, 4, company_info.get('street', ''), data_format)
            fila_actual += 1
            worksheet.write(fila_actual, 1, "Teléfono:", header_format)
            worksheet.write(fila_actual, 2, company_info.get('phone', ''), data_format)
            worksheet.write(fila_actual, 3, "Email:", header_format)
            worksheet.write(fila_actual, 4, company_info.get('email', ''), data_format)
            fila_actual += 1

        # Información del empleado/nómina
        if payslip_info:
            worksheet.write(fila_actual, 1, "Empleado:", header_format)
            worksheet.write(fila_actual, 2, payslip_info.get('employee_name', ''), data_format)
            worksheet.write(fila_actual, 3, "Documento:", header_format)
            worksheet.write(fila_actual, 4, payslip_info.get('employee_identification', ''), data_format)
            fila_actual += 1
            worksheet.write(fila_actual, 1, "Nómina No.:", header_format)
            worksheet.write(fila_actual, 2, payslip_info.get('number', ''), data_format)
            worksheet.write(fila_actual, 3, "Fecha:", header_format)
            worksheet.write(fila_actual, 4, payslip_info.get('date', ''), data_format)
            fila_actual += 1
            worksheet.write(fila_actual, 1, "Periodo:", header_format)
            periodo = f"{payslip_info.get('date_from', '')} - {payslip_info.get('date_to', '')}"
            worksheet.merge_range(fila_actual, 2, fila_actual, 4, periodo, data_format)
            fila_actual += 2

        # Título principal
        worksheet.merge_range(fila_actual, 1, fila_actual, 4, "RETENCIÓN EN LA FUENTE MENSUAL", titulo_formato)
        fila_actual += 1

        # Referencia legal
        worksheet.merge_range(fila_actual, 1, fila_actual, 4,
                        "Cálculo según Art. 383 del E.T., modificado por Art. 42 de la Ley 2010 de 2019",
                        referencia_legal_formato)
        fila_actual += 1

        # Valor UVT
        worksheet.merge_range(fila_actual, 1, fila_actual, 2, "Valor UVT:", workbook.add_format({
            'font_name': 'Arial', 'font_size': 10, 'bold': True,
            'align': 'left', 'valign': 'vcenter'
        }))
        worksheet.merge_range(fila_actual, 3, fila_actual, 4, f"${data.get('uvt', 0):,.0f}", workbook.add_format({
            'font_name': 'Arial', 'font_size': 10, 'bold': True,
            'align': 'right', 'valign': 'vcenter'
        }))
        fila_actual += 2

        # Verificar tipo de cálculo (fijo o normal)
        if data.get("tipo") == "monto_fijo":
            valor_fijo = data.get("valor", 0)

            # Sección de valor fijo con alerta
            worksheet.merge_range(fila_actual, 1, fila_actual, 4, "VALOR FIJO DE RETENCIÓN", subtitulo_formato)
            fila_actual += 1

            worksheet.merge_range(fila_actual, 1, fila_actual + 1, 4,
                            "ADVERTENCIA: Se está aplicando un valor fijo de retención establecido por el usuario. "
                            "Este valor no se calcula según el procedimiento estándar.",
                            alerta_formato)
            fila_actual += 3

            worksheet.merge_range(fila_actual, 1, fila_actual, 2, "Valor de retención fijo:", texto_bold)
            valor_fijo_formato = workbook.add_format({
                'font_name': 'Arial', 'font_size': 12, 'bold': True,
                'bg_color': verde_claro, 'color': '#0f5132',
                'align': 'right', 'valign': 'vcenter', 'border': 1
            })
            worksheet.merge_range(fila_actual, 3, fila_actual, 4, f"${valor_fijo:,.2f}", valor_fijo_formato)

        elif data.get("tipo") == "extranjero_no_residente":
            # Sección para extranjero no residente
            worksheet.merge_range(fila_actual, 1, fila_actual, 4, "RETENCIÓN PARA EXTRANJERO NO RESIDENTE", subtitulo_formato)
            fila_actual += 1

            worksheet.merge_range(fila_actual, 1, fila_actual + 1, 4,
                        "Se aplica una tarifa única del 20% sobre la totalidad de pagos laborales según Artículo 408 del Estatuto Tributario.",
                        alerta_formato)
            fila_actual += 3

            worksheet.merge_range(fila_actual, 1, fila_actual, 2, "Total ingresos:", texto_bold)
            worksheet.merge_range(fila_actual, 3, fila_actual, 4, f"${data.get('total_ingresos', 0):,.2f}", texto_bold)
            fila_actual += 1

            worksheet.merge_range(fila_actual, 1, fila_actual, 2, "Tarifa aplicable:", texto_bold)
            worksheet.merge_range(fila_actual, 3, fila_actual, 4, "20%", texto_bold)
            fila_actual += 1

            worksheet.merge_range(fila_actual, 1, fila_actual, 2, "Retención a aplicar:", texto_bold)
            worksheet.merge_range(fila_actual, 3, fila_actual, 4, f"${data.get('retencion', 0):,.2f}", retención_formato)

        else:
            # SECCIÓN DE PROYECCIÓN (solo si es cálculo normal y tiene proyección)
            es_proyectado = data.get('es_proyectado', False)

            if es_proyectado:
                worksheet.merge_range(fila_actual, 1, fila_actual, 4, "INFORMACIÓN DE PROYECCIÓN", proyeccion_titulo)
                fila_actual += 1

                worksheet.merge_range(fila_actual, 1, fila_actual + 1, 4,
                                "NOTA: Los valores han sido proyectados para el cálculo de la retención.\n"
                                "A continuación se muestran los valores originales y proyectados para comparación.\n"
                                "El resultado final se divide por 2 ya que solo aplica para esta quincena.",
                                alerta_formato)
                fila_actual += 3

                # Encabezados de tabla de proyección
                worksheet.write(fila_actual, 1, "Concepto", encabezado_proyeccion)
                worksheet.write(fila_actual, 2, "Valor Base", encabezado_proyeccion)
                worksheet.write(fila_actual, 3, "Valor Proyectado", encabezado_proyeccion)
                worksheet.write(fila_actual, 4, "Diferencia", encabezado_proyeccion)
                fila_actual += 1

                # Calcular formato alternado para filas
                def formato_alt(idx, normal, alt):
                    return alt if idx % 2 else normal

                # Valores de ingresos sin proyectar vs proyectados
                valores_sin_proyectar = data.get('valores_sin_proyectar', {})

                # Factor de proyección
                factor_idx = 0
                worksheet.write(fila_actual, 1, "Factor de proyección", formato_alt(factor_idx, texto_normal, texto_normal_alt))
                factor = 0
                for paso in data.get('pasos', []):
                    if isinstance(paso, dict) and paso.get('descripcion') == 'Factor de proyección':
                        factor = paso.get('valor', 0)
                        break
                worksheet.write(fila_actual, 2, f"{factor:.2f}", formato_alt(factor_idx, texto_bold, texto_bold_alt))
                worksheet.merge_range(fila_actual, 3, fila_actual, 4, "Se aplica este factor a los valores base", formato_alt(factor_idx, texto_normal, texto_normal_alt))
                fila_actual += 1

                # Días
                dias_idx = 1
                dias_trabajados = data.get('dias_trabajados', 0)
                worksheet.write(fila_actual, 1, "Días trabajados", formato_alt(dias_idx, texto_normal, texto_normal_alt))
                worksheet.write(fila_actual, 2, f"{dias_trabajados}", formato_alt(dias_idx, texto_bold, texto_bold_alt))
                worksheet.write(fila_actual, 3, f"{30}", formato_alt(dias_idx, texto_proyectado, texto_proyectado))
                worksheet.write(fila_actual, 4, f"{30 - dias_trabajados}", formato_alt(dias_idx, texto_bold, texto_bold_alt))
                fila_actual += 1

                # Ingresos proyectados
                conceptos_ingresos = [
                    ("Salario básico", "basic", "salario"),
                    ("Comisiones", "comisiones", "comisiones"),
                    ("Devengos salariales", "dev_salarial", "dev_salarial"),
                    ("Devengos no salariales", "dev_no_salarial", "dev_no_salarial"),
                    ("Total ingresos", "total_ing_base", "total_ing_base")
                ]

                for idx, (concepto, key_base, key_proy) in enumerate(conceptos_ingresos, 2):
                    valor_base = valores_sin_proyectar.get(key_base, 0)
                    valor_proyectado = data.get(key_proy, 0)
                    diferencia = valor_proyectado - valor_base

                    worksheet.write(fila_actual, 1, concepto, formato_alt(idx, texto_normal, texto_normal_alt))
                    worksheet.write(fila_actual, 2, f"${valor_base:,.0f}", formato_alt(idx, texto_bold, texto_bold_alt))
                    worksheet.write(fila_actual, 3, f"${valor_proyectado:,.0f}", formato_alt(idx, texto_proyectado, texto_proyectado))
                    worksheet.write(fila_actual, 4, f"${diferencia:,.0f}", formato_alt(idx, texto_bold, texto_bold_alt))
                    fila_actual += 1

                # Aportes proyectados
                aportes_sin_proyectar = data.get('aportes_sin_proyectar', {})
                desglose_pension = data.get('desglose_pension', {})

                fila_actual += 1  # Espacio entre secciones

                worksheet.write(fila_actual, 1, "APORTES OBLIGATORIOS", encabezado_proyeccion)
                worksheet.merge_range(fila_actual, 2, fila_actual, 4, "Comparativo de valores base y proyectados", encabezado_proyeccion)
                fila_actual += 1

                # Pensión total
                idx = 0
                concepto = "Pensión total"
                valor_base = aportes_sin_proyectar.get("pension_total", 0)
                valor_proyectado = data.get("total_pension", 0)
                diferencia = valor_proyectado - valor_base

                worksheet.write(fila_actual, 1, concepto, formato_alt(idx, texto_normal, texto_normal_alt))
                worksheet.write(fila_actual, 2, f"${valor_base:,.0f}", formato_alt(idx, texto_bold, texto_bold_alt))
                worksheet.write(fila_actual, 3, f"${valor_proyectado:,.0f}", formato_alt(idx, texto_proyectado, texto_proyectado))
                worksheet.write(fila_actual, 4, f"${diferencia:,.0f}", formato_alt(idx, texto_bold, texto_bold_alt))
                fila_actual += 1

                # Componentes de pensión
                componentes_pension = [
                    ("Aporte Pensión", "pension", "pension"),
                    ("Fondo de Solidaridad", "solidaridad", "solidaridad"),
                    ("Subsistencia", "subsistencia", "subsistencia")
                ]

                for idx, (concepto, key_base, key_desglose) in enumerate(componentes_pension, 1):
                    valor_base = aportes_sin_proyectar.get(key_base, 0)
                    valor_proyectado = desglose_pension.get(key_desglose, 0)
                    diferencia = valor_proyectado - valor_base

                    worksheet.write(fila_actual, 1, f"  • {concepto}", formato_alt(idx, texto_normal, texto_normal_alt))
                    worksheet.write(fila_actual, 2, f"${valor_base:,.0f}", formato_alt(idx, texto_bold, texto_bold_alt))
                    worksheet.write(fila_actual, 3, f"${valor_proyectado:,.0f}", formato_alt(idx, texto_proyectado, texto_proyectado))
                    worksheet.write(fila_actual, 4, f"${diferencia:,.0f}", formato_alt(idx, texto_bold, texto_bold_alt))
                    fila_actual += 1

                # Salud y total aportes
                otros_aportes = [
                    ("Salud", "salud", "salud"),
                    ("Total aportes", "total", "ing_no_gravados")
                ]

                for idx, (concepto, key_base, key_proy) in enumerate(otros_aportes, 4):
                    valor_base = aportes_sin_proyectar.get(key_base, 0)
                    valor_proyectado = data.get(key_proy, 0)
                    diferencia = valor_proyectado - valor_base

                    worksheet.write(fila_actual, 1, concepto, formato_alt(idx, texto_normal, texto_normal_alt))
                    worksheet.write(fila_actual, 2, f"${valor_base:,.0f}", formato_alt(idx, texto_bold, texto_bold_alt))
                    worksheet.write(fila_actual, 3, f"${valor_proyectado:,.0f}", formato_alt(idx, texto_proyectado, texto_proyectado))
                    worksheet.write(fila_actual, 4, f"${diferencia:,.0f}", formato_alt(idx, texto_bold, texto_bold_alt))
                    fila_actual += 1

                fila_actual += 1  # Espacio extra después de la sección de proyección

            # SECCIONES NORMALES DEL REPORTE

            def crear_seccion(titulo, contenido_filas, referencia_legal=None):
                nonlocal fila_actual
                worksheet.merge_range(fila_actual, 1, fila_actual, 4, titulo, subtitulo_formato)
                fila_actual += 1

                # Agregar referencia legal si existe
                if referencia_legal:
                    worksheet.merge_range(fila_actual, 1, fila_actual, 4, referencia_legal, referencia_legal_formato)
                    fila_actual += 1

                for i, fila in enumerate(contenido_filas):
                    es_alterna = i % 2 == 1
                    formato_texto = texto_normal_alt if es_alterna else texto_normal
                    formato_valor = texto_bold_alt if es_alterna else texto_bold
                    es_retencion = "Retención" in fila[0] if len(fila) > 0 else False
                    if es_retencion:
                        formato_valor = retención_formato
                    label = fila[0] if len(fila) > 0 else ""
                    value = fila[1] if len(fila) > 1 else ""
                    observation = fila[2] if len(fila) > 2 else None
                    limit = fila[3] if len(fila) > 3 else None
                    worksheet.merge_range(fila_actual, 1, fila_actual, 2, label, formato_texto)
                    worksheet.merge_range(fila_actual, 3, fila_actual, 4, value, formato_valor)
                    fila_actual += 1
                    if observation or limit:
                        notas = []
                        if observation:
                            notas.append(f"Nota: {observation}")
                        if limit:
                            notas.append(f"Límite: {limit}")

                        nota_texto = " | ".join(notas)
                        worksheet.merge_range(fila_actual, 1, fila_actual, 4, nota_texto, nota_formato)
                        fila_actual += 1

                fila_actual += 1

            # Crear entradas para ingresos
            ingresos_filas = [
                ("Sueldo básico", f"${data.get('salario', 0):,.0f}", None),
                ("Comisiones", f"${data.get('comisiones', 0):,.0f}", None),
                ("Otros pagos laborales", f"${data.get('dev_salarial', 0) + data.get('dev_no_salarial', 0):,.0f}", None),
                ("Total Ingresos Laborales", f"${data.get('total_ing_base', 0):,.0f}", None)
            ]
            crear_seccion("1. PAGOS LABORALES DEL MES", ingresos_filas)

            # Crear entradas para aportes
            aportes_filas = [
                ("Aportes obligatorios a Pensión", f"${data.get('total_pension', 0):,.0f}", "Sin límites"),
                ("Aportes obligatorios a Salud", f"${data.get('salud', 0):,.0f}", "Sin límites"),
                ("Total Ingresos No Constitutivos", f"${data.get('ing_no_gravados', 0):,.0f}", None),
                ("Subtotal 1", f"${data.get('subtotal_ibr1', 0) + data.get('total_deducciones', 0):,.0f}", None)
            ]
            crear_seccion("2. INGRESOS NO CONSTITUTIVOS DE RENTA", aportes_filas)

            # Crear entradas para deducciones
            deducciones_filas = [
                ("Vales de alimentación", f"${data.get('ded_vales', 0):,.0f}",
                "Máximo 41 UVT mensual para ingresos menores a 310 UVT"),

                ("Intereses de vivienda", f"${data.get('ded_vivienda', 0):,.0f}",
                "Límite máximo 100 UVT Mensuales"),

                ("Dependientes", f"${data.get('ded_dependientes', 0):,.0f}",
                "No puede exceder del 10% del ingreso bruto y máximo 32 UVT mensuales"),

                ("Medicina prepagada", f"${data.get('ded_salud', 0):,.0f}",
                "No puede exceder 16 UVT Mensuales"),

                ("Total Deducciones", f"${data.get('total_deducciones', 0):,.0f}", None)
            ]
            crear_seccion("3. DEDUCCIONES", deducciones_filas,
                        "Según Art. 387 del E.T. y normas reglamentarias")

            # Crear entradas para rentas exentas
            rentas_filas = [
                ("Aportes AFC", f"${data.get('re_afc', 0):,.0f}",
                "Límite del 30% del ingreso laboral y hasta 3.800 UVT anuales"),

                ("Renta Exenta 25%", f"${data.get('renta_exenta_25', 0):,.0f}",
                "Límite máximo de 790 UVT anuales (Ley 2277 de 2022)"),

                ("Total Rentas Exentas", f"${data.get('total_re', 0) + data.get('renta_exenta_25', 0):,.0f}", None)
            ]
            crear_seccion("4. RENTAS EXENTAS", rentas_filas,
                        "Basado en Art. 126-4 y Art. 206 numeral 10 del E.T.")

            # Crear entradas para base gravable y retención
            base_filas = [
                ("Base Gravable en UVTs", f"{data.get('ibr_uvts', 0):,.2f}", None),
                ("Porcentaje de Retención", f"{data.get('rate', 0)}%", None),
                ("Retención calculada", f"${data.get('retencion', 0):,.0f}", None),
            ]

            # Agregar nota de proyección si aplica
            if es_proyectado:
                nota_ajuste = "(Dividido por 2 al ser proyectado)"
                base_filas.append(("Ajuste por proyección", nota_ajuste, None))

            base_filas.extend([
                ("Retención anterior", f"${data.get('retencion_anterior', 0):,.0f}", None),
                ("Retención definitiva", f"${data.get('retencion_def', 0):,.0f}", None)
            ])

            crear_seccion("5. BASE GRAVABLE Y RETENCIÓN", base_filas,
                        "Calculado según Art. 383 del E.T. con redondeo según Ley 1111 de 2006, Art. 50")

            worksheet.merge_range(fila_actual, 1, fila_actual + 2, 4,
                                "NOTA IMPORTANTE: La sumatoria de las Deducciones, Rentas exentas y el 25% de la renta de trabajo exenta, "
                                "no podrá superar el 40% del ingreso señalado en el subtotal 1 hasta 1340 UVT anuales (Ley 2277 de 2022)",
                                alerta_formato)
            fila_actual += 4

            # SECCIÓN DE TABLA DE RANGOS

            worksheet.merge_range(fila_actual, 1, fila_actual, 4, "TABLA DE RANGOS DE RETENCIÓN EN LA FUENTE", subtitulo_formato)
            fila_actual += 1

            worksheet.merge_range(fila_actual, 1, fila_actual, 6,
                            "Conforme al Art. 383 del E.T., modificado por el Art. 42 de la Ley 2010 de 2019",
                            referencia_legal_formato)
            fila_actual += 1

            tabla_encabezado = workbook.add_format({
                'font_name': 'Arial', 'font_size': 10, 'bold': True,
                'bg_color': azul_oscuro, 'font_color': 'white',
                'align': 'center', 'valign': 'vcenter', 'border': 1
            })

            worksheet.write(fila_actual, 1, "Rangos en UVT", tabla_encabezado)
            worksheet.write(fila_actual, 2, "Desde", tabla_encabezado)
            worksheet.write(fila_actual, 3, "Hasta", tabla_encabezado)
            worksheet.write(fila_actual, 4, "Tarifa marginal", tabla_encabezado)
            worksheet.write(fila_actual, 5, "Impuesto", tabla_encabezado)
            worksheet.write(fila_actual, 6, "Aplicable", tabla_encabezado)
            fila_actual += 1

            tabla_data = [
                ["1", ">0", "95", "0%", "-"],
                ["2", "95", "150", "19%", "(Ingreso laboral gravado expresado en UVT menos 95 UVT)*19%"],
                ["3", "150", "360", "28%", "(Ingreso laboral gravado expresado en UVT menos 150 UVT)*28% más 10 UVT"],
                ["4", "360", "640", "33%", "(Ingreso laboral gravado expresado en UVT menos 360 UVT)*33% más 69 UVT"],
                ["5", "640", "945", "35%", "(Ingreso laboral gravado expresado en UVT menos 640 UVT)*35% más 162 UVT"],
                ["6", "945", "2300", "37%", "(Ingreso laboral gravado expresado en UVT menos 945 UVT)*37% más 268 UVT"],
                ["7", "2300", "En adelante", "39%", "(Ingreso laboral gravado expresado en UVT menos 2300 UVT)*39% más 770 UVT"]
            ]

            base_uvts = data.get('ibr_uvts', 0)
            rango_aplicable = 0

            if base_uvts <= 95:
                rango_aplicable = 1
            elif 95 < base_uvts <= 150:
                rango_aplicable = 2
            elif 150 < base_uvts <= 360:
                rango_aplicable = 3
            elif 360 < base_uvts <= 640:
                rango_aplicable = 4
            elif 640 < base_uvts <= 945:
                rango_aplicable = 5
            elif 945 < base_uvts <= 2300:
                rango_aplicable = 6
            else:  # > 2300
                rango_aplicable = 7

            formato_tabla = workbook.add_format({
                'font_name': 'Arial', 'font_size': 10, 'border': 1,
                'align': 'center', 'valign': 'vcenter'
            })

            formato_tabla_alt = workbook.add_format({
                'font_name': 'Arial', 'font_size': 10, 'border': 1,
                'align': 'center', 'valign': 'vcenter',
                'bg_color': gris_claro
            })

            formato_rango_aplicable = workbook.add_format({
                'font_name': 'Arial', 'font_size': 10, 'border': 1,
                'align': 'center', 'valign': 'vcenter',
                'bg_color': azul_claro, 'font_color': 'white', 'bold': True
            })

            for i, fila in enumerate(tabla_data):
                es_alterna = i % 2 == 1
                es_aplicable = int(fila[0]) == rango_aplicable

                formato_fila = formato_rango_aplicable if es_aplicable else (formato_tabla_alt if es_alterna else formato_tabla)

                for j, valor in enumerate(fila):
                    worksheet.write(fila_actual, j + 1, valor, formato_fila)
                worksheet.write(fila_actual, 6, "X" if es_aplicable else "", formato_fila)

                fila_actual += 1

            # BASE APLICABLE CON DISMINUCIÓN DE UVT
            if base_uvts > 0:
                fila_actual += 1
                worksheet.merge_range(fila_actual, 1, fila_actual, 6, "BASE APLICABLE CON DISMINUCIÓN DE UVT", subtitulo_formato)
                fila_actual += 1
                worksheet.write(fila_actual, 1, "Base UVTs", tabla_encabezado)
                worksheet.write(fila_actual, 2, "Menos UVTs", tabla_encabezado)
                worksheet.write(fila_actual, 3, "Base Restante", tabla_encabezado)
                worksheet.write(fila_actual, 4, "Tarifa", tabla_encabezado)
                worksheet.write(fila_actual, 5, "Más UVTs", tabla_encabezado)
                worksheet.write(fila_actual, 6, "Retención UVTs", tabla_encabezado)
                fila_actual += 1
                resta_uvt = 0
                mas_uvt = 0
                tarifa = data.get('rate', 0)

                if 95 < base_uvts <= 150:
                    resta_uvt = 95
                    mas_uvt = 0
                elif 150 < base_uvts <= 360:
                    resta_uvt = 150
                    mas_uvt = 10
                elif 360 < base_uvts <= 640:
                    resta_uvt = 360
                    mas_uvt = 69
                elif 640 < base_uvts <= 945:
                    resta_uvt = 640
                    mas_uvt = 162
                elif 945 < base_uvts <= 2300:
                    resta_uvt = 945
                    mas_uvt = 268
                elif base_uvts > 2300:
                    resta_uvt = 2300
                    mas_uvt = 770

                base_restante = base_uvts - resta_uvt
                retencion_uvts = (base_restante * tarifa / 100) + mas_uvt

                # Aplicar ajuste por proyección
                if es_proyectado:
                    retencion_uvts = retencion_uvts / 2

                formato_valores = workbook.add_format({
                    'font_name': 'Arial', 'font_size': 10, 'border': 1,
                    'align': 'center', 'valign': 'vcenter', 'bold': True,
                    'bg_color': azul_claro, 'font_color': 'white'
                })

                worksheet.write(fila_actual, 1, f"{base_uvts:,.2f}", formato_valores)
                worksheet.write(fila_actual, 2, f"{resta_uvt:,.0f}", formato_valores)
                worksheet.write(fila_actual, 3, f"{base_restante:,.2f}", formato_valores)
                worksheet.write(fila_actual, 4, f"{tarifa}%", formato_valores)
                worksheet.write(fila_actual, 5, f"{mas_uvt:,.0f}", formato_valores)
                worksheet.write(fila_actual, 6, f"{retencion_uvts:,.2f}", formato_valores)

                # Si es proyectado, agregar nota explicativa
                if es_proyectado:
                    fila_actual += 2
                    worksheet.merge_range(fila_actual, 1, fila_actual, 6,
                                    "Nota: El valor de retención UVTs ha sido dividido por 2 debido a que es una proyección para quincena.",
                                    alerta_formato)

        workbook.close()

        output.seek(0)
        return base64.b64encode(output.read()).decode('utf-8')
