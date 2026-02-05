# -*- coding: utf-8 -*-

import json
import logging
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class BasculaAPI(http.Controller):
    """API REST para integración con báscula externa"""

    @http.route('/api/bascula/actualizar_peso', type='json', auth='none', methods=['POST'], csrf=False)
    def actualizar_peso(self, **kwargs):
        """
        Endpoint para actualizar el peso desde el bridge externo

        POST /api/bascula/actualizar_peso
        Body: {
            "pesaje_id": 123,
            "peso": 28345.50,
            "api_key": "tu_api_key_secreta"
        }
        """
        try:
            data = json.loads(request.httprequest.data.decode('utf-8'))
            pesaje_id = data.get('pesaje_id')
            peso = data.get('peso')
            api_key = data.get('api_key')

            if not all([pesaje_id, peso is not None, api_key]):
                return {
                    'success': False,
                    'message': 'Parámetros faltantes: pesaje_id, peso, api_key'
                }

            # Llamar al modelo
            Pesaje = request.env['secadora.pesaje'].sudo()
            result = Pesaje.actualizar_peso_bascula(pesaje_id, peso, api_key)

            _logger.info(f"Peso actualizado: Pesaje {pesaje_id}, Peso {peso} kg")
            return result

        except Exception as e:
            _logger.error(f"Error actualizando peso: {str(e)}")
            return {'success': False, 'message': str(e)}

    @http.route('/api/bascula/pesaje_activo', type='json', auth='none', methods=['POST'], csrf=False)
    def obtener_pesaje_activo(self, **kwargs):
        """
        Endpoint para obtener el pesaje activo

        POST /api/bascula/pesaje_activo
        Body: {
            "api_key": "tu_api_key_secreta"
        }
        """
        try:
            data = json.loads(request.httprequest.data.decode('utf-8'))
            api_key = data.get('api_key')

            if not api_key:
                return {'success': False, 'message': 'API Key faltante'}

            # Llamar al modelo
            Pesaje = request.env['secadora.pesaje'].sudo()
            result = Pesaje.obtener_pesaje_activo(api_key)

            return result

        except Exception as e:
            _logger.error(f"Error obteniendo pesaje activo: {str(e)}")
            return {'success': False, 'message': str(e)}

    @http.route('/api/bascula/test', type='http', auth='none', methods=['GET'], csrf=False)
    def test_conexion(self):
        """Endpoint de prueba para verificar que la API esté funcionando"""
        return json.dumps({
            'success': True,
            'message': 'API de báscula funcionando correctamente',
            'version': '1.0'
        })
