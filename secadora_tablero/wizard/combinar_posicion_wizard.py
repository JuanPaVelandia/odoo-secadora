# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError


class CombinarPosicionWizard(models.TransientModel):
    _name = 'secadora.combinar.posicion.wizard'
    _description = 'Combinar Posiciones de Arroz'

    sitio_id = fields.Many2one(
        'secadora.sitio.muestra',
        string='Ubicación',
        required=True,
        readonly=True,
    )
    posicion_ids = fields.Many2many(
        'secadora.posicion.arroz',
        string='Posiciones a Combinar',
        domain="[('sitio_id', '=', sitio_id), ('state', '=', 'activo'), ('permite_combinar', '=', True)]",
    )
    peso_total = fields.Float(
        string='Peso Total (Kg)',
        digits=(12, 2),
        compute='_compute_peso_total',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'posicion_ids' in fields_list and res.get('sitio_id'):
            posiciones = self.env['secadora.posicion.arroz'].search([
                ('sitio_id', '=', res['sitio_id']),
                ('state', '=', 'activo'),
                ('permite_combinar', '=', True),
            ])
            res['posicion_ids'] = [fields.Command.set(posiciones.ids)]
        return res

    @api.depends('posicion_ids', 'posicion_ids.peso_kg')
    def _compute_peso_total(self):
        for rec in self:
            rec.peso_total = sum(rec.posicion_ids.mapped('peso_kg'))

    def action_combinar(self):
        self.ensure_one()

        if len(self.posicion_ids) < 2:
            raise UserError('Debe seleccionar al menos 2 posiciones para combinar.')

        sitios = self.posicion_ids.mapped('sitio_id')
        if len(sitios) > 1:
            raise UserError('Todas las posiciones deben estar en la misma ubicación.')

        if any(p.es_semilla for p in self.posicion_ids):
            raise UserError('No se pueden combinar posiciones de semilla.')

        # La posición con mayor peso determina el pesaje de la combinación
        posicion_mayor = max(self.posicion_ids, key=lambda p: p.peso_kg)

        peso_total = sum(self.posicion_ids.mapped('peso_kg'))

        # Variedad solo si todas las posiciones tienen la misma
        variedades = self.posicion_ids.mapped('variedad_id')
        variedad_id = variedades[0].id if len(set(variedades.ids)) == 1 and variedades else False

        # Crear nueva posición combinada (sin humedad/impurezas)
        nueva_posicion = self.env['secadora.posicion.arroz'].create({
            'pesaje_id': posicion_mayor.pesaje_id.id,
            'sitio_id': self.sitio_id.id,
            'peso_kg': peso_total,
            'peso_original': peso_total,
            'es_comercial': True,
            'variedad_id': variedad_id,
        })

        MovimientoArroz = self.env['secadora.movimiento.arroz']

        # Marcar las originales como combinadas y vincular
        for pos in self.posicion_ids:
            pos.write({
                'state': 'combinado',
                'posicion_combinada_id': nueva_posicion.id,
            })
            MovimientoArroz.create({
                'posicion_id': pos.id,
                'sitio_origen_id': pos.sitio_id.id if pos.sitio_id else False,
                'peso_kg': pos.peso_kg,
                'tipo': 'combinacion',
                'notas': f'Combinada en {nueva_posicion.name} ({peso_total:.2f} kg total)',
            })

        # Registrar movimiento de creación en la nueva posición
        nombres_origenes = ', '.join(self.posicion_ids.mapped('name'))
        MovimientoArroz.create({
            'posicion_id': nueva_posicion.id,
            'sitio_destino_id': self.sitio_id.id,
            'peso_kg': peso_total,
            'tipo': 'combinacion',
            'notas': f'Combinación de: {nombres_origenes}',
        })

        return {'type': 'ir.actions.act_window_close'}
