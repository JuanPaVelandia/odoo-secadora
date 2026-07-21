# -*- coding: utf-8 -*-

from odoo import models, fields, api


class OrdenServicioCalidad(models.Model):
    _inherit = 'secadora.orden.servicio'

    analisis_lab_ids = fields.One2many(
        'secadora.analisis.lab',
        'orden_servicio_id',
        string='Análisis de Laboratorio'
    )

    analisis_count = fields.Integer(
        string='Análisis',
        compute='_compute_analisis_count'
    )

    humedad_entrada = fields.Float(
        string='Humedad Entrada (%)',
        compute='_compute_calidad_resumen',
        digits=(5, 2),
        help='Promedio de humedad de análisis de entrada (origen Cultivo) confirmados'
    )

    humedad_salida = fields.Float(
        string='Humedad Salida (%)',
        compute='_compute_calidad_resumen',
        digits=(5, 2),
        help='Promedio de humedad de análisis de salida (origen Secamiento/Almacenamiento) confirmados'
    )

    diferencia_humedad = fields.Float(
        string='Reducción Humedad (puntos %)',
        compute='_compute_calidad_resumen',
        digits=(5, 2),
        help='Diferencia entre humedad de entrada y salida'
    )

    impurezas_entrada = fields.Float(
        string='Impurezas Entrada (%)',
        compute='_compute_calidad_resumen',
        digits=(5, 2),
        help='Promedio de impurezas de análisis de entrada (origen Cultivo) confirmados'
    )

    impurezas_salida = fields.Float(
        string='Impurezas Salida (%)',
        compute='_compute_calidad_resumen',
        digits=(5, 2),
        help='Promedio de impurezas de análisis de salida (origen Secamiento/Almacenamiento) confirmados'
    )

    def _compute_analisis_count(self):
        for record in self:
            record.analisis_count = len(record.analisis_lab_ids)

    @api.depends(
        'analisis_lab_ids.state',
        'analisis_lab_ids.origen_muestra_id',
        'analisis_lab_ids.humedad',
        'analisis_lab_ids.impurezas'
    )
    def _compute_calidad_resumen(self):
        # Obtener xmlids de los orígenes de referencia
        origen_cultivo = self.env.ref('secadora_calidad.origen_muestra_cultivo', raise_if_not_found=False)
        origen_secamiento = self.env.ref('secadora_calidad.origen_muestra_secamiento', raise_if_not_found=False)
        origen_almacenamiento = self.env.ref('secadora_calidad.origen_muestra_almacenamiento', raise_if_not_found=False)

        origenes_salida = self.env['secadora.origen.muestra']
        if origen_secamiento:
            origenes_salida |= origen_secamiento
        if origen_almacenamiento:
            origenes_salida |= origen_almacenamiento

        for record in self:
            confirmados = record.analisis_lab_ids.filtered(
                lambda a: a.state == 'confirmado'
            )
            entrada = confirmados.filtered(
                lambda a: a.origen_muestra_id == origen_cultivo
            ) if origen_cultivo else self.env['secadora.analisis.lab']
            salida = confirmados.filtered(
                lambda a: a.origen_muestra_id in origenes_salida
            ) if origenes_salida else self.env['secadora.analisis.lab']

            if entrada:
                record.humedad_entrada = sum(entrada.mapped('humedad')) / len(entrada)
                record.impurezas_entrada = sum(entrada.mapped('impurezas')) / len(entrada)
            else:
                record.humedad_entrada = 0.0
                record.impurezas_entrada = 0.0

            if salida:
                record.humedad_salida = sum(salida.mapped('humedad')) / len(salida)
                record.impurezas_salida = sum(salida.mapped('impurezas')) / len(salida)
            else:
                record.humedad_salida = 0.0
                record.impurezas_salida = 0.0

            if record.humedad_entrada and record.humedad_salida:
                record.diferencia_humedad = record.humedad_entrada - record.humedad_salida
            else:
                record.diferencia_humedad = 0.0

    def action_crear_analisis(self):
        """Crear análisis de laboratorio vinculado a la orden"""
        self.ensure_one()
        vals = {
            'orden_servicio_id': self.id,
            'tercero_id': self.cliente_id.id if self.cliente_id else False,
            'tipo_operacion_id': self.tipo_servicio_id.id if self.tipo_servicio_id else False,
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
        """Ver análisis de laboratorio vinculados a la orden"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Análisis - {self.name}',
            'res_model': 'secadora.analisis.lab',
            'domain': [('orden_servicio_id', '=', self.id)],
            'view_mode': 'list,form',
            'target': 'current',
            'context': {'default_orden_servicio_id': self.id},
        }
