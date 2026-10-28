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
    campana_id = fields.Many2one(
        'finca.campana', string='Campaña', required=True, index=True,
        default=lambda self: self.env['finca.campana']._get_campana())
    dueno_id = fields.Many2one(
        'res.partner', string='A cuenta de', required=True, index=True,
        domain=[('es_dueno_finca', '=', True)],
        help='Dueño cuyas labores se pagan. Los saldos se cargan de su cuenta '
             'en la campaña.')
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
            etiqueta = 'Anticipo labores %s · %s' % (rec.name, rec.campana_id.name)
            lineas = [(0, 0, {
                'account_id': cuenta.id,
                'partner_id': l.operador_id.id,
                'name': etiqueta,
                'debit': l.monto,
                'credit': 0.0,
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
        """Por cada línea: de dónde sale lo que se le paga al operador.

        [{'operador', 'trabajos': [filas], 'total_trabajos', 'pagos': [movs],
          'total_pagos', 'saldo', 'monto', 'queda'}]. Los trabajos se abren
        al detalle (tramo, jornal, trabajo de maquinaria); los pagos son los
        anteriores de la campaña con el dueño, sin contar el giro de esta
        liquidación."""
        self.ensure_one()
        Mov = self.env['finca.labor.movimiento']
        unidades = dict(self.env['finca.labor']._fields['unidad'].selection)
        propios = [(m, r.id) for m, r in (('account.move', self.move_id),
                                          ('account.payment', self.payment_id)) if r]
        detalle = []
        for linea in self.linea_ids.sorted(lambda l: l.operador_id.name or ''):
            op = linea.operador_id
            movs = Mov.search([
                ('campana_id', '=', self.campana_id.id),
                ('dueno_id', '=', self.dueno_id.id),
                ('operador_id', '=', op.id),
            ], order='fecha, id')
            filas = []
            for mov in movs.filtered(lambda m: m.tipo != 'pago'):
                origen = self.env[mov.res_model].browse(mov.res_id)
                if mov.tipo == 'contrato':
                    for tramo in origen.tramo_ids.filtered(lambda t: op in t.operador_ids):
                        concepto = origen.labor_id.name + ' · ' + (
                            'Lote %s' % tramo.lote_id.name if tramo.lote_id else '')
                        if tramo.detalle:
                            concepto += (' · ' if tramo.lote_id else '') + tramo.detalle
                        filas.append({
                            'fecha': origen.fecha, 'referencia': origen.name,
                            'finca': origen.finca_id.name, 'concepto': concepto,
                            'cantidad': tramo.cantidad, 'unidad': unidades.get(origen.unidad, ''),
                            'tarifa': tramo.tarifa,
                            'entre': tramo.num_operadores if tramo.num_operadores > 1 else 0,
                            'valor': tramo._valores_por_operador().get(op, 0.0),
                        })
                elif mov.tipo == 'jornal':
                    filas.append({
                        'fecha': origen.fecha_hasta, 'referencia': origen.name,
                        'finca': origen.finca_id.name,
                        'concepto': ' · '.join(filter(None, [origen.labor_id.name, origen.descripcion])),
                        'cantidad': origen.cantidad, 'unidad': unidades.get(origen.unidad, ''),
                        'tarifa': origen.valor_unitario, 'entre': 0, 'valor': origen.total,
                    })
                else:
                    filas.append({
                        'fecha': mov.fecha, 'referencia': mov.referencia,
                        'finca': mov.finca_id.name or '', 'concepto': mov.descripcion or 'Maquinaria',
                        'cantidad': 0, 'unidad': '', 'tarifa': 0, 'entre': 0, 'valor': mov.trabajos,
                    })
            pagos = movs.filtered(
                lambda m: m.tipo == 'pago' and (m.res_model, m.res_id) not in propios)
            total_trabajos = sum(f['valor'] for f in filas)
            total_pagos = sum(pagos.mapped('pagos'))
            saldo = total_trabajos - total_pagos
            detalle.append({
                'operador': op, 'trabajos': filas, 'total_trabajos': total_trabajos,
                'pagos': pagos, 'total_pagos': total_pagos, 'saldo': saldo,
                'monto': linea.monto, 'queda': saldo - linea.monto,
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
