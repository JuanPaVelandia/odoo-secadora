from odoo import fields, models, api, _


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ============ Configuración de Anticipos ============
    treasury_default_customer_advance_account_id = fields.Many2one(
        'account.account',
        string='Cuenta de Anticipos de Clientes',
        related='company_id.default_customer_advance_account_id',
        readonly=False,
        domain="[('account_type', 'in', ['liability_current', 'asset_receivable']), ('company_ids', '=', id)]",
        help='Cuenta por defecto para registrar anticipos de clientes'
    )

    treasury_default_supplier_advance_account_id = fields.Many2one(
        'account.account',
        string='Cuenta de Anticipos a Proveedores',
        related='company_id.default_supplier_advance_account_id',
        readonly=False,
        domain="[('account_type', 'in', ['asset_current', 'liability_payable']), ('company_ids', '=', id)]",
        help='Cuenta por defecto para registrar anticipos a proveedores'
    )

    treasury_auto_apply_advances = fields.Boolean(
        string='Aplicar Anticipos Automáticamente',
        related='company_id.treasury_auto_apply_advances',
        readonly=False,
        help='Aplica automáticamente los anticipos disponibles al confirmar facturas'
    )

    # ============ Configuración Multi-Tercero ============
    treasury_enable_multi_partner = fields.Boolean(
        string='Habilitar Multi-Tercero Global',
        config_parameter='custom_account_treasury.enable_multi_partner',
        help='Permite habilitar la funcionalidad multi-tercero en facturas, notas de crédito y recibos'
    )

    treasury_multi_partner_default = fields.Boolean(
        string='Multi-Tercero por Defecto',
        config_parameter='custom_account_treasury.multi_partner_default',
        help='Activa multi-tercero por defecto en nuevos documentos'
    )

    # ============ Configuración de Préstamos ============
    treasury_default_customer_loan_account_id = fields.Many2one(
        'account.account',
        string='Cuenta de Préstamos a Clientes',
        related='company_id.default_customer_loan_account_id',
        readonly=False,
        domain="[('account_type', '=', 'asset_current'), ('company_ids', '=', id)]",
        help='Cuenta por defecto para préstamos otorgados a clientes'
    )

    treasury_default_supplier_loan_account_id = fields.Many2one(
        'account.account',
        string='Cuenta de Préstamos de Proveedores',
        related='company_id.default_supplier_loan_account_id',
        readonly=False,
        domain="[('account_type', '=', 'liability_current'), ('company_ids', '=', id)]",
        help='Cuenta por defecto para préstamos recibidos de proveedores'
    )

    treasury_default_employee_loan_account_id = fields.Many2one(
        'account.account',
        string='Cuenta de Préstamos a Empleados',
        related='company_id.default_employee_loan_account_id',
        readonly=False,
        domain="[('account_type', '=', 'asset_current'), ('company_ids', '=', id)]",
        help='Cuenta por defecto para préstamos otorgados a empleados'
    )

    treasury_loan_payment_journal_id = fields.Many2one(
        'account.journal',
        string='Diario de Préstamos',
        related='company_id.loan_payment_journal_id',
        readonly=False,
        domain="[('type', '=', 'general'), ('company_id', '=', id)]",
        help='Diario utilizado para registrar asientos de cruce de préstamos'
    )

    treasury_auto_apply_loans = fields.Boolean(
        string='Aplicar Préstamos Automáticamente',
        related='company_id.treasury_auto_apply_loans',
        readonly=False,
        help='Aplica automáticamente los préstamos disponibles al confirmar facturas'
    )

    # ============ Configuración General de Tesorería ============
    treasury_advance_payment_journal_id = fields.Many2one(
        'account.journal',
        string='Diario de Anticipos',
        related='company_id.advance_payment_journal_id',
        readonly=False,
        domain="[('type', 'in', ['bank', 'general']), ('company_id', '=', id)]",
        help='Diario utilizado para registrar asientos de cruce de anticipos'
    )

    # ============ Configuración de Diferencia en Cambio ============
    treasury_exchange_diff_mode = fields.Selection(
        related='company_id.exchange_diff_mode',
        readonly=False,
        string='Modo de Registro',
        help='Define si la diferencia en cambio se registra en el mismo asiento del pago o en uno separado'
    )

    treasury_exchange_diff_group_mode = fields.Selection(
        related='company_id.exchange_diff_group_mode',
        readonly=False,
        string='Agrupación',
        help='Define cómo agrupar las líneas de diferencia en cambio'
    )

    treasury_exchange_diff_link_document = fields.Boolean(
        related='company_id.exchange_diff_link_document',
        readonly=False,
        string='Asociar a Documento Original',
        help='Asocia el asiento de diferencia en cambio al documento original'
    )

    treasury_exchange_diff_handle_manual_iva = fields.Boolean(
        related='company_id.exchange_diff_handle_manual_iva',
        readonly=False,
        string='Manejar IVA Manual',
        help='Cuando hay retención de IVA manual, ajusta la base de cálculo de la diferencia en cambio'
    )

    treasury_exchange_diff_iva_account_id = fields.Many2one(
        'account.account',
        related='company_id.exchange_diff_iva_account_id',
        readonly=False,
        string='Cuenta de Ajuste IVA',
        help='Cuenta para registrar ajustes de IVA cuando hay diferencia en cambio con retención manual'
    )

    treasury_exchange_diff_auto_reconcile = fields.Boolean(
        related='company_id.exchange_diff_auto_reconcile',
        readonly=False,
        string='Conciliar Automáticamente',
        help='Concilia automáticamente las líneas de diferencia en cambio con el documento original'
    )

    treasury_exchange_diff_separate_journal_id = fields.Many2one(
        'account.journal',
        related='company_id.exchange_diff_separate_journal_id',
        readonly=False,
        string='Diario para Diferencias',
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
        help='Diario específico para asientos de diferencia en cambio cuando se usa modo separado'
    )

    # ============ Configuración de Gastos Bancarios ============
    treasury_bank_expense_account_id = fields.Many2one(
        'account.account',
        related='company_id.bank_expense_account_id',
        readonly=False,
        string='Cuenta de Gastos Bancarios',
        domain="[('active', '=', True)]",
        help='Cuenta para registrar gastos bancarios (comisiones, GMF, etc.)'
    )

    treasury_bank_expense_iva_account_id = fields.Many2one(
        'account.account',
        related='company_id.bank_expense_iva_account_id',
        readonly=False,
        string='Cuenta de IVA Gastos Bancarios',
        domain="[('active', '=', True)]",
        help='Cuenta para registrar el IVA de los gastos bancarios'
    )

    treasury_bank_expense_partner_id = fields.Many2one(
        'res.partner',
        related='company_id.bank_expense_partner_id',
        readonly=False,
        string='Tercero por Defecto Gastos Bancarios',
        help='Tercero por defecto para cargar los gastos bancarios en conciliacion'
    )

    treasury_bank_expense_apply_iva = fields.Boolean(
        related='company_id.bank_expense_apply_iva',
        readonly=False,
        string='Aplicar IVA a Gastos Bancarios',
        help='Indica si se debe aplicar IVA a los gastos bancarios'
    )

    treasury_bank_expense_iva_rate = fields.Float(
        related='company_id.bank_expense_iva_rate',
        readonly=False,
        string='Tasa IVA Gastos Bancarios (%)',
        help='Tasa de IVA aplicable a gastos bancarios'
    )

    @api.model
    def get_values(self):
        """Obtiene los valores de configuración desde los parámetros globales."""
        res = super(ResConfigSettings, self).get_values()
        params = self.env['ir.config_parameter'].sudo()

        res.update(
            treasury_enable_multi_partner=params.get_param('custom_account_treasury.enable_multi_partner', default=False),
            treasury_multi_partner_default=params.get_param('custom_account_treasury.multi_partner_default', default=False),
        )

        return res

    def set_values(self):
        """Guarda los valores de configuración en los parámetros globales."""
        super(ResConfigSettings, self).set_values()
        params = self.env['ir.config_parameter'].sudo()

        params.set_param('custom_account_treasury.enable_multi_partner', self.treasury_enable_multi_partner)
        params.set_param('custom_account_treasury.multi_partner_default', self.treasury_multi_partner_default)