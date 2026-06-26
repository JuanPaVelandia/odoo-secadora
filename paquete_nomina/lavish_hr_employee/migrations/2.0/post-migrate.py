# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Post-migracion: Actualizar valores de prestaciones sociales.

    1. Actualiza hr.tipo.cotizante para tipos que no generan prestaciones
    2. Inicializa campos de prestaciones en hr.contract existentes
    """
    if not version:
        return

    _logger.info("Post-migracion lavish_hr_employee 2.0: Actualizando prestaciones sociales")

    # ═══════════════════════════════════════════════════════════════════════
    # 1. ACTUALIZAR hr.tipo.cotizante
    # ═══════════════════════════════════════════════════════════════════════
    cr.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'hr_tipo_cotizante'
        AND column_name = 'not_generate_prima'
    """)
    if cr.fetchone():
        # Tipos de cotizante que NO generan prestaciones sociales
        # 12 = Aprendiz lectivo, 19 = Aprendiz productivo, 20 = Estudiante
        tipos_sin_prestaciones = ['12', '19', '20']

        cr.execute("""
            UPDATE hr_tipo_cotizante
            SET not_generate_prima = TRUE,
                not_generate_cesantias = TRUE,
                not_generate_intereses_cesantias = TRUE,
                not_generate_vacaciones = TRUE
            WHERE code IN %s
            RETURNING id, code, name
        """, (tuple(tipos_sin_prestaciones),))

        updated = cr.fetchall()
        for tipo_id, code, name in updated:
            _logger.info(f"  Tipo cotizante {code}: {name} - Sin prestaciones")
        _logger.info(f"  Tipos cotizante actualizados: {len(updated)}")

    # ═══════════════════════════════════════════════════════════════════════
    # 2. INICIALIZAR hr.contract
    # ═══════════════════════════════════════════════════════════════════════
    cr.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'hr_contract'
        AND column_name = 'not_generate_prima'
    """)
    if cr.fetchone():
        # Verificar si existe el campo modality_salary
        cr.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'hr_contract'
            AND column_name = 'modality_salary'
        """)
        has_modality_salary = cr.fetchone()

        # 2.1 Contratos con modalidad integral: no genera prima, cesantias, intereses
        # Solo vacaciones aplica para salario integral
        count_integral = 0
        if has_modality_salary:
            cr.execute("""
                UPDATE hr_contract
                SET not_generate_prima = TRUE,
                    not_generate_cesantias = TRUE,
                    not_generate_intereses_cesantias = TRUE,
                    not_generate_vacaciones = FALSE
                WHERE modality_salary = 'integral'
                RETURNING id
            """)
            count_integral = cr.rowcount
        _logger.info(f"  Contratos integrales actualizados: {count_integral}")

        # Verificar si existe el campo contract_type
        cr.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'hr_contract'
            AND column_name = 'contract_type'
        """)
        has_contract_type = cr.fetchone()

        # 2.2 Contratos de aprendizaje: no genera ninguna prestacion
        count_aprendizaje = 0
        if has_contract_type:
            cr.execute("""
                UPDATE hr_contract
                SET not_generate_prima = TRUE,
                    not_generate_cesantias = TRUE,
                    not_generate_intereses_cesantias = TRUE,
                    not_generate_vacaciones = TRUE
                WHERE contract_type = 'aprendizaje'
                RETURNING id
            """)
            count_aprendizaje = cr.rowcount
        _logger.info(f"  Contratos aprendizaje actualizados: {count_aprendizaje}")

        # 2.3 Contratos con tipo cotizante sin prestaciones
        count_tipo_coti = 0
        try:
            # Construir condiciones dinamicamente segun campos existentes
            conditions = ["tc.not_generate_prima = TRUE"]
            if has_modality_salary:
                conditions.append("c.modality_salary != 'integral'")
            if has_contract_type:
                conditions.append("c.contract_type != 'aprendizaje'")

            where_clause = " AND ".join(conditions)

            cr.execute(f"""
                UPDATE hr_contract c
                SET not_generate_prima = tc.not_generate_prima,
                    not_generate_cesantias = tc.not_generate_cesantias,
                    not_generate_intereses_cesantias = tc.not_generate_intereses_cesantias,
                    not_generate_vacaciones = tc.not_generate_vacaciones
                FROM hr_employee e
                JOIN hr_tipo_cotizante tc ON e.tipo_coti_id = tc.id
                WHERE c.employee_id = e.id
                AND {where_clause}
                RETURNING c.id
            """)
            count_tipo_coti = cr.rowcount
        except Exception as e:
            _logger.warning(f"  Error actualizando contratos por tipo cotizante: {e}")
        _logger.info(f"  Contratos por tipo cotizante actualizados: {count_tipo_coti}")

        # 2.4 Resto de contratos: todas las prestaciones aplican (valores por defecto)
        cr.execute("""
            UPDATE hr_contract
            SET not_generate_prima = FALSE,
                not_generate_cesantias = FALSE,
                not_generate_intereses_cesantias = FALSE,
                not_generate_vacaciones = FALSE
            WHERE not_generate_prima IS NULL
            RETURNING id
        """)
        count_default = cr.rowcount
        _logger.info(f"  Contratos con valores por defecto: {count_default}")

    _logger.info("Post-migracion lavish_hr_employee 2.0 completada")
