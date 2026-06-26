# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class HRDashboardCopyWizard(models.TransientModel):
    """Wizard para copiar configuración de dashboard a otros usuarios"""

    _name = 'hr.dashboard.copy.wizard'
    _description = 'Copiar Dashboard a Usuarios'

    dashboard_id = fields.Many2one(
        'hr.dashboard',
        string='Dashboard a Copiar',
        required=True,
        default=lambda self: self.env.context.get('active_id'),
        help='Dashboard que se copiará a los usuarios seleccionados'
    )

    user_ids = fields.Many2many(
        'res.users',
        string='Usuarios Destino',
        required=True,
        domain=[('share', '=', False)],
        help='Usuarios a los que se copiará este dashboard'
    )

    copy_as_default = fields.Boolean(
        string='Establecer como Predeterminado',
        default=False,
        help='Si está marcado, el dashboard copiado se establecerá como predeterminado para cada usuario'
    )

    replace_existing = fields.Boolean(
        string='Reemplazar Dashboards Existentes',
        default=False,
        help='Si está marcado, eliminará los dashboards existentes del mismo nombre antes de copiar'
    )

    def action_copy_dashboard(self):
        """Copia el dashboard a los usuarios seleccionados"""
        self.ensure_one()

        if not self.dashboard_id:
            raise UserError(_('Debe seleccionar un dashboard para copiar'))

        if not self.user_ids:
            raise UserError(_('Debe seleccionar al menos un usuario destino'))

        dashboard_obj = self.env['hr.dashboard']
        widget_obj = self.env['hr.dashboard.widget']
        created_count = 0

        for user in self.user_ids:
            # Si se debe reemplazar, eliminar dashboards existentes con el mismo nombre
            if self.replace_existing:
                existing = dashboard_obj.search([
                    ('user_id', '=', user.id),
                    ('name', '=', self.dashboard_id.name),
                    ('company_id', '=', self.dashboard_id.company_id.id),
                ])
                if existing:
                    existing.unlink()

            # Si se debe establecer como predeterminado, desmarcar otros dashboards
            if self.copy_as_default:
                dashboard_obj.search([
                    ('user_id', '=', user.id),
                    ('company_id', '=', self.dashboard_id.company_id.id),
                    ('is_default', '=', True),
                ]).write({'is_default': False})

            # Crear el nuevo dashboard
            new_dashboard = dashboard_obj.create({
                'name': self.dashboard_id.name,
                'user_id': user.id,
                'company_id': self.dashboard_id.company_id.id,
                'sequence': self.dashboard_id.sequence,
                'is_default': self.copy_as_default,
                'grid_columns': self.dashboard_id.grid_columns,
                'active': True,
            })

            # Copiar los widgets
            for widget in self.dashboard_id.widget_ids:
                widget_obj.create({
                    'dashboard_id': new_dashboard.id,
                    'widget_type': widget.widget_type,
                    'row': widget.row,
                    'col': widget.col,
                    'colspan': widget.colspan,
                    'rowspan': widget.rowspan,
                    'visible': widget.visible,
                    'collapsed': widget.collapsed,
                    'sequence': widget.sequence,
                })

            created_count += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('¡Éxito!'),
                'message': _('Dashboard copiado a %d usuario(s)') % created_count,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }
