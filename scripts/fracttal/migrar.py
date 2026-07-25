#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Migra el historial de mantenimiento de Fracttal a Odoo.

Idempotente: cada registro se identifica por su clave externa (`external_ref`
en equipos y OT), así que volver a correrlo no duplica — solo carga lo que
falte. Por defecto SIMULA; para escribir hay que pasar --aplicar.

    python3 migrar.py                    # simulacro, no escribe nada
    python3 migrar.py --aplicar          # carga completa
    python3 migrar.py --aplicar --paso=activos    # solo una etapa
    python3 migrar.py --db=odoo_prueba_4 --aplicar

Etapas (en orden, cada una depende de la anterior):
    catalogos → activos → horometros → ordenes
"""
import sys
import os
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comun
import mapeo
from comun import (Odoo, leer_export, a_fecha, a_datetime, a_float, a_horas,
                   lectura_horometro, ultimo_nodo, barra)

APLICAR = '--aplicar' in sys.argv
DB = next((a.split('=', 1)[1] for a in sys.argv if a.startswith('--db=')),
          comun.DB_POR_DEFECTO)
PASOS = next((a.split('=', 1)[1] for a in sys.argv if a.startswith('--paso=')),
             'catalogos,activos,horometros,ordenes').split(',')

ORIGEN = 'Fracttal'


def titulo(txt):
    print(f'\n{"=" * 72}\n{txt}\n{"=" * 72}')


def log(txt):
    print(f'   {txt}')


class Migracion:
    def __init__(self, odoo):
        self.o = odoo
        self.stats = defaultdict(int)
        # cachés resueltas en preparar()
        self.companias = {}
        self.lugares = {}
        self.areas = {}
        self.categorias = {}
        self.equipos = {}          # nombre normalizado → id
        self.equipo_cia = {}       # nombre normalizado → id de compañía
        self.etapas = {}
        self.equipos_mant = {}     # id compañía → id maintenance.team
        self.partners = {}

    # ------------------------------------------------------------------
    # Preparación: leer lo que ya existe en Odoo
    # ------------------------------------------------------------------
    def preparar(self):
        o = self.o
        self.companias = {c['name']: c['id']
                          for c in o.buscar_leer('res.company', [], ['name'])}
        self.lugares = {mapeo.normalizar(l['name']): l['id']
                        for l in o.buscar_leer('secadora.lugar', [], ['name'])}
        self.areas = {mapeo.normalizar(a['name']): a['id']
                      for a in o.buscar_leer('secadora.origen.muestra', [], ['name'])}
        self.categorias = {c['name']: c['id']
                           for c in o.buscar_leer('maintenance.equipment.category',
                                                  [], ['name'])}
        self.etapas = {s['name']: s['id']
                       for s in o.buscar_leer('maintenance.stage', [], ['name'])}
        for eq in o.buscar_leer('maintenance.equipment', [], ['name', 'company_id']):
            self.equipos[mapeo.normalizar(eq['name'])] = eq['id']
            if eq['company_id']:
                self.equipo_cia[mapeo.normalizar(eq['name'])] = eq['company_id'][0]
        for t in o.buscar_leer('maintenance.team', [], ['name', 'company_id']):
            if t['company_id']:
                self.equipos_mant.setdefault(t['company_id'][0], t['id'])
        log(f'Compañías: {len(self.companias)} | Lugares: {len(self.lugares)} | '
            f'Áreas: {len(self.areas)} | Categorías: {len(self.categorias)}')
        log(f'Equipos ya en Odoo: {len(self.equipos)}')

    def cia(self, nombre):
        return self.companias.get(nombre)

    # ------------------------------------------------------------------
    # 1. Catálogos: lugares faltantes, áreas, talleres, equipos de mant.
    # ------------------------------------------------------------------
    def paso_catalogos(self):
        titulo('1. CATÁLOGOS (lugares, áreas de proceso, talleres)')
        o = self.o

        # --- Lugares que faltan ---
        for nombre, datos in mapeo.LUGAR_A_CREAR.items():
            destino = mapeo.LUGAR_EXISTENTE.get(nombre, nombre)
            if mapeo.normalizar(destino) in self.lugares:
                log(f'lugar ya existe, se reusa: {destino}')
                continue
            vals = dict(datos, name=destino)
            if APLICAR:
                nuevo = o.crear('secadora.lugar', vals)
                self.lugares[mapeo.normalizar(destino)] = nuevo
            log(f'CREAR lugar: {destino} ({datos["municipio"]})')
            self.stats['lugares_creados'] += 1

        # --- Áreas de proceso que faltan (se reusa secadora.origen.muestra) ---
        for nombre, codigo in mapeo.AREA_A_CREAR.items():
            if mapeo.normalizar(nombre) in self.areas:
                log(f'área ya existe, se reusa: {nombre}')
                continue
            if APLICAR:
                nuevo = o.crear('secadora.origen.muestra',
                                {'name': nombre, 'codigo': codigo, 'sequence': 50})
                self.areas[mapeo.normalizar(nombre)] = nuevo
            log(f'CREAR área de proceso: {nombre}')
            self.stats['areas_creadas'] += 1

        # --- Talleres como proveedores ---
        for taller in sorted(mapeo.TALLERES):
            existente = o.buscar('res.partner', [('name', '=', taller)], limit=1)
            if existente:
                self.partners[mapeo.normalizar(taller)] = existente[0]
                continue
            if APLICAR:
                nuevo = o.crear('res.partner', {
                    'name': taller,
                    'company_type': 'company',
                    'supplier_rank': 1,
                    'comment': 'Taller importado de Fracttal.',
                })
                self.partners[mapeo.normalizar(taller)] = nuevo
            log(f'CREAR proveedor (taller): {taller}')
            self.stats['talleres_creados'] += 1

        # --- Un equipo de mantenimiento por compañía (campo requerido en la OT) ---
        for nombre_cia, id_cia in self.companias.items():
            if id_cia in self.equipos_mant:
                continue
            if APLICAR:
                nuevo = o.crear('maintenance.team',
                                {'name': 'Mantenimiento', 'company_id': id_cia})
                self.equipos_mant[id_cia] = nuevo
            log(f'CREAR equipo de mantenimiento para: {nombre_cia}')
            self.stats['equipos_mant_creados'] += 1

    # ------------------------------------------------------------------
    # 2. Activos → maintenance.equipment (+ historial de ubicación)
    # ------------------------------------------------------------------
    def _ubicacion_de(self, ruta):
        """Resuelve (lugar_id, area_id) desde la ruta jerárquica de Fracttal."""
        nodo = ultimo_nodo(ruta)
        norm = mapeo.normalizar(nodo)
        if not nodo or norm in {mapeo.normalizar(x) for x in mapeo.UBICACION_IGNORAR}:
            return None, None
        # ¿área interna de planta?
        for area_fracttal, area_odoo in mapeo.AREA_PLANTA.items():
            if mapeo.normalizar(area_fracttal) == norm:
                lugar = mapeo.LUGAR_EXISTENTE.get(mapeo.LUGAR_DE_PLANTA,
                                                  mapeo.LUGAR_DE_PLANTA)
                return (self.lugares.get(mapeo.normalizar(lugar)),
                        self.areas.get(mapeo.normalizar(area_odoo)))
        # ¿taller? no es ubicación de maquinaria
        if norm in {mapeo.normalizar(t) for t in mapeo.TALLERES}:
            return None, None
        # finca / planta
        destino = mapeo.LUGAR_EXISTENTE.get(nodo, nodo)
        return self.lugares.get(mapeo.normalizar(destino)), None

    def paso_activos(self):
        titulo('2. ACTIVOS → maintenance.equipment')
        o = self.o
        filas = leer_export('ACTIVOS.xlsx')
        log(f'Activos en el export: {len(filas)}')

        # Ubicaciones conocidas, para distinguir raíz de componente
        ubis = {mapeo.normalizar(u['Nombre'])
                for u in leer_export('UBICACIONES.xlsx') if u.get('Nombre')}

        # Orden: primero los que cuelgan de una ubicación, luego los componentes,
        # para que el padre exista cuando se enlaza parent_equipment_id.
        def es_componente(f):
            return mapeo.normalizar(ultimo_nodo(f['Ubicado en ó es Parte de'])) not in ubis

        filas.sort(key=es_componente)

        historial = []
        for i, f in enumerate(filas, 1):
            nombre = (f.get('Nombre') or '').strip()
            if not nombre:
                continue
            norm = mapeo.normalizar(nombre)
            codigo = (f.get('Código') or '').strip() or nombre
            nombre_cia = mapeo.compania_de_activo(nombre)
            id_cia = self.cia(nombre_cia)
            ruta = f.get('Ubicado en ó es Parte de')
            componente = es_componente(f)

            id_lugar, id_area = (None, None)
            id_padre = None
            if componente:
                padre_norm = mapeo.normalizar(ultimo_nodo(ruta))
                id_padre = self.equipos.get(padre_norm)
                # el componente hereda ubicación y compañía del padre
                if id_padre and padre_norm in self.equipo_cia:
                    id_cia = self.equipo_cia[padre_norm]
            else:
                id_lugar, id_area = self._ubicacion_de(ruta)

            if norm in self.equipos:
                self.stats['activos_existentes'] += 1
                continue

            vals = {
                'name': nombre,
                'external_ref': codigo,
                'company_id': id_cia,
                'category_id': self.categorias.get(mapeo.categoria_de_activo(nombre)),
                'equipment_assign_to': 'other',
                'note': f.get('Notas') or False,
            }
            if f.get('Modelo'):
                vals['model'] = str(f['Modelo']).strip()
            if f.get('Número de Serial'):
                vals['serial_no'] = str(f['Número de Serial']).strip()
            if f.get('Fabricante'):
                vals['partner_ref'] = str(f['Fabricante']).strip()
            fecha_compra = a_fecha(f.get('Fecha de Compra'))
            if fecha_compra:
                vals['effective_date'] = fecha_compra
            if id_lugar:
                vals['lugar_id'] = id_lugar
            if id_area:
                vals['origen_muestra_id'] = id_area
            if id_padre:
                vals['parent_equipment_id'] = id_padre

            if APLICAR:
                nuevo = o.crear('maintenance.equipment', vals)
                self.equipos[norm] = nuevo
                if id_cia:
                    self.equipo_cia[norm] = id_cia
                if id_lugar or id_area or id_padre:
                    historial.append({
                        'equipment_id': nuevo,
                        'lugar_id': id_lugar or False,
                        'origen_muestra_id': id_area or False,
                        'parent_equipment_id': id_padre or False,
                        'date_from': fecha_compra or '2024-01-01',
                        'origin': ORIGEN,
                        'notes': f'Ubicación inicial importada de Fracttal: '
                                 f'{(ruta or "").strip()}',
                    })
            else:
                self.equipos[norm] = -1          # marcador para el simulacro
                if id_cia:
                    self.equipo_cia[norm] = id_cia
            self.stats['componentes' if componente else 'activos_raiz'] += 1
            self.stats['activos_creados'] += 1
            barra(i, len(filas), 'activos')

        # Historial de ubicación en lote
        if APLICAR and historial:
            for j in range(0, len(historial), 200):
                o.crear_lote('maintenance.equipment.location.history',
                             historial[j:j + 200])
            self.stats['historial_ubicacion'] = len(historial)

        log(f'Creados: {self.stats["activos_creados"]} '
            f'(raíz {self.stats["activos_raiz"]}, componentes {self.stats["componentes"]}) | '
            f'ya existían: {self.stats["activos_existentes"]}')

    # ------------------------------------------------------------------
    # 3. Horómetros
    # ------------------------------------------------------------------
    def paso_horometros(self):
        titulo('3. HORÓMETROS → maintenance.horometro.reading')
        o = self.o
        carpeta = os.path.join(comun.RUTA_EXPORT, 'Horómetros')
        archivos = sorted(f for f in os.listdir(carpeta) if f.endswith('.xlsx'))
        log(f'Archivos de horómetro: {len(archivos)}')

        # Intervalo preventivo y lectura actual desde MEDIDORES_HOY
        medidores = {}
        for m in leer_export('MEDIDORES_HOY.xlsx'):
            equipo = (m.get('Ubicado en ó es Parte de') or '').strip()
            if equipo:
                medidores[mapeo.normalizar(equipo)] = m

        sin_equipo, lecturas = [], []
        for archivo in archivos:
            nombre_equipo = os.path.splitext(archivo)[0].strip()
            norm = mapeo.normalizar(mapeo.ALIAS_ACTIVO.get(nombre_equipo, nombre_equipo))
            id_equipo = self.equipos.get(norm)
            if not id_equipo:
                sin_equipo.append(nombre_equipo)
                continue
            filas = comun.leer_excel(os.path.join(carpeta, archivo))
            # De más antigua a más reciente: el horómetro es acumulativo.
            filas.sort(key=lambda r: str(r.get('Fecha de Lectura') or ''))
            for f in filas:
                fecha = a_fecha(f.get('Fecha de Lectura') or f.get('Fecha de Ingreso'))
                valor = lectura_horometro(f.get('Lectura'))
                if not fecha or valor <= 0:
                    continue
                lecturas.append({
                    'equipment_id': id_equipo,
                    'date': fecha,
                    'value': valor,
                    'notes': f'Importado de Fracttal. Fuente: '
                             f'{f.get("Fuente") or "n/d"}.',
                })
            self.stats['equipos_con_horometro'] += 1

        log(f'Lecturas a cargar: {len(lecturas)}')
        if sin_equipo:
            log(f'AVISO: {len(sin_equipo)} archivos sin equipo en Odoo: '
                f'{", ".join(sin_equipo[:5])}')

        if APLICAR and lecturas:
            # Se desactiva el disparo automático de OT preventivas: son lecturas
            # históricas, no deben generar solicitudes nuevas.
            ctx = dict(comun.CTX, importando_historico=True)
            creadas = 0
            for j in range(0, len(lecturas), 200):
                o.x('maintenance.horometro.reading', 'create',
                    lecturas[j:j + 200], context=ctx)
                creadas += len(lecturas[j:j + 200])
                barra(creadas, len(lecturas), 'lecturas')
        self.stats['lecturas_horometro'] = len(lecturas)

        # Intervalo de mantenimiento por equipo
        for norm, m in medidores.items():
            id_equipo = self.equipos.get(norm)
            if not id_equipo or id_equipo == -1:
                continue
            valor = lectura_horometro(m.get('Última lectura'))
            if APLICAR and valor:
                o.escribir('maintenance.equipment', [id_equipo],
                           {'horometro_last_maintenance': valor})
            self.stats['medidores_actualizados'] += 1

    # ------------------------------------------------------------------
    # 4. Órdenes de trabajo + costos históricos
    # ------------------------------------------------------------------
    def _equipo_infraestructura(self, finca):
        """Equipo genérico que recibe el mantenimiento de una finca completa.

        Se crea bajo demanda y solo si la finca existe como `secadora.lugar`.
        """
        nombre = mapeo.equipo_generico_de(finca)
        norm = mapeo.normalizar(nombre)
        if norm in self.equipos:
            return self.equipos[norm]
        destino = mapeo.LUGAR_EXISTENTE.get(finca, finca)
        id_lugar = self.lugares.get(mapeo.normalizar(destino))
        # En simulacro los lugares del paso 1 aún no existen; el equipo se
        # crea igual (sin lugar) para no perder la OT ni su costo.
        id_cia = self.cia(mapeo.COMPANIA_POR_DEFECTO)
        vals = {
            'name': nombre,
            'external_ref': f'INFRA-{mapeo.normalizar(finca)}',
            'company_id': id_cia,
            'category_id': self.categorias.get('Servicios generales'),
            'equipment_assign_to': 'other',
            'lugar_id': id_lugar or False,
            'note': '<p>Equipo genérico creado en la migración de Fracttal '
                    'para agrupar las órdenes de trabajo registradas contra la '
                    'ubicación completa y no contra una máquina.</p>',
        }
        if APLICAR:
            nuevo = self.o.crear('maintenance.equipment', vals)
        else:
            nuevo = -1
        self.equipos[norm] = nuevo
        self.equipo_cia[norm] = id_cia
        self.stats['equipos_infraestructura'] += 1
        log(f'CREAR equipo de infraestructura: {nombre}')
        return nuevo

    def paso_ordenes(self):
        titulo('4. ÓRDENES DE TRABAJO → maintenance.request + costos históricos')
        o = self.o
        filas = leer_export('OT-RECURSOS.xlsx')
        log(f'Líneas de recurso: {len(filas)}')

        # Agrupar por OT (verificado: 1 OT = 1 activo = 1 tarea)
        por_ot = defaultdict(list)
        for f in filas:
            if f.get('Id OT'):
                por_ot[str(f['Id OT']).strip()].append(f)
        log(f'Órdenes distintas: {len(por_ot)}')

        # OTs ya migradas (idempotencia)
        ya = {r['external_ref']
              for r in o.buscar_leer('maintenance.request',
                                     [('external_ref', '!=', False)], ['external_ref'])}
        if ya:
            log(f'Ya migradas previamente: {len(ya)} (se omiten)')

        sin_activo = set()
        costos = []
        pendientes = sorted(por_ot.items())
        for i, (id_ot, lineas) in enumerate(pendientes, 1):
            if id_ot in ya:
                self.stats['ot_existentes'] += 1
                continue
            cab = lineas[0]
            nombre_activo = (cab.get('Activo') or '').strip()
            nombre_activo = mapeo.ALIAS_ACTIVO.get(nombre_activo, nombre_activo)
            id_equipo = self.equipos.get(mapeo.normalizar(nombre_activo))
            # OT registrada contra la finca entera, no contra una máquina:
            # se imputa al equipo genérico de infraestructura de esa finca.
            if not id_equipo and mapeo.es_ot_de_ubicacion(nombre_activo):
                finca = mapeo.finca_de_ot_ubicacion(nombre_activo)
                id_equipo = self._equipo_infraestructura(finca)
                if id_equipo:
                    self.stats['ot_de_ubicacion'] += 1
            if not id_equipo:
                sin_activo.add(nombre_activo or '(vacío)')
                self.stats['ot_sin_activo'] += 1
                continue

            id_cia = (self.equipo_cia.get(mapeo.normalizar(nombre_activo))
                      or self.cia(mapeo.COMPANIA_POR_DEFECTO))
            estado = (cab.get('Estado') or '').strip()
            etapa_nombre, hecha = mapeo.ESTADO_ETAPA.get(estado, ('In Progress', False))
            tarea = (cab.get('Tarea') or 'Mantenimiento').strip()
            fecha_ot = a_fecha(cab.get('Fecha de creación de la OT'))

            # Detalle de recursos en la descripción, para no perder nada.
            detalle = []
            for ln in lineas:
                detalle.append(
                    f'<li>{(ln.get("Descripción del Recurso") or "").strip()} — '
                    f'{a_float(ln.get("Cantidad Real Usada"))} '
                    f'{(ln.get("Unidad") or "").strip()} × '
                    f'${a_float(ln.get("coste unitario")):,.0f} = '
                    f'${a_float(ln.get("coste Total")):,.0f} '
                    f'<i>({(ln.get("Fuente del Recurso") or "n/d").strip()})</i></li>')
            total = sum(a_float(ln.get('coste Total')) for ln in lineas)
            descripcion = (
                f'<p><b>Importado de Fracttal</b> — orden {id_ot}, '
                f'estado original: {estado}.</p>'
                f'<p><b>Tarea:</b> {tarea}<br/>'
                f'<b>Ubicación:</b> {(cab.get("Ubicado en ó es Parte de") or "").strip()}</p>'
                f'<p><b>Recursos utilizados ({len(lineas)}):</b></p>'
                f'<ul>{"".join(detalle)}</ul>'
                f'<p><b>Costo total:</b> ${total:,.0f}</p>')

            vals = {
                'name': f'[{id_ot}] {tarea}',
                'external_ref': id_ot,
                'task_name': tarea,
                'equipment_id': id_equipo,
                'company_id': id_cia,
                'maintenance_team_id': self.equipos_mant.get(id_cia),
                'stage_id': self.etapas.get(etapa_nombre),
                'maintenance_type': mapeo.TIPO_MANTENIMIENTO.get(
                    (cab.get('Tipo de Tarea') or '').strip(), 'corrective'),
                'request_date': fecha_ot,
                'description': descripcion,
                'kanban_state': 'done' if hecha else 'normal',
                'done': hecha,
            }
            programada = a_datetime(cab.get('Fecha Programada'))
            if programada:
                vals['schedule_date'] = programada
            if hecha:
                # Cierre = última utilización de recurso, o la creación de la OT.
                fechas = [a_fecha(ln.get('Fecha Utilización del Recurso'))
                          for ln in lineas]
                fechas = [f for f in fechas if f]
                vals['close_date'] = max(fechas) if fechas else fecha_ot

            if APLICAR:
                id_req = o.crear('maintenance.request', vals)
            else:
                id_req = -1
            self.stats['ot_creadas'] += 1

            # Costos históricos (una línea por recurso)
            for ln in lineas:
                importe = a_float(ln.get('coste Total'))
                fuente = (ln.get('Fuente del Recurso') or '').strip()
                costos.append({
                    'equipment_id': id_equipo,
                    'request_id': id_req if APLICAR else False,
                    'date': (a_fecha(ln.get('Fecha Utilización del Recurso'))
                             or fecha_ot),
                    'name': (ln.get('Descripción del Recurso') or 'Recurso').strip(),
                    'code': (ln.get('Código del recurso') or '').strip() or False,
                    'resource_type': mapeo.TIPO_RECURSO.get(
                        (ln.get('Tipo de Recurso') or '').strip(), 'other'),
                    'quantity': a_float(ln.get('Cantidad Real Usada')),
                    'uom_name': (ln.get('Unidad') or '').strip() or False,
                    'unit_cost': a_float(ln.get('coste unitario')),
                    'amount': importe,
                    'source_name': fuente or False,
                    'partner_id': self.partners.get(mapeo.normalizar(fuente), False),
                    'company_id': id_cia,
                    'origin': ORIGEN,
                    'external_ref': id_ot,
                })
                self.stats['costo_total'] += importe
            barra(i, len(pendientes), 'órdenes')

        if APLICAR and costos:
            creados = 0
            for j in range(0, len(costos), 200):
                o.crear_lote('maintenance.historic.cost', costos[j:j + 200])
                creados += len(costos[j:j + 200])
                barra(creados, len(costos), 'costos')
        self.stats['costos_creados'] = len(costos)

        if sin_activo:
            log(f'AVISO: {len(sin_activo)} activos referidos en OT no existen '
                f'como equipo (OT omitidas): {", ".join(sorted(sin_activo)[:6])}')

    # ------------------------------------------------------------------
    def resumen(self):
        titulo('RESUMEN')
        etiquetas = [
            ('lugares_creados', 'Lugares creados'),
            ('areas_creadas', 'Áreas de proceso creadas'),
            ('talleres_creados', 'Talleres creados como proveedor'),
            ('equipos_mant_creados', 'Equipos de mantenimiento creados'),
            ('activos_creados', 'Equipos creados'),
            ('activos_raiz', '  · de los cuales raíz'),
            ('componentes', '  · de los cuales componentes'),
            ('activos_existentes', 'Equipos que ya existían (omitidos)'),
            ('equipos_infraestructura', 'Equipos de infraestructura creados'),
            ('ot_de_ubicacion', 'Órdenes imputadas a infraestructura'),
            ('historial_ubicacion', 'Registros de historial de ubicación'),
            ('equipos_con_horometro', 'Equipos con horómetro'),
            ('lecturas_horometro', 'Lecturas de horómetro'),
            ('ot_creadas', 'Órdenes de trabajo creadas'),
            ('ot_existentes', 'Órdenes ya migradas (omitidas)'),
            ('ot_sin_activo', 'Órdenes omitidas por activo inexistente'),
            ('costos_creados', 'Líneas de costo histórico'),
        ]
        for clave, texto in etiquetas:
            if self.stats.get(clave):
                print(f'   {texto:45} {self.stats[clave]:>10,}')
        if self.stats.get('costo_total'):
            print(f'   {"Costo histórico total":45} ${self.stats["costo_total"]:>9,.0f}')
        if not APLICAR:
            print('\n   *** SIMULACRO: no se escribió nada. '
                  'Usar --aplicar para cargar. ***')


def main():
    print(f'Base de datos: {DB} | Modo: '
          f'{"APLICAR (escribe)" if APLICAR else "SIMULACRO (no escribe)"}')
    print(f'Etapas: {", ".join(PASOS)}')
    o = Odoo(db=DB)
    print(f'Conectado (uid={o.uid})')

    m = Migracion(o)
    m.preparar()
    if 'catalogos' in PASOS:
        m.paso_catalogos()
    if 'activos' in PASOS:
        m.paso_activos()
    if 'horometros' in PASOS:
        m.paso_horometros()
    if 'ordenes' in PASOS:
        m.paso_ordenes()
    m.resumen()


if __name__ == '__main__':
    main()
