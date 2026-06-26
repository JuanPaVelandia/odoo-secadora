# -*- coding: utf-8 -*-

from odoo import models, fields, api


class AccountMove(models.Model):
    _inherit = 'account.move'

    tax_calculation_mode = fields.Selection(
        selection=[
            ('tax_included', 'Impuestos Incluidos en Precio'),
            ('tax_excluded', 'Impuestos Excluidos del Precio'),
        ],
        string='Modo de Cálculo de Impuestos',
        default='tax_excluded',
        help="Determina si los precios mostrados en este documento incluyen o no los impuestos. "
             "Esto NO afecta el total final, solo cómo se muestran los precios unitarios."
    )

    @api.onchange('tax_calculation_mode')
    def _onchange_tax_calculation_mode(self):
        """Recalcula los precios de las líneas cuando cambia el modo de cálculo"""
        if self.tax_calculation_mode and self.invoice_line_ids:
            for line in self.invoice_line_ids:
                if line.product_id and line.tax_ids:
                    line._onchange_product_id()


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'



    @api.depends('price_unit', 'tax_ids', 'move_id.tax_calculation_mode')
    def _compute_price_display(self):
        """Computa el precio a mostrar según el modo de cálculo"""
        for line in self:
            if line.move_id.tax_calculation_mode == 'tax_included':
                # Mostrar precio con impuestos incluidos
                if line.tax_ids:
                    tax_result = line.tax_ids.compute_all(
                        line.price_unit,
                        currency=line.move_id.currency_id,
                        quantity=1.0,
                        product=line.product_id,
                        partner=line.move_id.partner_id
                    )
                    line.price_display = tax_result['total_included']
                else:
                    line.price_display = line.price_unit
            else:
                # Mostrar precio sin impuestos
                line.price_display = line.price_unit

    price_display = fields.Monetary(
        string='Precio Mostrado',
        compute='_compute_price_display',
        help="Precio unitario mostrado según el modo de cálculo de impuestos"
    )
