# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HrLoanStub(models.Model):
    """Stub vacío de hr.loan declarado aquí para satisfacer la dependencia
    de hr.loan.request.loan_id durante el setup de modelos.

    El modelo real lo define lavish_hr_payroll con todos sus campos. Como
    lavish_hr_employee NO depende de lavish_hr_payroll (sería circular),
    este stub garantiza que hr.loan exista en el registro al momento de
    resolver el comodel del Many2one, sin importar el orden de carga.
    """
    _name = 'hr.loan'
    _description = 'Loan (stub, extendido por lavish_hr_payroll)'


class HrLoanRequest(models.Model):
    _name = 'hr.loan.request'
    _description = 'Solicitud de Préstamo'
    _order = 'request_date desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Número de Solicitud',
        required=True,
        copy=False,
        readonly=True,
        default='Nuevo',
        tracking=True
    )

    employee_id = fields.Many2one(
        'hr.employee',
        string='Empleado',
        required=True,
        readonly=True,
        tracking=True
    )

    loan_type = fields.Selection([
        ('personal', 'Préstamo Personal'),
        ('education', 'Préstamo Educación'),
        ('housing', 'Préstamo Vivienda'),
        ('calamity', 'Calamidad Doméstica'),
        ('other', 'Otro')
    ], string='Tipo de Préstamo', required=True, tracking=True)

    amount = fields.Monetary(
        string='Monto Solicitado',
        required=True,
        tracking=True,
        currency_field='currency_id'
    )

    approved_amount = fields.Monetary(
        string='Monto Aprobado',
        tracking=True,
        currency_field='currency_id'
    )

    installments = fields.Integer(
        string='Número de Cuotas',
        required=True,
        default=1,
        tracking=True
    )

    installment_amount = fields.Monetary(
        string='Valor Cuota',
        compute='_compute_installment_amount',
        store=True,
        currency_field='currency_id'
    )

    paid_installments = fields.Integer(
        string='Cuotas Pagadas',
        default=0,
        tracking=True
    )

    balance = fields.Monetary(
        string='Saldo Pendiente',
        compute='_compute_balance',
        store=True,
        currency_field='currency_id'
    )

    justification = fields.Text(
        string='Justificación',
        required=True,
        tracking=True
    )

    request_date = fields.Date(
        string='Fecha de Solicitud',
        default=fields.Date.today,
        required=True,
        readonly=True,
        tracking=True
    )

    approval_date = fields.Date(
        string='Fecha de Aprobación',
        readonly=True,
        tracking=True
    )

    rejection_date = fields.Date(
        string='Fecha de Rechazo',
        readonly=True,
        tracking=True
    )

    rejection_reason = fields.Text(
        string='Motivo de Rechazo',
        readonly=True,
        tracking=True
    )

    state = fields.Selection([
        ('draft', 'Borrador'),
        ('requested', 'Solicitado'),
        ('approved', 'Aprobado'),
        ('rejected', 'Rechazado'),
        ('in_payment', 'En Pago'),
        ('paid', 'Pagado'),
        ('cancelled', 'Cancelado')
    ], string='Estado', default='draft', required=True, tracking=True)

    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        related='employee_id.company_id',
        store=True,
        readonly=True
    )

    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        related='company_id.currency_id',
        readonly=True
    )

    # Responsable de aprobación
    approver_id = fields.Many2one(
        'res.users',
        string='Aprobado por',
        readonly=True,
        tracking=True
    )

    loan_id = fields.Many2one(
        'hr.loan',
        string='Préstamo Generado',
        readonly=True,
        tracking=True,
        help='Préstamo de nómina generado a partir de esta solicitud'
    )

    loan_category_id = fields.Many2one(
        'hr.loan.category',
        string='Categoría del Préstamo',
        help='Categoría que se usará al crear el préstamo de nómina'
    )

    # Contadores para smartbuttons
    payslip_count = fields.Integer(
        string='Nóminas',
        compute='_compute_document_counts'
    )

    leave_count = fields.Integer(
        string='Ausencias',
        compute='_compute_document_counts'
    )

    @api.model
    def _auto_init(self):
        """Normalize legacy varchar refs before ORM applies many2one FKs."""
        self.env.cr.execute("""
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = 'hr_loan_request'
              AND column_name = 'loan_id'
        """)
        row = self.env.cr.fetchone()
        if row and row[0] in ('character varying', 'text'):
            self.env.cr.execute("""
                ALTER TABLE hr_loan_request
                DROP CONSTRAINT IF EXISTS hr_loan_request_loan_id_fkey
            """)
            self.env.cr.execute("""
                ALTER TABLE hr_loan_request
                ALTER COLUMN loan_id TYPE integer
                USING (
                    CASE
                        WHEN loan_id IS NULL OR loan_id = '' THEN NULL
                        WHEN loan_id ~ '^[0-9]+$' THEN loan_id::integer
                        WHEN loan_id ~ '^hr\\.loan,[0-9]+$' THEN split_part(loan_id, ',', 2)::integer
                        ELSE NULL
                    END
                )
            """)
            self.env.cr.execute("""
                UPDATE hr_loan_request req
                SET loan_id = NULL
                WHERE loan_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM hr_loan l WHERE l.id = req.loan_id
                  )
            """)

        self.env.cr.execute("""
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = 'hr_loan_request'
              AND column_name = 'loan_category_id'
        """)
        row = self.env.cr.fetchone()
        if row and row[0] in ('character varying', 'text'):
            self.env.cr.execute("""
                ALTER TABLE hr_loan_request
                DROP CONSTRAINT IF EXISTS hr_loan_request_loan_category_id_fkey
            """)
            self.env.cr.execute("""
                ALTER TABLE hr_loan_request
                ALTER COLUMN loan_category_id TYPE integer
                USING (
                    CASE
                        WHEN loan_category_id IS NULL OR loan_category_id = '' THEN NULL
                        WHEN loan_category_id ~ '^[0-9]+$' THEN loan_category_id::integer
                        WHEN loan_category_id ~ '^hr\\.loan\\.category,[0-9]+$' THEN split_part(loan_category_id, ',', 2)::integer
                        ELSE NULL
                    END
                )
            """)
            self.env.cr.execute("""
                UPDATE hr_loan_request req
                SET loan_category_id = NULL
                WHERE loan_category_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM hr_loan_category c WHERE c.id = req.loan_category_id
                  )
            """)

        return super()._auto_init()

    @api.depends('employee_id')
    def _compute_document_counts(self):
        """Calcular contadores de documentos relacionados"""
        for record in self:
            if record.employee_id:
                # Contar nóminas del empleado (solo confirmadas)
                record.payslip_count = self.env['hr.payslip'].search_count([
                    ('employee_id', '=', record.employee_id.id),
                    ('state', '=', 'done')
                ])

                # Contar ausencias del empleado
                record.leave_count = self.env['hr.leave'].search_count([
                    ('employee_id', '=', record.employee_id.id)
                ])
            else:
                record.payslip_count = 0
                record.leave_count = 0

    @api.depends('approved_amount', 'installments')
    def _compute_installment_amount(self):
        """Calcular valor de cada cuota"""
        for record in self:
            if record.installments > 0 and record.approved_amount:
                record.installment_amount = record.approved_amount / record.installments
            else:
                record.installment_amount = 0.0

    @api.depends('approved_amount', 'paid_installments', 'installment_amount')
    def _compute_balance(self):
        """Calcular saldo pendiente"""
        for record in self:
            if record.approved_amount:
                paid_amount = record.paid_installments * record.installment_amount
                record.balance = record.approved_amount - paid_amount
            else:
                record.balance = 0.0

    @api.model_create_multi
    def create(self, vals_list):
        """Override para asignar secuencia"""
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'hr.loan.request'
                ) or f'LOAN/{fields.Date.today().year}/{self.env["ir.sequence"].next_by_code("default") or "001"}'

        return super().create(vals_list)

    @api.constrains('amount', 'approved_amount', 'installments')
    def _check_amounts(self):
        """Validar montos y cuotas"""
        for record in self:
            if record.amount <= 0:
                raise ValidationError(_('El monto solicitado debe ser mayor a 0'))

            if record.approved_amount and record.approved_amount <= 0:
                raise ValidationError(_('El monto aprobado debe ser mayor a 0'))

            if record.installments <= 0:
                raise ValidationError(_('El número de cuotas debe ser mayor a 0'))

    def action_request(self):
        """Enviar solicitud a aprobación"""
        self.ensure_one()
        self.state = 'requested'
        self.message_post(
            body=_('Solicitud de préstamo enviada a aprobación por $%s en %s cuotas') % (
                '{:,.2f}'.format(self.amount), self.installments
            )
        )

    def action_approve(self):
        """Aprobar préstamo"""
        self.ensure_one()

        if not self.approved_amount:
            self.approved_amount = self.amount

        self.write({
            'state': 'approved',
            'approval_date': fields.Date.today(),
            'approver_id': self.env.user.id
        })

        self.message_post(
            body=_('Préstamo aprobado por $%s en %s cuotas. Aprobado por: %s') % (
                '{:,.2f}'.format(self.approved_amount),
                self.installments,
                self.env.user.name
            )
        )

    def action_reject(self):
        """Rechazar préstamo"""
        self.ensure_one()

        self.write({
            'state': 'rejected',
            'rejection_date': fields.Date.today()
        })

        self.message_post(
            body=_('Solicitud de préstamo rechazada')
        )

    def action_start_payment(self):
        """Iniciar proceso de pago"""
        self.ensure_one()

        if self.state != 'approved':
            raise ValidationError(_('Solo se pueden iniciar pagos en préstamos aprobados'))

        self.state = 'in_payment'
        self.message_post(body=_('Inicio de proceso de pago del préstamo'))

    def action_mark_paid(self):
        """Marcar como pagado"""
        self.ensure_one()
        self.state = 'paid'
        self.paid_installments = self.installments
        self.message_post(body=_('Préstamo pagado en su totalidad'))

    def action_cancel(self):
        """Cancelar solicitud"""
        self.ensure_one()
        self.state = 'cancelled'

    def action_draft(self):
        """Volver a borrador"""
        self.ensure_one()
        self.state = 'draft'

    def action_create_payroll_loan(self):
        """
        Crear préstamo de nómina (hr.loan) desde la solicitud aprobada
        """
        self.ensure_one()

        if self.state != 'approved':
            raise ValidationError(_('Solo se pueden crear préstamos de nómina desde solicitudes aprobadas'))

        if self.loan_id:
            raise ValidationError(_('Ya existe un préstamo de nómina creado para esta solicitud'))

        if not self.loan_category_id:
            raise ValidationError(_('Debe seleccionar una categoría de préstamo antes de crear el préstamo de nómina'))

        # Buscar contrato activo del empleado
        contract = self.env['hr.contract'].search([
            ('employee_id', '=', self.employee_id.id),
            ('state', '=', 'open')
        ], limit=1)

        if not contract:
            raise ValidationError(_('El empleado no tiene un contrato activo'))

        # Mapear tipos de préstamo
        loan_type_map = {
            'personal': 'loan',
            'education': 'loan',
            'housing': 'loan',
            'calamity': 'loan',
            'other': 'loan'
        }

        # Crear préstamo de nómina con campos correctos
        loan_vals = {
            'employee_id': self.employee_id.id,
            'contract_id': contract.id,
            'category_id': self.loan_category_id.id,
            'loan_type': loan_type_map.get(self.loan_type, 'loan'),
            'date': fields.Date.today(),
            'date_account': fields.Date.today(),
            'original_amount': self.approved_amount,
            'loan_amount': self.approved_amount,
            'interest_rate': 0.0,  # Sin intereses por defecto
            'apply_interest': False,
            'calculation_type': 'period',
            'num_periods': self.installments,
            'payment_start_date': fields.Date.today(),
            'apply_on': '15',  # Primera quincena por defecto
            'state': 'draft',
            'description': self.justification or '',
        }

        loan = self.env['hr.loan'].sudo().create(loan_vals)

        # Vincular préstamo creado (relación bidireccional)
        self.loan_id = loan.id
        loan.loan_request_id = self.id
        self.state = 'in_payment'

        # Mensaje en chatter
        self.message_post(
            body=_('Préstamo de nómina %s creado exitosamente') % loan.name,
            subject=_('Préstamo Creado')
        )

        # Retornar acción para abrir el préstamo
        return {
            'type': 'ir.actions.act_window',
            'name': _('Préstamo de Nómina'),
            'res_model': 'hr.loan',
            'res_id': loan.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_payroll_loan(self):
        """Ver préstamo de nómina relacionado"""
        self.ensure_one()

        if not self.loan_id:
            raise ValidationError(_('No hay un préstamo de nómina asociado a esta solicitud'))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Préstamo de Nómina'),
            'res_model': 'hr.loan',
            'res_id': self.loan_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_payslips(self):
        """Ver nóminas del empleado"""
        self.ensure_one()

        if not self.employee_id:
            raise ValidationError(_('No hay empleado asociado'))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Nóminas de %s') % self.employee_id.name,
            'res_model': 'hr.payslip',
            'view_mode': 'list,form',
            'domain': [
                ('employee_id', '=', self.employee_id.id),
                ('state', '=', 'done')
            ],
            'context': {
                'default_employee_id': self.employee_id.id,
            },
        }

    def action_view_leaves(self):
        """Ver ausencias del empleado"""
        self.ensure_one()

        if not self.employee_id:
            raise ValidationError(_('No hay empleado asociado'))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Ausencias de %s') % self.employee_id.name,
            'res_model': 'hr.leave',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.employee_id.id)],
            'context': {
                'default_employee_id': self.employee_id.id,
            },
        }

    def action_download_payslips_pdf(self):
        """Descargar todas las nóminas del empleado en PDF"""
        self.ensure_one()

        if not self.employee_id:
            raise ValidationError(_('No hay empleado asociado'))

        payslips = self.env['hr.payslip'].search([
            ('employee_id', '=', self.employee_id.id),
            ('state', '=', 'done')
        ])

        if not payslips:
            raise ValidationError(_('No hay nóminas confirmadas para este empleado'))

        # Generar reporte PDF de todas las nóminas
        return self.env.ref('lavish_hr_payroll.action_report_payslip').report_action(payslips)
