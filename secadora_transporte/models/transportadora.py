# -*- coding: utf-8 -*-

from odoo import models, fields, api


class SecadoraTransportadoraTransporte(models.Model):
    _inherit = 'secadora.transportadora'

    flete_ids = fields.One2many(
        'secadora.flete',
        'transportadora_id',
        string='Fletes',
    )
    flete_count = fields.Integer(
        string='Nº Fletes',
        compute='_compute_flete_count',
    )
    factura_count = fields.Integer(
        string='Nº Facturas',
        compute='_compute_factura_count',
    )

    def _compute_flete_count(self):
        flete_data = self.env['secadora.flete'].read_group(
            [('transportadora_id', 'in', self.ids)],
            ['transportadora_id'],
            ['transportadora_id'],
        )
        flete_map = {d['transportadora_id'][0]: d['transportadora_id_count'] for d in flete_data}
        for rec in self:
            rec.flete_count = flete_map.get(rec.id, 0)

    def _compute_factura_count(self):
        for rec in self:
            if rec.flete_ids:
                facturas = rec.flete_ids.mapped('factura_transportadora_id')
                rec.factura_count = len(facturas)
            else:
                rec.factura_count = 0

    def action_ver_fletes(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Fletes - {self.name}',
            'res_model': 'secadora.flete',
            'view_mode': 'list,form',
            'domain': [('transportadora_id', '=', self.id)],
            'context': {'default_transportadora_id': self.id},
        }

    def action_ver_facturas(self):
        self.ensure_one()
        factura_ids = self.flete_ids.mapped('factura_transportadora_id').ids
        return {
            'type': 'ir.actions.act_window',
            'name': f'Facturas - {self.name}',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', factura_ids)],
        }
