# -*- coding: utf-8 -*-

from collections import defaultdict

from odoo import models, fields, tools


# Columnas que son razones (numerador ÷ hectáreas): al agrupar no se suman,
# se recalculan como total del grupo ÷ hectáreas de los lotes del grupo.
# Valor: (campo numerador, divisor adicional).
RAZONES = {
    'produccion_ha': ('peso_kg', 1.0),
    'produccion_ha_corregida': ('peso_kg_corregido', 1.0),
    'bultos_ha': ('peso_kg', 62.5),
    'bultos_ha_corregido': ('peso_kg_corregido', 62.5),
}
RECALCULADAS = set(RAZONES) | {'hectareas'}


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
    hectareas = fields.Float(
        string='Hectáreas', readonly=True, digits=(10, 2), aggregator='sum',
        help='Hectáreas del lote (del catálogo, o del nombre si es numérico). '
             'Al agrupar, cada lote cuenta una sola vez aunque tenga varias '
             'mulas: por finca es la suma de las hectáreas de sus lotes.')
    produccion_ha = fields.Float(
        string='Producción (kg/ha)', readonly=True, digits=(12, 2), aggregator='sum',
        help='Peso ÷ hectáreas del lote. Al agrupar es el peso total del grupo '
             '÷ hectáreas de sus lotes (no la suma de las filas).')
    peso_kg_corregido = fields.Float(
        string='Peso Corregido (kg)', readonly=True, digits=(12, 2), aggregator='sum',
        help='Peso ajustado a humedad base 22%: peso × (100 − humedad) / 78 '
             'cuando la humedad medida es menor a 22%. Sin corrección si la '
             'humedad es ≥ 22% o no fue medida.')
    produccion_ha_corregida = fields.Float(
        string='Producción Corregida (kg/ha)', readonly=True, digits=(12, 2), aggregator='sum',
        help='Peso corregido a humedad 22% ÷ hectáreas del lote. Al agrupar, '
             'total corregido del grupo ÷ hectáreas de sus lotes.')
    bultos_ha = fields.Float(
        string='Bultos/ha (62,5 kg)', readonly=True, digits=(12, 2), aggregator='sum',
        help='Peso ÷ 62,5 kg por bulto ÷ hectáreas del lote. Al agrupar, '
             'total del grupo ÷ 62,5 ÷ hectáreas de sus lotes.')
    bultos_ha_corregido = fields.Float(
        string='Bultos/ha Corregido', readonly=True, digits=(12, 2), aggregator='sum',
        help='Peso corregido a humedad 22% ÷ 62,5 kg por bulto ÷ hectáreas del '
             'lote. Al agrupar, total corregido del grupo ÷ 62,5 ÷ hectáreas.')
    humedad = fields.Float(string='Humedad (%)', readonly=True, digits=(5, 2), aggregator='avg')
    impurezas = fields.Float(string='Impurezas (%)', readonly=True, digits=(5, 2), aggregator='avg')
    grano_partido = fields.Float(string='Grano Partido (%)', readonly=True, digits=(5, 2), aggregator='avg')
    temperatura = fields.Float(string='Temperatura (°C)', readonly=True, digits=(5, 2), aggregator='avg')

    # ------------------------------------------------------------------
    # Agregación de razones (kg/ha, bultos/ha, hectáreas)
    #
    # Una razón no se puede sumar: la suma de kg/ha de las filas solo es
    # exacta agrupando por lote (hectáreas constantes). Por finca, o en el
    # total, daba la suma de los rendimientos de los lotes. Aquí se
    # recalcula cada grupo como total ÷ hectáreas, contando las hectáreas
    # de cada lote una sola vez. Se enganchan los dos caminos que usa el
    # cliente web: _read_group (lista, gráfico) y _read_grouping_sets
    # (pivot).
    # ------------------------------------------------------------------

    def _read_group(self, domain, groupby=(), aggregates=(), having=(),
                    offset=0, limit=None, order=None):
        # Si los grupos se ordenan por una razón, el ORDER BY de SQL (sobre
        # la suma) no sirve: se traen todos los grupos, se recalcula, se
        # ordena en Python y recién ahí se aplica el límite.
        ordenar = self._orden_por_razon(order)
        if ordenar:
            offset_sql, limit_sql = 0, None
        else:
            offset_sql, limit_sql = offset, limit
        rows = super()._read_group(
            domain, groupby, aggregates, having=having,
            offset=offset_sql, limit=limit_sql, order=order)
        rows = self._recalcular_razones(
            domain, groupby, aggregates, rows, orden=ordenar)
        if ordenar and (offset or limit):
            rows = rows[offset:(offset + limit) if limit else None]
        return rows

    def _read_grouping_sets(self, domain, grouping_sets, aggregates=(), order=None):
        result = super()._read_grouping_sets(
            domain, grouping_sets, aggregates, order=order)
        return [
            self._recalcular_razones(domain, groupby, aggregates, rows)
            for groupby, rows in zip(grouping_sets, result)
        ]

    def _totales_por_grupo(self, domain, groupby):
        """{clave del grupo: (hectáreas, kg, kg corregidos)}.

        Se agrupa además por lote para que las hectáreas de un lote con
        varias mulas cuenten una sola vez. Los lotes sin hectáreas no
        aportan ni al numerador ni al denominador (sus filas tampoco
        tienen razón calculada).
        """
        groupby = list(groupby)
        por_lote = groupby if 'lote_id' in groupby else groupby + ['lote_id']
        filas = super()._read_group(
            domain, por_lote,
            ['hectareas:max', 'peso_kg:sum', 'peso_kg_corregido:sum'])
        n = len(groupby)
        totales = defaultdict(lambda: [0.0, 0.0, 0.0])
        for fila in filas:
            ha, kg, kg_corr = fila[len(por_lote):]
            if ha and ha > 0:
                t = totales[tuple(fila[:n])]
                t[0] += ha
                t[1] += kg or 0.0
                t[2] += kg_corr or 0.0
        return totales

    @staticmethod
    def _orden_por_razon(order):
        """(campo, desc) si el primer criterio de `order` es una columna
        recalculada; None si no."""
        if not order:
            return None
        primero = order.split(',')[0].strip().split()
        fname = primero[0].split(':')[0]
        if fname not in RECALCULADAS:
            return None
        return fname, len(primero) > 1 and primero[1].lower() == 'desc'

    def _recalcular_razones(self, domain, groupby, aggregates, rows, orden=None):
        aggregates = list(aggregates)
        posiciones = [
            (i, spec.split(':')[0]) for i, spec in enumerate(aggregates)
            if spec.split(':')[0] in RECALCULADAS
        ]
        if not posiciones or not rows:
            return rows
        totales = self._totales_por_grupo(domain, groupby)
        n = len(groupby)
        nuevas = []
        for row in rows:
            row = list(row)
            ha, kg, kg_corr = totales.get(tuple(row[:n]), (0.0, 0.0, 0.0))
            for i, fname in posiciones:
                if fname == 'hectareas':
                    row[n + i] = ha or None
                else:
                    numerador, divisor = RAZONES[fname]
                    base = kg if numerador == 'peso_kg' else kg_corr
                    row[n + i] = base / divisor / ha if ha else None
            nuevas.append(tuple(row))

        if orden:
            fname, desc = orden
            indice = next((n + i for i, f in posiciones if f == fname), None)
            if indice is not None:
                # Los grupos sin valor van al final en ambos sentidos
                nuevas.sort(
                    key=lambda r: r[indice] if r[indice] is not None else 0.0,
                    reverse=desc)
                nuevas.sort(key=lambda r: r[indice] is None)
        return nuevas

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW secadora_produccion_lote_report AS (
                WITH lab_temp AS (
                    -- Último análisis por pesaje con temperatura medida
                    SELECT DISTINCT ON (al.pesaje_id)
                           al.pesaje_id,
                           al.temperatura
                    FROM secadora_analisis_lab al
                    WHERE al.pesaje_id IS NOT NULL
                      AND COALESCE(al.temperatura, 0) > 0
                    ORDER BY al.pesaje_id, al.fecha_hora DESC, al.id DESC
                ),
                lab_gp AS (
                    -- El grano partido se mide en el laboratorio, no en la
                    -- báscula: la columna del pesaje existe pero nunca se
                    -- llena. Se busca aparte de la temperatura porque un
                    -- análisis puede traer uno y no el otro.
                    --
                    -- Los análisis que quedaron sin hacer traen 0; se ignoran
                    -- para que no bajen el promedio del lote.
                    SELECT DISTINCT ON (al.pesaje_id)
                           al.pesaje_id,
                           al.grano_partido
                    FROM secadora_analisis_lab al
                    WHERE al.pesaje_id IS NOT NULL
                      AND COALESCE(al.grano_partido, 0) > 0
                    ORDER BY al.pesaje_id, al.fecha_hora DESC, al.id DESC
                ),
                lab AS (
                    SELECT COALESCE(t.pesaje_id, g.pesaje_id) AS pesaje_id,
                           t.temperatura,
                           g.grano_partido
                    FROM lab_temp t
                    FULL OUTER JOIN lab_gp g ON g.pesaje_id = t.pesaje_id
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
                       ha.hectareas,
                       CASE WHEN ha.hectareas > 0
                            THEN b.peso_kg / ha.hectareas END AS produccion_ha,
                       corr.peso_kg_corregido,
                       CASE WHEN ha.hectareas > 0
                            THEN corr.peso_kg_corregido / ha.hectareas END AS produccion_ha_corregida,
                       CASE WHEN ha.hectareas > 0
                            THEN b.peso_kg / 62.5 / ha.hectareas END AS bultos_ha,
                       CASE WHEN ha.hectareas > 0
                            THEN corr.peso_kg_corregido / 62.5 / ha.hectareas END AS bultos_ha_corregido,
                       -- Un análisis sin hacer deja estos campos en 0: se
                       -- anulan para que no cuenten en el promedio del lote.
                       NULLIF(p.humedad, 0) AS humedad,
                       NULLIF(p.impurezas, 0) AS impurezas,
                       lab.grano_partido,
                       lab.temperatura
                FROM base b
                JOIN secadora_pesaje p ON p.id = b.pesaje_id
                JOIN secadora_lugar lg ON lg.id = b.finca_id
                LEFT JOIN secadora_lote l ON l.id = b.lote_id
                LEFT JOIN LATERAL (
                    -- Hectáreas efectivas: campo del catálogo, o el nombre
                    -- del lote si es numérico (convención de la secadora)
                    SELECT COALESCE(
                        NULLIF(l.hectareas, 0),
                        CASE WHEN TRIM(l.name) ~ '^\\d+([.,]\\d+)?$'
                             THEN REPLACE(TRIM(l.name), ',', '.')::numeric
                        END) AS hectareas
                ) ha ON TRUE
                LEFT JOIN LATERAL (
                    -- Peso ajustado a humedad base 22%: solo cuando la humedad
                    -- medida es menor a 22 (arroz más seco vale más)
                    SELECT CASE WHEN COALESCE(p.humedad, 0) > 0 AND p.humedad < 22
                                THEN b.peso_kg * (100 - p.humedad) / 78.0
                                ELSE b.peso_kg END AS peso_kg_corregido
                ) corr ON TRUE
                LEFT JOIN lab ON lab.pesaje_id = b.pesaje_id
                WHERE p.direccion = 'entrada'
                  AND p.state = 'completado'
                  AND COALESCE(lg.incluir_reporte_produccion, TRUE)
            )
        """)
