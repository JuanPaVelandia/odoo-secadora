# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime
from pytz import timezone

import base64
import io
import logging

_logger = logging.getLogger(__name__)

try:
    import xlsxwriter
except ImportError:
    _logger.warning("xlsxwriter no instalado. Funcionalidad Excel limitada.")
    xlsxwriter = None


class HrSalaryHistoryReport(models.TransientModel):
    _name = "hr.salary.history.report"
    _description = "Reporte historico salarial"

    date_start = fields.Date(
        string='Fecha de Inicio'
    )
    date_end = fields.Date(
        string='Fecha de Fin'
    )
    employee_ids = fields.Many2many(
        'hr.employee',
        string='Empleados'
    )
    contract_active = fields.Boolean(
        string='Solo contratos activos',
        default=True
    )
    excel_file = fields.Binary(
        string='Excel'
    )
    excel_file_name = fields.Char(
        string='Excel filename'
    )

    def _get_report_data(self):
        """
        Obtiene los datos del reporte usando ORM search_read.
        Retorna lista de diccionarios con los datos formateados.
        """
        self.ensure_one()

        # Dominio base para cambios salariales
        domain = [('company_id', '=', self.env.company.id)]

        # Filtro fechas
        if self.date_start:
            domain.append(('date_start', '>=', self.date_start))
        if self.date_end:
            domain.append(('date_start', '<=', self.date_end))

        # Filtro empleados
        if self.employee_ids:
            domain.append(('employee_id', 'in', self.employee_ids.ids))

        # Filtro contratos activos
        if self.contract_active:
            domain.append(('contract_id.state', '=', 'open'))

        # Campos a leer en una sola operacion
        fields_to_read = [
            'contract_id',
            'employee_id',
            'date_start',
            'wage',
            'job_id',
        ]

        # search_read: busqueda + lectura en una sola operacion
        wage_changes = self.env['hr.contract.change.wage'].search_read(
            domain,
            fields=fields_to_read,
            order='employee_id, date_start'
        )

        if not wage_changes:
            return []

        # Obtener IDs unicos para prefetch
        contract_ids = list(set(r['contract_id'][0] for r in wage_changes if r.get('contract_id')))
        employee_ids = list(set(r['employee_id'][0] for r in wage_changes if r.get('employee_id')))

        # Leer contratos y empleados en batch
        contracts_data = {
            c['id']: c for c in self.env['hr.contract'].search_read(
                [('id', 'in', contract_ids)],
                ['sequence', 'name', 'date_start', 'state']
            )
        }
        employees_data = {
            e['id']: e for e in self.env['hr.employee'].search_read(
                [('id', 'in', employee_ids)],
                ['name', 'company_id']
            )
        }

        # Construir lista de resultados
        result = []
        for change in wage_changes:
            contract_id = change['contract_id'][0] if change.get('contract_id') else None
            employee_id = change['employee_id'][0] if change.get('employee_id') else None

            contract = contracts_data.get(contract_id, {})
            employee = employees_data.get(employee_id, {})

            # Formatear nombre del contrato
            contract_seq = contract.get('sequence') or '/'
            contract_name = contract.get('name') or ''
            contract_display = f"{contract_seq} - {contract_name}"

            # Estado del contrato
            state_label = 'En Proceso' if contract.get('state') == 'open' else 'Inactivo'

            # Compania
            company_name = ''
            if employee.get('company_id'):
                company_name = employee['company_id'][1] if isinstance(employee['company_id'], (list, tuple)) else ''

            result.append({
                'contrato': contract_display,
                'fecha_ingreso': contract.get('date_start'),
                'estado_contrato': state_label,
                'empleado': employee.get('name') or '',
                'compania': company_name,
                'fecha_inicio_salario_cargo': change.get('date_start'),
                'salario': change.get('wage') or 0,
                'cargo': change['job_id'][1] if change.get('job_id') else '',
            })

        return result

    def generate_excel(self):
        """Genera el reporte Excel de historico salarial"""
        self.ensure_one()

        if not xlsxwriter:
            raise ValidationError(_("xlsxwriter no instalado. Ejecute: pip install xlsxwriter"))

        # Obtener datos usando ORM
        result_data = self._get_report_data()

        if not result_data:
            raise ValidationError(_("No se encontraron datos con los filtros especificados."))

        # Generar Excel
        filename = 'Reporte historico salarial.xlsx'
        stream = io.BytesIO()
        book = xlsxwriter.Workbook(stream, {'in_memory': True})

        # Columnas
        columns = [
            'Contrato',
            'Fecha Ingreso',
            'Estado Contrato',
            'Empleado',
            'Compania',
            'Fecha Inicio Salario/Cargo',
            'Salario',
            'Cargo'
        ]

        # Mapeo de claves a columnas
        column_keys = [
            'contrato',
            'fecha_ingreso',
            'estado_contrato',
            'empleado',
            'compania',
            'fecha_inicio_salario_cargo',
            'salario',
            'cargo'
        ]

        sheet = book.add_worksheet('Historico salarial')

        # Formatos
        title_format = book.add_format({
            'bold': True,
            'align': 'left',
            'font_name': 'Calibri',
            'font_size': 15,
            'bottom': 5,
            'bottom_color': '#1F497D',
            'font_color': '#1F497D'
        })

        subtitle_format = book.add_format({
            'bold': False,
            'align': 'left',
            'font_name': 'Calibri',
            'font_size': 10,
            'bottom': 5,
            'bottom_color': '#1F497D',
            'font_color': '#1F497D'
        })

        header_format = book.add_format({
            'bold': True,
            'align': 'center',
            'font_name': 'Calibri',
            'font_size': 11,
            'bg_color': '#4472C4',
            'font_color': '#FFFFFF',
            'border': 1
        })

        date_format = book.add_format({'num_format': 'dd/mm/yyyy', 'align': 'center'})
        money_format = book.add_format({'num_format': '#,##0', 'align': 'right'})
        text_format = book.add_format({'align': 'left'})

        # Titulo
        user_tz = self.env.user.tz or 'UTC'
        text_generate = f"Informe generado el {datetime.now(timezone(user_tz)).strftime('%Y-%m-%d %H:%M:%S')}"

        sheet.merge_range('A1:H1', 'Historico salarial', title_format)
        sheet.merge_range('A2:H2', text_generate, subtitle_format)

        # Encabezados
        for col, column_name in enumerate(columns):
            sheet.write(2, col, column_name, header_format)

        # Datos
        row_num = 3
        for record in result_data:
            for col_num, key in enumerate(column_keys):
                value = record.get(key, '')

                if value is None:
                    sheet.write(row_num, col_num, '', text_format)
                elif key in ('fecha_ingreso', 'fecha_inicio_salario_cargo') and value:
                    sheet.write_datetime(row_num, col_num, value, date_format)
                elif key == 'salario':
                    sheet.write_number(row_num, col_num, value or 0, money_format)
                else:
                    sheet.write(row_num, col_num, str(value) if value else '', text_format)

            row_num += 1

        # Formato tabla
        if row_num > 3:
            array_header_table = [{'header': col} for col in columns]
            sheet.add_table(2, 0, row_num - 1, len(columns) - 1, {
                'style': 'Table Style Medium 2',
                'columns': array_header_table
            })

        # Ajustar anchos de columna
        column_widths = [25, 15, 15, 35, 25, 22, 15, 30]
        for col, width in enumerate(column_widths):
            sheet.set_column(col, col, width)

        book.close()

        self.write({
            'excel_file': base64.b64encode(stream.getvalue()).decode('utf-8'),
            'excel_file_name': filename,
        })

        return {
            'name': _('Reporte historico salarial'),
            'type': 'ir.actions.act_url',
            'url': f"web/content/?model=hr.salary.history.report&id={self.id}"
                   f"&filename_field=excel_file_name&field=excel_file&download=true"
                   f"&filename={self.excel_file_name}",
            'target': 'self',
        }
