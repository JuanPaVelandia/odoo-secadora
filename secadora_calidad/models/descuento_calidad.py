# -*- coding: utf-8 -*-

from odoo import models, fields


class DescuentoCalidad(models.Model):
    _name = 'secadora.descuento.calidad'
    _description = 'Regla de Descuento por Calidad'
    _order = 'sequence, id'

    name = fields.Char(string='Nombre', required=True)
    sequence = fields.Integer(string='Secuencia', default=10)
    active = fields.Boolean(string='Activo', default=True)

    parametro = fields.Selection([
        ('humedad', 'Humedad (%)'),
        ('impurezas', 'Impurezas (%)'),
        ('grano_partido', 'Grano Partido (%)'),
        ('grano_partido_verde', 'Grano Partido Verde (%)'),
        ('grano_rojo', 'Grano Rojo (%)'),
        ('infestacion', 'Infestación'),
        ('cascarilla_pct', 'Cascarilla (%)'),
        ('harina_pct', 'Harina (%)'),
        ('grano_yesado_pct', 'Grano Yesado (%)'),
        ('grano_ambarino_pct', 'Grano Ambarino (%)'),
        ('grano_con_dano_pct', 'Grano con Daño (%)'),
    ], string='Parámetro a Evaluar', required=True)

    umbral = fields.Float(
        string='Umbral Máximo Permitido',
        digits=(5, 2),
        required=True,
        help='Valor máximo permitido antes de aplicar descuento'
    )

    modo_descuento = fields.Selection([
        ('porcentaje_exceso', 'Porcentaje del Exceso'),
        ('factor_por_punto', 'Factor por Punto de Exceso'),
    ], string='Modo de Descuento', required=True, default='porcentaje_exceso')

    factor = fields.Float(
        string='Factor',
        digits=(8, 4),
        required=True,
        default=1.0,
        help='Factor multiplicador del descuento'
    )

    tipo_operacion_ids = fields.Many2many(
        'secadora.tipo.operacion',
        'descuento_calidad_tipo_operacion_rel',
        'descuento_id',
        'tipo_operacion_id',
        string='Tipos de Operación',
        help='Tipos a los que aplica esta regla (vacío = todos)'
    )

    def calcular_descuento(self, analisis):
        """Calcular el descuento en kg para un análisis dado.

        Args:
            analisis: record de secadora.analisis.lab

        Returns:
            float: kg descontados
        """
        self.ensure_one()
        valor = getattr(analisis, self.parametro, 0.0) or 0.0
        if valor <= self.umbral:
            return 0.0

        exceso = valor - self.umbral
        peso_neto = analisis.pesaje_id.peso_neto if analisis.pesaje_id else 0.0

        if self.modo_descuento == 'porcentaje_exceso':
            return peso_neto * (exceso / 100.0) * self.factor
        elif self.modo_descuento == 'factor_por_punto':
            return exceso * self.factor
        return 0.0
