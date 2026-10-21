# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class FincaPagoReparto(models.Model):
    """A quién le corresponde cada peso de un pago de labores.

    Un solo giro suele cubrir a varias personas: se le gira al encargado, o a
    un tercero que les entrega en efectivo, y él reparte. En contabilidad el
    pago sigue siendo uno, a quien recibió la plata; estas líneas dicen cuánto
    es de cada operador y el libro de saldos las usa en lugar del encabezado
    del pago. Quien recibe no queda con saldo salvo que esté en las líneas.
    """
    _name = 'finca.pago.reparto'
    _description = 'Reparto de un pago entre operadores'
    _order = 'payment_id, id'

    payment_id = fields.Many2one(
        'account.payment',
        string='Pago',
        required=True,
        ondelete='cascade',
        index=True,
    )
    operador_id = fields.Many2one(
        'res.partner',
        string='Operador',
        required=True,
        index=True,
    )
    dueno_id = fields.Many2one(
        'res.partner',
        string='A cuenta de',
        help='Vacío: el dueño del pago. Úselo solo si una parte del giro es '
             'a cuenta de otro dueño.',
    )
    monto = fields.Float(string='Monto', digits=(12, 2), required=True)
    company_id = fields.Many2one(related='payment_id.company_id', store=True)
    campana_id = fields.Many2one(related='payment_id.finca_campana_id', store=True)

    @api.constrains('monto', 'payment_id')
    def _check_monto(self):
        for rec in self:
            if rec.monto <= 0:
                raise ValidationError(
                    'El monto de %s en el reparto debe ser mayor que cero.'
                    % rec.operador_id.display_name)
        # La suma de las líneas debe seguir cuadrando con el pago también
        # cuando se edita una línea sola.
        self.payment_id._check_finca_reparto()
