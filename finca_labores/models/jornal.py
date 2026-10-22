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
        domain=[('es_dueno_finca', '=', True)],
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
    liquidacion_id = fields.Many2one(
        'finca.liquidacion',
        string='Liquidación',
        readonly=True,
        copy=False,
        index=True,
        help='Liquidación armada con este jornal (desde "Liquidar seleccionados").',
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

    def action_liquidar(self):
        """Arma una liquidación con los jornales seleccionados: una línea por
        persona con la suma de sus jornales. Tienen que ser de la misma
        campaña, dueño y empresa (un giro = un dueño)."""
        jornales = self.filtered(lambda j: j.state == 'confirmado')
        if not jornales:
            raise UserError('Seleccione jornales confirmados.')
        pendientes = jornales.filtered(
            lambda j: j.liquidacion_id and j.liquidacion_id.state != 'cancelada')
        if pendientes:
            raise UserError('Estos jornales ya están en una liquidación: %s.' % ', '.join(
                '%s (%s)' % (j.name, j.liquidacion_id.name) for j in pendientes))
        if len(jornales.campana_id) > 1 or len(jornales.dueno_id) > 1 or len(jornales.company_id) > 1:
            raise UserError(
                'Los jornales seleccionados deben ser de la misma campaña, el mismo dueño '
                'y la misma empresa: un giro se hace por dueño. Haga una liquidación por cada uno.')
        if not jornales.dueno_id:
            raise UserError('Los jornales no tienen dueño.')
        campana, dueno = jornales.campana_id, jornales.dueno_id
        saldos = self.env['finca.labor.movimiento']._saldos_por_operador(campana, dueno)
        lineas = []
        for operador in jornales.operador_id.sorted('name'):
            monto = sum(jornales.filtered(lambda j: j.operador_id == operador).mapped('total'))
            lineas.append((0, 0, {
                'operador_id': operador.id,
                'saldo': saldos.get(operador, 0.0),
                'monto': monto,
            }))
        liq = self.env['finca.liquidacion'].with_company(jornales.company_id).create({
            'campana_id': campana.id,
            'dueno_id': dueno.id,
            'company_id': jornales.company_id.id,
            'linea_ids': lineas,
        })
        jornales.write({'liquidacion_id': liq.id})
        liq.message_post(body='Armada con %d jornales: %s.' % (
            len(jornales), ', '.join(jornales.sorted('name').mapped('name'))))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'finca.liquidacion',
            'res_id': liq.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_cancelar(self):
        self.write({'state': 'cancelado'})
