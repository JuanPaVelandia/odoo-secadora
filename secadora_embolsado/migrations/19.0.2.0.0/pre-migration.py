# -*- coding: utf-8 -*-


def migrate(cr, version):
    """El viaje pasó de apuntar a una posición a apuntar al contenedor (FIFO).

    La columna posicion_id quedó huérfana con NOT NULL: soltarla para que los
    viajes nuevos (sin posición) puedan insertarse.
    """
    cr.execute("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'secadora_embolsado_viaje'
                  AND column_name = 'posicion_id'
            ) THEN
                ALTER TABLE secadora_embolsado_viaje
                    ALTER COLUMN posicion_id DROP NOT NULL;
            END IF;
        END $$;
    """)
