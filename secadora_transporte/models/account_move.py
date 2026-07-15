# -*- coding: utf-8 -*-

from odoo import models, fields, api


class AccountMove(models.Model):
    _inherit = 'account.move'

    flete_ids = fields.One2many(
        'secadora.flete',
        'factura_transportadora_id',
        string='Fletes',
        help='Fletes de transporte asociados a esta factura',
    )
    flete_count = fields.Integer(
        string='Nº Fletes',
        compute='_compute_flete_count',
    )

    @api.depends('flete_ids')
    def _compute_flete_count(self):
        # sudo: el form de factura lo abren usuarios contables que no tienen
        # ACL sobre secadora.flete; sin esto, TODA factura fallaría al cargar.
        for rec in self:
            rec.flete_count = len(rec.sudo().flete_ids)

    def es_por_pagar(self):
        """Factura publicada con saldo pendiente (sin pagar o pago parcial).

        Predicado único de "por pagar" para el tablero de transporte, el
        wizard de impresión y su revalidación. El filtro "Facturados por
        pagar" de flete_views.xml replica este dominio en XML (los dominios
        de vista deben ser literales) — mantenerlos sincronizados.
        """
        self.ensure_one()
        return self.state == 'posted' and self.payment_state in ('not_paid', 'partial')

    def fletes_activos(self):
        """Fletes no cancelados de la factura (para el reporte de giro).

        Un flete puede cancelarse después de asociarse a la factura sin que
        se limpie el vínculo; el soporte de giro no debe listarlo ni sumarlo.

        sudo acotado: el pesaje o los lugares del viaje pueden pertenecer a
        una compañía distinta de la que paga la factura, y la regla
        multi-compañía bloquearía su lectura al renderizar el PDF. Los datos
        quedan acotados a los fletes de esta factura, que el usuario ya
        puede leer.
        """
        self.ensure_one()
        return self.sudo().flete_ids.filtered(lambda f: f.state != 'cancelado')

    def action_ver_fletes(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Fletes de la Factura',
            'res_model': 'secadora.flete',
            'view_mode': 'list,form',
            'domain': [('factura_transportadora_id', '=', self.id)],
        }
