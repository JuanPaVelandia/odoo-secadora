# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

ITEM_TYPE_SELECTION = [
    ('shirt', 'Camisa/Sueter'),
    ('pants', 'Pantalon'),
    ('shoes', 'Zapatos'),
    ('helmet', 'Casco'),
    ('gloves', 'Guantes'),
    ('glasses', 'Gafas'),
    ('mask', 'Mascarilla'),
    ('vest', 'Chaleco'),
    ('boots', 'Botas'),
    ('other', 'Otro')
]

ITEMS_REQUIRING_SIZE = ('shirt', 'pants', 'shoes', 'boots')


class HrEppRequest(models.Model):
    _inherit = 'hr.epp.request'
    _order = 'create_date desc'

    name = fields.Char('Referencia', required=True, copy=False, default='New')
    employee_id = fields.Many2one('hr.employee', 'Empleado', required=True, tracking=True)
    department_id = fields.Many2one('hr.department', related='employee_id.department_id', store=True)
    job_id = fields.Many2one('hr.job', related='employee_id.job_id', store=True)
    configuration_id = fields.Many2one('hr.epp.configuration', 'Configuracion')
    batch_id = fields.Many2one('hr.epp.batch', string='Lote', index=True)
    employee_location_id = fields.Many2one('stock.location', related='employee_id.default_location_id', store=True)

    type = fields.Selection([
        ('epp', 'EPP - Elementos de Proteccion Personal'),
        ('dotacion', 'Dotacion - Uniformes')
    ], string='Tipo', required=True, tracking=True)

    request_date = fields.Date('Fecha Solicitud', default=fields.Date.today, required=True)
    delivery_date = fields.Date('Fecha Entrega')
    approved_date = fields.Date('Fecha Aprobacion')
    delivered_date = fields.Date('Fecha Entregado')
    approved_by = fields.Many2one('res.users', 'Aprobado por')

    state = fields.Selection([
        ('draft', 'Borrador'),
        ('requested', 'Solicitado'),
        ('approved', 'Aprobado'),
        ('picking', 'En Preparacion'),
        ('delivered', 'Entregado'),
        ('cancelled', 'Cancelado')
    ], string='Estado', default='draft', tracking=True)

    line_ids = fields.One2many('hr.epp.request.line', 'request_id', 'Items')
    delivery_line_ids = fields.One2many('hr.epp.delivery.line', 'request_id', 'Lineas de Entrega')

    location_id = fields.Many2one('stock.location', 'Ubicacion EPP')
    stock_move_ids = fields.Many2many('stock.move', 'hr_epp_request_stock_move_rel', 'request_id', 'move_id', string='Movimientos de Stock')
    stock_move_count = fields.Integer('Movimientos', compute='_compute_stock_move_count')
    picking_id = fields.Many2one('stock.picking', 'Movimiento de Inventario')
    purchase_order_id = fields.Many2one('purchase.order', 'Orden de Compra')

    delivery_location = fields.Selection([
        ('office', 'Oficina Principal'),
        ('warehouse', 'Almacen'),
        ('worksite', 'Sitio de Trabajo'),
        ('other', 'Otro')
    ], string='Lugar de Entrega', default='office')

    notes = fields.Text('Notas')
    signature = fields.Binary('Firma de Recibido')
    signed_by = fields.Char('Recibido por')
    signed_date = fields.Datetime('Fecha/Hora de Firma')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                seq_code = 'hr.epp.request' if vals.get('type') == 'epp' else 'hr.dotacion.request'
                vals['name'] = self.env['ir.sequence'].next_by_code(seq_code) or 'EPP/001'
        return super().create(vals_list)

    @api.depends('stock_move_ids')
    def _compute_stock_move_count(self):
        for record in self:
            record.stock_move_count = len(record.stock_move_ids)

    def action_request(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('Debe agregar al menos un item'))
        for line in self.line_ids:
            if line.requires_size and not line.size:
                raise UserError(_('Debe especificar la talla para %s') % line.name)
        self.state = 'requested'

    def action_approve(self):
        self.ensure_one()
        self.state = 'approved'
        self.approved_date = fields.Date.today()
        self.approved_by = self.env.user

    def action_deliver(self):
        self.ensure_one()
        if self.picking_id and self.picking_id.state != 'done':
            self.picking_id.button_validate()
        self.state = 'delivered'
        self.delivery_date = fields.Date.today()
        self.delivered_date = fields.Date.today()
        if not self.delivery_line_ids:
            self._generate_delivery_lines()

    def _generate_delivery_lines(self):
        """Genera líneas de entrega a partir de las líneas solicitadas"""
        self.ensure_one()
        self.delivery_line_ids.unlink()

        if not self.line_ids:
            return

        today = fields.Date.today()
        vals_list = [{
            'request_id': self.id,
            'request_line_id': line.id,
            'item_type_id': line.item_type_id.id,
            'product_id': line.product_id.id,
            'name': line.name,
            'quantity_requested': line.quantity,
            'quantity_delivered': line.quantity,
            'size': line.size,
            'delivery_date': today,
            'state': 'pending',
        } for line in self.line_ids]

        self.env['hr.epp.delivery.line'].create(vals_list)

    def action_cancel(self):
        self.ensure_one()
        if self.picking_id and self.picking_id.state == 'done':
            raise UserError(_('No se puede cancelar con movimiento completado'))
        if self.picking_id and self.picking_id.state != 'cancel':
            self.picking_id.action_cancel()
        self.state = 'cancelled'


class HrEppRequestLine(models.Model):
    _inherit = 'hr.epp.request.line'

    request_id = fields.Many2one('hr.epp.request', 'Solicitud', ondelete='cascade')
    product_id = fields.Many2one('product.product', 'Producto')
    name = fields.Char('Descripcion', required=True)
    quantity = fields.Float('Cantidad', default=1.0, required=True)
    size = fields.Char('Talla')

    # Nuevo campo Many2one para tipo de item
    item_type_id = fields.Many2one(
        'hr.epp.item.type',
        string='Tipo',
        domain="[('is_subtype', '=', True)]"
    )
    item_type_parent_id = fields.Many2one(
        related='item_type_id.parent_id',
        string='Categoría',
        store=True
    )

    requires_size = fields.Boolean('Requiere Talla', compute='_compute_requires_size', store=True)
    notes = fields.Text('Notas')

    @api.depends('item_type_id', 'item_type_id.requires_size')
    def _compute_requires_size(self):
        for line in self:
            line.requires_size = line.item_type_id.requires_size if line.item_type_id else False

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.name = self.product_id.name


class HrEppDeliveryLine(models.Model):
    _inherit = 'hr.epp.delivery.line'

    request_id = fields.Many2one('hr.epp.request', 'Solicitud', required=True, ondelete='cascade')
    request_line_id = fields.Many2one('hr.epp.request.line', 'Linea de Solicitud', ondelete='set null')
    employee_id = fields.Many2one('hr.employee', related='request_id.employee_id', store=True)
    product_id = fields.Many2one('product.product', 'Producto')
    name = fields.Char('Descripcion', required=True)

    # Nuevo campo Many2one para tipo de item
    item_type_id = fields.Many2one(
        'hr.epp.item.type',
        string='Tipo',
        domain="[('is_subtype', '=', True)]"
    )
    item_type_parent_id = fields.Many2one(
        related='item_type_id.parent_id',
        string='Categoría',
        store=True
    )

    quantity_requested = fields.Float('Cantidad Solicitada', default=1.0)
    quantity_delivered = fields.Float('Cantidad Entregada', default=1.0)
    size = fields.Char('Talla')
    delivery_date = fields.Date('Fecha de Entrega', default=fields.Date.today)
    delivered_date = fields.Datetime('Fecha/Hora Entregado')
    state = fields.Selection([('pending', 'Pendiente'), ('delivered', 'Entregado'), ('rejected', 'Rechazado')], default='pending', required=True)
    signature = fields.Binary('Firma de Recibido')
    notes = fields.Text('Observaciones')

    def action_mark_delivered(self):
        for line in self:
            line.write({'state': 'delivered', 'delivered_date': fields.Datetime.now()})

    def action_mark_rejected(self):
        for line in self:
            line.state = 'rejected'
