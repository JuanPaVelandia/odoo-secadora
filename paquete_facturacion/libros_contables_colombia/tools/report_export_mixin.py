# -*- coding: utf-8 -*-
from odoo import models
from datetime import datetime
import io
import base64

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class ReportExportMixin(models.AbstractModel):
    """Mixin unificado para exportacion PDF y Excel."""

    _name = 'report.export.mixin'
    _description = 'Mixin Unificado de Exportacion'

    STYLE_PRESETS = {
        'professional': {
            'name': 'Profesional',
            'colors': {
                'primary': '#2c3e50',
                'secondary': '#34495e',
                'positive': '#27ae60',
                'negative': '#e74c3c',
                'zero': '#95a5a6',
                'header_bg': '#ecf0f1',
                'total_bg': '#bdc3c7',
                'border': '#dee2e6',
            },
            'fonts': {'family': 'Lato', 'header_size': 14, 'title_size': 12, 'body_size': 10},
        },
        'corporate': {
            'name': 'Corporativo',
            'colors': {
                'primary': '#1a237e',
                'secondary': '#283593',
                'positive': '#2e7d32',
                'negative': '#c62828',
                'zero': '#757575',
                'header_bg': '#e8eaf6',
                'total_bg': '#c5cae9',
                'border': '#9fa8da',
            },
            'fonts': {'family': 'Arial', 'header_size': 14, 'title_size': 11, 'body_size': 10},
        },
        'minimal': {
            'name': 'Minimalista',
            'colors': {
                'primary': '#212121',
                'secondary': '#424242',
                'positive': '#000000',
                'negative': '#d32f2f',
                'zero': '#9e9e9e',
                'header_bg': '#fafafa',
                'total_bg': '#eeeeee',
                'border': '#e0e0e0',
            },
            'fonts': {'family': 'Helvetica', 'header_size': 12, 'title_size': 10, 'body_size': 9},
        },
        'accounting': {
            'name': 'Contable Tradicional',
            'colors': {
                'primary': '#000000',
                'secondary': '#333333',
                'positive': '#006400',
                'negative': '#8b0000',
                'zero': '#808080',
                'header_bg': '#f5f5f5',
                'total_bg': '#d3d3d3',
                'border': '#a9a9a9',
            },
            'fonts': {'family': 'Times New Roman', 'header_size': 14, 'title_size': 12, 'body_size': 11},
        },
        'colombia_dian': {
            'name': 'DIAN Colombia',
            'colors': {
                'primary': '#003366',
                'secondary': '#0055a4',
                'positive': '#006633',
                'negative': '#cc0000',
                'zero': '#666666',
                'header_bg': '#e6f0ff',
                'total_bg': '#cce0ff',
                'border': '#99c2ff',
            },
            'fonts': {'family': 'Arial', 'header_size': 12, 'title_size': 10, 'body_size': 9},
        },
    }

    COLUMN_PRESETS = {
        'balance_simple': [
            {'key': 'code', 'name': 'Codigo', 'width': 15, 'type': 'text'},
            {'key': 'name', 'name': 'Nombre', 'width': 45, 'type': 'text'},
            {'key': 'balance', 'name': 'Saldo', 'width': 18, 'type': 'monetary'},
        ],
        'balance_completo': [
            {'key': 'code', 'name': 'Codigo', 'width': 15, 'type': 'text'},
            {'key': 'name', 'name': 'Nombre', 'width': 40, 'type': 'text'},
            {'key': 'initial', 'name': 'Saldo Inicial', 'width': 16, 'type': 'monetary'},
            {'key': 'debit', 'name': 'Debito', 'width': 16, 'type': 'monetary'},
            {'key': 'credit', 'name': 'Credito', 'width': 16, 'type': 'monetary'},
            {'key': 'final', 'name': 'Saldo Final', 'width': 16, 'type': 'monetary'},
        ],
        'auxiliar': [
            {'key': 'date', 'name': 'Fecha', 'width': 12, 'type': 'date'},
            {'key': 'code', 'name': 'Cuenta', 'width': 12, 'type': 'text'},
            {'key': 'name', 'name': 'Descripcion', 'width': 35, 'type': 'text'},
            {'key': 'partner', 'name': 'Tercero', 'width': 25, 'type': 'text'},
            {'key': 'debit', 'name': 'Debito', 'width': 15, 'type': 'monetary'},
            {'key': 'credit', 'name': 'Credito', 'width': 15, 'type': 'monetary'},
            {'key': 'balance', 'name': 'Saldo', 'width': 15, 'type': 'monetary'},
        ],
        'comparativo': [
            {'key': 'code', 'name': 'Codigo', 'width': 12, 'type': 'text'},
            {'key': 'name', 'name': 'Cuenta', 'width': 35, 'type': 'text'},
            {'key': 'period_1', 'name': 'Periodo 1', 'width': 15, 'type': 'monetary'},
            {'key': 'period_2', 'name': 'Periodo 2', 'width': 15, 'type': 'monetary'},
            {'key': 'variation', 'name': 'Variacion', 'width': 15, 'type': 'monetary'},
            {'key': 'percentage', 'name': '%', 'width': 10, 'type': 'percentage'},
        ],
        'impuestos': [
            {'key': 'tax_name', 'name': 'Impuesto', 'width': 30, 'type': 'text'},
            {'key': 'base', 'name': 'Base', 'width': 18, 'type': 'monetary'},
            {'key': 'amount', 'name': 'Valor', 'width': 18, 'type': 'monetary'},
            {'key': 'rate', 'name': 'Tarifa', 'width': 10, 'type': 'percentage'},
        ],
    }

    HEADER_TEMPLATES = {
        'standard': {
            'show_logo': True,
            'logo_position': 'left',
            'logo_scale': 0.5,
            'show_company_name': True,
            'show_company_vat': True,
            'show_company_address': False,
            'show_report_title': True,
            'show_period': True,
            'show_generation_date': True,
            'show_user': False,
        },
        'compact': {
            'show_logo': False,
            'show_company_name': True,
            'show_company_vat': True,
            'show_company_address': False,
            'show_report_title': True,
            'show_period': True,
            'show_generation_date': False,
            'show_user': False,
        },
        'full': {
            'show_logo': True,
            'logo_position': 'left',
            'logo_scale': 0.6,
            'show_company_name': True,
            'show_company_vat': True,
            'show_company_address': True,
            'show_report_title': True,
            'show_period': True,
            'show_generation_date': True,
            'show_user': True,
        },
        'dian': {
            'show_logo': True,
            'logo_position': 'left',
            'logo_scale': 0.4,
            'show_company_name': True,
            'show_company_vat': True,
            'show_company_address': True,
            'show_report_title': True,
            'show_period': True,
            'show_generation_date': True,
            'show_user': True,
            'show_consecutive': True,
            'show_resolution': False,
        },
    }

    def build_export_config(self, options):
        """Construye configuracion de exportacion desde opciones."""
        return {
            'style_preset': options.get('style_preset', 'professional'),
            'custom_colors': options.get('custom_colors', {}),
            'header_template': options.get('header_template', 'standard'),
            'custom_logo': options.get('custom_logo'),
            'number_format': options.get('number_format', 'accounting'),
            'decimal_places': options.get('decimal_places', 2),
            'use_colors': options.get('use_colors', True),
            'highlight_negative': options.get('highlight_negative', True),
            'highlight_zero': options.get('highlight_zero', True),
            'column_preset': options.get('column_preset', 'balance_completo'),
            'custom_columns': options.get('custom_columns', []),
            'freeze_panes': options.get('freeze_panes', True),
            'auto_filter': options.get('auto_filter', True),
            'add_outline': options.get('add_outline', True),
        }

    def get_merged_colors(self, config):
        """Obtiene colores combinando preset y custom."""
        preset = self.STYLE_PRESETS.get(
            config.get('style_preset', 'professional'),
            self.STYLE_PRESETS['professional']
        )
        colors = dict(preset['colors'])
        colors.update(config.get('custom_colors', {}))
        return colors

    def get_columns(self, config):
        """Obtiene definicion de columnas."""
        if config.get('custom_columns'):
            return config['custom_columns']
        return self.COLUMN_PRESETS.get(
            config.get('column_preset', 'balance_simple'),
            self.COLUMN_PRESETS['balance_simple']
        )

    def get_header_config(self, config):
        """Obtiene configuracion de encabezado."""
        return self.HEADER_TEMPLATES.get(
            config.get('header_template', 'standard'),
            self.HEADER_TEMPLATES['standard']
        )

    def create_xlsx_workbook_formats(self, workbook, config):
        """Crea formatos Excel desde configuracion."""
        if not xlsxwriter:
            return {}

        colors = self.get_merged_colors(config)
        preset = self.STYLE_PRESETS.get(
            config.get('style_preset', 'professional'),
            self.STYLE_PRESETS['professional']
        )
        fonts = preset['fonts']
        formats = {}
        base = {'font_name': fonts['family'], 'font_size': fonts['body_size']}

        formats['company_name'] = workbook.add_format({
            **base,
            'font_size': fonts['header_size'] + 2,
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'font_color': colors['primary'],
        })
        formats['report_title'] = workbook.add_format({
            **base,
            'font_size': fonts['header_size'],
            'bold': True,
            'align': 'center',
            'font_color': colors['secondary'],
        })
        formats['subtitle'] = workbook.add_format({
            **base,
            'font_size': fonts['title_size'],
            'align': 'center',
            'font_color': colors['secondary'],
        })
        formats['column_header'] = workbook.add_format({
            **base,
            'font_size': fonts['title_size'],
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': colors['header_bg'],
            'border': 1,
            'border_color': colors['border'],
            'text_wrap': True,
        })

        decimal_places = config.get('decimal_places', 2)
        use_colors = config.get('use_colors', True)

        for level in range(7):
            font_size = fonts['body_size'] + (2 - min(level, 2))
            is_bold = level < 3
            formats[f'text_L{level}'] = workbook.add_format({
                **base,
                'font_size': font_size,
                'bold': is_bold,
                'indent': level * 2,
            })
            num_fmt = '#,##0.' + '0' * decimal_places
            formats[f'number_L{level}'] = workbook.add_format({
                **base,
                'font_size': font_size,
                'bold': is_bold,
                'num_format': num_fmt,
                'align': 'right',
            })
            formats[f'number_pos_L{level}'] = workbook.add_format({
                **base,
                'font_size': font_size,
                'bold': is_bold,
                'num_format': num_fmt,
                'align': 'right',
                'font_color': colors['positive'] if use_colors else colors['primary'],
            })
            formats[f'number_neg_L{level}'] = workbook.add_format({
                **base,
                'font_size': font_size,
                'bold': is_bold,
                'num_format': '(' + num_fmt + ')',
                'align': 'right',
                'font_color': colors['negative'] if use_colors else colors['primary'],
            })
            formats[f'number_zero_L{level}'] = workbook.add_format({
                **base,
                'font_size': font_size,
                'bold': is_bold,
                'num_format': num_fmt,
                'align': 'right',
                'font_color': colors['zero'] if use_colors else colors['primary'],
            })

        decimal_fmt = '#,##0.' + '0' * decimal_places
        formats['total_text'] = workbook.add_format({
            **base,
            'font_size': fonts['title_size'],
            'bold': True,
            'bg_color': colors['total_bg'],
            'border': 2,
            'border_color': colors['border'],
        })
        formats['total_number'] = workbook.add_format({
            **base,
            'font_size': fonts['title_size'],
            'bold': True,
            'num_format': decimal_fmt,
            'align': 'right',
            'bg_color': colors['total_bg'],
            'border': 2,
            'border_color': colors['border'],
        })
        formats['total_number_pos'] = workbook.add_format({
            **base,
            'font_size': fonts['title_size'],
            'bold': True,
            'num_format': decimal_fmt,
            'align': 'right',
            'bg_color': colors['total_bg'],
            'border': 2,
            'border_color': colors['border'],
            'font_color': colors['positive'],
        })
        formats['total_number_neg'] = workbook.add_format({
            **base,
            'font_size': fonts['title_size'],
            'bold': True,
            'num_format': '(' + decimal_fmt + ')',
            'align': 'right',
            'bg_color': colors['total_bg'],
            'border': 2,
            'border_color': colors['border'],
            'font_color': colors['negative'],
        })
        return formats

    def write_dynamic_header(self, worksheet, formats, config, options, row=0):
        """Escribe encabezado dinamico segun configuracion."""
        if not xlsxwriter:
            return row

        header_config = self.get_header_config(config)
        company = self.env.company
        col_count = len(self.get_columns(config))

        if header_config.get('show_logo'):
            logo = config.get('custom_logo') or (company.logo if company.logo else None)
            if logo:
                try:
                    logo_data = io.BytesIO(base64.b64decode(logo))
                    worksheet.insert_image(row, 0, 'logo.png', {
                        'image_data': logo_data,
                        'x_scale': header_config.get('logo_scale', 0.5),
                        'y_scale': header_config.get('logo_scale', 0.5),
                    })
                    row += 4
                except Exception:
                    pass

        if header_config.get('show_company_name'):
            worksheet.merge_range(row, 0, row, col_count - 1, company.name, formats['company_name'])
            row += 1
        if header_config.get('show_company_vat') and company.vat:
            worksheet.merge_range(row, 0, row, col_count - 1, 'NIT: ' + company.vat, formats['subtitle'])
            row += 1
        if header_config.get('show_company_address'):
            address_parts = [company.street, company.city, company.state_id.name if company.state_id else None]
            address = ', '.join(filter(None, address_parts))
            if address:
                worksheet.merge_range(row, 0, row, col_count - 1, address, formats['subtitle'])
                row += 1
        if header_config.get('show_report_title'):
            report_name = options.get('report_name', 'Reporte')
            worksheet.merge_range(row, 0, row, col_count - 1, report_name, formats['report_title'])
            row += 1
        if header_config.get('show_period'):
            date_from = options.get('date', {}).get('date_from', '')
            date_to = options.get('date', {}).get('date_to', '')
            if date_from and date_to:
                period_text = 'Periodo: ' + date_from + ' a ' + date_to
                worksheet.merge_range(row, 0, row, col_count - 1, period_text, formats['subtitle'])
                row += 1
        if header_config.get('show_generation_date'):
            gen_text = 'Generado: ' + datetime.now().strftime('%Y-%m-%d %H:%M')
            worksheet.merge_range(row, 0, row, col_count - 1, gen_text, formats['subtitle'])
            row += 1
        if header_config.get('show_user'):
            user_text = 'Usuario: ' + self.env.user.name
            worksheet.merge_range(row, 0, row, col_count - 1, user_text, formats['subtitle'])
            row += 1
        row += 1
        return row

    def export_to_xlsx_advanced(self, report_name, lines, options, config=None):
        """Exporta reporte a Excel con configuracion avanzada."""
        if not xlsxwriter:
            return b''

        if config is None:
            config = self.build_export_config(options)

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True, 'strings_to_formulas': False})
        formats = self.create_xlsx_workbook_formats(workbook, config)
        columns = self.get_columns(config)

        sheet_name = report_name[:31]
        worksheet = workbook.add_worksheet(sheet_name)

        row = 0
        options['report_name'] = report_name
        row = self.write_dynamic_header(worksheet, formats, config, options, row)

        for col_idx, col_def in enumerate(columns):
            worksheet.write(row, col_idx, col_def['name'], formats['column_header'])
            worksheet.set_column(col_idx, col_idx, col_def.get('width', 15))

        header_row = row
        row += 1

        if config.get('add_outline'):
            worksheet.outline_settings(True, False, False, True)

        for line in lines:
            level = line.get('level', 0)
            is_total = 'total' in line.get('class', '').lower()

            if config.get('add_outline') and level > 0:
                worksheet.set_row(row, None, None, {'level': min(level, 7)})

            for col_idx, col_def in enumerate(columns):
                key = col_def['key']
                col_type = col_def.get('type', 'text')

                if key in ('code', 'name'):
                    value = line.get(key, '')
                else:
                    col_values = line.get('columns', [])
                    if col_idx >= 2 and len(col_values) > col_idx - 2:
                        value = col_values[col_idx - 2].get('no_format', 0)
                    else:
                        value = 0

                if is_total:
                    if col_type == 'text':
                        fmt = formats['total_text']
                    elif col_type == 'monetary':
                        if value < 0:
                            fmt = formats['total_number_neg']
                        elif value > 0:
                            fmt = formats['total_number_pos']
                        else:
                            fmt = formats['total_number']
                    else:
                        fmt = formats['total_number']
                else:
                    level_key = min(level, 6)
                    if col_type == 'text':
                        fmt = formats.get('text_L' + str(level_key), formats['text_L0'])
                    elif col_type == 'monetary':
                        if value > 0:
                            fmt = formats.get('number_pos_L' + str(level_key))
                        elif value < 0:
                            fmt = formats.get('number_neg_L' + str(level_key))
                        else:
                            fmt = formats.get('number_zero_L' + str(level_key))
                    else:
                        fmt = formats.get('number_L' + str(level_key))

                if col_type in ('monetary', 'float', 'percentage') and isinstance(value, (int, float)):
                    worksheet.write_number(row, col_idx, value, fmt)
                else:
                    worksheet.write(row, col_idx, value, fmt)
            row += 1

        if config.get('auto_filter') and row > header_row + 1:
            worksheet.autofilter(header_row, 0, row - 1, len(columns) - 1)
        if config.get('freeze_panes'):
            worksheet.freeze_panes(header_row + 1, 2)

        workbook.close()
        output.seek(0)
        return output.read()

    def get_pdf_context(self, report_name, lines, options, config=None):
        """Genera contexto para renderizado PDF con QWeb."""
        if config is None:
            config = self.build_export_config(options)

        colors = self.get_merged_colors(config)
        header_config = self.get_header_config(config)
        columns = self.get_columns(config)
        company = self.env.company

        return {
            'report_name': report_name,
            'company': company,
            'lines': lines,
            'columns': columns,
            'options': options,
            'config': {
                'colors': colors,
                'header': header_config,
                'use_colors': config.get('use_colors', True),
            },
            'date_from': options.get('date', {}).get('date_from', ''),
            'date_to': options.get('date', {}).get('date_to', ''),
            'generation_date': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'user_name': self.env.user.name,
        }
