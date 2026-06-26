{
    "name": "Transferencias Internas de Tesorería",
    "version": "19.0.1.0.0",
    "category": "Treasury",
    "license": "AGPL-3",
    "summary": "Transferencias internas de dinero entre diarios en un solo paso, "
               "con responsables y confirmación de recepción.",
    "description": """
Transferencias Internas de Tesorería
====================================
Reemplaza el flujo manual de transferencias internas (dos pagos + conciliación
a mano) por un formulario único y automático:

* Eliges diario origen, diario destino, monto y motivo.
* Defines responsable que envía y responsable que recibe.
* Al confirmar, el sistema crea y contabiliza automáticamente el pago de salida
  y el cobro de entrada, y los concilia contra la cuenta de transferencia interna
  de la empresa (queda en cero).
* El responsable destino confirma la recepción del dinero.
* Trazabilidad completa en el chatter y comprobante imprimible.
""",
    "author": "PARAMO LABS",
    "website": "https://paramodigital.com.co",
    "depends": [
        "account",
        "custom_account_treasury",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/sequence_data.xml",
        "report/treasury_internal_transfer_report.xml",
        "report/treasury_internal_transfer_templates.xml",
        "views/treasury_internal_transfer_views.xml",
        "views/treasury_internal_transfer_menus.xml",
    ],
    "installable": True,
    "application": False,
}
