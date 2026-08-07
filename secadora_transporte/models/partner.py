# -*- coding: utf-8 -*-

from odoo import models, fields


class ResPartnerTransporte(models.Model):
    _inherit = 'res.partner'

    generar_flete_automatico = fields.Boolean(
        string='Generar Flete Automático',
        default=False,
        help='Si está marcado, al completar un pesaje con este tercero se creará un flete automáticamente.',
    )

    flete_pago = fields.Selection([
        ('agricultor', 'Agricultor paga directo'),
        ('secadora', 'Secadora paga y descuenta'),
    ], string='Pago de Flete', default='agricultor',
       help='Define quién paga el flete. Si "Secadora paga y descuenta", el costo se descontará al agricultor en la liquidación.')

    # El banco exige la certificación para inscribir al beneficiario, así que
    # viaja anexa al final de la orden de giro (ver ir_actions_report.py).
    certificacion_bancaria = fields.Binary(
        string='Certificación bancaria',
        attachment=True,
        help='PDF de la certificación bancaria. Se anexa al final del reporte '
             'de viajes por pagar, como respaldo de los datos de la cuenta.',
    )
    certificacion_bancaria_nombre = fields.Char(
        string='Nombre del archivo',
    )
    certificacion_bancaria_fecha = fields.Date(
        string='Fecha de expedición',
        help='Fecha en que el banco expidió la certificación. Los bancos '
             'suelen exigir que no tenga más de 30 a 90 días.',
    )
