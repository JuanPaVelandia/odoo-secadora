from odoo import api, fields, models
import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    # Ciudad para cálculo de ICA
    # Para facturas de venta: ciudad de la compañía (donde se realiza la actividad)
    # Para facturas de compra: ciudad del proveedor (donde está ubicado)
    city_id = fields.Many2one(
        'res.city',
        string='Municipality (ICA)',
        compute='_compute_partner_city_id',
        store=True,
        readonly=False,
        precompute=True,
        help='Municipality for ICA calculation. Sales: company city. Purchases: partner city.'
    )

    @api.depends('partner_id', 'move_type', 'company_id', 'journal_id')
    def _compute_partner_city_id(self):
        """
        Compute city_id based on move type and journal configuration:

        Priority:
        1. Journal ICA city (if configured with use_journal_ica_city = True)
        2. For sales (out_invoice, out_refund): Use company's city (where activity is performed)
        3. For purchases (in_invoice, in_refund): Use partner's city (supplier location)
        """
        for move in self:
            city_id = False

            # Prioridad 1: Ciudad del diario si está configurada
            if move.journal_id and move.journal_id.use_journal_ica_city and move.journal_id.ica_city_id:
                city_id = move.journal_id.ica_city_id.id
            elif move.move_type in ('out_invoice', 'out_refund'):
                # Prioridad 2: Facturas de venta -> ciudad de la compañía
                if move.company_id.partner_id.city_id:
                    city_id = move.company_id.partner_id.city_id.id
            elif move.move_type in ('in_invoice', 'in_refund'):
                # Prioridad 3: Facturas de compra -> ciudad del proveedor
                if move.partner_id and move.partner_id.city_id:
                    city_id = move.partner_id.city_id.id

            move.city_id = city_id

    def _prepare_tax_context(self, base_line_record=None):
        """Prepare context for tax computation with additional parameters

        :param base_line_record: Optional record to include for date detection
        """
        # Handle empty recordset
        if not self:
            return {}

        self.ensure_one()
        context = {
            'invoice_date': self.invoice_date or self.date or fields.Date.context_today(self),
            'move_type': self.move_type,
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            # Ciudad para cálculo de ICA
            'city_id': self.city_id.id if self.city_id else False,
            'municipality_id': self.city_id.id if self.city_id else False,
        }

        # Add the record if provided (for cron compatibility)
        if base_line_record:
            context['base_line_record'] = base_line_record

        return context

    @api.depends('line_ids.price_subtotal', 'line_ids.tax_base_amount', 'line_ids.tax_line_id', 'partner_id', 'currency_id', 'amount_total', 'amount_untaxed', 'amount_tax', 'invoice_date')
    def _compute_tax_totals(self):
        """Override to pass additional context for tax threshold validation"""
        for move in self:
            if move.is_invoice(include_receipts=True):
                # Add context for tax computation
                move = move.with_context(**move._prepare_tax_context())
        return super()._compute_tax_totals()

    def _sync_tax_lines(self, container):
        """Override to pass invoice date context when syncing tax lines"""
        # Add context for each move individually
        for move in container['records']:
            if move.is_invoice(include_receipts=True):
                move = move.with_context(**move._prepare_tax_context())

        # Call parent without modifying self's context (self can be multiple records)
        return super(AccountMove, self)._sync_tax_lines(container)


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.depends('quantity', 'discount', 'price_unit', 'tax_ids', 'currency_id', 'move_id.invoice_date')
    def _compute_totals(self):
        """Override to pass invoice date context when computing totals"""
        # Process each line with its move's context
        result = None
        for line in self:
            if line.display_type in ('product', 'rounding') and line.move_id:
                # Add invoice date to context for tax computation
                ctx = line.move_id._prepare_tax_context()
                result = super(AccountMoveLine, line.with_context(**ctx))._compute_totals()
            else:
                result = super(AccountMoveLine, line)._compute_totals()
        return result

    def _get_computed_taxes(self):
        """Override to ensure invoice date is in context when computing taxes"""
        self.ensure_one()

        if self.move_id:
            # Add context with invoice date
            self = self.with_context(**self.move_id._prepare_tax_context())

        return super()._get_computed_taxes()

    def _prepare_base_line_for_taxes_computation(self):
        """Prepare base line with additional context for tax computation"""
        self.ensure_one()
        base_line = super()._prepare_base_line_for_taxes_computation()

        # Add evaluation date to base line
        if self.move_id:
            base_line['date_eval'] = self.move_id.invoice_date or self.move_id.date or fields.Date.context_today(self)

        return base_line