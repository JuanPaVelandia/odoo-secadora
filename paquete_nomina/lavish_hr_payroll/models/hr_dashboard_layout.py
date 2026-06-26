# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import json


class HRDashboard(models.Model):
    """Dashboards personalizados del usuario"""

    _name = 'hr.dashboard'
    _description = 'HR Dashboard'
    _order = 'sequence, id'

    name = fields.Char(
        string='Nombre',
        required=True,
        translate=True
    )

    user_id = fields.Many2one(
        'res.users',
        string='Usuario',
        required=True,
        default=lambda self: self.env.user,
        ondelete='cascade',
        index=True
    )

    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
        ondelete='cascade'
    )

    sequence = fields.Integer(
        string='Secuencia',
        default=10
    )

    is_default = fields.Boolean(
        string='Dashboard por Defecto',
        default=False,
        help='Este dashboard se cargará automáticamente al abrir el módulo'
    )

    widget_ids = fields.One2many(
        'hr.dashboard.widget',
        'dashboard_id',
        string='Widgets'
    )

    active = fields.Boolean(
        default=True
    )

    grid_columns = fields.Integer(
        string='Columnas del Grid',
        default=4,
        help='Número de columnas del grid (recomendado: 4 o 12)'
    )

    @api.constrains('is_default')
    def _check_single_default(self):
        """Solo puede haber un dashboard por defecto por usuario"""
        for dashboard in self:
            if dashboard.is_default:
                other_defaults = self.search([
                    ('user_id', '=', dashboard.user_id.id),
                    ('company_id', '=', dashboard.company_id.id),
                    ('is_default', '=', True),
                    ('id', '!=', dashboard.id)
                ])
                if other_defaults:
                    raise ValidationError(_('Solo puede haber un dashboard por defecto por usuario'))

    def action_set_default(self):
        """Marca este dashboard como predeterminado"""
        self.ensure_one()
        # Desmarcar otros dashboards por defecto
        self.search([
            ('user_id', '=', self.user_id.id),
            ('company_id', '=', self.company_id.id),
            ('is_default', '=', True),
            ('id', '!=', self.id)
        ]).write({'is_default': False})

        self.is_default = True

    def action_duplicate(self):
        """Duplica este dashboard"""
        self.ensure_one()
        new_dashboard = self.copy({'name': _('%s (copia)') % self.name})
        return {
            'type': 'ir.actions.act_window',
            'name': _('Dashboard'),
            'res_model': 'hr.dashboard',
            'res_id': new_dashboard.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.model
    def get_user_dashboards(self):
        """Obtiene todos los dashboards del usuario actual"""
        dashboards = self.search([
            ('user_id', '=', self.env.user.id),
            ('company_id', '=', self.env.company.id),
            ('active', '=', True)
        ])

        return [{
            'id': d.id,
            'name': d.name,
            'is_default': d.is_default,
            'grid_columns': d.grid_columns,
            'widgets': [{
                'id': w.id,
                'widget_type': w.widget_type,
                'row': w.row,
                'col': w.col,
                'colspan': w.colspan,
                'rowspan': w.rowspan,
                'visible': w.visible,
                'collapsed': w.collapsed,
            } for w in d.widget_ids]
        } for d in dashboards]

    @api.model
    def get_default_dashboard(self):
        """Obtiene el dashboard por defecto del usuario o crea uno si no existe"""
        dashboard = self.search([
            ('user_id', '=', self.env.user.id),
            ('company_id', '=', self.env.company.id),
            ('is_default', '=', True),
            ('active', '=', True)
        ], limit=1)

        if not dashboard:
            # Si no tiene dashboard, crear uno por defecto
            dashboard = self.create({
                'name': _('Dashboard Principal'),
                'user_id': self.env.user.id,
                'company_id': self.env.company.id,
                'is_default': True,
                'grid_columns': 4,
            })

            # Crear widgets por defecto
            self._create_default_widgets(dashboard)

        return {
            'id': dashboard.id,
            'name': dashboard.name,
            'is_default': dashboard.is_default,
            'grid_columns': dashboard.grid_columns,
            'widgets': [{
                'id': w.id,
                'widget_type': w.widget_type,
                'row': w.row,
                'col': w.col,
                'colspan': w.colspan,
                'rowspan': w.rowspan,
                'visible': w.visible,
                'collapsed': w.collapsed,
            } for w in dashboard.widget_ids]
        }

    @api.model
    def _create_default_widgets(self, dashboard):
        """Crea los widgets por defecto para un dashboard nuevo"""
        widget_obj = self.env['hr.dashboard.widget']

        default_widgets = [
            # Row 0: KPIs Generales
            {'widget_type': 'kpi_employees', 'row': 0, 'col': 0, 'colspan': 1},
            {'widget_type': 'kpi_devengado', 'row': 0, 'col': 1, 'colspan': 1},
            {'widget_type': 'kpi_overtime', 'row': 0, 'col': 2, 'colspan': 1},
            {'widget_type': 'kpi_payslips', 'row': 0, 'col': 3, 'colspan': 1},

            # Row 1: KPIs Indicadores
            {'widget_type': 'kpi_accidents', 'row': 1, 'col': 0, 'colspan': 1},
            {'widget_type': 'kpi_absences', 'row': 1, 'col': 1, 'colspan': 1},
            {'widget_type': 'kpi_pending', 'row': 1, 'col': 2, 'colspan': 1},
            {'widget_type': 'kpi_new_employees', 'row': 1, 'col': 3, 'colspan': 1},

            # Row 2: KPIs Retenciones
            {'widget_type': 'kpi_retention_base', 'row': 2, 'col': 0, 'colspan': 2},
            {'widget_type': 'kpi_retention_total', 'row': 2, 'col': 2, 'colspan': 2},

            # Row 3: KPIs Alertas
            {'widget_type': 'kpi_without_ss', 'row': 3, 'col': 0, 'colspan': 1},
            {'widget_type': 'kpi_without_payslip', 'row': 3, 'col': 1, 'colspan': 1},
            {'widget_type': 'kpi_without_settlement', 'row': 3, 'col': 2, 'colspan': 1},

            # Row 4: Charts
            {'widget_type': 'chart_social_security', 'row': 4, 'col': 0, 'colspan': 2},
            {'widget_type': 'chart_income_deductions', 'row': 4, 'col': 2, 'colspan': 2},

            # Row 5: Charts & Lists
            {'widget_type': 'chart_disability', 'row': 5, 'col': 0, 'colspan': 2},
            {'widget_type': 'list_batches', 'row': 5, 'col': 2, 'colspan': 2},

            # Row 6: Management Cards
            {'widget_type': 'card_expiring_contracts', 'row': 6, 'col': 0, 'colspan': 1},
            {'widget_type': 'card_payment_schedule', 'row': 6, 'col': 1, 'colspan': 1},
            {'widget_type': 'card_pending_leaves', 'row': 6, 'col': 2, 'colspan': 1},

            # Row 7: New Employees
            {'widget_type': 'card_new_employees', 'row': 7, 'col': 0, 'colspan': 4},

            # Row 8: Payslips Table
            {'widget_type': 'list_payslips', 'row': 8, 'col': 0, 'colspan': 4},
        ]

        for widget_data in default_widgets:
            widget_obj.create({
                'dashboard_id': dashboard.id,
                **widget_data
            })

    @api.model
    def save_dashboard_layout(self, dashboard_id, widgets_data):
        """Guarda el layout de un dashboard"""
        dashboard = self.browse(dashboard_id)
        if not dashboard.exists() or dashboard.user_id != self.env.user:
            raise ValidationError(_('Dashboard no encontrado o sin permisos'))

        widget_obj = self.env['hr.dashboard.widget']

        for widget_data in widgets_data:
            widget_id = widget_data.get('id')
            if widget_id:
                widget = widget_obj.browse(widget_id)
                if widget.exists() and widget.dashboard_id == dashboard:
                    widget.write({
                        'row': widget_data.get('row', widget.row),
                        'col': widget_data.get('col', widget.col),
                        'colspan': widget_data.get('colspan', widget.colspan),
                        'rowspan': widget_data.get('rowspan', widget.rowspan),
                        'visible': widget_data.get('visible', widget.visible),
                        'collapsed': widget_data.get('collapsed', widget.collapsed),
                    })

        return True


class HRDashboardWidget(models.Model):
    """Widgets individuales de un dashboard"""

    _name = 'hr.dashboard.widget'
    _description = 'Dashboard Widget'
    _order = 'row, col'

    dashboard_id = fields.Many2one(
        'hr.dashboard',
        string='Dashboard',
        required=True,
        ondelete='cascade',
        index=True
    )

    widget_type = fields.Selection(
        selection=[
            # KPIs
            ('kpi_employees', 'Total Empleados'),
            ('kpi_devengado', 'Total Devengado'),
            ('kpi_overtime', 'Promedio Horas Extras'),
            ('kpi_payslips', 'Nóminas del Período'),
            ('kpi_accidents', 'Accidentes Laborales'),
            ('kpi_absences', 'Ausencias en Período'),
            ('kpi_pending', 'Solicitudes Pendientes'),
            ('kpi_new_employees', 'Nuevos Empleados'),
            ('kpi_retention_base', 'Base Retención'),
            ('kpi_retention_total', 'Total Retenido'),
            ('kpi_without_ss', 'Sin Seguridad Social'),
            ('kpi_without_payslip', 'Sin Nómina'),
            ('kpi_without_settlement', 'Sin Liquidación'),
            # Charts
            ('chart_social_security', 'Gráfico Seguridad Social'),
            ('chart_income_deductions', 'Gráfico Ingresos/Deducciones'),
            ('chart_disability', 'Gráfico Incapacidades'),
            # Lists
            ('list_batches', 'Lista de Lotes'),
            ('list_payslips', 'Lista de Nóminas'),
            # Cards
            ('card_expiring_contracts', 'Contratos por Vencer'),
            ('card_payment_schedule', 'Cronograma de Pagos'),
            ('card_pending_leaves', 'Ausencias Pendientes'),
            ('card_new_employees', 'Empleados Nuevos'),
        ],
        string='Tipo de Widget',
        required=True
    )

    row = fields.Integer(
        string='Fila',
        default=0,
        help='Posición vertical (fila) en el grid'
    )

    col = fields.Integer(
        string='Columna',
        default=0,
        help='Posición horizontal (columna) en el grid'
    )

    colspan = fields.Integer(
        string='Ancho (columnas)',
        default=1,
        help='Cuántas columnas ocupa el widget (1-4 o 1-12 según grid)'
    )

    rowspan = fields.Integer(
        string='Alto (filas)',
        default=1,
        help='Cuántas filas ocupa el widget'
    )

    visible = fields.Boolean(
        string='Visible',
        default=True
    )

    collapsed = fields.Boolean(
        string='Colapsado',
        default=False
    )

    sequence = fields.Integer(
        string='Secuencia',
        default=10
    )

    def action_toggle_visibility(self):
        """Alterna la visibilidad del widget"""
        self.visible = not self.visible

    def action_toggle_collapse(self):
        """Alterna el estado colapsado del widget"""
        self.collapsed = not self.collapsed

    def action_move_up(self):
        """Mueve el widget una fila hacia arriba"""
        if self.row > 0:
            self.row -= 1

    def action_move_down(self):
        """Mueve el widget una fila hacia abajo"""
        self.row += 1

    def action_move_left(self):
        """Mueve el widget una columna a la izquierda"""
        if self.col > 0:
            self.col -= 1

    def action_move_right(self):
        """Mueve el widget una columna a la derecha"""
        max_col = self.dashboard_id.grid_columns - self.colspan
        if self.col < max_col:
            self.col += 1
