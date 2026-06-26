# -*- coding: utf-8 -*-
"""
Wizard para exportación de reportes contables colombianos.

Permite configurar múltiples opciones de exportación:
- Formato: PDF, Excel (XLSX), CSV, XML
- Niveles de expansión: Todo expandido, por nivel, por tercero
- Colores: Activar/desactivar colores para números
- Logo: Incluir/excluir logo de empresa
- Filtros: Aplicar filtros actuales
- Moneda secundaria: Mostrar valores en moneda secundaria
"""

import io
import json
import base64
import logging
import xlsxwriter
from datetime import datetime

from odoo import api, fields, models, _
from odoo.tools import float_repr
from odoo.tools.misc import format_date

_logger = logging.getLogger(__name__)


class ColombianReportExportWizard(models.TransientModel):
    """Wizard para exportar reportes contables colombianos con múltiples opciones."""

    _name = 'libros.contables.export.wizard'
    _description = 'Wizard de Exportación de Reportes Contables Colombianos'

    # =========================================================================
    # CAMPOS BÁSICOS
    # =========================================================================

    report_id = fields.Many2one(
        'account.report',
        string='Reporte',
        required=True,
        readonly=True,
    )
    report_name = fields.Char(
        string='Nombre del Reporte',
        compute='_compute_report_name',
    )
    report_options = fields.Text(
        string='Opciones del Reporte',
        help='JSON con las opciones actuales del reporte',
    )
    doc_name = fields.Char(
        string='Nombre del Documento',
        help='Nombre base para los archivos exportados',
    )

    # =========================================================================
    # FORMATOS DE EXPORTACIÓN
    # =========================================================================

    export_format = fields.Selection([
        ('pdf', 'PDF'),
        ('xlsx', 'Excel (XLSX)'),
        ('csv', 'CSV'),
        ('xml', 'XML'),
    ], string='Formato', default='xlsx', required=True)

    # =========================================================================
    # OPCIONES DE EXPANSIÓN/NIVELES
    # =========================================================================

    expansion_mode = fields.Selection([
        ('current', 'Estado Actual (como se ve en pantalla)'),
        ('all_expanded', 'Todo Expandido'),
        ('level', 'Hasta Nivel Específico'),
        ('collapsed', 'Todo Colapsado'),
    ], string='Modo de Expansión', default='current',
       help='Controla qué niveles se muestran en la exportación')

    expansion_level = fields.Selection([
        ('1', 'Nivel 1 - Clase'),
        ('2', 'Nivel 2 - Grupo'),
        ('3', 'Nivel 3 - Cuenta'),
        ('4', 'Nivel 4 - Subcuenta'),
        ('5', 'Nivel 5 - Auxiliar'),
        ('6', 'Nivel 6 - Subauxiliar'),
        ('tercero', 'Hasta Terceros'),
        ('movimiento', 'Hasta Movimientos'),
    ], string='Expandir Hasta', default='3',
       help='Nivel máximo de detalle a mostrar')

    show_partners = fields.Boolean(
        string='Mostrar Terceros',
        default=True,
        help='Incluir detalle por tercero en la exportación',
    )

    show_movements = fields.Boolean(
        string='Mostrar Movimientos',
        default=False,
        help='Incluir movimientos individuales en la exportación',
    )

    # =========================================================================
    # OPCIONES DE FORMATO VISUAL
    # =========================================================================

    use_colors = fields.Boolean(
        string='Usar Colores',
        default=True,
        help='Aplicar colores a números (rojo para negativos, verde para positivos)',
    )

    color_mode = fields.Selection([
        ('accounting', 'Contable (Rojo=Negativo, Verde=Positivo)'),
        ('financial', 'Financiero (Rojo=Débito, Azul=Crédito)'),
        ('simple', 'Simple (Solo Rojo para Negativos)'),
    ], string='Modo de Color', default='accounting',
       help='Esquema de colores a aplicar')

    use_symbols = fields.Boolean(
        string='Usar Símbolos Contables',
        default=False,
        help='Mostrar símbolos como ▲▼ para indicar aumentos/disminuciones',
    )

    include_logo = fields.Boolean(
        string='Incluir Logo de Empresa',
        default=True,
        help='Agregar el logo de la empresa en el encabezado',
    )

    include_header = fields.Boolean(
        string='Incluir Encabezado',
        default=True,
        help='Incluir información de la empresa y período',
    )

    include_filters_summary = fields.Boolean(
        string='Incluir Resumen de Filtros',
        default=True,
        help='Agregar página/hoja con resumen de filtros aplicados',
    )

    # =========================================================================
    # OPCIONES DE MONEDA
    # =========================================================================

    show_secondary_currency = fields.Boolean(
        string='Mostrar Moneda Secundaria',
        default=False,
        help='Agregar columnas con valores en moneda secundaria',
    )

    secondary_currency_id = fields.Many2one(
        'res.currency',
        string='Moneda Secundaria',
        help='Moneda para mostrar valores adicionales',
    )

    # =========================================================================
    # OPCIONES ESPECÍFICAS PARA REPORTES DE IMPUESTOS
    # =========================================================================

    include_initial_balance = fields.Boolean(
        string='Incluir Saldo Inicial',
        default=False,
        help='Mostrar saldo inicial de períodos anteriores en reportes de impuestos',
    )

    initial_balance_date = fields.Date(
        string='Fecha de Saldo Inicial',
        help='Fecha desde la cual calcular el saldo inicial',
    )

    # =========================================================================
    # OPCIONES DE EXCEL
    # =========================================================================

    xlsx_freeze_panes = fields.Boolean(
        string='Congelar Paneles (Excel)',
        default=True,
        help='Congelar encabezados en Excel para facilitar navegación',
    )

    xlsx_auto_filter = fields.Boolean(
        string='Agregar Autofiltro (Excel)',
        default=True,
        help='Agregar filtros automáticos a las columnas en Excel',
    )

    xlsx_column_width_auto = fields.Boolean(
        string='Ajustar Ancho Automático (Excel)',
        default=True,
        help='Ajustar automáticamente el ancho de las columnas',
    )

    # =========================================================================
    # COMPUTES
    # =========================================================================

    @api.depends('report_id')
    def _compute_report_name(self):
        for wizard in self:
            wizard.report_name = wizard.report_id.name if wizard.report_id else ''

    @api.onchange('report_id')
    def _onchange_report_id(self):
        if self.report_id:
            self.doc_name = self.report_id.name

    @api.onchange('expansion_mode')
    def _onchange_expansion_mode(self):
        if self.expansion_mode == 'all_expanded':
            self.show_partners = True
            self.show_movements = True
        elif self.expansion_mode == 'collapsed':
            self.show_partners = False
            self.show_movements = False

    # =========================================================================
    # MÉTODOS DE EXPORTACIÓN PRINCIPAL
    # =========================================================================

    def action_export(self):
        """Ejecutar la exportación según las opciones seleccionadas."""
        self.ensure_one()

        # Obtener opciones del reporte
        options = json.loads(self.report_options) if self.report_options else {}

        # Aplicar modificaciones según wizard
        options = self._apply_wizard_options(options)

        # Exportar según formato seleccionado
        if self.export_format == 'pdf':
            return self._export_to_pdf(options)
        elif self.export_format == 'xlsx':
            return self._export_to_xlsx(options)
        elif self.export_format == 'csv':
            return self._export_to_csv(options)
        elif self.export_format == 'xml':
            return self._export_to_xml(options)

        return {'type': 'ir.actions.act_window_close'}

    def _apply_wizard_options(self, options):
        """Aplicar las opciones del wizard a las opciones del reporte."""
        options = dict(options)

        # Aplicar modo de expansión
        if self.expansion_mode == 'all_expanded':
            options['unfold_all'] = True
            options['puc_show_partners'] = True
            options['puc_show_movements'] = True
        elif self.expansion_mode == 'collapsed':
            options['unfold_all'] = False
            options['unfolded_lines'] = []
        elif self.expansion_mode == 'level':
            options['export_max_level'] = self.expansion_level
            options['puc_show_partners'] = self.expansion_level in ('tercero', 'movimiento')
            options['puc_show_movements'] = self.expansion_level == 'movimiento'

        # Aplicar opciones de terceros y movimientos
        options['puc_show_partners'] = self.show_partners
        options['puc_show_movements'] = self.show_movements

        # Opciones de formato visual
        options['export_use_colors'] = self.use_colors
        options['export_color_mode'] = self.color_mode
        options['export_use_symbols'] = self.use_symbols
        options['export_include_logo'] = self.include_logo
        options['export_include_header'] = self.include_header
        options['export_include_filters_summary'] = self.include_filters_summary

        # Opciones de moneda secundaria
        if self.show_secondary_currency and self.secondary_currency_id:
            options['show_secondary_currency'] = True
            options['secondary_currency_id'] = self.secondary_currency_id.id

        # Opciones de saldo inicial para impuestos
        if self.include_initial_balance:
            options['include_tax_initial_balance'] = True
            if self.initial_balance_date:
                options['tax_initial_balance_date'] = self.initial_balance_date.isoformat()

        # Opciones de Excel
        options['xlsx_freeze_panes'] = self.xlsx_freeze_panes
        options['xlsx_auto_filter'] = self.xlsx_auto_filter
        options['xlsx_column_width_auto'] = self.xlsx_column_width_auto

        # Marcar como exportación
        options['export_mode'] = 'file'

        return options

    # =========================================================================
    # EXPORTACIÓN A EXCEL (XLSX)
    # =========================================================================

    def _export_to_xlsx(self, options):
        """Exportar a Excel con todas las opciones del wizard."""
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {
            'in_memory': True,
            'strings_to_formulas': False,
        })

        # Crear formatos
        formats = self._create_xlsx_formats(workbook, options)

        # Crear hoja principal del reporte
        sheet_name = (self.doc_name or self.report_id.name)[:31]
        worksheet = workbook.add_worksheet(sheet_name)

        # Obtener datos del reporte
        report_data = self._get_report_data_for_export(options)

        row = 0

        # Encabezado con logo y empresa
        if options.get('export_include_header', True):
            row = self._write_xlsx_header(workbook, worksheet, formats, options, row)

        # Escribir encabezados de columnas
        row = self._write_xlsx_column_headers(worksheet, formats, options, row)
        header_row = row - 1

        # Escribir líneas del reporte
        row = self._write_xlsx_lines(worksheet, formats, options, report_data['lines'], row)

        # Aplicar autofiltro
        if options.get('xlsx_auto_filter', True) and row > header_row + 1:
            col_count = len(options.get('columns', [])) + 2  # +2 for code and name
            worksheet.autofilter(header_row, 0, row - 1, col_count - 1)

        # Congelar paneles
        if options.get('xlsx_freeze_panes', True):
            worksheet.freeze_panes(header_row + 1, 2)

        # Ajustar anchos de columna
        if options.get('xlsx_column_width_auto', True):
            self._auto_fit_xlsx_columns(worksheet, options)

        # Agregar hoja de filtros si está habilitado
        if options.get('export_include_filters_summary', True):
            self._write_xlsx_filters_sheet(workbook, formats, options)

        workbook.close()
        output.seek(0)

        # Crear attachment
        filename = f"{self.doc_name or self.report_id.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'datas': base64.b64encode(output.read()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'res_model': self._name,
            'res_id': self.id,
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    def _create_xlsx_formats(self, workbook, options):
        """Crear formatos para Excel según las opciones."""
        use_colors = options.get('export_use_colors', True)
        color_mode = options.get('export_color_mode', 'accounting')

        formats = {}

        # Colores base según modo
        if color_mode == 'accounting':
            positive_color = '#198754'  # Verde
            negative_color = '#dc3545'  # Rojo
        elif color_mode == 'financial':
            positive_color = '#0d6efd'  # Azul (crédito)
            negative_color = '#dc3545'  # Rojo (débito)
        else:  # simple
            positive_color = '#000000'  # Negro
            negative_color = '#dc3545'  # Rojo

        # Formato de encabezado de empresa
        formats['company_header'] = workbook.add_format({
            'font_name': 'Lato',
            'font_size': 16,
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
        })

        # Formato de título del reporte
        formats['report_title'] = workbook.add_format({
            'font_name': 'Lato',
            'font_size': 14,
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'font_color': '#666666',
        })

        # Formato de información de período
        formats['period_info'] = workbook.add_format({
            'font_name': 'Lato',
            'font_size': 11,
            'align': 'center',
            'valign': 'vcenter',
            'font_color': '#888888',
        })

        # Formato de encabezado de columnas
        formats['header'] = workbook.add_format({
            'font_name': 'Lato',
            'font_size': 11,
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#f8f9fa',
            'border': 1,
            'border_color': '#dee2e6',
        })

        # Formatos por nivel (0-6)
        for level in range(7):
            indent = level * 2

            # Texto
            formats[f'text_level_{level}'] = workbook.add_format({
                'font_name': 'Lato',
                'font_size': 12 - min(level, 2),
                'bold': level < 3,
                'indent': indent,
            })

            # Formato numérico contable: positivos normales, negativos en paréntesis con color
            # Excel format: #,##0.00_);[Red](#,##0.00)
            accounting_format = '#,##0.00_);[Red](#,##0.00)'
            accounting_format_no_color = '#,##0.00_);(#,##0.00)'

            # Numérico normal
            formats[f'number_level_{level}'] = workbook.add_format({
                'font_name': 'Lato',
                'font_size': 12 - min(level, 2),
                'bold': level < 3,
                'num_format': accounting_format if use_colors else accounting_format_no_color,
                'align': 'right',
            })

            # Numérico positivo (con color verde)
            formats[f'number_positive_level_{level}'] = workbook.add_format({
                'font_name': 'Lato',
                'font_size': 12 - min(level, 2),
                'bold': level < 3,
                'num_format': '#,##0.00',
                'align': 'right',
                'font_color': positive_color if use_colors else '#000000',
            })

            # Numérico negativo (con paréntesis y color rojo)
            formats[f'number_negative_level_{level}'] = workbook.add_format({
                'font_name': 'Lato',
                'font_size': 12 - min(level, 2),
                'bold': level < 3,
                'num_format': '(#,##0.00)',  # Paréntesis para negativos
                'align': 'right',
                'font_color': negative_color if use_colors else '#000000',
            })

            # Numérico cero (gris)
            formats[f'number_zero_level_{level}'] = workbook.add_format({
                'font_name': 'Lato',
                'font_size': 12 - min(level, 2),
                'bold': level < 3,
                'num_format': '#,##0.00',
                'align': 'right',
                'font_color': '#999999',
            })

        # Formato para totales
        formats['total_text'] = workbook.add_format({
            'font_name': 'Lato',
            'font_size': 12,
            'bold': True,
            'bg_color': '#e9ecef',
            'border': 1,
            'border_color': '#dee2e6',
        })

        formats['total_number'] = workbook.add_format({
            'font_name': 'Lato',
            'font_size': 12,
            'bold': True,
            'num_format': '#,##0.00',
            'align': 'right',
            'bg_color': '#e9ecef',
            'border': 1,
            'border_color': '#dee2e6',
        })

        formats['total_number_positive'] = workbook.add_format({
            'font_name': 'Lato',
            'font_size': 12,
            'bold': True,
            'num_format': '#,##0.00',
            'align': 'right',
            'bg_color': '#e9ecef',
            'border': 1,
            'border_color': '#dee2e6',
            'font_color': positive_color if use_colors else '#000000',
        })

        formats['total_number_negative'] = workbook.add_format({
            'font_name': 'Lato',
            'font_size': 12,
            'bold': True,
            'num_format': '(#,##0.00)',  # Paréntesis para negativos
            'align': 'right',
            'bg_color': '#e9ecef',
            'border': 1,
            'border_color': '#dee2e6',
            'font_color': negative_color if use_colors else '#000000',
        })

        # Formato para moneda secundaria
        formats['secondary_currency'] = workbook.add_format({
            'font_name': 'Lato',
            'font_size': 10,
            'num_format': '#,##0.00',
            'align': 'right',
            'font_color': '#666666',
            'italic': True,
        })

        return formats

    def _write_xlsx_header(self, workbook, worksheet, formats, options, row):
        """Escribir encabezado con logo y datos de empresa."""
        company = self.env.company

        # Logo de empresa
        if options.get('export_include_logo', True) and company.logo:
            logo_data = io.BytesIO(base64.b64decode(company.logo))
            try:
                worksheet.insert_image(row, 0, 'logo.png', {
                    'image_data': logo_data,
                    'x_scale': 0.5,
                    'y_scale': 0.5,
                })
                row += 4  # Espacio para el logo
            except Exception:
                pass  # Si falla la imagen, continuar sin ella

        # Nombre de la empresa
        worksheet.merge_range(row, 0, row, 6, company.name, formats['company_header'])
        row += 1

        # NIT de la empresa
        if company.vat:
            worksheet.merge_range(row, 0, row, 6, f"NIT: {company.vat}", formats['period_info'])
            row += 1

        # Nombre del reporte
        worksheet.merge_range(row, 0, row, 6, self.report_id.name, formats['report_title'])
        row += 1

        # Período
        date_from = options.get('date', {}).get('date_from', '')
        date_to = options.get('date', {}).get('date_to', '')
        if date_from and date_to:
            period_text = f"Período: {date_from} a {date_to}"
            worksheet.merge_range(row, 0, row, 6, period_text, formats['period_info'])
            row += 1

        # Fecha de generación
        worksheet.merge_range(row, 0, row, 6,
                              f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                              formats['period_info'])
        row += 2  # Línea en blanco

        return row

    def _write_xlsx_column_headers(self, worksheet, formats, options, row):
        """Escribir encabezados de columnas."""
        col = 0

        # Columnas fijas
        worksheet.write(row, col, 'Código', formats['header'])
        worksheet.set_column(col, col, 15)
        col += 1

        worksheet.write(row, col, 'Nombre', formats['header'])
        worksheet.set_column(col, col, 40)
        col += 1

        # Columnas del reporte
        for column in options.get('columns', []):
            worksheet.write(row, col, column.get('name', ''), formats['header'])
            worksheet.set_column(col, col, 18)
            col += 1

        return row + 1

    def _write_xlsx_lines(self, worksheet, formats, options, lines, row):
        """Escribir líneas del reporte con formato de colores."""
        use_colors = options.get('export_use_colors', True)
        use_symbols = options.get('export_use_symbols', False)
        max_level = options.get('export_max_level')

        for line in lines:
            level = line.get('level', 0)

            # Filtrar por nivel máximo si está configurado
            if max_level:
                try:
                    if max_level.isdigit() and level > int(max_level):
                        continue
                except (ValueError, AttributeError):
                    pass

            col = 0

            # Determinar si es línea de total
            is_total = line.get('class', '') == 'total' or 'total' in line.get('id', '').lower()

            # Código
            code = line.get('code', '') or ''
            if is_total:
                worksheet.write(row, col, code, formats['total_text'])
            else:
                worksheet.write(row, col, code, formats.get(f'text_level_{min(level, 6)}', formats['text_level_0']))
            col += 1

            # Nombre
            name = line.get('name', '')
            if is_total:
                worksheet.write(row, col, name, formats['total_text'])
            else:
                worksheet.write(row, col, name, formats.get(f'text_level_{min(level, 6)}', formats['text_level_0']))
            col += 1

            # Columnas numéricas
            for column_data in line.get('columns', []):
                value = column_data.get('no_format', 0) or 0
                figure_type = column_data.get('figure_type', 'monetary')

                # Solo aplicar formato a valores numéricos
                if figure_type in ('float', 'integer', 'monetary', 'percentage'):
                    if is_total:
                        if use_colors and value > 0:
                            fmt = formats['total_number_positive']
                        elif use_colors and value < 0:
                            fmt = formats['total_number_negative']
                        else:
                            fmt = formats['total_number']
                    else:
                        level_key = min(level, 6)
                        if use_colors and value > 0:
                            fmt = formats.get(f'number_positive_level_{level_key}', formats['number_positive_level_0'])
                        elif use_colors and value < 0:
                            fmt = formats.get(f'number_negative_level_{level_key}', formats['number_negative_level_0'])
                        elif value == 0:
                            fmt = formats.get(f'number_zero_level_{level_key}', formats['number_zero_level_0'])
                        else:
                            fmt = formats.get(f'number_level_{level_key}', formats['number_level_0'])

                    # Agregar símbolo si está habilitado
                    if use_symbols and value != 0:
                        symbol = '▲' if value > 0 else '▼'
                        # Para símbolos, usamos texto con valor formateado
                        if value < 0:
                            # Negativos con paréntesis y símbolo
                            worksheet.write(row, col, f"{symbol} ({abs(value):,.2f})", fmt)
                        else:
                            worksheet.write(row, col, f"{symbol} {value:,.2f}", fmt)
                    else:
                        # Para negativos, el formato de Excel ya maneja los paréntesis
                        # pero necesitamos escribir el valor absoluto si usamos formato con paréntesis
                        if value < 0 and use_colors:
                            # El formato ya tiene los paréntesis, escribimos el valor absoluto
                            worksheet.write_number(row, col, abs(value), fmt)
                        else:
                            worksheet.write_number(row, col, value, fmt)
                else:
                    # Valor de texto
                    text_value = column_data.get('name', '')
                    if is_total:
                        worksheet.write(row, col, text_value, formats['total_text'])
                    else:
                        worksheet.write(row, col, text_value, formats.get(f'text_level_{min(level, 6)}', formats['text_level_0']))

                col += 1

            row += 1

        return row

    def _auto_fit_xlsx_columns(self, worksheet, options):
        """Ajustar automáticamente el ancho de las columnas."""
        # Anchos predeterminados razonables
        worksheet.set_column(0, 0, 15)  # Código
        worksheet.set_column(1, 1, 45)  # Nombre

        # Columnas numéricas
        col_count = len(options.get('columns', []))
        if col_count > 0:
            worksheet.set_column(2, 2 + col_count - 1, 18)

    def _write_xlsx_filters_sheet(self, workbook, formats, options):
        """Escribir hoja con resumen de filtros aplicados."""
        sheet = workbook.add_worksheet('Filtros Aplicados')

        row = 0
        sheet.write(row, 0, 'Resumen de Filtros Aplicados', formats['report_title'])
        row += 2

        # Período
        date_info = options.get('date', {})
        if date_info:
            sheet.write(row, 0, 'Período:', formats['header'])
            sheet.write(row, 1, f"{date_info.get('date_from', '')} - {date_info.get('date_to', '')}")
            row += 1

        # Compañía
        companies = options.get('multi_company', [])
        if companies:
            selected_companies = [c['name'] for c in companies if c.get('selected')]
            sheet.write(row, 0, 'Compañías:', formats['header'])
            sheet.write(row, 1, ', '.join(selected_companies) if selected_companies else 'Todas')
            row += 1

        # Diarios
        journals = options.get('journals', [])
        if journals:
            selected_journals = [j['name'] for j in journals if j.get('selected')]
            sheet.write(row, 0, 'Diarios:', formats['header'])
            sheet.write(row, 1, ', '.join(selected_journals) if selected_journals else 'Todos')
            row += 1

        # Jerarquía PUC
        if options.get('puc_hierarchy'):
            sheet.write(row, 0, 'Jerarquía PUC:', formats['header'])
            sheet.write(row, 1, 'Activada')
            row += 1

            if options.get('puc_hierarchy_level'):
                sheet.write(row, 0, 'Nivel de Jerarquía:', formats['header'])
                sheet.write(row, 1, options.get('puc_hierarchy_level', 'all'))
                row += 1

        # Mostrar terceros/movimientos
        sheet.write(row, 0, 'Mostrar Terceros:', formats['header'])
        sheet.write(row, 1, 'Sí' if options.get('puc_show_partners', True) else 'No')
        row += 1

        sheet.write(row, 0, 'Mostrar Movimientos:', formats['header'])
        sheet.write(row, 1, 'Sí' if options.get('puc_show_movements', True) else 'No')
        row += 1

        # Rango de cuentas
        if options.get('account_from') or options.get('account_to'):
            sheet.write(row, 0, 'Rango de Cuentas:', formats['header'])
            range_text = f"{options.get('account_from', '')} - {options.get('account_to', '')}"
            sheet.write(row, 1, range_text)
            row += 1

        # Cuentas excluidas
        if options.get('account_exclude'):
            sheet.write(row, 0, 'Cuentas Excluidas:', formats['header'])
            sheet.write(row, 1, ', '.join(options.get('account_exclude', [])))
            row += 1

        # Opciones de exportación
        row += 1
        sheet.write(row, 0, 'Opciones de Exportación', formats['report_title'])
        row += 1

        sheet.write(row, 0, 'Colores:', formats['header'])
        sheet.write(row, 1, 'Activados' if options.get('export_use_colors', True) else 'Desactivados')
        row += 1

        sheet.write(row, 0, 'Modo de Color:', formats['header'])
        sheet.write(row, 1, options.get('export_color_mode', 'accounting'))
        row += 1

        sheet.write(row, 0, 'Símbolos Contables:', formats['header'])
        sheet.write(row, 1, 'Activados' if options.get('export_use_symbols', False) else 'Desactivados')
        row += 1

        # Ajustar anchos
        sheet.set_column(0, 0, 25)
        sheet.set_column(1, 1, 50)

    def _get_report_data_for_export(self, options):
        """Obtener datos del reporte para exportación."""
        report = self.report_id

        # Si está configurado para expandir todo, obtener todas las líneas
        if options.get('unfold_all'):
            options['unfolded_lines'] = []

        # Obtener líneas del reporte
        lines = report._get_lines(options)

        return {
            'lines': lines,
            'options': options,
        }

    # =========================================================================
    # EXPORTACIÓN A PDF
    # =========================================================================

    def _export_to_pdf(self, options):
        """Exportar a PDF con las opciones del wizard."""
        # Usar el método nativo de Odoo pero con opciones modificadas
        result = self.report_id.export_to_pdf(options)

        # Crear attachment
        filename = f"{self.doc_name or self.report_id.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'datas': base64.b64encode(result.get('file_content', b'')),
            'mimetype': 'application/pdf',
            'res_model': self._name,
            'res_id': self.id,
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    # =========================================================================
    # EXPORTACIÓN A CSV
    # =========================================================================

    def _export_to_csv(self, options):
        """Exportar a CSV con las opciones del wizard."""
        import csv

        output = io.StringIO()
        writer = csv.writer(output, delimiter=';', quotechar='"', quoting=csv.QUOTE_MINIMAL)

        # Encabezados
        headers = ['Código', 'Nombre']
        for column in options.get('columns', []):
            headers.append(column.get('name', ''))
        writer.writerow(headers)

        # Datos
        report_data = self._get_report_data_for_export(options)
        for line in report_data['lines']:
            row_data = [
                line.get('code', '') or '',
                line.get('name', ''),
            ]
            for column_data in line.get('columns', []):
                value = column_data.get('no_format', 0)
                if isinstance(value, (int, float)):
                    row_data.append(f"{value:.2f}")
                else:
                    row_data.append(column_data.get('name', ''))
            writer.writerow(row_data)

        # Crear attachment
        filename = f"{self.doc_name or self.report_id.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        content = output.getvalue().encode('utf-8-sig')  # BOM for Excel compatibility

        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'datas': base64.b64encode(content),
            'mimetype': 'text/csv',
            'res_model': self._name,
            'res_id': self.id,
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    # =========================================================================
    # EXPORTACIÓN A XML
    # =========================================================================

    def _export_to_xml(self, options):
        """Exportar a XML con estructura contable."""
        from xml.etree import ElementTree as ET

        # Crear elemento raíz
        root = ET.Element('ReporteContable')
        root.set('fecha_generacion', datetime.now().isoformat())
        root.set('reporte', self.report_id.name)

        # Información de empresa
        company_elem = ET.SubElement(root, 'Empresa')
        company_elem.set('nombre', self.env.company.name)
        company_elem.set('nit', self.env.company.vat or '')

        # Período
        periodo_elem = ET.SubElement(root, 'Periodo')
        date_info = options.get('date', {})
        periodo_elem.set('desde', date_info.get('date_from', ''))
        periodo_elem.set('hasta', date_info.get('date_to', ''))

        # Columnas
        columnas_elem = ET.SubElement(root, 'Columnas')
        for col in options.get('columns', []):
            col_elem = ET.SubElement(columnas_elem, 'Columna')
            col_elem.set('nombre', col.get('name', ''))
            col_elem.set('tipo', col.get('figure_type', 'monetary'))

        # Líneas
        lineas_elem = ET.SubElement(root, 'Lineas')
        report_data = self._get_report_data_for_export(options)

        for line in report_data['lines']:
            linea_elem = ET.SubElement(lineas_elem, 'Linea')
            linea_elem.set('codigo', line.get('code', '') or '')
            linea_elem.set('nombre', line.get('name', ''))
            linea_elem.set('nivel', str(line.get('level', 0)))

            for i, column_data in enumerate(line.get('columns', [])):
                valor_elem = ET.SubElement(linea_elem, 'Valor')
                valor_elem.set('columna', str(i))
                value = column_data.get('no_format', 0)
                if isinstance(value, (int, float)):
                    valor_elem.text = f"{value:.2f}"
                else:
                    valor_elem.text = column_data.get('name', '')

        # Convertir a string
        xml_string = ET.tostring(root, encoding='unicode', method='xml')
        xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'
        full_xml = xml_declaration + xml_string

        # Crear attachment
        filename = f"{self.doc_name or self.report_id.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xml"

        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'datas': base64.b64encode(full_xml.encode('utf-8')),
            'mimetype': 'application/xml',
            'res_model': self._name,
            'res_id': self.id,
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }
