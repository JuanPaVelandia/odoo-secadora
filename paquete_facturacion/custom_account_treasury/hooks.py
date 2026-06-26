# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Hook ejecutado después de instalar el módulo para crear dashboard inicial"""
    _create_today_dashboard(env)


def _create_today_dashboard(env):
    """Crear dashboard del día actual si no existe"""
    try:
        Dashboard = env['treasury.dashboard']
        dashboard = Dashboard.get_or_create_today_dashboard()
        _logger.info(f"Dashboard de tesorería verificado/creado: ID {dashboard.id}")
    except Exception as e:
        _logger.warning(f"Error al crear dashboard: {e}")
