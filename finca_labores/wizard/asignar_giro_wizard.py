# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError
from odoo.tools import float_compare

from ..models.contrato import _fmt


class FincaAsignarGiroWizard(models.TransientModel):
    """Asigna un giro ya subido (asiento 53959502 contra el banco) a labores.

    Sirve igual para un anticipo (el operador aún no tiene trabajos y queda
    con saldo negativo) que para pagar lo que se le debe: arma la liquidación
    con las líneas que se digiten, la confirma y le cruza el asiento.
    """
    _name = 'finca.asignar.giro.wizard'
    _description = 'Asignar giro a labores'

    move_id = fields.Many2one('account.move', string='Asiento', required=True, readonly=True)
    company_id = fields.Many2one(related='move_id.company_id')
    total = fields.Float(string='Valor del giro', digits=(12, 2), readonly=True)
    referencia = fields.Char(related='move_id.ref', string='Detalle del giro')
    campana_id = fields.Many2one(
        'finca.campana', string='Campaña', required=True,
        default=lambda self: self.env['finca.campana']._get_campana())
    dueno_id = fields.Many2one(
        'res.partner', string='A cuenta de', required=True,
        domain=[('es_dueno_finca', '=', True)],
        help='Dueño a cuya cuenta va el giro.')
    receptor_id = fields.Many2one(
        'res.partner', string='Recibió la plata',
        help='A quién se le giró: el operador o un tercero que le entrega. '
             'Vacío con un solo operador: el operador.')
    linea_ids = fields.One2many(
        'finca.asignar.giro.wizard.linea', 'wizard_id', string='Operadores')
    asignado = fields.Float(
        string='Asignado', digits=(12, 2), compute='_compute_asignado')

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        move = self.env['account.move'].browse(vals.get('move_id'))
        if move:
            if move.finca_campana_id:
                raise UserError('El asiento %s ya está asignado a labores.' % move.name)
            if not move.finca_giro_nomina or move.state != 'posted':
                raise UserError(
                    'Solo se asignan asientos publicados de nómina no deducible (53959502) '
                    'contra banco o caja.')
            total = sum(move.line_ids.filtered(
                lambda l: l.account_id.account_type in ('asset_cash', 'liability_credit_card')
            ).mapped('credit'))
            vals['total'] = total
            dueno = move.company_id.partner_id
            if dueno.es_dueno_finca:
                vals['dueno_id'] = dueno.id
            vals['linea_ids'] = [(0, 0, {'monto': total})]
        return vals

    @api.depends('linea_ids.monto')
    def _compute_asignado(self):
        for wiz in self:
            wiz.asignado = sum(wiz.linea_ids.mapped('monto'))

    @api.onchange('campana_id', 'dueno_id')
    def _onchange_saldos(self):
        # Muestra el saldo de cada operador con el dueño, para no girar de más
        # sin darse cuenta.
        if not (self.campana_id and self.dueno_id):
            return
        saldos = self.env['finca.labor.movimiento']._saldos_por_operador(
            self.campana_id, self.dueno_id)
        for linea in self.linea_ids:
            linea.saldo = saldos.get(linea.operador_id, 0.0)

    def action_asignar(self):
        self.ensure_one()
        lineas = self.linea_ids.filtered(lambda l: l.operador_id and l.monto)
        if not lineas:
            raise UserError('Ponga al menos un operador con su monto.')
        if float_compare(sum(lineas.mapped('monto')), self.total, precision_digits=0) != 0:
            raise UserError('Las líneas suman %s y el giro es de %s.' % (
                _fmt(sum(lineas.mapped('monto'))), _fmt(self.total)))
        saldos = self.env['finca.labor.movimiento']._saldos_por_operador(
            self.campana_id, self.dueno_id)
        liq = self.env['finca.liquidacion'].with_company(self.company_id).create({
            'campana_id': self.campana_id.id,
            'dueno_id': self.dueno_id.id,
            'company_id': self.company_id.id,
            'fecha': self.move_id.date,
            'receptor_id': self.receptor_id.id,
            'notas': self.move_id.ref,
            'linea_ids': [(0, 0, {
                'operador_id': l.operador_id.id,
                'saldo': saldos.get(l.operador_id, 0.0),
                'monto': l.monto,
            }) for l in lineas],
        })
        liq.action_confirmar()
        liq._cruzar_asiento(self.move_id)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'finca.liquidacion',
            'res_id': liq.id,
            'view_mode': 'form',
            'target': 'current',
        }


class FincaAsignarGiroWizardLinea(models.TransientModel):
    _name = 'finca.asignar.giro.wizard.linea'
    _description = 'Operador de un giro por asignar'

    wizard_id = fields.Many2one('finca.asignar.giro.wizard', required=True, ondelete='cascade')
    operador_id = fields.Many2one(
        'res.partner', string='Operador',
        context={'default_es_operador_finca': True, 'default_is_company': False})
    saldo = fields.Float(
        string='Se le debe', digits=(12, 2), readonly=True,
        help='Saldo con el dueño antes de este giro. Cero o negativo: el giro queda como anticipo.')
    monto = fields.Float(string='Monto', digits=(12, 2))

    @api.onchange('operador_id')
    def _onchange_operador_id(self):
        wiz = self.wizard_id
        if self.operador_id and wiz.campana_id and wiz.dueno_id:
            saldos = self.env['finca.labor.movimiento']._saldos_por_operador(
                wiz.campana_id, wiz.dueno_id)
            self.saldo = saldos.get(self.operador_id, 0.0)
