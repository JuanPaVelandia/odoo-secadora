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
    modo = fields.Selection([
        ('mantener', 'Mantener este peso aquí'),
        ('mover', 'Mover este peso al destino'),
    ], string='¿Qué hacer con el peso ingresado?', default='mantener', required=True)
    peso_ingresado = fields.Float(
        string='Peso (Kg)',
        digits=(12, 2),
        required=True,
    )
    peso_queda = fields.Float(
        string='Se queda aquí (Kg)',
        digits=(12, 2),
        compute='_compute_pesos_resultado',
    )
    peso_se_mueve = fields.Float(
        string='Se mueve al destino (Kg)',
        digits=(12, 2),
        compute='_compute_pesos_resultado',
    )
    sitio_destino_id = fields.Many2one(
        'secadora.sitio.muestra',
        string='Ubicación Destino',
        domain=[('es_contenedor', '=', True)],
        required=True,
    )

    @api.depends('peso_actual', 'peso_ingresado', 'modo')
    def _compute_pesos_resultado(self):
        for rec in self:
            if rec.modo == 'mantener':
                rec.peso_queda = rec.peso_ingresado
                rec.peso_se_mueve = rec.peso_actual - rec.peso_ingresado
            else:
                rec.peso_se_mueve = rec.peso_ingresado
                rec.peso_queda = rec.peso_actual - rec.peso_ingresado

    def action_dividir(self):
        self.ensure_one()
        posicion = self.posicion_id

        # Lock position to prevent concurrent modifications during division
        self.env.cr.execute(
            'SELECT id FROM secadora_posicion_arroz WHERE id = %s FOR UPDATE NOWAIT',
            [posicion.id]
        )
        posicion.invalidate_recordset(['peso_kg', 'state'])

        # Re-read actual weight from DB after lock
        peso_actual_real = posicion.peso_kg
        if abs(peso_actual_real - self.peso_actual) > 0.01:
            raise UserError(
                f'El peso de la posición cambió mientras se preparaba la división. '
                f'Peso esperado: {self.peso_actual:.2f} kg, peso actual: {peso_actual_real:.2f} kg. '
                f'Por favor intente de nuevo.'
            )

        if self.modo == 'mantener':
            peso_mantener = self.peso_ingresado
            peso_mover = self.peso_actual - self.peso_ingresado
        else:
            peso_mover = self.peso_ingresado
            peso_mantener = self.peso_actual - self.peso_ingresado

        # Validaciones
        if peso_mantener <= 0:
            raise UserError('El peso que se queda debe ser mayor a cero.')
        if peso_mover <= 0:
            raise UserError('El peso a mover debe ser mayor a cero.')
        if abs(peso_mantener + peso_mover - self.peso_actual) > 0.01:
            raise UserError('La suma de los pesos no coincide con el peso actual.')
        if self.sitio_destino_id == posicion.sitio_id:
            raise UserError('La ubicación destino debe ser diferente a la ubicación actual.')

        # Reducir peso de la posición original
        posicion.write({'peso_kg': peso_mantener})

        # Crear nueva posición en destino
        nueva_posicion = self.env['secadora.posicion.arroz'].create({
            'pesaje_id': posicion.pesaje_id.id,
            'sitio_id': self.sitio_destino_id.id,
            'peso_kg': peso_mover,
            'peso_original': posicion.peso_original,
            'posicion_origen_id': posicion.id,
            'es_comercial': posicion.es_comercial,
            'humedad': posicion.humedad,
            'impurezas': posicion.impurezas,
            'variedad_id': posicion.variedad_id.id if posicion.variedad_id else False,
        })

        # Registrar movimientos tipo división
        MovimientoArroz = self.env['secadora.movimiento.arroz']

        # Movimiento en posición original (reducción de peso)
        MovimientoArroz.create({
            'posicion_id': posicion.id,
            'sitio_origen_id': posicion.sitio_id.id if posicion.sitio_id else False,
            'sitio_destino_id': posicion.sitio_id.id if posicion.sitio_id else False,
            'peso_kg': peso_mantener,
            'tipo': 'division',
            'notas': f'División: se mantienen {peso_mantener:.2f} kg, se mueven {peso_mover:.2f} kg a {self.sitio_destino_id.name}',
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
