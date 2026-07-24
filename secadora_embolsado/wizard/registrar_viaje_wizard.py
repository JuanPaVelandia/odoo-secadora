# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError


class RegistrarViajeWizard(models.TransientModel):
    _name = 'secadora.registrar.viaje.wizard'
    _description = 'Registrar Viaje de Embolsado'

    silobolsa_id = fields.Many2one(
        'secadora.silobolsa',
        string='Silobolsa',
        required=True,
        domain=[('state', '=', 'abierto')],
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
    sitio_id = fields.Many2one(
        'secadora.sitio.muestra',
        string='Contenedor Origen',
        required=True,
        domain=[('es_contenedor', '=', True)],
    )
    peso_disponible_kg = fields.Float(
        string='Disponible en Contenedor (Kg)',
        digits=(12, 2),
        compute='_compute_disponible',
    )
    # La tara vigente se computa siempre en el servidor a partir de la pareja:
    # así el valor no depende de lo que el cliente envíe en el guardado.
    tara_id = fields.Many2one(
        'secadora.embolsado.tara',
        string='Tara Vigente',
        compute='_compute_tara',
    )
    peso_tara_kg = fields.Float(
        string='Peso Vacío (Kg)',
        digits=(12, 2),
        compute='_compute_tara',
    )
    tara_fecha = fields.Datetime(
        string='Fecha de la Tara',
        compute='_compute_tara',
    )
    tara_vencida = fields.Boolean(
        string='Tara Vencida',
        compute='_compute_tara',
    )
    # Campo ancla del widget de peso en vivo (el valor real capturado va en peso_lleno_kg)
    peso_vivo = fields.Float(string='Peso en Vivo')
    peso_lleno_kg = fields.Float(
        string='Peso Lleno (Kg)',
        digits=(12, 2),
    )
    peso_neto_kg = fields.Float(
        string='Peso Neto (Kg)',
        digits=(12, 2),
        compute='_compute_pesos',
    )
    peso_restante_kg = fields.Float(
        string='Quedaría en Contenedor (Kg)',
        digits=(12, 2),
        compute='_compute_pesos',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        # Precargar la pareja y silobolsa del último viaje (el tolvo casi no cambia)
        ultimo = self.env['secadora.embolsado.viaje'].search([
            ('state', '=', 'confirmado'),
            ('company_id', '=', self.env.company.id),
        ], order='id desc', limit=1)
        if ultimo:
            res.setdefault('tractor_id', ultimo.tractor_id.id)
            res.setdefault('tolvo_id', ultimo.tolvo_id.id)
            if 'silobolsa_id' not in res and ultimo.silobolsa_id.state == 'abierto':
                res['silobolsa_id'] = ultimo.silobolsa_id.id
            res.setdefault('sitio_id', ultimo.sitio_id.id)
        return res

    @api.depends('sitio_id')
    def _compute_disponible(self):
        Viaje = self.env['secadora.embolsado.viaje']
        for rec in self:
            if rec.sitio_id:
                posiciones = Viaje._posiciones_fifo(rec.sitio_id, self.env.company)
                rec.peso_disponible_kg = sum(posiciones.mapped('peso_kg'))
            else:
                rec.peso_disponible_kg = 0.0

    @api.depends('tractor_id', 'tolvo_id')
    def _compute_tara(self):
        Tara = self.env['secadora.embolsado.tara']
        for rec in self:
            tara = Tara._tara_vigente(
                rec.tractor_id.id or False, rec.tolvo_id.id or False)
            rec.tara_id = tara
            rec.peso_tara_kg = tara.peso_tara_kg if tara else 0.0
            rec.tara_fecha = tara.fecha if tara else False
            rec.tara_vencida = tara.esta_vencida if tara else False

    @api.depends('peso_lleno_kg', 'peso_tara_kg', 'peso_disponible_kg')
    def _compute_pesos(self):
        for rec in self:
            rec.peso_neto_kg = rec.peso_lleno_kg - rec.peso_tara_kg
            rec.peso_restante_kg = rec.peso_disponible_kg - rec.peso_neto_kg

    @api.onchange('tractor_id', 'tolvo_id')
    def _onchange_pareja(self):
        if self.tractor_id and self.tolvo_id and not self.tara_id:
            return {
                'warning': {
                    'title': 'Sin tara registrada',
                    'message': 'La pareja %s + %s no tiene tara registrada. '
                               'Regístrela en Embolsado → Taras antes de confirmar el viaje.' % (
                                   self.tractor_id.placa, self.tolvo_id.placa),
                }
            }

    def _reabrir(self):
        return {
            'name': 'Registrar Viaje de Embolsado',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_capturar_peso(self):
        """Tomar el peso lleno de la lectura en vivo de la báscula."""
        self.ensure_one()
        peso = self.env['secadora.pesaje']._peso_bascula_reciente()
        if peso <= 0:
            raise UserError(
                'No hay peso reciente de la báscula (últimos 15 segundos). '
                'Verifica que la báscula esté conectada (botón "Conectar báscula") '
                'y que el vehículo esté sobre la plataforma.'
            )
        self.peso_lleno_kg = peso
        return self._reabrir()

    def _crear_viaje(self):
        self.ensure_one()
        if not self.sitio_id:
            raise UserError('Seleccione el contenedor del tablero de donde sale el arroz.')
        if not self.tara_id:
            raise UserError(
                'La pareja %s + %s no tiene tara registrada. '
                'Regístrela primero en Embolsado → Taras.' % (
                    self.tractor_id.placa or '?', self.tolvo_id.placa or '?')
            )
        if self.peso_lleno_kg <= 0:
            raise UserError('Capture o digite el peso lleno del viaje.')

        viaje = self.env['secadora.embolsado.viaje'].create({
            'silobolsa_id': self.silobolsa_id.id,
            'tractor_id': self.tractor_id.id,
            'tolvo_id': self.tolvo_id.id,
            'tara_id': self.tara_id.id,
            'peso_tara_kg': self.tara_id.peso_tara_kg,
            'peso_lleno_kg': self.peso_lleno_kg,
            'sitio_id': self.sitio_id.id,
        })
        viaje.action_confirmar()
        return viaje

    def _notificar(self, viaje, siguiente):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': 'Viaje registrado',
                'message': '%s: %.2f kg netos → %s' % (
                    viaje.name, viaje.peso_neto_kg, viaje.silobolsa_id.name),
                'next': siguiente,
            },
        }

    def action_registrar(self):
        """Registrar el viaje y abrir un wizard nuevo para el siguiente."""
        viaje = self._crear_viaje()
        nuevo = self.create({
            'silobolsa_id': viaje.silobolsa_id.id,
            'tractor_id': viaje.tractor_id.id,
            'tolvo_id': viaje.tolvo_id.id,
            'sitio_id': viaje.sitio_id.id,
        })
        return self._notificar(viaje, nuevo._reabrir())

    def action_registrar_cerrar(self):
        """Registrar el viaje y cerrar el modal."""
        viaje = self._crear_viaje()
        return self._notificar(viaje, {'type': 'ir.actions.act_window_close'})
