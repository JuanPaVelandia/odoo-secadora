# -*- coding: utf-8 -*-

from odoo import models, fields, api


class OrdenServicioFlete(models.Model):
    _inherit = 'secadora.orden.servicio'

    flete_ids = fields.One2many(
        'secadora.flete',
        'orden_servicio_id',
        string='Fletes',
    )

    flete_secadora_ids = fields.One2many(
        'secadora.flete',
        compute='_compute_flete_secadora_ids',
        string='Fletes Pagados por Secadora',
    )

    cobro_flete = fields.Float(
        string='Flete Secadora ($)',
        compute='_compute_cobro_flete',
        store=True,
        digits='Product Price',
        help='Costo de fletes pagados por la secadora y cobrados al agricultor',
    )

    @api.depends(
        'pesaje_entrada_ids.flete_ids.costo_total',
        'pesaje_entrada_ids.flete_ids.pago_flete',
        'pesaje_salida_ids.flete_ids.costo_total',
        'pesaje_salida_ids.flete_ids.pago_flete',
    )
    def _compute_cobro_flete(self):
        for record in self:
            fletes = self.env['secadora.flete'].search([
                ('orden_servicio_id', '=', record.id),
                ('pesaje_id.tipo_operacion_id.es_servicio', '=', True),
                ('pago_flete', '=', 'secadora'),
                ('state', '!=', 'cancelado'),
            ])
            record.cobro_flete = sum(fletes.mapped('costo_total'))

    @api.depends('flete_ids.pago_flete', 'flete_ids.state')
    def _compute_flete_secadora_ids(self):
        for record in self:
            record.flete_secadora_ids = record.flete_ids.filtered(
                lambda f: f.pago_flete == 'secadora'
                and f.state != 'cancelado'
                and f.pesaje_id.tipo_operacion_id.es_servicio
            )

    @api.depends('subtotal_servicios', 'subtotal_empaques', 'descuento_monto', 'cobro_flete')
    def _compute_total_a_facturar(self):
        """Calcular total general: servicios + empaques - descuento + flete secadora"""
        for record in self:
            record.total_a_facturar = (
                record.subtotal_servicios
                + record.subtotal_empaques
                - record.descuento_monto
                + record.cobro_flete
            )
