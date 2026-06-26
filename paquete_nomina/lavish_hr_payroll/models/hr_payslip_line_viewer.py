# -*- coding: utf-8 -*-
"""
Modelo para visualizacion de lineas de nomina con grid interactivo.
Soporta filtros por lote, empleado, agrupacion y navegacion.
"""
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from collections import defaultdict


class HrPayslipLineViewer(models.TransientModel):
    """
    Visor de lineas de nomina con funcionalidades avanzadas:
    - Filtros por lote, empleado, departamento, categoria
    - Agrupacion por diferentes criterios
    - Navegacion directa a registros
    - Exportacion a Excel/PDF
    """
    _name = 'hr.payslip.line.viewer'
    _description = 'Visor de Lineas de Nomina'

    # Filtros principales
    payslip_run_ids = fields.Many2many(
        'hr.payslip.run',
        'payslip_line_viewer_run_rel',
        'viewer_id', 'run_id',
        string='Lotes de Nomina',
        domain="[('state', '!=', 'draft')]"
    )
    employee_ids = fields.Many2many(
        'hr.employee',
        'payslip_line_viewer_employee_rel',
        'viewer_id', 'employee_id',
        string='Empleados'
    )
    department_ids = fields.Many2many(
        'hr.department',
        'payslip_line_viewer_dept_rel',
        'viewer_id', 'department_id',
        string='Departamentos'
    )
    category_ids = fields.Many2many(
        'hr.salary.rule.category',
        'payslip_line_viewer_cat_rel',
        'viewer_id', 'category_id',
        string='Categorias'
    )
    salary_rule_ids = fields.Many2many(
        'hr.salary.rule',
        'payslip_line_viewer_rule_rel',
        'viewer_id', 'rule_id',
        string='Reglas Salariales'
    )

    # Filtros de fecha
    date_from = fields.Date(string='Fecha Desde')
    date_to = fields.Date(string='Fecha Hasta')

    # Opciones de agrupacion
    group_by = fields.Selection([
        ('none', 'Sin Agrupar'),
        ('employee', 'Por Empleado'),
        ('department', 'Por Departamento'),
        ('category', 'Por Categoria'),
        ('rule', 'Por Regla Salarial'),
        ('payslip_run', 'Por Lote'),
        ('month', 'Por Mes'),
    ], string='Agrupar Por', default='employee')

    # Opciones de visualizacion
    show_zero_lines = fields.Boolean(string='Mostrar Lineas en Cero', default=False)
    show_subtotals = fields.Boolean(string='Mostrar Subtotales', default=True)
    show_totals = fields.Boolean(string='Mostrar Totales', default=True)

    # Resultados
    line_ids = fields.One2many(
        'hr.payslip.line.viewer.line',
        'viewer_id',
        string='Lineas'
    )
    total_devengos = fields.Float(string='Total Devengos', compute='_compute_totals')
    total_deducciones = fields.Float(string='Total Deducciones', compute='_compute_totals')
    total_neto = fields.Float(string='Total Neto', compute='_compute_totals')
    employee_count = fields.Integer(string='Cantidad de empleados', compute='_compute_totals')

    @api.depends('line_ids')
    def _compute_totals(self):
        for viewer in self:
            lines = viewer.line_ids.filtered(lambda l: not l.is_subtotal and not l.is_total)
            viewer.total_devengos = sum(
                l.amount for l in lines
                if l.rule_id and l.rule_id._get_afecta_totales_effective() == 'devengo'
            )
            viewer.total_deducciones = sum(
                l.amount for l in lines
                if l.rule_id and l.rule_id._get_afecta_totales_effective() == 'deduccion'
            )
            neto_lines = lines.filtered(lambda l: l.rule_code == 'NET')
            viewer.total_neto = sum(neto_lines.mapped('amount'))
            viewer.employee_count = len(set(lines.mapped('employee_id').ids))

    def action_load_lines(self):
        """Carga las lineas segun los filtros seleccionados."""
        self.ensure_one()

        # Limpiar lineas anteriores
        self.line_ids.unlink()

        # Construir dominio de busqueda
        domain = self._build_payslip_domain()

        # Obtener payslips
        payslips = self.env['hr.payslip'].search(domain)

        if not payslips:
            raise ValidationError(_('No se encontraron nominas con los filtros seleccionados.'))

        # Usar servicio optimizado
        from .services.payroll_report_query_service import PayrollReportQueryService
        query_service = PayrollReportQueryService(self.env)

        # Obtener datos en batch
        payslip_ids = payslips.ids
        lines_by_slip = query_service.get_payslip_lines_by_payslip(
            payslip_ids,
            include_zero=self.show_zero_lines
        )
        employees_data = query_service.get_employees_data(
            list(set(payslips.mapped('employee_id.id')))
        )
        payslips_data = query_service.get_payslips_data(payslip_ids)

        # Crear lineas del visor
        viewer_lines = []
        groups_data = defaultdict(list)

        for slip_id, lines in lines_by_slip.items():
            slip_data = payslips_data.get(slip_id, {})
            emp_id = slip_data.get('employee_id', [None])[0]
            emp_data = employees_data.get(emp_id, {})

            for line in lines:
                # Aplicar filtros adicionales
                if self.category_ids:
                    cat_id = line['category_id'][0] if line.get('category_id') else None
                    if cat_id and cat_id not in self.category_ids.ids:
                        continue

                if self.salary_rule_ids:
                    rule_id = line['salary_rule_id'][0] if line.get('salary_rule_id') else None
                    if rule_id and rule_id not in self.salary_rule_ids.ids:
                        continue

                line_vals = self._prepare_line_vals(line, slip_data, emp_data)
                group_key = self._get_group_key(line_vals)
                groups_data[group_key].append(line_vals)

        # Crear lineas ordenadas por grupo
        sequence = 0
        for group_key in sorted(groups_data.keys()):
            group_lines = groups_data[group_key]

            for line_vals in group_lines:
                sequence += 1
                line_vals['sequence'] = sequence
                line_vals['viewer_id'] = self.id
                viewer_lines.append((0, 0, line_vals))

            # Agregar subtotal si aplica
            if self.show_subtotals and self.group_by != 'none':
                sequence += 1
                subtotal_vals = self._create_subtotal_line(group_key, group_lines, sequence)
                subtotal_vals['viewer_id'] = self.id
                viewer_lines.append((0, 0, subtotal_vals))

        # Agregar total general
        if self.show_totals:
            all_lines = [vals for group in groups_data.values() for vals in group]
            sequence += 1
            total_vals = self._create_total_line(all_lines, sequence)
            total_vals['viewer_id'] = self.id
            viewer_lines.append((0, 0, total_vals))

        self.line_ids = viewer_lines

        return {
            'type': 'ir.actions.act_window',
            'name': _('Lineas de Nomina'),
            'res_model': 'hr.payslip.line.viewer',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _build_payslip_domain(self):
        """Construye el dominio de busqueda para payslips."""
        domain = [('state', 'in', ('validated', 'paid'))]

        if self.payslip_run_ids:
            domain.append(('payslip_run_id', 'in', self.payslip_run_ids.ids))

        if self.employee_ids:
            domain.append(('employee_id', 'in', self.employee_ids.ids))

        if self.department_ids:
            domain.append(('employee_id.department_id', 'in', self.department_ids.ids))

        if self.date_from:
            domain.append(('date_from', '>=', self.date_from))

        if self.date_to:
            domain.append(('date_to', '<=', self.date_to))

        return domain

    def _prepare_line_vals(self, line_data, slip_data, emp_data):
        """Prepara los valores para crear una linea del visor."""
        return {
            'payslip_id': slip_data.get('id'),
            'payslip_name': slip_data.get('name', ''),
            'payslip_run_id': slip_data.get('payslip_run_id', [None, ''])[0],
            'payslip_run_name': slip_data.get('payslip_run_id', [None, ''])[1] if slip_data.get('payslip_run_id') else '',
            'employee_id': emp_data.get('id'),
            'employee_name': emp_data.get('name', ''),
            'employee_identification': emp_data.get('identification_id', ''),
            'department_id': emp_data.get('department_id', [None])[0] if emp_data.get('department_id') else None,
            'department_name': emp_data.get('department_id', [None, ''])[1] if emp_data.get('department_id') else '',
            'rule_id': line_data.get('salary_rule_id', [None])[0] if line_data.get('salary_rule_id') else None,
            'rule_name': line_data.get('salary_rule_id', [None, ''])[1] if line_data.get('salary_rule_id') else '',
            'rule_code': line_data.get('code', ''),
            'category_id': line_data.get('category_id', [None])[0] if line_data.get('category_id') else None,
            'category_name': line_data.get('category_id', [None, ''])[1] if line_data.get('category_id') else '',
            'category_code': '',  # Se obtendra del lookup
            'quantity': line_data.get('quantity', 0),
            'rate': line_data.get('rate', 0),
            'amount': line_data.get('total', 0),
            'amount_base': line_data.get('amount_base', 0),
            'date_from': slip_data.get('date_from'),
            'date_to': slip_data.get('date_to'),
            'line_id': line_data.get('id'),
        }

    def _get_group_key(self, line_vals):
        """Obtiene la clave de agrupacion segun la configuracion."""
        if self.group_by == 'employee':
            return (line_vals.get('employee_name', ''), line_vals.get('employee_id', 0))
        elif self.group_by == 'department':
            return (line_vals.get('department_name', ''), line_vals.get('department_id', 0))
        elif self.group_by == 'category':
            return (line_vals.get('category_name', ''), line_vals.get('category_id', 0))
        elif self.group_by == 'rule':
            return (line_vals.get('rule_name', ''), line_vals.get('rule_id', 0))
        elif self.group_by == 'payslip_run':
            return (line_vals.get('payslip_run_name', ''), line_vals.get('payslip_run_id', 0))
        elif self.group_by == 'month':
            date = line_vals.get('date_from')
            if date:
                return (f"{date.year}-{date.month:02d}", 0)
            return ('Sin Fecha', 0)
        return ('Todo', 0)

    def _create_subtotal_line(self, group_key, lines, sequence):
        """Crea una linea de subtotal para un grupo."""
        total_amount = sum(l.get('amount', 0) for l in lines)
        return {
            'sequence': sequence,
            'is_subtotal': True,
            'group_name': f'Subtotal: {group_key[0]}',
            'amount': total_amount,
            'employee_name': '',
            'rule_name': '',
        }

    def _create_total_line(self, lines, sequence):
        """Crea la linea de total general."""
        total_amount = sum(l.get('amount', 0) for l in lines)
        return {
            'sequence': sequence,
            'is_total': True,
            'group_name': 'TOTAL GENERAL',
            'amount': total_amount,
            'employee_name': '',
            'rule_name': '',
        }

    def action_export_excel(self):
        """Exporta las lineas a Excel."""
        # TODO: Implementar exportacion a Excel
        return True

    def action_export_pdf(self):
        """Exporta las lineas a PDF."""
        # TODO: Implementar exportacion a PDF
        return True


class HrPayslipLineViewerLine(models.TransientModel):
    """Linea individual del visor de nominas."""
    _name = 'hr.payslip.line.viewer.line'
    _description = 'Linea del Visor de Nomina'
    _order = 'sequence, id'

    viewer_id = fields.Many2one(
        'hr.payslip.line.viewer',
        string='Visor',
        ondelete='cascade'
    )
    sequence = fields.Integer(string='Secuencia', default=10)

    # Referencias a registros originales
    payslip_id = fields.Many2one('hr.payslip', string='Nomina')
    payslip_name = fields.Char(string='Nombre Nomina')
    payslip_run_id = fields.Many2one('hr.payslip.run', string='Lote')
    payslip_run_name = fields.Char(string='Nombre Lote')
    line_id = fields.Many2one('hr.payslip.line', string='Linea Original')

    # Datos del empleado
    employee_id = fields.Many2one('hr.employee', string='Empleado')
    employee_name = fields.Char(string='Nombre Empleado')
    employee_identification = fields.Char(string='Identificacion')
    department_id = fields.Many2one('hr.department', string='Departamento')
    department_name = fields.Char(string='Nombre Departamento')

    # Datos de la regla
    rule_id = fields.Many2one('hr.salary.rule', string='Regla Salarial')
    rule_name = fields.Char(string='Nombre Regla')
    rule_code = fields.Char(string='Codigo Regla')
    category_id = fields.Many2one('hr.salary.rule.category', string='Categoria')
    category_name = fields.Char(string='Nombre Categoria')
    category_code = fields.Char(string='Codigo Categoria')

    # Valores
    quantity = fields.Float(string='Cantidad')
    rate = fields.Float(string='Tasa (%)')
    amount = fields.Float(string='Monto')
    amount_base = fields.Float(string='Base')

    # Fechas
    date_from = fields.Date(string='Fecha Desde')
    date_to = fields.Date(string='Fecha Hasta')

    # Flags para subtotales/totales
    is_subtotal = fields.Boolean(string='Es Subtotal', default=False)
    is_total = fields.Boolean(string='Es Total', default=False)
    group_name = fields.Char(string='Nombre Grupo')

    def action_open_payslip(self):
        """Navega a la nomina relacionada."""
        self.ensure_one()
        if self.payslip_id:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Nomina'),
                'res_model': 'hr.payslip',
                'res_id': self.payslip_id.id,
                'view_mode': 'form',
                'target': 'current',
            }
        return False

    def action_open_employee(self):
        """Navega al empleado relacionado."""
        self.ensure_one()
        if self.employee_id:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Empleado'),
                'res_model': 'hr.employee',
                'res_id': self.employee_id.id,
                'view_mode': 'form',
                'target': 'current',
            }
        return False

    def action_open_line(self):
        """Navega a la linea original."""
        self.ensure_one()
        if self.line_id:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Linea de Nomina'),
                'res_model': 'hr.payslip.line',
                'res_id': self.line_id.id,
                'view_mode': 'form',
                'target': 'current',
            }
        return False
