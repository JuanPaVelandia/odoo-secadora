# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.tools import SQL


class AccountInvoiceReportInherit(models.Model):
	_inherit = "account.invoice.report"

	diancode_id = fields.Many2one('dian.document', string='Código DIAN')

	_depends = {
		'account.move': ['diancode_id'],
	}

	def _select(self) -> SQL:
		return SQL("%s, move.diancode_id as diancode_id", super()._select())

	def _group_by(self) -> SQL:
		return SQL("%s, move.diancode_id", super()._group_by())