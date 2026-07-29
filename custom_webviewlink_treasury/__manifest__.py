{
    'name': 'Enlace Documento Drive - Tesoreria',
    'version': '19.0.1.0.0',
    'summary': 'Muestra el comprobante y mensaje de WhatsApp en las vistas de pago de custom_account_treasury',
    'description': """
Puente entre custom_webviewlink y custom_account_treasury
=========================================================

custom_account_treasury define sus vistas form de pago en mode="primary":
unas con arch propio (sin inherit_id) y otras que heredan de la estandar pero,
por ser primary, tampoco reciben sus extensiones. En ambos casos la vista
custom_webviewlink.view_account_payment_form_webviewlink no llega a aplicarse y
los campos x_whatsapp_comprobante_link / x_whatsapp_mensaje quedan invisibles
aunque tengan datos.

Este modulo repone esos campos con vistas de extension, sin tocar el arch ni la
prioridad de las vistas de custom_account_treasury, asi que sobrevive a sus
actualizaciones.

Se instala solo (auto_install) cuando los dos modulos que conecta estan
presentes, y desaparece sin dejar rastro si alguno se desinstala.
    """,
    'category': 'Accounting',
    'author': 'Secadora La Gran Colombia',
    'depends': ['custom_webviewlink', 'custom_account_treasury'],
    'data': [
        'views/account_payment_views.xml',
    ],
    'installable': True,
    'auto_install': True,
    'license': 'LGPL-3',
}
