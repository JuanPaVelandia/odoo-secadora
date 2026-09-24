# -*- coding: utf-8 -*-
{
    'name': 'Pesajes en Google Sheets',
    'version': '19.0.1.1.0',
    'category': 'Operations',
    'summary': 'Publica pesajes de entrada y horómetros en Google Sheets cada hora',
    'description': """
        Pesajes en Google Sheets - Secadora La Gran Colombia
        ====================================================

        Un cron reescribe cada hora una hoja de Google Sheets con los pesajes
        de entrada (origen, lote, transporte, pesos y calidad) y el detalle de
        las cargas mixtas. Odoo escribe en la hoja; nada consulta a Odoo desde
        afuera.

        Requiere la cuenta de servicio de Google que ya usa custom_webviewlink
        (parámetro custom_webviewlink.drive_sa_json_path), con la API de
        Google Sheets habilitada y la hoja compartida como editor con esa
        cuenta.
    """,
    'author': 'Secadora La Gran Colombia S.A.S',
    'depends': ['bascula', 'custom_webviewlink'],
    'external_dependencies': {'python': ['googleapiclient', 'google.oauth2']},
    'data': [
        'data/config_parameter_data.xml',
        'data/cron_data.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
