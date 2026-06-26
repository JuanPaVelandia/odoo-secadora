# -*- coding: utf-8 -*-
from odoo import models, fields, api


class HrEppProviderAgreement(models.Model):
    _name = 'hr.epp.provider.agreement'
    _description = 'Acuerdo con Proveedor'
    _order = 'date_start desc'

    name = fields.Char('Referencia', required=True, default='Nuevo')
    configuration_id = fields.Many2one('hr.epp.configuration', string='Configuracion', required=True, ondelete='cascade')
    provider_id = fields.Many2one('res.partner', string='Proveedor', required=True, domain=[('supplier_rank', '>', 0)])

    date_start = fields.Date('Fecha Inicio', required=True, default=fields.Date.today)
    date_end = fields.Date('Fecha Fin')

    state = fields.Selection([
        ('draft', 'Borrador'),
        ('active', 'Activo'),
        ('expired', 'Vencido'),
        ('cancelled', 'Cancelado'),
    ], string='Estado', default='draft', required=True)

    discount_percentage = fields.Float('% Descuento', digits=(5, 2))
    fixed_price = fields.Monetary('Precio Fijo', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    payment_terms_id = fields.Many2one('account.payment.term', string='Terminos de Pago')
    delivery_days = fields.Integer('Dias de Entrega', default=7)
    minimum_quantity = fields.Integer('Cantidad Minima')
    maximum_quantity = fields.Integer('Cantidad Maxima')
    notes = fields.Text('Observaciones')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('hr.epp.provider.agreement') or 'AGR/001'
        return super().create(vals_list)

    def action_activate(self):
        self.write({'state': 'active'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})
