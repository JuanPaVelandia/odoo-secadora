# -*- coding: utf-8 -*-

from odoo import models, fields


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    x_numero_tiquete = fields.Char(string='Numero de Tiquete')

    x_pesaje_id = fields.Many2one(
        'secadora.pesaje',
        string='Pesaje',
        index=True,
        help='Pesaje de bascula que origino este picking'
    )

    x_orden_servicio_id = fields.Many2one(
        'secadora.orden.servicio',
        string='Orden de Servicio',
        index=True,
        help='Orden de servicio asociada a este picking'
    )

    def action_confirm(self):
        """Propaga owner_id a restrict_partner_id de los moves antes de confirmar.

        Odoo 18 solo propaga owner_id a los move_lines en _action_done (validacion),
        pero _action_assign no usa restrict_partner_id para filtrar quants.
        Esto asegura que restrict_partner_id este listo para nuestro override.
        """
        for picking in self:
            if picking.owner_id:
                picking.move_ids.filtered(
                    lambda m: not m.restrict_partner_id
                ).write({'restrict_partner_id': picking.owner_id.id})
        return super().action_confirm()


class StockMove(models.Model):
    _inherit = 'stock.move'

    x_orden_servicio_id = fields.Many2one(
        'secadora.orden.servicio',
        string='Orden de Servicio',
        index=True,
        help='Orden de servicio asociada a este movimiento'
    )

    x_pesaje_id = fields.Many2one(
        'secadora.pesaje',
        string='Pesaje',
        index=True,
        help='Pesaje que origino este movimiento'
    )

    x_tipo_movimiento_secadora = fields.Selection([
        ('transformacion_consumo', 'Consumo (Verde)'),
        ('transformacion_produccion', 'Produccion (Seco)'),
        ('salida_servicio', 'Entrega al Cliente'),
        ('merma', 'Merma'),
    ], string='Tipo Movimiento Secadora',
       help='Tipo de movimiento generado por la secadora'
    )

    def _update_reserved_quantity(self, need, location_id, lot_id=None,
                                  package_id=None, owner_id=None, strict=True):
        """Override para respetar restrict_partner_id al reservar quants.

        Odoo 18 no pasa owner_id en _action_assign, asi que los quants se
        reservan de cualquier propietario. Este fix filtra por el owner
        correcto cuando el move tiene restrict_partner_id (consignacion).
        """
        if not owner_id and self.restrict_partner_id:
            owner_id = self.restrict_partner_id
        return super()._update_reserved_quantity(
            need, location_id, lot_id=lot_id, package_id=package_id,
            owner_id=owner_id, strict=strict
        )
