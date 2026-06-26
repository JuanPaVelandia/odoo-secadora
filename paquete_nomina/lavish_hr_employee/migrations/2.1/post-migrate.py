# -*- coding: utf-8 -*-
"""
Migración 2.1: Crear/Actualizar tipos de contrato colombianos
==============================================================
Asegura que todos los tipos de contrato existan con el campo contract_category.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Post-migración: Crear o actualizar tipos de contrato colombianos"""
    _logger.info("=== INICIO POST-MIGRACIÓN 2.1: Crear/Actualizar tipos de contrato ===")

    # Obtener el ID de Colombia
    cr.execute("SELECT id FROM res_country WHERE code = 'CO' LIMIT 1")
    result = cr.fetchone()
    country_id = result[0] if result else None
    _logger.info(f"ID de Colombia: {country_id}")

    # Definir los tipos de contrato
    contract_types = [
        {
            'name': 'Contrato a Término Indefinido',
            'code': 'INDEFINIDO',
            'sequence': 5,
            'contract_category': 'indefinido',
        },
        {
            'name': 'Contrato a Término Fijo',
            'code': 'FIJO',
            'sequence': 10,
            'contract_category': 'fijo',
        },
        {
            'name': 'Contrato a Término Fijo Tiempo Parcial',
            'code': 'FIJO_PARCIAL',
            'sequence': 12,
            'contract_category': 'fijo',
        },
        {
            'name': 'Contrato por Obra o Labor',
            'code': 'OBRA',
            'sequence': 15,
            'contract_category': 'obra',
        },
        {
            'name': 'Contrato de Aprendizaje',
            'code': 'APRENDIZAJE',
            'sequence': 20,
            'contract_category': 'aprendizaje',
        },
        {
            'name': 'Contrato Ocasional o Transitorio',
            'code': 'OCASIONAL',
            'sequence': 25,
            'contract_category': 'ocasional',
        },
        {
            'name': 'Contrato Agropecuario',
            'code': 'AGROPECUARIO',
            'sequence': 30,
            'contract_category': 'agropecuario',
        },
    ]

    for ct in contract_types:
        # Verificar si ya existe el tipo
        cr.execute(
            "SELECT id FROM hr_contract_type WHERE code = %s AND (country_id = %s OR country_id IS NULL)",
            (ct['code'], country_id)
        )
        existing = cr.fetchone()

        if existing:
            _logger.info(f"Tipo de contrato '{ct['name']}' ya existe (ID: {existing[0]}), actualizando contract_category...")
            # Actualizar solo contract_category si no tiene
            cr.execute("""
                UPDATE hr_contract_type
                SET contract_category = %s
                WHERE id = %s AND (contract_category IS NULL OR contract_category = '')
            """, (ct['contract_category'], existing[0]))
            if cr.rowcount > 0:
                _logger.info(f"Actualizado contract_category para {ct['name']}")
        else:
            _logger.info(f"Creando tipo de contrato: {ct['name']}")
            # Crear el tipo básico (el resto se carga desde data XML)
            cr.execute("""
                INSERT INTO hr_contract_type (name, code, sequence, country_id, contract_category)
                VALUES (%s, %s, %s, %s, %s)
            """, (ct['name'], ct['code'], ct['sequence'], country_id, ct['contract_category']))

    _logger.info("=== FIN POST-MIGRACIÓN 2.1 ===")
