# -*- coding: utf-8 -*-

from odoo import models, fields


class FetchmailServer(models.Model):
    _inherit = 'fetchmail.server'

    # El fetchmail.server ya soporta elegir modelo destino (object_id).
    # Configurar el servidor de correo entrante para que apunte a
    # "secadora.factura.email" como "Create a New Record".
    # Esto llamará automáticamente message_new() en nuestro modelo.
    #
    # No se requiere override adicional. Este archivo existe para
    # facilitar futuras extensiones si se necesitan.
