# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class SecadoraPesajeDistribucion(models.Model):
    _name = 'secadora.pesaje.distribucion'
    _description = 'Distribución de carga por Finca/Lote'

    _pesaje_finca_lote_unique = models.Constraint(
        'UNIQUE(pesaje_id, finca_id, lote_id)',
        'Ya existe una línea para ese lote en este pesaje. Ajusta los bultos de la línea existente.',
    )

    pesaje_id = fields.Many2one(
        'secadora.pesaje',
        string='Pesaje',
        required=True,
        ondelete='cascade',
        index=True,
    )
    finca_id = fields.Many2one(
        'secadora.lugar',
        string='Finca',
        required=True,
        domain=[('tipo', '=', 'finca')],
    )
    lote_id = fields.Many2one(
        'secadora.lote',
        string='Lote',
        required=True,
        domain="[('finca_id', '=', finca_id)]",
    )
    bultos = fields.Integer(
        string='Bultos',
        required=True,
        help='Bultos de este lote según remisión del agricultor',
    )
    peso_kg = fields.Float(
        string='Peso (kg)',
        compute='_compute_peso_kg',
        store=True,
        digits=(12, 2),
        help='Peso neto del pesaje prorrateado por bultos',
    )
    porcentaje = fields.Float(
        string='%',
        compute='_compute_peso_kg',
        store=True,
        digits=(5, 2),
    )

    @api.depends('bultos', 'pesaje_id.peso_neto', 'pesaje_id.distribucion_ids.bultos')
    def _compute_peso_kg(self):
        for record in self:
            total_bultos = sum(record.pesaje_id.distribucion_ids.mapped('bultos'))
            if total_bultos > 0:
                proporcion = record.bultos / total_bultos
                record.peso_kg = record.pesaje_id.peso_neto * proporcion
                record.porcentaje = proporcion * 100
            else:
                record.peso_kg = 0
                record.porcentaje = 0

    @api.constrains('bultos')
    def _check_bultos(self):
        for record in self:
            if record.bultos <= 0:
                raise ValidationError('Los bultos de cada línea de distribución deben ser mayores a 0.')
        # Revalidar el cuadre contra el total del pesaje (cubre ediciones
        # directas de líneas sin pasar por el write del pesaje)
        self.mapped('pesaje_id')._check_distribucion_bultos()

    @api.onchange('finca_id')
    def _onchange_finca_id(self):
        if self.lote_id and self.lote_id.finca_id != self.finca_id:
            self.lote_id = False
