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
        # Verificar si ya existe una posición pre-asignada desde el tablero
        preasignada = self.env['secadora.posicion.arroz'].search([
            ('pesaje_id', '=', pesaje.id),
            ('es_preasignado', '=', True),
            ('state', '=', 'activo'),
        ], limit=1)

        if preasignada:
            # Calcular peso ya distribuido en otras posiciones activas (divisiones)
            otras_posiciones = self.env['secadora.posicion.arroz'].search([
                ('pesaje_id', '=', pesaje.id),
                ('state', '=', 'activo'),
                ('id', '!=', preasignada.id),
            ])
            peso_ya_distribuido = sum(otras_posiciones.mapped('peso_kg'))
            peso_para_preasignada = pesaje.peso_neto - peso_ya_distribuido

            preasignada.write({
                'peso_kg': peso_para_preasignada,
                'peso_original': pesaje.peso_neto,
                'es_preasignado': False,
                'humedad': pesaje.humedad,
                'impurezas': pesaje.impurezas,
                'variedad_id': pesaje.variedad_id.id if pesaje.variedad_id else False,
            })
            self.env['secadora.movimiento.arroz'].create({
                'posicion_id': preasignada.id,
                'sitio_destino_id': preasignada.sitio_id.id,
                'peso_kg': peso_para_preasignada,
                'tipo': 'creacion',
                'notas': f'Pesaje completado. Peso neto: {pesaje.peso_neto:.2f} kg, distribuido en otras: {peso_ya_distribuido:.2f} kg, asignado aquí: {peso_para_preasignada:.2f} kg',
            })
            return

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
            'humedad': pesaje.humedad,
            'impurezas': pesaje.impurezas,
            'variedad_id': pesaje.variedad_id.id if pesaje.variedad_id else False,
            'company_id': pesaje.company_id.id,
        })

        # Registrar movimiento de creación
        self.env['secadora.movimiento.arroz'].create({
            'posicion_id': posicion.id,
            'sitio_destino_id': sitio.id,
            'peso_kg': pesaje.peso_neto,
            'tipo': 'creacion',
            'notas': f'Creado automáticamente desde pesaje {pesaje.name}',
        })

    def write(self, vals):
        res = super().write(vals)
        if 'humedad' in vals or 'impurezas' in vals:
            for rec in self:
                update = {}
                if 'humedad' in vals:
                    update['humedad'] = rec.humedad
                if 'impurezas' in vals:
                    update['impurezas'] = rec.impurezas
                posiciones = self.env['secadora.posicion.arroz'].search([
                    ('pesaje_id', '=', rec.id),
                    ('es_comercial', '=', False),
                ])
                if posiciones:
                    posiciones.write(update)
                # Propagar a fletes vinculados
                fletes = self.env['secadora.flete'].search([
                    ('pesaje_id', '=', rec.id),
                ])
                if fletes:
                    fletes.write(update)
        return res

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
