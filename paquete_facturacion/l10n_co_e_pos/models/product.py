# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.tools import format_amount


class ProductProduct(models.Model):
    _inherit = 'product.product'

    # Campos de precio con y sin impuestos para variantes
    lst_price_incl = fields.Monetary(
        string="Precio Venta (c/IVA)",
        compute="_compute_lst_price_with_taxes",
        currency_field="currency_id",
        help="Precio de venta con impuestos incluidos"
    )

    lst_price_excl = fields.Monetary(
        string="Precio Venta (s/IVA)",
        compute="_compute_lst_price_with_taxes",
        currency_field="currency_id",
        help="Precio de venta sin impuestos"
    )

    taxes_price_include = fields.Boolean(
        string="Impuestos Incluidos",
        compute="_compute_taxes_price_include",
        store=True,
        help="Indica si los impuestos del producto está incluidos en el precio"
    )

    @api.depends('taxes_id', 'taxes_id.price_include')
    def _compute_taxes_price_include(self):
        """Determina si los impuestos están incluidos en el precio"""
        for product in self:
            product.taxes_price_include = any(
                tax.price_include for tax in product.taxes_id
            )

    @api.depends('lst_price', 'taxes_id')
    def _compute_lst_price_with_taxes(self):
        """Calcula precio con y sin impuestos para variantes"""
        for product in self:
            if product.taxes_id:
                tax_result = product.taxes_id._filter_taxes_by_company(
                    self.env.company
                ).compute_all(
                    product.lst_price,
                    product=product,
                    partner=self.env['res.partner']
                )
                product.lst_price_incl = tax_result['total_included']
                product.lst_price_excl = tax_result['total_excluded']
            else:
                product.lst_price_incl = product.lst_price
                product.lst_price_excl = product.lst_price

    def _construct_tax_string(self, price):
        """Computa el precio con o sin impuestos según la configuración del impuesto

        Args:
            price: Precio base del producto

        Returns:
            dict con tax_string, price_included y price_excluded
        """
        currency = self.currency_id

        # Calcular impuestos sobre el precio
        res = self.taxes_id._filter_taxes_by_company(self.env.company).compute_all(
            price,
            product=self,
            partner=self.env['res.partner']
        )

        joined = []
        included = res['total_included']
        excluded = res['total_excluded']

        # Si el precio con impuesto es diferente al precio base, mostrar "Incl. Taxes"
        if not currency.is_zero(included - price):
            joined.append(_('%(amount)s Incl. Taxes',
                          amount=format_amount(self.env, included, currency)))

        # Si el precio sin impuesto es diferente al precio base, mostrar "Excl. Taxes"
        if not currency.is_zero(excluded - price):
            joined.append(_('%(amount)s Excl. Taxes',
                          amount=format_amount(self.env, excluded, currency)))

        if joined:
            tax_string = f"(= {', '.join(joined)})"
        else:
            tax_string = ""

        return {
            'tax_string': tax_string,
            'price_included': included,
            'price_excluded': excluded,
        }

    def _get_combination_info_variant(self):
        """Override para incluir información de impuestos y datos adicionales en variantes"""
        res = super()._get_combination_info_variant()

        # Agregar unidad de medida
        if self.uom_id:
            res['uom_name'] = self.uom_id.name

        # Calcular precio con impuestos
        price = res.get('price', 0)
        if price:
            tax_info = self._construct_tax_string(price)

            res.update({
                'price_tax_string': tax_info['tax_string'],
                'price_included': tax_info['price_included'],
                'price_excluded': tax_info['price_excluded'],
            })

        return res


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # Campos de precio con y sin impuestos
    list_price_incl = fields.Monetary(
        string="Precio Venta (c/IVA)",
        compute="_compute_list_price_with_taxes",
        currency_field="currency_id",
        help="Precio de venta con impuestos incluidos"
    )

    list_price_excl = fields.Monetary(
        string="Precio Venta (s/IVA)",
        compute="_compute_list_price_with_taxes",
        currency_field="currency_id",
        help="Precio de venta sin impuestos"
    )

    taxes_price_include = fields.Boolean(
        string="Impuestos Incluidos",
        compute="_compute_taxes_price_include",
        store=True,
        help="Indica si los impuestos del producto están incluidos en el precio"
    )

    @api.depends('taxes_id', 'taxes_id.price_include')
    def _compute_taxes_price_include(self):
        """Determina si los impuestos están incluidos en el precio"""
        for product in self:
            product.taxes_price_include = any(
                tax.price_include for tax in product.taxes_id
            )

    @api.depends('list_price', 'taxes_id')
    def _compute_list_price_with_taxes(self):
        """Calcula precio con y sin impuestos para vistas"""
        for product in self:
            if product.taxes_id:
                tax_result = product.taxes_id._filter_taxes_by_company(
                    self.env.company
                ).compute_all(
                    product.list_price,
                    product=product,
                    partner=self.env['res.partner']
                )
                product.list_price_incl = tax_result['total_included']
                product.list_price_excl = tax_result['total_excluded']
            else:
                product.list_price_incl = product.list_price
                product.list_price_excl = product.list_price
