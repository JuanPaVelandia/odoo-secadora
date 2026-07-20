# -*- coding: utf-8 -*-

from odoo import models, fields, api


class SecadoraLote(models.Model):
    _name = 'secadora.lote'
    _description = 'Lote de Finca'
    _order = 'finca_id, name'

    _sql_constraints = [
        ('name_finca_unique', 'UNIQUE(name, finca_id)',
         'Ya existe un lote con ese nombre en esta finca.'),
    ]

    name = fields.Char(
        string='Nombre',
        required=True,
        index=True,
        help='Nombre o número del lote dentro de la finca (Ej: 180, El Bajo)',
    )
    finca_id = fields.Many2one(
        'secadora.lugar',
        string='Finca',
        required=True,
        index=True,
        ondelete='restrict',
        domain=[('tipo', '=', 'finca')],
    )
    hectareas = fields.Float(
        string='Hectáreas',
        digits=(10, 2),
        help='Área del lote (opcional)',
    )
    active = fields.Boolean(
        string='Activo',
        default=True,
    )
    notes = fields.Text(string='Notas')

    @api.onchange('name')
    def _onchange_name_hectareas(self):
        """Convención de la secadora: el nombre del lote suele ser su número
        de hectáreas (Ej: lote "180" = 180 ha). Auto-llenar si está vacío."""
        if self.name and not self.hectareas:
            try:
                self.hectareas = float(self.name.strip().replace(',', '.'))
            except ValueError:
                pass
