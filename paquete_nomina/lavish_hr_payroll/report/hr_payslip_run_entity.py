from odoo import tools
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime

import base64
import io
import json
import xlsxwriter

class HrPayslipRun(models.Model):
    _inherit = 'hr.payslip.run'

    excel_report_entity = fields.Binary(string='Reporte por fondos')
    excel_report_entity_filename = fields.Char(string='Filename reporte por fondos')
    excel_consolidated = fields.Binary(string='Reporte consolidado')
    excel_consolidated_filename = fields.Char(string='Filename reporte consolidado')

    # Reporte liquidacion lote por entidad
    def generate_settlement_report_entity(self):
        # Obtener líneas via search_read para compatibilidad JSONB Odoo 17
        lines_data = self.env['hr.payslip.line'].search_read(
            [
                ('slip_id.payslip_run_id', '=', self.id),
                ('entity_id', '!=', False),
            ],
            fields=['quantity', 'total', 'slip_id', 'entity_id'],
        )

        # Cargar entidades y empleados en batch
        entity_ids = list({l['entity_id'][0] for l in lines_data if l.get('entity_id')})
        slip_ids = list({l['slip_id'][0] for l in lines_data if l.get('slip_id')})

        entities_data = self.env['hr.employee.entities'].search_read(
            [('id', 'in', entity_ids)], fields=['partner_id'],
        )
        ent_map = {e['id']: e for e in entities_data}

        partner_ids = list({e['partner_id'][0] for e in entities_data if e.get('partner_id')})
        partners_data = self.env['res.partner'].search_read(
            [('id', 'in', partner_ids)], fields=['name'],
        )
        partner_map = {p['id']: p.get('name', '') for p in partners_data}

        slips_data = self.env['hr.payslip'].search_read(
            [('id', 'in', slip_ids)], fields=['employee_id'],
        )
        slip_map = {s['id']: s for s in slips_data}

        emp_ids = list({s['employee_id'][0] for s in slips_data if s.get('employee_id')})
        emps_data = self.env['hr.employee'].search_read(
            [('id', 'in', emp_ids)], fields=['name', 'identification_id'],
        )
        emp_map = {e['id']: e for e in emps_data}

        result_query = []
        for line in lines_data:
            ent_rec = ent_map.get((line.get('entity_id') or [False])[0], {})
            partner_id = (ent_rec.get('partner_id') or [False])[0]
            slip_rec = slip_map.get((line.get('slip_id') or [False])[0], {})
            emp_id = (slip_rec.get('employee_id') or [False])[0]
            emp_rec = emp_map.get(emp_id, {})

            result_query.append({
                'entidad': partner_map.get(partner_id, ''),
                'nombreempleado': emp_rec.get('name', ''),
                'identificacionempleado': emp_rec.get('identification_id', ''),
                'tiempo': line.get('quantity', 0),
                'unidades': (30 / 360.0) * (line.get('quantity') or 0),
                'valor': line.get('total', 0),
            })

        # Generar EXCEL
        filename = f'Reporte por fondos {self.name}'
        stream = io.BytesIO()
        book = xlsxwriter.Workbook(stream, {'in_memory': True})

        # Columnas
        columns = ['Entidad', 'Nombre del empleado', 'Identificación', 'Tiempo', 'Unidades', 'Valor liquidado']
        sheet = book.add_worksheet('Reporte por fondos')

        # Agregar textos al excel
        text_company = self.company_id.name
        text_title = f'Liquidacion - {self.name}'
        text_generate = 'Informe generado el %s' % (datetime.now())
        cell_format_title = book.add_format({'bold': True, 'align': 'left'})
        cell_format_title.set_font_name('Calibri')
        cell_format_title.set_font_size(15)
        cell_format_title.set_bottom(5)
        cell_format_title.set_bottom_color('#1F497D')
        cell_format_title.set_font_color('#1F497D')
        sheet.merge_range('A1:F1', text_company, cell_format_title)
        sheet.merge_range('A2:F2', text_title, cell_format_title)
        cell_format_text_generate = book.add_format({'bold': False, 'align': 'left'})
        cell_format_text_generate.set_font_name('Calibri')
        cell_format_text_generate.set_font_size(10)
        cell_format_text_generate.set_bottom(5)
        cell_format_text_generate.set_bottom_color('#1F497D')
        cell_format_text_generate.set_font_color('#1F497D')
        sheet.merge_range('A3:F3', text_generate, cell_format_text_generate)

        # Formato para fechas
        date_format = book.add_format({'num_format': 'dd/mm/yyyy'})

        # Agregar columnas
        aument_columns = 0
        for column in columns:
            sheet.write(3, aument_columns, column)
            aument_columns = aument_columns + 1

        # Agregar query
        aument_columns = 0
        aument_rows = 4
        for query in result_query:
            for row in query.values():
                width = len(str(row)) + 10
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

        sheet.add_table(3, 0, aument_rows, 5, {'style': 'Table Style Medium 2', 'columns': array_header_table})

        # Guadar Excel
        book.close()

        self.write({
            'excel_report_entity': base64.b64encode(stream.getvalue()).decode('utf-8'),
            'excel_report_entity_filename': filename,
        })

        action = {
            'name': 'Reporte por fondos',
            'type': 'ir.actions.act_url',
            'url': "web/content/?model=hr.payslip.run&id=" + str(
                self.id) + "&filename_field=excel_report_entity_filename&field=excel_report_entity&download=true&filename=" + self.excel_report_entity_filename,
            'target': 'self',
        }
        return action

    # Reporte Excel Consolidado para Consolidación Anual
    def generate_excel_consolidado(self):
        """Genera reporte Excel consolidado con datos estructurados de computation."""
        self.ensure_one()

        if not self.slip_ids:
            raise UserError(_('No hay nóminas en este lote para generar el consolidado.'))

        # ── 1. Obtener datos via search_read ────────────────────────────
        slip_ids = self.slip_ids.ids

        slips_data = self.env['hr.payslip'].search_read(
            [('id', 'in', slip_ids)],
            fields=['employee_id', 'contract_id'],
        )
        slip_map = {s['id']: s for s in slips_data}

        emp_ids = list({s['employee_id'][0] for s in slips_data if s['employee_id']})
        employees_data = self.env['hr.employee'].search_read(
            [('id', 'in', emp_ids)],
            fields=['name', 'identification_id', 'department_id', 'job_id'],
        )
        emp_map = {e['id']: e for e in employees_data}

        con_ids = list({s['contract_id'][0] for s in slips_data if s['contract_id']})
        contracts_data = self.env['hr.contract'].search_read(
            [('id', 'in', con_ids)],
            fields=['date_start', 'wage'],
        )
        con_map = {c['id']: c for c in contracts_data}

        # Obtener días de licencia por contrato en el período
        leave_days_by_con = {}
        if self.date_start and self.date_end and con_ids:
            ll_data = self.env['hr.leave.line'].search_read(
                [
                    ('leave_id.contract_id', 'in', con_ids),
                    ('date', '>=', self.date_start),
                    ('date', '<=', self.date_end),
                    ('state', 'in', ('done', 'validated')),
                ],
                fields=['leave_id'],
            )
            if ll_data:
                ll_leave_ids = list({l['leave_id'][0] for l in ll_data if l.get('leave_id')})
                ll_leaves = self.env['hr.leave'].search_read(
                    [('id', 'in', ll_leave_ids)], fields=['contract_id'],
                )
                ll_con_map = {lv['id']: (lv.get('contract_id') or [False])[0] for lv in ll_leaves}
                for ll in ll_data:
                    lid = (ll.get('leave_id') or [False])[0]
                    cid = ll_con_map.get(lid)
                    if cid:
                        leave_days_by_con[cid] = leave_days_by_con.get(cid, 0) + 1

        lines_data = self.env['hr.payslip.line'].search_read(
            [
                ('slip_id', 'in', slip_ids),
                ('category_id.code', 'not in', ['COMP_TOT', 'COMPAÑIA']),
                ('total', '!=', 0),
            ],
            fields=['code', 'name', 'total', 'quantity', 'amount',
                    'computation', 'slip_id', 'salary_rule_id'],
        )

        if not lines_data:
            raise UserError(_('No se encontraron líneas con valor para generar el consolidado.'))

        # ── 2. Detectar conceptos y parsear computation ─────────────────
        # Sub-columnas por concepto
        SUB_COLS = ['Días Trab.', 'Variable', 'Base Mensual', 'Obligación', 'Valor Contable', 'Ajuste']
        NUM_SUB = len(SUB_COLS)

        rule_codes_ordered = []
        rule_names = {}

        # {emp_key: {info, conceptos: {code: {total, dias, variable, base, obligacion, valor_contable, ajuste}}}}
        employees = {}

        for line in lines_data:
            slip_rec = slip_map.get(line['slip_id'][0], {})
            emp_id = slip_rec.get('employee_id', [False])[0]
            con_id = slip_rec.get('contract_id', [False])[0]
            emp_rec = emp_map.get(emp_id, {})
            con_rec = con_map.get(con_id, {})

            emp_key = emp_rec.get('identification_id') or emp_rec.get('name', '')
            code = line.get('code', '')

            if emp_key not in employees:
                employees[emp_key] = {
                    'empleado': emp_rec.get('name', ''),
                    'identificacion': emp_rec.get('identification_id', ''),
                    'departamento': (emp_rec.get('department_id') or [False, ''])[1],
                    'cargo': (emp_rec.get('job_id') or [False, ''])[1],
                    'fecha_ingreso': con_rec.get('date_start'),
                    'salario': con_rec.get('wage', 0),
                    'dias_licencia': leave_days_by_con.get(con_id, 0),
                    'conceptos': {},
                }

            if code not in rule_names:
                rule_names[code] = (line.get('salary_rule_id') or [False, code])[1] or code
                rule_codes_ordered.append(code)

            # Parsear computation JSON
            comp = {}
            raw_comp = line.get('computation') or ''
            if raw_comp:
                try:
                    comp = json.loads(raw_comp)
                except (json.JSONDecodeError, TypeError):
                    comp = {}

            metricas = comp.get('metricas', {})
            saldo_contable = comp.get('saldo_contable', {})

            dias = metricas.get('dias_trabajados', line.get('quantity') or 0)
            variable = metricas.get('promedio', 0)
            base_mensual = metricas.get('base_mensual', 0)
            obligacion = metricas.get('valor_total', 0) or comp.get('obligacion_real', 0)
            valor_contable = (
                saldo_contable.get('provision_acumulada', 0)
                or comp.get('provision_acumulada', 0)
            )
            ajuste = line.get('total', 0)

            employees[emp_key]['conceptos'][code] = {
                'total': ajuste,
                'dias': dias,
                'variable': variable,
                'base_mensual': base_mensual,
                'obligacion': obligacion,
                'valor_contable': valor_contable,
                'ajuste': ajuste,
            }

        # Ordenar empleados por nombre
        employees = dict(sorted(employees.items(), key=lambda x: x[1].get('empleado', '')))

        # ── 3. Generar EXCEL ────────────────────────────────────────────
        filename = f'Consolidado {self.name}'
        stream = io.BytesIO()
        book = xlsxwriter.Workbook(stream, {'in_memory': True})

        # Formatos base
        fmt_title = book.add_format({
            'bold': True, 'align': 'center', 'font_name': 'Calibri',
            'font_size': 14, 'bottom': 5, 'bottom_color': '#1F497D',
            'font_color': '#1F497D',
        })
        fmt_subtitle = book.add_format({
            'bold': False, 'align': 'center', 'font_name': 'Calibri',
            'font_size': 10, 'bottom': 2, 'bottom_color': '#1F497D',
            'font_color': '#1F497D',
        })
        fmt_group_header = book.add_format({
            'bold': True, 'align': 'center', 'font_name': 'Calibri',
            'font_size': 10, 'bg_color': '#1F497D', 'font_color': 'white',
            'border': 1,
        })
        fmt_header = book.add_format({
            'bold': True, 'align': 'center', 'font_name': 'Calibri',
            'font_size': 8, 'bg_color': '#2E75B6', 'font_color': 'white',
            'border': 1, 'text_wrap': True,
        })
        fmt_header_fixed = book.add_format({
            'bold': True, 'align': 'center', 'font_name': 'Calibri',
            'font_size': 9, 'bg_color': '#1F497D', 'font_color': 'white',
            'border': 1, 'text_wrap': True,
        })
        fmt_currency = book.add_format({
            'num_format': '#,##0', 'font_name': 'Calibri', 'font_size': 9,
        })
        fmt_integer = book.add_format({
            'num_format': '0', 'font_name': 'Calibri', 'font_size': 9,
            'align': 'center',
        })
        fmt_text = book.add_format({
            'font_name': 'Calibri', 'font_size': 9,
        })
        fmt_date = book.add_format({
            'num_format': 'dd/mm/yyyy', 'font_name': 'Calibri', 'font_size': 9,
        })
        # Formato ajuste: positivo=verde ▲, negativo=rojo ▼, cero=gris
        fmt_ajuste = book.add_format({
            'num_format': '[Color10]"▲ "#,##0;[Red]"▼ "#,##0;"—"',
            'font_name': 'Calibri', 'font_size': 9, 'bold': True,
        })
        fmt_total_currency = book.add_format({
            'bold': True, 'num_format': '#,##0', 'font_name': 'Calibri',
            'font_size': 9, 'top': 2, 'top_color': '#1F497D',
        })
        fmt_total_int = book.add_format({
            'bold': True, 'num_format': '0', 'font_name': 'Calibri',
            'font_size': 9, 'top': 2, 'top_color': '#1F497D', 'align': 'center',
        })
        fmt_total_ajuste = book.add_format({
            'bold': True,
            'num_format': '[Color10]"▲ "#,##0;[Red]"▼ "#,##0;"—"',
            'font_name': 'Calibri', 'font_size': 9,
            'top': 2, 'top_color': '#1F497D',
        })
        fmt_total_label = book.add_format({
            'bold': True, 'font_name': 'Calibri', 'font_size': 9,
            'top': 2, 'top_color': '#1F497D',
        })

        sheet = book.add_worksheet('Consolidado')

        # ── Dimensiones ──
        fixed_cols = ['Nombre', 'Identificación', 'Departamento', 'Cargo', 'Fecha Ingreso', 'Salario', 'Días Licencia']
        num_fixed = len(fixed_cols)
        num_concepts = len(rule_codes_ordered)
        total_cols = num_fixed + (num_concepts * NUM_SUB)

        # ── Títulos (filas 0-2) ──
        last_col = max(total_cols - 1, 0)
        last_letter = xlsxwriter.utility.xl_col_to_name(last_col)
        sheet.merge_range(f'A1:{last_letter}1', self.company_id.name or '', fmt_title)
        sheet.merge_range(f'A2:{last_letter}2', f'Consolidado - {self.name}', fmt_title)
        period_text = ''
        if self.date_start and self.date_end:
            period_text = f'Período: {self.date_start.strftime("%d/%m/%Y")} al {self.date_end.strftime("%d/%m/%Y")}'
        sheet.merge_range(f'A3:{last_letter}3', period_text, fmt_subtitle)

        # ── Fila 3: Headers de grupo (merge por concepto) ──
        row_group = 3
        # Fixed cols: merge vertical rows 3-4
        for col_idx, col_name in enumerate(fixed_cols):
            sheet.merge_range(row_group, col_idx, row_group + 1, col_idx, col_name, fmt_header_fixed)

        # Concept group headers: merge horizontal spanning SUB_COLS
        for ci, code in enumerate(rule_codes_ordered):
            start_col = num_fixed + ci * NUM_SUB
            end_col = start_col + NUM_SUB - 1
            label = rule_names.get(code, code)
            if NUM_SUB > 1:
                sheet.merge_range(row_group, start_col, row_group, end_col, label, fmt_group_header)
            else:
                sheet.write(row_group, start_col, label, fmt_group_header)

        # ── Fila 4: Sub-headers por concepto ──
        row_sub = 4
        for ci, code in enumerate(rule_codes_ordered):
            start_col = num_fixed + ci * NUM_SUB
            for si, sub_name in enumerate(SUB_COLS):
                sheet.write(row_sub, start_col + si, sub_name, fmt_header)

        # ── Anchos de columna ──
        sheet.set_column(0, 0, 35)   # Nombre
        sheet.set_column(1, 1, 15)   # Identificación
        sheet.set_column(2, 2, 20)   # Departamento
        sheet.set_column(3, 3, 20)   # Cargo
        sheet.set_column(4, 4, 14)   # Fecha Ingreso
        sheet.set_column(5, 5, 15)   # Salario
        sheet.set_column(6, 6, 14)   # Días Licencia
        for ci in range(num_concepts):
            base_col = num_fixed + ci * NUM_SUB
            sheet.set_column(base_col, base_col, 10)       # Días
            sheet.set_column(base_col + 1, base_col + 1, 14)  # Variable
            sheet.set_column(base_col + 2, base_col + 2, 15)  # Base Mensual
            sheet.set_column(base_col + 3, base_col + 3, 15)  # Obligación
            sheet.set_column(base_col + 4, base_col + 4, 16)  # Valor Contable
            sheet.set_column(base_col + 5, base_col + 5, 16)  # Ajuste

        # ── Datos (fila 5 en adelante) ──
        row_idx = 5
        # Totales por sub-columna
        totals = {}
        total_leave_days = 0
        for code in rule_codes_ordered:
            totals[code] = {'dias': 0, 'variable': 0, 'base_mensual': 0,
                            'obligacion': 0, 'valor_contable': 0, 'ajuste': 0}

        for emp_key, emp_data in employees.items():
            sheet.write(row_idx, 0, emp_data['empleado'], fmt_text)
            sheet.write(row_idx, 1, emp_data['identificacion'], fmt_text)
            sheet.write(row_idx, 2, emp_data['departamento'], fmt_text)
            sheet.write(row_idx, 3, emp_data['cargo'], fmt_text)
            if emp_data['fecha_ingreso']:
                sheet.write_datetime(row_idx, 4, emp_data['fecha_ingreso'], fmt_date)
            else:
                sheet.write(row_idx, 4, '', fmt_text)
            sheet.write(row_idx, 5, emp_data['salario'], fmt_currency)
            sheet.write(row_idx, 6, emp_data['dias_licencia'], fmt_integer)
            total_leave_days += emp_data['dias_licencia']

            for ci, code in enumerate(rule_codes_ordered):
                base_col = num_fixed + ci * NUM_SUB
                cd = emp_data['conceptos'].get(code, {})

                dias = cd.get('dias', 0)
                variable = cd.get('variable', 0)
                base_m = cd.get('base_mensual', 0)
                oblig = cd.get('obligacion', 0)
                val_cont = cd.get('valor_contable', 0)
                ajuste = cd.get('ajuste', 0)

                sheet.write(row_idx, base_col, dias, fmt_integer)
                sheet.write(row_idx, base_col + 1, variable, fmt_currency)
                sheet.write(row_idx, base_col + 2, base_m, fmt_currency)
                sheet.write(row_idx, base_col + 3, oblig, fmt_currency)
                sheet.write(row_idx, base_col + 4, val_cont, fmt_currency)
                sheet.write(row_idx, base_col + 5, ajuste, fmt_ajuste)

                totals[code]['dias'] += dias
                totals[code]['variable'] += variable
                totals[code]['base_mensual'] += base_m
                totals[code]['obligacion'] += oblig
                totals[code]['valor_contable'] += val_cont
                totals[code]['ajuste'] += ajuste

            row_idx += 1

        # ── Fila de totales ──
        sheet.write(row_idx, 0, 'TOTALES', fmt_total_label)
        for i in range(1, num_fixed):
            sheet.write(row_idx, i, '', fmt_total_label)
        # Sobreescribir celda Días Licencia con total real
        sheet.write(row_idx, num_fixed - 1, total_leave_days, fmt_total_int)

        for ci, code in enumerate(rule_codes_ordered):
            base_col = num_fixed + ci * NUM_SUB
            t = totals[code]
            sheet.write(row_idx, base_col, t['dias'], fmt_total_int)
            sheet.write(row_idx, base_col + 1, t['variable'], fmt_total_currency)
            sheet.write(row_idx, base_col + 2, t['base_mensual'], fmt_total_currency)
            sheet.write(row_idx, base_col + 3, t['obligacion'], fmt_total_currency)
            sheet.write(row_idx, base_col + 4, t['valor_contable'], fmt_total_currency)
            sheet.write(row_idx, base_col + 5, t['ajuste'], fmt_total_ajuste)

        # ── Freeze panes: fijar columnas fijas y header rows ──
        sheet.freeze_panes(5, num_fixed)

        book.close()

        self.write({
            'excel_consolidated': base64.b64encode(stream.getvalue()).decode('utf-8'),
            'excel_consolidated_filename': filename,
        })

        return {
            'name': f'Consolidado - {self.name}',
            'type': 'ir.actions.act_url',
            'url': f"web/content/?model=hr.payslip.run&id={self.id}"
                   f"&filename_field=excel_consolidated_filename&field=excel_consolidated"
                   f"&download=true&filename={self.excel_consolidated_filename}",
            'target': 'self',
        }