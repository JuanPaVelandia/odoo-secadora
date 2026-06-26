# -*- coding: utf-8 -*-
"""
Cargador de parámetros anuales con cache optimizado
"""

from odoo import _
from odoo.exceptions import UserError
from datetime import date
from typing import Dict

# Cache simple por (company_id, year)
_PARAM_CACHE: Dict[tuple, Dict[str, float]] = {}


class ParamLoader:
    """
    Cargador de parámetros anuales con cache simple
    """

    @staticmethod
    def _read_params(env, company_id: int, year: int) -> Dict[str, float]:
        """
        Lee parámetros anuales desde la base de datos con cache simple

        Args:
            env: Entorno de Odoo
            company_id: ID de la compañía
            year: Año a consultar

        Returns:
            Dict con parámetros SMMLV, SMMLV_DAILY, TOPE_25_SMMLV, TOPE_40, INT_FACTOR

        Raises:
            UserError: Si no existen parámetros para el año
        """
        global _PARAM_CACHE
        cache_key = (company_id, year)

        if cache_key in _PARAM_CACHE:
            return _PARAM_CACHE[cache_key]

        rec = env['hr.annual.parameters'].get_for_year(
            year,
            company_id=company_id,
            raise_if_not_found=True,
        )

        params = {
            'SMMLV': rec.smmlv_monthly,
            'SMMLV_DAILY': rec.smmlv_daily,
            'TOPE_25_SMMLV': rec.top_twenty_five_smmlv,
            'TOPE_40': rec.value_porc_statute_1395 / 100,
            'INT_FACTOR': rec.porc_integral_salary / 100,  # 0.70
        }

        _PARAM_CACHE[cache_key] = params
        return params

    @classmethod
    def for_date(cls, env, d: date) -> Dict[str, float]:
        """
        Obtiene parámetros para una fecha específica

        Args:
            env: Entorno de Odoo
            d: Fecha de consulta

        Returns:
            Dict con parámetros del año de la fecha
        """
        return cls._read_params(env, env.company.id, d.year)

    @classmethod
    def clear_cache(cls, env=None):
        """
        Limpia el cache de parámetros
        Útil cuando se actualizan parámetros anuales
        """
        global _PARAM_CACHE
        _PARAM_CACHE.clear()
    
    @classmethod
    def obtener_parametro_vigente(cls, env, fecha: date, clave: str) -> float:
        """
        Obtiene el valor vigente de un parámetro según fecha.
        
        Implementación para Reforma Laboral (Ley 2466/2025) y otros parámetros
        con vigencia por fecha.
        
        Args:
            env: Entorno de Odoo
            fecha: Fecha de consulta
            clave: Clave del parámetro
            
        Returns:
            Valor del parámetro vigente para esa fecha
            
        Ejemplos:
            - obtener_parametro_vigente(date(2025, 7, 1), 'RECARGO_DOMINICAL') -> 0.90
            - obtener_parametro_vigente(date(2025, 12, 25), 'RECARGO_NOCTURNO') -> 0.35
            - obtener_parametro_vigente(date(2025, 1, 1), 'JORNADA_SEMANAL') -> 44.0
        """
        # Tabla de parámetros con vigencia por fecha
        # Formato: (fecha_inicio, fecha_fin, clave, valor)
        PARAMETROS_VIGENCIA = [
            # Reforma Laboral - Recargo Dominical/Festivo
            (date(2025, 7, 1), date(2026, 6, 30), 'RECARGO_DOMINICAL', 0.80),
            (date(2026, 7, 1), date(2027, 6, 30), 'RECARGO_DOMINICAL', 0.90),
            (date(2027, 7, 1), None, 'RECARGO_DOMINICAL', 1.00),
            
            # Reforma Laboral - Recargo Nocturno (desde 7:00 p.m.)
            (date(2025, 12, 25), None, 'RECARGO_NOCTURNO', 0.35),
            
            # Reforma Laboral - Jornada Semanal
            (date(2025, 1, 1), date(2025, 12, 31), 'JORNADA_SEMANAL', 44.0),
            (date(2026, 1, 1), None, 'JORNADA_SEMANAL', 42.0),
            
            # Contrato término fijo máximo
            (date(2025, 1, 1), None, 'CONTRATO_FIJO_MAX_ANIOS', 4),
        ]
        
        # Buscar parámetro vigente
        for fecha_inicio, fecha_fin, param_clave, valor in PARAMETROS_VIGENCIA:
            if param_clave == clave:
                if fecha >= fecha_inicio:
                    if fecha_fin is None or fecha <= fecha_fin:
                        return valor
        
        # Si no se encuentra, retornar valor por defecto según clave
        defaults = {
            'RECARGO_DOMINICAL': 0.75,  # Antes de la reforma
            'RECARGO_NOCTURNO': 0.35,   # Antes de la reforma (ya estaba)
            'JORNADA_SEMANAL': 48.0,    # Antes de Ley 2101/2021
            'CONTRATO_FIJO_MAX_ANIOS': 3,  # Antes de la reforma
        }
        
        return defaults.get(clave, 0.0)
