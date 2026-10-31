# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError

from .labor import UNIDADES


class FincaMaquinariaTrabajo(models.Model):
    """Pago a un operador por el trabajo con un equipo durante la campaña.

    Equivale a la hoja "Maquinaria". Al confirmar se crea también una línea de
    costo (tipo "Recursos Humanos") en el equipo, para que el costo por equipo
    de mantenimiento incluya la mano de obra de los operadores.

    Puede ser un valor fijo (mantenimiento de la campaña) o, con una labor,
    cantidad por tarifa: pilotos y ayudantes de dron, que se pagan por hectárea
    rociada y bulto esparcido, sin finca. Ese costo es de la maquinaria del
    dueño del equipo; a la finca se le cobra aparte.
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
        domain=[('es_dueno_finca', '=', True)],
        compute='_compute_desde_equipo',
        store=True,
        readonly=False,
        index=True,
        help='Se propone el dueño en labores del equipo o, si no tiene, su compañía.',
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
    labor_id = fields.Many2one(
        'finca.labor',
        string='Labor',
        domain=[('tipo', '=', 'maquinaria')],
        help='Para los trabajos que se pagan por cantidad. Vacío en los de '
             'valor fijo.',
    )
    unidad = fields.Selection(UNIDADES, related='labor_id.unidad', string='Unidad')
    cantidad = fields.Float(string='Cantidad', digits=(12, 2))
    tarifa = fields.Float(
        string='Tarifa',
        digits=(12, 2),
        help='Se propone la última de este operador en la labor; se puede cambiar.',
    )
    valor = fields.Float(
        string='Valor',
        digits=(12, 2),
        required=True,
        tracking=True,
        compute='_compute_valor',
        store=True,
        precompute=True,
        readonly=False,
    )
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

    @api.depends('equipment_id', 'labor_id')
    def _compute_desde_equipo(self):
        for rec in self:
            equipo = rec.equipment_id
            rec.lugar_id = equipo.lugar_id
            rec.dueno_id = equipo.finca_dueno_id or equipo.company_id.partner_id
            if rec.labor_id:
                rec.descripcion = '%s %s' % (rec.labor_id.name, equipo.name or '')
            else:
                rec.descripcion = 'MTTO %s' % equipo.name if equipo else False

    @api.depends('labor_id', 'cantidad', 'tarifa')
    def _compute_valor(self):
        for rec in self:
            if rec.labor_id:
                rec.valor = rec.cantidad * rec.tarifa
            else:
                rec.valor = rec.valor or 0.0

    @api.onchange('labor_id', 'operador_id')
    def _onchange_proponer_tarifa(self):
        """La tarifa cambia por persona: se propone la última que se le pagó en
        esa labor y, si es la primera vez, la del catálogo."""
        if not self.labor_id:
            return
        anterior = self.operador_id and self.search([
            ('labor_id', '=', self.labor_id.id),
            ('operador_id', '=', self.operador_id.id),
            ('state', '=', 'confirmado'),
        ], order='fecha desc, id desc', limit=1)
        self.tarifa = anterior.tarifa if anterior else self.labor_id.valor_unitario

    @api.depends('equipment_id', 'campana_id', 'valor', 'state', 'labor_id')
    def _compute_pagado_equipo(self):
        # El tope es del mantenimiento de la campaña: lo que se paga por
        # cantidad depende de cuánto se trabajó y no cuenta contra él.
        for rec in self:
            if rec.labor_id:
                rec.pagado_equipo = rec.valor if rec.state != 'cancelado' else 0.0
                rec.excede_tope = False
                continue
            otros = self.search([
                ('equipment_id', '=', rec.equipment_id.id),
                ('campana_id', '=', rec.campana_id.id),
                ('labor_id', '=', False),
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
                'quantity': rec.cantidad if rec.labor_id else 1.0,
                'unit_cost': rec.tarifa if rec.labor_id else rec.valor,
                'uom_name': rec.unidad or False,
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
