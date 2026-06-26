# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

class DianTributes(models.Model):
	_name = 'dian.tributes'
	_description = 'Model DIAN Tributes'
	_rec_name = 'code_name'

	code = fields.Char(string="Código Tributo DIAN", required=True)
	name = fields.Char(string="Descripción tributos DIAN", required=True)
	code_name = fields.Char(string="Código y nombre Tributo", compute = "_code_name", store = True) 

	@api.depends('code','name')
	def _code_name(self):		
		for rec_tributes in self:
			code = rec_tributes.code or ''
			name = rec_tributes.name or ''
			if code and name:
				rec_tributes.code_name = f"{code}-{name}"
			else:
				rec_tributes.code_name = code or name
		return

