# -*- coding: utf-8 -*-
"""
Controlador para el Grid de Lineas de Nomina.
Genera PDF y Excel con estructura agrupada.
"""
import json
import io
import base64
from datetime import datetime
from collections import OrderedDict

from odoo import http, fields, _
from odoo.http import request, content_disposition


class PayslipLineGridController(http.Controller):
    """
    Controlador para generar reportes del Grid de Lineas.
    """

    # Orden de categorias
    CATEGORY_ORDER = {
        'BASIC': 1,
        'DEV_SALARIAL': 2,
        'HEYREC': 3,
        'COMISIONES': 4,
        'AUX': 5,
        'DEV_NO_SALARIAL': 6,
        'TOTALDEV': 7,
        'SSOCIAL': 10,
        'DED': 20,
        'DEDUCCIONES': 21,
        'TOTALDED': 22,
        'NET': 30,
        'PROVISIONES': 40,
        'PRESTACIONES_SOCIALES': 41,
    }

    CATEGORY_GROUPS = {
        'devengos': ['BASIC', 'DEV_SALARIAL', 'HEYREC', 'COMISIONES', 'AUX', 'DEV_NO_SALARIAL', 'TOTALDEV'],
        'seguridad_social': ['SSOCIAL'],
        'deducciones': ['DED', 'DEDUCCIONES', 'TOTALDED'],
        'neto': ['NET'],
        'provisiones': ['PROVISIONES', 'PRESTACIONES_SOCIALES'],
    }

    DEFAULT_STATES = ['verify', 'done', 'paid']

    def _parse_states(self, selected_states=None):
        """Normaliza el filtro de estados recibido por query/json."""
        if not selected_states:
            return list(self.DEFAULT_STATES)
        if isinstance(selected_states, str):
            try:
                parsed = json.loads(selected_states)
                if isinstance(parsed, list):
                    return parsed or list(self.DEFAULT_STATES)
            except Exception:
                return [selected_states]
        if isinstance(selected_states, list):
            return selected_states or list(self.DEFAULT_STATES)
        return list(self.DEFAULT_STATES)

    @http.route('/payroll/grid/data', type='jsonrpc', auth='user')
    def get_grid_data(self, payslip_run_id=None, employee_id=None, department_id=None,
                      group_by='employee', show_zero=False, selected_states=None, **kwargs):
        """
        Obtiene los datos del grid con agrupacion y ordenamiento.
        """
        domain = [('slip_id.state', 'in', self._parse_states(selected_states))]

        if payslip_run_id:
            domain.append(('slip_id.payslip_run_id', '=', int(payslip_run_id)))
        if employee_id:
            domain.append(('slip_id.employee_id', '=', int(employee_id)))
        if department_id:
            domain.append(('slip_id.employee_id.department_id', '=', int(department_id)))

        lines = request.env['hr.payslip.line'].sudo().search(domain, order='slip_id, sequence')

        grouped_data = self._group_lines(lines, group_by)
        totals = self._calculate_totals(lines)

        return {
            'success': True,
            'grouped_data': grouped_data,
            'totals': totals,
        }

    @http.route('/payroll/grid/pdf', type='http', auth='user')
    def generate_pdf(self, payslip_run_id=None, employee_ids=None, department_ids=None,
                     group_by='employee', show_zero=False, selected_states=None, **kwargs):
        """
        Genera el PDF del reporte usando QWeb.
        """
        # Preparar datos
        data = {
            'payslip_run_id': int(payslip_run_id) if payslip_run_id else None,
            'employee_ids': json.loads(employee_ids) if employee_ids else [],
            'department_ids': json.loads(department_ids) if department_ids else [],
            'group_by': group_by,
            'show_zero': show_zero == 'true',
            'selected_states': self._parse_states(selected_states),
        }

        # Generar PDF usando el reporte QWeb
        report = request.env.ref('lavish_hr_payroll.action_report_payslip_lines_grid')

        # En Odoo 19 la firma es _render_qweb_pdf(report_ref, res_ids=None, data=None)
        # Pasar el nombre del reporte como report_ref y None como res_ids
        pdf_content, _ = report.sudo()._render_qweb_pdf(report.report_name, res_ids=None, data=data)

        # Nombre del archivo
        if data['payslip_run_id']:
            payslip_run = request.env['hr.payslip.run'].sudo().browse(data['payslip_run_id'])
            filename = 'Lineas_Nomina_%s_%s.pdf' % (
                payslip_run.name.replace(' ', '_') if payslip_run else '',
                datetime.now().strftime('%Y%m%d_%H%M')
            )
        else:
            filename = 'Lineas_Nomina_%s.pdf' % datetime.now().strftime('%Y%m%d_%H%M')

        return request.make_response(
            pdf_content,
            headers=[
                ('Content-Type', 'application/pdf'),
                ('Content-Disposition', content_disposition(filename)),
            ]
        )

    @http.route('/payroll/grid/excel', type='http', auth='user')
    def generate_excel(self, payslip_run_id=None, employee_ids=None, department_ids=None,
                       group_by='employee', show_zero=False, selected_states=None, **kwargs):
        """
        Genera el Excel del reporte.
        """
        try:
            import xlsxwriter
        except ImportError:
            return request.make_response(
                json.dumps({'error': 'xlsxwriter no instalado'}),
                headers=[('Content-Type', 'application/json')]
            )

        # Construir dominio
        domain = [('slip_id.state', 'in', self._parse_states(selected_states))]

        if payslip_run_id:
            domain.append(('slip_id.payslip_run_id', '=', int(payslip_run_id)))
        if employee_ids:
            emp_ids = json.loads(employee_ids) if isinstance(employee_ids, str) else employee_ids
            if emp_ids:
                domain.append(('slip_id.employee_id', 'in', emp_ids))
        if department_ids:
            dept_ids = json.loads(department_ids) if isinstance(department_ids, str) else department_ids
            if dept_ids:
                domain.append(('slip_id.employee_id.department_id', 'in', dept_ids))

        lines = request.env['hr.payslip.line'].sudo().search(domain, order='slip_id, sequence')

        # Crear Excel
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})

        # Formatos
        header_format = workbook.add_format({
            'bold': True, 'bg_color': '#2c3e50', 'font_color': 'white',
            'border': 1, 'align': 'center', 'valign': 'vcenter'
        })
        group_format = workbook.add_format({
            'bold': True, 'bg_color': '#3498db', 'font_color': 'white',
            'border': 1
        })
        devengos_format = workbook.add_format({
            'bg_color': '#e8f5e9', 'border': 1
        })
        deducciones_format = workbook.add_format({
            'bg_color': '#ffebee', 'border': 1
        })
        ss_format = workbook.add_format({
            'bg_color': '#f3e5f5', 'border': 1
        })
        money_format = workbook.add_format({
            'num_format': '$ #,##0.00', 'border': 1, 'align': 'right'
        })
        total_format = workbook.add_format({
            'bold': True, 'bg_color': '#2c3e50', 'font_color': 'white',
            'num_format': '$ #,##0.00', 'border': 1, 'align': 'right'
        })

        # Hoja principal
        sheet = workbook.add_worksheet('Lineas de Nomina')
        sheet.set_column('A:A', 35)  # Empleado
        sheet.set_column('B:B', 12)  # Identificacion
        sheet.set_column('C:C', 30)  # Concepto
        sheet.set_column('D:D', 12)  # Codigo
        sheet.set_column('E:E', 18)  # Categoria
        sheet.set_column('F:F', 10)  # Cantidad
        sheet.set_column('G:G', 10)  # Tasa
        sheet.set_column('H:H', 15)  # Base
        sheet.set_column('I:I', 15)  # Total

        # Encabezados
        headers = ['Empleado', 'Identificacion', 'Concepto', 'Codigo',
                   'Categoria', 'Cantidad', 'Tasa %', 'Base', 'Total']
        for col, header in enumerate(headers):
            sheet.write(0, col, header, header_format)

        row = 1

        # Agrupar datos
        grouped = self._group_lines(lines, group_by)
        # Catalogo global de conceptos/reglas para no omitir columnas/filas por empleado.
        master_concepts = OrderedDict()
        for line in lines:
            if not line.code:
                continue
            if line.code not in master_concepts:
                cat_code = line.category_id.code if line.category_id else ''
                master_concepts[line.code] = {
                    'code': line.code,
                    'name': line.name or line.code,
                    'category': line.category_id.name if line.category_id else '',
                    'category_code': cat_code,
                    'sequence': line.sequence or 0,
                    'order': self.CATEGORY_ORDER.get(cat_code, 99),
                }
        master_concepts = sorted(
            master_concepts.values(),
            key=lambda x: (x['order'], x['sequence'], x['code'])
        )

        for group_key, group_data in grouped.items():
            # Header del grupo
            sheet.merge_range(row, 0, row, 8, group_data['name'], group_format)
            row += 1

            # Mapa de lineas existentes en el grupo por codigo para completar faltantes en cero.
            group_lines_by_code = OrderedDict()
            for cat_key in ['devengos', 'seguridad_social', 'deducciones', 'neto', 'provisiones', 'otros']:
                for line in group_data['categories'].get(cat_key, []):
                    code = line.get('code')
                    if not code:
                        continue
                    if code in group_lines_by_code:
                        # Si hay duplicados de codigo en el mismo grupo, consolidar valores.
                        group_lines_by_code[code]['quantity'] = (
                            group_lines_by_code[code].get('quantity', 0) + (line.get('quantity') or 0)
                        )
                        group_lines_by_code[code]['amount'] = (
                            group_lines_by_code[code].get('amount', 0) + (line.get('amount') or 0)
                        )
                        group_lines_by_code[code]['total'] = (
                            group_lines_by_code[code].get('total', 0) + (line.get('total') or 0)
                        )
                    else:
                        group_lines_by_code[code] = dict(line)

            # Construir salida final garantizando todas las reglas del lote.
            all_lines = []
            for concept in master_concepts:
                existing = group_lines_by_code.get(concept['code'])
                if existing:
                    all_lines.append(existing)
                else:
                    all_lines.append({
                        'name': concept['name'],
                        'code': concept['code'],
                        'category': concept['category'],
                        'category_code': concept['category_code'],
                        'quantity': 0,
                        'rate': 0,
                        'amount': 0,
                        'total': 0,
                        'employee_name': group_data.get('name', ''),
                        'identification': group_data.get('extra', {}).get('identification', ''),
                        'sequence': concept['sequence'],
                        'order': concept['order'],
                    })

            for line in all_lines:
                cat_code = line.get('category_code', '')

                # Seleccionar formato segun categoria
                if cat_code in self.CATEGORY_GROUPS['devengos']:
                    cell_format = devengos_format
                elif cat_code in self.CATEGORY_GROUPS['deducciones']:
                    cell_format = deducciones_format
                elif cat_code in self.CATEGORY_GROUPS['seguridad_social']:
                    cell_format = ss_format
                else:
                    cell_format = None

                sheet.write(row, 0, line.get('employee_name', ''), cell_format)
                sheet.write(row, 1, line.get('identification', ''), cell_format)
                sheet.write(row, 2, line.get('name', ''), cell_format)
                sheet.write(row, 3, line.get('code', ''), cell_format)
                sheet.write(row, 4, line.get('category', ''), cell_format)
                sheet.write(row, 5, line.get('quantity', 0) if line.get('quantity', 1) != 1 else '', cell_format)
                sheet.write(row, 6, line.get('rate', 0) if line.get('rate', 100) != 100 else '', cell_format)
                sheet.write(row, 7, line.get('amount', 0), money_format)
                sheet.write(row, 8, line.get('total', 0), money_format)
                row += 1

            # Subtotales del grupo
            sheet.write(row, 7, 'Subtotal:', total_format)
            sheet.write(row, 8, sum(l.get('total', 0) for l in all_lines), total_format)
            row += 2

        # Totales generales
        totals = self._calculate_totals(lines)
        row += 1
        sheet.merge_range(row, 0, row, 6, 'TOTALES GENERALES', header_format)
        sheet.write(row, 7, 'Devengos:', total_format)
        sheet.write(row, 8, totals['devengos'], total_format)
        row += 1
        sheet.write(row, 7, 'Deducciones:', total_format)
        sheet.write(row, 8, totals['deducciones'], total_format)
        row += 1
        sheet.write(row, 7, 'Seg. Social:', total_format)
        sheet.write(row, 8, totals['seguridad_social'], total_format)
        row += 1
        sheet.write(row, 7, 'Neto:', total_format)
        sheet.write(row, 8, totals['neto'], total_format)

        workbook.close()
        output.seek(0)

        filename = 'Lineas_Nomina_%s.xlsx' % datetime.now().strftime('%Y%m%d_%H%M')

        return request.make_response(
            output.read(),
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', content_disposition(filename)),
            ]
        )

    @http.route('/payroll/grid/excel_compiled', type='http', auth='user')
    def generate_excel_compiled(self, payslip_run_id=None, employee_ids=None, department_ids=None,
                                selected_states=None, **kwargs):
        """
        Genera un Excel compilado (matriz):
        Filas = empleados, Columnas = reglas/conceptos, con total al final.
        """
        try:
            import xlsxwriter
        except ImportError:
            return request.make_response(
                json.dumps({'error': 'xlsxwriter no instalado'}),
                headers=[('Content-Type', 'application/json')]
            )

        payslip_domain = [('state', 'in', self._parse_states(selected_states))]

        if payslip_run_id:
            payslip_domain.append(('payslip_run_id', '=', int(payslip_run_id)))
        if employee_ids:
            emp_ids = json.loads(employee_ids) if isinstance(employee_ids, str) else employee_ids
            if emp_ids:
                payslip_domain.append(('employee_id', 'in', emp_ids))
        if department_ids:
            dept_ids = json.loads(department_ids) if isinstance(department_ids, str) else department_ids
            if dept_ids:
                payslip_domain.append(('employee_id.department_id', 'in', dept_ids))

        payslips = request.env['hr.payslip'].sudo().search(payslip_domain, order='employee_id')
        payslip_ids = payslips.ids
        employees = payslips.mapped('employee_id').sorted(key=lambda e: e.name or '')

        line_domain = [('slip_id', 'in', payslip_ids)] if payslip_ids else [('id', '=', 0)]
        lines = request.env['hr.payslip.line'].sudo().search(line_domain, order='sequence, id')

        # Catalogo global de reglas (todas las columnas).
        master_rules = OrderedDict()
        for line in lines:
            code = line.code or ''
            if not code or code in master_rules:
                continue
            cat_code = line.category_id.code if line.category_id else ''
            master_rules[code] = {
                'code': code,
                'name': line.name or code,
                'order': self.CATEGORY_ORDER.get(cat_code, 99),
                'sequence': line.sequence or 0,
            }
        master_rules = sorted(master_rules.values(), key=lambda x: (x['order'], x['sequence'], x['code']))

        # Matriz empleado x regla.
        matrix = {emp.id: {rule['code']: 0 for rule in master_rules} for emp in employees}
        for line in lines:
            emp_id = line.slip_id.employee_id.id
            code = line.code or ''
            if emp_id in matrix and code in matrix[emp_id]:
                matrix[emp_id][code] += (line.total or 0)

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Compilado')

        header_format = workbook.add_format({
            'bold': True, 'bg_color': '#0f172a', 'font_color': 'white',
            'border': 1, 'align': 'center', 'valign': 'vcenter'
        })
        header_left_format = workbook.add_format({
            'bold': True, 'bg_color': '#0f172a', 'font_color': 'white',
            'border': 1, 'align': 'left', 'valign': 'vcenter'
        })
        text_format = workbook.add_format({'border': 1, 'align': 'left'})
        text_center_format = workbook.add_format({'border': 1, 'align': 'center'})
        number_format = workbook.add_format({'border': 1, 'align': 'right', 'num_format': '#,##0.00'})
        empty_value_format = workbook.add_format({'border': 1, 'align': 'center', 'font_color': '#64748b'})
        total_format = workbook.add_format({'border': 1, 'align': 'right', 'bold': True, 'num_format': '$ #,##0.00'})

        # Encabezados base
        base_headers = ['EMPLEADO', 'ID', 'DEPARTAMENTO', 'CARGO']
        for col, header in enumerate(base_headers):
            fmt = header_left_format if col == 0 else header_format
            sheet.write(0, col, header, fmt)

        # Encabezados reglas
        col = len(base_headers)
        for rule in master_rules:
            sheet.write(0, col, (rule['name'] or rule['code']).upper(), header_format)
            col += 1

        # Total final
        total_col = col
        sheet.write(0, total_col, 'TOTAL', header_format)

        # Anchos columnas
        sheet.set_column(0, 0, 34)
        sheet.set_column(1, 1, 12)
        sheet.set_column(2, 2, 34)
        sheet.set_column(3, 3, 30)
        if master_rules:
            sheet.set_column(4, total_col - 1, 16)
        sheet.set_column(total_col, total_col, 16)

        # Freeze panel similar a la grilla
        sheet.freeze_panes(1, 4)

        # Filas empleados
        row = 1
        for emp in employees:
            sheet.write(row, 0, emp.name or '', text_format)
            sheet.write(row, 1, emp.identification_id or '', text_center_format)
            sheet.write(row, 2, emp.department_id.name or '', text_center_format)
            sheet.write(row, 3, emp.job_id.name or '', text_center_format)

            row_total = 0
            col = 4
            for rule in master_rules:
                value = matrix.get(emp.id, {}).get(rule['code'], 0) or 0
                row_total += value
                if abs(value) < 0.000001:
                    sheet.write(row, col, '-', empty_value_format)
                else:
                    sheet.write_number(row, col, value, number_format)
                col += 1

            sheet.write_number(row, total_col, row_total, total_format)
            row += 1

        workbook.close()
        output.seek(0)

        filename = 'Lineas_Nomina_Compilado_%s.xlsx' % datetime.now().strftime('%Y%m%d_%H%M')
        return request.make_response(
            output.read(),
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', content_disposition(filename)),
            ]
        )

    def _group_lines(self, lines, group_by):
        """Agrupa las lineas segun el criterio."""
        grouped = OrderedDict()

        for line in lines:
            # Determinar clave de agrupacion
            if group_by == 'employee':
                key = line.slip_id.employee_id.id
                name = line.slip_id.employee_id.name
                extra = {
                    'identification': line.slip_id.employee_id.identification_id or '',
                    'department': line.slip_id.employee_id.department_id.name or '',
                }
            elif group_by == 'department':
                dept = line.slip_id.employee_id.department_id
                key = dept.id if dept else 0
                name = dept.name if dept else 'Sin Departamento'
                extra = {}
            elif group_by == 'category':
                cat = line.category_id
                key = cat.id if cat else 0
                name = cat.name if cat else 'Sin Categoria'
                extra = {}
            else:
                key = 'all'
                name = 'Todas'
                extra = {}

            if key not in grouped:
                grouped[key] = {
                    'name': name,
                    'extra': extra,
                    'categories': {
                        'devengos': [],
                        'seguridad_social': [],
                        'deducciones': [],
                        'neto': [],
                        'provisiones': [],
                        'otros': [],
                    },
                    'subtotals': {k: 0 for k in ['devengos', 'seguridad_social', 'deducciones', 'neto', 'provisiones']},
                    'employees': set(),
                }

            grouped[key]['employees'].add(line.slip_id.employee_id.id)

            # Clasificar linea
            cat_code = line.category_id.code if line.category_id else ''
            cat_group = self._get_category_group(cat_code)

            line_data = {
                'id': line.id,
                'name': line.name,
                'code': line.code,
                'category': line.category_id.name if line.category_id else '',
                'category_code': cat_code,
                'quantity': line.quantity,
                'rate': line.rate,
                'amount': line.amount,
                'total': line.total,
                'employee_name': line.slip_id.employee_id.name,
                'identification': line.slip_id.employee_id.identification_id or '',
                'sequence': line.sequence,
                'order': self.CATEGORY_ORDER.get(cat_code, 99),
            }

            grouped[key]['categories'][cat_group].append(line_data)
            if cat_group in grouped[key]['subtotals']:
                grouped[key]['subtotals'][cat_group] += line.total or 0

        # Ordenar lineas y convertir sets
        for group_data in grouped.values():
            group_data['employee_count'] = len(group_data['employees'])
            group_data['employees'] = list(group_data['employees'])

            for cat_key in group_data['categories']:
                group_data['categories'][cat_key].sort(key=lambda x: (x['order'], x['sequence']))

        return grouped

    def _get_category_group(self, cat_code):
        """Determina el grupo de una categoria."""
        for group, codes in self.CATEGORY_GROUPS.items():
            if cat_code in codes:
                return group
        return 'otros'

    def _calculate_totals(self, lines):
        """Calcula totales generales."""
        totals = {
            'devengos': 0,
            'deducciones': 0,
            'seguridad_social': 0,
            'neto': 0,
            'provisiones': 0,
            'employee_count': 0,
            'line_count': len(lines),
        }

        employees = set()

        for line in lines:
            employees.add(line.slip_id.employee_id.id)
            cat_code = line.category_id.code if line.category_id else ''

            if cat_code == 'TOTALDEV':
                totals['devengos'] += line.total or 0
            elif cat_code == 'TOTALDED':
                totals['deducciones'] += abs(line.total or 0)
            elif cat_code == 'NET':
                totals['neto'] += line.total or 0
            elif cat_code == 'SSOCIAL':
                totals['seguridad_social'] += abs(line.total or 0)

        totals['employee_count'] = len(employees)
        return totals
