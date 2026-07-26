from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class MaintenanceEquipment(models.Model):
    _inherit = 'maintenance.equipment'

    # --- Ubicación ---
    lugar_id = fields.Many2one(
        'secadora.lugar',
        string='Ubicación',
    )
    origen_muestra_id = fields.Many2one(
        'secadora.origen.muestra',
        string='Área de proceso',
        help='Área dentro de la planta (Prelimpieza, Secamiento, '
             'Almacenamiento). Se reusa el catálogo de calidad para no '
             'duplicar el listado de áreas.',
    )
    parent_equipment_id = fields.Many2one(
        'maintenance.equipment',
        string='Parte de',
        index=True,
        ondelete='set null',
        help='Equipo padre, cuando este registro es un componente '
             '(motor, alternador, etc.).',
    )
    component_ids = fields.One2many(
        'maintenance.equipment',
        'parent_equipment_id',
        string='Componentes',
    )
    # Nombre completo de la jerarquía, para ubicar un componente de un vistazo:
    # "SILO KEPLER WEBER 1000 TON ALM 5 / MOTOR 52".
    complete_name = fields.Char(
        string='Nombre completo',
        compute='_compute_complete_name',
        recursive=True,
        store=True,
    )

    @api.onchange('parent_equipment_id')
    def _onchange_parent_equipment_id(self):
        """Un componente está donde esté su máquina: hereda su ubicación."""
        for equipment in self.filtered('parent_equipment_id'):
            padre = equipment.parent_equipment_id
            if padre.lugar_id:
                equipment.lugar_id = padre.lugar_id
            if padre.origen_muestra_id:
                equipment.origen_muestra_id = padre.origen_muestra_id

    def _heredar_ubicacion_a_componentes(self):
        """Propaga la ubicación del equipo a sus componentes."""
        for equipment in self:
            componentes = equipment.component_ids
            if not componentes:
                continue
            vals = {
                'lugar_id': equipment.lugar_id.id or False,
                'origen_muestra_id': equipment.origen_muestra_id.id or False,
            }
            desactualizados = componentes.filtered(
                lambda c: (c.lugar_id.id or False) != vals['lugar_id']
                or (c.origen_muestra_id.id or False) != vals['origen_muestra_id']
            )
            if desactualizados:
                desactualizados.write(vals)

    @api.depends('name', 'parent_equipment_id.complete_name')
    def _compute_complete_name(self):
        for equipment in self:
            if equipment.parent_equipment_id:
                equipment.complete_name = (
                    f'{equipment.parent_equipment_id.complete_name} / '
                    f'{equipment.name}')
            else:
                equipment.complete_name = equipment.name

    @api.constrains('parent_equipment_id')
    def _check_parent_recursion(self):
        if not self._check_recursion('parent_equipment_id'):
            raise ValidationError(_(
                'Un equipo no puede ser componente de sí mismo.'
            ))

    # ------------------------------------------------------------------
    # Historial de ubicación
    # ------------------------------------------------------------------
    def write(self, vals):
        """Al mover un equipo, cierra el tramo anterior y abre uno nuevo."""
        rastrear = {'lugar_id', 'origen_muestra_id', 'parent_equipment_id'}
        if (not rastrear & set(vals)
                or self.env.context.get('importando_historico')):
            return super().write(vals)

        anterior = {
            eq.id: (eq.lugar_id.id, eq.origen_muestra_id.id,
                    eq.parent_equipment_id.id)
            for eq in self
        }
        res = super().write(vals)
        # Los componentes viajan con su máquina.
        if {'lugar_id', 'origen_muestra_id'} & set(vals):
            self._heredar_ubicacion_a_componentes()
        self._registrar_movimiento(anterior)
        return res

    def _registrar_movimiento(self, anterior):
        """Crea el tramo de historial de los equipos que cambiaron de sitio."""
        Historial = self.env['maintenance.equipment.location.history']
        hoy = fields.Date.context_today(self)
        for equipment in self:
            actual = (equipment.lugar_id.id, equipment.origen_muestra_id.id,
                      equipment.parent_equipment_id.id)
            if actual == anterior.get(equipment.id):
                continue
            # Cerrar el tramo abierto: hasta ayer estuvo donde estaba.
            abiertos = Historial.search([
                ('equipment_id', '=', equipment.id),
                ('date_to', '=', False),
            ])
            abiertos.write({'date_to': hoy})
            if not any(actual):
                continue        # se quitó la ubicación, no hay tramo nuevo
            Historial.create({
                'equipment_id': equipment.id,
                'lugar_id': equipment.lugar_id.id or False,
                'origen_muestra_id': equipment.origen_muestra_id.id or False,
                'parent_equipment_id': equipment.parent_equipment_id.id or False,
                'date_from': hoy,
                'origin': 'Odoo',
            })

    @api.model_create_multi
    def create(self, vals_list):
        # Un componente nace donde está su máquina.
        for vals in vals_list:
            if vals.get('parent_equipment_id') and not vals.get('lugar_id'):
                padre = self.browse(vals['parent_equipment_id'])
                if padre.lugar_id:
                    vals['lugar_id'] = padre.lugar_id.id
                if padre.origen_muestra_id and not vals.get('origen_muestra_id'):
                    vals['origen_muestra_id'] = padre.origen_muestra_id.id
        equipos = super().create(vals_list)
        # La importación crea el historial con las fechas reales de origen,
        # no con la de hoy: ahí no se registra el alta automática.
        if not self.env.context.get('importando_historico'):
            equipos._registrar_movimiento({})
        return equipos
    component_count = fields.Integer(
        string='Nro. componentes',
        compute='_compute_component_count',
    )
    location_history_ids = fields.One2many(
        'maintenance.equipment.location.history',
        'equipment_id',
        string='Historial de ubicación',
    )
    location_history_count = fields.Integer(
        string='Nro. movimientos',
        compute='_compute_component_count',
    )

    # --- Costos (modelo intermedio) ---
    equipment_cost_line_ids = fields.One2many(
        'maintenance.equipment.cost.line',
        'equipment_id',
        string='Líneas de costo',
    )
    maintenance_cost_total = fields.Monetary(
        string='Costo total de mantenimiento',
        compute='_compute_maintenance_cost_total',
        store=True,
        currency_field='cost_currency_id',
        help='Todos los costos imputados al equipo: facturados, importados '
             'del histórico y registrados a mano.',
    )
    maintenance_invoice_count = fields.Integer(
        string='Nro. líneas de costo',
        compute='_compute_maintenance_cost_total',
        store=True,
    )
    external_ref = fields.Char(
        string='Referencia externa',
        index=True,
        copy=False,
        help='Código del activo en el sistema de origen (Fracttal). '
             'Se usa para no duplicar en re-importaciones.',
    )
    cost_currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id,
    )

    # --- Horómetro ---
    horometro_interval = fields.Float(
        string='Intervalo horómetro (horas)',
        help='Cada cuántas horas se genera una solicitud de mantenimiento preventivo.',
    )
    horometro_last_maintenance = fields.Float(
        string='Última lectura mant. (horas)',
        help='Lectura del horómetro en el último mantenimiento disparado.',
    )
    horometro_reading_ids = fields.One2many(
        'maintenance.horometro.reading',
        'equipment_id',
        string='Lecturas de horómetro',
    )
    horometro_current = fields.Float(
        string='Horómetro actual',
        compute='_compute_horometro_current',
    )
    horometro_reading_count = fields.Integer(
        string='Nro. lecturas',
        compute='_compute_horometro_current',
    )

    @api.depends('equipment_cost_line_ids.amount')
    def _compute_maintenance_cost_total(self):
        for equipment in self:
            lines = equipment.equipment_cost_line_ids
            equipment.maintenance_cost_total = sum(lines.mapped('amount'))
            equipment.maintenance_invoice_count = len(lines)

    @api.depends('component_ids', 'location_history_ids')
    def _compute_component_count(self):
        for equipment in self:
            equipment.component_count = len(equipment.component_ids)
            equipment.location_history_count = len(equipment.location_history_ids)

    @api.depends('horometro_reading_ids.value')
    def _compute_horometro_current(self):
        for equipment in self:
            readings = equipment.horometro_reading_ids
            equipment.horometro_reading_count = len(readings)
            if readings:
                equipment.horometro_current = readings[0].value  # ordered desc
            else:
                equipment.horometro_current = 0.0

    def action_view_maintenance_costs(self):
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id(
            'maintenance_purchase_link.action_equipment_cost_lines'
        )
        action['domain'] = [('equipment_id', '=', self.id)]
        action['context'] = dict(self.env.context, default_equipment_id=self.id)
        return action

    def action_view_location_history(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Historial de ubicación',
            'res_model': 'maintenance.equipment.location.history',
            'view_mode': 'list,form',
            'domain': [('equipment_id', '=', self.id)],
            'context': dict(self.env.context, default_equipment_id=self.id),
        }

    def action_view_components(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Componentes',
            'res_model': 'maintenance.equipment',
            'view_mode': 'list,form',
            'domain': [('parent_equipment_id', '=', self.id)],
            'context': dict(self.env.context, default_parent_equipment_id=self.id),
        }

    def action_view_horometro_readings(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Lecturas de horómetro',
            'res_model': 'maintenance.horometro.reading',
            'view_mode': 'list,form',
            'domain': [('equipment_id', '=', self.id)],
            'context': dict(self.env.context, default_equipment_id=self.id),
        }
