# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError


class OrdenLote(models.Model):
    _name = 'secadora.orden.lote'
    _description = 'Lote dentro de una Orden de Servicio'
    _order = 'orden_id, sequence, id'

    name = fields.Char(
        string='Nombre del Lote',
        compute='_compute_name',
        store=True,
        help='Nombre automático: Lote 1, Lote 2, etc.'
    )

    orden_id = fields.Many2one(
        'secadora.orden.servicio',
        string='Orden de Servicio',
        required=True,
        ondelete='cascade',
        index=True,
        help='Orden de servicio a la que pertenece este lote'
    )

    sequence = fields.Integer(
        string='Secuencia',
        default=10,
        help='Orden de los lotes dentro de la orden'
    )

    tipo_operacion_id = fields.Many2one(
        'secadora.tipo.operacion',
        string='Tipo de Servicio',
        required=True,
        domain=[('es_servicio', '=', True)],
        help='Tipo de servicio para este lote (Secamiento, Prelimpieza, etc.)'
    )

    # Relación con pesajes
    pesaje_ids = fields.One2many(
        'secadora.pesaje',
        'lote_id',
        string='Pesajes',
        help='Todos los pesajes (entrada y salida) de este lote'
    )

    pesaje_entrada_ids = fields.One2many(
        'secadora.pesaje',
        'lote_id',
        string='Pesajes de Entrada',
        domain=[('direccion', '=', 'entrada')],
        help='Pesajes de entrada de este lote'
    )

    pesaje_salida_ids = fields.One2many(
        'secadora.pesaje',
        'lote_id',
        string='Pesajes de Salida',
        domain=[('direccion', '=', 'salida')],
        help='Pesajes de salida de este lote'
    )

    # Campos computados de pesos
    peso_entrada = fields.Float(
        string='Peso Entrada (kg)',
        compute='_compute_pesos',
        store=True,
        digits=(12, 2),
        help='Suma de todos los pesos netos de entrada'
    )

    peso_salida = fields.Float(
        string='Peso Salida (kg)',
        compute='_compute_pesos',
        store=True,
        digits=(12, 2),
        help='Suma de todos los pesos netos de salida'
    )

    merma = fields.Float(
        string='Merma (kg)',
        compute='_compute_pesos',
        store=True,
        digits=(12, 2),
        help='Diferencia entre peso entrada y peso salida'
    )

    merma_porcentaje = fields.Float(
        string='Merma (%)',
        compute='_compute_pesos',
        store=True,
        digits=(5, 2),
        help='Porcentaje de merma sobre el peso de entrada'
    )

    # Campos informativos
    observaciones = fields.Text(
        string='Observaciones',
        help='Notas específicas de este lote (variedad, instrucciones, etc.)'
    )

    # ==================== MÉTODOS COMPUTADOS ====================

    @api.depends('orden_id', 'sequence')
    def _compute_name(self):
        """Generar nombre automático: Lote 1, Lote 2, etc."""
        for record in self:
            if record.orden_id:
                # Contar cuántos lotes hay en la misma orden (solo registros guardados)
                if record.id and isinstance(record.id, int):
                    # Registro ya guardado: contar lotes anteriores por ID
                    lotes_anteriores = self.search([
                        ('orden_id', '=', record.orden_id.id),
                        ('id', '<', record.id)
                    ], order='sequence, id')
                    numero = len(lotes_anteriores) + 1
                else:
                    # Registro nuevo (aún no guardado): contar todos los lotes existentes + 1
                    lotes_existentes = self.search([
                        ('orden_id', '=', record.orden_id.id)
                    ])
                    numero = len(lotes_existentes) + 1
                record.name = f'Lote {numero}'
            else:
                record.name = 'Nuevo Lote'

    @api.depends('pesaje_entrada_ids.peso_neto', 'pesaje_salida_ids.peso_neto')
    def _compute_pesos(self):
        """Calcular pesos y merma del lote"""
        for record in self:
            peso_entrada = sum(record.pesaje_entrada_ids.mapped('peso_neto'))
            peso_salida = sum(record.pesaje_salida_ids.mapped('peso_neto'))

            record.peso_entrada = peso_entrada
            record.peso_salida = peso_salida
            record.merma = peso_entrada - peso_salida

            if peso_entrada > 0:
                record.merma_porcentaje = (record.merma / peso_entrada) * 100
            else:
                record.merma_porcentaje = 0.0

    # ==================== MÉTODOS DE ACCIÓN ====================

    def action_crear_pesaje_entrada(self):
        """Crear un pesaje de entrada para este lote"""
        self.ensure_one()

        pesaje = self.env['secadora.pesaje'].create({
            'lote_id': self.id,
            'orden_servicio_id': self.orden_id.id,
            'tipo_operacion_id': self.tipo_operacion_id.id,
            'direccion': 'entrada',
            'tercero_id': self.orden_id.cliente_id.id if self.orden_id.cliente_id else False,
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'secadora.pesaje',
            'res_id': pesaje.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_crear_pesaje_salida(self):
        """Crear un pesaje de salida para este lote"""
        self.ensure_one()

        pesaje = self.env['secadora.pesaje'].create({
            'lote_id': self.id,
            'orden_servicio_id': self.orden_id.id,
            'tipo_operacion_id': self.tipo_operacion_id.id,
            'direccion': 'salida',
            'tercero_id': self.orden_id.cliente_id.id if self.orden_id.cliente_id else False,
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'secadora.pesaje',
            'res_id': pesaje.id,
            'view_mode': 'form',
            'target': 'current',
        }
