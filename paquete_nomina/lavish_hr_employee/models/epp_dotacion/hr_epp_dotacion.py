# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from dateutil.relativedelta import relativedelta

class HrEppConfiguration(models.Model):
    _inherit = 'hr.epp.configuration'

    @api.model
    def create_default_configuration(self):
        """Crear configuración por defecto para dotación"""
        # Buscar o crear ubicación EPP
        location = self.env['stock.location'].search([
            ('name', '=', 'EPP/Dotación'),
            ('usage', '=', 'internal')
        ], limit=1)
        
        if not location:
            warehouse = self.env['stock.warehouse'].search([
                ('company_id', '=', self.env.company.id)
            ], limit=1)
            
            if warehouse:
                location = self.env['stock.location'].create({
                    'name': 'EPP/Dotación',
                    'usage': 'internal',
                    'location_id': warehouse.lot_stock_id.id,
                })
        
        # Crear configuración de dotación
        config = self.create({
            'name': 'Dotación Estándar',
            'type': 'dotacion',
            'frequency': 3,
            'use_stock_location': bool(location),
            'location_id': location.id if location else False,
        })
        
        # Agregar items estándar
        items = [
            ('shirt', 'Camisa/Suéter', 3),
            ('pants', 'Pantalón', 3),
            ('shoes', 'Zapatos', 1),
        ]
        
        for item_type, name, qty in items:
            self.env['hr.epp.configuration.line'].create({
                'configuration_id': config.id,
                'item_type': item_type,
                'name': name,
                'quantity': qty,
            })
        
        return config


class HrEppConfigurationLine(models.Model):
    _inherit = 'hr.epp.configuration.line'

    item_type = fields.Selection([
        ('shirt', 'Camisa/Suéter'),
        ('pants', 'Pantalón'),
        ('shoes', 'Zapatos'),
        ('helmet', 'Casco'),
        ('gloves', 'Guantes'),
        ('glasses', 'Gafas'),
        ('mask', 'Mascarilla'),
        ('vest', 'Chaleco'),
        ('boots', 'Botas'),
        ('other', 'Otro')
    ], string='Tipo Legado', default='other')


class HrEppRequest(models.Model):
    _name = 'hr.epp.request'
    _description = 'Solicitud de EPP/Dotación'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'
    
    name = fields.Char('Referencia', required=True, copy=False, default='New')
    employee_id = fields.Many2one('hr.employee', 'Empleado', required=True, tracking=True)
    department_id = fields.Many2one('hr.department', string='Departamento', related='employee_id.department_id', store=True, readonly=True)
    job_id = fields.Many2one('hr.job', string='Puesto', related='employee_id.job_id', store=True, readonly=True)
    configuration_id = fields.Many2one('hr.epp.configuration', 'Configuración')

    batch_id = fields.Many2one(
        'hr.epp.batch',
        string='Lote',
        help='Lote de entregas al que pertenece esta solicitud',
        index=True
    )
    employee_location_id = fields.Many2one(
        'stock.location',
        string='Bodega del Empleado',
        related='employee_id.default_location_id',
        store=True,
        help='Bodega asignada al empleado (tiene prioridad sobre la global)'
    )

    type = fields.Selection([
        ('epp', 'EPP - Elementos de Protección Personal'),
        ('dotacion', 'Dotación - Uniformes')
    ], string='Tipo', required=True, tracking=True)
    
    # Fechas
    request_date = fields.Date('Fecha Solicitud', default=fields.Date.today, required=True)
    delivery_date = fields.Date('Fecha Entrega')
    approved_date = fields.Date('Fecha Aprobación')
    delivered_date = fields.Date('Fecha Entregado')

    # Aprobación
    approved_by = fields.Many2one('res.users', 'Aprobado por')

    # Estado
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('requested', 'Solicitado'),
        ('approved', 'Aprobado'),
        ('picking', 'En Preparación'),
        ('delivered', 'Entregado'),
        ('cancelled', 'Cancelado')
    ], string='Estado', default='draft', tracking=True)
    
    # Líneas
    line_ids = fields.One2many('hr.epp.request.line', 'request_id', 'Items')
    delivery_line_ids = fields.One2many('hr.epp.delivery.line', 'request_id', 'Líneas de Entrega',
                                         help='Registro detallado de entregas por item')

    # Ubicación y movimientos (stock.move DIRECTO, sin picking)
    location_id = fields.Many2one('stock.location', 'Ubicación EPP')
    stock_move_ids = fields.Many2many(
        'stock.move',
        'hr_epp_request_stock_move_rel',
        'request_id',
        'move_id',
        string='Movimientos de Stock'
    )
    stock_move_count = fields.Integer('Número de Movimientos', compute='_compute_stock_move_count')
    
    # Deprecated (mantener por compatibilidad)
    picking_id = fields.Many2one('stock.picking', 'Movimiento de Inventario')
    picking_count = fields.Integer('Número de Movimientos (picking)', compute='_compute_picking_count')

    # Documentos
    purchase_order_id = fields.Many2one('purchase.order', 'Orden de Compra')
    purchase_count = fields.Integer('Número de Órdenes', compute='_compute_purchase_count')
    
    # Entrega
    delivery_location = fields.Selection([
        ('office', 'Oficina Principal'),
        ('warehouse', 'Almacén'),
        ('worksite', 'Sitio de Trabajo'),
        ('other', 'Otro')
    ], string='Lugar de Entrega', default='office')
    
    delivery_location_detail = fields.Char('Detalle de Ubicación')
    delivery_address = fields.Char('Dirección de Entrega')
    delivery_notes = fields.Text('Notas de Entrega')
    notes = fields.Text('Notas')

    # Firma digital
    signature = fields.Binary('Firma de Recibido')
    signed_by = fields.Char('Recibido por')
    signed_date = fields.Datetime('Fecha/Hora de Firma')
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                if vals.get('type') == 'epp':
                    vals['name'] = self.env['ir.sequence'].next_by_code('hr.epp.request') or 'EPP/001'
                else:
                    vals['name'] = self.env['ir.sequence'].next_by_code('hr.dotacion.request') or 'DOT/001'
        return super().create(vals_list)

    @api.depends('stock_move_ids')
    def _compute_stock_move_count(self):
        """Calcula el número de movimientos de stock"""
        for record in self:
            record.stock_move_count = len(record.stock_move_ids)

    @api.depends('picking_id')
    @api.depends('stock_move_ids')
    def _compute_stock_move_count(self):
        """Calcula el número de movimientos de stock"""
        for record in self:
            record.stock_move_count = len(record.stock_move_ids)

    def _compute_picking_count(self):
        """Calcula el número de movimientos de inventario asociados (deprecated)"""
        for record in self:
            record.picking_count = 1 if record.picking_id else 0

    @api.depends('purchase_order_id')
    def _compute_purchase_count(self):
        """Calcula el número de órdenes de compra asociadas"""
        for record in self:
            record.purchase_count = 1 if record.purchase_order_id else 0

    def action_request(self):
        """Enviar solicitud"""
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('Debe agregar al menos un item'))
        
        # Validar tallas
        for line in self.line_ids:
            if line.requires_size and not line.size:
                raise UserError(_('Debe especificar la talla para %s') % line.name)
        
        self.state = 'requested'
        
        # Notificar
        self.message_post(
            body=_('Nueva solicitud de %s de %s') % (
                dict(self._fields['type'].selection).get(self.type),
                self.employee_id.name
            ),
            message_type='notification',
        )
    
    def action_approve(self):
        """Aprobar solicitud"""
        self.ensure_one()
        self.state = 'approved'
        self.approved_date = fields.Date.today()
        self.approved_by = self.env.user
        
        # NOTE: Los stock.move se crean desde el batch de forma agrupada
        # No crear movimientos individuales aquí
    
    def action_create_picking(self):
        """Crear movimiento de inventario con bodega configurable"""
        self.ensure_one()

        # Determinar bodega (3 niveles de prioridad):
        # 1. Bodega del empleado (si permitida)
        # 2. Bodega del batch
        # 3. Bodega de la configuración

        location_id = False

        if self.employee_location_id and self.batch_id and self.batch_id.allow_employee_location:
            location_id = self.employee_location_id
        elif self.batch_id and self.batch_id.default_location_id:
            location_id = self.batch_id.default_location_id
        elif self.configuration_id and self.configuration_id.location_id:
            location_id = self.configuration_id.location_id

        if not location_id:
            raise UserError(_('No hay ubicación de EPP configurada'))

        self.location_id = location_id
        
        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'),
            ('warehouse_id.company_id', '=', self.env.company.id)
        ], limit=1)
        
        if not picking_type:
            picking_type = self.env['stock.picking.type'].search([
                ('code', '=', 'outgoing'),
                ('warehouse_id.company_id', '=', self.env.company.id)
            ], limit=1)
        
        if not picking_type:
            raise UserError(_('No hay tipo de movimiento configurado'))
        
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'location_id': self.location_id.id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
            'origin': self.name,
            'partner_id': self.employee_id.work_contact_id.id if self.employee_id.work_contact_id else False,
        })
        
        for line in self.line_ids:
            if line.product_id:
                self.env['stock.move'].create({
                    'name': line.name,
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.quantity,
                    'product_uom': line.product_id.uom_id.id,
                    'picking_id': picking.id,
                    'location_id': self.location_id.id,
                    'location_dest_id': self.env.ref('stock.stock_location_customers').id,
                })
        
        picking.action_confirm()
        self.picking_id = picking
        self.state = 'picking'
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'res_id': picking.id,
            'view_mode': 'form',
        }
    
    def action_deliver(self):
        """Marcar como entregado"""
        self.ensure_one()

        # Validar picking si existe
        if self.picking_id and self.picking_id.state != 'done':
            self.picking_id.button_validate()

        self.state = 'delivered'
        self.delivery_date = fields.Date.today()
        self.delivered_date = fields.Date.today()

        # Generar líneas de entrega si no existen
        if not self.delivery_line_ids:
            self.action_generate_delivery_lines()

        # Registrar en el historial del empleado
        self.env['hr.employee.endowment'].create({
            'contract_id': self.employee_id.contract_id.id,
            'date': self.delivery_date,
            'supplies': '%s - %s' % (self.name, ', '.join(self.line_ids.mapped('name'))),
        })

    def action_generate_delivery_lines(self):
        """Generar líneas de entrega individuales por item"""
        self.ensure_one()

        # Limpiar líneas existentes
        self.delivery_line_ids.unlink()

        # Crear una línea de entrega por cada item solicitado
        for line in self.line_ids:
            self.env['hr.epp.delivery.line'].create({
                'request_id': self.id,
                'request_line_id': line.id,
                'item_type': line.item_type,
                'product_id': line.product_id.id if line.product_id else False,
                'name': line.name,
                'quantity_requested': line.quantity,
                'quantity_delivered': line.quantity,  # Por defecto, se entrega todo
                'size': line.size,
                'delivery_date': fields.Date.today(),
                'state': 'pending',
            })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Líneas de Entrega Generadas'),
                'message': _('Se generaron %d líneas de entrega') % len(self.line_ids),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_cancel(self):
        """Cancelar solicitud"""
        self.ensure_one()

        # Validar que no haya picking en estado done
        if self.picking_id and self.picking_id.state == 'done':
            raise UserError(_('No se puede cancelar una solicitud con movimiento de inventario completado'))

        # Cancelar picking si existe
        if self.picking_id and self.picking_id.state != 'cancel':
            self.picking_id.action_cancel()

        self.state = 'cancelled'

        # Notificar
        self.message_post(
            body=_('Solicitud %s cancelada') % self.name,
            subject=_('Solicitud cancelada')
        )

    def action_print_delivery(self):
        """Imprimir acta de entrega"""
        return self.env.ref('lavish_hr_employee.action_report_epp_delivery').report_action(self)
    
    def action_view_picking(self):
        """Ver movimiento de inventario"""
        self.ensure_one()
        if not self.picking_id:
            raise UserError(_('No hay movimiento de inventario'))

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'res_id': self.picking_id.id,
            'view_mode': 'form',
        }

    def action_view_purchase_order(self):
        """Ver orden de compra"""
        self.ensure_one()
        if not self.purchase_order_id:
            raise UserError(_('No hay orden de compra asociada'))

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'res_id': self.purchase_order_id.id,
            'view_mode': 'form',
        }

    def action_create_purchase_order(self):
        """Crear orden de compra para items faltantes"""
        self.ensure_one()
        
        if not self.configuration_id.supplier_ids:
            raise UserError(_('No hay proveedores configurados'))
        
        supplier = self.configuration_id.supplier_ids[0]
        
        # Crear líneas para productos
        lines = []
        for line in self.line_ids:
            if line.product_id:
                lines.append((0, 0, {
                    'product_id': line.product_id.id,
                    'name': '%s - Talla: %s' % (line.name, line.size) if line.size else line.name,
                    'product_qty': line.quantity,
                    'product_uom': line.product_id.uom_id.id,
                }))
        
        if not lines:
            raise UserError(_('No hay productos configurados para comprar'))
        
        po = self.env['purchase.order'].create({
            'partner_id': supplier.id,
            'origin': self.name,
            'order_line': lines,
        })
        
        self.purchase_order_id = po
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'res_id': po.id,
            'view_mode': 'form',
        }


class HrEppRequestLine(models.Model):
    _name = 'hr.epp.request.line'
    _description = 'Línea de Solicitud EPP'
    
    request_id = fields.Many2one('hr.epp.request', 'Solicitud', ondelete='cascade')
    
    # Producto
    product_id = fields.Many2one('product.product', 'Producto')
    name = fields.Char('Descripción', required=True)
    
    # Cantidad y talla
    quantity = fields.Float('Cantidad', default=1.0, required=True)
    size = fields.Char('Talla')
    
    # Tipo
    item_type = fields.Selection([
        ('shirt', 'Camisa/Suéter'),
        ('pants', 'Pantalón'),
        ('shoes', 'Zapatos'),
        ('helmet', 'Casco'),
        ('gloves', 'Guantes'),
        ('glasses', 'Gafas'),
        ('mask', 'Mascarilla'),
        ('vest', 'Chaleco'),
        ('boots', 'Botas'),
        ('other', 'Otro')
    ], string='Tipo')
    
    requires_size = fields.Boolean('Requiere Talla', compute='_compute_requires_size')
    
    # Notas
    notes = fields.Text('Notas')
    
    @api.depends('item_type', 'product_id')
    def _compute_requires_size(self):
        for line in self:
            line.requires_size = line.item_type in ['shirt', 'pants', 'shoes', 'boots']
    
    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.name = self.product_id.name


class HrEppDeliveryLine(models.Model):
    _name = 'hr.epp.delivery.line'
    _description = 'Línea de Entrega EPP'
    _order = 'delivery_date desc, id desc'

    request_id = fields.Many2one('hr.epp.request', 'Solicitud', required=True, ondelete='cascade')
    request_line_id = fields.Many2one('hr.epp.request.line', 'Línea de Solicitud', ondelete='set null')

    employee_id = fields.Many2one('hr.employee', 'Empleado', related='request_id.employee_id', store=True, readonly=True)

    # Producto
    product_id = fields.Many2one('product.product', 'Producto')
    name = fields.Char('Descripción', required=True)

    # Tipo de item
    item_type = fields.Selection([
        ('shirt', 'Camisa/Suéter'),
        ('pants', 'Pantalón'),
        ('shoes', 'Zapatos'),
        ('helmet', 'Casco'),
        ('gloves', 'Guantes'),
        ('glasses', 'Gafas'),
        ('mask', 'Mascarilla'),
        ('vest', 'Chaleco'),
        ('boots', 'Botas'),
        ('other', 'Otro')
    ], string='Tipo')

    # Cantidades
    quantity_requested = fields.Float('Cantidad Solicitada', default=1.0)
    quantity_delivered = fields.Float('Cantidad Entregada', default=1.0)
    size = fields.Char('Talla')

    # Fechas
    delivery_date = fields.Date('Fecha de Entrega', default=fields.Date.today)
    delivered_date = fields.Datetime('Fecha/Hora Entregado')

    # Estado
    state = fields.Selection([
        ('pending', 'Pendiente'),
        ('delivered', 'Entregado'),
        ('rejected', 'Rechazado')
    ], string='Estado', default='pending', required=True)

    # Firma y recepción
    signature = fields.Binary('Firma de Recibido')
    signed_by = fields.Char('Recibido por')
    signed_date = fields.Datetime('Fecha/Hora de Firma')

    # Observaciones
    notes = fields.Text('Observaciones')

    def action_mark_delivered(self):
        """Marcar línea como entregada"""
        for line in self:
            line.write({
                'state': 'delivered',
                'delivered_date': fields.Datetime.now(),
            })

    def action_mark_rejected(self):
        """Marcar línea como rechazada"""
        for line in self:
            line.write({
                'state': 'rejected',
            })