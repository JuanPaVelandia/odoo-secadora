# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Para filtrar los campos "Dueño" / "A cuenta de": solo los dueños de
    # alguna finca y las sociedades con socios, no todos los contactos.
    es_dueno_finca = fields.Boolean(
        string='Dueño de finca',
        compute='_compute_es_dueno_finca',
        search='_search_es_dueno_finca',
    )

    def _duenos_finca_domain(self):
        lugares = self.env['secadora.lugar'].sudo().search([('dueno_id', '!=', False)])
        return ['|', ('id', 'in', lugares.dueno_id.ids), ('finca_socio_ids', '!=', False)]

    def _compute_es_dueno_finca(self):
        duenos = self.sudo().search(self._duenos_finca_domain())
        for rec in self:
            rec.es_dueno_finca = rec in duenos

    def _search_es_dueno_finca(self, operator, value):
        if operator not in ('=', '!=') or not isinstance(value, bool):
            raise NotImplementedError('Operador no soportado para es_dueno_finca')
        dominio = self._duenos_finca_domain()
        return dominio if (operator == '=') == value else ['!'] + dominio

    es_operador_finca = fields.Boolean(
        string='Operador de finca',
        help='Trabajador de campo. Sus pagos se descuentan del saldo de labores '
             'de la campaña. Se marca solo al confirmar una labor a su nombre.',
    )

    def _marcar_operador_finca(self):
        # sudo: quien registra labores no siempre puede editar contactos.
        self.filtered(lambda p: not p.es_operador_finca).sudo().write({'es_operador_finca': True})
