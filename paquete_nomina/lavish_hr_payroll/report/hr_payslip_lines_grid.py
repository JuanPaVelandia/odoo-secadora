# -*- coding: utf-8 -*-
"""
Modelo abstracto para el reporte de lineas de nomina en grid.
"""
from collections import OrderedDict
from odoo import models, api


class PayslipLinesGridReport(models.AbstractModel):
    _name = 'report.lavish_hr_payroll.report_payslip_lines_grid'
    _description = 'Reporte Grid Lineas de Nomina'

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

    def _format_currency(self, value):
        """Formatea valor como moneda COP."""
        if value is None:
            return '$ 0'
        return '$ {:,.0f}'.format(value).replace(',', '.')

    def _get_category_group(self, cat_code):
        """Determina el grupo de una categoria."""
        for group, codes in self.CATEGORY_GROUPS.items():
            if cat_code in codes:
                return group
        return 'otros'

    def _group_lines(self, lines, group_by='employee'):
        """Agrupa las lineas segun el criterio."""
        grouped = OrderedDict()

        for line in lines:
            # Determinar clave de agrupacion
            if group_by == 'employee':
                key = line.slip_id.employee_id.id
                name = line.slip_id.employee_id.name
                extra = {
                    'identification': line.slip_id.employee_id.identification_id or '',
                    'department': line.slip_id.employee_id.department_id.name if line.slip_id.employee_id.department_id else '',
                    'job': line.slip_id.employee_id.job_id.name if line.slip_id.employee_id.job_id else '',
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
                    'extra_data': extra,
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

    @api.model
    def _get_report_values(self, docids, data=None):
        """Prepara los valores para el reporte QWeb."""
        data = data or {}

        payslip_run_id = data.get('payslip_run_id')
        department_ids = data.get('department_ids', [])
        employee_ids = data.get('employee_ids', [])
        group_by = data.get('group_by', 'employee')
        show_zero = data.get('show_zero', False)

        # Construir dominio
        domain = [('slip_id.state', 'in', ['done', 'paid'])]

        if payslip_run_id:
            domain.append(('slip_id.payslip_run_id', '=', payslip_run_id))
        if employee_ids:
            domain.append(('slip_id.employee_id', 'in', employee_ids))
        if department_ids:
            domain.append(('slip_id.employee_id.department_id', 'in', department_ids))
        if not show_zero:
            domain.append(('total', '!=', 0))

        lines = self.env['hr.payslip.line'].sudo().search(domain, order='slip_id, sequence')

        # Obtener el payslip run si existe
        docs = False
        if payslip_run_id:
            docs = self.env['hr.payslip.run'].sudo().browse(payslip_run_id)

        grouped_data = self._group_lines(lines, group_by)
        totals = self._calculate_totals(lines)

        return {
            'doc_ids': docids,
            'doc_model': 'hr.payslip.run',
            'docs': docs,
            'data': data,
            'grouped_data': grouped_data,
            'totals': totals,
            'format_currency': self._format_currency,
        }
