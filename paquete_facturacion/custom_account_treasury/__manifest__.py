
{
    "name": "Tesoreria Pagos y Cobros",
    "version": "19.0.1.3.1",
    "category": "Treasury",
    "license": "AGPL-3",
    "summary": "Permite el pago multiple de cuentas por cobrar y/o pagar",
    "author": "Lavish S.A.S",
    "external_dependencies": {
        "python": ["dateutil", "pytz"],
    },
    
    "depends":[
        "base",
        "account",
        "account_check_printing",
        "sale",
        "sale_management",
        "purchase",
        "lavish_erp"
    ],
    "data": [
        'data/sequence_data.xml',
        'data/payment_request_stage_data.xml',
        'data/advance_type_data.xml',
        'data/advance_type_stages_data.xml',
        'data/treasury_weekday_data.xml',
        'data/treasury_payment_schedule_day_data.xml',
        'data/treasury_holiday_colombia_data.xml',
        'data/treasury_bank_charge_type_data.xml',
        # Comisiones: el usuario configura manualmente por banco
        "security/group_users.xml",
        "security/ir.model.access.csv",
        # Menú root primero (otros archivos dependen de él)
        "views/treasury_menu_root.xml",
        # Dashboard
        "views/treasury_dashboard_views.xml",
        # Vistas y acciones primero (antes del menú)
        "views/account_payment_by_state_menu.xml",
        "views/account_massive_payment_view.xml",
        "views/advance_type_view.xml",
        "views/account_move_inherit.xml",
        # "views/account_move.xml",  # Campos force_account_id en líneas
        "views/account_payment_view.xml",
        "views/account_payment_treasury_views.xml",
        "views/account_payment_method_view.xml",
        "views/account_payment_method_treasury_views.xml",
        "views/account_account_views.xml",
        "views/account_account_treasury_views.xml",
        "views/payment_request_stage_views.xml",
        "views/advance_approval_limit_views.xml",
        "views/advance_request_stage_views.xml",
        "wizards/payment_request_advance_wizard_views.xml",
        "wizards/purchase_advance_wizard_views.xml",
        "wizards/sale_advance_wizard_views.xml",
        "wizards/select_documents_wizard_view.xml",
        "wizards/treasury_report_wizard_views.xml",
        "reports/bank_transfer_report.xml",
        "reports/payment_voucher_report.xml",
        "views/payment_request_views.xml",
        "views/advance_request_views.xml",
        # "views/payment_operation_type_views.xml",  # COMENTADO: Campo operation_type_id no existe
        "views/advance_request_kanban_enhanced_views.xml",
        "views/res_config_settings_views.xml",
        "views/sale_order_views.xml",
        "views/purchase_order_views.xml",
        # Vista mejorada de pagos
        "views/account_payment_enhanced_view.xml",
        # Vista heredada de la nativa de Odoo
        "views/account_payment_treasury_form.xml",
        # Configuración de secuencias
        "views/treasury_sequence_config_views.xml",
        # Comisiones bancarias y calendario de pagos
        "views/treasury_bank_commission_views.xml",
        "views/treasury_bank_charge_type_views.xml",
        "views/account_bank_statement_line_views.xml",
        # Menu al final (después de las acciones)
        "views/treasury_menu_unified.xml",
    ],
    'assets': {
        'web.assets_backend': [
            # Chart.js (desde Odoo core)
            ('include', 'web.chartjs_lib'),
            # CSS
            'custom_account_treasury/static/src/css/treasury_menu.css',
            'custom_account_treasury/static/src/css/treasury_dashboard.css',
            'custom_account_treasury/static/src/css/payment_enhanced.css',
            'custom_account_treasury/static/src/js/payment_amount.css',
            'custom_account_treasury/static/src/css/payment_section_and_note.scss',
            'custom_account_treasury/static/src/css/account_debt_selector.scss',
            'custom_account_treasury/static/src/css/report_styles.scss',
            # JavaScript widgets
            'custom_account_treasury/static/src/js/payment_amount_widget.js',
            'custom_account_treasury/static/src/js/payment_amount_templates.xml',
            # Section and Note widgets
            'custom_account_treasury/static/src/xml/payment_section_and_note.xml',
            'custom_account_treasury/static/src/js/payment_section_and_note.js',
            # Account Debt Selector widget
            'custom_account_treasury/static/src/xml/account_debt_selector.xml',
            'custom_account_treasury/static/src/js/account_debt_selector.js',
            # Dashboard
            'custom_account_treasury/static/src/xml/treasury_dashboard.xml',
            'custom_account_treasury/static/src/js/treasury_dashboard.js',
        ],
    },
    "active": True,
    "application": True,
    "installable": True,
    "pre_init_hook": "pre_init_hook",
}
