# -*- coding: utf-8 -*-
"""
Generador de Reglas de Seguridad Social
=======================================
Genera reglas salariales para seguridad social (salud, pensión, fondos).
"""


class SocialSecurityRulesGenerator:
    """Generador de reglas de seguridad social"""
    
    @staticmethod
    def get_rules():
        """
        Retorna lista de reglas de seguridad social.
        
        Returns:
            list: Lista de diccionarios con propiedades de reglas
        """
        return [
            {
                'code': 'SSOCIAL002',
                'name': 'PENSION EMPLEADO',
                'category_code': 'SSOCIAL',
                'sequence': 201,
                'process_code': 'nomina',
                'dev_or_ded': 'deduccion'
            },
            {
                'code': 'SSOCIAL001',
                'name': 'SALUD EMPLEADO',
                'category_code': 'SSOCIAL',
                'sequence': 200,
                'process_code': 'nomina',
                'dev_or_ded': 'deduccion'
            },
            {
                'code': 'SSOCIAL004',
                'name': 'FONDO SOLIDADRIDAD',
                'category_code': 'SSOCIAL',
                'sequence': 203,
                'process_code': 'nomina',
                'dev_or_ded': 'deduccion'
            },
            {
                'code': 'SSOCIAL003',
                'name': 'FONDO DE SUBSISTENCIA',
                'category_code': 'SSOCIAL',
                'sequence': 202,
                'process_code': 'nomina',
                'dev_or_ded': 'deduccion'
            },
        ]
