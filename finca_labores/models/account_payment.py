# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    # Los pagos ya se registran en contabilidad; aquí solo se marcan para
    # descontarlos del saldo de labores. Los tres campos se proponen solos y
    # se pueden corregir a mano en el pago.
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
    finca_pagador_id = fields.Many2one(
        'res.partner',
        string='Pagado por',
        compute='_compute_finca_labores',
        store=True,
        readonly=False,
        index=True,
        help='Quién hizo el pago. Se propone el contacto de la compañía del pago.',
    )
    finca_dueno_id = fields.Many2one(
        'res.partner',
        string='A cuenta de',
        compute='_compute_finca_labores',
        store=True,
        readonly=False,
        index=True,
        domain=[('es_dueno_finca', '=', True)],
        help='Dueño a cuya cuenta se descuenta el pago. Por defecto quien pagó; '
             'si el pago se hizo a nombre de una sociedad (ej. Juan Pablo paga '
             'por La Alianza), ponga aquí la sociedad: el pago queda para ella y '
             'cuenta como aporte del socio en Costo por socio.',
    )
    # Un giro que cubre a varias personas: el pago contable es a quien recibió
    # la plata y estas líneas dicen cuánto es de cada operador. Si hay líneas,
    # el libro de saldos las usa en vez del contacto del pago.
    finca_reparto_ids = fields.One2many(
        'finca.pago.reparto',
        'payment_id',
        string='Reparto entre operadores',
        copy=False,
    )
    finca_reparto_total = fields.Float(
        string='Total repartido', digits=(12, 2),
        compute='_compute_finca_reparto_total')
    finca_reparto_diferencia = fields.Float(
        string='Sin repartir', digits=(12, 2),
        compute='_compute_finca_reparto_total',
        help='Pago menos lo repartido. Debe quedar en cero.')
    finca_liquidacion_ids = fields.One2many(
        'finca.liquidacion', 'payment_id', string='Liquidaciones', readonly=True)

    @api.depends('partner_id', 'partner_id.es_operador_finca', 'date', 'company_id',
                 'reconciled_bill_ids')
    def _compute_finca_labores(self):
        Campana = self.env['finca.campana']
        duenos = self.env['res.partner'].sudo().search([('es_dueno_finca', '=', True)])
        for pay in self:
            # Asignar siempre: un compute almacenado que deja registros sin
            # valor falla. Lo ya marcado (a mano o antes) no se toca.
            pay.finca_campana_id = pay.finca_campana_id
            pay.finca_pagador_id = pay.finca_pagador_id
            pay.finca_dueno_id = pay.finca_dueno_id
            if pay.reconciled_bill_ids and not pay.finca_reparto_ids:
                # Un pago que cancela una factura de proveedor es una compra,
                # no un pago de labores, aunque el contacto también sea
                # operador (p. ej. una tornillería a nombre de una persona).
                pay.finca_campana_id = False
                continue
            if pay.finca_campana_id or not pay.partner_id.es_operador_finca or not pay.date:
                continue
            pay.finca_campana_id = Campana.search([
                ('fecha_inicio', '<=', pay.date),
                ('fecha_fin', '>=', pay.date),
            ], limit=1)
            if not pay.finca_campana_id:
                continue
            if not pay.finca_pagador_id:
                pay.finca_pagador_id = pay.company_id.partner_id
            if not pay.finca_dueno_id and pay.finca_pagador_id in duenos:
                pay.finca_dueno_id = pay.finca_pagador_id

    @api.depends('amount', 'finca_reparto_ids.monto')
    def _compute_finca_reparto_total(self):
        for pay in self:
            pay.finca_reparto_total = sum(pay.finca_reparto_ids.mapped('monto'))
            pay.finca_reparto_diferencia = (
                pay.amount - pay.finca_reparto_total if pay.finca_reparto_ids else 0.0)

    @api.constrains('amount', 'finca_reparto_ids', 'finca_campana_id')
    def _check_finca_reparto(self):
        for pay in self:
            if not pay.finca_reparto_ids:
                continue
            if not pay.finca_campana_id:
                raise ValidationError(
                    'El pago %s tiene reparto entre operadores pero no tiene '
                    'campaña de labores.' % pay.display_name)
            # Tolerancia de un peso: los giros se redondean.
            if float_compare(pay.finca_reparto_total, pay.amount, precision_digits=0) != 0:
                raise ValidationError(
                    'El reparto del pago %s suma %s y el pago es de %s. '
                    'Las líneas deben sumar el valor del pago.'
                    % (pay.display_name,
                       '{:,.0f}'.format(pay.finca_reparto_total).replace(',', '.'),
                       '{:,.0f}'.format(pay.amount).replace(',', '.')))

    # --- Cruce con liquidaciones -------------------------------------------
    # Los giros nuevos se registran como asiento desde la liquidación. Un pago
    # ya registrado (giros de antes) se cruza a mano con este botón; ya no se
    # cruza solo, para que un pago a proveedor del mismo valor no se tome por
    # un giro de labores.

    def action_finca_cruzar_liquidacion(self):
        """Botón del pago: busca la liquidación por pagar que le corresponde."""
        self.ensure_one()
        Liq = self.env['finca.liquidacion']
        candidatas = Liq.search([
            ('state', '=', 'confirmada'),
            ('company_id', '=', self.company_id.id),
            ('total', '=', self.amount),
        ])
        if len(candidatas) > 1:
            con_receptor = candidatas.filtered(lambda l: l.receptor_id == self.partner_id)
            candidatas = con_receptor if len(con_receptor) == 1 else candidatas
        if not candidatas:
            raise UserError(
                'No hay ninguna liquidación por pagar de %s en %s. Créela en Labores de '
                'Finca › Liquidaciones y se cruzará con este pago.' % (
                    '{:,.0f}'.format(self.amount).replace(',', '.'), self.company_id.name))
        if len(candidatas) > 1:
            raise UserError(
                'Hay varias liquidaciones por pagar de ese valor: %s. Abra la que corresponde, '
                'elija este pago en el campo "Pago" y use "Cruzar pago".'
                % ', '.join(candidatas.mapped('name')))
        candidatas._cruzar(self)

    @api.onchange('finca_pagador_id')
    def _onchange_finca_pagador_id(self):
        # Al corregir quién pagó, el pago pasa a su cuenta salvo que ya se haya
        # puesto a nombre de una sociedad.
        if self.finca_pagador_id and not self.finca_dueno_id.finca_socio_ids:
            self.finca_dueno_id = self.finca_pagador_id

    def action_finca_proponer_reparto(self):
        """Llena el reparto con los saldos pendientes del dueño en la campaña,
        de mayor a menor, hasta cubrir el pago. Lo que sobre va a quien recibió
        el pago si es operador; si no, al operador con más saldo, para que las
        líneas cuadren y el usuario ajuste desde ahí."""
        self.ensure_one()
        if not self.finca_campana_id or not self.finca_dueno_id:
            raise UserError('Para proponer el reparto el pago necesita campaña y dueño.')
        saldos = self.env['finca.labor.movimiento']._saldos_por_operador(
            self.finca_campana_id, self.finca_dueno_id, excluir_payment=self)
        pendientes = sorted(
            ((op, saldo) for op, saldo in saldos.items() if saldo > 0.5),
            key=lambda item: item[1], reverse=True)
        if not pendientes:
            raise UserError(
                'Ningún operador tiene saldo pendiente con %s en la campaña %s.'
                % (self.finca_dueno_id.display_name, self.finca_campana_id.name))
        restante = self.amount
        lineas = {}
        for operador, saldo in pendientes:
            if restante <= 0.5:
                break
            monto = min(saldo, restante)
            lineas[operador] = monto
            restante -= monto
        if restante > 0.5:
            destino = self.partner_id if self.partner_id.es_operador_finca else pendientes[0][0]
            lineas[destino] = lineas.get(destino, 0.0) + restante
        self.finca_reparto_ids = [(5, 0, 0)] + [
            (0, 0, {'operador_id': op.id, 'monto': monto})
            for op, monto in lineas.items() if not float_is_zero(monto, precision_digits=2)
        ]
