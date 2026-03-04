# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class SecadoraLiquidacionLinea(models.Model):
    _name = 'secadora.liquidacion.linea'
    _description = 'Línea de Liquidación'
    _order = 'fecha_pesaje, id'

    _sql_constraints = [
        ('pesaje_unique', 'UNIQUE(pesaje_id)',
         'Un pesaje solo puede estar en una liquidación.'),
    ]

    liquidacion_id = fields.Many2one(
        'secadora.liquidacion',
        string='Liquidación',
        required=True,
        ondelete='cascade',
        index=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        related='liquidacion_id.company_id',
        store=True,
    )
    pesaje_id = fields.Many2one(
        'secadora.pesaje',
        string='Pesaje',
        required=True,
        index=True,
    )
    fecha_pesaje = fields.Date(
        string='Fecha',
        related='pesaje_id.fecha',
        store=True,
    )
    variedad_id = fields.Many2one(
        'secadora.variedad.arroz',
        string='Variedad',
        related='pesaje_id.variedad_id',
        store=True,
    )
    peso_neto = fields.Float(
        string='Peso Neto (kg)',
        related='pesaje_id.peso_neto',
        store=True,
        digits=(12, 2),
    )
    analisis_id = fields.Many2one(
        'secadora.analisis.lab',
        string='Análisis',
        compute='_compute_analisis_id',
        store=True,
    )
    peso_comercial = fields.Float(
        string='Peso Comercial (kg)',
        digits=(12, 2),
    )
    humedad = fields.Float(
        string='Humedad (%)',
        related='analisis_id.humedad',
        digits=(5, 2),
    )
    precio = fields.Float(
        string='Precio ($/kg)',
        digits=(12, 2),
    )
    subtotal = fields.Float(
        string='Subtotal ($)',
        compute='_compute_subtotal',
        store=True,
        digits=(12, 2),
    )

    @api.constrains('pesaje_id', 'liquidacion_id')
    def _check_pesaje_agricultor(self):
        for rec in self:
            if rec.pesaje_id and rec.liquidacion_id.tercero_id:
                if rec.pesaje_id.tercero_id != rec.liquidacion_id.tercero_id:
                    raise ValidationError(
                        'El pesaje %s pertenece a %s, pero la liquidación es de %s.' % (
                            rec.pesaje_id.name,
                            rec.pesaje_id.tercero_id.name,
                            rec.liquidacion_id.tercero_id.name,
                        )
                    )

    @api.depends('pesaje_id')
    def _compute_analisis_id(self):
        AnalisisLab = self.env['secadora.analisis.lab']
        for rec in self:
            if rec.pesaje_id:
                analisis = AnalisisLab.search([
                    ('pesaje_id', '=', rec.pesaje_id.id),
                    ('state', '=', 'confirmado'),
                ], limit=1, order='id desc')
                rec.analisis_id = analisis
            else:
                rec.analisis_id = False

    @api.depends('peso_comercial', 'precio')
    def _compute_subtotal(self):
        for rec in self:
            rec.subtotal = rec.peso_comercial * rec.precio

    @api.onchange('pesaje_id')
    def _onchange_pesaje_id(self):
        if self.pesaje_id:
            # Verificar duplicado en la misma liquidación
            otras_lineas = self.liquidacion_id.linea_ids - self
            if self.pesaje_id in otras_lineas.mapped('pesaje_id'):
                warning = {
                    'title': 'Pesaje duplicado',
                    'message': 'El pesaje %s ya está en esta liquidación.' % self.pesaje_id.name,
                }
                self.pesaje_id = False
                return {'warning': warning}
            # Buscar análisis confirmado
            analisis = self.env['secadora.analisis.lab'].search([
                ('pesaje_id', '=', self.pesaje_id.id),
                ('state', '=', 'confirmado'),
            ], limit=1, order='id desc')
            if analisis and analisis.peso_comercial > 0:
                self.peso_comercial = analisis.peso_comercial
            else:
                self.peso_comercial = self.pesaje_id.peso_neto
            # Prioridad de precio: agricultor > catálogo > pesaje
            tercero = self.liquidacion_id.tercero_id or self.pesaje_id.tercero_id
            if tercero and tercero.precio_compra_kg > 0:
                self.precio = tercero.precio_compra_kg
            else:
                PrecioCompra = self.env['secadora.precio.compra']
                precio_catalogo = PrecioCompra._obtener_precio(
                    self.pesaje_id.variedad_id.id,
                    self.pesaje_id.fecha,
                    self.liquidacion_id.company_id.id,
                )
                self.precio = precio_catalogo if precio_catalogo else self.pesaje_id.precio

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        # Actualizar liquidacion_id en los pesajes
        for rec in records:
            if rec.pesaje_id and rec.liquidacion_id:
                rec.pesaje_id.sudo().write({'liquidacion_id': rec.liquidacion_id.id})
        return records

    def unlink(self):
        # Limpiar liquidacion_id de los pesajes antes de eliminar
        pesajes = self.mapped('pesaje_id')
        result = super().unlink()
        pesajes.sudo().write({'liquidacion_id': False})
        return result
