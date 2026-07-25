from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class MaintenanceEquipmentLocationHistory(models.Model):
    """Historial de ubicación de un equipo.

    La maquinaria se mueve entre fincas y áreas de planta. `lugar_id` guarda
    solo dónde está hoy; aquí queda el rastro de dónde estuvo y desde cuándo.
    """

    _name = 'maintenance.equipment.location.history'
    _description = 'Historial de ubicación de equipo'
    _order = 'date_from desc, id desc'

    equipment_id = fields.Many2one(
        'maintenance.equipment',
        string='Equipo',
        required=True,
        index=True,
        ondelete='cascade',
    )
    lugar_id = fields.Many2one(
        'secadora.lugar',
        string='Ubicación',
        index=True,
        help='Punto operativo (finca, planta) donde estuvo el equipo.',
    )
    origen_muestra_id = fields.Many2one(
        'secadora.origen.muestra',
        string='Área de proceso',
        help='Área dentro de la planta (Prelimpieza, Secamiento, '
             'Almacenamiento). Se reusa el catálogo de calidad.',
    )
    parent_equipment_id = fields.Many2one(
        'maintenance.equipment',
        string='Parte de',
        help='Si el equipo es un componente, el equipo padre que lo contiene.',
    )
    date_from = fields.Date(
        string='Desde',
        required=True,
        default=fields.Date.context_today,
        index=True,
    )
    date_to = fields.Date(
        string='Hasta',
        help='Vacío = ubicación actual.',
    )
    is_current = fields.Boolean(
        string='Actual',
        compute='_compute_is_current',
        store=True,
    )
    origin = fields.Char(string='Origen', default='Fracttal')
    notes = fields.Text(string='Notas')

    @api.depends('date_to')
    def _compute_is_current(self):
        for rec in self:
            rec.is_current = not rec.date_to

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_to and rec.date_to < rec.date_from:
                raise ValidationError(_(
                    'La fecha "Hasta" no puede ser anterior a la fecha "Desde".'
                ))
