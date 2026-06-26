# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"
    resolution_number = fields.Char("Resolution number in invoice")
    resolution_date = fields.Date(string="Resolution Date")
    resolution_date_to = fields.Date(string="Resolution Date To")
    resolution_number_from = fields.Char(string="Resolution  Number From")
    resolution_number_to = fields.Char(string="Resolution Number To")

    # Relación a resolución DIAN
    dian_resolution_id = fields.Many2one(
        'ir.sequence.dian_resolution',
        string='Resolución DIAN',
        readonly=True,
        copy=False,
        help='Resolución DIAN activa al momento de confirmar la factura'
    )

    # Campo texto computado con info DIAN desde la relación
    dian_resolution_info = fields.Text(
        string="Información Resolución DIAN",
        compute='_compute_dian_resolution_info',
        store=False,
    )

    @api.depends('dian_resolution_id')
    def _compute_dian_resolution_info(self):
        """Computa texto informativo de la resolución DIAN"""
        for move in self:
            res = move.dian_resolution_id
            if res:
                lines = []
                lines.append(f"Resolución DIAN No. {res.resolution_number}")
                if res.date_from and res.date_to:
                    lines.append(f"Vigencia: {res.date_from.strftime('%d/%m/%Y')} al {res.date_to.strftime('%d/%m/%Y')}")
                if res.number_from and res.number_to:
                    lines.append(f"Autoriza del {res.number_from} al {res.number_to}")
                move.dian_resolution_info = '\n'.join(lines)
            else:
                move.dian_resolution_info = False

    def validate_number_phone(self, data):
        """Retorna telefono y/o celular para reportes de factura"""
        if data.phone and data.mobile:
            return f"{data.phone} - {data.mobile}"
        return data.phone or data.mobile or ''

    def validate_state_city(self, data):
        """Retorna Pais, Departamento, Ciudad para reportes de factura"""
        parts = []
        if data.country_id:
            parts.append(data.country_id.name)
        if data.state_id:
            parts.append(data.state_id.name)
        if data.city_id:
            parts.append(data.city_id.name)
        return ' '.join(parts)

    def _post(self, soft=True):
        """Guarda relación a resolución DIAN al confirmar factura"""
        result = super()._post(soft)
        for inv in self:
            if inv.journal_id.sequence_id:
                resolution = self.env["ir.sequence.dian_resolution"].search([
                    ("sequence_id", "=", inv.journal_id.sequence_id.id),
                    ("active_resolution", "=", True),
                ], limit=1)
                if resolution:
                    inv.dian_resolution_id = resolution.id
                    # Snapshot the active resolution details onto the invoice for reporting.
                    inv.resolution_number = resolution.resolution_number
                    inv.resolution_date = resolution.date_from
                    inv.resolution_date_to = resolution.date_to
                    inv.resolution_number_from = str(resolution.number_from) if resolution.number_from else False
                    inv.resolution_number_to = str(resolution.number_to) if resolution.number_to else False
        return result


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    @api.depends('product_id', 'account_id', 'move_id.move_type')
    def _compute_account_id(self):
        """Usa cuenta de devolucion cuando es nota credito"""
        super()._compute_account_id()
        for line in self:
            if not line.product_id or not line.move_id:
                continue

            move_type = line.move_id.move_type

            # Solo para notas credito (devoluciones)
            if move_type == 'out_refund':  # Nota credito cliente
                accounts = line.product_id._get_product_accounts()
                refund_account = accounts.get('refund_income')
                if refund_account and refund_account != line.account_id:
                    line.account_id = refund_account

            elif move_type == 'in_refund':  # Nota credito proveedor
                accounts = line.product_id._get_product_accounts()
                refund_account = accounts.get('refund_expense')
                if refund_account and refund_account != line.account_id:
                    line.account_id = refund_account
