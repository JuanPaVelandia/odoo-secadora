# -*- coding: utf-8 -*-
from odoo import models, fields, api

class AccountNomenclatureCode(models.Model):
    """
    Modelo para almacenar los códigos de nomenclatura DIAN
    Usado para construir direcciones colombianas estructuradas
    """
    _name = 'account.nomenclature.code'
    _description = 'Códigos de Nomenclatura DIAN para Direcciones'
    _order = 'sequence, abbreviation'

    name = fields.Char(
        string='Nombre',
        required=True,
        help='Nombre completo del código de nomenclatura'
    )
    abbreviation = fields.Char(
        string='Abreviatura',
        required=True,
        index=True,
        help='Abreviatura del código (ej: CL, KR, AV, BIS, NORTE, etc)'
    )
    type_code = fields.Selection(
        [
            ('principal', 'Vía Principal'),
            ('qualifying', 'Calificador'),
            ('letter', 'Letra'),
            ('additional', 'Complemento Adicional'),
        ],
        string='Tipo de Código',
        required=True,
        default='principal',
        index=True,
        help='Clasificación del código según su uso en la dirección'
    )
    sequence = fields.Integer(
        string='Secuencia',
        default=10,
        help='Orden de visualización en las listas'
    )
    active = fields.Boolean(
        string='Activo',
        default=True
    )

    _abbreviation_type_unique = models.Constraint('unique(abbreviation, type_code)',
                                                  'La abreviatura debe ser única por tipo de código')

    def _compute_display_name(self):
        """Mostrar formato: [Abreviatura] Nombre"""
        for record in self:
            record.display_name = f"[{record.abbreviation}] {record.name}"

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        """Permitir buscar por abreviatura o nombre"""
        if not args:
            args = []

        domain = args[:]
        if name:
            domain = ['|',
                ('abbreviation', operator, name),
                ('name', operator, name)
            ] + domain

        records = self.search(domain, limit=limit)
        return [(r.id, r.display_name) for r in records]
