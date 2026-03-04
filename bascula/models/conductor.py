# -*- coding: utf-8 -*-

from odoo import models, fields, api


class SecadoraConductor(models.Model):
    _name = 'secadora.conductor'
    _description = 'Conductores'
    _order = 'name'

    name = fields.Char(
        string='Nombre',
        required=True,
        index=True
    )
    cedula = fields.Char(
        string='Cédula',
        required=True,
        index=True
    )
    telefono = fields.Char(string='Teléfono')
    licencia = fields.Char(string='Licencia de Conducción')
    licencia_vencimiento = fields.Date(string='Vencimiento Licencia')
    active = fields.Boolean(
        string='Activo',
        default=True
    )
    vehiculo_ids = fields.Many2many(
        'secadora.vehiculo',
        'secadora_conductor_vehiculo_rel',
        'conductor_id',
        'vehiculo_id',
        string='Vehículos',
    )

    _sql_constraints = [
        ('cedula_unique', 'unique(cedula)', 'La cédula del conductor debe ser única.')
    ]

    def write(self, vals):
        res = super().write(vals)
        if 'vehiculo_ids' in vals:
            for record in self:
                record.vehiculo_ids.filtered(
                    lambda v: v.conductor_habitual_id != record
                ).write({'conductor_habitual_id': record.id})
        return res
