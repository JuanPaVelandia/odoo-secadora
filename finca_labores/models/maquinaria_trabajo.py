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
    # Periodo interno de los saldos: se toma solo de la fecha y no se muestra.
    campana_id = fields.Many2one(
        'finca.campana',
        string='Campaña',
        required=True,
        index=True,
        compute='_compute_campana_id',
        store=True,
        readonly=False,
    )
    cosecha_id = fields.Many2one(
        'account.analytic.account',
        string='Cosecha',
        index='btree_not_null',
        ondelete='restrict',
        domain=lambda self: self.env['finca.campana']._dominio_cosecha(),
        compute='_compute_cosecha_id',
        store=True,
        readonly=False,
        help='Cosecha a la que va el costo (2026 secano, 2026 riego...). Es la '
             'misma analítica de las facturas y pasa al asiento del giro. Se '
             'propone la del último registro de el mismo equipo.',
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
        help='Suma de los trabajos confirmados de este equipo en el año (oct–sep), '
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
    liquidacion_id = fields.Many2one(
        'finca.liquidacion',
        string='Liquidación',
        readonly=True,
        copy=False,
        index=True,
        ondelete='set null',
        help='Liquidación con la que se pagó este trabajo (desde "Liquidar seleccionados").',
    )
    move_id = fields.Many2one(
        related='liquidacion_id.move_id',
        string='Asiento del pago',
    )
    liquidacion_state = fields.Selection(
        related='liquidacion_id.state',
        string='Estado del pago',
    )

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

    @api.depends('fecha')
    def _compute_campana_id(self):
        Campana = self.env['finca.campana']
        for rec in self:
            rec.campana_id = Campana._get_campana(rec.fecha)

    @api.depends('equipment_id')
    def _compute_cosecha_id(self):
        Campana = self.env['finca.campana']
        for rec in self:
            if rec.cosecha_id or not rec.equipment_id:
                continue
            rec.cosecha_id = Campana._cosecha_sugerida(
                rec._name, [('equipment_id', '=', rec.equipment_id.id), ('id', '!=', rec._origin.id or 0)])

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

    def action_liquidar(self):
        """Arma una liquidación con los trabajos seleccionados: una línea por
        persona con la suma de sus trabajos. Tienen que ser de la misma
        campaña, dueño y empresa que paga (un giro = un dueño)."""
        trabajos = self.filtered(lambda t: t.state == 'confirmado')
        if not trabajos:
            raise UserError('Seleccione trabajos confirmados.')
        pendientes = trabajos.filtered(
            lambda t: t.liquidacion_id and t.liquidacion_id.state != 'cancelada')
        if pendientes:
            raise UserError('Estos trabajos ya están en una liquidación: %s.' % ', '.join(
                '%s (%s)' % (t.name, t.liquidacion_id.name) for t in pendientes))
        if len(trabajos.campana_id) > 1 or len(trabajos.dueno_id) > 1:
            raise UserError(
                'Los trabajos seleccionados deben ser del mismo dueño y el mismo periodo '
                '(año de octubre a septiembre): un giro se hace por dueño. Haga una '
                'liquidación por cada uno.')
        if not trabajos.dueno_id:
            raise UserError('Los trabajos no tienen dueño.')
        # Un dron de una sociedad puede estar en la compañía de un socio y
        # pagarlo otro: el giro sale de la empresa activa.
        empresa = trabajos.company_id if len(trabajos.company_id) == 1 else self.env.company
        campana, dueno = trabajos.campana_id, trabajos.dueno_id
        saldos = self.env['finca.labor.movimiento']._saldos_por_operador(campana, dueno)
        lineas = []
        for operador in trabajos.operador_id.sorted('name'):
            monto = sum(trabajos.filtered(lambda t: t.operador_id == operador).mapped('valor'))
            lineas.append((0, 0, {
                'operador_id': operador.id,
                'saldo': saldos.get(operador, 0.0),
                'monto': monto,
            }))
        liq = self.env['finca.liquidacion'].with_company(empresa).create({
            'campana_id': campana.id,
            'dueno_id': dueno.id,
            'company_id': empresa.id,
            'linea_ids': lineas,
        })
        trabajos.write({'liquidacion_id': liq.id})
        liq.message_post(body='Armada con %d trabajos de maquinaria: %s.' % (
            len(trabajos), ', '.join(trabajos.sorted('name').mapped('name'))))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'finca.liquidacion',
            'res_id': liq.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def unlink(self):
        if any(rec.state == 'confirmado' for rec in self):
            raise UserError('Pase el trabajo a borrador antes de eliminarlo.')
        return super().unlink()
