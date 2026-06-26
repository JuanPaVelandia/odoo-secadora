# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class ResCompany(models.Model):
    _inherit = 'res.company'

    advance_excess_as_advance = fields.Boolean(
        string='Excedentes como Anticipos',
        default=True,
        help='Convertir excedentes de pago en anticipos automáticamente'
    )
    advance_payment_journal_id = fields.Many2one(
        'account.journal',
        string='Diario de Anticipos',
        domain="[('type', '=', 'bank'), ('company_id', '=', id)]",
        help='Diario utilizado para registrar los anticipos'
    )
    default_customer_advance_account_id = fields.Many2one(
        'account.account',
        string='Cuenta de Anticipos de Clientes',
        domain="[('account_type', '=', 'liability_current'), ('active', '=', True)]",
        help='Cuenta por defecto para anticipos de clientes'
    )
    treasury_auto_apply_advances = fields.Boolean(
        string='Aplicar Anticipos Automáticamente', 
        default=True,
        help='Aplica automáticamente los anticipos disponibles al confirmar facturas'
    )
    default_supplier_advance_account_id = fields.Many2one(
        'account.account',
        string='Cuenta de Anticipos de Proveedores',
        domain="[('account_type', '=', 'asset_current'), ('active', '=', True)]",
        help='Cuenta por defecto para anticipos de proveedores'
    )

    default_employee_advance_account_id = fields.Many2one(
        'account.account',
        string='Cuenta de Anticipos de Empleados',
        domain="[('account_type', '=', 'asset_current'), ('active', '=', True)]",
        help='Cuenta por defecto para anticipos de empleados'
    )

    third_party_advance_account_id = fields.Many2one(
        'account.account',
        string='Cuenta Global de Anticipos de Terceros',
        domain="[('active', '=', True)]",
        help='Cuenta global para anticipos cuando no se especifica tipo'
    )
    treasury_multi_partner_default = fields.Boolean(
        string='Multi-Tercero por Defecto', 
        default=False,
        help='Activa multi-tercero por defecto en nuevos documentos'
    )
    auto_create_exchange_diff = fields.Boolean(
        string='Crear Diferencias de Cambio Automáticamente',
        default=True,
        help='Crear asientos de diferencia de cambio automáticamente en transferencias'
    )

    exchange_diff_threshold = fields.Float(
        string='Umbral de Diferencia de Cambio',
        default=0.01,
        help='Umbral mínimo para crear asientos de diferencia de cambio'
    )

    # ========== CONFIGURACIÓN DE PRÉSTAMOS ==========

    default_customer_loan_account_id = fields.Many2one(
        'account.account',
        string='Cuenta de Préstamos a Clientes',
        domain="[('account_type', '=', 'asset_current'), ('active', '=', True)]",
        help='Cuenta por defecto para préstamos otorgados a clientes'
    )

    default_supplier_loan_account_id = fields.Many2one(
        'account.account',
        string='Cuenta de Préstamos de Proveedores',
        domain="[('account_type', '=', 'liability_current'), ('active', '=', True)]",
        help='Cuenta por defecto para préstamos recibidos de proveedores'
    )

    default_employee_loan_account_id = fields.Many2one(
        'account.account',
        string='Cuenta de Préstamos a Empleados',
        domain="[('account_type', '=', 'asset_current'), ('active', '=', True)]",
        help='Cuenta por defecto para préstamos otorgados a empleados'
    )

    loan_payment_journal_id = fields.Many2one(
        'account.journal',
        string='Diario de Préstamos',
        domain="[('type', '=', 'general'), ('company_id', '=', id)]",
        help='Diario utilizado para registrar asientos de cruce de préstamos'
    )

    treasury_auto_apply_loans = fields.Boolean(
        string='Aplicar Préstamos Automáticamente',
        default=False,
        help='Aplica automáticamente los préstamos disponibles al confirmar facturas'
    )

    # ========== CONFIGURACIÓN DE DIFERENCIA EN CAMBIO ==========

    exchange_diff_mode = fields.Selection([
        ('same_entry', 'En el mismo asiento'),
        ('separate_entry', 'En asiento separado'),
    ], string='Modo de Diferencia en Cambio',
        default='separate_entry',
        help='Define si la diferencia en cambio se registra en el mismo asiento del pago o en uno separado'
    )

    exchange_diff_group_mode = fields.Selection([
        ('per_line', 'Por línea de deuda'),
        ('grouped', 'Agrupado por documento'),
        ('general', 'General (una sola línea)'),
    ], string='Agrupación de Diferencia en Cambio',
        default='per_line',
        help='Define cómo agrupar las líneas de diferencia en cambio:\n'
             '- Por línea: Una línea de diferencia por cada deuda pagada\n'
             '- Agrupado: Una línea por documento (factura)\n'
             '- General: Una sola línea consolidada de diferencia'
    )

    exchange_diff_link_document = fields.Boolean(
        string='Asociar a Documento Original',
        default=True,
        help='Asocia el asiento de diferencia en cambio al documento original (factura/pago)'
    )

    exchange_diff_handle_manual_iva = fields.Boolean(
        string='Manejar IVA Manual en Diferencia',
        default=False,
        help='Cuando hay retención de IVA manual, ajusta la base de cálculo de la diferencia en cambio'
    )

    exchange_diff_iva_account_id = fields.Many2one(
        'account.account',
        string='Cuenta de Ajuste IVA en Diferencia',
        domain="[('active', '=', True)]",
        help='Cuenta para registrar ajustes de IVA cuando hay diferencia en cambio con retención manual'
    )

    exchange_diff_auto_reconcile = fields.Boolean(
        string='Conciliar Diferencia Automáticamente',
        default=True,
        help='Concilia automáticamente las líneas de diferencia en cambio con el documento original'
    )

    exchange_diff_separate_journal_id = fields.Many2one(
        'account.journal',
        string='Diario para Diferencias en Cambio',
        domain="[('type', '=', 'general'), ('company_id', '=', id)]",
        help='Diario específico para asientos de diferencia en cambio cuando se usa modo separado. '
             'Si no se define, usa el diario configurado en la compañía para diferencias de cambio.'
    )

    # ========== CONFIGURACIÓN DE GASTOS BANCARIOS ==========

    bank_expense_account_id = fields.Many2one(
        'account.account',
        string='Cuenta de Gastos Bancarios',
        domain="[('active', '=', True)]",
        help='Cuenta para registrar gastos bancarios (comisiones, GMF, etc.)'
    )

    bank_expense_iva_account_id = fields.Many2one(
        'account.account',
        string='Cuenta de IVA Gastos Bancarios',
        domain="[('active', '=', True)]",
        help='Cuenta para registrar el IVA de los gastos bancarios'
    )

    bank_expense_partner_id = fields.Many2one(
        'res.partner',
        string='Tercero por Defecto Gastos Bancarios',
        help='Tercero por defecto para cargar los gastos bancarios en conciliacion'
    )

    bank_expense_apply_iva = fields.Boolean(
        string='Aplicar IVA a Gastos Bancarios',
        default=True,
        help='Indica si se debe aplicar IVA a los gastos bancarios'
    )

    bank_expense_iva_rate = fields.Float(
        string='Tasa IVA Gastos Bancarios (%)',
        default=19.0,
        help='Tasa de IVA aplicable a gastos bancarios'
    )