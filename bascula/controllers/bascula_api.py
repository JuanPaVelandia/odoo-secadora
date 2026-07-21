# -*- coding: utf-8 -*-

import json
import logging
from odoo import http, api, SUPERUSER_ID
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


def _json_response(data, status=200):
    """Helper para retornar respuesta JSON desde endpoint type='http'."""
    return Response(
        json.dumps(data),
        content_type='application/json',
        status=status,
    )


def _get_env_from_db(db_name):
    """Obtiene un Environment para la BD especificada (para auth='none')."""
    registry = api.Registry(db_name)
    cr = registry.cursor()
    env = api.Environment(cr, SUPERUSER_ID, {})
    return env, cr


class BasculaAPI(http.Controller):
    """API REST para integración con báscula externa"""

    def _get_db_and_data(self):
        """Parsea body JSON y retorna (db, data). db viene del body o de Odoo."""
        raw = request.httprequest.data.decode('utf-8')
        data = json.loads(raw) if raw else {}
        # Si hay params (JSON-RPC), extraer; si no, usar directo
        if 'params' in data:
            data = data['params']
        db = data.get('db') or getattr(request, 'db', None) or request.session.get('db')
        return db, data

    @http.route('/api/bascula/actualizar_peso', type='http', auth='none', methods=['POST'], csrf=False)
    def actualizar_peso(self, **kwargs):
        """
        POST /api/bascula/actualizar_peso
        Body: {"pesaje_id": 123, "peso": 28345.50, "api_key": "...", "db": "odoo_secadora"}
        """
        env = cr = None
        try:
            db, data = self._get_db_and_data()
            pesaje_id = data.get('pesaje_id')
            peso = data.get('peso')
            api_key = data.get('api_key')

            if not all([pesaje_id, peso is not None, api_key]):
                return _json_response({
                    'success': False,
                    'message': 'Parámetros faltantes: pesaje_id, peso, api_key'
                }, 400)

            if not db:
                return _json_response({'success': False, 'message': 'Falta parámetro db'}, 400)

            env, cr = _get_env_from_db(db)
            Pesaje = env['secadora.pesaje']
            result = Pesaje.actualizar_peso_bascula(pesaje_id, peso, api_key)
            cr.commit()
            return _json_response(result)

        except Exception as e:
            _logger.error(f"Error actualizando peso: {e}")
            return _json_response({'success': False, 'message': str(e)}, 500)
        finally:
            if cr:
                cr.close()

    @http.route('/api/bascula/pesaje_activo', type='http', auth='none', methods=['POST'], csrf=False)
    def obtener_pesaje_activo(self, **kwargs):
        """
        POST /api/bascula/pesaje_activo
        Body: {"api_key": "...", "db": "odoo_secadora"}
        """
        env = cr = None
        try:
            db, data = self._get_db_and_data()
            api_key = data.get('api_key')

            if not api_key:
                return _json_response({'success': False, 'message': 'API Key faltante'}, 400)

            if not db:
                return _json_response({'success': False, 'message': 'Falta parámetro db'}, 400)

            env, cr = _get_env_from_db(db)
            Pesaje = env['secadora.pesaje']
            result = Pesaje.obtener_pesaje_activo(api_key)
            return _json_response(result)

        except Exception as e:
            _logger.error(f"Error obteniendo pesaje activo: {e}")
            return _json_response({'success': False, 'message': str(e)}, 500)
        finally:
            if cr:
                cr.close()

    @http.route('/api/bascula/actualizar_peso_global', type='http', auth='none', methods=['POST'], csrf=False)
    def actualizar_peso_global(self, **kwargs):
        """
        POST /api/bascula/actualizar_peso_global
        Body: {"peso": 28345.50, "api_key": "...", "db": "odoo_secadora"}
        """
        env = cr = None
        try:
            db, data = self._get_db_and_data()
            peso = data.get('peso')
            api_key = data.get('api_key')

            if not all([peso is not None, api_key]):
                return _json_response({
                    'success': False,
                    'message': 'Parámetros faltantes: peso, api_key'
                }, 400)

            if not db:
                return _json_response({'success': False, 'message': 'Falta parámetro db'}, 400)

            env, cr = _get_env_from_db(db)
            Pesaje = env['secadora.pesaje']
            result = Pesaje.actualizar_peso_global_bascula(peso, api_key)
            cr.commit()
            return _json_response(result)

        except Exception as e:
            _logger.error(f"Error actualizando peso global: {e}")
            return _json_response({'success': False, 'message': str(e)}, 500)
        finally:
            if cr:
                cr.close()

    @http.route('/api/bascula/peso_actual_global', type='http', auth='none', methods=['POST'], csrf=False)
    def obtener_peso_actual_global(self, **kwargs):
        """
        POST /api/bascula/peso_actual_global
        Body: {"db": "odoo_secadora"}
        """
        env = cr = None
        try:
            db, data = self._get_db_and_data()

            if not db:
                return _json_response({'success': False, 'message': 'Falta parámetro db'}, 400)

            env, cr = _get_env_from_db(db)
            Pesaje = env['secadora.pesaje']
            result = Pesaje.obtener_peso_actual_global_ui()
            return _json_response(result)

        except Exception as e:
            _logger.error(f"Error obteniendo peso actual global: {e}")
            return _json_response({'success': False, 'message': str(e)}, 500)
        finally:
            if cr:
                cr.close()

    @http.route('/api/bascula/test', type='http', auth='none', methods=['GET'], csrf=False)
    def test_conexion(self):
        """Endpoint de prueba"""
        return _json_response({
            'success': True,
            'message': 'API de báscula funcionando correctamente',
            'version': '2.0'
        })
