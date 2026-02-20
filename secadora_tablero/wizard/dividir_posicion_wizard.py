# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError


class DividirPosicionWizard(models.TransientModel):
    _name = 'secadora.dividir.posicion.wizard'
    _description = 'Dividir Posición de Arroz'

    posicion_id = fields.Many2one(
        'secadora.posicion.arroz',
        string='Posición',
        required=True,
        readonly=True,
    )
    peso_actual = fields.Float(
        string='Peso Actual (Kg)',
        digits=(12, 2),
        readonly=True,
    )
    peso_mantener = fields.Float(
        string='Peso a Mantener (Kg)',
        digits=(12, 2),
        required=True,
    )
    peso_mover = fields.Float(
        string='Peso a Mover (Kg)',
        digits=(12, 2),
        compute='_compute_peso_mover',
    )
    sitio_destino_id = fields.Many2one(
        'secadora.sitio.muestra',
        string='Ubicación Destino',
        domain=[('es_contenedor', '=', True)],
        required=True,
    )

    @api.depends('peso_actual', 'peso_mantener')
    def _compute_peso_mover(self):
        for rec in self:
            rec.peso_mover = rec.peso_actual - rec.peso_mantener

    def action_dividir(self):
        self.ensure_one()
        posicion = self.posicion_id

        # Validaciones
        if self.peso_mantener <= 0:
            raise UserError('El peso a mantener debe ser mayor a cero.')
        if self.peso_mantener >= self.peso_actual:
            raise UserError('El peso a mantener debe ser menor al peso actual.')
        if self.sitio_destino_id == posicion.sitio_id:
            raise UserError('La ubicación destino debe ser diferente a la ubicación actual.')

        peso_mover = self.peso_actual - self.peso_mantener

        # Reducir peso de la posición original
        posicion.write({'peso_kg': self.peso_mantener})

        # Crear nueva posición en destino
        nueva_posicion = self.env['secadora.posicion.arroz'].create({
            'pesaje_id': posicion.pesaje_id.id,
            'sitio_id': self.sitio_destino_id.id,
            'peso_kg': peso_mover,
            'peso_original': posicion.peso_original,
            'posicion_origen_id': posicion.id,
        })

        # Registrar movimientos tipo división
        MovimientoArroz = self.env['secadora.movimiento.arroz']

        # Movimiento en posición original (reducción de peso)
        MovimientoArroz.create({
            'posicion_id': posicion.id,
            'sitio_origen_id': posicion.sitio_id.id if posicion.sitio_id else False,
            'sitio_destino_id': posicion.sitio_id.id if posicion.sitio_id else False,
            'peso_kg': self.peso_mantener,
            'tipo': 'division',
            'notas': f'División: se mantienen {self.peso_mantener:.2f} kg, se mueven {peso_mover:.2f} kg a {self.sitio_destino_id.name}',
        })

        # Movimiento en nueva posición (creación por división)
        MovimientoArroz.create({
            'posicion_id': nueva_posicion.id,
            'sitio_origen_id': posicion.sitio_id.id if posicion.sitio_id else False,
            'sitio_destino_id': self.sitio_destino_id.id,
            'peso_kg': peso_mover,
            'tipo': 'division',
            'notas': f'División: {peso_mover:.2f} kg movidos desde {posicion.sitio_id.name or "sin ubicación"} ({posicion.name})',
        })

        return {'type': 'ir.actions.act_window_close'}
