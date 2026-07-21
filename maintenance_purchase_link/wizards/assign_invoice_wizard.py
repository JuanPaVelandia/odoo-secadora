from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AssignInvoiceWizard(models.TransientModel):
    _name = 'maintenance.assign.invoice.wizard'
    _description = 'Asignar factura a equipos'

    move_id = fields.Many2one(
        'account.move',
        string='Factura',
        required=True,
    )
    move_partner_id = fields.Many2one(
        related='move_id.partner_id',
        string='Proveedor',
    )
    move_amount = fields.Monetary(
        related='move_id.amount_untaxed',
        string='Subtotal factura',
    )
    currency_id = fields.Many2one(
        related='move_id.currency_id',
    )
    line_count = fields.Integer(
        string='Líneas pendientes',
        compute='_compute_line_count',
    )
    line_ids = fields.One2many(
        'maintenance.assign.invoice.wizard.line',
        'wizard_id',
        string='Equipos',
    )
    total_percentage = fields.Float(
        string='Total %',
        compute='_compute_total_percentage',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ctx = self.env.context
        if ctx.get('default_request_id') or ctx.get('default_equipment_id'):
            line_vals = {'percentage': 100.0}
            if ctx.get('default_equipment_id'):
                line_vals['equipment_id'] = ctx['default_equipment_id']
            if ctx.get('default_request_id'):
                line_vals['request_id'] = ctx['default_request_id']
            res['line_ids'] = [(0, 0, line_vals)]
        return res

    @api.onchange('move_id')
    def _onchange_move_id(self):
        """Filtrar solo facturas con cost lines sin equipo asignado."""
        if self.move_id:
            # Verificar que la factura tenga líneas sin equipo
            pending = self.env['maintenance.equipment.cost.line'].search_count([
                ('move_id', '=', self.move_id.id),
                ('equipment_id', '=', False),
            ])
            if not pending:
                # Verificar si tiene cost lines con equipo (ya asignada)
                assigned = self.env['maintenance.equipment.cost.line'].search_count([
                    ('move_id', '=', self.move_id.id),
                    ('equipment_id', '!=', False),
                ])
                if assigned:
                    return {'warning': {
                        'title': _('Factura ya asignada'),
                        'message': _('Esta factura ya tiene todos los equipos asignados.'),
                    }}

    @api.depends('move_id')
    def _compute_line_count(self):
        for wiz in self:
            if wiz.move_id:
                wiz.line_count = self.env['maintenance.equipment.cost.line'].search_count([
                    ('move_id', '=', wiz.move_id.id),
                    ('equipment_id', '=', False),
                ])
            else:
                wiz.line_count = 0

    @api.depends('line_ids.percentage')
    def _compute_total_percentage(self):
        for wiz in self:
            wiz.total_percentage = sum(wiz.line_ids.mapped('percentage'))

    def action_assign(self):
        self.ensure_one()
        CostLine = self.env['maintenance.equipment.cost.line']

        if not self.line_ids:
            raise ValidationError(_('Debe agregar al menos un equipo.'))

        total = sum(self.line_ids.mapped('percentage'))
        if abs(total - 100.0) > 0.01:
            raise ValidationError(_(
                'Los porcentajes deben sumar exactamente 100%%. '
                'Actualmente suman %.1f%%.',
                total,
            ))

        # Buscar cost lines sin equipo de esta factura
        pending_lines = CostLine.search([
            ('move_id', '=', self.move_id.id),
            ('equipment_id', '=', False),
        ])

        if not pending_lines:
            # Si no hay pendientes, buscar líneas de producto de la factura
            product_lines = self.move_id.invoice_line_ids.filtered(
                lambda l: l.display_type == 'product'
            )
            if not product_lines:
                raise ValidationError(_('La factura no tiene líneas de producto.'))

            # Crear cost lines nuevas
            vals_list = []
            for wiz_line in self.line_ids:
                for ml in product_lines:
                    vals_list.append({
                        'move_line_id': ml.id,
                        'equipment_id': wiz_line.equipment_id.id,
                        'percentage': wiz_line.percentage,
                        'request_id': wiz_line.request_id.id if wiz_line.request_id else False,
                    })
            CostLine.create(vals_list)
            created = len(vals_list)
        else:
            # Asignar equipo/OT a cost lines pendientes
            if len(self.line_ids) == 1:
                # Un solo equipo: asignar a todas las pendientes
                wiz_line = self.line_ids[0]
                pending_lines.write({
                    'equipment_id': wiz_line.equipment_id.id,
                    'percentage': wiz_line.percentage,
                    'request_id': wiz_line.request_id.id if wiz_line.request_id else False,
                })
                created = len(pending_lines)
            else:
                # Múltiples equipos: duplicar cada pending line por equipo
                for pl in pending_lines:
                    first = True
                    for wiz_line in self.line_ids:
                        if first:
                            # Actualizar la línea existente con el primer equipo
                            pl.write({
                                'equipment_id': wiz_line.equipment_id.id,
                                'percentage': wiz_line.percentage,
                                'request_id': wiz_line.request_id.id if wiz_line.request_id else False,
                            })
                            first = False
                        else:
                            # Crear copia para los demás equipos
                            CostLine.create({
                                'move_line_id': pl.move_line_id.id,
                                'equipment_id': wiz_line.equipment_id.id,
                                'percentage': wiz_line.percentage,
                                'request_id': wiz_line.request_id.id if wiz_line.request_id else False,
                            })
                created = len(pending_lines) * len(self.line_ids)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Factura asignada'),
                'message': _('%(count)d asignación(es) creada(s).', count=created),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }


class AssignInvoiceWizardLine(models.TransientModel):
    _name = 'maintenance.assign.invoice.wizard.line'
    _description = 'Línea del wizard asignar factura'

    wizard_id = fields.Many2one(
        'maintenance.assign.invoice.wizard',
        required=True,
        ondelete='cascade',
    )
    equipment_id = fields.Many2one(
        'maintenance.equipment',
        string='Equipo',
        required=True,
    )
    request_id = fields.Many2one(
        'maintenance.request',
        string='Orden de trabajo',
    )
    percentage = fields.Float(
        string='Porcentaje (%)',
        default=100.0,
        required=True,
    )
