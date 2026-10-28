# -*- coding: utf-8 -*-

from odoo import models, fields, api


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
    # Giro de nómina no deducible: gasto 53959502 contra banco o caja. Los
    # sube el bot como "bancarizado"; cada uno tiene que quedar asignado a
    # una liquidación o un anticipo de labores (vista "Giros por asignar").
    finca_giro_nomina = fields.Boolean(
        string='Giro de nómina no deducible',
        compute='_compute_finca_giro_nomina',
        store=True,
        index=True,
    )

    @api.depends('line_ids.account_id', 'journal_id.type')
    def _compute_finca_giro_nomina(self):
        codigo = self.env['finca.liquidacion'].CODIGO_CUENTA_ANTICIPOS
        for move in self:
            cuentas = move.line_ids.account_id.with_company(move.company_id)
            move.finca_giro_nomina = (
                move.move_type == 'entry'
                and move.journal_id.type in ('bank', 'cash')
                and codigo in cuentas.mapped('code'))

    def action_finca_asignar_giro(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Asignar a labores',
            'res_model': 'finca.asignar.giro.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_move_id': self.id},
        }

    def action_finca_ver_liquidacion(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'finca.liquidacion',
            'res_id': self.finca_liquidacion_ids[:1].id,
            'view_mode': 'form',
            'target': 'current',
        }
