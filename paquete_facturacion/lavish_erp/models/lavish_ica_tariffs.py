# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class LavishIcaTariffs(models.Model):
    _name = 'lavish.ica.tariffs'
    _description = 'Tarifas ICA por Municipio y CIIU'
    _rec_name = 'display_name'
    _order = 'city_id, ciiu_id'

    state_id = fields.Many2one('res.country.state', string='Departamento', required=True,
                               domain="[('country_id.code', '=', 'CO')]")
    city_id = fields.Many2one('res.city', string='Municipio', required=True,
                              domain="[('state_id', '=', state_id)]")
    ciiu_id = fields.Many2one('lavish.ciiu', string='Actividad CIIU', required=True)
    rate = fields.Float(string='Tarifa (por mil)', required=True, digits=(10, 4),
                        help="Tarifa en por mil (e.g. 9.66)")
    rate_percent = fields.Float(string='Tarifa (%)', compute='_compute_rate_percent',
                                store=True, digits=(10, 6),
                                help="Tarifa en porcentaje (por mil / 10)")
    rte_ica_percent = fields.Float(string='Rete ICA (%)', digits=(10, 6),
                                   help="Porcentaje de retencion de ICA")
    description = fields.Char(string='Descripcion')

    @api.depends('rate')
    def _compute_rate_percent(self):
        """Convertir tarifa por mil a porcentaje"""
        for record in self:
            record.rate_percent = record.rate / 10 if record.rate else 0.0

    _city_ciiu_uniq = models.Constraint('unique (city_id, ciiu_id)', 'Ya existe una tarifa definida para este municipio y actividad CIIU.')

    @api.depends('city_id', 'ciiu_id', 'rate')
    def _compute_display_name(self):
        for record in self:
            if record.city_id and record.ciiu_id:
                record.display_name = f"{record.city_id.name} - {record.ciiu_id.code} - {record.rate}"
            else:
                record.display_name = _('Nuevo')

    @api.onchange('state_id')
    def _onchange_state_id(self):
        """Limpiar ciudad cuando cambia el departamento."""
        self.city_id = False
        return {'domain': {'city_id': [('state_id', '=', self.state_id.id)]}}
