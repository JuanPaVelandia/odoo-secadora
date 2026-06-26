# -*- coding: utf-8 -*-
from odoo import models, fields


class AccountDebitNote(models.TransientModel):
    _inherit = 'account.debit.note'

    copy_lines = fields.Boolean(
        "Copy Lines",
        default=True,
        help="In case you need to do corrections for every line, it can be in handy to copy them.",
    )

    def _prepare_default_values(self, move):
        if move.move_type in ('in_refund', 'out_refund'):
            move_type = 'in_invoice' if move.move_type == 'in_refund' else 'out_invoice'
        else:
            move_type = move.move_type
        default_values = {
            'ref': '%s, %s' % (move.name, self.reason) if self.reason else move.name,
            'date': self.date or move.date,
            'invoice_date': move.is_invoice(include_receipts=True) and (self.date or move.date) or False,
            'journal_id': self.journal_id and self.journal_id.id or move.journal_id.id,
            'invoice_payment_term_id': None,
            'debit_origin_id': move.id,
            'move_type': move_type,
        }
        if not self.copy_lines:
            default_values['line_ids'] = [(5, 0, 0)]
        return default_values
