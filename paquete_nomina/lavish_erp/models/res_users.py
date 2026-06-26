# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResUsers(models.Model):
    _inherit = 'res.users'

    signature_documents = fields.Binary(string='Firma lavish')
    signature_certification_laboral = fields.Boolean('Firma autorizada para certificado laboral')