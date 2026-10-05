# -*- coding: utf-8 -*-

from odoo import models, fields, api


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    # Los pagos ya se registran en contabilidad; aquí solo se marcan para
    # descontarlos del saldo de labores. Ambos campos se proponen solos y se
    # pueden corregir a mano en el pago.
    finca_campana_id = fields.Many2one(
        'finca.campana',
        string='Campaña de labores',
        compute='_compute_finca_labores',
        store=True,
        readonly=False,
        index=True,
        help='Si tiene campaña, el pago se descuenta del saldo de labores del '
             'operador. Se asigna sola a los pagos a operadores de finca según '
             'la fecha; déjela vacía si el pago no es por labores.',
    )
    finca_dueno_id = fields.Many2one(
        'res.partner',
        string='Dueño que paga',
        compute='_compute_finca_labores',
        store=True,
        readonly=False,
        index=True,
        help='Dueño a cuya cuenta se descuenta el pago. Se propone el contacto '
             'de la compañía del pago cuando esa compañía es dueña de alguna finca.',
    )

    @api.depends('partner_id', 'partner_id.es_operador_finca', 'date', 'company_id')
    def _compute_finca_labores(self):
        Campana = self.env['finca.campana']
        duenos = self.env['secadora.lugar'].sudo().search([('dueno_id', '!=', False)]).dueno_id
        for pay in self:
            # Asignar siempre: un compute almacenado que deja registros sin
            # valor falla. Lo ya marcado (a mano o antes) no se toca.
            pay.finca_campana_id = pay.finca_campana_id
            pay.finca_dueno_id = pay.finca_dueno_id
            if pay.finca_campana_id or not pay.partner_id.es_operador_finca or not pay.date:
                continue
            pay.finca_campana_id = Campana.search([
                ('fecha_inicio', '<=', pay.date),
                ('fecha_fin', '>=', pay.date),
            ], limit=1)
            if pay.finca_campana_id and not pay.finca_dueno_id and pay.company_id.partner_id in duenos:
                pay.finca_dueno_id = pay.company_id.partner_id
