# -*- coding: utf-8 -*-

from datetime import date, datetime, timedelta
from typing import Dict, List, Tuple, Any, Optional
from collections import defaultdict
from dateutil.relativedelta import relativedelta
from decimal import Decimal, getcontext, ROUND_HALF_UP
import base64
import io
import xlsxwriter
import logging

from odoo import api, models, fields, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_is_zero

from .hr_payslip_constants import MONTH_NAMES

_logger = logging.getLogger(__name__)
getcontext().prec = 12


class LavishRetencionAcumulados(models.Model):
    _name = 'lavish.retencion.acumulados'
    _description = 'Acumulados para retención en la fuente'
    
    employee_id = fields.Many2one('hr.employee', 'Empleado', required=True)
    year = fields.Integer('Año', required=True)
    month = fields.Integer('Mes', default=0)
    quincena = fields.Selection([
        ('0', 'No aplica'),
        ('1', 'Primera quincena'),
        ('2', 'Segunda quincena')
    ], string='Quincena', default='0', required=True)
    date = fields.Date('Fecha', required=True)
    tipo = fields.Selection([
        ('avp_afc', 'AVP/AFC'),
        ('renta_exenta_25', 'Renta exenta 25%'),
        ('beneficios_40', 'Límite 40%'),
        ('periodo', 'Registro por periodo')
    ], string='Tipo de acumulado', required=True)
    
    valor_acumulado = fields.Float('Valor acumulado', default=0.0)
    last_update = fields.Date('Última actualización')
    
    avp_afc_periodo = fields.Float('AVP/AFC del periodo', default=0.0)
    renta_exenta_25_periodo = fields.Float('Renta exenta 25% del periodo', default=0.0)
    beneficios_40_periodo = fields.Float('Beneficios 40% del periodo', default=0.0)
    payslip_id = fields.Many2one('hr.payslip', 'Liquidación')
    
class LavishRetencionReporte(models.Model):
    _name = 'lavish.retencion.reporte'
    _description = 'Reporte de retención en la fuente'
    _order = 'year desc, month desc, quincena desc'
    
    name = fields.Char('Referencia', compute='_compute_name', store=True)
    employee_id = fields.Many2one('hr.employee', 'Empleado', required=True)
    date = fields.Date('Fecha', required=True)
    payslip_id = fields.Many2one('hr.payslip', 'Liquidación')
    
    year = fields.Integer('Año', required=True)
    month = fields.Integer('Mes', required=True)
    quincena = fields.Selection([
        ('0', 'Mensual'),
        ('1', 'Primera quincena'),
        ('2', 'Segunda quincena')
    ], string='Quincena', default='0', required=True)
    
    salario_basico = fields.Float('Salario básico', default=0.0)
    comisiones = fields.Float('Comisiones', default=0.0)
    dev_salarial = fields.Float('Devengos salariales', default=0.0)
    dev_no_salarial = fields.Float('Devengos no salariales', default=0.0)
    total_ingresos = fields.Float('Total ingresos laborales', default=0.0)
    
    salud = fields.Float('Aporte a salud', default=0.0)
    pension = fields.Float('Aporte a pensión', default=0.0)
    subsistencia = fields.Float('Fondo subsistencia', default=0.0)
    solidaridad = fields.Float('Fondo solidaridad', default=0.0)
    pension_total = fields.Float('Total aportes pensión', default=0.0)
    total_aportes = fields.Float('Total aportes obligatorios', default=0.0)
    
    ded_vivienda = fields.Float('Deducción vivienda', default=0.0)
    ded_dependientes = fields.Float('Deducción dependientes', default=0.0)
    ded_salud = fields.Float('Deducción salud prepagada', default=0.0)
    total_deducciones = fields.Float('Total deducciones', default=0.0)
    
    valor_avp_afc = fields.Float('Valor AVP/AFC', default=0.0)
    renta_exenta_25 = fields.Float('Renta exenta 25%', default=0.0)
    total_rentas_exentas = fields.Float('Total rentas exentas', default=0.0)
    
    subtotal_ibr1 = fields.Float('Subtotal 1 (Ingresos - Deducciones)', default=0.0)
    subtotal_ibr2 = fields.Float('Subtotal 2 (Subtotal 1 - AVP/AFC)', default=0.0)
    
    beneficios_limitados = fields.Float('Beneficios limitados', default=0.0)
    
    base_gravable = fields.Float('Base gravable')
    ibr_uvts = fields.Float('Base gravable en UVTs', default=0.0)
    tasa_aplicada = fields.Float('Tasa aplicada %', default=0.0)
    retencion_calculada = fields.Float('Retención calculada', default=0.0)
    retencion_anterior = fields.Float('Retención anterior', default=0.0)
    retencion_aplicada = fields.Float('Retención aplicada')
    
    base_legal = fields.Text('Base legal aplicada')
    uvt_valor = fields.Float('Valor UVT')
    ingresos_totales = fields.Float('Ingresos totales')
    es_proyectado = fields.Boolean('Es proyectado', default=False)
    
    reporte_json = fields.Text('Reporte detallado (JSON)')
    html_reporte = fields.Html('Reporte HTML')
    excel_file = fields.Binary('Archivo Excel')
    excel_filename = fields.Char('Nombre del archivo')

    # =========================================================================
    # Métodos de utilidad (antes en common.utils.mixin)
    # =========================================================================

    def _get_company_data(self, company=None):
        """Obtiene datos de la empresa para reportes."""
        company = company or self.env.company
        return {
            'name': company.name,
            'vat': company.vat,
            'nit': company.vat,
            'phone': company.phone,
            'email': company.email,
            'street': company.street,
            'city': company.city,
            'state': company.state_id.name if company.state_id else '',
            'country': company.country_id.name if company.country_id else '',
        }

    def _get_month_name(self, month_number):
        """Obtiene el nombre del mes en español."""
        from .hr_payslip_constants import get_month_name
        return get_month_name(month_number)

    def _format_period(self, year, month, quincena='0'):
        """Formatea el periodo para mostrar en reportes."""
        mes = self._get_month_name(month)
        if quincena == '0':
            return f"{mes} {year}"
        return f"{'Q1' if quincena == '1' else 'Q2'} {mes} {year}"

    def _add_explanatory_notes(self, worksheet, row, format_title, format_text, width):
        """Agrega notas explicativas al reporte"""
        # Título de la sección
        worksheet.merge_range(f'A{row}:{width}{row}', 'NOTAS EXPLICATIVAS SOBRE EL CÁLCULO DE RETENCIÓN', format_title)
        row += 1
        
        # Notas explicativas
        notes = [
            ('1. Base Legal:', 'La retención en la fuente se calcula según los artículos 383 a 389 del Estatuto Tributario y la Ley 2277 de 2022.'),
            ('2. Límite Global 40%:', 'La suma de deducciones y rentas exentas no puede exceder el 40% del ingreso neto, con un límite máximo de 1.340 UVT anuales.'),
            ('3. Rentas Exentas:', 'Los aportes voluntarios a pensión y AFC están limitados al 30% del ingreso y 3.800 UVT anuales.'),
            ('4. Renta Exenta 25%:', 'La renta exenta del 25% está limitada a 790 UVT anuales.'),
            ('5. Proyección:', 'En primera quincena, se proyecta el ingreso mensual para calcular la retención, aplicando solo el 50% del valor calculado.'),
            ('6. Depuración:', 'El proceso de depuración sigue el siguiente orden: ingresos, ingresos no constitutivos de renta, deducciones, rentas exentas, límite 40%, base gravable y aplicación de tarifa.'),
            ('7. UVT:', f'Valor UVT para el año fiscal: Revisar el valor en cada registro (columna UVT).')
        ]
        
        # Escribir cada nota
        for title, content in notes:
            worksheet.merge_range(f'A{row}:B{row}', title, format_text)
            worksheet.merge_range(f'C{row}:{width}{row}', content, format_text)
            row += 1
        
        return row + 1  # Retornar la siguiente fila disponible
    
    def action_export_standard(self):
        if not self:
            raise models.UserError('No hay registros seleccionados para exportar.')
            
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        
        title_format = workbook.add_format({
            'bold': True, 'font_size': 14, 'align': 'center', 
            'valign': 'vcenter', 'bg_color': '#1E6C93', 'font_color': 'white'
        })
        header_format = workbook.add_format({
            'bold': True, 'font_size': 11, 'align': 'center', 
            'valign': 'vcenter', 'bg_color': '#D9EDF7', 'border': 1
        })
        subheader_format = workbook.add_format({
            'bold': True, 'font_size': 10, 'align': 'left', 
            'valign': 'vcenter', 'bg_color': '#F5F5F5', 'border': 1
        })
        section_format = workbook.add_format({
            'bold': True, 'font_size': 12, 'align': 'left', 
            'valign': 'vcenter', 'bg_color': '#E6F3F8', 'border': 1
        })
        cell_format = workbook.add_format({
            'font_size': 10, 'align': 'left', 'border': 1
        })
        number_format = workbook.add_format({
            'font_size': 10, 'align': 'right', 'border': 1,
            'num_format': '#,##0.00'
        })
        money_format = workbook.add_format({
            'font_size': 10, 'align': 'right', 'border': 1,
            'num_format': '$#,##0.00'
        })
        percent_format = workbook.add_format({
            'font_size': 10, 'align': 'right', 'border': 1,
            'num_format': '0.00%'
        })
        total_format = workbook.add_format({
            'bold': True, 'font_size': 11, 'align': 'right', 'border': 1,
            'num_format': '$#,##0.00', 'bg_color': '#F5F5F5'
        })
        company_format = workbook.add_format({
            'bold': True, 'font_size': 12, 'align': 'left',
            'valign': 'vcenter'
        })
        date_format = workbook.add_format({
            'font_size': 10, 'align': 'center', 'border': 1,
            'num_format': 'dd/mm/yyyy'
        })
        note_title_format = workbook.add_format({
            'bold': True, 'font_size': 11, 'align': 'left',
            'bg_color': '#FCF8E3', 'border': 1
        })
        note_text_format = workbook.add_format({
            'font_size': 10, 'align': 'left', 'border': 1,
            'text_wrap': True
        })
        
        company_data = self._get_company_data()
        
        worksheet = workbook.add_worksheet('Retenciones')
        
        worksheet.set_column('A:A', 30)
        worksheet.set_column('B:Z', 15)
        
        worksheet.merge_range('A1:H1', company_data['name'], company_format)
        worksheet.merge_range('A2:H2', f"NIT: {company_data['vat']}", cell_format)
        worksheet.merge_range('A3:H3', f"Teléfono: {company_data['phone']} - Email: {company_data['email']}", cell_format)
        worksheet.merge_range('A4:H4', f"Dirección: {company_data['street']}, {company_data['city']}, {company_data['country']}", cell_format)
        current_date = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        worksheet.merge_range('A6:H6', 'REPORTE COMPLETO DE RETENCIÓN EN LA FUENTE', title_format)
        worksheet.merge_range('A7:H7', f"Fecha generación: {current_date}", cell_format)
        worksheet.merge_range('A8:H8', f"Total registros: {len(self)}", cell_format)
        worksheet.merge_range('A9:H9', f"Total empleados: {len(self.mapped('employee_id'))}", cell_format)
        
        row = 11
        all_fields_headers = [
            'Empleado', 'Documento', 'Periodo', 'UVT', '¿Proyectado?',
            'Salario', 'Comisiones', 'Dev. Salarial', 'Dev. No Salarial', 'Total Ingresos',
            'Pensión Total', 'Salud', 'Total Aportes', 
            'Vivienda', 'Dependientes', 'Salud Prep.', 'Total Deducciones',
            'AVP/AFC', 'Renta Ex. 25%', 'Total Rentas Exentas',
            'Subtotal 1', 'Subtotal 2', 'Beneficios Limit.', 
            'Base Gravable', 'Base UVTs', 'Tasa %', 'Retención'
        ]
        
        for col, header in enumerate(all_fields_headers):
            worksheet.write(row, col, header, header_format)
        
        row += 1
        
        for record in self:
            periodo = self._format_period(record.year, record.month, record.quincena)
            
            col = 0
            worksheet.write(row, col, record.employee_id.name, cell_format); col += 1
            worksheet.write(row, col, record.employee_id.identification_id, cell_format); col += 1
            worksheet.write(row, col, periodo, cell_format); col += 1
            worksheet.write(row, col, record.uvt_valor, number_format); col += 1
            worksheet.write(row, col, "Sí" if record.es_proyectado else "No", cell_format); col += 1
            
            worksheet.write(row, col, record.salario_basico, money_format); col += 1
            worksheet.write(row, col, record.comisiones, money_format); col += 1
            worksheet.write(row, col, record.dev_salarial, money_format); col += 1
            worksheet.write(row, col, record.dev_no_salarial, money_format); col += 1
            worksheet.write(row, col, record.total_ingresos, money_format); col += 1
            
            worksheet.write(row, col, record.pension_total, money_format); col += 1
            worksheet.write(row, col, record.salud, money_format); col += 1
            worksheet.write(row, col, record.total_aportes, money_format); col += 1
            
            worksheet.write(row, col, record.ded_vivienda, money_format); col += 1
            worksheet.write(row, col, record.ded_dependientes, money_format); col += 1
            worksheet.write(row, col, record.ded_salud, money_format); col += 1
            worksheet.write(row, col, record.total_deducciones, money_format); col += 1
            
            worksheet.write(row, col, record.valor_avp_afc, money_format); col += 1
            worksheet.write(row, col, record.renta_exenta_25, money_format); col += 1
            worksheet.write(row, col, record.total_rentas_exentas, money_format); col += 1
            
            worksheet.write(row, col, record.subtotal_ibr1, money_format); col += 1
            worksheet.write(row, col, record.subtotal_ibr2, money_format); col += 1
            worksheet.write(row, col, record.beneficios_limitados, money_format); col += 1
            
            worksheet.write(row, col, record.base_gravable, money_format); col += 1
            worksheet.write(row, col, record.ibr_uvts, number_format); col += 1
            worksheet.write(row, col, record.tasa_aplicada / 100, percent_format); col += 1
            worksheet.write(row, col, record.retencion_aplicada, money_format); col += 1
            
            row += 1
        
        col = 0
        worksheet.write(row, col, 'TOTALES', subheader_format); col += 1
        worksheet.write(row, col, '', subheader_format); col += 1
        worksheet.write(row, col, '', subheader_format); col += 1
        worksheet.write(row, col, '', subheader_format); col += 1
        worksheet.write(row, col, '', subheader_format); col += 1
        
        worksheet.write(row, col, sum(r.salario_basico for r in self), total_format); col += 1
        worksheet.write(row, col, sum(r.comisiones for r in self), total_format); col += 1
        worksheet.write(row, col, sum(r.dev_salarial for r in self), total_format); col += 1
        worksheet.write(row, col, sum(r.dev_no_salarial for r in self), total_format); col += 1
        worksheet.write(row, col, sum(r.total_ingresos for r in self), total_format); col += 1
        
        worksheet.write(row, col, sum(r.pension_total for r in self), total_format); col += 1
        worksheet.write(row, col, sum(r.salud for r in self), total_format); col += 1
        worksheet.write(row, col, sum(r.total_aportes for r in self), total_format); col += 1
        
        worksheet.write(row, col, sum(r.ded_vivienda for r in self), total_format); col += 1
        worksheet.write(row, col, sum(r.ded_dependientes for r in self), total_format); col += 1
        worksheet.write(row, col, sum(r.ded_salud for r in self), total_format); col += 1
        worksheet.write(row, col, sum(r.total_deducciones for r in self), total_format); col += 1
        
        worksheet.write(row, col, sum(r.valor_avp_afc for r in self), total_format); col += 1
        worksheet.write(row, col, sum(r.renta_exenta_25 for r in self), total_format); col += 1
        worksheet.write(row, col, sum(r.total_rentas_exentas for r in self), total_format); col += 1
        
        worksheet.write(row, col, sum(r.subtotal_ibr1 for r in self), total_format); col += 1
        worksheet.write(row, col, sum(r.subtotal_ibr2 for r in self), total_format); col += 1
        worksheet.write(row, col, sum(r.beneficios_limitados for r in self), total_format); col += 1
        
        worksheet.write(row, col, sum(r.base_gravable for r in self), total_format); col += 1
        worksheet.write(row, col, '', subheader_format); col += 1
        worksheet.write(row, col, '', subheader_format); col += 1
        worksheet.write(row, col, sum(r.retencion_aplicada for r in self), total_format); col += 1
        
        row += 2
        final_row = self._add_explanatory_notes(worksheet, row, note_title_format, note_text_format, 'AB')
        
        process_sheet = workbook.add_worksheet('Estadísticas')
        process_sheet.set_column('A:A', 25)
        process_sheet.set_column('B:E', 15)
        
        process_sheet.merge_range('A1:E1', 'ESTADÍSTICAS DE RETENCIÓN EN LA FUENTE', title_format)
        
        row = 3
        process_sheet.merge_range(f'A{row}:E{row}', 'Estadísticas por Proyección', section_format)
        row += 1
        
        for col, header in enumerate(['Tipo', 'Cantidad', 'Promedio Base', 'Promedio Retención', 'Total Retención']):
            process_sheet.write(row, col, header, header_format)
        row += 1
        
        proyectados = self.filtered(lambda r: r.es_proyectado)
        no_proyectados = self.filtered(lambda r: not r.es_proyectado)
        
        if proyectados:
            process_sheet.write(row, 0, 'Proyectados', cell_format)
            process_sheet.write(row, 1, len(proyectados), number_format)
            process_sheet.write(row, 2, sum(r.base_gravable for r in proyectados) / len(proyectados), money_format)
            process_sheet.write(row, 3, sum(r.retencion_aplicada for r in proyectados) / len(proyectados), money_format)
            process_sheet.write(row, 4, sum(r.retencion_aplicada for r in proyectados), money_format)
            row += 1
        
        if no_proyectados:
            process_sheet.write(row, 0, 'No Proyectados', cell_format)
            process_sheet.write(row, 1, len(no_proyectados), number_format)
            process_sheet.write(row, 2, sum(r.base_gravable for r in no_proyectados) / len(no_proyectados), money_format)
            process_sheet.write(row, 3, sum(r.retencion_aplicada for r in no_proyectados) / len(no_proyectados), money_format)
            process_sheet.write(row, 4, sum(r.retencion_aplicada for r in no_proyectados), money_format)
            row += 1
        
        process_sheet.write(row, 0, 'Total', subheader_format)
        process_sheet.write(row, 1, len(self), number_format)
        process_sheet.write(row, 2, sum(r.base_gravable for r in self) / len(self), money_format)
        process_sheet.write(row, 3, sum(r.retencion_aplicada for r in self) / len(self), money_format)
        process_sheet.write(row, 4, sum(r.retencion_aplicada for r in self), money_format)
        row += 2
        
        row += 1
        process_sheet.merge_range(f'A{row}:E{row}', 'Estadísticas por Quincena', section_format)
        row += 1
        
        for col, header in enumerate(['Tipo', 'Cantidad', 'Promedio Base', 'Promedio Retención', 'Total Retención']):
            process_sheet.write(row, col, header, header_format)
        row += 1
        
        for quincena, nombre in [('1', 'Primera Quincena'), ('2', 'Segunda Quincena'), ('0', 'Mensual')]:
            records = self.filtered(lambda r: r.quincena == quincena)
            if records:
                process_sheet.write(row, 0, nombre, cell_format)
                process_sheet.write(row, 1, len(records), number_format)
                process_sheet.write(row, 2, sum(r.base_gravable for r in records) / len(records), money_format)
                process_sheet.write(row, 3, sum(r.retencion_aplicada for r in records) / len(records), money_format)
                process_sheet.write(row, 4, sum(r.retencion_aplicada for r in records), money_format)
                row += 1
        
        row += 2
        process_sheet.merge_range(f'A{row}:E{row}', 'Estadísticas por Mes', section_format)
        row += 1
        
        for col, header in enumerate(['Mes', 'Cantidad', 'Base Promedio', 'Retención Promedio', 'Total Retención']):
            process_sheet.write(row, col, header, header_format)
        row += 1
        
        month_groups = {}
        for record in self:
            month_key = (record.year, record.month)
            if month_key not in month_groups:
                month_groups[month_key] = []
            month_groups[month_key].append(record)
        
        for month_key, records in sorted(month_groups.items()):
            year, month = month_key
            month_name = f"{self._get_month_name(month)} {year}"
            
            process_sheet.write(row, 0, month_name, cell_format)
            process_sheet.write(row, 1, len(records), number_format)
            process_sheet.write(row, 2, sum(r.base_gravable for r in records) / len(records), money_format)
            process_sheet.write(row, 3, sum(r.retencion_aplicada for r in records) / len(records), money_format)
            process_sheet.write(row, 4, sum(r.retencion_aplicada for r in records), money_format)
            row += 1
        
        # Cerrar el libro
        workbook.close()
        
        # Guardar archivo
        xlsx_data = output.getvalue()
        filename = f"Retenciones_Completo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        # Guardar el primer registro para descargar
        self[0].write({
            'excel_file': base64.b64encode(xlsx_data),
            'excel_filename': filename
        })
        
        # Devolver acción para descargar
        return {
            'type': 'ir.actions.act_url',
            'url': f"web/content/?model={self._name}&id={self[0].id}&field=excel_file&download=true&filename={filename}",
            'target': 'self',
        }
    
    def action_export_by_employee(self):
        """Exporta registros seleccionados agrupados por empleado"""
        if not self:
            raise models.UserError('No hay registros seleccionados para exportar.')
            
        # Preparar archivo Excel
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        
        # Estilos (mismos que en la función anterior)
        title_format = workbook.add_format({
            'bold': True, 'font_size': 14, 'align': 'center', 
            'valign': 'vcenter', 'bg_color': '#1E6C93', 'font_color': 'white'
        })
        header_format = workbook.add_format({
            'bold': True, 'font_size': 11, 'align': 'center', 
            'valign': 'vcenter', 'bg_color': '#D9EDF7', 'border': 1
        })
        subheader_format = workbook.add_format({
            'bold': True, 'font_size': 10, 'align': 'left', 
            'valign': 'vcenter', 'bg_color': '#F5F5F5', 'border': 1
        })
        cell_format = workbook.add_format({
            'font_size': 10, 'align': 'left', 'border': 1
        })
        number_format = workbook.add_format({
            'font_size': 10, 'align': 'right', 'border': 1,
            'num_format': '#,##0.00'
        })
        money_format = workbook.add_format({
            'font_size': 10, 'align': 'right', 'border': 1,
            'num_format': '$#,##0.00'
        })
        percent_format = workbook.add_format({
            'font_size': 10, 'align': 'right', 'border': 1,
            'num_format': '0.00%'
        })
        total_format = workbook.add_format({
            'bold': True, 'font_size': 11, 'align': 'right', 'border': 1,
            'num_format': '$#,##0.00', 'bg_color': '#F5F5F5'
        })
        company_format = workbook.add_format({
            'bold': True, 'font_size': 12, 'align': 'left',
            'valign': 'vcenter'
        })
        date_format = workbook.add_format({
            'font_size': 10, 'align': 'center', 'border': 1,
            'num_format': 'dd/mm/yyyy'
        })
        employee_format = workbook.add_format({
            'bold': True, 'font_size': 12, 'align': 'left',
            'valign': 'vcenter', 'bg_color': '#E6F3F8'
        })
        info_format = workbook.add_format({
            'font_size': 10, 'align': 'left', 'bg_color': '#FCF8E3',
            'border': 1, 'text_wrap': True
        })
        note_title_format = workbook.add_format({
            'bold': True, 'font_size': 11, 'align': 'left',
            'bg_color': '#FCF8E3', 'border': 1
        })
        note_text_format = workbook.add_format({
            'font_size': 10, 'align': 'left', 'border': 1,
            'text_wrap': True
        })
        section_format = workbook.add_format({
            'bold': True, 'font_size': 12, 'align': 'left', 
            'valign': 'vcenter', 'bg_color': '#E6F3F8', 'border': 1
        })
        
        company_data = self._get_company_data()
        
        worksheet = workbook.add_worksheet('Por Empleado')
        
        worksheet.set_column('A:A', 30)
        worksheet.set_column('B:Z', 15)
        
        worksheet.merge_range('A1:P1', company_data['name'], company_format)
        worksheet.merge_range('A2:P2', f"NIT: {company_data['vat']}", cell_format)
        worksheet.merge_range('A3:P3', f"Teléfono: {company_data['phone']} - Email: {company_data['email']}", cell_format)
        worksheet.merge_range('A4:P4', f"Dirección: {company_data['street']}, {company_data['city']}, {company_data['country']}", cell_format)
        
        current_date = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        worksheet.merge_range('A6:P6', 'REPORTE DE RETENCIÓN EN LA FUENTE POR EMPLEADO', title_format)
        worksheet.merge_range('A7:P7', f"Fecha generación: {current_date}", cell_format)
        worksheet.merge_range('A8:P8', f"Total registros: {len(self)}", cell_format)
        worksheet.merge_range('A9:P9', f"Total empleados: {len(self.mapped('employee_id'))}", cell_format)
        
        employee_groups = {}
        for record in self:
            if record.employee_id not in employee_groups:
                employee_groups[record.employee_id] = []
            employee_groups[record.employee_id].append(record)
        
        headers = [
            'Periodo', 'UVT', 'Salario', 'Total Ing.', 'Total Aportes', 
            'Total Ded.', 'AVP/AFC', 'Renta Ex. 25%', 'Beneficios Lim.', 
            'Base Grav.', 'Base UVTs', 'Tasa %', 'Retención'
        ]
        
        row = 11
        grand_total_retention = 0
        
        for employee, records in sorted(employee_groups.items(), key=lambda x: x[0].name):
            worksheet.merge_range(f'A{row}:P{row}', f"Empleado: {employee.name} - Documento: {employee.identification_id}", employee_format)
            row += 1
            
            worksheet.merge_range(f'A{row}:P{row}', f"Se encontraron {len(records)} registros de retención en la fuente.", info_format)
            row += 1
            
            row += 1
            for col, header in enumerate(headers):
                worksheet.write(row, col, header, header_format)
            row += 1
            
            employee_total_salary = 0
            employee_total_income = 0
            employee_total_contrib = 0
            employee_total_deductions = 0
            employee_total_avp_afc = 0
            employee_total_exenta_25 = 0
            employee_total_benefits = 0
            employee_total_base = 0
            employee_total_retention = 0
            
            for record in sorted(records, key=lambda r: (r.year, r.month, r.quincena)):
                periodo = self._format_period(record.year, record.month, record.quincena)
                
                col = 0
                worksheet.write(row, col, periodo, cell_format); col += 1
                worksheet.write(row, col, record.uvt_valor, number_format); col += 1
                worksheet.write(row, col, record.salario_basico, money_format); col += 1
                worksheet.write(row, col, record.total_ingresos, money_format); col += 1
                worksheet.write(row, col, record.total_aportes, money_format); col += 1
                worksheet.write(row, col, record.total_deducciones, money_format); col += 1
                worksheet.write(row, col, record.valor_avp_afc, money_format); col += 1
                worksheet.write(row, col, record.renta_exenta_25, money_format); col += 1
                worksheet.write(row, col, record.beneficios_limitados, money_format); col += 1
                worksheet.write(row, col, record.base_gravable, money_format); col += 1
                worksheet.write(row, col, record.ibr_uvts, number_format); col += 1
                worksheet.write(row, col, record.tasa_aplicada / 100, percent_format); col += 1
                worksheet.write(row, col, record.retencion_aplicada, money_format); col += 1
                
                employee_total_salary += record.salario_basico
                employee_total_income += record.total_ingresos
                employee_total_contrib += record.total_aportes
                employee_total_deductions += record.total_deducciones
                employee_total_avp_afc += record.valor_avp_afc
                employee_total_exenta_25 += record.renta_exenta_25
                employee_total_benefits += record.beneficios_limitados
                employee_total_base += record.base_gravable
                employee_total_retention += record.retencion_aplicada
                
                row += 1
            
            col = 0
            worksheet.write(row, col, 'SUBTOTAL', subheader_format); col += 1
            worksheet.write(row, col, '', subheader_format); col += 1
            worksheet.write(row, col, employee_total_salary, total_format); col += 1
            worksheet.write(row, col, employee_total_income, total_format); col += 1
            worksheet.write(row, col, employee_total_contrib, total_format); col += 1
            worksheet.write(row, col, employee_total_deductions, total_format); col += 1
            worksheet.write(row, col, employee_total_avp_afc, total_format); col += 1
            worksheet.write(row, col, employee_total_exenta_25, total_format); col += 1
            worksheet.write(row, col, employee_total_benefits, total_format); col += 1
            worksheet.write(row, col, employee_total_base, total_format); col += 1
            worksheet.write(row, col, '', subheader_format); col += 1
            worksheet.write(row, col, '', subheader_format); col += 1
            worksheet.write(row, col, employee_total_retention, total_format); col += 1
            
            grand_total_retention += employee_total_retention
            
            row += 2
            worksheet.merge_range(f'A{row}:P{row}', 'Distribución de retenciones por periodo:', section_format)
            row += 1
            
            periodos = {}
            for record in records:
                periodo = self._format_period(record.year, record.month, record.quincena)
                if periodo not in periodos:
                    periodos[periodo] = 0
                periodos[periodo] += record.retencion_aplicada
            
            worksheet.write(row, 0, 'Periodo', header_format)
            worksheet.write(row, 1, 'Retención', header_format)
            worksheet.write(row, 2, 'Porcentaje', header_format)
            row += 1
            
            for periodo, valor in sorted(periodos.items()):
                worksheet.write(row, 0, periodo, cell_format)
                worksheet.write(row, 1, valor, money_format)
                worksheet.write(row, 2, valor / employee_total_retention if employee_total_retention else 0, percent_format)
                row += 1
            
            row += 3
        
        # Gran total
        worksheet.merge_range(f'A{row}:L{row}', 'GRAN TOTAL RETENCIÓN', subheader_format)
        worksheet.write(row, 12, grand_total_retention, total_format)
        
        row += 2
        final_row = self._add_explanatory_notes(worksheet, row, note_title_format, note_text_format, 'P')
        
        summary_sheet = workbook.add_worksheet('Resumen Consolidado')
        summary_sheet.set_column('A:A', 30)
        summary_sheet.set_column('B:Z', 15)
        
        summary_sheet.merge_range('A1:K1', company_data['name'], company_format)
        summary_sheet.merge_range('A2:K2', 'RESUMEN CONSOLIDADO DE RETENCIÓN EN LA FUENTE', title_format)
        summary_sheet.merge_range('A3:K3', f"Fecha generación: {current_date}", cell_format)
        
        # Sección de análisis
        summary_row = 5
        summary_sheet.merge_range(f'A{summary_row}:K{summary_row}', 'ANÁLISIS CONSOLIDADO POR EMPLEADO', section_format)
        summary_row += 1
        
        # Encabezados consolidados
        summary_headers = [
            'Empleado', 'Documento', 'Total Registros', 'Salario', 'Ingresos', 
            'Deducciones', 'Rentas Exentas', 'Base Gravable', 'Retención', '% del Total'
        ]
        
        for col, header in enumerate(summary_headers):
            summary_sheet.write(summary_row, col, header, header_format)
        summary_row += 1
        
        # Datos consolidados
        grand_totals = {
            'registros': 0,
            'salario': 0,
            'ingresos': 0,
            'deducciones': 0,
            'rentas_exentas': 0,
            'base': 0,
            'retencion': 0
        }
        
        for employee, records in sorted(employee_groups.items(), key=lambda x: x[0].name):
            # Calcular totales por empleado
            total_registros = len(records)
            total_salario = sum(r.salario_basico for r in records)
            total_ingresos = sum(r.total_ingresos for r in records)
            total_deducciones = sum(r.total_deducciones for r in records)
            total_rentas = sum(r.total_rentas_exentas for r in records)
            total_base = sum(r.base_gravable for r in records)
            total_retencion = sum(r.retencion_aplicada for r in records)
            
            # Actualizar totales generales
            grand_totals['registros'] += total_registros
            grand_totals['salario'] += total_salario
            grand_totals['ingresos'] += total_ingresos
            grand_totals['deducciones'] += total_deducciones
            grand_totals['rentas_exentas'] += total_rentas
            grand_totals['base'] += total_base
            grand_totals['retencion'] += total_retencion
            
            # Escribir datos
            col = 0
            summary_sheet.write(summary_row, col, employee.name, cell_format); col += 1
            summary_sheet.write(summary_row, col, employee.identification_id, cell_format); col += 1
            summary_sheet.write(summary_row, col, total_registros, number_format); col += 1
            summary_sheet.write(summary_row, col, total_salario, money_format); col += 1
            summary_sheet.write(summary_row, col, total_ingresos, money_format); col += 1
            summary_sheet.write(summary_row, col, total_deducciones, money_format); col += 1
            summary_sheet.write(summary_row, col, total_rentas, money_format); col += 1
            summary_sheet.write(summary_row, col, total_base, money_format); col += 1
            summary_sheet.write(summary_row, col, total_retencion, money_format); col += 1
            summary_sheet.write(summary_row, col, total_retencion / grand_totals['retencion'] if grand_totals['retencion'] else 0, percent_format); col += 1
            
            summary_row += 1
        
        # Totales generales
        col = 0
        summary_sheet.write(summary_row, col, 'TOTAL GENERAL', subheader_format); col += 1
        summary_sheet.write(summary_row, col, '', subheader_format); col += 1
        summary_sheet.write(summary_row, col, grand_totals['registros'], number_format); col += 1
        summary_sheet.write(summary_row, col, grand_totals['salario'], total_format); col += 1
        summary_sheet.write(summary_row, col, grand_totals['ingresos'], total_format); col += 1
        summary_sheet.write(summary_row, col, grand_totals['deducciones'], total_format); col += 1
        summary_sheet.write(summary_row, col, grand_totals['rentas_exentas'], total_format); col += 1
        summary_sheet.write(summary_row, col, grand_totals['base'], total_format); col += 1
        summary_sheet.write(summary_row, col, grand_totals['retencion'], total_format); col += 1
        summary_sheet.write(summary_row, col, 1.0, percent_format); col += 1
        
        # Sección de análisis por año/mes
        summary_row += 3
        summary_sheet.merge_range(f'A{summary_row}:K{summary_row}', 'ANÁLISIS POR AÑO Y MES', section_format)
        summary_row += 1
        
        # Encabezados por año/mes
        year_month_headers = [
            'Año', 'Mes', 'Total Registros', 'Salario', 'Ingresos', 
            'Deducciones', 'Rentas Exentas', 'Base Gravable', 'Retención', 'Tasa Efectiva'
        ]
        
        for col, header in enumerate(year_month_headers):
            summary_sheet.write(summary_row, col, header, header_format)
        summary_row += 1
        
        # Agrupar por año/mes
        year_month_groups = {}
        for record in self:
            key = (record.year, record.month)
            if key not in year_month_groups:
                year_month_groups[key] = []
            year_month_groups[key].append(record)
        
        # Datos por año/mes
        for key, records in sorted(year_month_groups.items()):
            year, month = key
            month_name = self._get_month_name(month)
            
            # Calcular totales
            total_registros = len(records)
            total_salario = sum(r.salario_basico for r in records)
            total_ingresos = sum(r.total_ingresos for r in records)
            total_deducciones = sum(r.total_deducciones for r in records)
            total_rentas = sum(r.total_rentas_exentas for r in records)
            total_base = sum(r.base_gravable for r in records)
            total_retencion = sum(r.retencion_aplicada for r in records)
            tasa_efectiva = total_retencion / total_base if total_base else 0
            
            # Escribir datos
            col = 0
            summary_sheet.write(summary_row, col, year, cell_format); col += 1
            summary_sheet.write(summary_row, col, month_name, cell_format); col += 1
            summary_sheet.write(summary_row, col, total_registros, number_format); col += 1
            summary_sheet.write(summary_row, col, total_salario, money_format); col += 1
            summary_sheet.write(summary_row, col, total_ingresos, money_format); col += 1
            summary_sheet.write(summary_row, col, total_deducciones, money_format); col += 1
            summary_sheet.write(summary_row, col, total_rentas, money_format); col += 1
            summary_sheet.write(summary_row, col, total_base, money_format); col += 1
            summary_sheet.write(summary_row, col, total_retencion, money_format); col += 1
            summary_sheet.write(summary_row, col, tasa_efectiva, percent_format); col += 1
            
            summary_row += 1
        
        # Cerrar el libro
        workbook.close()
        
        # Guardar archivo
        xlsx_data = output.getvalue()
        filename = f"Retenciones_por_Empleado_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        # Guardar el primer registro para descargar
        self[0].write({
            'excel_file': base64.b64encode(xlsx_data),
            'excel_filename': filename
        })
        
        # Devolver acción para descargar
        return {
            'type': 'ir.actions.act_url',
            'url': f"web/content/?model={self._name}&id={self[0].id}&field=excel_file&download=true&filename={filename}",
            'target': 'self',
        }
    
    def action_export_detailed(self):
        """Exporta registros seleccionados con detalles en múltiples hojas"""
        if not self:
            raise models.UserError('No hay registros seleccionados para exportar.')
            
        # Preparar archivo Excel
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        
        # Estilos (mismos que en funciones anteriores)
        title_format = workbook.add_format({
            'bold': True, 'font_size': 14, 'align': 'center', 
            'valign': 'vcenter', 'bg_color': '#1E6C93', 'font_color': 'white'
        })
        header_format = workbook.add_format({
            'bold': True, 'font_size': 11, 'align': 'center', 
            'valign': 'vcenter', 'bg_color': '#D9EDF7', 'border': 1
        })
        subheader_format = workbook.add_format({
            'bold': True, 'font_size': 10, 'align': 'left', 
            'valign': 'vcenter', 'bg_color': '#F5F5F5', 'border': 1
        })
        cell_format = workbook.add_format({
            'font_size': 10, 'align': 'left', 'border': 1
        })
        number_format = workbook.add_format({
            'font_size': 10, 'align': 'right', 'border': 1,
            'num_format': '#,##0.00'
        })
        money_format = workbook.add_format({
            'font_size': 10, 'align': 'right', 'border': 1,
            'num_format': '$#,##0.00'
        })
        percent_format = workbook.add_format({
            'font_size': 10, 'align': 'right', 'border': 1,
            'num_format': '0.00%'
        })
        total_format = workbook.add_format({
            'bold': True, 'font_size': 11, 'align': 'right', 'border': 1,
            'num_format': '$#,##0.00', 'bg_color': '#F5F5F5'
        })
        company_format = workbook.add_format({
            'bold': True, 'font_size': 12, 'align': 'left',
            'valign': 'vcenter'
        })
        date_format = workbook.add_format({
            'font_size': 10, 'align': 'center', 'border': 1,
            'num_format': 'dd/mm/yyyy'
        })
        section_format = workbook.add_format({
            'bold': True, 'font_size': 12, 'align': 'left', 
            'valign': 'vcenter', 'bg_color': '#E6F3F8', 'border': 1
        })
        note_title_format = workbook.add_format({
            'bold': True, 'font_size': 11, 'align': 'left',
            'bg_color': '#FCF8E3', 'border': 1
        })
        note_text_format = workbook.add_format({
            'font_size': 10, 'align': 'left', 'border': 1,
            'text_wrap': True
        })
        calculation_format = workbook.add_format({
            'font_size': 10, 'align': 'left', 'bg_color': '#F0F0F0',
            'border': 1, 'text_wrap': True
        })
        
        # Obtener datos de la empresa
        company_data = self._get_company_data()
        
        #----------------------------------------------------------------------------------
        # HOJA 1: RESUMEN GENERAL
        #----------------------------------------------------------------------------------
        worksheet = workbook.add_worksheet('Resumen General')
        worksheet.set_column('A:A', 30)
        worksheet.set_column('B:Z', 15)
        
        # Encabezado
        worksheet.merge_range('A1:I1', company_data['name'], company_format)
        worksheet.merge_range('A2:I2', f"NIT: {company_data['vat']}", cell_format)
        worksheet.merge_range('A3:I3', f"Teléfono: {company_data['phone']} - Email: {company_data['email']}", cell_format)
        worksheet.merge_range('A4:I4', f"Dirección: {company_data['street']}, {company_data['city']}, {company_data['country']}", cell_format)
        
        # Información del reporte
        current_date = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        worksheet.merge_range('A6:I6', 'REPORTE DETALLADO DE RETENCIÓN EN LA FUENTE', title_format)
        worksheet.merge_range('A7:I7', f"Fecha generación: {current_date}", cell_format)
        worksheet.merge_range('A8:I8', f"Total registros: {len(self)}", cell_format)
        worksheet.merge_range('A9:I9', f"Total empleados: {len(self.mapped('employee_id'))}", cell_format)
        
        # Resumen de causas de retención (explicar el proceso)
        row = 11
        worksheet.merge_range(f'A{row}:I{row}', 'PROCESO DE CÁLCULO DE RETENCIÓN EN LA FUENTE', section_format)
        row += 1
        
        calculation_steps = [
            ("1. Ingresos Laborales", "Se suman todos los ingresos laborales del empleado: salario básico, comisiones, devengos salariales y no salariales."),
            ("2. Ingresos No Constitutivos", "Se restan los aportes obligatorios a pensión y salud, que no constituyen renta."),
            ("3. Ingreso Neto", "Se obtiene el ingreso neto: Total Ingresos - Ingresos No Constitutivos."),
            ("4. Deducciones", "Se aplican deducciones por vivienda, dependientes y salud prepagada, con sus respectivos límites."),
            ("5. Rentas Exentas", "Se aplican los aportes a AVP/AFC y la renta exenta del 25% sobre el resto de ingresos."),
            ("6. Límite Global 40%", "Se verifica que la suma de deducciones y rentas exentas no supere el 40% del ingreso neto ni 1.340 UVT anuales."),
            ("7. Base Gravable", "Se calcula la base gravable: Ingreso Neto - Beneficios Limitados."),
            ("8. Aplicación de Tarifa", "Se convierte la base a UVTs y se aplica la tarifa del Art. 383 ET."),
            ("9. Retención Final", "En caso de proyección (primera quincena), se aplica solo el 50% de la retención calculada.")
        ]
        
        for step, explanation in calculation_steps:
            worksheet.write(row, 0, step, subheader_format)
            worksheet.merge_range(f'B{row}:I{row}', explanation, calculation_format)
            row += 1
        
        # Tabla de resumen general
        row += 2
        worksheet.merge_range(f'A{row}:I{row}', 'RESUMEN GENERAL POR PERIODO', section_format)
        row += 1
        
        # Encabezados
        headers = [
            'Periodo', 'Cant. Registros', 'Total Ingresos', 'Aportes', 'Deducciones', 
            'Rentas Exentas', 'Base Gravable', 'Retención', 'Tasa Efectiva'
        ]
        
        for col, header in enumerate(headers):
            worksheet.write(row, col, header, header_format)
        row += 1
        
        # Agrupar por periodo (año, mes, quincena)
        period_groups = {}
        for record in self:
            period_key = (record.year, record.month, record.quincena)
            if period_key not in period_groups:
                period_groups[period_key] = []
            period_groups[period_key].append(record)
        
        # Datos por periodo
        grand_totals = {
            'records': 0,
            'income': 0, 
            'contrib': 0,
            'deductions': 0, 
            'exempt': 0,
            'base': 0, 
            'retention': 0
        }
        
        for period_key, records in sorted(period_groups.items()):
            year, month, quincena = period_key
            
            # Formatear periodo
            periodo = self._format_period(year, month, quincena)
            
            # Calcular totales para este periodo
            total_income = sum(r.total_ingresos for r in records)
            total_contrib = sum(r.total_aportes for r in records)
            total_deductions = sum(r.total_deducciones for r in records)
            total_exempt = sum(r.total_rentas_exentas for r in records)
            total_base = sum(r.base_gravable for r in records)
            total_retention = sum(r.retencion_aplicada for r in records)
            tasa_efectiva = total_retention / total_base if total_base else 0
            
            # Escribir datos
            worksheet.write(row, 0, periodo, cell_format)
            worksheet.write(row, 1, len(records), number_format)
            worksheet.write(row, 2, total_income, money_format)
            worksheet.write(row, 3, total_contrib, money_format)
            worksheet.write(row, 4, total_deductions, money_format)
            worksheet.write(row, 5, total_exempt, money_format)
            worksheet.write(row, 6, total_base, money_format)
            worksheet.write(row, 7, total_retention, money_format)
            worksheet.write(row, 8, tasa_efectiva, percent_format)
            
            # Actualizar totales generales
            grand_totals['records'] += len(records)
            grand_totals['income'] += total_income
            grand_totals['contrib'] += total_contrib
            grand_totals['deductions'] += total_deductions
            grand_totals['exempt'] += total_exempt
            grand_totals['base'] += total_base
            grand_totals['retention'] += total_retention
            
            row += 1
        
        # Totales generales
        worksheet.write(row, 0, 'TOTAL GENERAL', subheader_format)
        worksheet.write(row, 1, grand_totals['records'], number_format)
        worksheet.write(row, 2, grand_totals['income'], total_format)
        worksheet.write(row, 3, grand_totals['contrib'], total_format)
        worksheet.write(row, 4, grand_totals['deductions'], total_format)
        worksheet.write(row, 5, grand_totals['exempt'], total_format)
        worksheet.write(row, 6, grand_totals['base'], total_format)
        worksheet.write(row, 7, grand_totals['retention'], total_format)
        worksheet.write(row, 8, grand_totals['retention'] / grand_totals['base'] if grand_totals['base'] else 0, percent_format)
        
        # Agregar notas explicativas
        row += 2
        final_row = self._add_explanatory_notes(worksheet, row, note_title_format, note_text_format, 'I')
        
        #----------------------------------------------------------------------------------
        # HOJA 2: DETALLE POR EMPLEADO
        #----------------------------------------------------------------------------------
        details_sheet = workbook.add_worksheet('Detalle por Empleado')
        details_sheet.set_column('A:A', 30)
        details_sheet.set_column('B:Z', 15)
        
        # Encabezado
        details_sheet.merge_range('A1:M1', 'DETALLE POR EMPLEADO', title_format)
        details_sheet.merge_range('A2:M2', 'Listado completo de todos los registros ordenados por empleado', subheader_format)
        
        # Encabezados
        detail_row = 4
        detail_headers = [
            'Empleado', 'Documento', 'Periodo', 'Salario', 'Comisiones', 'Otros Ingresos',
            'Aportes', 'Deducciones', 'AVP/AFC', 'Renta Ex. 25%', 'Base', 'Retención', 'Tasa'
        ]
        
        for col, header in enumerate(detail_headers):
            details_sheet.write(detail_row, col, header, header_format)
        detail_row += 1
        
        # Datos detallados por empleado
        for record in sorted(self, key=lambda r: (r.employee_id.name, r.year, r.month, r.quincena)):
            # Formatear periodo
            periodo = self._format_period(record.year, record.month, record.quincena)
            otros_ingresos = record.dev_salarial + record.dev_no_salarial
            tasa_aplicada = record.tasa_aplicada / 100 if record.tasa_aplicada else 0
            
            col = 0
            details_sheet.write(detail_row, col, record.employee_id.name, cell_format); col += 1
            details_sheet.write(detail_row, col, record.employee_id.identification_id, cell_format); col += 1
            details_sheet.write(detail_row, col, periodo, cell_format); col += 1
            details_sheet.write(detail_row, col, record.salario_basico, money_format); col += 1
            details_sheet.write(detail_row, col, record.comisiones, money_format); col += 1
            details_sheet.write(detail_row, col, otros_ingresos, money_format); col += 1
            details_sheet.write(detail_row, col, record.total_aportes, money_format); col += 1
            details_sheet.write(detail_row, col, record.total_deducciones, money_format); col += 1
            details_sheet.write(detail_row, col, record.valor_avp_afc, money_format); col += 1
            details_sheet.write(detail_row, col, record.renta_exenta_25, money_format); col += 1
            details_sheet.write(detail_row, col, record.base_gravable, money_format); col += 1
            details_sheet.write(detail_row, col, record.retencion_aplicada, money_format); col += 1
            details_sheet.write(detail_row, col, tasa_aplicada, percent_format); col += 1
            
            detail_row += 1
        
        #----------------------------------------------------------------------------------
        # HOJA 3: CONSOLIDADO ANUAL POR EMPLEADO
        #----------------------------------------------------------------------------------
        annual_sheet = workbook.add_worksheet('Consolidado Anual')
        annual_sheet.set_column('A:A', 30)
        annual_sheet.set_column('B:Z', 15)
        
        # Encabezado
        annual_sheet.merge_range('A1:K1', 'CONSOLIDADO ANUAL POR EMPLEADO', title_format)
        annual_sheet.merge_range('A2:K2', 'Totales anuales por cada empleado', subheader_format)
        
        # Explicación para certificados de retención
        annual_row = 4
        annual_sheet.merge_range(f'A{annual_row}:K{annual_row}', 'NOTA: Esta información puede ser útil para la emisión de certificados de retención en la fuente.', note_title_format)
        annual_row += 2
        
        # Encabezados
        annual_headers = [
            'Empleado', 'Documento', 'Año', 'Total Registros', 'Total Ingresos', 
            'Aportes', 'Deducciones', 'Rentas Exentas', 'Base Gravable', 'Retención', 'Tasa Efectiva'
        ]
        
        for col, header in enumerate(annual_headers):
            annual_sheet.write(annual_row, col, header, header_format)
        annual_row += 1
        
        # Agrupar por empleado y año
        employee_year_groups = {}
        for record in self:
            key = (record.employee_id, record.year)
            if key not in employee_year_groups:
                employee_year_groups[key] = []
            employee_year_groups[key].append(record)
        
        # Datos consolidados por empleado y año
        for key, records in sorted(employee_year_groups.items(), key=lambda x: (x[0], x[1])):
            employee, year = key
            
            # Calcular totales anuales
            annual_income = sum(r.total_ingresos for r in records)
            annual_contrib = sum(r.total_aportes for r in records)
            annual_deductions = sum(r.total_deducciones for r in records)
            annual_exempt = sum(r.total_rentas_exentas for r in records)
            annual_base = sum(r.base_gravable for r in records)
            annual_retention = sum(r.retencion_aplicada for r in records)
            tasa_efectiva = annual_retention / annual_base if annual_base else 0
            
            # Escribir datos
            col = 0
            annual_sheet.write(annual_row, col, employee.name, cell_format); col += 1
            annual_sheet.write(annual_row, col, employee.identification_id, cell_format); col += 1
            annual_sheet.write(annual_row, col, year, cell_format); col += 1
            annual_sheet.write(annual_row, col, len(records), number_format); col += 1
            annual_sheet.write(annual_row, col, annual_income, money_format); col += 1
            annual_sheet.write(annual_row, col, annual_contrib, money_format); col += 1
            annual_sheet.write(annual_row, col, annual_deductions, money_format); col += 1
            annual_sheet.write(annual_row, col, annual_exempt, money_format); col += 1
            annual_sheet.write(annual_row, col, annual_base, money_format); col += 1
            annual_sheet.write(annual_row, col, annual_retention, money_format); col += 1
            annual_sheet.write(annual_row, col, tasa_efectiva, percent_format); col += 1
            
            annual_row += 1
        
        #----------------------------------------------------------------------------------
        # HOJA 4: ANÁLISIS DE BENEFICIOS TRIBUTARIOS
        #----------------------------------------------------------------------------------
        benefits_sheet = workbook.add_worksheet('Beneficios Tributarios')
        benefits_sheet.set_column('A:A', 30)
        benefits_sheet.set_column('B:Z', 15)
        
        # Encabezado
        benefits_sheet.merge_range('A1:I1', 'ANÁLISIS DE BENEFICIOS TRIBUTARIOS', title_format)
        benefits_sheet.merge_range('A2:I2', 'Detalle de deducciones y rentas exentas por empleado y año', subheader_format)
        
        # Encabezados
        benefits_row = 4
        benefits_headers = [
            'Empleado', 'Año', 'Vivienda', 'Dependientes', 'Salud Prepagada', 
            'AVP/AFC', 'Renta Exenta 25%', 'Total Beneficios', 'Beneficios Aplicados'
        ]
        
        for col, header in enumerate(benefits_headers):
            benefits_sheet.write(benefits_row, col, header, header_format)
        benefits_row += 1
        
        # Agrupar por empleado y año para beneficios
        for key, records in sorted(employee_year_groups.items(), key=lambda x: (x[0], x[1])):
            employee, year = key
            
            # Calcular totales de beneficios
            total_vivienda = sum(r.ded_vivienda for r in records)
            total_dependientes = sum(r.ded_dependientes for r in records)
            total_salud = sum(r.ded_salud for r in records)
            total_avp_afc = sum(r.valor_avp_afc for r in records)
            total_renta_25 = sum(r.renta_exenta_25 for r in records)
            total_beneficios = total_vivienda + total_dependientes + total_salud + total_avp_afc + total_renta_25
            total_beneficios_aplicados = sum(r.beneficios_limitados for r in records)
            
            # Escribir datos
            col = 0
            benefits_sheet.write(benefits_row, col, employee.name, cell_format); col += 1
            benefits_sheet.write(benefits_row, col, year, cell_format); col += 1
            benefits_sheet.write(benefits_row, col, total_vivienda, money_format); col += 1
            benefits_sheet.write(benefits_row, col, total_dependientes, money_format); col += 1
            benefits_sheet.write(benefits_row, col, total_salud, money_format); col += 1
            benefits_sheet.write(benefits_row, col, total_avp_afc, money_format); col += 1
            benefits_sheet.write(benefits_row, col, total_renta_25, money_format); col += 1
            benefits_sheet.write(benefits_row, col, total_beneficios, money_format); col += 1
            benefits_sheet.write(benefits_row, col, total_beneficios_aplicados, money_format); col += 1
            
            benefits_row += 1
        
        # Explicación del límite global
        benefits_row += 2
        benefits_sheet.merge_range(f'A{benefits_row}:I{benefits_row}', 'EXPLICACIÓN DEL LÍMITE GLOBAL 40%', note_title_format)
        benefits_row += 1
        
        limite_explanation = (
            "El límite global establece que la suma de deducciones y rentas exentas no puede exceder el 40% del ingreso neto "
            "con un tope máximo de 1.340 UVT anuales (Art. 387 ET y Ley 2277 de 2022). "
            "Si el total de beneficios supera este límite, se aplica una proporción para ajustarlos."
        )
        
        benefits_sheet.merge_range(f'A{benefits_row}:I{benefits_row}', limite_explanation, note_text_format)
        
        # Cerrar el libro
        workbook.close()
        
        # Guardar archivo
        xlsx_data = output.getvalue()
        filename = f"Reporte_Detallado_Retenciones_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        # Guardar el primer registro para descargar
        self[0].write({
            'excel_file': base64.b64encode(xlsx_data),
            'excel_filename': filename
        })
        
        # Devolver acción para descargar
        return {
            'type': 'ir.actions.act_url',
            'url': f"web/content/?model={self._name}&id={self[0].id}&field=excel_file&download=true&filename={filename}",
            'target': 'self',
        }
    @api.depends('employee_id', 'year', 'month', 'quincena')
    def _compute_name(self):
        """Calcula automáticamente un nombre de referencia para el reporte"""
        for record in self:
            if not record.employee_id or not record.year or not record.month:
                record.name = "Reporte sin datos"
                continue

            mes = MONTH_NAMES.get(record.month, f"Mes {record.month}")
            
            if record.quincena == '0':
                periodo = f"{mes} {record.year}"
            else:
                quincena = 'Q1' if record.quincena == '1' else 'Q2'
                periodo = f"{mes} {quincena} {record.year}"
                
            record.name = f"{record.employee_id.name} - {periodo}"