from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime
from pytz import timezone

import base64
import io
import xlsxwriter
import logging

from odoo.addons.lavish_hr_employee.models.payroll.hr_payslip_constants import (
    MONTH_SELECTION, get_month_name, get_weekday_name, format_date_spanish
)

_logger = logging.getLogger(__name__)


class HrBirthdayList(models.TransientModel):
    _name = "hr.birthday.tree"
    _description = "Listado de cumpleaños"

    company = fields.Many2many('res.company', 'hr_birthday_tree_res_company_rel', 'hr_birthday_tree_id', 'res_company_id', string='Compañías', required=True, default=lambda self: self.env.company.ids)
    month = fields.Selection(selection=MONTH_SELECTION, string='Mes', required=True)

    excel_file = fields.Binary('Excel')
    excel_file_name = fields.Char('Excel filename')
    show_dependent = fields.Boolean(string='Mostrar dependientes')
    active_employee = fields.Boolean(string='Solo empleados con contrato activo', default=True)

    @api.depends('month')
    def _compute_display_name(self):
        for record in self:
            record.display_name = "Listado de cumpleaños"

    def get_month(self):
        if self.month == '0':
            month = [1,2,3,4,5,6,7,8,9,10,11,12]
        else: 
            month = [int(self.month)]
        return month

    def get_info_birthday(self,month):
        domain = [('birthday','!=',False)]
        if len(self.company) > 0:
            domain.append(('company_id','in',self.company.ids))
        obj_employee = self.env['hr.employee'].search(domain).filtered(lambda x: x.birthday.month == int(month))
        return obj_employee

    def get_name_month(self, month_number):
        """Obtiene el nombre del mes. Usa constante centralizada."""
        return get_month_name(month_number)

    def get_date_text(self, date, calculated_week=0, hide_year=0):
        """Formatea fecha en español. Usa función centralizada."""
        include_weekday = calculated_week != 0
        include_year = hide_year == 0
        return format_date_spanish(date, include_weekday=include_weekday, include_year=include_year)

    def generate_report(self):
        datas = {
             'id': self.id,
             'model': 'hr.birthday.tree'             
            }

        return {
            'type': 'ir.actions.report',
            'report_name': 'lavish_hr_employee.report_birthday_list',
            'report_type': 'qweb-pdf',
            'datas': datas        
        }      
    def build_query(self):
        # Inicializando filtros
        filters = []
        filters_dependent = []

        if self.month != '0':
            month_filter = f"date_part('month',a.birthday) = {self.month}"
            month_filter_dependent = f"date_part('month',hed.date_birthday) = {self.month}"
            filters.append(month_filter)
            filters_dependent.append(month_filter_dependent)

        company_filter = f"a.company_id in ({','.join(map(str, self.company.ids))})"
        filters.append(company_filter)
        filters_dependent.append(company_filter)

        if not self.show_dependent:
            filters.append("1=2")

        # Construyendo la consulta
        active_employee_join = f"Inner join hr_contract as hc on a.id = hc.employee_id and hc.state='open'" if self.active_employee else ''
        where_clause = " AND ".join(filters)
        where_clause_dependent = " AND ".join(filters_dependent)

        query_report = f'''
            SELECT * FROM (
                SELECT c.name, b.vat, b.name as name_employee, '' as name_dependet, '' as dependents_type,
                    a.birthday, date_part('year',age(a.birthday)) as edad
                FROM hr_employee as a
                {active_employee_join}
                LEFT JOIN res_partner as b ON b.id = a.work_contact_id
                LEFT JOIN res_company c ON c.id = a.company_id
                WHERE {where_clause}
                AND EXISTS (SELECT 1 FROM hr_contract hc WHERE a.id = hc.employee_id AND hc.state='open')
                UNION
                SELECT c."name", '' as vat, b.name as name_employee, hed.name as name_dependet,
                    upper(hed.dependents_type) as dependents_type,
                    hed.date_birthday, date_part('year',age(hed.date_birthday)) as edad
                FROM hr_employee as a
                {active_employee_join}
                LEFT JOIN hr_employee_dependents hed ON a.id = hed.employee_id
                LEFT JOIN res_partner as b ON b.id = a.work_contact_id
                LEFT JOIN res_company c ON c.id = a.company_id
                WHERE {where_clause_dependent}
                AND EXISTS (SELECT 1 FROM hr_contract hc WHERE a.id = hc.employee_id AND hc.state='open')
            ) as a
            ORDER BY name_employee, date_part('month',birthday), date_part('day',birthday)
        '''
        return query_report
    def generate_birthday_excel(self):
        # Luego, para ejecutar:
        query = self.build_query()
        _logger.info(query)
        self._cr.execute(query)
        result_query = self._cr.dictfetchall()
        _logger.info(result_query)
        if len(result_query) == 0:
            raise ValidationError(_('No se encontraron datos con los filtros seleccionados, por favor verificar.'))
        # Generar EXCEL
        filename = 'Reporte Listado de Cumpleaños'
        stream = io.BytesIO()
        book = xlsxwriter.Workbook(stream, {'in_memory': True})

        # Columnas
        columns = ['Compañia', 'Identificación', 'Empleado', 'Dependiente', 'Tipo dependiente', 'Sucursal','Fecha de cumpleaños', 'Edad']
        sheet = book.add_worksheet('Listado de Cumpleaños')

        # Agregar textos al excel
        text_title = 'Listado de Cumpleaños'
        text_generate = 'Informe generado el %s' % (datetime.now(timezone(self.env.user.tz)))
        cell_format_title = book.add_format({'bold': True, 'align': 'left'})
        cell_format_title.set_font_name('Calibri')
        cell_format_title.set_font_size(15)
        cell_format_title.set_bottom(5)
        cell_format_title.set_bottom_color('#1F497D')
        cell_format_title.set_font_color('#1F497D')
        sheet.merge_range('A1:H1', text_title, cell_format_title)
        cell_format_text_generate = book.add_format({'bold': False, 'align': 'left'})
        cell_format_text_generate.set_font_name('Calibri')
        cell_format_text_generate.set_font_size(10)
        cell_format_text_generate.set_bottom(5)
        cell_format_text_generate.set_bottom_color('#1F497D')
        cell_format_text_generate.set_font_color('#1F497D')
        sheet.merge_range('A2:H2', text_generate, cell_format_text_generate)
        # Formato para fechas
        date_format = book.add_format({'num_format': 'dd/mm/yyyy'})

        # Agregar columnas
        aument_columns = 0
        for column in columns:
            sheet.write(2, aument_columns, column)
            aument_columns = aument_columns + 1

        # Agregar query
        aument_columns = 0
        aument_rows = 3
        for query in result_query:
            for row in query.values():
                width = len(str(row)) + 10
                width = 40 if width == 10 else width
                if str(type(row)).find('date') > -1:
                    sheet.write_datetime(aument_rows, aument_columns, row, date_format)
                else:
                    sheet.write(aument_rows, aument_columns, row)
                # Ajustar tamaño columna
                sheet.set_column(aument_columns, aument_columns, width)
                aument_columns = aument_columns + 1
            aument_rows = aument_rows + 1
            aument_columns = 0

        # Convertir en tabla
        array_header_table = []
        for i in columns:
            dict = {'header': i}
            array_header_table.append(dict)

        sheet.add_table(2, 0, aument_rows-1, len(columns)-1, {'style': 'Table Style Medium 2', 'columns': array_header_table})
        # Guadar Excel
        book.close()

        self.write({
            'excel_file': base64.b64encode(stream.getvalue()).decode('utf-8'),
            'excel_file_name': filename,
        })

        action = {
            'name': 'Listado de Cumpleaños',
            'type': 'ir.actions.act_url',
            'url': "web/content/?model=hr.birthday.tree&id=" + str(
                self.id) + "&filename_field=excel_file_name&field=excel_file&download=true&filename=" + self.excel_file_name,
            'target': 'self',
        }
        return action
