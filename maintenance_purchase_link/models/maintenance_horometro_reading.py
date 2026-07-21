from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class MaintenanceHorometroReading(models.Model):
    _name = 'maintenance.horometro.reading'
    _description = 'Lectura de horómetro'
    _order = 'date desc, id desc'

    equipment_id = fields.Many2one(
        'maintenance.equipment',
        string='Equipo',
        required=True,
        ondelete='cascade',
    )
    date = fields.Date(
        string='Fecha',
        required=True,
        default=fields.Date.context_today,
    )
    value = fields.Float(
        string='Lectura (horas)',
        required=True,
    )
    user_id = fields.Many2one(
        'res.users',
        string='Registrado por',
        default=lambda self: self.env.user,
    )
    notes = fields.Text(
        string='Notas',
    )
    triggered_request_id = fields.Many2one(
        'maintenance.request',
        string='OT generada',
        readonly=True,
    )

    @api.constrains('value')
    def _check_value_positive(self):
        for rec in self:
            if rec.value < 0:
                raise ValidationError(_(
                    'La lectura del horómetro no puede ser negativa.'
                ))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._check_maintenance_trigger()
        return records

    def _check_maintenance_trigger(self):
        for reading in self:
            eq = reading.equipment_id
            if not eq.horometro_interval or eq.horometro_interval <= 0:
                continue
            if (reading.value - eq.horometro_last_maintenance) >= eq.horometro_interval:
                request = self.env['maintenance.request'].create({
                    'name': _('Mant. preventivo - %(equipo)s (%(horas).0f hrs)',
                              equipo=eq.name, horas=reading.value),
                    'equipment_id': eq.id,
                    'request_date': reading.date,
                    'description': _(
                        'Generado automáticamente al alcanzar %(actual).0f horas. '
                        'Último mantenimiento a las %(ultimo).0f horas.',
                        actual=reading.value,
                        ultimo=eq.horometro_last_maintenance,
                    ),
                })
                reading.triggered_request_id = request.id
                eq.horometro_last_maintenance = reading.value
