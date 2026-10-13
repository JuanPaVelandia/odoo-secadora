# -*- coding: utf-8 -*-

from odoo import fields, models, tools
from odoo.tools import SQL


class AcpmCompra(models.Model):
    """Resumen de ACPM: una fila por línea de factura marcada como ACPM. Los
    galones y el valor van en negativo en las notas crédito."""
    _name = 'secadora.acpm.compra'
    _description = 'Compra de ACPM'
    _auto = False
    _order = 'fecha desc, id desc'
    _rec_name = 'factura'

    fecha = fields.Date(string='Fecha', readonly=True)
    company_id = fields.Many2one('res.company', string='Empresa', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Proveedor', readonly=True)
    move_id = fields.Many2one('account.move', string='Factura', readonly=True)
    factura = fields.Char(string='Número', readonly=True)
    descripcion = fields.Char(string='Descripción', readonly=True)
    account_id = fields.Many2one('account.account', string='Cuenta', readonly=True)
    lugar_id = fields.Many2one('secadora.lugar', string='Finca', readonly=True)
    campana_id = fields.Many2one('finca.campana', string='Campaña', readonly=True)
    galones = fields.Float(string='Galones', digits=(12, 2), readonly=True)
    valor = fields.Float(string='Valor', digits=(14, 0), readonly=True)
    precio_galon = fields.Float(
        string='Precio por galón', digits=(12, 0), readonly=True, aggregator='avg')
    estado = fields.Selection([
        ('draft', 'Borrador'),
        ('posted', 'Publicada'),
        ('cancel', 'Anulada'),
    ], string='Estado factura', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(SQL("""
            CREATE OR REPLACE VIEW %(table)s AS (
                SELECT aml.id,
                       COALESCE(am.invoice_date, am.date) AS fecha,
                       aml.company_id,
                       am.partner_id,
                       am.id AS move_id,
                       am.name AS factura,
                       aml.name AS descripcion,
                       aml.account_id,
                       aml.acpm_lugar_id AS lugar_id,
                       aml.acpm_campana_id AS campana_id,
                       aml.acpm_galones AS galones,
                       aml.acpm_valor AS valor,
                       CASE WHEN COALESCE(aml.acpm_galones, 0) <> 0
                            THEN aml.acpm_valor / aml.acpm_galones END AS precio_galon,
                       am.state AS estado
                  FROM account_move_line aml
                  JOIN account_move am ON am.id = aml.move_id
                 WHERE aml.acpm_es
                   AND am.move_type IN ('in_invoice', 'in_refund')
            )
        """, table=SQL.identifier(self._table)))

    def action_abrir_factura(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'views': [(False, 'form')],
            'target': 'current',
        }
