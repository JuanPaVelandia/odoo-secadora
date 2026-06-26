# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class AdvanceApprovalLimit(models.Model):
    """Límites de Aprobación para Anticipos - Simple"""
    _name = 'advance.approval.limit'
    _description = 'Límite de Aprobación de Anticipos'
    _order = 'sequence, id'

    # ========== CAMPOS BÁSICOS ==========

    name = fields.Char(
        string='Nombre',
        required=True,
        help='Ej: "Gerente - Hasta 5M", "Director - Sin límite"'
    )

    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)

    # ========== APROBADOR ==========

    user_id = fields.Many2one(
        'res.users',
        string='Usuario Aprobador',
        required=True,
        help='Usuario que puede aprobar bajo estos límites'
    )

    # ========== TIPO DE SOLICITUD ==========

    request_type_ids = fields.Many2many(
        'payment.request',
        string='Tipos Permitidos',
        help='Tipos de solicitud que puede aprobar. Si está vacío, puede aprobar todos',
        domain=[],
        compute='_compute_allowed_types',
        store=False
    )

    # Simplificado: solo los tipos básicos
    can_approve_supplier = fields.Boolean(
        string='Aprobar Pagos a Proveedor',
        default=True
    )

    can_approve_customer = fields.Boolean(
        string='Aprobar Cobros a Cliente',
        default=True
    )

    can_approve_advance = fields.Boolean(
        string='Aprobar Anticipos',
        default=True
    )

    # ========== LÍMITES DE MONTO ==========

    has_amount_limit = fields.Boolean(
        string='Tiene Límite de Monto',
        default=True,
        help='Si NO tiene límite, puede aprobar cualquier monto'
    )

    amount_min = fields.Monetary(
        string='Monto Mínimo',
        currency_field='currency_id',
        help='Monto mínimo que puede aprobar'
    )

    amount_max = fields.Monetary(
        string='Monto Máximo',
        currency_field='currency_id',
        help='Monto máximo que puede aprobar (0 = sin límite)'
    )

    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        required=True,
        default=lambda self: self.env.company.currency_id
    )

    # ========== RESTRICCIONES ADICIONALES ==========

    partner_ids = fields.Many2many(
        'res.partner',
        'approval_limit_partner_rel',
        'limit_id',
        'partner_id',
        string='Terceros Específicos',
        help='Si se especifica, solo puede aprobar solicitudes de estos terceros'
    )

    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company
    )

    # ========== DELEGACIÓN ==========

    can_delegate = fields.Boolean(
        string='Puede Delegar',
        default=False,
        help='Permite delegar la aprobación temporalmente'
    )

    delegate_to_id = fields.Many2one(
        'res.users',
        string='Delegado A',
        help='Usuario al que se delega temporalmente'
    )

    delegation_date_from = fields.Date(
        string='Delegación Desde'
    )

    delegation_date_to = fields.Date(
        string='Delegación Hasta'
    )

    # ========== MÉTODOS ==========

    @api.depends('can_approve_supplier', 'can_approve_customer', 'can_approve_advance')
    def _compute_allowed_types(self):
        """Calcula tipos permitidos (solo para filtros)"""
        for rec in self:
            types = []
            if rec.can_approve_supplier:
                types.append('supplier')
            if rec.can_approve_customer:
                types.append('customer')
            if rec.can_approve_advance:
                types.append('advance')
            # No se puede asignar directamente, es solo para dominio
            rec.request_type_ids = False

    @api.constrains('amount_min', 'amount_max')
    def _check_amounts(self):
        """Validar que min <= max"""
        for rec in self:
            if rec.has_amount_limit and rec.amount_max > 0:
                if rec.amount_min > rec.amount_max:
                    raise ValidationError(
                        _('El monto mínimo no puede ser mayor al monto máximo')
                    )

    @api.constrains('delegation_date_from', 'delegation_date_to')
    def _check_delegation_dates(self):
        """Validar fechas de delegación"""
        for rec in self:
            if rec.delegate_to_id:
                if not rec.delegation_date_from or not rec.delegation_date_to:
                    raise ValidationError(
                        _('Debe especificar fechas de inicio y fin para la delegación')
                    )
                if rec.delegation_date_from > rec.delegation_date_to:
                    raise ValidationError(
                        _('La fecha de inicio no puede ser posterior a la fecha de fin')
                    )

    def can_approve_request(self, request):
        """
        Verifica si este límite puede aprobar la solicitud.

        :param request: Registro de payment.request
        :return: Boolean
        """
        self.ensure_one()

        # Verificar tipo de solicitud
        if request.request_type == 'supplier' and not self.can_approve_supplier:
            return False
        if request.request_type == 'customer' and not self.can_approve_customer:
            return False
        if request.request_type == 'advance' and not self.can_approve_advance:
            return False

        # Verificar monto
        if self.has_amount_limit:
            amount = request.amount
            if self.currency_id != request.currency_id:
                # Convertir a la moneda del límite
                amount = request.currency_id._convert(
                    amount,
                    self.currency_id,
                    request.company_id,
                    fields.Date.today()
                )

            if amount < self.amount_min:
                return False

            if self.amount_max > 0 and amount > self.amount_max:
                return False

        # Verificar tercero específico
        if self.partner_ids and request.partner_id not in self.partner_ids:
            return False

        return True

    def get_current_approver(self):
        """
        Obtiene el usuario aprobador actual (considerando delegación).

        :return: res.users record
        """
        self.ensure_one()

        # Verificar si hay delegación activa
        if self.delegate_to_id and self.delegation_date_from and self.delegation_date_to:
            today = fields.Date.today()
            if self.delegation_date_from <= today <= self.delegation_date_to:
                return self.delegate_to_id

        return self.user_id

    @api.model
    def get_approvers_for_request(self, request):
        """
        Obtiene lista de usuarios que pueden aprobar una solicitud.

        :param request: Registro de payment.request
        :return: Lista de res.users
        """
        limits = self.search([
            ('company_id', '=', request.company_id.id),
            ('active', '=', True)
        ])

        approvers = self.env['res.users']

        for limit in limits:
            if limit.can_approve_request(request):
                approvers |= limit.get_current_approver()

        return approvers

    @api.model
    def get_approval_matrix(self):
        """
        Genera matriz de aprobación para visualización.

        :return: Lista de diccionarios con info de límites
        """
        limits = self.search([('active', '=', True)], order='sequence, amount_max')

        matrix = []
        for limit in limits:
            types = []
            if limit.can_approve_supplier:
                types.append('Proveedor')
            if limit.can_approve_customer:
                types.append('Cliente')
            if limit.can_approve_advance:
                types.append('Anticipo')

            amount_range = ''
            if limit.has_amount_limit:
                if limit.amount_max > 0:
                    amount_range = f'{limit.amount_min:,.0f} - {limit.amount_max:,.0f}'
                else:
                    amount_range = f'Desde {limit.amount_min:,.0f}'
            else:
                amount_range = 'Sin límite'

            matrix.append({
                'user': limit.user_id.name,
                'types': ', '.join(types),
                'amount_range': amount_range,
                'currency': limit.currency_id.name,
                'partners': len(limit.partner_ids) if limit.partner_ids else 'Todos',
                'delegated': limit.delegate_to_id.name if limit.delegate_to_id else False,
            })

        return matrix
