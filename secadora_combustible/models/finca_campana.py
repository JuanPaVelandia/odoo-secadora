# -*- coding: utf-8 -*-

from odoo import models


class FincaCampana(models.Model):
    _inherit = 'finca.campana'

    def _asignar_pagos(self):
        """Además de los pagos, las compras de ACPM sin campaña cuya fecha cae
        en la campaña (p. ej. facturas marcadas antes de crearla)."""
        super()._asignar_pagos()
        lineas = self.env['account.move.line'].sudo().search([
            ('acpm_es', '=', True),
            ('acpm_campana_id', '=', False),
        ])
        lineas._compute_acpm_campana_id()
