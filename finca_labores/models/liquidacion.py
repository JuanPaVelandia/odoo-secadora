# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare

from .contrato import _fmt, _fmt_cantidad


class FincaLiquidacion(models.Model):
    """Un giro para varios operadores.

    1. Liquidación: al elegir campaña y dueño se cargan los saldos pendientes
       de cada operador; se quita a quien no se le paga en este giro y se
       confirma. Queda "por pagar".
    2. Giro: se elige el banco y "Registrar giro" crea el asiento: una línea
       de gasto 53959502 (nómina no deducible) por operador contra el banco.
       No es un pago a proveedor: no queda esperando factura. El libro de
       saldos descuenta a cada operador su línea; quien recibió la plata (un
       tercero que les entrega en efectivo) no queda con saldo.

    Los giros de antes se registraban como pagos (account.payment) con
    reparto; esos se siguen leyendo y se pueden cruzar a mano con "Cruzar
    pago".
    """
    _name = 'finca.liquidacion'
    _description = 'Liquidación de labores'
    _inherit = ['mail.thread']
    _order = 'fecha desc, id desc'

    name = fields.Char(
        string='Número', required=True, copy=False, readonly=True, index=True,
        default=lambda self: 'Nuevo')
    # Periodo interno de los saldos: sale de la fecha y no se muestra.
    campana_id = fields.Many2one(
        'finca.campana', string='Campaña', required=True, index=True,
        compute='_compute_campana_id', store=True, readonly=False)
    dueno_id = fields.Many2one(
        'res.partner', string='A cuenta de', required=True, index=True,
        domain=[('es_dueno_finca', '=', True)],
        help='Dueño cuyas labores se pagan. Se cargan los saldos pendientes '
             'de sus operadores.')
    fecha = fields.Date(string='Fecha', required=True, default=fields.Date.context_today)
    receptor_id = fields.Many2one(
        'res.partner', string='Recibe el pago',
        help='A quién se le gira la plata: uno de los operadores o un tercero '
             'que les entrega en efectivo. No le queda saldo, cada peso se '
             'descuenta al operador de su línea. Si se deja vacío se toma del '
             'pago al cruzarlo.')
    company_id = fields.Many2one(
        'res.company', string='Empresa', required=True, index=True,
        default=lambda self: self.env.company,
        help='Empresa desde la que sale el pago.')
    payment_id = fields.Many2one(
        'account.payment', string='Pago', copy=False, index=True,
        domain="[('payment_type', '=', 'outbound'), ('state', 'in', ('in_process', 'paid')), "
               "('company_id', '=', company_id), ('finca_reparto_ids', '=', False), "
               "('finca_liquidacion_ids', '=', False)]",
        help='El pago registrado en contabilidad para este giro. Se cruza solo '
             'cuando hay uno por el mismo valor; si no, elíjalo aquí y use '
             '"Cruzar pago".')
    payment_state = fields.Selection(related='payment_id.state', string='Estado del pago')
    journal_id = fields.Many2one(
        'account.journal', string='Sale de', copy=False,
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
        help='Banco o caja desde el que se hace el giro.')
    fecha_giro = fields.Date(
        string='Fecha del giro', copy=False, default=fields.Date.context_today)
    move_id = fields.Many2one(
        'account.move', string='Asiento', copy=False, index=True,
        domain="[('move_type', '=', 'entry'), ('state', '=', 'posted'), "
               "('company_id', '=', company_id), ('finca_campana_id', '=', False), "
               "('journal_id.type', 'in', ('bank', 'cash'))]",
        help='Asiento del giro: gasto de nómina no deducible por operador contra el banco. '
             'Si el giro ya se subió (p. ej. un bancarizado del bot), elíjalo aquí y use '
             '"Cruzar asiento".')
    move_cruzado = fields.Boolean(
        copy=False, readonly=True,
        help='El asiento ya existía y se cruzó; al cancelar la liquidación no se anula.')
    move_state = fields.Selection(related='move_id.state', string='Estado del asiento')
    linea_ids = fields.One2many(
        'finca.liquidacion.linea', 'liquidacion_id', string='Operadores', copy=True)
    jornal_ids = fields.One2many(
        'finca.jornal', 'liquidacion_id', string='Jornales', readonly=True,
        help='Jornales con los que se armó (desde la lista de jornales). Vacío '
             'si se cargó por saldos.')
    maquinaria_ids = fields.One2many(
        'finca.maquinaria.trabajo', 'liquidacion_id', string='Trabajos de maquinaria',
        readonly=True,
        help='Trabajos de maquinaria y drones que se pagan con esta liquidación.')
    total = fields.Float(
        string='Total a girar', digits=(12, 2), compute='_compute_total', store=True)
    state = fields.Selection([
        ('borrador', 'Borrador'),
        ('confirmada', 'Por pagar'),
        ('pagada', 'Pagada'),
        ('cancelada', 'Cancelada'),
    ], string='Estado', default='borrador', required=True, index=True, tracking=True)
    notas = fields.Text(string='Notas')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('finca.liquidacion') or 'Nuevo'
        return super().create(vals_list)

    @api.depends('fecha')
    def _compute_campana_id(self):
        Campana = self.env['finca.campana']
        for rec in self:
            if rec.state in (False, 'borrador'):
                rec.campana_id = Campana._get_campana(rec.fecha)

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
        if self.payment_id.company_id != self.company_id:
            self.payment_id = False
        if self.journal_id.company_id != self.company_id:
            self.journal_id = False

    # --- Paso 1: liquidar --------------------------------------------------

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

    def _validar_lineas(self):
        self.ensure_one()
        if not self.linea_ids:
            raise UserError('La liquidación %s no tiene operadores.' % self.name)
        if any(l.monto <= 0 for l in self.linea_ids):
            raise UserError('Todas las líneas deben tener un monto mayor que cero.')
        repetidos = self.linea_ids.mapped('operador_id').filtered(
            lambda op: len(self.linea_ids.filtered(lambda l: l.operador_id == op)) > 1)
        if repetidos:
            raise UserError('Hay operadores repetidos: %s.' % ', '.join(repetidos.mapped('name')))

    def action_confirmar(self):
        """Deja la liquidación por pagar. Si se eligió un pago ya registrado
        (giro de antes, como account.payment), se cruza de una vez."""
        for rec in self.filtered(lambda r: r.state == 'borrador'):
            rec._validar_lineas()
            rec.state = 'confirmada'
            if rec.payment_id:
                rec._cruzar(rec.payment_id)

    # --- Paso 2: registrar el giro -------------------------------------------

    CODIGO_CUENTA_ANTICIPOS = '53959502'

    def _cuenta_anticipos(self):
        self.ensure_one()
        cuenta = self.env['account.account'].with_company(self.company_id).search([
            ('code', '=', self.CODIGO_CUENTA_ANTICIPOS),
            ('company_ids', 'parent_of', self.company_id.id),
        ], limit=1)
        if not cuenta:
            raise UserError(
                'La empresa %s no tiene la cuenta %s (Nómina no deducible – anticipos '
                'a contratistas).' % (self.company_id.name, self.CODIGO_CUENTA_ANTICIPOS))
        return cuenta

    def _distribucion_maquinaria(self, operador):
        """Analítica del gasto de un operador en el giro.

        Los pagos a pilotos y ayudantes son costo de la unidad de negocio
        Maquinaria de quien paga. La línea del giro es un monto por operador,
        no por trabajo: si también hizo otras labores para este dueño, a
        Maquinaria solo va la parte de sus trabajos de la campaña que lo es.
        """
        self.ensure_one()
        cuenta = self.env['account.analytic.account'].sudo().search([
            ('name', '=ilike', 'maquinaria'),
            ('plan_id.name', '=ilike', 'unidad de negocio'),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        if not cuenta:
            return False
        Movimiento = self.env['finca.labor.movimiento'].sudo()
        self.env.flush_all()
        por_tipo = dict(Movimiento._read_group(
            [('campana_id', '=', self.campana_id.id),
             ('dueno_id', '=', self.dueno_id.id),
             ('operador_id', '=', operador.id),
             ('tipo', '!=', 'pago')],
            ['tipo'], ['trabajos:sum']))
        total = sum(por_tipo.values())
        maquinaria = por_tipo.get('maquinaria', 0.0)
        if not total or not maquinaria:
            return False
        return {str(cuenta.id): round(maquinaria * 100.0 / total, 2)}

    def _distribucion_cosecha(self, operador):
        """Cosecha del gasto de un operador en el giro, en porcentaje.

        Sale de los trabajos que paga esta liquidación (jornales y
        maquinaria). Si se armó por saldos y no tiene trabajos amarrados, de
        todo lo trabajado por el operador para el dueño en el periodo. Lo que
        no tiene cosecha queda sin ella (la distribución suma menos de 100).
        """
        self.ensure_one()
        por_cosecha = {}
        trabajos = (self.jornal_ids.filtered(lambda j: j.operador_id == operador),
                    self.maquinaria_ids.filtered(lambda m: m.operador_id == operador))
        if any(trabajos):
            total = 0.0
            for j in trabajos[0]:
                total += j.total
                if j.cosecha_id:
                    por_cosecha[j.cosecha_id.id] = por_cosecha.get(j.cosecha_id.id, 0.0) + j.total
            for m in trabajos[1]:
                total += m.valor
                if m.cosecha_id:
                    por_cosecha[m.cosecha_id.id] = por_cosecha.get(m.cosecha_id.id, 0.0) + m.valor
        else:
            self.env.flush_all()
            filas = self.env['finca.labor.movimiento'].sudo()._read_group(
                [('campana_id', '=', self.campana_id.id),
                 ('dueno_id', '=', self.dueno_id.id),
                 ('operador_id', '=', operador.id),
                 ('tipo', '!=', 'pago')],
                ['cosecha_id'], ['trabajos:sum'])
            total = sum(v for _c, v in filas)
            por_cosecha = {c.id: v for c, v in filas if c}
        if not total or not por_cosecha:
            return {}
        dist = {str(c): round(v * 100.0 / total, 2) for c, v in por_cosecha.items()}
        # Que lo cubierto sume exacto (100 si todo tiene cosecha).
        cubierto = round(sum(por_cosecha.values()) * 100.0 / total, 2)
        ultima = max(dist, key=dist.get)
        dist[ultima] = round(dist[ultima] + cubierto - sum(dist.values()), 2)
        return dist

    def _distribucion_giro(self, operador):
        dist = dict(self._distribucion_maquinaria(operador) or {})
        dist.update(self._distribucion_cosecha(operador))
        return dist or False

    def action_aplicar_cosecha(self):
        """Vuelve a poner la cosecha en las líneas de gasto del asiento del
        giro (p. ej. si se corrigió la cosecha de un jornal después de pagar).
        Solo toca la Cosecha; las demás analíticas de la línea se quedan."""
        plan = self.env['finca.campana']._plan_cosecha()
        cosechas = self.env['account.analytic.account'].sudo().search([('plan_id', '=', plan.id)])
        ids_cosecha = {str(c) for c in cosechas.ids}
        for rec in self:
            if not rec.move_id:
                raise UserError('La liquidación %s no tiene asiento del giro.' % rec.name)
            banco = rec._lineas_banco(rec.move_id)
            for linea in rec.move_id.line_ids - banco:
                if not linea.partner_id:
                    continue
                dist = {k: v for k, v in (linea.analytic_distribution or {}).items()
                        if not set(k.split(',')) & ids_cosecha}
                dist.update(rec._distribucion_cosecha(linea.partner_id))
                linea.analytic_distribution = dist or False
            rec.message_post(body='Cosecha aplicada al asiento %s.' % rec.move_id.name)

    def action_registrar_giro(self):
        """Crea y publica el asiento del giro: una línea de gasto por operador
        (con el operador como contacto) contra la cuenta del banco."""
        for rec in self:
            if rec.state != 'confirmada':
                raise UserError('La liquidación %s no está por pagar.' % rec.name)
            if rec.payment_id or rec.move_id:
                raise UserError(
                    'La liquidación %s ya tiene un giro elegido. Si es un asiento ya subido, '
                    'use "Cruzar asiento".' % rec.name)
            if not rec.journal_id:
                raise UserError('Elija en "Sale de" el banco o caja del giro.')
            if not rec.journal_id.default_account_id:
                raise UserError('El diario %s no tiene cuenta.' % rec.journal_id.name)
            rec._validar_lineas()
            cuenta = rec._cuenta_anticipos()
            receptor = rec.receptor_id
            if not receptor and len(rec.linea_ids) == 1:
                receptor = rec.linea_ids.operador_id
            etiqueta = 'Anticipo labores %s · %s' % (rec.name, rec.dueno_id.name)
            lineas = [(0, 0, {
                'account_id': cuenta.id,
                'partner_id': l.operador_id.id,
                'name': etiqueta,
                'debit': l.monto,
                'credit': 0.0,
                'analytic_distribution': rec._distribucion_giro(l.operador_id),
            }) for l in rec.linea_ids]
            lineas.append((0, 0, {
                'account_id': rec.journal_id.default_account_id.id,
                'partner_id': receptor.id,
                'name': etiqueta + (' · Girado a %s' % receptor.name if receptor else ''),
                'debit': 0.0,
                'credit': rec.total,
            }))
            move = self.env['account.move'].with_company(rec.company_id).create({
                'move_type': 'entry',
                'journal_id': rec.journal_id.id,
                'date': rec.fecha_giro or fields.Date.context_today(rec),
                'ref': '%s · %s' % (rec.name, rec.dueno_id.name),
                'finca_campana_id': rec.campana_id.id,
                'finca_dueno_id': rec.dueno_id.id,
                'finca_pagador_id': rec.company_id.partner_id.id,
                'line_ids': lineas,
            })
            move.action_post()
            rec.write({
                'move_id': move.id,
                'receptor_id': receptor.id,
                'state': 'pagada',
            })
            rec.linea_ids.operador_id._marcar_operador_finca()
            rec.message_post(body='Giro registrado: asiento %s desde %s por %s.' % (
                move.name, rec.journal_id.name,
                '{:,.0f}'.format(rec.total).replace(',', '.')))

    # --- Giro ya subido como asiento: cruzarlo ------------------------------

    def _lineas_banco(self, move):
        return move.line_ids.filtered(
            lambda l: l.account_id.account_type in ('asset_cash', 'liability_credit_card'))

    def _buscar_asiento(self):
        """El asiento bancarizado que corresponde a esta liquidación, solo si
        es uno: publicado, de la empresa, sin campaña, con gasto 53959502 y
        el mismo valor."""
        self.ensure_one()
        cuenta = self._cuenta_anticipos()
        moves = self.env['account.move'].search([
            ('move_type', '=', 'entry'), ('state', '=', 'posted'),
            ('company_id', '=', self.company_id.id), ('finca_campana_id', '=', False),
            ('journal_id.type', 'in', ('bank', 'cash')),
            ('line_ids.account_id', '=', cuenta.id),
            ('amount_total', '=', self.total),
        ], limit=2)
        return moves if len(moves) == 1 else self.env['account.move']

    def _cruzar_asiento(self, move):
        """Toma un asiento ya publicado (gasto 53959502 contra el banco) como
        el giro: el gasto se reparte en una línea por operador y la línea del
        banco queda a nombre de quien recibió."""
        self.ensure_one()
        if self.state != 'confirmada':
            raise UserError('La liquidación %s no está por pagar.' % self.name)
        if self.payment_id:
            raise UserError('La liquidación %s ya está cruzada con un pago.' % self.name)
        if move.company_id != self.company_id:
            raise UserError('El asiento %s es de otra empresa.' % move.name)
        if move.finca_campana_id or (move.finca_liquidacion_ids - self):
            raise UserError('El asiento %s ya es de labores.' % move.name)
        banco = self._lineas_banco(move)
        resto = move.line_ids - banco
        cuenta = self._cuenta_anticipos()
        if not banco or resto.account_id != cuenta:
            raise UserError(
                'El asiento %s debe ser gasto %s contra un banco o caja.'
                % (move.name, self.CODIGO_CUENTA_ANTICIPOS))
        girado = -sum(banco.mapped('balance'))
        if float_compare(girado, self.total, precision_digits=0) != 0:
            raise UserError('El asiento %s gira %s y la liquidación suma %s.' % (
                move.name, _fmt(girado), _fmt(self.total)))
        self._validar_lineas()
        receptor = self.receptor_id
        if not receptor and len(self.linea_ids) == 1:
            receptor = self.linea_ids.operador_id
        etiqueta = resto[:1].name or 'Anticipo labores %s' % self.name
        move.button_draft()
        move.write({
            'finca_campana_id': self.campana_id.id,
            'finca_dueno_id': self.dueno_id.id,
            'finca_pagador_id': self.company_id.partner_id.id,
            'line_ids': [(2, l.id) for l in resto] + [(0, 0, {
                'account_id': cuenta.id,
                'partner_id': l.operador_id.id,
                'name': etiqueta,
                'debit': l.monto,
                'credit': 0.0,
                'analytic_distribution': self._distribucion_giro(l.operador_id),
            }) for l in self.linea_ids] + [
                (1, l.id, {'partner_id': receptor.id}) for l in banco if receptor],
        })
        move.action_post()
        self.write({
            'move_id': move.id,
            'move_cruzado': True,
            'journal_id': move.journal_id.id,
            'fecha_giro': move.date,
            'receptor_id': receptor.id,
            'state': 'pagada',
        })
        self.linea_ids.operador_id._marcar_operador_finca()
        self.message_post(body='Cruzada con el asiento %s de %s por %s.' % (
            move.name, move.journal_id.name, _fmt(girado)))

    def action_cruzar_asiento(self):
        for rec in self:
            move = rec.move_id or rec._buscar_asiento()
            if not move:
                raise UserError(
                    'No hay un asiento bancarizado por %s sin cruzar en %s. Elíjalo en el '
                    'campo "Asiento".' % (_fmt(rec.total), rec.company_id.name))
            rec._cruzar_asiento(move)

    # --- Giros de antes: cruzar con un pago ----------------------------------

    def _dominio_pago(self):
        self.ensure_one()
        dominio = [
            ('payment_type', '=', 'outbound'),
            ('state', 'in', ('in_process', 'paid')),
            ('company_id', '=', self.company_id.id),
            ('amount', '=', self.total),
            ('finca_reparto_ids', '=', False),
            ('finca_liquidacion_ids', '=', False),
        ]
        if self.receptor_id:
            dominio.append(('partner_id', '=', self.receptor_id.id))
        return dominio

    def _buscar_pago(self):
        """El pago que corresponde a esta liquidación, solo si es uno solo."""
        pagos = self.env['account.payment'].search(self._dominio_pago(), limit=2)
        return pagos if len(pagos) == 1 else self.env['account.payment']

    def _cruzar(self, pago):
        self.ensure_one()
        if self.state != 'confirmada':
            raise UserError('La liquidación %s no está por pagar.' % self.name)
        if float_compare(pago.amount, self.total, precision_digits=0) != 0:
            raise UserError(
                'El pago %s es de %s y la liquidación suma %s.' % (
                    pago.display_name,
                    '{:,.0f}'.format(pago.amount).replace(',', '.'),
                    '{:,.0f}'.format(self.total).replace(',', '.')))
        if pago.finca_reparto_ids or (pago.finca_liquidacion_ids - self):
            raise UserError('El pago %s ya está cruzado con otra liquidación.' % pago.display_name)
        if pago.company_id != self.company_id:
            raise UserError('El pago %s es de otra empresa.' % pago.display_name)
        if self.move_id:
            raise UserError('La liquidación %s ya tiene el asiento %s.' % (self.name, self.move_id.name))
        pago.write({
            'finca_campana_id': self.campana_id.id,
            'finca_dueno_id': self.dueno_id.id,
            'finca_pagador_id': pago.finca_pagador_id.id or self.company_id.partner_id.id,
            'finca_reparto_ids': [(5, 0, 0)] + [
                (0, 0, {'operador_id': l.operador_id.id, 'monto': l.monto})
                for l in self.linea_ids],
        })
        self.write({
            'payment_id': pago.id,
            'receptor_id': self.receptor_id.id or pago.partner_id.id,
            'state': 'pagada',
        })
        self.linea_ids.operador_id._marcar_operador_finca()
        self.message_post(body='Cruzada con el pago %s a %s por %s.' % (
            pago.display_name, pago.partner_id.name,
            '{:,.0f}'.format(pago.amount).replace(',', '.')))

    def action_cruzar_pago(self):
        for rec in self:
            if rec.state != 'confirmada':
                raise UserError('La liquidación %s no está por pagar.' % rec.name)
            pago = rec.payment_id or rec._buscar_pago()
            if not pago:
                raise UserError(
                    'No hay un pago por %s %s. Regístrelo en contabilidad, o elíjalo en '
                    'el campo "Pago" si ya existe.' % (
                        '{:,.0f}'.format(rec.total).replace(',', '.'),
                        'a %s' % rec.receptor_id.name if rec.receptor_id else ''))
            rec._cruzar(pago)

    # --- Deshacer ------------------------------------------------------------

    def action_cancelar(self):
        for rec in self:
            if rec.state == 'pagada' and rec.move_id and rec.move_cruzado:
                # El asiento ya existía: sigue en contabilidad, deja de ser de labores.
                rec.move_id.finca_campana_id = False
                rec.message_post(body='Se separó el asiento %s.' % rec.move_id.name)
                rec.write({'move_id': False, 'move_cruzado': False})
            elif rec.state == 'pagada' and rec.move_id:
                # El asiento es de la liquidación: se cancela con ella.
                move = rec.move_id
                if move.state == 'posted':
                    move.button_draft()
                move.button_cancel()
                rec.message_post(body='Se canceló el asiento %s.' % move.name)
                rec.move_id = False
            if rec.state == 'pagada' and rec.payment_id:
                # El pago sigue en contabilidad; solo deja de ser de labores.
                rec.payment_id.finca_reparto_ids.unlink()
                rec.payment_id.finca_campana_id = False
                rec.message_post(body='Se quitó el reparto del pago %s.' % rec.payment_id.display_name)
                rec.payment_id = False
            rec.jornal_ids.write({'liquidacion_id': False})
            rec.maquinaria_ids.write({'liquidacion_id': False})
            rec.state = 'cancelada'

    def action_borrador(self):
        for rec in self:
            if rec.state == 'pagada':
                raise UserError('Cancele primero la liquidación %s para separarla del pago.' % rec.name)
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

    # --- Detalle para imprimir ----------------------------------------------

    def _detalle_nomina(self):
        """Por cada línea, solo lo que se paga en esta liquidación.

        [{'operador', 'trabajos': [filas], 'total_trabajos', 'monto',
          'ajuste'}]. Las filas salen de los jornales y trabajos de maquinaria
        con los que se armó; si se cargó por saldos no hay filas y queda solo
        el monto. 'ajuste' es lo que el monto difiere de la suma de las filas
        (anticipos descontados o cambios a mano)."""
        self.ensure_one()
        unidades = dict(self.env['finca.labor']._fields['unidad'].selection)
        detalle = []
        for linea in self.linea_ids.sorted(lambda l: l.operador_id.name or ''):
            op = linea.operador_id
            filas = []
            for j in self.jornal_ids.filtered(lambda r: r.operador_id == op).sorted(
                    lambda r: (r.fecha_desde, r.id)):
                filas.append({
                    'desde': j.fecha_desde, 'hasta': j.fecha_hasta, 'referencia': j.name,
                    'finca': j.finca_id.name,
                    'concepto': ' · '.join(filter(None, [j.labor_id.name, j.descripcion])),
                    'cantidad': j.cantidad, 'unidad': unidades.get(j.unidad, ''),
                    'tarifa': j.valor_unitario, 'valor': j.total,
                })
            for t in self.maquinaria_ids.filtered(lambda r: r.operador_id == op).sorted(
                    lambda r: (r.fecha, r.id)):
                filas.append({
                    'desde': t.fecha, 'hasta': t.fecha, 'referencia': t.name,
                    'finca': t.lugar_id.name or '',
                    'concepto': ' · '.join(filter(None, [
                        t.labor_id.name, t.equipment_id.name, t.descripcion])),
                    'cantidad': t.cantidad, 'unidad': unidades.get(t.unidad, ''),
                    'tarifa': t.tarifa, 'valor': t.valor,
                })
            total_trabajos = sum(f['valor'] for f in filas)
            detalle.append({
                'operador': op, 'trabajos': filas, 'total_trabajos': total_trabajos,
                'monto': linea.monto,
                'ajuste': linea.monto - total_trabajos if filas else 0.0,
            })
        return detalle

    def _fmt(self, valor):
        return _fmt(valor)

    def _fmt_cantidad(self, valor):
        return _fmt_cantidad(valor)

    def action_imprimir_detalle(self):
        return self.env.ref('finca_labores.action_report_liquidacion').report_action(self)

    def action_ver_asiento(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def unlink(self):
        if any(rec.state == 'pagada' for rec in self):
            raise UserError('No se puede borrar una liquidación pagada. Cancélela primero.')
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
