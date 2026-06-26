# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class PaymentRequest(models.Model):
    _name = 'payment.request'
    _description = 'Solicitud de Pago'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(string='Referencia', required=True, copy=False, readonly=True, default='Nuevo')
    active = fields.Boolean(default=True)
    memo = fields.Char(string='Memo', help='Concepto o referencia corta', tracking=True)
    partner_id = fields.Many2one('res.partner', string='Proveedor/Cliente', required=True, tracking=True)
    request_type = fields.Selection([
        ('supplier', 'Pago a Proveedor'),
        ('customer', 'Cobro a Cliente'),
        ('advance', 'Anticipo'),
    ], string='Tipo', required=True, default='supplier', tracking=True)

    # ========== TIPO DE ANTICIPO ==========
    advance_type_id = fields.Many2one(
        'advance.type',
        string='Tipo de Anticipo',
        tracking=True,
        help='Tipo de anticipo que controla validaciones y comportamiento'
    )

    # Campos relacionados del tipo de anticipo
    allow_sale_orders = fields.Boolean(related='advance_type_id.allow_sale_orders', readonly=True)
    allow_purchase_orders = fields.Boolean(related='advance_type_id.allow_purchase_orders', readonly=True)
    require_orders = fields.Boolean(related='advance_type_id.require_orders', readonly=True)
    auto_fill_amount = fields.Boolean(related='advance_type_id.auto_fill_amount', readonly=True)
    percentage_advance = fields.Float(related='advance_type_id.percentage_advance', readonly=True)

    amount = fields.Monetary(string='Monto', required=True, tracking=True)
    currency_id = fields.Many2one('res.currency', string='Moneda',
                                  default=lambda self: self.env.company.currency_id, required=True)

    date_request = fields.Date(string='Fecha Solicitud', default=fields.Date.context_today, required=True)
    date_due = fields.Date(string='Fecha Vencimiento')

    # Etapas con kanban (estilo CRM)
    stage_id = fields.Many2one('payment.request.stage', string='Etapa', tracking=True,
                               group_expand='_read_group_stage_ids', copy=False,
                               default=lambda self: self._get_default_stage_id())

    # Estados basados en etapa
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('requested', 'Solicitado'),
        ('approved', 'Aprobado'),
        ('paid', 'Pagado'),
        ('cancelled', 'Cancelado'),
    ], string='Estado', compute='_compute_state', store=True, tracking=True)

    # ========== NUEVO: ÓRDENES ASOCIADAS ==========

    sale_order_ids = fields.Many2many(
        'sale.order',
        'payment_request_sale_order_rel',
        'request_id',
        'order_id',
        string='Pedidos de Venta',
        domain="[('partner_id', '=', partner_id)]"
    )

    purchase_order_ids = fields.Many2many(
        'purchase.order',
        'payment_request_purchase_order_rel',
        'request_id',
        'order_id',
        string='Órdenes de Compra',
        domain="[('partner_id', '=', partner_id)]"
    )

    invoice_ids = fields.Many2many('account.move', string='Facturas',
                                   domain="[('partner_id', '=', partner_id), ('state', '=', 'posted')]")

    # ========== ANTICIPOS ASOCIADOS ==========
    advance_payment_ids = fields.Many2many(
        'account.payment',
        'payment_request_advance_payment_rel',
        'request_id',
        'payment_id',
        string='Anticipos a Aplicar',
        domain="[('partner_id', '=', partner_id), ('advance', '=', True), ('state', '=', 'posted')]",
        help='Anticipos existentes que se aplicarán a esta solicitud'
    )

    total_advances_amount = fields.Monetary(
        string='Total Anticipos',
        compute='_compute_advances_amount',
        currency_field='currency_id',
        store=True
    )

    payment_id = fields.Many2one('account.payment', string='Pago', readonly=True)

    # Contadores para smartbuttons
    sale_count = fields.Integer(compute='_compute_doc_counts')
    purchase_count = fields.Integer(compute='_compute_doc_counts')
    invoice_count = fields.Integer(compute='_compute_doc_counts')
    advance_count = fields.Integer(compute='_compute_doc_counts')

    # Control de facturación y anticipos
    orders_fully_invoiced = fields.Boolean(
        string='Órdenes Completamente Facturadas',
        compute='_compute_invoice_status',
        store=True,
        help='Indica si todas las órdenes asociadas están completamente facturadas'
    )
    can_apply_advances = fields.Boolean(
        string='Puede Aplicar Anticipos',
        compute='_compute_can_apply_advances',
        help='Indica si se pueden aplicar anticipos a las facturas'
    )
    advances_applied = fields.Boolean(
        string='Anticipos Aplicados',
        default=False,
        help='Indica si los anticipos ya fueron aplicados a las facturas'
    )

    # ========== FIN NUEVO ==========

    description = fields.Text(string='Descripción')
    company_id = fields.Many2one('res.company', string='Compañía',
                                 default=lambda self: self.env.company, required=True)

    # Aprobación automática
    requires_approval = fields.Boolean(string='Requiere Aprobación', compute='_compute_requires_approval')
    minimum_approval_amount = fields.Float(string='Monto Mínimo para Aprobación',
                                          default=50000.0,
                                          help='Si el monto es mayor a este valor, requiere aprobación')

    # Colores para kanban
    color = fields.Integer(string='Color')
    priority = fields.Selection([
        ('0', 'Normal'),
        ('1', 'Alta'),
    ], string='Prioridad', default='0')

    # ========== NUEVO: CAMPO PARA PUBLICAR ==========
    is_published = fields.Boolean(string='Publicado', default=False, tracking=True)

    # ========== CAMPOS DE APROBACIÓN CON LÍMITES ==========

    suggested_approver_ids = fields.Many2many(
        'res.users',
        'payment_request_suggested_approver_rel',
        'request_id',
        'user_id',
        string='Aprobadores Sugeridos',
        compute='_compute_suggested_approvers',
        help='Usuarios que pueden aprobar según límites configurados'
    )

    approved_by_id = fields.Many2one(
        'res.users',
        string='Aprobado Por',
        readonly=True,
        tracking=True
    )

    approval_date = fields.Datetime(
        string='Fecha Aprobación',
        readonly=True
    )

    can_current_user_approve = fields.Boolean(
        string='Puede Aprobar',
        compute='_compute_can_current_user_approve',
        help='Indica si el usuario actual puede aprobar esta solicitud'
    )

    @api.depends('amount', 'currency_id', 'request_type', 'partner_id', 'company_id')
    def _compute_suggested_approvers(self):
        """Calcula aprobadores sugeridos según límites configurados"""
        for request in self:
            limits_model = self.env['advance.approval.limit']
            approvers = limits_model.get_approvers_for_request(request)
            request.suggested_approver_ids = [(6, 0, approvers.ids)]

    @api.depends('amount', 'currency_id', 'request_type', 'partner_id', 'company_id')
    def _compute_can_current_user_approve(self):
        """Verifica si el usuario actual puede aprobar"""
        for request in self:
            current_user = self.env.user

            # Superusuario siempre puede aprobar
            if current_user.id == self.env.ref('base.user_admin').id:
                request.can_current_user_approve = True
                continue

            # Verificar si está en la lista de aprobadores sugeridos
            request.can_current_user_approve = current_user in request.suggested_approver_ids

    @api.depends('stage_id')
    def _compute_state(self):
        for request in self:
            if not request.stage_id:
                request.state = 'draft'
            elif request.stage_id.is_cancelled:
                request.state = 'cancelled'
            elif request.stage_id.is_paid:
                request.state = 'paid'
            elif request.stage_id.is_approved:
                request.state = 'approved'
            elif request.stage_id.sequence > 10:
                request.state = 'requested'
            else:
                request.state = 'draft'

    @api.depends('amount')
    def _compute_requires_approval(self):
        min_amount = self.env['ir.config_parameter'].sudo().get_param('payment_request.minimum_approval_amount', 50000.0)
        for request in self:
            request.requires_approval = request.amount > float(min_amount)

    def _get_default_stage_id(self):
        return self.env['payment.request.stage'].search([('sequence', '=', 1)], limit=1).id

    @api.model
    def _read_group_stage_ids(self, stages, domain, order):
        return stages.search([], order=order)

    # ========== ONCHANGE METHODS ==========

    @api.onchange('advance_type_id')
    def _onchange_advance_type_id(self):
        """Actualizar tipo de solicitud según tipo de anticipo"""
        if self.advance_type_id:
            self.request_type = 'advance'

            # Limpiar órdenes que no están permitidas
            if not self.advance_type_id.allow_sale_orders:
                self.sale_order_ids = [(5, 0, 0)]
            if not self.advance_type_id.allow_purchase_orders:
                self.purchase_order_ids = [(5, 0, 0)]

    @api.onchange('sale_order_ids', 'purchase_order_ids')
    def _onchange_orders(self):
        """Calcular monto automático desde órdenes"""
        if not self.auto_fill_amount or not self.advance_type_id:
            return

        total = 0.0

        # Sumar pedidos de venta
        if self.allow_sale_orders and self.sale_order_ids:
            for order in self.sale_order_ids:
                total += order.amount_total

        # Sumar órdenes de compra
        if self.allow_purchase_orders and self.purchase_order_ids:
            for order in self.purchase_order_ids:
                total += order.amount_total

        # Aplicar porcentaje
        if total > 0 and self.percentage_advance:
            self.amount = total * (self.percentage_advance / 100.0)

    @api.onchange('request_type')
    def _onchange_request_type(self):
        """Limpiar tipo de anticipo si no es anticipo"""
        if self.request_type != 'advance':
            self.advance_type_id = False

    # ========== CONSTRAINTS ==========

    @api.constrains('advance_type_id', 'sale_order_ids', 'purchase_order_ids')
    def _check_advance_type_orders(self):
        """Validar que las órdenes sean compatibles con el tipo"""
        for request in self:
            if not request.advance_type_id:
                continue

            # Validar órdenes de venta
            if request.sale_order_ids and not request.allow_sale_orders:
                raise UserError(_(
                    'El tipo de anticipo "%s" no permite asociar órdenes de venta'
                ) % request.advance_type_id.name)

            # Validar órdenes de compra
            if request.purchase_order_ids and not request.allow_purchase_orders:
                raise UserError(_(
                    'El tipo de anticipo "%s" no permite asociar órdenes de compra'
                ) % request.advance_type_id.name)

            # Validar que haya órdenes si es requerido
            if request.require_orders:
                if not request.sale_order_ids and not request.purchase_order_ids:
                    raise UserError(_(
                        'El tipo de anticipo "%s" requiere asociar al menos una orden'
                    ) % request.advance_type_id.name)

    @api.constrains('advance_type_id', 'amount')
    def _check_advance_type_max_amount(self):
        """Validar monto máximo según tipo"""
        for request in self:
            if not request.advance_type_id:
                continue

            if request.advance_type_id.max_amount > 0:
                if request.amount > request.advance_type_id.max_amount:
                    raise UserError(_(
                        'El monto %.2f excede el límite máximo de %.2f para el tipo "%s"'
                    ) % (request.amount, request.advance_type_id.max_amount, request.advance_type_id.name))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('payment.request') or 'Nuevo'
        return super(PaymentRequest, self).create(vals_list)

    def action_request(self):
        """Enviar solicitud"""
        self.ensure_one()
        self.state = 'requested'
        return True

    def action_approve(self):
        """Aprobar solicitud - CON VALIDACIÓN DE LÍMITES"""
        self.ensure_one()

        # Verificar si el usuario actual puede aprobar según límites
        if not self.can_current_user_approve:
            raise UserError(_(
                'No tiene autorización para aprobar esta solicitud.\n'
                'Monto: %s %s\n'
                'Aprobadores sugeridos: %s'
            ) % (
                self.amount,
                self.currency_id.name,
                ', '.join(self.suggested_approver_ids.mapped('name')) or 'Ninguno'
            ))

        # Registrar aprobación
        self.write({
            'state': 'approved',
            'approved_by_id': self.env.user.id,
            'approval_date': fields.Datetime.now(),
        })

        # Notificar
        self.message_post(
            body=_('Solicitud aprobada por %s') % self.env.user.name,
            subject=_('Aprobación'),
            message_type='notification'
        )

        return True

    def action_cancel(self):
        """Cancelar solicitud"""
        self.ensure_one()
        if self.state == 'paid':
            raise UserError(_('No se puede cancelar una solicitud pagada'))
        self.state = 'cancelled'
        return True

    def action_create_payment(self):
        """Crear pago desde la solicitud"""
        self.ensure_one()
        if self.state != 'approved':
            raise UserError(_('Solo se pueden pagar solicitudes aprobadas'))

        payment_vals = {
            'partner_id': self.partner_id.id,
            'amount': self.amount,
            'currency_id': self.currency_id.id,
            'date': fields.Date.context_today(self),
            'payment_type': self.request_type == 'customer' and 'inbound' or 'outbound',
            'partner_type': self.request_type == 'customer' and 'customer' or 'supplier',
        }

        payment = self.env['account.payment'].create(payment_vals)
        self.payment_id = payment.id
        self.state = 'paid'

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'res_id': payment.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ========== NUEVOS MÉTODOS ==========

    @api.depends('sale_order_ids', 'purchase_order_ids', 'invoice_ids')
    @api.depends('advance_payment_ids')
    def _compute_advances_amount(self):
        """Calcular total de anticipos asociados"""
        for rec in self:
            rec.total_advances_amount = sum(rec.advance_payment_ids.mapped('amount'))

    def _compute_doc_counts(self):
        for rec in self:
            rec.sale_count = len(rec.sale_order_ids)
            rec.purchase_count = len(rec.purchase_order_ids)
            rec.invoice_count = len(rec.invoice_ids)
            rec.advance_count = len(rec.advance_payment_ids)

    @api.depends('sale_order_ids.invoice_status', 'purchase_order_ids.invoice_status')
    def _compute_invoice_status(self):
        """Verifica si todas las órdenes están completamente facturadas"""
        for rec in self:
            fully_invoiced = True

            # Verificar pedidos de venta
            for order in rec.sale_order_ids:
                if order.invoice_status != 'invoiced':
                    fully_invoiced = False
                    break

            # Verificar órdenes de compra
            if fully_invoiced:
                for order in rec.purchase_order_ids:
                    if order.invoice_status != 'invoiced':
                        fully_invoiced = False
                        break

            rec.orders_fully_invoiced = fully_invoiced and (rec.sale_order_ids or rec.purchase_order_ids)

    @api.depends('orders_fully_invoiced', 'advance_payment_ids', 'invoice_ids', 'advances_applied')
    def _compute_can_apply_advances(self):
        """Verifica si se pueden aplicar anticipos a las facturas"""
        for rec in self:
            rec.can_apply_advances = (
                rec.orders_fully_invoiced and
                rec.advance_payment_ids and
                rec.invoice_ids and
                not rec.advances_applied and
                any(inv.state == 'posted' for inv in rec.invoice_ids)
            )

    def action_load_advances(self):
        """Cargar anticipos disponibles del tercero"""
        self.ensure_one()

        if not self.partner_id:
            raise UserError(_('Debe seleccionar un tercero primero'))

        # Buscar anticipos disponibles del tercero
        available_advances = self.env['account.payment'].search([
            ('partner_id', '=', self.partner_id.id),
            ('advance', '=', True),
            ('state', '=', 'posted'),
        ])

        if not available_advances:
            raise UserError(_('No hay anticipos disponibles para %s') % self.partner_id.name)

        # Asociar anticipos
        self.advance_payment_ids = [(6, 0, available_advances.ids)]

        # Mensaje en chatter
        self.message_post(
            body=_('Se cargaron %d anticipos disponibles del tercero') % len(available_advances),
            subject=_('Anticipos Cargados'),
            message_type='notification'
        )

        return True

    def action_add_orders_wizard(self):
        """Abrir wizard para agregar órdenes"""
        self.ensure_one()
        return {
            'name': _('Agregar Órdenes'),
            'type': 'ir.actions.act_window',
            'res_model': 'payment.request.add.orders',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_request_id': self.id}
        }

    def action_publish(self):
        """Publicar solicitud (marca como lista)"""
        for rec in self:
            if not rec.sale_order_ids and not rec.purchase_order_ids:
                raise UserError(_('Agregue al menos una orden antes de publicar'))
            rec.is_published = True

    def action_create_invoice_from_orders(self):
        """Crear factura desde órdenes asociadas"""
        self.ensure_one()

        if not self.is_published:
            raise UserError(_('Publique la solicitud primero'))

        lines = []

        # Desde ventas
        for order in self.sale_order_ids:
            for line in order.order_line.filtered(lambda l: l.qty_to_invoice > 0):
                lines.append((0, 0, {
                    'product_id': line.product_id.id,
                    'name': line.name,
                    'quantity': line.qty_to_invoice,
                    'price_unit': line.price_unit,
                    'tax_ids': [(6, 0, line.tax_id.ids)],
                    'sale_line_ids': [(4, line.id)],
                }))

        # Desde compras
        for order in self.purchase_order_ids:
            for line in order.order_line.filtered(lambda l: l.qty_to_invoice > 0):
                lines.append((0, 0, {
                    'product_id': line.product_id.id,
                    'name': line.name,
                    'quantity': line.qty_to_invoice,
                    'price_unit': line.price_unit,
                    'tax_ids': [(6, 0, line.taxes_id.ids)],
                    'purchase_line_id': line.id,
                }))

        if not lines:
            raise UserError(_('No hay líneas para facturar'))

        move_type = 'out_invoice' if self.sale_order_ids else 'in_invoice'

        invoice = self.env['account.move'].create({
            'move_type': move_type,
            'partner_id': self.partner_id.id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': lines,
            'ref': self.name,
        })

        self.invoice_ids = [(4, invoice.id)]

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': invoice.id,
            'view_mode': 'form',
        }

    def action_apply_advances_to_invoices(self):
        """Aplicar anticipos a las facturas generadas"""
        self.ensure_one()

        if not self.can_apply_advances:
            raise UserError(_(
                'No se pueden aplicar anticipos. Verifique que:\n'
                '- Las órdenes estén completamente facturadas\n'
                '- Existan anticipos asociados\n'
                '- Existan facturas contabilizadas\n'
                '- Los anticipos no hayan sido aplicados previamente'
            ))

        # Obtener facturas contabilizadas con saldo pendiente
        invoices_to_pay = self.invoice_ids.filtered(
            lambda inv: inv.state == 'posted' and inv.amount_residual > 0
        )

        if not invoices_to_pay:
            raise UserError(_('No hay facturas contabilizadas con saldo pendiente'))

        # Obtener anticipos disponibles
        advances = self.advance_payment_ids.filtered(lambda a: a.state == 'posted')

        if not advances:
            raise UserError(_('No hay anticipos contabilizados disponibles'))

        # Buscar líneas de anticipo en cuentas de anticipo
        advance_lines = self.env['account.move.line'].search([
            ('payment_id', 'in', advances.ids),
            ('account_id.is_advance_account', '=', True),
            ('reconciled', '=', False),
            ('parent_state', '=', 'posted'),
            '|', ('amount_residual', '!=', 0.0), ('amount_residual_currency', '!=', 0.0),
        ])

        if not advance_lines:
            raise UserError(_('No se encontraron líneas de anticipo disponibles para aplicar'))

        applied_count = 0
        total_applied = 0.0

        # Aplicar cada línea de anticipo a las facturas
        for advance_line in advance_lines:
            if not invoices_to_pay:
                break  # Ya no hay facturas pendientes

            for invoice in invoices_to_pay:
                if invoice.amount_residual <= 0:
                    continue  # Esta factura ya está pagada

                try:
                    # Usar el método nativo de Odoo para aplicar el crédito pendiente
                    invoice.js_assign_outstanding_line(advance_line.id)
                    applied_count += 1
                    total_applied += abs(advance_line.amount_residual)

                    # Si el anticipo se agotó, pasar al siguiente
                    if advance_line.reconciled or advance_line.amount_residual == 0:
                        break

                except Exception as e:
                    # Registrar el error pero continuar con los demás
                    self.message_post(
                        body=_('Error al aplicar anticipo %s a factura %s: %s') % (
                            advance_line.move_id.name,
                            invoice.name,
                            str(e)
                        ),
                        message_type='notification'
                    )

        if applied_count == 0:
            raise UserError(_('No se pudo aplicar ningún anticipo. Verifique los montos y estados.'))

        # Marcar como aplicados
        self.advances_applied = True

        # Mensaje de éxito
        self.message_post(
            body=_('Se aplicaron %d anticipo(s) por un total de %s a las facturas') % (
                applied_count,
                '{:,.2f}'.format(total_applied)
            ),
            subject=_('Anticipos Aplicados'),
            message_type='notification'
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Anticipos Aplicados'),
                'message': _('Se aplicaron %d anticipo(s) por un total de %s') % (
                    applied_count,
                    '{:,.2f}'.format(total_applied)
                ),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_force_reconcile_invoices(self):
        """Forzar conciliación de facturas con pagos"""
        self.ensure_one()

        for invoice in self.invoice_ids.filtered(lambda i: i.state == 'posted' and i.amount_residual > 0):
            # Buscar pagos pendientes del partner
            lines = self.env['account.move.line'].search([
                ('partner_id', '=', invoice.commercial_partner_id.id),
                ('account_id.account_type', 'in', ['asset_receivable', 'liability_payable']),
                ('reconciled', '=', False),
                ('parent_state', '=', 'posted'),
            ])

            if lines:
                invoice_lines = invoice.line_ids.filtered(
                    lambda l: l.account_id.account_type in ['asset_receivable', 'liability_payable']
                    and not l.reconciled
                )

                to_reconcile = lines + invoice_lines
                for account in to_reconcile.account_id:
                    acc_lines = to_reconcile.filtered(lambda l: l.account_id == account)
                    if len(acc_lines) > 1:
                        try:
                            acc_lines.reconcile()
                        except:
                            pass

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': _('Conciliación completada'),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_view_sales(self):
        return {
            'name': _('Pedidos de Venta'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.sale_order_ids.ids)],
        }

    def action_view_purchases(self):
        return {
            'name': _('Órdenes de Compra'),
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.purchase_order_ids.ids)],
        }

    def action_view_invoices(self):
        return {
            'name': _('Facturas'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.invoice_ids.ids)],
        }


class PaymentRequestAddOrders(models.TransientModel):
    """Wizard simple para agregar órdenes"""
    _name = 'payment.request.add.orders'
    _description = 'Agregar Órdenes a Solicitud'

    request_id = fields.Many2one('payment.request', required=True)
    partner_id = fields.Many2one('res.partner', related='request_id.partner_id')

    sale_order_ids = fields.Many2many(
        'sale.order',
        string='Pedidos de Venta',
        domain="[('partner_id', '=', partner_id), ('state', 'in', ['sale', 'done'])]"
    )

    purchase_order_ids = fields.Many2many(
        'purchase.order',
        string='Órdenes de Compra',
        domain="[('partner_id', '=', partner_id), ('state', 'in', ['purchase', 'done'])]"
    )

    def action_add(self):
        if self.sale_order_ids:
            self.request_id.sale_order_ids = [(4, oid) for oid in self.sale_order_ids.ids]

        if self.purchase_order_ids:
            self.request_id.purchase_order_ids = [(4, oid) for oid in self.purchase_order_ids.ids]

        return {'type': 'ir.actions.act_window_close'}


class PaymentRequestStage(models.Model):
    """Etapas de Solicitud de Pago"""
    _name = 'payment.request.stage'
    _description = 'Etapas de Solicitud de Pago'
    _order = 'sequence, id'

    name = fields.Char(string='Nombre', required=True)
    sequence = fields.Integer(string='Secuencia', default=10)
    fold = fields.Boolean(string='Plegado en Kanban')

    # Estados específicos
    is_approved = fields.Boolean(string='Es Aprobado', help='Marcar si esta etapa significa aprobación')
    is_paid = fields.Boolean(string='Es Pagado', help='Marcar si esta etapa significa pago realizado')
    is_cancelled = fields.Boolean(string='Es Cancelado', help='Marcar si esta etapa significa cancelación')

    # Configuración de aprobación
    approval_amount = fields.Float(
        string='Monto Mínimo para Aprobación',
        help='Monto mínimo requerido para necesitar aprobación en esta etapa'
    )
    approval_group_id = fields.Many2one(
        'res.groups',
        string='Grupo de Aprobación',
        help='Grupo que puede aprobar en esta etapa'
    )