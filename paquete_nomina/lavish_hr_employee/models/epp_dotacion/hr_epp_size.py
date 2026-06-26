# -*- coding: utf-8 -*-

from odoo import models, fields, api


class HrEppSize(models.Model):
    """Modelo para tallas de items EPP/Dotación"""
    _name = 'hr.epp.size'
    _description = 'Talla EPP/Dotación'
    _order = 'size_type, sequence, name'
    _rec_name = 'display_name'

    name = fields.Char('Código', required=True, help="Código de la talla (ej: M, 42, XL)")
    display_name = fields.Char('Nombre', compute='_compute_display_name', store=True)
    description = fields.Char('Descripción', help="Descripción opcional (ej: Mediano, Talla 42)")

    size_type = fields.Selection([
        ('clothing', 'Ropa'),
        ('shoes', 'Calzado'),
        ('gloves', 'Guantes'),
        ('helmet', 'Casco'),
        ('custom', 'Personalizado')
    ], string='Tipo de Talla', required=True, index=True)

    sequence = fields.Integer('Secuencia', default=10)
    active = fields.Boolean('Activo', default=True)

    # Medidas asociadas (opcional)
    measurement_min = fields.Float('Medida Mínima', help="Medida mínima en cm o número")
    measurement_max = fields.Float('Medida Máxima', help="Medida máxima en cm o número")

    _name_type_uniq = models.Constraint('unique(name, size_type)', 'La combinación código/tipo de talla debe ser única!')

    @api.depends('name', 'description', 'size_type')
    def _compute_display_name(self):
        for record in self:
            if record.description:
                record.display_name = f"{record.name} - {record.description}"
            else:
                record.display_name = record.name

    @api.model
    def get_sizes_for_type(self, size_type):
        """Obtener tallas disponibles para un tipo específico"""
        return self.search([('size_type', '=', size_type), ('active', '=', True)])

