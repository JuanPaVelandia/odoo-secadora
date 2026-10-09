# -*- coding: utf-8 -*-
"""Planes de mantenimiento por horómetro para las combinadas Kubota.

Replica los planes de los tractores (aceite 200 h / hidráulico 1200 h) pero
como planes APARTE, para que las combinadas no compartan el plan de los
tractores y se puedan ajustar intervalos sin tocarlos.

Las combinadas no tenían lecturas de horómetro en Odoo (Fracttal tampoco las
traía). El punto de partida sale de las notas de la última OT de cambio de
aceite, donde el taller anotó las horas. Para cada una se registra esa
lectura en el horómetro del equipo y se siembra la línea del plan:

    Aceite:     último cambio = horas anotadas en la OT
    Hidráulico: no hay horas del último cambio → arranca desde la lectura
                actual (mejor que darlo por vencido).

Las combinadas sin horas anotadas NO entran todavía al plan: si entraran
con "último cambio = 0", la primera lectura que se les registre dispararía
dos OT de inmediato. Hay que registrarles la primera lectura a mano desde
el equipo (botón "Lecturas de horómetro") y luego volver a correr este
script (o agregarlas al plan por pantalla): la línea arranca desde esa
lectura. El script es idempotente.

Se corre con el shell de Odoo en el VPS (no necesita credenciales):

    ssh odoo-vps "sudo -u odoo19 /opt/odoo19/odoo/odoo-venv/bin/python \\
        /opt/odoo19/odoo/odoo-bin shell -c /etc/odoo19.conf -d secadora_2 \\
        --no-http" < scripts/fracttal/planes_combinadas.py

Por defecto SIMULA (termina en rollback). Para aplicar, poner APLICAR = True.
"""
APLICAR = False

PLANES = [
    {'tarea': 'ACEITE', 'intervalo': 200.0,
     'name': 'Cambio de aceite de motor - Combinadas (200 h)',
     'descripcion': 'Cambio de aceite de motor y filtros cada 200 horas '
                    '(combinadas Kubota).'},
    {'tarea': 'HIDRAULICO', 'intervalo': 1200.0,
     'name': 'Cambio de hidráulico - Combinadas (1200 h)',
     'descripcion': 'Cambio de aceite hidráulico y filtros cada 1200 horas '
                    '(combinadas Kubota).'},
]

# Horas anotadas por el taller en la descripción de la última OT de cambio
# de aceite (revisadas el 9-oct-2026). Fecha = cierre de la OT.
#   equipo → (OT, fecha, horas, texto original)
LECTURAS_EN_OT = {
    'COMB KUBOTA DC105 FT/JPV 1': ('OT-1294', '2026-08-11', 1870.0,
                                   'Cambio de aceite a las 1.870 hrs'),
    'COMB KUBOTA DC105 FT/JPV 2': ('OT-1292', '2026-08-21', 1091.5,
                                   'Cambio de aceite: 1091.5 horas'),
    'COMB KUBOTA DC105 JPV 1':    ('OT-1290', '2026-08-11', 872.0,
                                   'Cambio a las 872 horas (11/08/2026)'),
    'COMB KUBOTA DC105 JV 1':     ('OT-1266', '2026-08-08', 2848.0,
                                   'CAMBIO A LAS 2848 HR'),
    'COMB KUBOTA DC105 JV 3':     ('OT-1264', '2026-08-14', 1224.0,
                                   'Cambio de aceite 1.224 hr'),
}

ADMIN_UID = 2  # las lecturas quedan "registradas por" el admin, no por OdooBot


def titulo(txt):
    print(f'\n{"=" * 72}\n{txt}\n{"=" * 72}')


def correr(env):
    print(f'Base: {env.cr.dbname} | Modo: {"APLICAR" if APLICAR else "SIMULACRO"}')
    Equipo = env['maintenance.equipment']
    Lectura = env['maintenance.horometro.reading']
    Plan = env['maintenance.task.plan']
    Linea = env['maintenance.task.plan.line']
    OT = env['maintenance.request']

    combinadas = Equipo.search([('name', '=ilike', 'COMB KUBOTA%'),
                                ('active', '=', True)], order='name')
    titulo(f'COMBINADAS KUBOTA: {len(combinadas)}')
    for eq in combinadas:
        print(f'   {eq.name:30} cía {eq.company_id.id}  '
              f'lecturas: {eq.horometro_reading_count}  '
              f'actual: {eq.horometro_current:,.0f} h')
    assert len(combinadas) == 11, f'Se esperaban 11 combinadas, hay {len(combinadas)}'

    contador = env['maintenance.counter.type'].search(
        [('unit', '=ilike', 'h%')], limit=1)
    assert contador, 'No hay tipo de contador en horas.'
    plan_tractores = Plan.search([('name', '=', 'Cambio de aceite de motor (200 h)')],
                                 limit=1)
    compania = plan_tractores.company_id or env.company

    # ---------- 1. Lecturas de horómetro desde las OT ----------
    titulo('LECTURAS DE HORÓMETRO (desde las notas de la OT)')
    lectura_por_equipo = {}
    creadas = 0
    for eq in combinadas:
        dato = LECTURAS_EN_OT.get(eq.name)
        if not dato:
            if eq.horometro_current > 0:
                # Ya le registraron la lectura a mano después de la primera
                # corrida: entra al plan desde ahí.
                lectura_por_equipo[eq.id] = (eq.horometro_current, None)
                print(f'   {eq.name:30} {eq.horometro_current:>8,.1f} h  '
                      f'(lectura ya registrada en Odoo)')
            else:
                print(f'   {eq.name:30} sin horas anotadas → NO entra al plan '
                      f'hasta registrarle la primera lectura')
            continue
        ot_num, fecha, horas, texto = dato
        ot = OT.search([('ot_number', '=', ot_num)], limit=1)
        assert ot and ot.equipment_id == eq, f'{ot_num} no es de {eq.name}'
        lectura_por_equipo[eq.id] = (horas, ot)
        ya = Lectura.search([('equipment_id', '=', eq.id),
                             ('value', '=', horas), ('date', '=', fecha)],
                            limit=1)
        print(f'   {eq.name:30} {horas:>8,.1f} h  el {fecha}  '
              f'({ot_num}: "{texto}"){"  [ya existe]" if ya else ""}')
        if not ya:
            Lectura.with_context(importando_historico=True,
                                 skip_task_plan_update=True).create({
                'equipment_id': eq.id,
                'date': fecha,
                'value': horas,
                'user_id': ADMIN_UID,
                'notes': f'Lectura tomada de la {ot_num} ({ot.name}): "{texto}".',
            })
            creadas += 1
    combinadas.invalidate_recordset(['horometro_current',
                                     'horometro_reading_count'])

    # ---------- 2. Planes ----------
    con_lectura = combinadas.filtered(lambda e: e.id in lectura_por_equipo)
    resumen = []
    for plan in PLANES:
        titulo(f'{plan["name"]}  →  {len(con_lectura)} de {len(combinadas)} '
               f'combinadas')
        vals = {
            'name': plan['name'],
            'description': plan['descripcion'],
            'counter_type_id': contador.id,
            'interval': plan['intervalo'],
            'company_id': compania.id,
            'equipment_ids': [(6, 0, con_lectura.ids)],
        }
        registro = Plan.search([('name', '=', plan['name'])], limit=1)
        if registro:
            print('   (ya existe, se actualiza la lista de equipos)')
            registro.write(vals)
        else:
            registro = Plan.create(vals)
        lineas = {l.equipment_id.id: l for l in registro.task_line_ids}
        assert set(lineas) == set(con_lectura.ids), 'Faltan líneas de plan'
        for eq in con_lectura:
            horas, ot = lectura_por_equipo[eq.id]
            vals_linea = {'last_counter_reading': horas,
                          'current_counter_reading': horas}
            # Solo el aceite tiene OT de respaldo: la lectura viene de ahí.
            if plan['tarea'] == 'ACEITE' and ot:
                vals_linea['last_request_id'] = ot.id
            lineas[eq.id].write(vals_linea)
            l = lineas[eq.id]
            print(f'   {eq.name:30} último {l.last_counter_reading:>8,.1f} h → '
                  f'próximo {l.next_counter_reading:>8,.1f} h  '
                  f'[{l.state}]')
        vencidas = registro.task_line_ids.filtered(lambda l: l.state == 'overdue')
        assert not vencidas, 'Ninguna línea debería nacer vencida'
        resumen.append((registro, len(registro.task_line_ids)))

    # Las OT del plan de tractores no deben verse afectadas.
    assert OT.search_count([('task_plan_id', 'in', [r.id for r, _ in resumen])]) == 0, \
        'Se generaron OT al sembrar: no debería'

    titulo('RESUMEN')
    print(f'   Combinadas: {len(combinadas)} | en el plan: '
          f'{len(con_lectura)} | fuera del plan hasta tener lectura: '
          f'{len(combinadas) - len(con_lectura)} | '
          f'lecturas nuevas: {creadas}')
    for eq in combinadas - con_lectura:
        print(f'      pendiente: {eq.name}')
    for registro, n in resumen:
        print(f'   {registro.name:50} {n:>3} líneas')
    print(f'   Planes en la base: {Plan.search_count([])} | '
          f'líneas: {Linea.search_count([])}')


correr(env)
if APLICAR:
    env.cr.commit()
    print('\n   *** APLICADO (commit). ***')
else:
    env.cr.rollback()
    print('\n   *** SIMULACRO: rollback, no se escribió nada. ***')
