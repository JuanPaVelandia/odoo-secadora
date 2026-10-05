# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError


class FincaMaquinariaTrabajo(models.Model):
    """Pago a un operador por el mantenimiento de un equipo durante la campaña.

    Equivale a la hoja "Maquinaria". Al confirmar se crea también una línea de
    costo (tipo "Recursos Humanos") en el equipo, para que el costo por equipo
    de mantenimiento incluya la mano de obra de los operadores.
    """
    _name = 'finca.maquinaria.trabajo'
    _description = 'Trabajo de Maquinaria'
    _inherit = ['mail.thread']
    _order = 'fecha desc, id desc'

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
    fecha = fields.Date(string='Fecha', required=True, default=fields.Date.context_today)
    equipment_id = fields.Many2one(
        'maintenance.equipment',
        string='Equipo',
        required=True,
        index=True,
    )
    category_id = fields.Many2one(
        related='equipment_id.category_id',
        string='Tipo de equipo',
        store=True,
    )
    lugar_id = fields.Many2one(
        'secadora.lugar',
        string='Ubicación',
        compute='_compute_desde_equipo',
        store=True,
        readonly=False,
    )
    dueno_id = fields.Many2one(
        'res.partner',
        string='Dueño',
        compute='_compute_desde_equipo',
        store=True,
        readonly=False,
        index=True,
        help='Se propone la compañía dueña del equipo (siglas JV, JPV, FT del nombre).',
    )
    operador_id = fields.Many2one(
        'res.partner',
        string='Operador',
        required=True,
        index=True,
    )
    descripcion = fields.Char(
        string='Trabajo',
        compute='_compute_desde_equipo',
        store=True,
        readonly=False,
    )
    valor = fields.Float(string='Valor', digits=(12, 2), required=True, tracking=True)
    valor_max_contrato = fields.Float(
        related='category_id.finca_valor_max_contrato',
        string='Tope por contrato',
    )
    pagado_equipo = fields.Float(
        string='Acumulado del equipo',
        digits=(12, 2),
        compute='_compute_pagado_equipo',
        help='Suma de los trabajos confirmados de este equipo en la campaña, '
             'incluyendo este.',
    )
    excede_tope = fields.Boolean(string='Supera el tope', compute='_compute_pagado_equipo')
    cost_line_id = fields.Many2one(
        'maintenance.equipment.cost.line',
        string='Costo en el equipo',
        readonly=True,
        copy=False,
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
                vals['name'] = self.env['ir.sequence'].next_by_code('finca.maquinaria.trabajo') or 'Nuevo'
        return super().create(vals_list)

    @api.depends('equipment_id')
    def _compute_desde_equipo(self):
        for rec in self:
            equipo = rec.equipment_id
            rec.lugar_id = equipo.lugar_id
            rec.dueno_id = equipo.company_id.partner_id
            rec.descripcion = 'MTTO %s' % equipo.name if equipo else False

    @api.depends('equipment_id', 'campana_id', 'valor', 'state')
    def _compute_pagado_equipo(self):
        for rec in self:
            otros = self.search([
                ('equipment_id', '=', rec.equipment_id.id),
                ('campana_id', '=', rec.campana_id.id),
                ('state', '=', 'confirmado'),
                ('id', '!=', rec._origin.id or 0),
            ]) if rec.equipment_id and rec.campana_id else self.browse()
            propio = rec.valor if rec.state != 'cancelado' else 0.0
            rec.pagado_equipo = sum(otros.mapped('valor')) + propio
            rec.excede_tope = bool(rec.valor_max_contrato) and rec.pagado_equipo > rec.valor_max_contrato

    def action_confirmar(self):
        CostLine = self.env['maintenance.equipment.cost.line'].sudo()
        for rec in self.filtered(lambda r: r.state == 'borrador'):
            if not rec.valor:
                raise UserError('El trabajo %s no tiene valor.' % rec.name)
            if not rec.dueno_id:
                raise UserError('El trabajo %s no tiene dueño.' % rec.name)
            rec.operador_id._marcar_operador_finca()
            rec.cost_line_id = CostLine.create({
                'origin': 'manual',
                'equipment_id': rec.equipment_id.id,
                'date': rec.fecha,
                'name': rec.descripcion or rec.name,
                'partner_id': rec.operador_id.id,
                'quantity': 1.0,
                'unit_cost': rec.valor,
                'amount': rec.valor,
                'resource_type': 'human',
                'external_ref': rec.name,
                'company_id': rec.company_id.id,
            })
            rec.state = 'confirmado'

    def _quitar_costo(self):
        lineas = self.cost_line_id
        self.cost_line_id = False
        lineas.sudo().unlink()

    def action_borrador(self):
        self._quitar_costo()
        self.write({'state': 'borrador'})

    def action_cancelar(self):
        self._quitar_costo()
        self.write({'state': 'cancelado'})

    def unlink(self):
        if any(rec.state == 'confirmado' for rec in self):
            raise UserError('Pase el trabajo a borrador antes de eliminarlo.')
        return super().unlink()
