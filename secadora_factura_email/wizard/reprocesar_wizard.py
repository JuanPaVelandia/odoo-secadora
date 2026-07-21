# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError


class ReprocesarFacturaWizard(models.TransientModel):
    _name = 'secadora.reprocesar.factura.wizard'
    _description = 'Reprocesar Facturas Email con Error'

    factura_email_ids = fields.Many2many(
        'secadora.factura.email',
        string='Facturas a Reprocesar',
    )
    cantidad = fields.Integer(
        string='Registros Seleccionados',
        compute='_compute_cantidad',
    )

    @api.depends('factura_email_ids')
    def _compute_cantidad(self):
        for rec in self:
            rec.cantidad = len(rec.factura_email_ids)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_ids = self.env.context.get('active_ids', [])
        if active_ids:
            registros = self.env['secadora.factura.email'].browse(active_ids)
            # Solo los que están en error o pendiente
            reprocesables = registros.filtered(lambda r: r.state in ('error', 'pendiente'))
            res['factura_email_ids'] = [(6, 0, reprocesables.ids)]
        return res

    def action_reprocesar(self):
        """Reprocesa todos los registros seleccionados."""
        self.ensure_one()
        if not self.factura_email_ids:
            raise UserError('No hay registros para reprocesar.')

        for rec in self.factura_email_ids:
            rec.action_reprocesar()

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'secadora.factura.email',
            'view_mode': 'list,form',
            'target': 'current',
        }
