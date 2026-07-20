# -*- coding: utf-8 -*-

from odoo import models, fields, tools


class ProduccionLoteReport(models.Model):
    """Vista SQL de producción (entradas) por Finca y Lote.

    Una fila por (pesaje de entrada completado, finca, lote):
    - Pesaje sin líneas de distribución: una fila con su origen/lote y peso neto.
    - Pesaje con carga mixta: una fila por línea, peso prorrateado por bultos.

    Las métricas de calidad vienen NULLIF(0): un 0 significa "no medido" y no
    debe diluir los promedios del pivot. La temperatura sale del último
    análisis de laboratorio del pesaje que la tenga registrada.
    """
    _name = 'secadora.produccion.lote.report'
    _description = 'Producción por Finca y Lote'
    _auto = False
    _order = 'fecha desc, id desc'

    pesaje_id = fields.Many2one('secadora.pesaje', string='Pesaje', readonly=True)
    name = fields.Char(string='Número', readonly=True)
    fecha = fields.Date(string='Fecha', readonly=True)
    finca_id = fields.Many2one('secadora.lugar', string='Finca', readonly=True)
    lote_id = fields.Many2one('secadora.lote', string='Lote', readonly=True)
    tercero_id = fields.Many2one('res.partner', string='Tercero', readonly=True)
    variedad_id = fields.Many2one('secadora.variedad.arroz', string='Variedad', readonly=True)
    company_id = fields.Many2one('res.company', string='Empresa', readonly=True)
    empresa_arroz_id = fields.Many2one('res.company', string='Empresa del Arroz', readonly=True)
    placa = fields.Char(string='Placa', readonly=True)
    bultos = fields.Integer(string='Bultos', readonly=True, aggregator='sum')
    peso_kg = fields.Float(string='Peso (kg)', readonly=True, digits=(12, 2), aggregator='sum')
    humedad = fields.Float(string='Humedad (%)', readonly=True, digits=(5, 2), aggregator='avg')
    impurezas = fields.Float(string='Impurezas (%)', readonly=True, digits=(5, 2), aggregator='avg')
    grano_partido = fields.Float(string='Grano Partido (%)', readonly=True, digits=(5, 2), aggregator='avg')
    temperatura = fields.Float(string='Temperatura (°C)', readonly=True, digits=(5, 2), aggregator='avg')

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW secadora_produccion_lote_report AS (
                WITH lab AS (
                    -- Último análisis de laboratorio por pesaje con temperatura medida
                    SELECT DISTINCT ON (al.pesaje_id)
                           al.pesaje_id,
                           al.temperatura
                    FROM secadora_analisis_lab al
                    WHERE al.pesaje_id IS NOT NULL
                      AND COALESCE(al.temperatura, 0) > 0
                    ORDER BY al.pesaje_id, al.fecha_hora DESC, al.id DESC
                ),
                tot AS (
                    SELECT pesaje_id, SUM(bultos) AS total_bultos
                    FROM secadora_pesaje_distribucion
                    GROUP BY pesaje_id
                ),
                base AS (
                    -- Caso simple: pesaje sin líneas de distribución
                    SELECT p.id AS pesaje_id,
                           p.origen_id AS finca_id,
                           p.lote_id,
                           COALESCE(p.bultos, 0) AS bultos,
                           p.peso_neto AS peso_kg
                    FROM secadora_pesaje p
                    WHERE NOT EXISTS (
                        SELECT 1 FROM secadora_pesaje_distribucion d
                        WHERE d.pesaje_id = p.id
                    )
                    UNION ALL
                    -- Carga mixta: una fila por línea, peso prorrateado por bultos
                    SELECT d.pesaje_id,
                           d.finca_id,
                           d.lote_id,
                           d.bultos,
                           CASE WHEN t.total_bultos > 0
                                THEN p.peso_neto * d.bultos::numeric / t.total_bultos
                                ELSE 0 END AS peso_kg
                    FROM secadora_pesaje_distribucion d
                    JOIN secadora_pesaje p ON p.id = d.pesaje_id
                    JOIN tot t ON t.pesaje_id = d.pesaje_id
                )
                SELECT ROW_NUMBER() OVER (ORDER BY b.pesaje_id, b.lote_id) AS id,
                       b.pesaje_id,
                       p.name,
                       p.fecha,
                       b.finca_id,
                       b.lote_id,
                       p.tercero_id,
                       p.variedad_id,
                       p.company_id,
                       p.empresa_arroz_id,
                       p.placa_texto AS placa,
                       b.bultos,
                       b.peso_kg,
                       NULLIF(p.humedad, 0) AS humedad,
                       NULLIF(p.impurezas, 0) AS impurezas,
                       NULLIF(p.grano_partido, 0) AS grano_partido,
                       lab.temperatura
                FROM base b
                JOIN secadora_pesaje p ON p.id = b.pesaje_id
                LEFT JOIN lab ON lab.pesaje_id = b.pesaje_id
                WHERE p.direccion = 'entrada'
                  AND p.state = 'completado'
            )
        """)
