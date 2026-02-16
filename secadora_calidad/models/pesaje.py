# -*- coding: utf-8 -*-

from odoo import models, fields, api


class SecadoraPesajeCalidad(models.Model):
    _inherit = 'secadora.pesaje'

    analisis_lab_ids = fields.One2many(
        'secadora.analisis.lab',
        'pesaje_id',
        string='Análisis de Laboratorio'
    )

    analisis_count = fields.Integer(
        string='Análisis',
        compute='_compute_analisis_count'
    )

    peso_comercial = fields.Float(
        string='Peso Comercial (kg)',
        compute='_compute_calidad_desde_analisis',
        digits=(12, 2),
        help='Peso ajustado por humedad desde el último análisis confirmado'
    )

    humedad_analisis = fields.Float(
        string='Humedad Laboratorio (%)',
        compute='_compute_calidad_desde_analisis',
        digits=(5, 2),
        help='Humedad del último análisis de laboratorio confirmado'
    )

    def _compute_analisis_count(self):
        for record in self:
            record.analisis_count = len(record.analisis_lab_ids)

    @api.depends('analisis_lab_ids.state', 'analisis_lab_ids.humedad',
                 'analisis_lab_ids.peso_comercial')
    def _compute_calidad_desde_analisis(self):
        for record in self:
            analisis_confirmado = record.analisis_lab_ids.filtered(
                lambda a: a.state == 'confirmado'
            ).sorted('fecha_hora', reverse=True)
            if analisis_confirmado:
                ultimo = analisis_confirmado[0]
                record.humedad_analisis = ultimo.humedad
                record.peso_comercial = ultimo.peso_comercial
            else:
                record.humedad_analisis = 0.0
                record.peso_comercial = 0.0

    def action_crear_analisis(self):
        """Crear un análisis de laboratorio pre-llenado con datos del pesaje"""
        self.ensure_one()
        vals = {
            'pesaje_id': self.id,
            'tercero_id': self.tercero_id.id if self.tercero_id else False,
            'variedad_id': self.variedad_id.id if self.variedad_id else False,
            'tipo_operacion_id': self.tipo_operacion_id.id if self.tipo_operacion_id else False,
            'orden_servicio_id': self.orden_servicio_id.id if self.orden_servicio_id else False,
        }
        analisis = self.env['secadora.analisis.lab'].create(vals)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'secadora.analisis.lab',
            'res_id': analisis.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_ver_analisis(self):
        """Ver análisis de laboratorio vinculados al pesaje"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Análisis - {self.name}',
            'res_model': 'secadora.analisis.lab',
            'domain': [('pesaje_id', '=', self.id)],
            'view_mode': 'list,form',
            'target': 'current',
            'context': {'default_pesaje_id': self.id},
        }
