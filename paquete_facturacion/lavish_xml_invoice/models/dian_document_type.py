# -*- coding: utf-8 -*-

from odoo import models, fields, api


class DianDocumentType(models.Model):
    """Model to store DIAN document types"""
    _name = 'dian.document.type'
    _description = 'DIAN Document Type'
    _order = 'code'

    code = fields.Char(
        string='Code',
        required=True,
        help='DIAN document type code (e.g., 01, 02, 91, 92)'
    )
    name = fields.Char(
        string='Name',
        required=True,
        translate=True,
        help='Document type name (e.g., Factura de Venta, Nota Crédito)'
    )
    active = fields.Boolean(
        string='Active',
        default=True,
        help='Whether this document type is active'
    )

    _code_unique = models.Constraint('unique(code)', 'The document type code must be unique!')

    def _compute_display_name(self):
        """Display code and name together"""
        for record in self:
            record.display_name = f"[{record.code}] {record.name}"
