# -*- coding: utf-8 -*-
"""
Generador de Reglas de Consolidación
=====================================
Genera reglas salariales para consolidación de prestaciones sociales.

La consolidación compara:
- Saldo cuenta provisión (26XX - Pasivos estimados)
- Saldo cuenta obligación (25XX - Obligaciones laborales)

Cuentas PUC Colombia:
- Cesantías:  261005 (Prov) vs 2510 (Oblig)
- Intereses:  261010 (Prov) vs 2515 (Oblig)
- Vacaciones: 261015 (Prov) vs 2525 (Oblig)
"""


class ConsolidacionRulesGenerator:
    """Generador de reglas de consolidación de prestaciones"""

    # Configuración de cuentas PUC para cada concepto
    CUENTAS_PUC = {
        'cesantias': {
            'provision': '261005',    # Provisión cesantías
            'obligacion': '2510',     # Cesantías consolidadas
        },
        'intereses': {
            'provision': '261010',    # Provisión intereses sobre cesantías
            'obligacion': '2515',     # Intereses sobre cesantías
        },
        'vacaciones': {
            'provision': '261015',    # Provisión vacaciones
            'obligacion': '2525',     # Vacaciones consolidadas
        },
        'primas': {
            'provision': '261020',    # Provisión prima de servicios
            'obligacion': '2520',     # Prima de servicios
        },
    }

    @staticmethod
    def get_rules():
        """
        Retorna lista de reglas de consolidación.

        Returns:
            list: Lista de diccionarios con propiedades de reglas
        """
        return [
            # CONSOLIDACIÓN VACACIONES - Código: CONS_VAC
            {
                'code': 'CONS_VAC',
                'name': 'CONSOLIDACIÓN VACACIONES',
                'category_code': 'CONS',
                'sequence': 500,
                'process_code': 'consolidacion',
                'appears_on_payslip': True,
                'cuenta_provision': '261015',
                'cuenta_obligacion': '2525',
                # Ajuste = Obligación real - Provisión acumulada
            },

            # CONSOLIDACIÓN CESANTÍAS - Código: CONS_CES
            {
                'code': 'CONS_CES',
                'name': 'CONSOLIDACIÓN CESANTÍAS',
                'category_code': 'CONS',
                'sequence': 501,
                'process_code': 'consolidacion',
                'appears_on_payslip': True,
                'cuenta_provision': '261005',
                'cuenta_obligacion': '2510',
                # Contabilidad: D:2510 (Oblig) C:261005 (Prov)
            },

            # CONSOLIDACIÓN INTERESES CESANTÍAS - Código: CONS_INT
            {
                'code': 'CONS_INT',
                'name': 'CONSOLIDACIÓN INTERESES CESANTÍAS',
                'category_code': 'CONS',
                'sequence': 502,
                'process_code': 'consolidacion',
                'appears_on_payslip': True,
                'cuenta_provision': '261010',
                'cuenta_obligacion': '2515',
                # Contabilidad: D:2515 (Oblig) C:261010 (Prov)
            },

            # GASTO FESTIVO - Ajuste de provisión vs obligación
            # Se usa cuando solo hay una cuenta de provisión para ajustar
            # la diferencia entre lo provisionado y la obligación real
            {
                'code': 'GASTO_FESTIVO',
                'name': 'GASTO FESTIVO - AJUSTE PROVISIÓN/OBLIGACIÓN',
                'category_code': 'CONSOLIDACION',
                'sequence': 510,
                'process_code': 'consolidacion',
                'appears_on_payslip': False,
                'cuenta_provision': '261015',  # Provisión vacaciones (gasto)
                'cuenta_obligacion': '2525',   # Vacaciones consolidadas
                # Contabilidad: D:261015 (Prov/Gasto) C:2525 (Oblig)
                # Este es el movimiento inverso para ajustar
            },
        ]

    @classmethod
    def get_cuenta_provision(cls, concepto):
        """
        Obtiene el código de cuenta de provisión para un concepto.

        Args:
            concepto: 'cesantias', 'intereses', 'vacaciones', 'primas'

        Returns:
            str: Código de cuenta PUC (ej: '261005')
        """
        config = cls.CUENTAS_PUC.get(concepto, {})
        return config.get('provision', '')

    @classmethod
    def get_cuenta_obligacion(cls, concepto):
        """
        Obtiene el código de cuenta de obligación para un concepto.

        Args:
            concepto: 'cesantias', 'intereses', 'vacaciones', 'primas'

        Returns:
            str: Código de cuenta PUC (ej: '2510')
        """
        config = cls.CUENTAS_PUC.get(concepto, {})
        return config.get('obligacion', '')

    @classmethod
    def get_all_cuentas(cls):
        """
        Retorna todas las cuentas configuradas.

        Returns:
            dict: Diccionario con todas las cuentas PUC
        """
        return cls.CUENTAS_PUC.copy()
