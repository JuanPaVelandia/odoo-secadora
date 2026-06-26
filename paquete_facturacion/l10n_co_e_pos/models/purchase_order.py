# -*- coding: utf-8 -*-

from odoo import models, fields, api


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

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
                    # Re-ejecutar el compute del precio para aplicar el nuevo modo
                    line._compute_price_unit_and_date_planned_and_name()


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    @api.depends('product_id', 'product_qty', 'product_uom_id', 'order_id.partner_id',
                 'order_id.date_order', 'order_id.company_id', 'order_id.tax_calculation_mode')
    def _compute_price_unit_and_date_planned_and_name(self):
        """Override para ajustar precio según el modo de cálculo de impuestos del documento

        Este método se ejecuta después del cálculo estándar que obtiene el precio
        del historial de proveedores (supplierinfo)
        """
        # Ejecutar el método estándar que obtiene el precio del proveedor
        result = super()._compute_price_unit_and_date_planned_and_name()

        # Ajustar según el modo de cálculo de impuestos
        for line in self:
            if not line.order_id.tax_calculation_mode or not line.product_id or not line.tax_ids:
                continue

            if line.invoice_lines:
                # No modificar líneas ya facturadas
                continue

            # El precio actual ya viene ajustado por _fix_tax_included_price_company
            # Ahora necesitamos verificar si debemos convertirlo según tax_calculation_mode
            current_price = line.price_unit

            if not current_price:
                continue

            taxes = line.tax_ids.filtered(lambda t: t.company_id == line.company_id)
            if not taxes:
                continue

            # Determinar si los impuestos del producto están incluidos en el precio
            product_taxes_included = any(tax.price_include for tax in line.product_id.supplier_taxes_id)

            # Calcular ambos precios (con y sin impuestos)
            if product_taxes_included:
                # El precio actual incluye impuestos
                tax_result = taxes.compute_all(
                    current_price,
                    currency=line.currency_id,
                    quantity=1.0,
                    product=line.product_id,
                    partner=line.partner_id
                )
                price_with_tax = current_price
                price_without_tax = tax_result['total_excluded']
            else:
                # El precio actual NO incluye impuestos
                tax_result = taxes.compute_all(
                    current_price,
                    currency=line.currency_id,
                    quantity=1.0,
                    product=line.product_id,
                    partner=line.partner_id
                )
                price_without_tax = current_price
                price_with_tax = tax_result['total_included']

            # Aplicar el precio según el modo de cálculo seleccionado
            if line.order_id.tax_calculation_mode == 'tax_included':
                line.price_unit = price_with_tax
            else:
                line.price_unit = price_without_tax

        return result
