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

    @http.route('/api/bascula/peso_actual_global', type='json', auth='public', methods=['POST'], csrf=False)
    def obtener_peso_actual_global(self, **kwargs):
        """
        Endpoint para obtener el último peso actualizado por la báscula
        SIN necesidad de tener un pesaje_id específico.

        Útil para mostrar el peso en formularios nuevos antes de guardar.

        POST /api/bascula/peso_actual_global
        Body: {} (no requiere parámetros)
        """
        try:
            # Obtener el pesaje más reciente que tenga peso_actual
            Pesaje = request.env['secadora.pesaje'].sudo()
            pesaje = Pesaje.search([
                ('peso_actual', '>', 0),
                ('state', 'in', ['borrador', 'en_transito'])
            ], order='write_date desc', limit=1)

            if pesaje:
                return {
                    'success': True,
                    'peso_actual': pesaje.peso_actual,
                    'timestamp': pesaje.write_date.isoformat() if pesaje.write_date else None,
                    'pesaje_id': pesaje.id
                }
            else:
                return {
                    'success': True,
                    'peso_actual': 0.0,
                    'timestamp': None,
                    'message': 'No hay peso disponible'
                }

        except Exception as e:
            _logger.error(f"Error obteniendo peso actual global: {str(e)}")
            return {'success': False, 'message': str(e)}

    @http.route('/api/bascula/test', type='http', auth='none', methods=['GET'], csrf=False)
    def test_conexion(self):
        """Endpoint de prueba para verificar que la API esté funcionando"""
        return json.dumps({
            'success': True,
            'message': 'API de báscula funcionando correctamente',
            'version': '1.0'
        })
