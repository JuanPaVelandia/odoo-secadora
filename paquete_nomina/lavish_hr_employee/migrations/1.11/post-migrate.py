# -*- coding: utf-8 -*-
"""
Migracion 1.11: Tipos de Contrato Ley 2466/2025
================================================
Crea los tipos de contrato base segun la reforma laboral colombiana
y mapea los contratos existentes a los nuevos tipos.

Referencia Legal: https://www.alcaldiabogota.gov.co/sisjur/normas/Norma1.jsp?i=181933

Tipos de Contrato creados:
- Termino Fijo (max 4 anos, renovacion automatica)
- Termino Indefinido (modalidad preferente)
- Obra o Labor
- Aprendizaje (75% lectiva, 100% productiva + prestaciones)
- Ocasional/Transitorio (max 30 dias)
- Agropecuario (nuevo tipo Ley 2466)
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Migracion post-instalacion para crear tipos de contrato
    y mapear contratos existentes.
    """
    _logger.info("=== INICIO MIGRACION 1.11: Tipos de Contrato Ley 2466/2025 ===")

    # Obtener el ID de Colombia
    cr.execute("SELECT id FROM res_country WHERE code = 'CO' LIMIT 1")
    result = cr.fetchone()
    country_id = result[0] if result else None

    if not country_id:
        _logger.warning("No se encontro el pais Colombia (CO), los tipos se crearan sin pais")

    # Definir los tipos de contrato segun Ley 2466/2025
    contract_types = [
        {
            'name': 'Contrato a Termino Fijo',
            'code': 'FIJO',
            'sequence': 10,
            'country_id': country_id,
            'contract_category': 'fijo',
            'requires_end_date': True,
            'max_duration_months': 48,
            'max_renewals': 3,
            'auto_convert_indefinite': True,
            'renewal_notice_days': 30,
            'auto_renewal': True,
            'has_prima': True,
            'has_cesantias': True,
            'has_intereses_cesantias': True,
            'has_vacaciones': True,
            'has_dotacion': True,
            'has_auxilio_transporte': True,
            'has_salud': True,
            'has_pension': True,
            'has_riesgos': True,
            'has_caja_compensacion': True,
            'has_parafiscales': True,
            'indemnization_type': 'dias_faltantes',
            'has_union_rights': True,
            'description': 'Contrato de trabajo a termino fijo segun Ley 2466 de 2025. '
                          'Duracion maxima de 4 anos incluyendo renovaciones. '
                          'Se convierte automaticamente a indefinido si supera este limite.',
        },
        {
            'name': 'Contrato a Termino Indefinido',
            'code': 'INDEFINIDO',
            'sequence': 5,
            'country_id': country_id,
            'contract_category': 'indefinido',
            'requires_end_date': False,
            'max_duration_months': 0,
            'max_renewals': 0,
            'auto_convert_indefinite': False,
            'has_prima': True,
            'has_cesantias': True,
            'has_intereses_cesantias': True,
            'has_vacaciones': True,
            'has_dotacion': True,
            'has_auxilio_transporte': True,
            'has_salud': True,
            'has_pension': True,
            'has_riesgos': True,
            'has_caja_compensacion': True,
            'has_parafiscales': True,
            'indemnization_type': 'tabla_antiguedad',
            'has_union_rights': True,
            'description': 'Contrato de trabajo a termino indefinido. '
                          'Modalidad preferente segun Ley 2466 de 2025.',
        },
        {
            'name': 'Contrato por Obra o Labor',
            'code': 'OBRA',
            'sequence': 15,
            'country_id': country_id,
            'contract_category': 'obra',
            'requires_end_date': False,
            'max_duration_months': 0,
            'max_renewals': 0,
            'auto_convert_indefinite': False,
            'has_prima': True,
            'has_cesantias': True,
            'has_intereses_cesantias': True,
            'has_vacaciones': True,
            'has_dotacion': True,
            'has_auxilio_transporte': True,
            'has_salud': True,
            'has_pension': True,
            'has_riesgos': True,
            'has_caja_compensacion': True,
            'has_parafiscales': True,
            'indemnization_type': 'dias_faltantes',
            'indemnization_min_days': 15,
            'has_union_rights': True,
            'description': 'Contrato de trabajo por obra o labor determinada. '
                          'Termina al completar la obra o labor contratada.',
        },
        {
            'name': 'Contrato de Aprendizaje',
            'code': 'APRENDIZAJE',
            'sequence': 20,
            'country_id': country_id,
            'contract_category': 'aprendizaje',
            'requires_end_date': True,
            'max_duration_months': 24,
            'is_apprenticeship': True,
            'apprentice_wage_pct_lectiva': 75.0,
            'apprentice_wage_pct_productiva': 100.0,
            'apprentice_max_duration_months': 24,
            # Ley 2466: Aprendices ahora tienen prestaciones
            'has_prima': True,
            'has_cesantias': True,
            'has_intereses_cesantias': True,
            'has_vacaciones': True,
            'has_dotacion': False,
            'has_auxilio_transporte': True,
            'has_salud': True,
            'has_pension': True,  # Ley 2466: derecho a pension
            'has_riesgos': True,
            'has_caja_compensacion': False,
            'has_parafiscales': False,
            'indemnization_type': 'no_aplica',
            'has_union_rights': True,  # Ley 2466: derecho a sindicalizacion
            'description': 'Contrato de aprendizaje segun Ley 2466 de 2025. '
                          'Etapa lectiva: 75%% SMMLV. Etapa productiva: 100%% SMMLV. '
                          'Incluye prestaciones sociales, pension y derecho a sindicalizacion.',
        },
        {
            'name': 'Contrato Ocasional o Transitorio',
            'code': 'OCASIONAL',
            'sequence': 25,
            'country_id': country_id,
            'contract_category': 'ocasional',
            'requires_end_date': True,
            'max_duration_days': 30,
            'max_duration_months': 0,
            'has_prima': False,
            'has_cesantias': False,
            'has_intereses_cesantias': False,
            'has_vacaciones': False,
            'has_dotacion': False,
            'has_auxilio_transporte': True,
            'has_salud': True,
            'has_pension': True,
            'has_riesgos': True,
            'has_caja_compensacion': False,
            'has_parafiscales': False,
            'indemnization_type': 'no_aplica',
            'has_union_rights': True,
            'description': 'Contrato ocasional, accidental o transitorio. '
                          'Para tareas excepcionales no habituales. Duracion maxima 30 dias.',
        },
        {
            'name': 'Contrato Agropecuario',
            'code': 'AGROPECUARIO',
            'sequence': 30,
            'country_id': country_id,
            'contract_category': 'agropecuario',
            'requires_end_date': False,
            'is_agricultural': True,
            'agricultural_special_rules': True,
            'has_prima': True,
            'has_cesantias': True,
            'has_intereses_cesantias': True,
            'has_vacaciones': True,
            'has_dotacion': True,
            'has_auxilio_transporte': False,  # Sector rural puede no aplicar
            'has_salud': True,
            'has_pension': True,
            'has_riesgos': True,
            'has_caja_compensacion': True,
            'has_parafiscales': True,
            'indemnization_type': 'tabla_antiguedad',
            'has_union_rights': True,
            'description': 'Contrato agropecuario segun Ley 2466 de 2025. '
                          'Especifico para el sector agricola y pecuario con reglas '
                          'especiales de jornada, descanso y riesgos laborales.',
        },
        {
            'name': 'Contrato a Termino Fijo Tiempo Parcial',
            'code': 'FIJO_PARCIAL',
            'sequence': 12,
            'country_id': country_id,
            'contract_category': 'fijo',
            'requires_end_date': True,
            'max_duration_months': 48,
            'max_renewals': 3,
            'auto_convert_indefinite': True,
            'renewal_notice_days': 30,
            'auto_renewal': True,
            'has_prima': True,
            'has_cesantias': True,
            'has_intereses_cesantias': True,
            'has_vacaciones': True,
            'has_dotacion': True,
            'has_auxilio_transporte': True,
            'has_salud': True,
            'has_pension': True,
            'has_riesgos': True,
            'has_caja_compensacion': True,
            'has_parafiscales': True,
            'indemnization_type': 'dias_faltantes',
            'has_union_rights': True,
            'description': 'Contrato de trabajo a termino fijo con jornada parcial.',
        },
    ]

    # Crear los tipos de contrato
    for ct in contract_types:
        # Verificar si ya existe
        cr.execute(
            "SELECT id FROM hr_contract_type WHERE code = %s AND (country_id = %s OR country_id IS NULL)",
            (ct['code'], country_id)
        )
        existing = cr.fetchone()

        if existing:
            _logger.info(f"Tipo de contrato '{ct['name']}' ya existe (ID: {existing[0]}), actualizando...")
            # Actualizar campos existentes
            update_fields = []
            update_values = []
            for key, value in ct.items():
                if key not in ('name', 'code'):  # No actualizar name y code
                    update_fields.append(f"{key} = %s")
                    update_values.append(value)

            if update_fields:
                update_values.append(existing[0])
                cr.execute(
                    f"UPDATE hr_contract_type SET {', '.join(update_fields)} WHERE id = %s",
                    tuple(update_values)
                )
        else:
            _logger.info(f"Creando tipo de contrato: {ct['name']}")
            # Construir la consulta INSERT
            fields = list(ct.keys())
            placeholders = ', '.join(['%s'] * len(fields))
            columns = ', '.join(fields)
            values = [ct[f] for f in fields]

            cr.execute(
                f"INSERT INTO hr_contract_type ({columns}) VALUES ({placeholders})",
                tuple(values)
            )

    # Mapear contratos existentes al nuevo hr.contract.type
    _logger.info("Mapeando contratos existentes a tipos de contrato...")

    # Mapeo de contract_type (selection) a codigo de hr.contract.type
    mapping = {
        'obra': 'OBRA',
        'fijo': 'FIJO',
        'fijo_parcial': 'FIJO_PARCIAL',
        'indefinido': 'INDEFINIDO',
        'aprendizaje': 'APRENDIZAJE',
        'temporal': 'OCASIONAL',
    }

    for old_type, new_code in mapping.items():
        # Obtener el ID del nuevo tipo
        cr.execute(
            "SELECT id FROM hr_contract_type WHERE code = %s AND (country_id = %s OR country_id IS NULL) LIMIT 1",
            (new_code, country_id)
        )
        result = cr.fetchone()

        if result:
            new_type_id = result[0]
            # Actualizar contratos que no tienen contract_type_id asignado
            cr.execute("""
                UPDATE hr_contract
                SET contract_type_id = %s
                WHERE contract_type = %s
                AND (contract_type_id IS NULL OR contract_type_id = 0)
            """, (new_type_id, old_type))

            updated = cr.rowcount
            if updated > 0:
                _logger.info(f"Actualizados {updated} contratos de tipo '{old_type}' a hr.contract.type '{new_code}'")

    _logger.info("=== FIN MIGRACION 1.11: Tipos de Contrato Ley 2466/2025 ===")
