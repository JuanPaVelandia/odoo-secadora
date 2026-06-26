"""Fix hr.payslip.run state labels en es_CO/es/es_419.

Cuando se cargo el modulo en v19 enterprise, las traducciones de los valores
de Selection state (Ready/Done/Paid) fueron capturadas como es_CO="Listo"
para varios valores. Al renombrar las labels v18-style (Nuevo/Confirmado/Listo/
Pagado/Cancelado) las traducciones es_CO quedaron desactualizadas y muestran
"Listo" para 01_ready y 02_close. Aqui las sincronizamos con el en_US correcto
o eliminamos las claves obsoletas para que caigan al en_US.
"""
import json
import logging

_logger = logging.getLogger(__name__)

LABELS = {
    '01_ready': 'Nuevo',
    '02_close': 'Confirmado',
    '02b_done': 'Listo',
    '03_paid': 'Pagado',
    '04_cancel': 'Cancelado',
}


def migrate(cr, version):
    if not version:
        return

    _logger.info("Sincronizando labels es_CO/es/es_419 de hr.payslip.run.state")

    cr.execute("""
        SELECT s.id, s.value, s.name
        FROM ir_model_fields_selection s
        JOIN ir_model_fields f ON f.id = s.field_id
        WHERE f.model = 'hr.payslip.run' AND f.name = 'state'
    """)

    for sel_id, value, name_json in cr.fetchall():
        target = LABELS.get(value)
        if not target:
            continue
        new_name = dict(name_json or {})
        new_name['en_US'] = target
        for lang in ('es_CO', 'es', 'es_419'):
            new_name[lang] = target
        cr.execute(
            "UPDATE ir_model_fields_selection SET name = %s::jsonb WHERE id = %s",
            (json.dumps(new_name), sel_id),
        )
    _logger.info("Labels hr.payslip.run.state actualizadas")
