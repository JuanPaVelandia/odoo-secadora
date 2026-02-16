# -*- coding: utf-8 -*-

import secrets
from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    bascula_api_key = fields.Char(
        string='API Key de Báscula',
        config_parameter='bascula.api_key',
        help='Clave secreta para autenticación del bridge de báscula'
    )

    def action_generate_bascula_api_key(self):
        """Genera una API Key aleatoria segura"""
        # Generar token aleatorio de 32 caracteres
        api_key = secrets.token_urlsafe(32)
        self.bascula_api_key = api_key

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'API Key Generada',
                'message': f'Nueva API Key: {api_key}',
                'type': 'success',
                'sticky': False,
            }
        }
