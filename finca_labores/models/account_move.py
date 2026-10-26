# -*- coding: utf-8 -*-

from odoo import models, fields


class AccountMove(models.Model):
    _inherit = 'account.move'

    # Los anticipos de labores se contabilizan como gasto de nómina no
    # deducible (53959502) con un asiento contra el banco, no como un pago que
    # espera factura. Con campaña, cada línea de gasto del asiento se descuenta
    # al operador que tenga como contacto; las líneas de banco no cuentan.
    finca_campana_id = fields.Many2one(
        'finca.campana',
        string='Campaña de labores',
        index=True,
        copy=False,
        help='Si tiene campaña, las líneas de gasto del asiento se descuentan '
             'del saldo de labores del operador de cada línea.',
    )
    finca_pagador_id = fields.Many2one(
        'res.partner',
        string='Pagado por',
        copy=False,
        help='Quién hizo el giro. Se propone el contacto de la compañía.',
    )
    finca_dueno_id = fields.Many2one(
        'res.partner',
        string='A cuenta de',
        index=True,
        copy=False,
        domain=[('es_dueno_finca', '=', True)],
        help='Dueño a cuya cuenta se descuenta el giro.',
    )
    finca_liquidacion_ids = fields.One2many(
        'finca.liquidacion', 'move_id', string='Liquidaciones', readonly=True)
