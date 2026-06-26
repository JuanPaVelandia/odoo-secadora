# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class ProductCategory(models.Model):
    _inherit = 'product.category'

    # Impuestos por defecto para productos de esta categoria
    taxes_ids = fields.Many2many(
        'account.tax',
        'product_category_taxes_rel',
        'categ_id',
        'tax_id',
        string="Impuestos de Venta",
        domain="[('type_tax_use','=','sale')]",
        help="Impuestos aplicados por defecto en ventas para productos de esta categoria.",
    )
    supplier_taxes_ids = fields.Many2many(
        'account.tax',
        'product_category_supplier_taxes_rel',
        'categ_id',
        'tax_id',
        string="Impuestos de Compra",
        domain="[('type_tax_use','=','purchase')]",
        help="Impuestos aplicados por defecto en compras para productos de esta categoria.",
    )

    # Cuentas de devolucion por categoria
    property_account_refund_income_categ_id = fields.Many2one(
        'account.account',
        string='Cuenta Devolucion Ventas',
        company_dependent=True,
        domain="[('account_type', 'in', ['income', 'income_other']), ('active', '=', True)]",
        help='Cuenta contable para devoluciones en ventas de productos de esta categoria.'
    )
    property_account_refund_expense_categ_id = fields.Many2one(
        'account.account',
        string='Cuenta Devolucion Compras',
        company_dependent=True,
        domain="[('account_type', 'in', ['expense', 'expense_direct_cost']), ('active', '=', True)]",
        help='Cuenta contable para devoluciones en compras de productos de esta categoria.'
    )


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # Campos DIAN para facturacion electronica
    dian_brand = fields.Char(
        'Marca (DIAN)',
        help='Marca reportada en los documentos electronicos a la DIAN.'
    )
    dian_model = fields.Char(
        'Modelo (DIAN)',
        help='Modelo reportado en los documentos electronicos a la DIAN.'
    )
    dian_customs_code = fields.Char(
        'Partida Arancelaria',
        help='Codigo arancelario para facturas de exportacion.'
    )

    # Cuentas de devolucion por producto
    property_account_refund_income_id = fields.Many2one(
        'account.account',
        string='Cuenta Devolucion Ventas',
        company_dependent=True,
        domain="[('account_type', 'in', ['income', 'income_other']), ('active', '=', True)]",
        help='Cuenta contable para devoluciones en ventas. Si no se especifica, se usa la de la categoria o la cuenta de ingresos.'
    )
    property_account_refund_expense_id = fields.Many2one(
        'account.account',
        string='Cuenta Devolucion Compras',
        company_dependent=True,
        domain="[('account_type', 'in', ['expense', 'expense_direct_cost']), ('active', '=', True)]",
        help='Cuenta contable para devoluciones en compras. Si no se especifica, se usa la de la categoria o la cuenta de gastos.'
    )

    def _get_product_accounts(self):
        """Extiende para incluir cuentas de devolucion del producto o categoria"""
        accounts = super()._get_product_accounts()

        # Cuenta devolucion ventas: producto > categoria > cuenta ingreso
        refund_income = (
            self.property_account_refund_income_id or
            self.categ_id.property_account_refund_income_categ_id or
            accounts.get('income')
        )
        if refund_income:
            accounts['refund_income'] = refund_income

        # Cuenta devolucion compras: producto > categoria > cuenta gasto
        refund_expense = (
            self.property_account_refund_expense_id or
            self.categ_id.property_account_refund_expense_categ_id or
            accounts.get('expense')
        )
        if refund_expense:
            accounts['refund_expense'] = refund_expense

        return accounts
