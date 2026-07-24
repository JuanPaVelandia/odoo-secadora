# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


class EmbolsadoViaje(models.Model):
    _name = 'secadora.embolsado.viaje'
    _description = 'Viaje de Embolsado'
    _inherit = ['mail.thread']
    _order = 'fecha desc, id desc'
    _peso_lleno_no_negativo = models.Constraint(
        'CHECK(peso_lleno_kg >= 0)',
        'El peso lleno no puede ser negativo.',
    )

    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    name = fields.Char(
        string='Referencia',
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: 'Nuevo',
    )
    fecha = fields.Datetime(
        string='Fecha',
        default=fields.Datetime.now,
        required=True,
        index=True,
    )
    usuario_id = fields.Many2one(
        'res.users',
        string='Usuario',
        default=lambda self: self.env.uid,
        required=True,
    )
    silobolsa_id = fields.Many2one(
        'secadora.silobolsa',
        string='Silobolsa',
        required=True,
        ondelete='restrict',
        index=True,
        domain=[('state', '=', 'abierto')],
        tracking=True,
    )
    tractor_id = fields.Many2one(
        'secadora.vehiculo',
        string='Tractor',
        required=True,
    )
    tolvo_id = fields.Many2one(
        'secadora.vehiculo',
        string='Tolvo',
        required=True,
    )
    tara_id = fields.Many2one(
        'secadora.embolsado.tara',
        string='Tara Usada',
        readonly=True,
        ondelete='restrict',
        help='Tara vigente de la pareja tractor+tolvo al momento del viaje.',
    )
    peso_tara_kg = fields.Float(
        string='Peso Vacío (Kg)',
        digits=(12, 2),
        readonly=True,
        help='Copia del peso de la tara al momento del viaje (no cambia si la tara se edita después).',
    )
    peso_lleno_kg = fields.Float(
        string='Peso Lleno (Kg)',
        digits=(12, 2),
        tracking=True,
    )
    peso_neto_kg = fields.Float(
        string='Peso Neto (Kg)',
        digits=(12, 2),
        compute='_compute_peso_neto',
        store=True,
    )
    sitio_id = fields.Many2one(
        'secadora.sitio.muestra',
        string='Contenedor Origen',
        required=True,
        ondelete='restrict',
        index=True,
        domain=[('es_contenedor', '=', True)],
        tracking=True,
        help='Contenedor del tablero de donde sale el arroz. El descuento agota '
             'primero la tarjeta más antigua (FIFO).',
    )
    state = fields.Selection([
        ('borrador', 'Borrador'),
        ('confirmado', 'Confirmado'),
        ('cancelado', 'Cancelado'),
    ], string='Estado', default='borrador', required=True, tracking=True, index=True)
    movimiento_ids = fields.One2many(
        'secadora.movimiento.arroz',
        'embolsado_viaje_id',
        string='Movimientos de Arroz',
        help='Tarjetas del tablero afectadas por este viaje (descuentos y reversas).',
    )
    notas = fields.Text(string='Notas')

    @api.depends('peso_lleno_kg', 'peso_tara_kg')
    def _compute_peso_neto(self):
        for rec in self:
            rec.peso_neto_kg = rec.peso_lleno_kg - rec.peso_tara_kg

    @api.constrains('tractor_id', 'tolvo_id')
    def _check_tractor_distinto_tolvo(self):
        for rec in self:
            if rec.tractor_id == rec.tolvo_id:
                raise ValidationError('El tractor y el tolvo deben ser vehículos distintos.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('secadora.embolsado.viaje') or 'Nuevo'
        return super().create(vals_list)

    def unlink(self):
        if any(rec.state == 'confirmado' for rec in self):
            raise UserError('No se puede eliminar un viaje confirmado. Cancélelo primero.')
        return super().unlink()

    @api.model
    def _posiciones_fifo(self, sitio, company):
        """Tarjetas activas del contenedor, de la más vieja a la más nueva."""
        return self.env['secadora.posicion.arroz'].search([
            ('sitio_id', '=', sitio.id),
            ('state', '=', 'activo'),
            ('company_id', 'in', [company.id, False]),
        ], order='fecha_ingreso asc, id asc')

    def _lock_posiciones(self, posiciones):
        """Lock de tarjetas para evitar descuentos concurrentes
        (mismo protocolo que dividir/despachar del tablero)."""
        if not posiciones:
            return
        self.env.cr.execute(
            'SELECT id FROM secadora_posicion_arroz WHERE id IN %s FOR UPDATE NOWAIT',
            [tuple(posiciones.ids)]
        )
        posiciones.invalidate_recordset(['peso_kg', 'state'])

    def action_confirmar(self):
        """Confirmar el viaje: descuenta el neto del contenedor (FIFO sobre sus
        tarjetas) y consume la silobolsa del inventario si es el primer viaje."""
        for rec in self:
            if rec.state != 'borrador':
                raise UserError('Solo se pueden confirmar viajes en borrador.')
            # Viajes creados a mano (sin el wizard): tomar la tara vigente aquí
            if not rec.tara_id:
                tara = self.env['secadora.embolsado.tara']._tara_vigente(
                    rec.tractor_id.id, rec.tolvo_id.id)
                if tara:
                    rec.write({'tara_id': tara.id, 'peso_tara_kg': tara.peso_tara_kg})
            if not rec.tara_id or rec.peso_tara_kg <= 0:
                raise UserError(
                    'El viaje no tiene tara asignada. Registre la tara de la pareja '
                    '%s + %s antes de confirmar.' % (
                        rec.tractor_id.placa or '?', rec.tolvo_id.placa or '?')
                )
            if rec.peso_neto_kg <= 0:
                raise UserError(
                    'El peso neto debe ser mayor a cero '
                    '(lleno: %.2f kg, vacío: %.2f kg).' % (rec.peso_lleno_kg, rec.peso_tara_kg)
                )
            if rec.silobolsa_id.state != 'abierto':
                raise UserError('La silobolsa %s está cerrada.' % rec.silobolsa_id.name)

            posiciones = self._posiciones_fifo(rec.sitio_id, rec.company_id)
            if not posiciones:
                raise UserError(
                    'El contenedor %s no tiene arroz activo en el tablero.' % rec.sitio_id.name
                )
            self._lock_posiciones(posiciones)
            posiciones = posiciones.filtered(lambda p: p.state == 'activo')

            disponible = sum(posiciones.mapped('peso_kg'))
            if rec.peso_neto_kg > disponible + 0.01:
                raise UserError(
                    'El peso neto del viaje (%.2f kg) supera el arroz disponible en '
                    '%s (%.2f kg).' % (rec.peso_neto_kg, rec.sitio_id.name, disponible)
                )

            # Descuento FIFO: agotar la tarjeta más vieja y seguir con la siguiente
            Movimiento = self.env['secadora.movimiento.arroz']
            restante = rec.peso_neto_kg
            primera_pos = posiciones[:1]
            for pos in posiciones:
                if restante <= 0.01:
                    break
                descuento = min(pos.peso_kg, restante)
                nuevo_peso = pos.peso_kg - descuento
                if nuevo_peso <= 0.01:
                    pos.write({'peso_kg': 0, 'state': 'retirado'})
                else:
                    pos.write({'peso_kg': nuevo_peso})
                Movimiento.create({
                    'posicion_id': pos.id,
                    'sitio_origen_id': rec.sitio_id.id,
                    'peso_kg': descuento,
                    'tipo': 'embolsado',
                    'embolsado_viaje_id': rec.id,
                    'notas': 'Embolsado: %.2f kg → %s (viaje %s)' % (
                        descuento, rec.silobolsa_id.name, rec.name),
                })
                restante -= descuento

            rec.state = 'confirmado'

            # Al primer viaje confirmado se consume la silobolsa (idempotente)
            rec.silobolsa_id._crear_consumo_silobolsa()

            # Heredar variedad del primer arroz embolsado si no está definida
            if not rec.silobolsa_id.variedad_id and primera_pos.variedad_id:
                rec.silobolsa_id.variedad_id = primera_pos.variedad_id

    def action_cancelar(self):
        """Cancelar un viaje confirmado devolviendo el peso a sus tarjetas."""
        for rec in self:
            if rec.state == 'borrador':
                rec.state = 'cancelado'
                continue
            if rec.state != 'confirmado':
                raise UserError('El viaje %s ya está cancelado.' % rec.name)
            if not self.env.user.has_group('secadora_embolsado.group_embolsado_admin'):
                raise UserError('Solo un administrador de embolsado puede cancelar viajes confirmados.')

            # Los descuentos originales tienen sitio_origen_id; las reversas, sitio_destino_id
            descuentos = rec.movimiento_ids.filtered(
                lambda m: m.tipo == 'embolsado' and m.sitio_origen_id)
            posiciones = descuentos.mapped('posicion_id')
            self._lock_posiciones(posiciones)

            Movimiento = self.env['secadora.movimiento.arroz']
            for mov in descuentos:
                pos = mov.posicion_id
                vals = {'peso_kg': pos.peso_kg + mov.peso_kg}
                # Si el embolsado dejó la tarjeta en cero y retirada, reactivarla
                if pos.state == 'retirado' and pos.peso_kg <= 0.01:
                    vals['state'] = 'activo'
                elif pos.state != 'activo':
                    raise UserError(
                        'La tarjeta %s no está activa (%s); no se puede devolver el peso. '
                        'Reactívela primero.' % (pos.name, pos.state)
                    )
                pos.write(vals)
                Movimiento.create({
                    'posicion_id': pos.id,
                    'sitio_destino_id': mov.sitio_origen_id.id,
                    'peso_kg': mov.peso_kg,
                    'tipo': 'embolsado',
                    'embolsado_viaje_id': rec.id,
                    'notas': 'Cancelación de embolsado: +%.2f kg devueltos desde %s (viaje %s)' % (
                        mov.peso_kg, rec.silobolsa_id.name, rec.name),
                })
            rec.state = 'cancelado'
