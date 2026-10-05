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
    company_id = fields.Many2one('res.company', string='Empresa', readonly=True)
    res_model = fields.Char(readonly=True)
    res_id = fields.Integer(readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        # Los id se arman como id_origen * 10 + tipo para que sean estables.
        self.env.cr.execute(SQL("""
            CREATE OR REPLACE VIEW %(table)s AS (
                SELECT l.id * 10 + 1 AS id,
                       c.fecha, c.campana_id, c.dueno_id, l.operador_id, c.finca_id,
                       'contrato' AS tipo, c.name AS referencia,
                       CONCAT_WS(' · ', lab.name, 'Lote ' || lote.name) AS descripcion,
                       l.valor AS trabajos, 0.0 AS pagos, l.valor AS saldo,
                       c.company_id, 'finca.contrato' AS res_model, c.id AS res_id
                  FROM finca_contrato_linea l
                  JOIN finca_contrato c ON c.id = l.contrato_id
                  JOIN finca_labor lab ON lab.id = c.labor_id
             LEFT JOIN secadora_lote lote ON lote.id = c.lote_id
                 WHERE c.state = 'confirmado'

             UNION ALL

                SELECT j.id * 10 + 2,
                       j.fecha_hasta, j.campana_id, j.dueno_id, j.operador_id, j.finca_id,
                       'jornal', j.name,
                       CONCAT_WS(' · ', lab.name, j.descripcion),
                       j.total, 0.0, j.total,
                       j.company_id, 'finca.jornal', j.id
                  FROM finca_jornal j
                  JOIN finca_labor lab ON lab.id = j.labor_id
                 WHERE j.state = 'confirmado'

             UNION ALL

                SELECT m.id * 10 + 3,
                       m.fecha, m.campana_id, m.dueno_id, m.operador_id, m.lugar_id,
                       'maquinaria', m.name, m.descripcion,
                       m.valor, 0.0, m.valor,
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
