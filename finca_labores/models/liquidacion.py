# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare


class FincaLiquidacion(models.Model):
    """Un giro para varios operadores.

    Al elegir campaña y dueño se cargan los saldos pendientes de cada
    operador; se quita a quien no se le paga en este giro, se ajustan montos
    si hace falta y se dice quién recibe la plata (uno de ellos o un tercero
    que les entrega en efectivo). Al confirmar se crea un solo pago en
    contabilidad a quien recibe, con el reparto de cuánto es de cada uno, y
    el libro de saldos descuenta a cada operador su parte. También se puede
    vincular un pago ya registrado (p. ej. por el bot) en vez de crear uno.
    """
    _name = 'finca.liquidacion'
    _description = 'Liquidación de labores'
    _inherit = ['mail.thread']
    _order = 'fecha desc, id desc'

    name = fields.Char(
        string='Número', required=True, copy=False, readonly=True, index=True,
        default=lambda self: 'Nuevo')
    campana_id = fields.Many2one(
        'finca.campana', string='Campaña', required=True, index=True,
        default=lambda self: self.env['finca.campana']._get_campana())
    dueno_id = fields.Many2one(
        'res.partner', string='A cuenta de', required=True, index=True,
        help='Dueño cuyas labores se pagan. Los saldos se cargan de su cuenta '
             'en la campaña.')
    fecha = fields.Date(string='Fecha', required=True, default=fields.Date.context_today)
    receptor_id = fields.Many2one(
        'res.partner', string='Recibe el pago', required=True,
        help='A quién se le gira la plata. Puede ser uno de los operadores o un '
             'tercero que les entrega en efectivo. No le queda saldo: cada peso '
             'se descuenta al operador de la línea.')
    company_id = fields.Many2one(
        'res.company', string='Empresa', required=True, index=True,
        default=lambda self: self.env.company,
        help='Empresa desde la que sale el pago.')
    journal_id = fields.Many2one(
        'account.journal', string='Banco / caja',
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
        help='De dónde sale el giro. Al confirmar se crea el pago en este diario, '
             'salvo que se vincule un pago ya registrado.')
    payment_id = fields.Many2one(
        'account.payment', string='Pago', copy=False, index=True,
        domain="[('payment_type', '=', 'outbound'), ('state', 'in', ('in_process', 'paid')), "
               "('company_id', '=', company_id), ('finca_reparto_ids', '=', False)]",
        help='Déjelo vacío para que la liquidación cree el pago al confirmar. '
             'O elija un pago ya registrado en contabilidad: debe ser por el '
             'mismo valor y se le pondrá la campaña, el dueño y el reparto.')
    payment_creado = fields.Boolean(
        string='Pago creado por la liquidación', copy=False, readonly=True)
    payment_state = fields.Selection(related='payment_id.state', string='Estado del pago')
    linea_ids = fields.One2many(
        'finca.liquidacion.linea', 'liquidacion_id', string='Operadores', copy=True)
    total = fields.Float(
        string='Total a girar', digits=(12, 2), compute='_compute_total', store=True)
    state = fields.Selection([
        ('borrador', 'Borrador'),
        ('confirmada', 'Confirmada'),
        ('cancelada', 'Cancelada'),
    ], string='Estado', default='borrador', required=True, index=True, tracking=True)
    notas = fields.Text(string='Notas')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('finca.liquidacion') or 'Nuevo'
        return super().create(vals_list)

    @api.depends('linea_ids.monto')
    def _compute_total(self):
        for rec in self:
            rec.total = sum(rec.linea_ids.mapped('monto'))

    @api.depends('name', 'dueno_id', 'fecha')
    def _compute_display_name(self):
        for rec in self:
            partes = [rec.name]
            if rec.dueno_id:
                partes.append(rec.dueno_id.name)
            if rec.fecha:
                partes.append(rec.fecha.strftime('%d/%m/%Y'))
            rec.display_name = ' · '.join(partes)

    @api.onchange('campana_id', 'dueno_id')
    def _onchange_cargar_saldos(self):
        if self.state == 'borrador' and self.campana_id and self.dueno_id:
            self.linea_ids = self._lineas_desde_saldos()

    @api.onchange('company_id')
    def _onchange_company_id(self):
        if self.journal_id.company_id != self.company_id:
            self.journal_id = False
        if self.payment_id.company_id != self.company_id:
            self.payment_id = False

    @api.onchange('payment_id')
    def _onchange_payment_id(self):
        if self.payment_id:
            self.journal_id = self.payment_id.journal_id
            if not self.receptor_id:
                self.receptor_id = self.payment_id.partner_id

    def _lineas_desde_saldos(self):
        """Comandos para reemplazar las líneas por los saldos pendientes."""
        saldos = self.env['finca.labor.movimiento']._saldos_por_operador(
            self.campana_id, self.dueno_id, excluir_payment=self.payment_id)
        comandos = [(5, 0, 0)]
        for operador, saldo in sorted(saldos.items(), key=lambda s: s[0].name or ''):
            if saldo > 0.5:
                comandos.append((0, 0, {
                    'operador_id': operador.id,
                    'saldo': saldo,
                    'monto': saldo,
                }))
        return comandos

    def action_cargar_saldos(self):
        for rec in self:
            if rec.state != 'borrador':
                raise UserError('Solo se recargan los saldos de una liquidación en borrador.')
            rec.linea_ids = rec._lineas_desde_saldos()

    def _validar(self):
        self.ensure_one()
        if not self.linea_ids:
            raise UserError('La liquidación %s no tiene operadores.' % self.name)
        if any(l.monto <= 0 for l in self.linea_ids):
            raise UserError('Todas las líneas deben tener un monto mayor que cero.')
        repetidos = self.linea_ids.mapped('operador_id').filtered(
            lambda op: len(self.linea_ids.filtered(lambda l: l.operador_id == op)) > 1)
        if repetidos:
            raise UserError('Hay operadores repetidos: %s.' % ', '.join(repetidos.mapped('name')))
        if self.payment_id:
            if float_compare(self.payment_id.amount, self.total, precision_digits=0) != 0:
                raise UserError(
                    'El pago %s es de %s y la liquidación suma %s. Ajuste las líneas '
                    'o elija otro pago.' % (
                        self.payment_id.display_name,
                        '{:,.0f}'.format(self.payment_id.amount).replace(',', '.'),
                        '{:,.0f}'.format(self.total).replace(',', '.')))
            if self.payment_id.finca_reparto_ids:
                raise UserError('El pago %s ya tiene un reparto.' % self.payment_id.display_name)
        elif not self.journal_id:
            raise UserError('Indique el banco o caja del giro, o vincule un pago ya registrado.')

    def _reparto_vals(self):
        return [(0, 0, {'operador_id': l.operador_id.id, 'monto': l.monto}) for l in self.linea_ids]

    def _crear_pago(self):
        self.ensure_one()
        Payment = self.env['account.payment'].with_company(self.company_id)
        pago = Payment.create({
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': self.receptor_id.id,
            'amount': self.total,
            'date': self.fecha,
            'journal_id': self.journal_id.id,
            'memo': '%s · Labores %s · %s' % (self.name, self.campana_id.name, self.dueno_id.name),
            'finca_campana_id': self.campana_id.id,
            'finca_pagador_id': self.company_id.partner_id.id,
            'finca_dueno_id': self.dueno_id.id,
            'finca_reparto_ids': self._reparto_vals(),
        })
        pago.action_post()
        return pago

    def action_confirmar(self):
        for rec in self.filtered(lambda r: r.state == 'borrador'):
            rec._validar()
            if rec.payment_id:
                rec.payment_id.write({
                    'finca_campana_id': rec.campana_id.id,
                    'finca_dueno_id': rec.dueno_id.id,
                    'finca_pagador_id': rec.payment_id.finca_pagador_id.id
                    or rec.company_id.partner_id.id,
                    'finca_reparto_ids': rec._reparto_vals(),
                })
                rec.payment_creado = False
            else:
                rec.payment_id = rec._crear_pago()
                rec.payment_creado = True
            rec.linea_ids.operador_id._marcar_operador_finca()
            rec.state = 'confirmada'
            rec.message_post(body='Pago %s a %s por %s.' % (
                rec.payment_id.display_name, rec.receptor_id.name,
                '{:,.0f}'.format(rec.total).replace(',', '.')))

    def action_cancelar(self):
        for rec in self:
            pago = rec.payment_id
            if rec.state == 'confirmada' and pago:
                pago.finca_reparto_ids.unlink()
                if rec.payment_creado:
                    if pago.reconciled_bill_ids or pago.reconciled_invoice_ids or pago.is_matched:
                        raise UserError(
                            'El pago %s ya está conciliado en contabilidad. Rómpale la '
                            'conciliación antes de cancelar la liquidación.' % pago.display_name)
                    pago.action_cancel()
                    pago.finca_campana_id = False
                    rec.message_post(body='Pago %s cancelado.' % pago.display_name)
                else:
                    # El pago venía de contabilidad: se deja, solo se le quita
                    # la liquidación. Vuelve a ser un pago a su contacto.
                    rec.message_post(body='Se quitó el reparto del pago %s.' % pago.display_name)
                    rec.payment_id = False
            rec.state = 'cancelada'

    def action_borrador(self):
        for rec in self:
            if rec.state != 'cancelada':
                raise UserError('Solo una liquidación cancelada vuelve a borrador.')
            if rec.payment_creado and rec.payment_id and rec.payment_id.state == 'canceled':
                rec.payment_id = False
                rec.payment_creado = False
            rec.state = 'borrador'

    def action_ver_pago(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'res_id': self.payment_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def unlink(self):
        if any(rec.state == 'confirmada' for rec in self):
            raise UserError('No se puede borrar una liquidación confirmada. Cancélela primero.')
        return super().unlink()


class FincaLiquidacionLinea(models.Model):
    _name = 'finca.liquidacion.linea'
    _description = 'Operador en una liquidación'
    _order = 'liquidacion_id, id'

    liquidacion_id = fields.Many2one(
        'finca.liquidacion', required=True, ondelete='cascade', index=True)
    operador_id = fields.Many2one('res.partner', string='Operador', required=True)
    saldo = fields.Float(
        string='Saldo pendiente', digits=(12, 2), readonly=True,
        help='Lo que se le debía al cargar la liquidación.')
    monto = fields.Float(string='A pagar', digits=(12, 2), required=True)
    company_id = fields.Many2one(related='liquidacion_id.company_id', store=True)

    @api.constrains('monto')
    def _check_monto(self):
        for rec in self:
            if rec.monto < 0:
                raise ValidationError('El monto no puede ser negativo.')
