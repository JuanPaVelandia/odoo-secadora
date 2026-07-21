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

        # La semilla solo puede combinarse cuando todas las posiciones son del
        # mismo viaje (pesaje) que fue dividido antes; nunca se mezclan viajes.
        if any(p.es_semilla for p in self.posicion_ids):
            if not all(p.es_semilla for p in self.posicion_ids):
                raise UserError('No se pueden combinar posiciones de semilla con posiciones que no son semilla.')
            pesajes = self.posicion_ids.mapped('pesaje_id')
            if len(pesajes) > 1:
                raise UserError(
                    'Solo se pueden combinar posiciones de semilla del mismo viaje '
                    '(mismo pesaje) que fue dividido previamente.'
                )

        # La posición con mayor peso determina el pesaje de la combinación
        posicion_mayor = max(self.posicion_ids, key=lambda p: p.peso_kg)

        peso_total = sum(self.posicion_ids.mapped('peso_kg'))

        # Variedad solo si todas las posiciones tienen la misma
        variedades = self.posicion_ids.mapped('variedad_id')
        variedad_id = variedades[0].id if len(set(variedades.ids)) == 1 and variedades else False

        # La combinación de semilla (viaje dividido que se reúne) NO es comercial:
        # todas las posiciones comparten el mismo pesaje, así que la posición
        # resultante conserva la información del viaje (tercero, conductor, salida,
        # etc.) vía los related de pesaje_id. Solo las combinaciones no-semilla se
        # marcan como comerciales.
        es_semilla_combinacion = all(p.es_semilla for p in self.posicion_ids)

        # Calidad consolidada: promedio ponderado por peso de los viajes que
        # se combinan. Solo cuentan las posiciones que traen el dato — incluir
        # una sin medición como 0% diluiría el promedio falsamente.
        def _promedio_ponderado(campo):
            con_dato = self.posicion_ids.filtered(
                lambda p: getattr(p, campo) > 0 and p.peso_kg > 0
            )
            peso_base = sum(con_dato.mapped('peso_kg'))
            if not peso_base:
                return 0.0
            return sum(getattr(p, campo) * p.peso_kg for p in con_dato) / peso_base

        nueva_posicion = self.env['secadora.posicion.arroz'].create({
            'pesaje_id': posicion_mayor.pesaje_id.id,
            'sitio_id': self.sitio_id.id,
            'peso_kg': peso_total,
            'peso_original': peso_total,
            'es_comercial': not es_semilla_combinacion,
            'variedad_id': variedad_id,
            'humedad': _promedio_ponderado('humedad'),
            'impurezas': _promedio_ponderado('impurezas'),
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
