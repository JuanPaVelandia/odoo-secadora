# -*- coding: utf-8 -*-
{
    "name": "Facturación Electrónica POS Colombia",
    "summary": "Facturación electrónica DIAN desde el Punto de Venta para Colombia",
    "description": """
        Módulo de facturación electrónica para el Punto de Venta (POS) en Colombia.

        Características principales:
        ─────────────────────────────
        • Emisión de facturas electrónicas DIAN directamente desde el POS
        • Soporte para notas crédito electrónicas
        • Selección de diario independiente por tipo de documento
        • Ticket personalizado con CUFE/CUDE, resolución, datos del cliente y NIT
        • Captura completa del cliente según exigencias DIAN (tipo responsabilidad,
          régimen, correo electrónico, municipio, etc.)
        • Compatible con Odoo 19 Community y Enterprise
    """,
    "author": "PARAMO DIGITAL",
    "website": "https://paramodigital.com.co",
    "license": "AGPL-3",
    "category": "Accounting/Localizations/Point of Sale",
    "version": "19.0.1.0.47",
    "depends": [
        "point_of_sale",
        "l10n_co_e_invoice",
        "sale",
        "purchase",
        "account",
    ],
    "data": [
        "data/res_partner_data.xml",
        "views/res_partner_view.xml",
        "views/pos_config_view.xml",
        "views/pos_payment_method_views.xml",
        "views/pos_order_views.xml",
        "views/product_views.xml",
        "views/sale_order_views.xml",
        "views/purchase_order_views.xml",
        "views/account_move_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            # CSS para formulario de partner
            "l10n_co_e_pos/static/src/css/partner_form.css",
        ],
        "point_of_sale._assets_pos": [
            # CSS
            "l10n_co_e_pos/static/src/css/pos.css",
            # qrcode.js eliminado: Odoo 19 POS ya incluye su propia librería QRCode
            # Templates XML
            "l10n_co_e_pos/static/src/xml/OrderReceipt.xml",
            "l10n_co_e_pos/static/src/xml/PaymentScreen.xml",
            "l10n_co_e_pos/static/src/app/popups/nc_type_popup/nc_type_popup.xml",
            # Orderline props extension
            "l10n_co_e_pos/static/src/app/overides/orderline/orderline.js",
            # Models
            "l10n_co_e_pos/static/src/app/overides/store/models.js",
            # Popups
            "l10n_co_e_pos/static/src/app/popups/nc_type_popup/nc_type_popup.js",
            "l10n_co_e_pos/static/src/app/popups/nc_type_popup/nc_type_popup.scss",
            # Store and Receipt overrides
            "l10n_co_e_pos/static/src/app/overides/payment_screen/PaymentScreen.js",
            "l10n_co_e_pos/static/src/app/overides/ticket_screen/TicketScreen.js",
            "l10n_co_e_pos/static/src/app/overides/store/pos_store.js",
            "l10n_co_e_pos/static/src/app/overides/store/order_receipt_co.js",
        ],
    },
    "installable": True,
    "auto_install": True,
}
