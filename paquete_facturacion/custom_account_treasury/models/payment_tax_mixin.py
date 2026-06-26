# -*- coding: utf-8 -*-
"""
Mixin para manejo de impuestos y pronto pago en pagos.
Sigue los patrones de Odoo 18 (account y hr_expense).
"""
from odoo import models, fields, api, _
from odoo.tools import float_is_zero, float_compare
from collections import defaultdict
import logging

_logger = logging.getLogger(__name__)


class PaymentTaxMixin(models.AbstractModel):
    """
    Mixin que proporciona funcionalidad de impuestos para pagos.
    Implementa lógica similar a account.move y hr.expense.
    """
    _name = 'payment.tax.mixin'
    _description = 'Mixin de Impuestos para Pagos'

    # === Campos para pronto pago (Early Payment Discount) ===
    has_epd = fields.Boolean(
        string='Tiene Pronto Pago',
        compute='_compute_has_epd',
        store=True,
        help='Indica si alguna factura tiene descuento por pronto pago disponible'
    )
    epd_amount = fields.Float(
        string='Descuento Pronto Pago',
        compute='_compute_epd_amount',
        store=True,
        digits='Product Price',
        help='Monto total de descuento por pronto pago aplicable'
    )
    apply_epd = fields.Boolean(
        string='Aplicar Pronto Pago',
        default=False,
        help='Si está activo, aplica el descuento por pronto pago a las facturas elegibles'
    )

    # === Campos para reversión de impuestos ===
    tax_revert_mode = fields.Selection([
        ('none', 'Sin Reversión'),
        ('partial', 'Reversión Parcial'),
        ('full', 'Reversión Total'),
    ], string='Modo Reversión IVA', default='none',
        help='Define cómo se revierten los impuestos del documento original')

    tax_revert_account_id = fields.Many2one(
        'account.account',
        string='Cuenta Reversión IVA',
        domain="[('account_type', 'not in', ('asset_receivable', 'liability_payable'))]",
        help='Cuenta donde se registra el impuesto revertido'
    )

    # === Métodos de cálculo ===

    @api.depends('payment_line_ids.invoice_id', 'payment_line_ids.invoice_id.invoice_payment_term_id')
    def _compute_has_epd(self):
        """Verifica si hay facturas con descuento por pronto pago."""
        for payment in self:
            has_epd = False
            for line in payment.payment_line_ids.filtered(lambda l: l.invoice_id):
                invoice = line.invoice_id
                # Verificar si la factura tiene término de pago con descuento
                if invoice.invoice_payment_term_id:
                    epd_lines = invoice.line_ids.filtered(lambda l: l.display_type == 'epd')
                    if epd_lines:
                        has_epd = True
                        break
            payment.has_epd = has_epd

    @api.depends('payment_line_ids.invoice_id', 'apply_epd', 'date')
    def _compute_epd_amount(self):
        """Calcula el monto total de descuento por pronto pago disponible."""
        for payment in self:
            epd_total = 0.0
            if payment.apply_epd:
                for line in payment.payment_line_ids.filtered(lambda l: l.invoice_id):
                    epd_total += payment._get_invoice_epd_amount(line.invoice_id)
            payment.epd_amount = epd_total

    def _get_invoice_epd_amount(self, invoice):
        """
        Obtiene el monto de descuento por pronto pago de una factura.
        Similar a la lógica en account.move para early payment discount.
        """
        self.ensure_one()
        if not invoice or not invoice.invoice_payment_term_id:
            return 0.0

        # Buscar líneas EPD en la factura
        epd_lines = invoice.line_ids.filtered(
            lambda l: l.display_type == 'epd' and not l.reconciled
        )

        if not epd_lines:
            return 0.0

        # Verificar si el pago está dentro del período de descuento
        payment_date = self.date or fields.Date.context_today(self)

        for epd_line in epd_lines:
            if epd_line.date_maturity and payment_date <= epd_line.date_maturity:
                # Retornar el monto del descuento (es negativo en la factura)
                return abs(epd_line.amount_residual)

        return 0.0

    # === Métodos de preparación de líneas base (siguiendo patrón Odoo) ===

    def _prepare_base_line_for_taxes(self, line, price_unit=None, quantity=1.0):
        """
        Prepara un diccionario de línea base para cálculo de impuestos.
        Sigue el patrón de hr_expense._prepare_base_line_for_taxes_computation.
        """
        self.ensure_one()

        if price_unit is None:
            price_unit = abs(line.payment_amount)

        return {
            'record': line,
            'price_unit': price_unit,
            'quantity': quantity,
            'discount': 0.0,
            'product': line.product_id if hasattr(line, 'product_id') else False,
            'partner': line.partner_id or self.partner_id,
            'currency': line.payment_currency_id or self.currency_id,
            'account': line.account_id,
            'analytic_distribution': line.analytic_distribution if hasattr(line, 'analytic_distribution') else {},
            'tax_ids': line.tax_ids if hasattr(line, 'tax_ids') else self.env['account.tax'],
            'taxes_computed': False,
            'price_subtotal': price_unit * quantity,
            'extra_context': {},
        }

    def _compute_taxes_for_line(self, base_line, is_refund=False, force_price_include=None):
        """
        Calcula impuestos para una línea base.
        Sigue el patrón de account.tax.compute_all().

        Args:
            base_line: Diccionario preparado por _prepare_base_line_for_taxes
            is_refund: Si es True, usa cuentas de reembolso
            force_price_include: Forzar modo precio incluido

        Returns:
            Diccionario con resultados de compute_all()
        """
        taxes = base_line.get('tax_ids', self.env['account.tax'])
        if not taxes:
            return {
                'total_excluded': base_line['price_subtotal'],
                'total_included': base_line['price_subtotal'],
                'taxes': [],
                'base_tags': [],
            }

        # Contexto para forzar precio incluido (como en expenses)
        ctx = {}
        if force_price_include is not None:
            ctx['force_price_include'] = force_price_include

        return taxes.with_context(**ctx).compute_all(
            base_line['price_unit'],
            currency=base_line['currency'],
            quantity=base_line['quantity'],
            product=base_line.get('product'),
            partner=base_line.get('partner'),
            is_refund=is_refund,
        )

    # === Métodos de creación de líneas de impuesto ===

    def _prepare_tax_line_vals(self, tax_data, base_line, payment_line):
        """
        Prepara los valores para crear una línea de impuesto.

        Args:
            tax_data: Diccionario de un impuesto de compute_all()['taxes']
            base_line: Línea base original
            payment_line: Línea de pago origen

        Returns:
            Diccionario de valores para account.payment.detail
        """
        self.ensure_one()

        tax = self.env['account.tax'].browse(tax_data['id'])

        # Obtener cuenta del impuesto
        account = self.env['account.account'].browse(tax_data.get('account_id'))
        if not account:
            # Fallback: usar líneas de repartición
            repartition_lines = tax.invoice_repartition_line_ids.filtered(
                lambda l: l.repartition_type == 'tax' and l.account_id
            )
            account = repartition_lines[0].account_id if repartition_lines else payment_line.account_id

        # Signo: el impuesto revertido tiene signo opuesto
        sign = -1 if self.payment_type == 'inbound' else 1
        tax_amount = tax_data['amount'] * sign

        return {
            'payment_id': self.id,
            'name': f"IVA: {tax.name}",
            'account_id': account.id,
            'partner_id': payment_line.partner_id.id or self.partner_id.id,
            'currency_id': (payment_line.payment_currency_id or self.currency_id).id,
            'company_currency_id': self.company_currency_id.id,
            'payment_amount': tax_amount,
            'payment_currency_id': (payment_line.payment_currency_id or self.currency_id).id,
            'auto_tax_line': True,
            'display_type': 'tax',
            'tax_line_id2': tax.id,
            'tax_base_amount': base_line['price_subtotal'],
            'tax_repartition_line_id': tax_data.get('tax_repartition_line_id'),
            'analytic_distribution': base_line.get('analytic_distribution', {}),
            'parent_line_id': payment_line.id,
            'is_tax_revert_line': True,
        }

    # === Métodos de acción principales ===

    def action_compute_taxes(self):
        """
        Recalcula todos los impuestos de las líneas de pago.
        Elimina líneas de impuesto existentes y crea nuevas.
        """
        self.ensure_one()

        # Eliminar líneas de impuesto automáticas existentes
        self.payment_line_ids.filtered(lambda l: l.auto_tax_line).unlink()

        # Procesar cada línea con impuestos
        PaymentDetail = self.env['account.payment.detail']

        for line in self.payment_line_ids.filtered(lambda l: l.tax_ids and not l.is_main):
            base_line = self._prepare_base_line_for_taxes(line)

            # Calcular impuestos
            is_refund = self.payment_type == 'inbound'  # Cobros son como reembolsos
            tax_result = self._compute_taxes_for_line(base_line, is_refund=is_refund)

            # Crear líneas de impuesto
            for tax_data in tax_result['taxes']:
                vals = self._prepare_tax_line_vals(tax_data, base_line, line)
                PaymentDetail.create(vals)

            # Actualizar tags de la línea base
            if tax_result.get('base_tags'):
                line.write({
                    'tax_tag_ids': [(6, 0, tax_result['base_tags'])]
                })

        return True

    def action_apply_epd(self):
        """
        Aplica el descuento por pronto pago a las líneas elegibles.
        Crea líneas de ajuste para el descuento.
        """
        self.ensure_one()

        if not self.apply_epd:
            return False

        PaymentDetail = self.env['account.payment.detail']

        for line in self.payment_line_ids.filtered(lambda l: l.invoice_id):
            epd_amount = self._get_invoice_epd_amount(line.invoice_id)

            if float_is_zero(epd_amount, precision_rounding=self.currency_id.rounding):
                continue

            # Crear línea de descuento
            epd_account = self._get_epd_account(line.invoice_id)

            sign = 1 if self.payment_type == 'inbound' else -1

            epd_vals = {
                'payment_id': self.id,
                'name': f"Pronto Pago: {line.invoice_id.name}",
                'account_id': epd_account.id,
                'partner_id': line.partner_id.id or self.partner_id.id,
                'currency_id': self.currency_id.id,
                'company_currency_id': self.company_currency_id.id,
                'payment_amount': epd_amount * sign,
                'payment_currency_id': self.currency_id.id,
                'display_type': 'epd',
                'parent_line_id': line.id,
                'invoice_id': line.invoice_id.id,
            }

            PaymentDetail.create(epd_vals)

            # Ajustar monto de la línea original
            line.payment_amount -= epd_amount

        return True

    def _get_epd_account(self, invoice):
        """
        Obtiene la cuenta para registrar el descuento por pronto pago.
        """
        # Buscar configuración de la compañía o usar cuenta de ingresos/gastos
        if self.payment_type == 'inbound':
            # Para cobros: cuenta de descuentos otorgados (gasto)
            return self.company_id.account_sale_tax_id.refund_repartition_line_ids.filtered(
                lambda l: l.repartition_type == 'base'
            ).account_id or invoice.journal_id.default_account_id
        else:
            # Para pagos: cuenta de descuentos recibidos (ingreso)
            return self.company_id.account_purchase_tax_id.refund_repartition_line_ids.filtered(
                lambda l: l.repartition_type == 'base'
            ).account_id or invoice.journal_id.default_account_id

    def action_revert_invoice_taxes(self, line_ids=None):
        """
        Revierte los impuestos de las facturas seleccionadas.
        Crea líneas que anulan el efecto del IVA del documento original.

        Este método implementa la lógica de "retención de IVA" o
        "reversión parcial de impuestos" común en tesorería.
        """
        self.ensure_one()

        if line_ids:
            lines = self.payment_line_ids.filtered(lambda l: l.id in line_ids)
        else:
            lines = self.payment_line_ids.filtered(lambda l: l.taxes_to_revert_ids)

        if not lines:
            return False

        PaymentDetail = self.env['account.payment.detail']

        for line in lines:
            if not line.taxes_to_revert_ids:
                continue

            # Calcular impuestos a revertir
            base_amount = abs(line.payment_amount)

            for tax in line.taxes_to_revert_ids:
                # Calcular monto del impuesto
                tax_result = tax.compute_all(
                    base_amount,
                    currency=line.payment_currency_id,
                    quantity=1.0,
                    partner=line.partner_id,
                )

                for tax_data in tax_result['taxes']:
                    if tax_data['id'] != tax.id:
                        continue

                    tax_amount = tax_data['amount']

                    # Obtener cuenta de reversión
                    if self.tax_revert_account_id:
                        account = self.tax_revert_account_id
                    else:
                        repartition_lines = tax.invoice_repartition_line_ids.filtered(
                            lambda l: l.repartition_type == 'tax' and l.account_id
                        )
                        account = repartition_lines[0].account_id if repartition_lines else line.account_id

                    # Signo: reversión es opuesto al impuesto original
                    sign = -1 if line.payment_amount > 0 else 1

                    revert_vals = {
                        'payment_id': self.id,
                        'name': f"Reversión IVA: {tax.name}",
                        'account_id': account.id,
                        'partner_id': line.partner_id.id or self.partner_id.id,
                        'currency_id': line.payment_currency_id.id,
                        'company_currency_id': self.company_currency_id.id,
                        'payment_amount': tax_amount * sign,
                        'payment_currency_id': line.payment_currency_id.id,
                        'auto_tax_line': True,
                        'display_type': 'tax',
                        'is_tax_revert_line': True,
                        'tax_line_id2': tax.id,
                        'tax_base_amount': base_amount,
                        'parent_line_id': line.id,
                    }

                    PaymentDetail.create(revert_vals)

        return True

    def action_clear_tax_lines(self):
        """
        Elimina todas las líneas de impuesto automáticas.
        """
        self.ensure_one()
        self.payment_line_ids.filtered(lambda l: l.auto_tax_line or l.is_tax_revert_line).unlink()
        return True
