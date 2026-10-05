# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


class FincaContrato(models.Model):
    """Una labor por contrato en un lote: cantidad x tarifa, repartida entre
    los operadores que la hicieron.

    Equivale a una columna de un bloque de la pestaña "Por contrato" de las
    hojas de finca (Lote / Trabajo / N.º de has / Valor x ha / Entre cuántos).
    """
    _name = 'finca.contrato'
    _description = 'Labor por Contrato'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'fecha desc, name desc'

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
        tracking=True,
    )
    fecha = fields.Date(
        string='Fecha',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    finca_id = fields.Many2one(
        'secadora.lugar',
        string='Finca',
        required=True,
        index=True,
        domain=[('tipo', '=', 'finca')],
        tracking=True,
    )
    dueno_id = fields.Many2one(
        'res.partner',
        string='Dueño',
        compute='_compute_dueno_id',
        store=True,
        readonly=False,
        index=True,
        tracking=True,
        help='Se toma de la finca; se puede cambiar si esta labor la paga otro.',
    )
    lote_id = fields.Many2one(
        'secadora.lote',
        string='Lote',
        domain="[('finca_id', '=', finca_id)]",
        tracking=True,
    )
    labor_id = fields.Many2one(
        'finca.labor',
        string='Labor',
        required=True,
        domain=[('tipo', '=', 'contrato')],
        tracking=True,
    )
    unidad = fields.Selection(related='labor_id.unidad', string='Unidad')
    cantidad = fields.Float(
        string='Cantidad',
        digits=(12, 2),
        compute='_compute_cantidad',
        store=True,
        readonly=False,
        tracking=True,
        help='Hectáreas o bultos trabajados. Si la labor es por hectárea se '
             'propone el área del lote.',
    )
    tarifa = fields.Float(
        string='Tarifa',
        digits=(12, 2),
        compute='_compute_tarifa',
        store=True,
        readonly=False,
        tracking=True,
    )
    total = fields.Float(
        string='Total',
        digits=(12, 2),
        compute='_compute_total',
        store=True,
    )
    linea_ids = fields.One2many(
        'finca.contrato.linea',
        'contrato_id',
        string='Operadores',
        copy=True,
    )
    cantidad_operadores = fields.Integer(
        string='Entre cuántos',
        compute='_compute_total',
        store=True,
    )
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
    observaciones = fields.Text(string='Observaciones')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('finca.contrato') or 'Nuevo'
        return super().create(vals_list)

    @api.depends('finca_id')
    def _compute_dueno_id(self):
        for rec in self:
            rec.dueno_id = rec.finca_id.dueno_id

    @api.depends('lote_id', 'labor_id')
    def _compute_cantidad(self):
        for rec in self:
            if rec.labor_id.unidad == 'ha' and rec.lote_id.hectareas:
                rec.cantidad = rec.lote_id.hectareas
            else:
                rec.cantidad = rec.cantidad or 0.0

    @api.depends('labor_id')
    def _compute_tarifa(self):
        for rec in self:
            rec.tarifa = rec.labor_id.valor_unitario

    @api.depends('cantidad', 'tarifa', 'linea_ids')
    def _compute_total(self):
        for rec in self:
            rec.total = rec.cantidad * rec.tarifa
            rec.cantidad_operadores = len(rec.linea_ids)

    @api.onchange('finca_id')
    def _onchange_finca_id(self):
        if self.lote_id and self.lote_id.finca_id != self.finca_id:
            self.lote_id = False

    def action_confirmar(self):
        for rec in self:
            if not rec.linea_ids:
                raise UserError('Agregue al menos un operador antes de confirmar %s.' % rec.name)
            if not rec.total:
                raise UserError('La labor %s no tiene valor (cantidad x tarifa = 0).' % rec.name)
            if not rec.dueno_id:
                raise UserError(
                    'La labor %s no tiene dueño. Asigne el dueño en la finca %s o en la labor.'
                    % (rec.name, rec.finca_id.name))
            rec.linea_ids.operador_id._marcar_operador_finca()
            rec.state = 'confirmado'

    def action_borrador(self):
        self.write({'state': 'borrador'})

    def action_cancelar(self):
        self.write({'state': 'cancelado'})


class FincaContratoLinea(models.Model):
    _name = 'finca.contrato.linea'
    _description = 'Operador en Labor por Contrato'
    _order = 'contrato_id, id'

    _operador_unique = models.Constraint(
        'UNIQUE(contrato_id, operador_id)',
        'Un operador aparece dos veces en la misma labor.',
    )

    contrato_id = fields.Many2one(
        'finca.contrato',
        string='Labor',
        required=True,
        ondelete='cascade',
        index=True,
    )
    operador_id = fields.Many2one(
        'res.partner',
        string='Operador',
        required=True,
        index=True,
    )
    participacion = fields.Float(
        string='Participación',
        default=1.0,
        digits=(6, 2),
        help='Parte de la labor que hizo. Con 1 para todos el valor se reparte '
             'por igual; ponga 0,5 a quien hizo media parte.',
    )
    valor = fields.Float(
        string='Valor',
        digits=(12, 2),
        compute='_compute_valor',
        store=True,
    )

    @api.depends('participacion', 'contrato_id.total', 'contrato_id.linea_ids.participacion')
    def _compute_valor(self):
        for rec in self:
            suma = sum(rec.contrato_id.linea_ids.mapped('participacion'))
            rec.valor = rec.contrato_id.total * rec.participacion / suma if suma else 0.0

    @api.constrains('participacion')
    def _check_participacion(self):
        for rec in self:
            if rec.participacion <= 0:
                raise ValidationError('La participación debe ser mayor que cero.')
