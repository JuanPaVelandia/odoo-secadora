# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)


class AdvanceRequest(models.Model):
    """Modelo para solicitudes de anticipo con flujo tipo CRM"""
    _name = 'advance.request'
    _description = 'Solicitud de Anticipo'
    _inherit = ['mail.activity.mixin',
                'mail.tracking.duration.mixin', 'analytic.mixin']
    _order = 'priority desc, create_date desc'
    _rec_name = 'name'
    _track_duration_field = 'stage_id'  # Campo para tracking de duración en etapas

    # Campos básicos
    name = fields.Char(
        string='Referencia',
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default='Nuevo'
    )

    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company
    )

    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        required=True,
        default=lambda self: self.env.company.currency_id
    )

    # Tipo y configuración
    advance_type_id = fields.Many2one(
        'advance.type',
        string='Tipo de Anticipo',
        required=False,  # No es obligatorio
        tracking=True,
        help='Define el tipo y flujo del anticipo. AVISO: Configure el tipo para definir la cuenta contable.'
    )

    request_type = fields.Selection([
        ('customer', 'Anticipo de Cliente'),
        ('supplier', 'Anticipo a Proveedor'),
        ('employee', 'Anticipo a Empleado'),
        ('other', 'Otro')
    ],
        string='Tipo de Solicitud',
        compute='_compute_request_type',
        store=True,
        readonly=False
    )

    # Etapas CRM
    stage_id = fields.Many2one(
        'advance.request.stage',
        string='Etapa',
        group_expand='_group_expand_stage_id',
        tracking=True,
        copy=False,
        index=True,
        domain="[('advance_type_ids', 'in', advance_type_id)]",
        default=lambda self: self._get_default_stage_id()
    )

    # Campo para tracking si hay pago generado (solo info, no es un estado)
    has_payment = fields.Boolean(
        string='Tiene Pago',
        compute='_compute_has_payment',
        store=True
    )

    is_paid = fields.Boolean(
        string='Pagado',
        compute='_compute_payment_status',
        store=True
    )

    is_reconciled = fields.Boolean(
        string='Conciliado',
        compute='_compute_payment_status',
        store=True
    )

    priority = fields.Selection([
        ('0', 'Baja'),
        ('1', 'Normal'),
        ('2', 'Alta'),
        ('3', 'Urgente')
    ],
        string='Prioridad',
        default='1',
        index=True
    )

    color = fields.Integer(
        string='Color',
        default=0
    )

    kanban_state = fields.Selection([
        ('normal', 'En progreso'),
        ('done', 'Listo'),
        ('blocked', 'Bloqueado')
    ],
        string='Estado Kanban',
        default='normal',
        tracking=True
    )

    # Información del partner
    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente/Proveedor',
        required=True,
        tracking=True
    )

    partner_type = fields.Selection(
        [('customer', 'Cliente'), ('supplier', 'Proveedor')],
        string='Tipo de Partner',
        compute='_compute_partner_type',
        store=True
    )
    is_defaulted = fields.Boolean(
        string='¿Es por defecto?',
        default=False
    )
    # Montos
    amount_requested = fields.Monetary(
        string='Monto Solicitado',
        currency_field='currency_id',
        required=True,
        tracking=True
    )

    amount_suggested = fields.Monetary(
        string='Monto Sugerido',
        currency_field='currency_id',
        compute='_compute_amount_suggested',
        store=False,
        help='Monto sugerido basado en el tipo de anticipo y contexto'
    )

    amount_approved = fields.Monetary(
        string='Monto Aprobado',
        currency_field='currency_id',
        tracking=True
    )

    amount_paid = fields.Monetary(
        string='Monto Pagado',
        currency_field='currency_id',
        compute='_compute_amounts',
        store=True
    )

    amount_available = fields.Monetary(
        string='Saldo Disponible',
        currency_field='currency_id',
        compute='_compute_amounts',
        store=True,
        help='Saldo disponible del anticipo'
    )

    amount_reconciled = fields.Monetary(
        string='Monto Aplicado',
        currency_field='currency_id',
        compute='_compute_amounts',
        store=True,
        help='Monto aplicado a facturas'
    )

    # Fechas
    date_request = fields.Date(
        string='Fecha Solicitud',
        default=fields.Date.today,
        required=True,
        tracking=True
    )

    date_due = fields.Date(
        string='Fecha Requerida',
        tracking=True
    )

    date_approved = fields.Datetime(
        string='Fecha Aprobación',
        readonly=True,
        copy=False
    )

    date_last_stage_update = fields.Datetime(
        string='Última Actualización de Etapa',
        compute='_compute_date_last_stage_update',
        store=True,
        index=True,
        help='Fecha de la última vez que se cambió de etapa'
    )

    date_paid = fields.Datetime(
        string='Fecha de Pago',
        readonly=True,
        copy=False
    )

    # Usuarios
    user_id = fields.Many2one(
        'res.users',
        string='Responsable',
        default=lambda self: self.env.user,
        tracking=True
    )

    approved_by = fields.Many2one(
        'res.users',
        string='Aprobado por',
        readonly=True,
        copy=False
    )

    # Aprobadores sugeridos
    suggested_approver_ids = fields.Many2many(
        'res.users',
        'advance_request_approver_rel',
        'request_id',
        'user_id',
        string='Aprobadores Sugeridos',
        compute='_compute_suggested_approvers'
    )

    approval_limit_ids = fields.One2many(
        'advance.approval.limit',
        compute='_compute_approval_limits',
        string='Límites de Aprobación'
    )

    # Relaciones con otros documentos
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Orden de Venta',
        help='Orden de venta relacionada'
    )

    sale_line_ids = fields.Many2many(
        'sale.order.line',
        'advance_request_sale_line_rel',
        'request_id',
        'line_id',
        string='Líneas de Venta',
        help='Líneas específicas de la orden de venta para este anticipo'
    )

    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='Orden de Compra',
        help='Orden de compra relacionada'
    )

    purchase_line_ids = fields.Many2many(
        'purchase.order.line',
        'advance_request_purchase_line_rel',
        'request_id',
        'line_id',
        string='Líneas de Compra',
        help='Líneas específicas de la orden de compra para este anticipo'
    )

    # Campo de adjuntos
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'advance_request_attachment_rel',
        'request_id',
        'attachment_id',
        string='Adjuntos',
        help='Documentos adjuntos a la solicitud'
    )

    payment_ids = fields.One2many(
        'account.payment',
        'advance_request_id',
        string='Pagos',
        readonly=True
    )

    payment_count = fields.Integer(
        string='# Pagos',
        compute='_compute_payment_count'
    )

    invoice_ids = fields.Many2many(
        'account.move',
        'advance_request_invoice_rel',
        'request_id',
        'invoice_id',
        string='Facturas Aplicadas',
        domain=[('move_type', 'in', ['out_invoice', 'in_invoice'])],
        readonly=True
    )

    invoice_count = fields.Integer(
        string='# Facturas',
        compute='_compute_invoice_count'
    )

    reconciliation_ids = fields.One2many(
        'advance.reconciliation',
        'request_id',
        string='Conciliaciones',
        readonly=True
    )

    # Los campos analytic_distribution y analytic_precision vienen del mixin analytic.mixin
    # Solo necesitamos el campo computado para compatibilidad
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Cuenta Analítica',
        compute='_compute_analytic_account',
        store=True
    )

    # Información adicional
    description = fields.Text(
        string='Descripción'
    )

    notes = fields.Text(
        string='Notas Internas'
    )

    rejection_reason = fields.Text(
        string='Motivo de Rechazo',
        readonly=True
    )

    # Configuración de auto-conciliación
    auto_reconcile = fields.Boolean(
        string='Auto-conciliar',
        default=True,
        help='Conciliar automáticamente con facturas cuando se confirme'
    )

    reconcile_warning_shown = fields.Boolean(
        string='Aviso mostrado',
        default=False
    )

    # Campo técnico para usar en vistas
    stage_code = fields.Char(
        string='Código de Etapa',
        compute='_compute_stage_code',
        store=True,
        help='Campo técnico para validaciones en vistas'
    )

    # Campos computados para dashboard
    days_overdue = fields.Integer(
        string='Días Vencidos',
        compute='_compute_days_overdue'
    )

    progress = fields.Float(
        string='Progreso %',
        compute='_compute_progress',
        store=True
    )

    # Actividades predeterminadas
    activity_date_deadline = fields.Date(
        string='Próxima Actividad',
        related='activity_ids.date_deadline',
        readonly=True
    )

    # Tracking de tiempo en etapas
    stage_enter_date = fields.Datetime(
        string='Fecha entrada etapa',
        help='Fecha y hora cuando entró a la etapa actual'
    )

    stage_duration = fields.Float(
        string='Tiempo en etapa',
        compute='_compute_stage_duration',
        help='Tiempo en la etapa actual (en horas)'
    )

    stage_history_ids = fields.One2many(
        'advance.request.stage.history',
        'request_id',
        string='Historial de Etapas'
    )

    # Campos adicionales para reportes
    amount_in_words = fields.Char(
        string='Monto en Palabras',
        compute='_compute_amount_in_words'
    )

    amount_applied = fields.Monetary(
        string='Monto Aplicado',
        currency_field='currency_id',
        compute='_compute_amounts',
        store=True
    )

    balance_pending = fields.Monetary(
        string='Saldo Pendiente',
        currency_field='currency_id',
        compute='_compute_amounts',
        store=True
    )

    # Campos de garantía
    requires_guarantee = fields.Boolean(
        string='Requiere Garantía',
        default=False
    )

    guarantee_type = fields.Selection([
        ('personal', 'Personal'),
        ('bank', 'Bancaria'),
        ('property', 'Propiedad'),
        ('other', 'Otra')
    ],
        string='Tipo de Garantía'
    )
    
    guarantee_description = fields.Text(
        string='Descripción de Garantía'
    )

    guarantee_amount = fields.Monetary(
        string='Monto de Garantía',
        currency_field='currency_id'
    )

    # Líneas de aplicación/reconciliación
    reconcile_line_ids = fields.One2many(
        'advance.request.reconcile.line',
        'request_id',
        string='Líneas de Aplicación'
    )

    @api.model
    def _get_default_stage_id(self):
        """Obtiene la etapa por defecto para nuevas solicitudes"""
        # Primero buscar etapa con código 'draft'
        stage = self.env['advance.request.stage'].search([
            ('code', '=', 'draft')
        ], limit=1)
        # Si no existe, buscar la etapa marcada como default
        if not stage:
            stage = self.env['advance.request.stage'].search([
                ('is_default', '=', True)
            ], limit=1)
        # Si aún no hay, tomar la primera por secuencia
        if not stage:
            stage = self.env['advance.request.stage'].search([], order='sequence', limit=1)
        return stage

    @api.model
    def _group_expand_stage_id(self, stages, domain):
        """Expande todas las etapas en vista kanban"""
        request_type = self.env.context.get('default_request_type', False)
        #if request_type:
        #    search_domain = [('partner_type', '=', partner_type)]
        #else:
        search_domain = []
        stage_ids = stages._search(search_domain, order=stages._order)
        return stages.browse(stage_ids)

    @api.depends('analytic_distribution')
    def _compute_analytic_account(self):
        """Calcula la cuenta analítica desde la distribución"""
        for record in self:
            if record.analytic_distribution:
                account_ids = list(record.analytic_distribution.keys())
                if account_ids:
                    record.analytic_account_id = int(account_ids[0])
            else:
                record.analytic_account_id = False

    @api.depends('amount_requested', 'advance_type_id', 'stage_id', 'partner_id')
    def _compute_suggested_approvers(self):
        """Calcula los aprobadores sugeridos según el monto y configuración"""
        ApprovalLimit = self.env['advance.approval.limit']

        for record in self:
            approvers = self.env['res.users']

            # Buscar aprobadores que pueden aprobar este monto
            limits = ApprovalLimit.search([
                ('active', '=', True),
                ('company_id', '=', record.company_id.id)
            ])

            for limit in limits:
                if limit.can_approve_amount(
                    record.amount_requested,
                    advance_type=record.advance_type_id,
                    partner=record.partner_id,
                    stage=record.stage_id
                ):
                    # Considerar delegación
                    if limit.delegate_to_id:
                        today = fields.Date.today()
                        if limit.delegation_date_from and limit.delegation_date_to:
                            if limit.delegation_date_from <= today <= limit.delegation_date_to:
                                approvers |= limit.delegate_to_id
                                continue

                    approvers |= limit.user_id

            record.suggested_approver_ids = approvers

    def _compute_approval_limits(self):
        """Obtiene los límites de aprobación aplicables"""
        ApprovalLimit = self.env['advance.approval.limit']

        for record in self:
            limits = ApprovalLimit.search([
                ('active', '=', True),
                ('company_id', '=', record.company_id.id),
                '|', ('advance_type_ids', '=', False),
                     ('advance_type_ids', 'in', record.advance_type_id.id if record.advance_type_id else [])
            ])
            record.approval_limit_ids = limits

    @api.depends('advance_type_id', 'partner_id', 'sale_order_id', 'purchase_order_id',
                 'sale_line_ids', 'purchase_line_ids')
    def _compute_amount_suggested(self):
        """Calcula el monto sugerido basado en el contexto"""
        for record in self:
            suggested = 0
            percentage = 0.3  # 30% por defecto

            if record.advance_type_id and record.advance_type_id.default_percentage:
                percentage = record.advance_type_id.default_percentage / 100.0

            # Si hay líneas específicas seleccionadas de venta
            if record.sale_line_ids:
                total = sum(record.sale_line_ids.mapped('price_total'))
                suggested = total * percentage
            # Si hay líneas específicas seleccionadas de compra
            elif record.purchase_line_ids:
                total = sum(record.purchase_line_ids.mapped('price_total'))
                suggested = total * percentage
            # Si hay una orden de venta completa
            elif record.sale_order_id:
                suggested = record.sale_order_id.amount_total * percentage
            # Si hay una orden de compra completa
            elif record.purchase_order_id:
                suggested = record.purchase_order_id.amount_total * percentage
            # Si no hay orden pero hay límites definidos
            elif record.advance_type_id and record.advance_type_id.min_amount:
                suggested = record.advance_type_id.min_amount

            record.amount_suggested = suggested

    def action_use_suggested_amount(self):
        """Usa el monto sugerido como monto solicitado"""
        self.ensure_one()
        if self.amount_suggested > 0:
            self.amount_requested = self.amount_suggested
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'type': 'success',
                    'message': _('Monto sugerido aplicado: %s') % self.amount_suggested,
                    'sticky': False,
                }
            }

    def get_advance_percentage(self):
        """Calcula el porcentaje de anticipo basado en el monto solicitado y el total"""
        self.ensure_one()
        total = 0

        # Calcular el total según las líneas o las órdenes
        if self.sale_line_ids:
            total = sum(self.sale_line_ids.mapped('price_total'))
        elif self.purchase_line_ids:
            total = sum(self.purchase_line_ids.mapped('price_total'))
        elif self.sale_order_id:
            total = self.sale_order_id.amount_total
        elif self.purchase_order_id:
            total = self.purchase_order_id.amount_total

        if total > 0:
            return (self.amount_requested / total) * 100
        return 0

    @api.depends('stage_id', 'stage_id.code')
    def _compute_stage_code(self):
        """Calcula el código de la etapa actual"""
        for record in self:
            record.stage_code = record.stage_id.code if record.stage_id else 'draft'

    @api.onchange('sale_line_ids', 'purchase_line_ids')
    def _onchange_order_lines(self):
        """Actualiza el monto sugerido cuando cambian las líneas seleccionadas"""
        if self.sale_line_ids or self.purchase_line_ids:
            self._compute_amount_suggested()

    @api.depends('advance_type_id', 'partner_id', 'sale_order_id', 'purchase_order_id')
    def _compute_request_type(self):
        """Calcula el tipo de solicitud basado en el contexto"""
        for record in self:
            # Si viene de una orden de venta
            if record.sale_order_id:
                record.request_type = 'customer'
            # Si viene de una orden de compra
            elif record.purchase_order_id:
                record.request_type = 'supplier'
            # Basado en el tipo de anticipo
            elif record.advance_type_id:
                if record.advance_type_id.operation_code == 'ADV_CUST':
                    record.request_type = 'customer'
                elif record.advance_type_id.operation_code == 'ADV_SUPP':
                    record.request_type = 'supplier'
                elif record.advance_type_id.operation_code == 'ADV_EMP':
                    record.request_type = 'employee'
                else:
                    record.request_type = 'other'
            # Basado en el partner
            elif record.partner_id:
                if record.partner_id.customer_rank > 0:
                    record.request_type = 'customer'
                elif record.partner_id.supplier_rank > 0:
                    record.request_type = 'supplier'
                else:
                    record.request_type = 'other'
            else:
                # Valor por defecto del contexto
                record.request_type = self._context.get('default_request_type', 'customer')

    @api.depends('request_type')
    def _compute_partner_type(self):
        """Calcula el tipo de partner basado en el tipo de solicitud"""
        for record in self:
            if record.request_type == 'customer':
                record.partner_type = 'customer'
            else:
                record.partner_type = 'supplier'

    @api.depends('payment_ids', 'payment_ids.state', 'reconciliation_ids')
    def _compute_amounts(self):
        """Calcula montos pagados, disponibles y reconciliados"""
        for record in self:
            # Monto pagado
            paid_payments = record.payment_ids.filtered(
                lambda p: p.state == 'posted'
            )
            record.amount_paid = sum(paid_payments.mapped('amount'))

            # Monto reconciliado/aplicado
            record.amount_reconciled = sum(
                record.reconciliation_ids.mapped('amount')
            )
            record.amount_applied = record.amount_reconciled

            # Saldo disponible
            record.amount_available = record.amount_paid - record.amount_reconciled

            # Saldo pendiente
            record.balance_pending = record.amount_approved - record.amount_paid if record.amount_approved else record.amount_requested - record.amount_paid

    @api.depends('payment_ids')
    def _compute_has_payment(self):
        """Determina si tiene pagos asociados"""
        for record in self:
            record.has_payment = bool(record.payment_ids)

    @api.depends('payment_ids.state', 'amount_paid', 'amount_reconciled')
    def _compute_payment_status(self):
        """Calcula estado del pago y reconciliación"""
        for record in self:
            record.is_paid = record.amount_paid > 0
            record.is_reconciled = record.amount_reconciled >= record.amount_paid and record.amount_paid > 0

    @api.depends('amount_requested', 'currency_id')
    def _compute_amount_in_words(self):
        """Convierte el monto a palabras"""
        for record in self:
            if record.amount_requested and record.currency_id:
                try:
                    from num2words import num2words
                    amount_words = num2words(record.amount_requested, lang='es')
                    record.amount_in_words = f"{amount_words.upper()} {record.currency_id.currency_unit_label or record.currency_id.name}"
                except:
                    # Fallback si no está instalado num2words
                    record.amount_in_words = f"{record.amount_requested:,.2f} {record.currency_id.name}"
            else:
                record.amount_in_words = ""

    @api.depends('payment_ids')
    def _compute_payment_count(self):
        """Cuenta el número de pagos"""
        for record in self:
            record.payment_count = len(record.payment_ids)

    @api.depends('invoice_ids')
    def _compute_invoice_count(self):
        """Cuenta el número de facturas aplicadas"""
        for record in self:
            record.invoice_count = len(record.invoice_ids)

    @api.depends('date_due', 'is_paid', 'is_reconciled')
    def _compute_days_overdue(self):
        """Calcula días vencidos"""
        today = fields.Date.today()
        for record in self:
            # Solo calcular días vencidos si no está pagado o conciliado
            if record.date_due and not (record.is_paid or record.is_reconciled):
                diff = today - record.date_due
                record.days_overdue = max(0, diff.days)
            else:
                record.days_overdue = 0

    @api.depends('stage_enter_date')
    def _compute_stage_duration(self):
        """Calcula el tiempo en la etapa actual"""
        now = fields.Datetime.now()
        for record in self:
            if record.stage_enter_date:
                delta = now - record.stage_enter_date
                # Convertir a horas
                record.stage_duration = delta.total_seconds() / 3600.0
            else:
                record.stage_duration = 0.0

    @api.depends('stage_id')
    def _compute_date_last_stage_update(self):
        """Actualiza la fecha del último cambio de etapa"""
        for request in self:
            if not request.date_last_stage_update:
                request.date_last_stage_update = request.create_date or fields.Datetime.now()
            else:
                # Este campo se actualizará automáticamente cuando cambie stage_id
                # gracias al tracking del mixin
                request.date_last_stage_update = fields.Datetime.now()

    @api.depends('amount_requested', 'amount_paid', 'amount_reconciled', 'is_reconciled')
    def _compute_progress(self):
        """Calcula el progreso del anticipo"""
        for record in self:
            if record.amount_requested:
                if record.is_reconciled:
                    record.progress = 100
                elif record.amount_paid:
                    record.progress = (record.amount_paid / record.amount_requested) * 100
                else:
                    record.progress = 0
            else:
                record.progress = 0

    @api.model_create_multi
    def create(self, vals_list):
        """Override create para generar secuencia"""
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                # Obtener secuencia según el tipo
                request_type = vals.get('request_type', 'customer')
                if request_type == 'customer':
                    seq_code = 'advance.request.customer'
                elif request_type == 'supplier':
                    seq_code = 'advance.request.supplier'
                else:
                    seq_code = 'advance.request.other'

                vals['name'] = self.env['ir.sequence'].next_by_code(seq_code) or 'Nuevo'

        records = super().create(vals_list)

        # Crear actividades predeterminadas
        for record in records:
            record._create_default_activities()
            # Establecer fecha de entrada a la etapa
            if record.stage_id:
                record.stage_enter_date = fields.Datetime.now()

        return records

    def write(self, vals):
        """Override write para rastrear cambios de etapa"""
        # Si se cambia la etapa, guardar historial y actualizar fecha de entrada
        if 'stage_id' in vals:
            for record in self:
                if record.stage_id:
                    # Crear registro en el historial
                    duration = 0
                    if record.stage_enter_date:
                        delta = fields.Datetime.now() - record.stage_enter_date
                        duration = delta.total_seconds() / 3600.0

                    self.env['advance.request.stage.history'].create({
                        'request_id': record.id,
                        'stage_id': record.stage_id.id,
                        'enter_date': record.stage_enter_date,
                        'exit_date': fields.Datetime.now(),
                        'duration': duration,
                        'user_id': self.env.user.id,
                    })

            # Actualizar fecha de entrada a la nueva etapa
            vals['stage_enter_date'] = fields.Datetime.now()

        return super().write(vals)

    def _create_default_activities(self):
        """Crea actividades predeterminadas según la etapa"""
        self.ensure_one()
        if self.stage_id.activity_type_ids:
            for activity_type in self.stage_id.activity_type_ids:
                self.activity_schedule(
                    activity_type_id=activity_type.id,
                    summary=activity_type.name,
                    date_deadline=fields.Date.today() + timedelta(days=activity_type.delay_count)
                )

    @api.onchange('stage_id')
    def _onchange_stage_id(self):
        """Actualiza actividades al cambiar de etapa"""
        if self.stage_id:
            # Marcar actividades actuales como hechas
            self.activity_ids.action_done()
            # Crear nuevas actividades
            self._create_default_activities()

            # Avisar cuando la etapa cambia a pago generado
            if self.stage_id.code == 'in_payment' and self.has_payment:
                self.message_post(
                    body=_('Pago generado para el anticipo'),
                    message_type='notification'
                )

    @api.onchange('sale_order_id')
    def _onchange_sale_order(self):
        """Actualiza datos desde orden de venta"""
        if self.sale_order_id:
            self.partner_id = self.sale_order_id.partner_id
            self.amount_requested = self.sale_order_id.amount_total * 0.3  # 30% por defecto
            self.analytic_account_id = self.sale_order_id.analytic_account_id
            # Agregar todas las líneas de la orden
            self.sale_line_ids = [(6, 0, self.sale_order_id.order_line.ids)]
        else:
            self.sale_line_ids = [(5, 0, 0)]

    @api.onchange('purchase_order_id')
    def _onchange_purchase_order(self):
        """Actualiza datos desde orden de compra"""
        if self.purchase_order_id:
            self.partner_id = self.purchase_order_id.partner_id
            self.amount_requested = self.purchase_order_id.amount_total * 0.3  # 30% por defecto
            # Agregar todas las líneas de la orden
            self.purchase_line_ids = [(6, 0, self.purchase_order_id.order_line.ids)]
        else:
            self.purchase_line_ids = [(5, 0, 0)]

    @api.onchange('auto_reconcile')
    def _onchange_auto_reconcile(self):
        """Muestra aviso de auto-conciliación"""
        if self.auto_reconcile and not self.reconcile_warning_shown:
            self.reconcile_warning_shown = True
            return {
                'warning': {
                    'title': _('Auto-conciliación activada'),
                    'message': _('El sistema conciliará automáticamente este anticipo con las facturas del cliente/proveedor cuando se confirme el pago.')
                }
            }

    @api.onchange('advance_type_id')
    def _onchange_advance_type_id(self):
        """Muestra aviso si el tipo no tiene cuenta configurada"""
        if self.advance_type_id and not self.advance_type_id.account_id:
            return {
                'warning': {
                    'title': _('Cuenta no configurada'),
                    'message': _('El tipo de anticipo seleccionado no tiene una cuenta contable configurada. '
                                'Por favor, configure la cuenta en el tipo de anticipo antes de proceder con el pago.')
                }
            }

    def action_request(self):
        """Envía la solicitud - mueve a etapa de solicitud"""
        self.ensure_one()

        # Buscar etapa de solicitud
        request_stage = self.env['advance.request.stage'].search([
            #('request_type', '=', self.request_type),
            ('code', '=', 'pending')
        ], limit=1)

        if not request_stage:
            raise UserError(_('No se encontró la etapa de solicitud pendiente'))

        self.write({
            'stage_id': request_stage.id,
            'date_request': fields.Date.today()
        })

        # Enviar notificación
        self.message_post(
            body=_('Solicitud de anticipo enviada para aprobación'),
            message_type='notification'
        )

    def action_approve(self):
        """Aprueba la solicitud - mueve a etapa aprobada"""
        self.ensure_one()

        # Verificar si el usuario puede aprobar
        can_approve = self._check_approval_rights()
        if not can_approve:
            # Sugerir aprobadores
            if self.suggested_approver_ids:
                approvers = ', '.join(self.suggested_approver_ids.mapped('name'))
                raise UserError(_('No tiene permisos para aprobar esta solicitud.\n\n'
                                'Aprobadores sugeridos: %s') % approvers)
            else:
                raise UserError(_('No tiene permisos para aprobar esta solicitud'))

        # Verificar si requiere doble aprobación
        ApprovalLimit = self.env['advance.approval.limit']
        limit = ApprovalLimit.search([
            ('user_id', '=', self.env.user.id),
            ('active', '=', True),
            ('company_id', '=', self.company_id.id)
        ], limit=1)

        if limit and limit.require_two_approvals and not self.approved_by:
            # Primera aprobación - no mover etapa aún
            self.write({
                'approved_by': self.env.user.id,
                'date_approved': fields.Datetime.now()
            })

            second_approver = limit.second_approver_id.name if limit.second_approver_id else 'otro aprobador'
            self.message_post(
                body=_('Primera aprobación realizada por %s. Esperando segunda aprobación de %s') %
                     (self.env.user.name, second_approver),
                message_type='notification'
            )
            return

        # Buscar siguiente etapa
        next_stage = self._get_next_stage()
        if not next_stage:
            raise UserError(_('No se encontró la siguiente etapa'))

        if not self.amount_approved:
            self.amount_approved = self.amount_requested

        self.write({
            'stage_id': next_stage.id,
            'date_approved': fields.Datetime.now(),
            'approved_by': self.env.user.id
        })

        # Usar template de aprobación de la etapa
        message = self.stage_id.template_approved or _('Solicitud aprobada')
        self.message_post(
            body=_('%s por %s') % (message, self.env.user.name),
            message_type='notification'
        )

    def action_show_approval_matrix(self):
        """Muestra la matriz de aprobación"""
        self.ensure_one()

        ApprovalLimit = self.env['advance.approval.limit']
        matrix = ApprovalLimit.get_approval_matrix(self.advance_type_id)

        # Crear mensaje con la matriz
        message = '<table class="table table-sm">'
        message += '<thead><tr>'
        message += '<th>Usuario</th><th>Puesto</th><th>Modo</th>'
        message += '<th>Mín</th><th>Máx</th><th>Pendientes</th>'
        message += '</tr></thead><tbody>'

        for row in matrix:
            message += '<tr>'
            message += f'<td>{row["user"]}</td>'
            message += f'<td>{row["job"]}</td>'
            message += f'<td>{row["mode"]}</td>'
            message += f'<td>{row["min_amount"]:,.0f}</td>' if row["min_amount"] else '<td>-</td>'
            message += f'<td>{row["max_amount"]:,.0f}</td>' if row["max_amount"] else '<td>Sin límite</td>'
            message += f'<td>{row["pending"]}</td>'
            message += '</tr>'

        message += '</tbody></table>'

        self.message_post(
            body=message,
            message_type='comment',
            subtype_xmlid='mail.mt_note'
        )

    def _check_approval_rights(self):
        """Verifica si el usuario actual puede aprobar usando la tabla de límites"""
        self.ensure_one()
        user = self.env.user

        # Primero verificar en la tabla de límites de aprobación
        ApprovalLimit = self.env['advance.approval.limit']

        # Buscar límite específico para este usuario
        limit = ApprovalLimit.search([
            ('user_id', '=', user.id),
            ('active', '=', True),
            ('company_id', '=', self.company_id.id)
        ], limit=1)

        if limit:
            # Verificar si puede aprobar este monto
            can_approve = limit.can_approve_amount(
                self.amount_requested,
                advance_type=self.advance_type_id,
                partner=self.partner_id,
                stage=self.stage_id
            )

            # Si no puede auto-aprobar y es su propia solicitud
            if can_approve and not limit.can_self_approve:
                if self.user_id == user:
                    self.message_post(
                        body=_('No puede aprobar su propia solicitud'),
                        message_type='notification'
                    )
                    return False

            # Si requiere doble aprobación
            if can_approve and limit.require_two_approvals:
                # Verificar si ya hay una aprobación previa
                if not self.approved_by:
                    # Primera aprobación
                    self.message_post(
                        body=_('Primera aprobación registrada. Se requiere una segunda aprobación de %s') %
                             (limit.second_approver_id.name if limit.second_approver_id else 'otro aprobador'),
                        message_type='notification'
                    )
                    return True

            return can_approve

        # Si no hay límite específico, usar la configuración de la etapa (compatibilidad)
        if self.stage_id.approval_user_ids:
            if user in self.stage_id.approval_user_ids:
                return True

        # Si hay límite por monto en la etapa
        if self.stage_id.approval_amount_min and self.amount_requested >= self.stage_id.approval_amount_min:
            if self.stage_id.approval_group_id:
                return user.has_group(self.stage_id.approval_group_id.id)

        # Por defecto, verificar si existe algún límite que permita aprobar
        approver = ApprovalLimit.get_approver_for_amount(
            self.amount_requested,
            advance_type=self.advance_type_id,
            partner=self.partner_id,
            stage=self.stage_id
        )

        return approver == user if approver else False

    def _get_next_stage(self):
        """Obtiene la siguiente etapa en la secuencia"""
        self.ensure_one()

        # Buscar etapas del mismo tipo de anticipo
        domain = []
        if self.advance_type_id:
            domain = [('advance_type_ids', 'in', self.advance_type_id.id)]

        stages = self.env['advance.request.stage'].search(
            domain,
            order='sequence'
        )

        # Encontrar la etapa actual y devolver la siguiente
        current_found = False
        for stage in stages:
            if current_found:
                return stage
            if stage == self.stage_id:
                current_found = True

        return False

    def action_reject(self):
        """Rechaza la solicitud - mueve a etapa rechazada"""
        self.ensure_one()

        # Buscar etapa de rechazo
        rejected_stage = self.env['advance.request.stage'].search([
            ('request_type', '=', self.request_type),
            ('code', '=', 'rejected')
        ], limit=1)

        if not rejected_stage:
            raise UserError(_('No se encontró la etapa de rechazo'))

        # Abrir wizard para motivo de rechazo
        return {
            'name': _('Rechazar Solicitud'),
            'type': 'ir.actions.act_window',
            'res_model': 'advance.request.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_request_id': self.id, 'default_rejected_stage_id': rejected_stage.id}
        }

    def action_cancel(self):
        """Cancela la solicitud - mueve a etapa cancelada"""
        self.ensure_one()

        if self.is_paid or self.is_reconciled:
            raise UserError(_('No se pueden cancelar solicitudes pagadas o reconciliadas'))

        # Buscar etapa de cancelación
        cancelled_stage = self.env['advance.request.stage'].search([
            ('request_type', '=', self.request_type),
            ('code', '=', 'cancelled')
        ], limit=1)

        if not cancelled_stage:
            raise UserError(_('No se encontró la etapa de cancelación'))

        self.write({'stage_id': cancelled_stage.id})

        self.message_post(
            body=_('Solicitud cancelada'),
            message_type='notification'
        )

    def action_create_payment(self):
        """Crea el pago del anticipo"""
        self.ensure_one()

        # Verificar si la etapa permite crear pagos en borrador
        if not self.stage_id.can_create_draft_payment:
            raise UserError(_('No se pueden crear pagos en la etapa actual'))

        # Advertir si no hay cuenta configurada
        if self.advance_type_id and not self.advance_type_id.account_id:
            message = _('Atención: El tipo de anticipo %s no tiene una cuenta contable configurada. '
                       'Por favor, configure la cuenta antes de continuar con el pago.') % self.advance_type_id.name
            self.message_post(body=message, message_type='comment')

        # Determinar tipo de pago
        if self.request_type == 'customer':
            payment_type = 'inbound'
            partner_type = 'customer'
        else:
            payment_type = 'outbound'
            partner_type = 'supplier'

        return {
            'name': _('Registrar Pago de Anticipo'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'view_mode': 'form',
            'context': {
                'default_advance_request_id': self.id,
                'default_payment_type': payment_type,
                'default_partner_type': partner_type,
                'default_partner_id': self.partner_id.id,
                'default_amount': self.amount_approved,
                'default_is_advance': True,
                'default_ref': self.name,
                'default_analytic_distribution': self.analytic_distribution,
            },
            'target': 'current',
        }

    def action_view_payments(self):
        """Ver pagos asociados"""
        self.ensure_one()
        return {
            'name': _('Pagos'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'view_mode': 'list,form',
            'domain': [('advance_request_id', '=', self.id)],
            'context': {'create': False}
        }

    def action_view_invoices(self):
        """Ver facturas aplicadas"""
        self.ensure_one()
        return {
            'name': _('Facturas Aplicadas'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.invoice_ids.ids)],
            'context': {'create': False}
        }

    def action_view_reconciliations(self):
        """Ver conciliaciones del anticipo"""
        self.ensure_one()
        return {
            'name': _('Conciliaciones'),
            'type': 'ir.actions.act_window',
            'res_model': 'advance.reconciliation',
            'view_mode': 'list,form',
            'domain': [('request_id', '=', self.id)],
            'context': {'create': False}
        }

    def action_reconcile(self):
        """Abre wizard para conciliar con facturas"""
        self.ensure_one()
        if self.amount_available <= 0:
            raise UserError(_('No hay saldo disponible para conciliar'))

        return {
            'name': _('Aplicar Anticipo a Facturas'),
            'type': 'ir.actions.act_window',
            'res_model': 'advance.reconciliation.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_request_id': self.id,
                'default_partner_id': self.partner_id.id,
                'default_amount_available': self.amount_available
            }
        }

    def auto_reconcile_advances(self):
        """Método para auto-conciliar anticipos con facturas pendientes"""
        for record in self.filtered(lambda r: r.auto_reconcile and r.amount_available > 0):
            # Buscar facturas pendientes del partner
            domain = [
                ('partner_id', '=', record.partner_id.id),
                ('state', '=', 'posted'),
                ('payment_state', 'in', ['not_paid', 'partial']),
                ('company_id', '=', record.company_id.id)
            ]

            if record.request_type == 'customer':
                domain.append(('move_type', '=', 'out_invoice'))
            else:
                domain.append(('move_type', '=', 'in_invoice'))

            invoices = self.env['account.move'].search(domain, order='invoice_date_due')

            remaining = record.amount_available
            for invoice in invoices:
                if remaining <= 0:
                    break

                amount_to_apply = min(remaining, invoice.amount_residual)
                if amount_to_apply > 0:
                    # Crear registro de conciliación
                    self.env['advance.reconciliation'].create({
                        'request_id': record.id,
                        'invoice_id': invoice.id,
                        'amount': amount_to_apply,
                        'date': fields.Date.today()
                    })

                    remaining -= amount_to_apply

                    # Actualizar factura
                    invoice.message_post(
                        body=_('Anticipo %s aplicado: %s %s') % (
                            record.name,
                            amount_to_apply,
                            record.currency_id.symbol
                        )
                    )

            # Actualizar etapa si está totalmente reconciliado
            if record.amount_available <= 0.01:
                reconciled_stage = self.env['advance.request.stage'].search([
                    ('request_type', '=', record.request_type),
                    ('code', '=', 'reconciled')
                ], limit=1)
                if reconciled_stage:
                    record.stage_id = reconciled_stage

    @api.model
    def create_from_sale_order(self, sale_order):
        """Crea anticipo desde orden de venta"""
        advance_type = self.env['advance.type'].search([
            ('code', '=', 'SALE_ADVANCE')
        ], limit=1)

        if not advance_type:
            raise UserError(_('No se encontró el tipo de anticipo para ventas'))

        return self.create({
            'request_type': 'customer',
            'advance_type_id': advance_type.id,
            'partner_id': sale_order.partner_id.id,
            'sale_order_id': sale_order.id,
            'amount_requested': sale_order.amount_total * 0.3,
            'description': _('Anticipo para orden de venta %s') % sale_order.name
        })

    @api.model
    def create_from_purchase_order(self, purchase_order):
        """Crea anticipo desde orden de compra"""
        advance_type = self.env['advance.type'].search([
            ('code', '=', 'PURCHASE_ADVANCE')
        ], limit=1)

        if not advance_type:
            raise UserError(_('No se encontró el tipo de anticipo para compras'))

        return self.create({
            'request_type': 'supplier',
            'advance_type_id': advance_type.id,
            'partner_id': purchase_order.partner_id.id,
            'purchase_order_id': purchase_order.id,
            'amount_requested': purchase_order.amount_total * 0.3,
            'description': _('Anticipo para orden de compra %s') % purchase_order.name
        })


# =============================================================================
# MODELOS RELACIONADOS (Consolidados)
# =============================================================================

class AdvanceReconciliation(models.Model):
    """Modelo para registrar conciliaciones de anticipos"""
    _name = 'advance.reconciliation'
    _description = 'Conciliación de Anticipo'
    _order = 'date desc'

    request_id = fields.Many2one(
        'advance.request',
        string='Solicitud de Anticipo',
        required=True,
        ondelete='cascade'
    )
    invoice_id = fields.Many2one(
        'account.move',
        string='Factura',
        required=True,
        domain=[('move_type', 'in', ['out_invoice', 'in_invoice'])]
    )
    amount = fields.Monetary(
        string='Monto Aplicado',
        currency_field='currency_id',
        required=True
    )
    currency_id = fields.Many2one(
        related='request_id.currency_id',
        string='Moneda'
    )
    date = fields.Date(
        string='Fecha',
        default=fields.Date.today,
        required=True
    )
    notes = fields.Text(string='Notas')


class AdvanceRequestReconcileLine(models.Model):
    """Línea de Aplicación de Anticipo"""
    _name = 'advance.request.reconcile.line'
    _description = 'Línea de Aplicación de Anticipo'
    _order = 'date desc'

    request_id = fields.Many2one(
        'advance.request',
        string='Solicitud de Anticipo',
        required=True,
        ondelete='cascade'
    )
    invoice_id = fields.Many2one(
        'account.move',
        string='Factura',
        required=True,
        domain="[('move_type', 'in', ['out_invoice', 'in_invoice']), ('state', '=', 'posted')]"
    )
    date = fields.Date(
        string='Fecha',
        required=True,
        default=fields.Date.today
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        related='request_id.currency_id'
    )
    invoice_amount = fields.Monetary(
        string='Monto Factura',
        currency_field='currency_id',
        compute='_compute_invoice_amount',
        store=True
    )
    amount_applied = fields.Monetary(
        string='Monto Aplicado',
        currency_field='currency_id',
        required=True
    )
    balance = fields.Monetary(
        string='Saldo',
        currency_field='currency_id',
        compute='_compute_balance',
        store=True
    )

    @api.depends('invoice_id')
    def _compute_invoice_amount(self):
        for line in self:
            line.invoice_amount = line.invoice_id.amount_total if line.invoice_id else 0.0

    @api.depends('invoice_amount', 'amount_applied')
    def _compute_balance(self):
        for line in self:
            line.balance = line.invoice_amount - line.amount_applied