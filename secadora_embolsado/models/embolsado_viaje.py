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
    posicion_id = fields.Many2one(
        'secadora.posicion.arroz',
        string='Posición Origen',
        required=True,
        ondelete='restrict',
        index=True,
        domain=[('state', '=', 'activo'), ('sitio_id.es_contenedor', '=', True)],
        tracking=True,
    )
    sitio_id = fields.Many2one(
        related='posicion_id.sitio_id',
        store=True,
        string='Contenedor Origen',
    )
    state = fields.Selection([
        ('borrador', 'Borrador'),
        ('confirmado', 'Confirmado'),
        ('cancelado', 'Cancelado'),
    ], string='Estado', default='borrador', required=True, tracking=True, index=True)
    movimiento_arroz_id = fields.Many2one(
        'secadora.movimiento.arroz',
        string='Movimiento de Arroz',
        readonly=True,
        copy=False,
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

    @api.constrains('posicion_id', 'company_id')
    def _check_posicion_company(self):
        for rec in self:
            if rec.posicion_id.company_id and rec.posicion_id.company_id != rec.company_id:
                raise ValidationError(
                    'La posición %s pertenece a otra empresa.' % rec.posicion_id.name
                )

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

    def action_confirmar(self):
        """Confirmar el viaje: descuenta el peso neto de la posición del tablero
        y consume la silobolsa del inventario si es el primer viaje."""
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

            posicion = rec.posicion_id

            # Lock de la posición para evitar descuentos concurrentes
            # (mismo protocolo que dividir/despachar del tablero)
            self.env.cr.execute(
                'SELECT id FROM secadora_posicion_arroz WHERE id = %s FOR UPDATE NOWAIT',
                [posicion.id]
            )
            posicion.invalidate_recordset(['peso_kg', 'state'])

            if posicion.state != 'activo':
                raise UserError(
                    'La posición %s ya no está activa. Actualice el tablero e intente de nuevo.'
                    % posicion.name
                )
            if rec.peso_neto_kg > posicion.peso_kg + 0.01:
                raise UserError(
                    'El peso neto del viaje (%.2f kg) supera el peso disponible en '
                    '%s (%.2f kg).' % (rec.peso_neto_kg, posicion.name, posicion.peso_kg)
                )

            nuevo_peso = posicion.peso_kg - rec.peso_neto_kg
            if nuevo_peso <= 0.01:
                posicion.write({'peso_kg': 0, 'state': 'retirado'})
            else:
                posicion.write({'peso_kg': nuevo_peso})

            movimiento = self.env['secadora.movimiento.arroz'].create({
                'posicion_id': posicion.id,
                'sitio_origen_id': posicion.sitio_id.id if posicion.sitio_id else False,
                'peso_kg': rec.peso_neto_kg,
                'tipo': 'embolsado',
                'embolsado_viaje_id': rec.id,
                'notas': 'Embolsado: %.2f kg → %s (viaje %s)' % (
                    rec.peso_neto_kg, rec.silobolsa_id.name, rec.name),
            })

            rec.write({'state': 'confirmado', 'movimiento_arroz_id': movimiento.id})

            # Al primer viaje confirmado se consume la silobolsa (idempotente)
            rec.silobolsa_id._crear_consumo_silobolsa()

            # Heredar variedad del primer arroz embolsado si no está definida
            if not rec.silobolsa_id.variedad_id and posicion.variedad_id:
                rec.silobolsa_id.variedad_id = posicion.variedad_id

    def action_cancelar(self):
        """Cancelar un viaje confirmado devolviendo el peso a la posición."""
        for rec in self:
            if rec.state == 'borrador':
                rec.state = 'cancelado'
                continue
            if rec.state != 'confirmado':
                raise UserError('El viaje %s ya está cancelado.' % rec.name)
            if not self.env.user.has_group('secadora_embolsado.group_embolsado_admin'):
                raise UserError('Solo un administrador de embolsado puede cancelar viajes confirmados.')

            posicion = rec.posicion_id
            self.env.cr.execute(
                'SELECT id FROM secadora_posicion_arroz WHERE id = %s FOR UPDATE NOWAIT',
                [posicion.id]
            )
            posicion.invalidate_recordset(['peso_kg', 'state'])

            vals = {'peso_kg': posicion.peso_kg + rec.peso_neto_kg}
            # Si el embolsado dejó la posición en cero y retirada, reactivarla
            if posicion.state == 'retirado' and posicion.peso_kg <= 0.01:
                vals['state'] = 'activo'
            elif posicion.state != 'activo':
                raise UserError(
                    'La posición %s no está activa (%s); no se puede devolver el peso. '
                    'Reactívela primero.' % (posicion.name, posicion.state)
                )
            posicion.write(vals)

            self.env['secadora.movimiento.arroz'].create({
                'posicion_id': posicion.id,
                'sitio_destino_id': posicion.sitio_id.id if posicion.sitio_id else False,
                'peso_kg': rec.peso_neto_kg,
                'tipo': 'embolsado',
                'embolsado_viaje_id': rec.id,
                'notas': 'Cancelación de embolsado: +%.2f kg devueltos desde %s (viaje %s)' % (
                    rec.peso_neto_kg, rec.silobolsa_id.name, rec.name),
            })
            rec.state = 'cancelado'
