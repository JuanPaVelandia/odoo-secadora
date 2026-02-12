# -*- coding: utf-8 -*-

from odoo import models, fields


class OrdenServicioStock(models.Model):
    _inherit = 'secadora.orden.servicio'

    picking_ids = fields.One2many(
        'stock.picking',
        'x_orden_servicio_id',
        string='Movimientos de Inventario',
        readonly=True,
    )

    picking_count = fields.Integer(
        string='Movimientos',
        compute='_compute_picking_count',
    )

    def _compute_picking_count(self):
        for record in self:
            record.picking_count = len(record.picking_ids)

    def action_ver_pickings(self):
        """Abre los pickings vinculados a esta orden"""
        self.ensure_one()
        action = {
            'type': 'ir.actions.act_window',
            'name': f'Inventario - {self.name}',
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('x_orden_servicio_id', '=', self.id)],
            'context': {'default_x_orden_servicio_id': self.id},
        }
        if self.picking_count == 1:
            action['view_mode'] = 'form'
            action['res_id'] = self.picking_ids[0].id
        return action
