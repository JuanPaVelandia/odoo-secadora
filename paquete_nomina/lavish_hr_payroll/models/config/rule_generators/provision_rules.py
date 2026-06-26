# -*- coding: utf-8 -*-
"""
Generador de Reglas de Provisiones
====================================
Genera reglas salariales para provisiones (vacaciones, cesantías, intereses, primas).
"""


class ProvisionRulesGenerator:
    """Generador de reglas de provisiones"""
    
    @staticmethod
    def get_rules():
        """
        Retorna lista de reglas de provisiones.
        
        Returns:
            list: Lista de diccionarios con propiedades de reglas
        """
        return [
            {
                'code': 'PRV_VAC',
                'name': 'PROV. VACACIONES',
                'category_code': 'PROV',
                'sequence': 306,
                'process_code': 'nomina',
                'appears_on_payslip': False
            },
            {
                'code': 'PRV_CES',
                'name': 'PROV. CESANTIAS',
                'category_code': 'PROV',
                'sequence': 304,
                'process_code': 'nomina',
                'appears_on_payslip': False
            },
            {
                'code': 'PRV_ICES',
                'name': 'PROV. INT. CESANTIAS',
                'category_code': 'PROV',
                'sequence': 305,
                'process_code': 'nomina',
                'appears_on_payslip': False
            },
            {
                'code': 'PRV_PRIM',
                'name': 'PROV. PRIMAS',
                'category_code': 'PROV',
                'sequence': 302,
                'process_code': 'nomina',
                'appears_on_payslip': False
            },
        ]
