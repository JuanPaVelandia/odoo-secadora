# -*- coding: utf-8 -*-

from odoo import models, fields, api


class SaleOrder(models.Model):
    _inherit = 'sale.order'

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
        if self.tax_calculation_mode and self.order_line:
            for line in self.order_line:
                if line.product_id and line.tax_ids:
                    line._onchange_product_id_set_price_unit()


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _onchange_product_id_set_price_unit(self):
        """Override para ajustar precio según el modo de cálculo de impuestos del documento"""
        result = super()._onchange_product_id_set_price_unit()

        if self.order_id.tax_calculation_mode and self.product_id and self.tax_ids:
            # Obtener precio base del producto
            price = self.product_id.lst_price

            # Calcular con/sin impuestos
            taxes = self.tax_ids.filtered(lambda t: t.company_id == self.order_id.company_id)
            if taxes:
                tax_result = taxes.compute_all(
                    price,
                    currency=self.order_id.currency_id,
                    quantity=1.0,
                    product=self.product_id,
                    partner=self.order_id.partner_id
                )

                # Ajustar precio según el modo de cálculo seleccionado
                if self.order_id.tax_calculation_mode == 'tax_included':
                    self.price_unit = tax_result['total_included']
                else:
                    self.price_unit = tax_result['total_excluded']

        return result

    @api.depends('price_unit', 'tax_ids', 'order_id.tax_calculation_mode')
    def _compute_price_display(self):
        """Computa el precio a mostrar según el modo de cálculo"""
        for line in self:
            if line.order_id.tax_calculation_mode == 'tax_included':
                # Mostrar precio con impuestos incluidos
                if line.tax_ids:
                    tax_result = line.tax_ids.compute_all(
                        line.price_unit,
                        currency=line.order_id.currency_id,
                        quantity=1.0,
                        product=line.product_id,
                        partner=line.order_id.partner_id
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
