# -*- coding: utf-8 -*-

from odoo import models, fields


class ResPartner(models.Model):
    _inherit = 'res.partner'

    es_operador_finca = fields.Boolean(
        string='Operador de finca',
        help='Trabajador de campo. Sus pagos se descuentan del saldo de labores '
             'de la campaña. Se marca solo al confirmar una labor a su nombre.',
    )

    def _marcar_operador_finca(self):
        # sudo: quien registra labores no siempre puede editar contactos.
        self.filtered(lambda p: not p.es_operador_finca).sudo().write({'es_operador_finca': True})
