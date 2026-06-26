# -*- coding: utf-8 -*-
from odoo import models, fields, api

CIIU_TYPE = [
    ('section', 'Seccion'),
    ('division', 'Division'),
    ('group', 'Grupo'),
    ('class', 'Clase'),
    ('dian', 'DIAN Especial'),
]

CIIU_SECTION = [
    ('A', 'A - Agricultura, ganaderia, caza, silvicultura y pesca'),
    ('B', 'B - Explotacion de minas y canteras'),
    ('C', 'C - Industrias manufactureras'),
    ('D', 'D - Suministro de electricidad, gas, vapor y aire acondicionado'),
    ('E', 'E - Distribucion de agua, saneamiento, gestion de desechos'),
    ('F', 'F - Construccion'),
    ('G', 'G - Comercio al por mayor y menor, reparacion de vehiculos'),
    ('H', 'H - Transporte y almacenamiento'),
    ('I', 'I - Alojamiento y servicios de comida'),
    ('J', 'J - Informacion y comunicaciones'),
    ('K', 'K - Actividades financieras y de seguros'),
    ('L', 'L - Actividades inmobiliarias'),
    ('M', 'M - Actividades profesionales, cientificas y tecnicas'),
    ('N', 'N - Actividades de servicios administrativos y de apoyo'),
    ('O', 'O - Administracion publica y defensa'),
    ('P', 'P - Educacion'),
    ('Q', 'Q - Actividades de atencion de la salud humana'),
    ('R', 'R - Actividades artisticas, entretenimiento y recreacion'),
    ('S', 'S - Otras actividades de servicios'),
    ('T', 'T - Actividades de los hogares como empleadores'),
    ('U', 'U - Actividades de organizaciones extraterritoriales'),
    ('DIAN', 'DIAN - Otras clasificaciones especiales'),
]


class LavishCiiu(models.Model):
    _name = 'lavish.ciiu'
    _description = 'CIIU - Actividades Economicas Colombia'
    _order = 'code'
    _parent_name = 'parent_id'
    _parent_store = True

    code = fields.Char('Codigo', required=True, index=True)
    name = fields.Char('Descripcion', required=True)
    ciiu_type = fields.Selection(
        CIIU_TYPE,
        string='Tipo',
        default='class',
        help='Tipo de clasificacion CIIU'
    )
    section = fields.Selection(
        CIIU_SECTION,
        string='Seccion',
        help='Seccion economica (A-U)'
    )
    parent_id = fields.Many2one(
        'lavish.ciiu',
        string='Padre',
        ondelete='cascade',
        index=True
    )
    child_ids = fields.One2many(
        'lavish.ciiu',
        'parent_id',
        string='Hijos'
    )
    parent_path = fields.Char(index=True)
    active = fields.Boolean(default=True)
    color = fields.Integer(string='Color', default=0)
    is_dian_special = fields.Boolean(
        string='Codigo DIAN Especial',
        help='Codigos especiales DIAN: 0010-Asalariados, 0020-Pensionados, etc.'
    )

    _code_uniq = models.Constraint('unique(code)', 'El codigo CIIU debe ser unico')

    @api.depends('code', 'name', 'section', 'ciiu_type', 'is_dian_special')
    def _compute_display_name(self):
        for record in self:
            if not record.code:
                record.display_name = record.name or ''
                continue
            parts = [f"[{record.code}]"]
            if record.name:
                parts.append(record.name)
            if record.is_dian_special:
                parts.append('(DIAN)')
            record.display_name = ' '.join(parts)

    @api.model
    def name_search(self, name, args=None, operator='ilike', limit=100):
        if not args:
            args = []
        domain = args[:]
        if name:
            name = name.strip()
            if name.isdigit():
                domain = [('code', '=like', f'{name}%')] + domain
            else:
                domain = ['|', '|',
                    ('code', operator, name),
                    ('name', operator, name),
                    ('section', operator, name)
                ] + domain
        records = self.search(domain, limit=limit)
        return [(r.id, r.display_name) for r in records]

    @api.model
    def get_codes_by_section(self, section):
        return self.search([('section', '=', section), ('ciiu_type', '=', 'class')])

    @api.model
    def get_dian_special_codes(self):
        return self.search([('is_dian_special', '=', True)])
