# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Taras y viajes pasaron de tractor/tolvo (secadora.vehiculo) a combos
    de equipos de mantenimiento. Soltar los NOT NULL de las columnas viejas
    para que los registros nuevos puedan insertarse.
    """
    for tabla in ('secadora_embolsado_tara', 'secadora_embolsado_viaje'):
        for columna in ('tractor_id', 'tolvo_id'):
            cr.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_name = %s AND column_name = %s AND is_nullable = 'NO'
                """,
                (tabla, columna),
            )
            if cr.fetchone():
                cr.execute(
                    'ALTER TABLE "%s" ALTER COLUMN "%s" DROP NOT NULL' % (tabla, columna)
                )
