# -*- coding: utf-8 -*-
"""
Modelo para generacion de reportes PDF de lineas de nomina.
Soporta agrupacion por empleado, departamento, categoria.
Ordenamiento por tipo: Devengos, Deducciones, Seguridad Social.
"""
from odoo import models, fields, api, _
from collections import defaultdict, OrderedDict


class HrPayslipLineReport(models.AbstractModel):
    """
    Modelo abstracto para generar reportes PDF de lineas de nomina.
    Usado por el reporte QWeb report_payslip_lines_grid.
    """
    _name = 'report.lavish_hr_payroll.report_payslip_lines_grid'
    _description = 'Reporte de Lineas de Nomina'

    # Orden de categorias para el reporte
    CATEGORY_ORDER = [
        'BASIC',           # Salario Basico
        'DEV_SALARIAL',    # Devengos Salariales
        'HEYREC',          # Horas Extra y Recargos
        'COMISIONES',      # Comisiones
        'AUX',             # Auxilios
        'DEV_NO_SALARIAL', # Devengos No Salariales
        'TOTALDEV',        # Total Devengos
        'SSOCIAL',         # Seguridad Social
        'DED',             # Deducciones
        'DEDUCCIONES',     # Deducciones Generales
        'TOTALDED',        # Total Deducciones
        'NET',             # Neto a Pagar
        'PROVISIONES',     # Provisiones
        'PRESTACIONES_SOCIALES',  # Prestaciones
    ]

    # Mapeo de categorias a grupos visuales
    CATEGORY_GROUPS = {
        'devengos': ['BASIC', 'DEV_SALARIAL', 'HEYREC', 'COMISIONES', 'AUX', 'DEV_NO_SALARIAL', 'TOTALDEV'],
        'deducciones': ['DED', 'DEDUCCIONES', 'TOTALDED'],
        'seguridad_social': ['SSOCIAL'],
        'neto': ['NET'],
        'provisiones': ['PROVISIONES', 'PRESTACIONES_SOCIALES'],
    }

    @api.model
    def _get_report_values(self, docids, data=None):
        """
        Prepara los datos para el reporte PDF.
        """
        data = data or {}

        # Obtener parametros
        payslip_run_id = data.get('payslip_run_id')
        employee_ids = data.get('employee_ids', [])
        department_ids = data.get('department_ids', [])
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

        # Obtener lineas
        lines = self.env['hr.payslip.line'].search(domain, order='slip_id, sequence')

        # Preparar datos agrupados
        grouped_data = self._group_lines(lines, group_by)

        # Calcular totales generales
        totals = self._calculate_totals(lines)

        # Obtener info del lote
        payslip_run = None
        if payslip_run_id:
            payslip_run = self.env['hr.payslip.run'].browse(payslip_run_id)

        return {
            'doc_ids': docids,
            'doc_model': 'hr.payslip.run',
            'docs': payslip_run,
            'data': data,
            'grouped_data': grouped_data,
            'totals': totals,
            'group_by': group_by,
            'company': self.env.company,
            'category_labels': self._get_category_labels(),
            'format_currency': self._format_currency,
        }

    def _group_lines(self, lines, group_by):
        """
        Agrupa las lineas segun el criterio seleccionado.
        Retorna un OrderedDict con la estructura:
        {
            group_key: {
                'name': 'Nombre del Grupo',
                'employee_data': {...},  # Solo para group_by != employee
                'categories': {
                    'devengos': [lines...],
                    'deducciones': [lines...],
                    'seguridad_social': [lines...],
                    'neto': [lines...],
                    'provisiones': [lines...],
                },
                'subtotals': {...},
            }
        }
        """
        grouped = OrderedDict()

        for line in lines:
            # Determinar clave de agrupacion
            if group_by == 'employee':
                key = line.slip_id.employee_id.id
                name = line.slip_id.employee_id.name
                extra_data = {
                    'identification': line.slip_id.employee_id.identification_id or '',
                    'department': line.slip_id.employee_id.department_id.name or '',
                    'job': line.slip_id.employee_id.job_id.name or '',
                    'contract': line.slip_id.contract_id.name or '',
                }
            elif group_by == 'department':
                dept = line.slip_id.employee_id.department_id
                key = dept.id if dept else 0
                name = dept.name if dept else 'Sin Departamento'
                extra_data = {'employee_count': 0}
            elif group_by == 'category':
                cat = line.category_id
                key = cat.id if cat else 0
                name = cat.name if cat else 'Sin Categoria'
                extra_data = {}
            else:
                key = 'all'
                name = 'Todas las Lineas'
                extra_data = {}

            # Inicializar grupo si no existe
            if key not in grouped:
                grouped[key] = {
                    'name': name,
                    'extra_data': extra_data,
                    'categories': {
                        'devengos': [],
                        'deducciones': [],
                        'seguridad_social': [],
                        'neto': [],
                        'provisiones': [],
                        'otros': [],
                    },
                    'subtotals': {
                        'devengos': 0,
                        'deducciones': 0,
                        'seguridad_social': 0,
                        'neto': 0,
                        'provisiones': 0,
                    },
                    'employees': set(),
                }

            # Agregar empleado al set
            grouped[key]['employees'].add(line.slip_id.employee_id.id)

            # Clasificar linea en categoria
            cat_code = line.category_id.code if line.category_id else ''
            category_group = self._get_category_group(cat_code)

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
                'sequence': line.sequence,
            }

            grouped[key]['categories'][category_group].append(line_data)

            # Actualizar subtotales
            if category_group in grouped[key]['subtotals']:
                grouped[key]['subtotals'][category_group] += line.total or 0

        # Ordenar lineas dentro de cada categoria
        for group_data in grouped.values():
            group_data['employee_count'] = len(group_data['employees'])
            del group_data['employees']  # No necesitamos el set en el reporte

            for cat_key in group_data['categories']:
                group_data['categories'][cat_key].sort(
                    key=lambda x: (self._get_category_order(x['category_code']), x['sequence'])
                )

        return grouped

    def _get_category_group(self, category_code):
        """Determina a que grupo pertenece una categoria."""
        for group_name, codes in self.CATEGORY_GROUPS.items():
            if category_code in codes:
                return group_name
        return 'otros'

    def _get_category_order(self, category_code):
        """Retorna el orden de una categoria."""
        try:
            return self.CATEGORY_ORDER.index(category_code)
        except ValueError:
            return 999

    def _calculate_totals(self, lines):
        """Calcula los totales generales del reporte."""
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
            elif cat_code in ['PROVISIONES', 'PRESTACIONES_SOCIALES']:
                totals['provisiones'] += line.total or 0

        totals['employee_count'] = len(employees)

        return totals

    def _get_category_labels(self):
        """Retorna etiquetas para las categorias."""
        return {
            'devengos': 'Devengos',
            'deducciones': 'Deducciones',
            'seguridad_social': 'Seguridad Social',
            'neto': 'Neto a Pagar',
            'provisiones': 'Provisiones',
            'otros': 'Otros Conceptos',
        }

    def _format_currency(self, value):
        """Formatea un valor como moneda colombiana."""
        if value is None:
            return '$ 0'
        return '$ {:,.0f}'.format(value).replace(',', '.')
