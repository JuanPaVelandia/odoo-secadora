# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class FincaSocio(models.Model):
    """Participación de un socio en una sociedad dueña de finca.

    La Alianza y La Fortuna son sociedades entre dos dueños: la sociedad es la
    que contrata y paga a los operadores (es el dueño de la finca y el "dueño
    que paga" en los anticipos), así que el saldo del operador se lleva con la
    sociedad. Esta tabla solo reparte el costo de la sociedad entre sus socios
    para el reporte "Costo por socio".
    """
    _name = 'finca.socio'
    _description = 'Socio de Sociedad Dueña de Finca'
    _order = 'sociedad_id, porcentaje desc'

    _socio_unique = models.Constraint(
        'UNIQUE(sociedad_id, socio_id)',
        'El socio ya está en esta sociedad.',
    )

    sociedad_id = fields.Many2one(
        'res.partner',
        string='Sociedad',
        required=True,
        index=True,
        ondelete='cascade',
    )
    socio_id = fields.Many2one(
        'res.partner',
        string='Socio',
        required=True,
        index=True,
    )
    porcentaje = fields.Float(
        string='Participación (%)',
        digits=(5, 2),
        required=True,
    )

    @api.depends('socio_id', 'porcentaje')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = '%s (%s %%)' % (rec.socio_id.name or '', ('%.2f' % rec.porcentaje).rstrip('0').rstrip('.'))

    @api.constrains('sociedad_id', 'socio_id', 'porcentaje')
    def _check_porcentajes(self):
        for sociedad in self.sociedad_id:
            socios = self.search([('sociedad_id', '=', sociedad.id)])
            if socios.filtered(lambda s: s.socio_id == sociedad):
                raise ValidationError('%s no puede ser socio de sí mismo.' % sociedad.name)
            if self.search_count([('sociedad_id', 'in', socios.socio_id.ids)]):
                raise ValidationError(
                    'Un socio de %s es a su vez una sociedad. Registre los socios '
                    'finales directamente.' % sociedad.name)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    finca_socio_ids = fields.One2many(
        'finca.socio',
        'sociedad_id',
        string='Socios',
    )

    # La suma se valida en la sociedad y no en cada línea: al pasar de 60/40
    # a 50/50 las líneas se guardan una por una y en medio sumarían 90.
    @api.constrains('finca_socio_ids')
    def _check_finca_socios_100(self):
        for rec in self.filtered('finca_socio_ids'):
            total = sum(rec.finca_socio_ids.mapped('porcentaje'))
            if abs(total - 100.0) > 0.01:
                raise ValidationError(
                    'Las participaciones de %s suman %.2f%%; deben sumar 100%%.'
                    % (rec.name, total))
