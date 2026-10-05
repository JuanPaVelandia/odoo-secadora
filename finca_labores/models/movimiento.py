# -*- coding: utf-8 -*-

from odoo import models, fields, tools
from odoo.tools import SQL


class FincaLaborMovimiento(models.Model):
    """Libro de cada operador: lo trabajado menos lo pagado, por dueño.

    Reemplaza "Resumen total" y "Reporte" del consolidado. Junta las labores
    por contrato, los jornales y los trabajos de maquinaria confirmados (columna
    Trabajos) con los pagos de contabilidad marcados con campaña (columna
    Pagos). Saldo positivo = se le debe al operador.
    """
    _name = 'finca.labor.movimiento'
    _description = 'Movimiento de Labores por Operador'
    _auto = False
    _order = 'fecha, id'
    _rec_name = 'referencia'

    fecha = fields.Date(string='Fecha', readonly=True)
    campana_id = fields.Many2one('finca.campana', string='Campaña', readonly=True)
    dueno_id = fields.Many2one('res.partner', string='Dueño', readonly=True)
    operador_id = fields.Many2one('res.partner', string='Operador', readonly=True)
    finca_id = fields.Many2one('secadora.lugar', string='Finca', readonly=True)
    tipo = fields.Selection([
        ('contrato', 'Labor por contrato'),
        ('jornal', 'Jornal'),
        ('maquinaria', 'Maquinaria'),
        ('pago', 'Pago'),
    ], string='Tipo', readonly=True)
    referencia = fields.Char(string='Referencia', readonly=True)
    descripcion = fields.Char(string='Detalle', readonly=True)
    trabajos = fields.Float(string='Trabajos', digits=(12, 2), readonly=True)
    pagos = fields.Float(string='Pagos', digits=(12, 2), readonly=True)
    saldo = fields.Float(string='Saldo', digits=(12, 2), readonly=True)
    pagador_id = fields.Many2one(
        'res.partner', string='Pagado por', readonly=True,
        help='En los pagos: quién hizo el pago. Puede ser distinto del dueño '
             'cuando un socio paga a nombre de la sociedad.')
    company_id = fields.Many2one('res.company', string='Empresa', readonly=True)
    res_model = fields.Char(readonly=True)
    res_id = fields.Integer(readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        # Los id se arman como id_origen * 10 + tipo para que sean estables.
        # Una labor por contrato da una fila por operador con la suma de sus
        # tramos, como el subtotal por trabajo del "Reporte" de las hojas.
        # El valor de cada operador en un tramo sigue la misma regla que
        # finca.contrato.tramo._valores_por_operador: el monto fijo tal cual y
        # el resto del tramo repartido por partes (1 si no tiene ajuste).
        self.env.cr.execute(SQL("""
            CREATE OR REPLACE VIEW %(table)s AS (
              WITH base AS (
                SELECT rel.tramo_id, rel.operador_id, t.total,
                       NULLIF(a.valor_fijo, 0) AS fijo,
                       COALESCE(a.partes, 1.0) AS partes
                  FROM finca_contrato_tramo_operador_rel rel
                  JOIN finca_contrato_tramo t ON t.id = rel.tramo_id
             LEFT JOIN finca_contrato_tramo_ajuste a
                       ON a.tramo_id = rel.tramo_id AND a.operador_id = rel.operador_id
              ), sumas AS (
                SELECT b.*,
                       SUM(COALESCE(b.fijo, 0)) OVER w AS suma_fijos,
                       SUM(CASE WHEN b.fijo IS NULL THEN b.partes ELSE 0 END) OVER w AS suma_partes
                  FROM base b
                WINDOW w AS (PARTITION BY b.tramo_id)
              ), valores AS (
                SELECT tramo_id, operador_id,
                       CASE WHEN fijo IS NOT NULL THEN fijo
                            WHEN suma_partes > 0 THEN (total - suma_fijos) * partes / suma_partes
                            ELSE 0 END AS valor
                  FROM sumas
              )
                SELECT (c.id::bigint * 1000000 + v.operador_id) * 10 + 1 AS id,
                       c.fecha, c.campana_id, c.dueno_id, v.operador_id, c.finca_id,
                       'contrato' AS tipo, c.name AS referencia,
                       lab.name || ' · Lotes ' || STRING_AGG(
                           COALESCE(lote.name, t.detalle, '?'), ', ' ORDER BY t.sequence, t.id
                       ) AS descripcion,
                       SUM(v.valor) AS trabajos, 0.0 AS pagos, SUM(v.valor) AS saldo,
                       NULL::integer AS pagador_id,
                       c.company_id, 'finca.contrato' AS res_model, c.id AS res_id
                  FROM valores v
                  JOIN finca_contrato_tramo t ON t.id = v.tramo_id
                  JOIN finca_contrato c ON c.id = t.contrato_id
                  JOIN finca_labor lab ON lab.id = c.labor_id
             LEFT JOIN secadora_lote lote ON lote.id = t.lote_id
                 WHERE c.state = 'confirmado'
              GROUP BY c.id, v.operador_id, lab.name

             UNION ALL

                SELECT j.id * 10 + 2,
                       j.fecha_hasta, j.campana_id, j.dueno_id, j.operador_id, j.finca_id,
                       'jornal', j.name,
                       CONCAT_WS(' · ', lab.name, j.descripcion),
                       j.total, 0.0, j.total, NULL,
                       j.company_id, 'finca.jornal', j.id
                  FROM finca_jornal j
                  JOIN finca_labor lab ON lab.id = j.labor_id
                 WHERE j.state = 'confirmado'

             UNION ALL

                SELECT m.id * 10 + 3,
                       m.fecha, m.campana_id, m.dueno_id, m.operador_id, m.lugar_id,
                       'maquinaria', m.name, m.descripcion,
                       m.valor, 0.0, m.valor, NULL,
                       m.company_id, 'finca.maquinaria.trabajo', m.id
                  FROM finca_maquinaria_trabajo m
                 WHERE m.state = 'confirmado'

             UNION ALL

                -- amount_company_currency_signed es negativo en los pagos
                -- salientes: un pago al operador suma en Pagos y una
                -- devolución del operador resta.
                SELECT p.id * 10 + 4,
                       p.date, p.finca_campana_id, p.finca_dueno_id, p.partner_id, NULL,
                       'pago', p.name, p.memo,
                       0.0, -p.amount_company_currency_signed, p.amount_company_currency_signed,
                       p.finca_pagador_id,
                       p.company_id, 'account.payment', p.id
                  FROM account_payment p
                 WHERE p.finca_campana_id IS NOT NULL
                   AND p.state IN ('in_process', 'paid')
            )
        """, table=SQL.identifier(self._table)))

    def action_abrir_origen(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.res_model,
            'res_id': self.res_id,
            'view_mode': 'form',
            'target': 'current',
        }


class FincaLaborSocio(models.Model):
    """Los movimientos repartidos entre los socios de cada dueño.

    Un dueño sin socios aparece al 100 %; una sociedad (La Alianza, La
    Fortuna) se reparte según finca.socio. Sirve para ver cuánto le cuesta a
    cada socio; el saldo con el operador sigue siendo con la sociedad.
    """
    _name = 'finca.labor.socio'
    _description = 'Costo de Labores por Socio'
    _auto = False
    _order = 'fecha, id'

    fecha = fields.Date(string='Fecha', readonly=True)
    campana_id = fields.Many2one('finca.campana', string='Campaña', readonly=True)
    socio_id = fields.Many2one('res.partner', string='Socio', readonly=True)
    dueno_id = fields.Many2one('res.partner', string='Dueño', readonly=True)
    porcentaje = fields.Float(string='Participación (%)', readonly=True)
    operador_id = fields.Many2one('res.partner', string='Operador', readonly=True)
    finca_id = fields.Many2one('secadora.lugar', string='Finca', readonly=True)
    tipo = fields.Selection(
        lambda self: self.env['finca.labor.movimiento']._fields['tipo'].selection,
        string='Tipo', readonly=True)
    referencia = fields.Char(string='Referencia', readonly=True)
    trabajos = fields.Float(string='Trabajos', digits=(12, 2), readonly=True)
    pagos = fields.Float(string='Pagos', digits=(12, 2), readonly=True)
    saldo = fields.Float(string='Saldo', digits=(12, 2), readonly=True)
    aportes = fields.Float(
        string='Aportes', digits=(12, 2), readonly=True,
        help='Pagos que el socio hizo de su bolsillo a nombre de la sociedad.')
    cuenta_socios = fields.Float(
        string='Cuenta entre socios', digits=(12, 2), readonly=True,
        help='Aportes menos la parte de los pagos de la sociedad que le toca al '
             'socio. Positivo: la sociedad le debe al socio.')
    company_id = fields.Many2one('res.company', string='Empresa', readonly=True)

    def init(self):
        # Se crea después de finca_labor_movimiento (mismo archivo, clase
        # posterior); drop_view_if_exists usa CASCADE, así que al recrear el
        # movimiento esta vista se vuelve a crear aquí.
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(SQL("""
            CREATE OR REPLACE VIEW %(table)s AS (
                -- ROW_NUMBER y no m.id * k + s.id: los id de contrato ya son
                -- grandes y multiplicarlos pasaría el límite de enteros del
                -- navegador. Es una vista de consulta, no se enlaza por id.
                SELECT ROW_NUMBER() OVER (ORDER BY m.id, s.id) AS id,
                       m.fecha, m.campana_id,
                       COALESCE(s.socio_id, m.dueno_id) AS socio_id,
                       m.dueno_id,
                       COALESCE(s.porcentaje, 100.0) AS porcentaje,
                       m.operador_id, m.finca_id, m.tipo, m.referencia,
                       m.trabajos * COALESCE(s.porcentaje, 100.0) / 100.0 AS trabajos,
                       m.pagos * COALESCE(s.porcentaje, 100.0) / 100.0 AS pagos,
                       m.saldo * COALESCE(s.porcentaje, 100.0) / 100.0 AS saldo,
                       CASE WHEN s.socio_id = m.pagador_id THEN m.pagos ELSE 0.0 END AS aportes,
                       CASE WHEN s.id IS NULL THEN 0.0
                            ELSE (CASE WHEN s.socio_id = m.pagador_id THEN m.pagos ELSE 0.0 END)
                                 - m.pagos * s.porcentaje / 100.0
                       END AS cuenta_socios,
                       m.company_id
                  FROM finca_labor_movimiento m
             LEFT JOIN finca_socio s ON s.sociedad_id = m.dueno_id
            )
        """, table=SQL.identifier(self._table)))
