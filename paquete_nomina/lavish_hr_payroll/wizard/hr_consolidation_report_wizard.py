# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import io
import logging

_logger = logging.getLogger(__name__)

try:
    import xlsxwriter
except ImportError:
    _logger.warning("xlsxwriter not installed. Excel export will not work.")
    xlsxwriter = None


class HrConsolidationReportWizard(models.TransientModel):
    _name = 'hr.consolidation.report.wizard'
    _description = 'Wizard para Reporte de Consolidación Anual'

    year = fields.Integer(
        string='Año',
        required=True,
        default=lambda self: fields.Date.today().year
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company
    )
    department_ids = fields.Many2many(
        'hr.department',
        string='Departamentos',
        help='Dejar vacío para incluir todos'
    )
    employee_ids = fields.Many2many(
        'hr.employee',
        string='Empleados',
        help='Dejar vacío para incluir todos'
    )
    include_vacaciones = fields.Boolean('Incluir Vacaciones', default=True)
    include_cesantias = fields.Boolean('Incluir Cesantías', default=True)
    include_intereses = fields.Boolean('Incluir Intereses', default=True)

    excel_file = fields.Binary('Archivo Excel', readonly=True)
    excel_filename = fields.Char('Nombre del archivo')

    def action_generate_report(self):
        """Genera el reporte Excel de consolidación"""
        if not xlsxwriter:
            raise UserError(_("La librería xlsxwriter no está instalada"))

        # Buscar nóminas de consolidación del año
        domain = [
            ('struct_process', '=', 'consolidacion'),
            ('company_id', '=', self.company_id.id),
            ('state', 'in', ['done', 'paid', 'verify']),
        ]

        # Filtrar por año
        date_start = f'{self.year}-01-01'
        date_end = f'{self.year}-12-31'
        domain += [
            ('date_from', '>=', date_start),
            ('date_to', '<=', date_end),
        ]

        if self.department_ids:
            domain.append(('department_id', 'in', self.department_ids.ids))
        if self.employee_ids:
            domain.append(('employee_id', 'in', self.employee_ids.ids))

        payslips = self.env['hr.payslip'].search(domain, order='employee_id, date_from')

        if not payslips:
            raise UserError(_("No se encontraron nóminas de consolidación para los criterios seleccionados"))

        # Generar Excel
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})

        # Formatos
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#17a2b8',
            'font_color': 'white',
            'border': 1,
            'align': 'center',
            'valign': 'vcenter',
            'text_wrap': True,
        })
        title_format = workbook.add_format({
            'bold': True,
            'font_size': 14,
            'align': 'center',
            'valign': 'vcenter',
        })
        money_format = workbook.add_format({
            'num_format': '$#,##0.00',
            'border': 1,
        })
        number_format = workbook.add_format({
            'num_format': '#,##0.00',
            'border': 1,
        })
        text_format = workbook.add_format({
            'border': 1,
        })
        total_format = workbook.add_format({
            'bold': True,
            'bg_color': '#f8f9fa',
            'num_format': '$#,##0.00',
            'border': 1,
        })
        positive_format = workbook.add_format({
            'num_format': '$#,##0.00',
            'border': 1,
            'bg_color': '#d4edda',
        })
        negative_format = workbook.add_format({
            'num_format': '$#,##0.00',
            'border': 1,
            'bg_color': '#f8d7da',
        })

        # Hoja de resumen
        self._create_summary_sheet(workbook, payslips, header_format, title_format,
                                    money_format, text_format, total_format,
                                    positive_format, negative_format)

        # Hoja de detalle por concepto
        if self.include_vacaciones:
            self._create_concept_sheet(workbook, payslips, 'CONS_VAC', 'Vacaciones',
                                       header_format, money_format, number_format,
                                       text_format, total_format)
        if self.include_cesantias:
            self._create_concept_sheet(workbook, payslips, 'CONS_CES', 'Cesantías',
                                       header_format, money_format, number_format,
                                       text_format, total_format)
        if self.include_intereses:
            self._create_concept_sheet(workbook, payslips, 'CONS_INT', 'Intereses',
                                       header_format, money_format, number_format,
                                       text_format, total_format)

        workbook.close()
        output.seek(0)

        # Guardar archivo
        self.excel_file = base64.b64encode(output.read())
        self.excel_filename = f'Consolidacion_Anual_{self.year}_{self.company_id.name}.xlsx'

        # Retornar acción para descargar
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{self._name}/{self.id}/excel_file/{self.excel_filename}?download=true',
            'target': 'new',
        }

    def _create_summary_sheet(self, workbook, payslips, header_format, title_format,
                               money_format, text_format, total_format,
                               positive_format, negative_format):
        """Crea la hoja de resumen general"""
        sheet = workbook.add_worksheet('Resumen Consolidación')

        # Título
        sheet.merge_range('A1:K1', f'CONSOLIDACIÓN ANUAL DE PRESTACIONES SOCIALES - {self.year}', title_format)
        sheet.merge_range('A2:K2', f'Compañía: {self.company_id.name}', title_format)

        # Encabezados
        headers = [
            'No.', 'Identificación', 'Empleado', 'Departamento', 'Cargo',
            'Salario Base', 'Ajuste Vacaciones', 'Ajuste Cesantías',
            'Ajuste Intereses', 'Total Ajuste', 'Estado'
        ]

        row = 4
        for col, header in enumerate(headers):
            sheet.write(row, col, header, header_format)

        # Anchos de columna
        sheet.set_column(0, 0, 5)    # No.
        sheet.set_column(1, 1, 15)   # Identificación
        sheet.set_column(2, 2, 30)   # Empleado
        sheet.set_column(3, 3, 20)   # Departamento
        sheet.set_column(4, 4, 20)   # Cargo
        sheet.set_column(5, 5, 15)   # Salario
        sheet.set_column(6, 8, 18)   # Ajustes
        sheet.set_column(9, 9, 18)   # Total
        sheet.set_column(10, 10, 12) # Estado

        # Datos
        row = 5
        totals = {'vac': 0, 'ces': 0, 'int': 0, 'total': 0}
        num = 1

        for payslip in payslips:
            employee = payslip.employee_id
            contract = payslip.contract_id

            # Obtener líneas de consolidación
            vac_line = payslip.line_ids.filtered(lambda l: l.code == 'CONS_VAC')
            ces_line = payslip.line_ids.filtered(lambda l: l.code == 'CONS_CES')
            int_line = payslip.line_ids.filtered(lambda l: l.code == 'CONS_INT')

            vac_amount = vac_line.total if vac_line else 0
            ces_amount = ces_line.total if ces_line else 0
            int_amount = int_line.total if int_line else 0
            total_amount = vac_amount + ces_amount + int_amount

            totals['vac'] += vac_amount
            totals['ces'] += ces_amount
            totals['int'] += int_amount
            totals['total'] += total_amount

            sheet.write(row, 0, num, text_format)
            sheet.write(row, 1, employee.identification_id or '', text_format)
            sheet.write(row, 2, employee.name, text_format)
            sheet.write(row, 3, employee.department_id.name or '', text_format)
            sheet.write(row, 4, employee.job_id.name or '', text_format)
            sheet.write(row, 5, contract.wage if contract else 0, money_format)

            # Usar formatos condicionales para ajustes
            vac_fmt = positive_format if vac_amount >= 0 else negative_format
            ces_fmt = positive_format if ces_amount >= 0 else negative_format
            int_fmt = positive_format if int_amount >= 0 else negative_format
            total_fmt = positive_format if total_amount >= 0 else negative_format

            sheet.write(row, 6, vac_amount, vac_fmt)
            sheet.write(row, 7, ces_amount, ces_fmt)
            sheet.write(row, 8, int_amount, int_fmt)
            sheet.write(row, 9, total_amount, total_fmt)
            sheet.write(row, 10, dict(payslip._fields['state'].selection).get(payslip.state, ''), text_format)

            row += 1
            num += 1

        # Fila de totales
        sheet.write(row, 5, 'TOTALES:', total_format)
        sheet.write(row, 6, totals['vac'], total_format)
        sheet.write(row, 7, totals['ces'], total_format)
        sheet.write(row, 8, totals['int'], total_format)
        sheet.write(row, 9, totals['total'], total_format)

    def _create_concept_sheet(self, workbook, payslips, code, concept_name,
                               header_format, money_format, number_format,
                               text_format, total_format):
        """Crea una hoja de detalle por concepto"""
        sheet = workbook.add_worksheet(f'Detalle {concept_name}')

        # Encabezados específicos según el concepto
        if code == 'CONS_VAC':
            headers = [
                'No.', 'Identificación', 'Empleado', 'Días Trabajados',
                'Días Causados', 'Días Disfrutados', 'Días Pendientes',
                'Base Promedio', 'Valor Real', 'Provisión Acumulada',
                'Liquidaciones Año', 'Ajuste Final'
            ]
        else:
            headers = [
                'No.', 'Identificación', 'Empleado', 'Días Trabajados',
                'Base Mensual', 'Auxilio Transporte', 'Variable Promedio',
                'Base Promedio', 'Valor Real', 'Provisión Acumulada',
                'Liquidaciones Año', 'Ajuste Final'
            ]

        row = 0
        for col, header in enumerate(headers):
            sheet.write(row, col, header, header_format)

        # Anchos
        sheet.set_column(0, 0, 5)
        sheet.set_column(1, 1, 15)
        sheet.set_column(2, 2, 30)
        sheet.set_column(3, 11, 15)

        row = 1
        total_ajuste = 0
        num = 1

        for payslip in payslips:
            line = payslip.line_ids.filtered(lambda l: l.code == code)
            if not line:
                continue

            employee = payslip.employee_id

            # Obtener data_visual del log si está disponible
            data = {}
            if line.log_compute_visual:
                try:
                    import json
                    data = json.loads(line.log_compute_visual) if isinstance(line.log_compute_visual, str) else {}
                except (KeyError, AttributeError):
                    data = {}

            sheet.write(row, 0, num, text_format)
            sheet.write(row, 1, employee.identification_id or '', text_format)
            sheet.write(row, 2, employee.name, text_format)
            sheet.write(row, 3, data.get('dias_ano', 0), number_format)

            if code == 'CONS_VAC':
                data_calculo = data.get('data_calculo', {})
                sheet.write(row, 4, data_calculo.get('dias_causados', 0), number_format)
                sheet.write(row, 5, data_calculo.get('dias_disfrutados', 0), number_format)
                sheet.write(row, 6, data_calculo.get('dias_pendientes', 0), number_format)
                sheet.write(row, 7, data_calculo.get('base_promedio', 0), money_format)
            else:
                data_calculo = data.get('data_calculo', {})
                sheet.write(row, 4, data_calculo.get('base_mensual', 0), money_format)
                sheet.write(row, 5, data_calculo.get('auxilio', 0), money_format)
                sheet.write(row, 6, (data_calculo.get('variable_anual', 0) / max(data.get('dias_ano', 1), 1) * 30), money_format)
                sheet.write(row, 7, data_calculo.get('base_promedio', 0), money_format)

            sheet.write(row, 8, data.get('valor_real', 0), money_format)
            sheet.write(row, 9, abs(data.get('saldo_contable', 0)), money_format)
            sheet.write(row, 10, data.get('liquidaciones_ano', 0), money_format)
            sheet.write(row, 11, line.total, money_format)

            total_ajuste += line.total
            row += 1
            num += 1

        # Total
        sheet.write(row, 10, 'TOTAL:', total_format)
        sheet.write(row, 11, total_ajuste, total_format)
