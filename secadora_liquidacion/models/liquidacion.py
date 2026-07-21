# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError


class SecadoraLiquidacion(models.Model):
    _name = 'secadora.liquidacion'
    _description = 'Liquidación de Compra'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'

    name = fields.Char(
        string='Número',
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: 'Nuevo',
    )
    fecha = fields.Date(
        string='Fecha',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    tercero_id = fields.Many2one(
        'res.partner',
        string='Agricultor',
        required=True,
        index=True,
        tracking=True,
    )
    fecha_desde = fields.Date(
        string='Fecha Desde',
        help='Inicio del período de pesajes',
    )
    fecha_hasta = fields.Date(
        string='Fecha Hasta',
        help='Fin del período de pesajes',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    linea_ids = fields.One2many(
        'secadora.liquidacion.linea',
        'liquidacion_id',
        string='Líneas de Pesaje',
    )
    deduccion_ids = fields.One2many(
        'secadora.liquidacion.deduccion',
        'liquidacion_id',
        string='Deducciones',
    )
    total_peso_comercial = fields.Float(
        string='Total Peso Comercial (kg)',
        compute='_compute_totales',
        store=True,
        digits=(12, 2),
    )
    total_bruto = fields.Float(
        string='Total Bruto ($)',
        compute='_compute_totales',
        store=True,
        digits=(12, 2),
    )
    total_deducciones = fields.Float(
        string='Total Deducciones ($)',
        compute='_compute_totales',
        store=True,
        digits=(12, 2),
    )
    total_neto = fields.Float(
        string='Total Neto ($)',
        compute='_compute_totales',
        store=True,
        digits=(12, 2),
    )
    cantidad_pesajes = fields.Integer(
        string='Cantidad de Pesajes',
        compute='_compute_totales',
        store=True,
    )
    state = fields.Selection([
        ('borrador', 'Borrador'),
        ('confirmado', 'Confirmado'),
        ('facturado', 'Facturado'),
        ('cancelado', 'Cancelado'),
    ], string='Estado', default='borrador', required=True, index=True, tracking=True)
    factura_id = fields.Many2one(
        'account.move',
        string='Factura',
        tracking=True,
        ondelete='set null',
        copy=False,
        domain="[('move_type', '=', 'in_invoice'), ('partner_id', '=', tercero_id)]",
    )
    observaciones = fields.Text(string='Observaciones')
    usuario_id = fields.Many2one(
        'res.users',
        string='Responsable',
        default=lambda self: self.env.user,
        tracking=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('secadora.liquidacion') or 'Nuevo'
        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        if 'factura_id' in vals:
            for rec in self:
                if rec.factura_id and rec.state == 'confirmado':
                    rec.state = 'facturado'
                elif not rec.factura_id and rec.state == 'facturado':
                    rec.state = 'confirmado'
        return res

    @api.depends('linea_ids.subtotal', 'linea_ids.peso_comercial', 'deduccion_ids.monto')
    def _compute_totales(self):
        for rec in self:
            lineas = rec.linea_ids
            deducciones = rec.deduccion_ids
            rec.total_peso_comercial = sum(lineas.mapped('peso_comercial'))
            rec.total_bruto = sum(lineas.mapped('subtotal'))
            rec.total_deducciones = sum(deducciones.mapped('monto'))
            rec.total_neto = rec.total_bruto - rec.total_deducciones
            rec.cantidad_pesajes = len(lineas)

    def action_confirmar(self):
        for rec in self:
            if not rec.linea_ids:
                raise UserError('Debe agregar al menos una línea de pesaje antes de confirmar.')
            rec.action_cargar_fletes()
            rec.state = 'confirmado'

    def action_borrador(self):
        for rec in self:
            rec.state = 'borrador'

    def action_cancelar(self):
        for rec in self:
            rec.state = 'cancelado'

    def action_ver_factura(self):
        self.ensure_one()
        if not self.factura_id:
            raise UserError('No hay factura vinculada.')
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.factura_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.onchange('linea_ids')
    def _onchange_linea_ids(self):
        if not self.tercero_id and self.linea_ids:
            pesaje = self.linea_ids[0].pesaje_id
            if pesaje and pesaje.tercero_id:
                self.tercero_id = pesaje.tercero_id
        # Excluir pesajes ya seleccionados del domain
        pesajes_usados = self.linea_ids.mapped('pesaje_id').ids
        domain = [
            ('state', '=', 'completado'),
            ('direccion', '=', 'entrada'),
            ('tipo_operacion_id.codigo', '=', 'COMPRA'),
            ('liquidacion_id', '=', False),
        ]
        if self.tercero_id:
            domain.append(('tercero_id', '=', self.tercero_id.id))
        if pesajes_usados:
            domain.append(('id', 'not in', pesajes_usados))
        return {'domain': {'pesaje_id': domain}}

    def action_cargar_fletes(self):
        """Busca fletes vinculados a los pesajes de esta liquidación y crea deducciones."""
        for rec in self:
            pesaje_ids = rec.linea_ids.mapped('pesaje_id').ids
            if not pesaje_ids:
                raise UserError('No hay pesajes en la liquidación para buscar fletes.')

            fletes = self.env['secadora.flete'].search([
                ('pesaje_id', 'in', pesaje_ids),
                ('pago_flete', '=', 'secadora'),
                ('state', '!=', 'cancelado'),
            ])

            # Eliminar deducciones tipo flete existentes
            rec.deduccion_ids.filtered(lambda d: d.tipo == 'flete').unlink()

            for flete in fletes:
                self.env['secadora.liquidacion.deduccion'].create({
                    'liquidacion_id': rec.id,
                    'tipo': 'flete',
                    'descripcion': 'Flete %s (%s → %s)' % (
                        flete.name,
                        flete.origen_id.name or '',
                        flete.destino_id.name or '',
                    ),
                    'monto': flete.costo_total,
                    'flete_id': flete.id,
                })

    def action_aplicar_deducciones(self):
        """Aplica deducciones automáticas según el agricultor (tercero_id)."""
        Deduccion = self.env['secadora.liquidacion.deduccion']
        for rec in self:
            tipos = rec.tercero_id.tipo_deduccion_ids.filtered('active')
            if not tipos:
                raise UserError('El agricultor %s no tiene deducciones configuradas.' % rec.tercero_id.name)

            # Eliminar deducciones auto-generadas previas (excepto fletes)
            rec.deduccion_ids.filtered(lambda d: d.tipo_deduccion_id).unlink()

            for tipo in tipos:
                if tipo.tipo_calculo == 'porcentaje':
                    monto = rec.total_bruto * tipo.valor / 100.0
                else:
                    monto = tipo.valor

                # Mapear tipo selection
                if 'reten' in (tipo.codigo or '').lower():
                    tipo_sel = 'retencion'
                else:
                    tipo_sel = 'otro'

                Deduccion.create({
                    'liquidacion_id': rec.id,
                    'tipo': tipo_sel,
                    'descripcion': '%s (%s)' % (tipo.name, tipo.codigo),
                    'monto': monto,
                    'tipo_deduccion_id': tipo.id,
                    'sequence': tipo.sequence,
                })

    def action_abrir_wizard_pesajes(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Agregar Pesajes',
            'res_model': 'secadora.crear.liquidacion.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_liquidacion_id': self.id,
                'default_tercero_id': self.tercero_id.id,
                'default_fecha_desde': self.fecha_desde,
                'default_fecha_hasta': self.fecha_hasta,
            },
        }
