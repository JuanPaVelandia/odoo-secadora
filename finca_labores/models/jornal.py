# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


class FincaJornal(models.Model):
    """Trabajo pagado por tiempo: días, meses o unidades a un valor fijo.

    Equivale a las pestañas "Por jornales" y "Liquidador_jornales", que en las
    hojas no llegaban al consolidado.
    """
    _name = 'finca.jornal'
    _description = 'Jornal de Finca'
    _inherit = ['mail.thread']
    _order = 'fecha_hasta desc, id desc'

    name = fields.Char(
        string='Número',
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: 'Nuevo',
    )
    campana_id = fields.Many2one(
        'finca.campana',
        string='Campaña',
        required=True,
        index=True,
        default=lambda self: self.env['finca.campana']._get_campana(),
    )
    finca_id = fields.Many2one(
        'secadora.lugar',
        string='Finca',
        required=True,
        index=True,
        domain=[('tipo', '=', 'finca')],
    )
    dueno_id = fields.Many2one(
        'res.partner',
        string='Dueño',
        compute='_compute_dueno_id',
        store=True,
        readonly=False,
        index=True,
    )
    fecha_desde = fields.Date(string='Desde', required=True, default=fields.Date.context_today)
    fecha_hasta = fields.Date(string='Hasta', required=True, default=fields.Date.context_today)
    operador_id = fields.Many2one(
        'res.partner',
        string='Persona',
        required=True,
        index=True,
    )
    labor_id = fields.Many2one(
        'finca.labor',
        string='Trabajo',
        required=True,
        domain=[('tipo', '=', 'jornal')],
    )
    unidad = fields.Selection(related='labor_id.unidad', string='Unidad')
    cantidad = fields.Float(string='Cantidad', digits=(12, 2), default=1.0)
    valor_unitario = fields.Float(
        string='Valor por unidad',
        digits=(12, 2),
        compute='_compute_valor_unitario',
        store=True,
        readonly=False,
    )
    total = fields.Float(
        string='Total',
        digits=(12, 2),
        compute='_compute_total',
        store=True,
    )
    descripcion = fields.Char(string='Detalle')
    state = fields.Selection([
        ('borrador', 'Borrador'),
        ('confirmado', 'Confirmado'),
        ('cancelado', 'Cancelado'),
    ], string='Estado', default='borrador', required=True, index=True, tracking=True)
    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('finca.jornal') or 'Nuevo'
        return super().create(vals_list)

    @api.depends('finca_id')
    def _compute_dueno_id(self):
        for rec in self:
            rec.dueno_id = rec.finca_id.dueno_id

    @api.depends('labor_id')
    def _compute_valor_unitario(self):
        for rec in self:
            rec.valor_unitario = rec.labor_id.valor_unitario

    @api.depends('cantidad', 'valor_unitario')
    def _compute_total(self):
        for rec in self:
            rec.total = rec.cantidad * rec.valor_unitario

    @api.constrains('fecha_desde', 'fecha_hasta')
    def _check_fechas(self):
        for rec in self:
            if rec.fecha_hasta < rec.fecha_desde:
                raise ValidationError('La fecha "Hasta" no puede ser anterior a "Desde".')

    def action_confirmar(self):
        for rec in self.filtered(lambda r: r.state == 'borrador'):
            if not rec.total:
                raise UserError('El jornal %s no tiene valor.' % rec.name)
            if not rec.dueno_id:
                raise UserError(
                    'El jornal %s no tiene dueño. Asigne el dueño en la finca %s.'
                    % (rec.name, rec.finca_id.name))
            rec.operador_id._marcar_operador_finca()
            rec.state = 'confirmado'

    def action_borrador(self):
        self.write({'state': 'borrador'})

    def action_cancelar(self):
        self.write({'state': 'cancelado'})
