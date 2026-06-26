# -*- coding: utf-8 -*-

from odoo import models, fields, api


class HrEppItemType(models.Model):
    """Modelo jerárquico para tipos y subtipos de items EPP/Dotación"""
    _name = 'hr.epp.item.type'
    _description = 'Tipo de Item EPP/Dotación'
    _parent_name = 'parent_id'
    _parent_store = True
    _order = 'sequence, complete_name'
    _rec_name = 'complete_name'

    name = fields.Char('Nombre', required=True, translate=True)
    complete_name = fields.Char(
        'Nombre Completo',
        compute='_compute_complete_name',
        recursive=True,
        store=True
    )
    code = fields.Char('Código', index=True)
    description = fields.Text('Descripción')
    sequence = fields.Integer('Secuencia', default=10)
    icon = fields.Char('Icono', help="Clase de icono FontAwesome (ej: fa-shield)")

    # Jerarquía
    parent_id = fields.Many2one(
        'hr.epp.item.type',
        string='Tipo Padre',
        index=True,
        ondelete='cascade',
        domain="[('parent_id', '=', False)]"
    )
    parent_path = fields.Char(index=True, unaccent=False)
    child_ids = fields.One2many(
        'hr.epp.item.type',
        'parent_id',
        string='Subtipos'
    )

    # Clasificación
    classification = fields.Selection([
        ('epp', 'EPP'),
        ('dotacion', 'Dotación'),
        ('both', 'Ambos')
    ], string='Clasificación', default='both', required=True)

    # Configuración de tallas
    requires_size = fields.Boolean(
        'Requiere Talla',
        default=False,
        help="Indica si los items de este tipo requieren especificar talla"
    )
    size_type = fields.Selection([
        ('clothing', 'Ropa (XS, S, M, L, XL, XXL)'),
        ('shoes', 'Calzado (Número)'),
        ('gloves', 'Guantes (6-12)'),
        ('helmet', 'Casco (Circunferencia)'),
        ('custom', 'Personalizado')
    ], string='Tipo de Talla')

    # Campos computados
    is_type = fields.Boolean(
        'Es Tipo',
        compute='_compute_is_type',
        store=True,
        help="True si es un tipo padre (no tiene parent_id)"
    )
    is_subtype = fields.Boolean(
        'Es Subtipo',
        compute='_compute_is_type',
        store=True,
        help="True si es un subtipo (tiene parent_id)"
    )

    active = fields.Boolean('Activo', default=True)

    _code_uniq = models.Constraint('unique(code)', 'El código debe ser único!')

    @api.depends('name', 'parent_id.complete_name')
    def _compute_complete_name(self):
        for record in self:
            if record.parent_id:
                record.complete_name = f"{record.parent_id.complete_name} / {record.name}"
            else:
                record.complete_name = record.name

    @api.depends('parent_id')
    def _compute_is_type(self):
        for record in self:
            record.is_type = not record.parent_id
            record.is_subtype = bool(record.parent_id)

