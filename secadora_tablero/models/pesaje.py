# -*- coding: utf-8 -*-

from odoo import models, fields, api


class SecadoraPesaje(models.Model):
    _inherit = 'secadora.pesaje'

    posicion_arroz_ids = fields.One2many(
        'secadora.posicion.arroz',
        'pesaje_id',
        string='Posiciones de Arroz',
    )
    posicion_count = fields.Integer(
        string='Posiciones',
        compute='_compute_posicion_count',
    )

    @api.depends('posicion_arroz_ids')
    def _compute_posicion_count(self):
        for rec in self:
            rec.posicion_count = len(rec.posicion_arroz_ids)

    def action_segunda_pesada(self):
        res = super().action_segunda_pesada()
        for record in self:
            if record.state == 'completado' and record.direccion == 'entrada':
                self._crear_posicion_arroz(record)
        return res

    def _crear_posicion_arroz(self, pesaje):
        """Crear tarjeta de posición de arroz al completar pesaje de entrada."""
        # Buscar el primer sitio contenedor por secuencia (ej: Tolva)
        sitio = self.env['secadora.sitio.muestra'].search(
            [('es_contenedor', '=', True)],
            order='sequence, id',
            limit=1,
        )
        if not sitio:
            return

        posicion = self.env['secadora.posicion.arroz'].create({
            'pesaje_id': pesaje.id,
            'sitio_id': sitio.id,
            'peso_kg': pesaje.peso_neto,
            'peso_original': pesaje.peso_neto,
        })

        # Registrar movimiento de creación
        self.env['secadora.movimiento.arroz'].create({
            'posicion_id': posicion.id,
            'sitio_destino_id': sitio.id,
            'peso_kg': pesaje.peso_neto,
            'tipo': 'creacion',
            'notas': f'Creado automáticamente desde pesaje {pesaje.name}',
        })

    def action_ver_posiciones(self):
        """Abrir vista de posiciones de arroz del pesaje."""
        self.ensure_one()
        return {
            'name': 'Posiciones de Arroz',
            'type': 'ir.actions.act_window',
            'res_model': 'secadora.posicion.arroz',
            'view_mode': 'kanban,list,form',
            'domain': [('pesaje_id', '=', self.id)],
            'context': {'default_pesaje_id': self.id},
        }
