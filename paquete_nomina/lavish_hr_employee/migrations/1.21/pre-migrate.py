# -*- coding: utf-8 -*-
"""
Pre-migration script for lavish_hr_employee 1.21

Adds new columns to hr_indicador_especial_pila table for:
- Prestaciones sociales (dias, base_dias, paga_*)
- Auxilio de transporte configuration
- Configuracion de uso (solo_prestaciones, no_usar_en_pila)
- Dias manuales para proporcionalidad
- Campos computados proporcionales
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    _logger.info("Pre-migrate 1.21: Adding new columns to hr_indicador_especial_pila")

    # Check if table exists
    cr.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'hr_indicador_especial_pila'
        )
    """)
    if not cr.fetchone()[0]:
        _logger.info("Table hr_indicador_especial_pila does not exist, skipping")
        return

    # Define columns to add with their defaults
    columns = [
        # Prestaciones - Vacaciones
        ("dias_vacaciones", "NUMERIC", "15.0"),
        ("base_dias_vacaciones", "VARCHAR", "'360'"),
        ("paga_vacaciones", "BOOLEAN", "TRUE"),
        ("dias_vacaciones_proporcional", "NUMERIC", "15.0"),

        # Prestaciones - Prima
        ("dias_prima", "NUMERIC", "15.0"),
        ("base_dias_prima", "VARCHAR", "'360'"),
        ("paga_prima", "BOOLEAN", "TRUE"),
        ("dias_prima_proporcional", "NUMERIC", "15.0"),

        # Prestaciones - Cesantias
        ("dias_cesantias", "NUMERIC", "30.0"),
        ("base_dias_cesantias", "VARCHAR", "'360'"),
        ("paga_cesantias", "BOOLEAN", "TRUE"),
        ("dias_cesantias_proporcional", "NUMERIC", "30.0"),

        # Prestaciones - Intereses
        ("porc_intereses_cesantias", "NUMERIC", "12.0"),
        ("paga_intereses_cesantias", "BOOLEAN", "TRUE"),
        ("porc_intereses_proporcional", "NUMERIC", "12.0"),

        # Base dias prestaciones
        ("base_dias_prestaciones", "VARCHAR", "'360'"),

        # Auxilio Transporte
        ("paga_auxilio_transporte", "BOOLEAN", "TRUE"),
        ("incluye_aux_transporte_prestaciones", "BOOLEAN", "TRUE"),

        # Configuracion de uso
        ("solo_prestaciones", "BOOLEAN", "FALSE"),
        ("no_usar_en_pila", "BOOLEAN", "FALSE"),

        # Dias manuales para proporcionalidad
        ("usar_dias_manuales", "BOOLEAN", "FALSE"),
        ("dias_manuales", "NUMERIC", "30.0"),
        ("dias_base_proporcion", "NUMERIC", "30.0"),

        # Porcentajes proporcionales (computados)
        ("porc_pension_proporcional", "NUMERIC", "0.0"),
        ("porc_salud_proporcional", "NUMERIC", "0.0"),
        ("factor_proporcion", "NUMERIC", "1.0"),
    ]

    for col_name, col_type, default_val in columns:
        # Check if column exists
        cr.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.columns
                WHERE table_name = 'hr_indicador_especial_pila'
                AND column_name = %s
            )
        """, (col_name,))

        if not cr.fetchone()[0]:
            _logger.info(f"Adding column {col_name} to hr_indicador_especial_pila")
            try:
                cr.execute(f"""
                    ALTER TABLE hr_indicador_especial_pila
                    ADD COLUMN {col_name} {col_type} DEFAULT {default_val}
                """)
            except Exception as e:
                _logger.warning(f"Error adding column {col_name}: {e}")
        else:
            _logger.info(f"Column {col_name} already exists, skipping")

    _logger.info("Pre-migrate 1.21: Completed adding columns to hr_indicador_especial_pila")
