# -*- coding: utf-8 -*-
"""Publica los pesajes de entrada y los horómetros en hojas de Google Sheets.

La hoja se reescribe completa en cada corrida: es la forma más simple de que
una corrección en Odoo (humedad, cancelación, cambio de lote) se vea en la
hoja sin llevar registro de qué cambió.
"""
import logging

import pytz

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

SHEETS_SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SHEETS_TIMEOUT = 60
TZ_COLOMBIA = pytz.timezone('America/Bogota')

HOJA_PESAJES = 'Pesajes entrada'
HOJA_MIXTAS = 'Cargas mixtas'
HOJA_INFO = 'Actualización'

COLUMNAS_PESAJES = [
    'Número', 'Fecha', 'Hora entrada', 'Hora salida', 'Estado',
    'Tipo de operación', 'Origen', 'Tipo origen', 'Municipio', 'Lote',
    'Lote (texto)', 'Carga mixta', 'Destino', 'Producto', 'Variedad',
    'Semilla', 'Tercero', 'NIT', 'Empresa del arroz', 'Placa', 'Conductor',
    'Cédula', 'Transportadora', 'Peso lleno (kg)', 'Peso vacío (kg)',
    'Peso neto (kg)', 'Bultos', 'Humedad (%)', 'Grano partido (%)',
    'Impurezas (%)', 'Precio', 'Plazo', 'Observaciones',
]
COLUMNAS_MIXTAS = [
    'Número', 'Fecha', 'Finca', 'Lote', 'Bultos', 'Peso (kg)', 'Porcentaje (%)',
]

HOJA_HOROMETROS = 'Lecturas'
HOJA_EQUIPOS = 'Estado por equipo'
COLUMNAS_HOROMETROS = [
    'Fecha', 'Equipo', 'Categoría', 'Serie', 'Ubicación', 'Lectura (horas)',
    'Horas desde la anterior', 'Días desde la anterior', 'Registrado por',
    'Notas', 'OT generada',
]
HOJA_BULTOS = 'Registros'
HOJA_BULTOS_SALDO = 'Saldo por bodega'
HOJA_BULTOS_MES = 'Empacado por mes'
COLUMNAS_BULTOS = [
    'Fecha empaque', 'Descripción', 'Orden de servicio', 'Dueño / Agricultor',
    'Empresa', 'Producto', 'Variedad', 'Código', 'Semilla', 'Bodega',
    'Tipo de empaque', 'Provee el empaque', 'Bultos', 'Peso promedio (kg)',
    'Peso total (kg)', 'Despachados', 'Pendientes', 'Estado', 'Origen',
    'Registrado por', 'Observaciones',
]
_TOTALES = ['Bultos empacados', 'Despachados', 'Pendientes (saldo)', 'Peso total (kg)']
COLUMNAS_BULTOS_SALDO = [
    'Dueño / Agricultor', 'Producto', 'Variedad', 'Código', 'Semilla', 'Bodega',
] + _TOTALES
COLUMNAS_BULTOS_MES = ['Mes', 'Dueño / Agricultor', 'Producto'] + _TOTALES

COLUMNAS_EQUIPOS = [
    'Equipo', 'Categoría', 'Serie', 'Ubicación', 'Horómetro actual',
    'Fecha última lectura', 'Nro. lecturas', 'Intervalo mant. (horas)',
    'Lectura último mant.', 'Horas para el próximo mant.',
]


class GoogleSheetsSync(models.AbstractModel):
    _name = 'secadora.google.sheets.sync'
    _description = 'Publicación de datos en Google Sheets'

    # ------------------------------------------------------------------
    # Cliente
    # ------------------------------------------------------------------
    @api.model
    def _cliente_sheets(self):
        """Cliente de la API de Sheets con la cuenta de servicio de Drive.
        Devuelve None (y deja un warning) si falta la clave o la librería."""
        path = self.env['ir.config_parameter'].sudo().get_param(
            'custom_webviewlink.drive_sa_json_path')
        if not path:
            _logger.warning('Sheets: falta el parámetro '
                            'custom_webviewlink.drive_sa_json_path.')
            return None
        try:
            import httplib2
            from google.oauth2 import service_account
            from google_auth_httplib2 import AuthorizedHttp
            from googleapiclient.discovery import build
        except ImportError:
            _logger.warning('Sheets: faltan las librerías de Google en el '
                            'entorno de Odoo.')
            return None
        try:
            creds = service_account.Credentials.from_service_account_file(
                path, scopes=SHEETS_SCOPES)
            http = AuthorizedHttp(creds, http=httplib2.Http(timeout=SHEETS_TIMEOUT))
            return build('sheets', 'v4', http=http, cache_discovery=False)
        except Exception as e:
            _logger.warning('Sheets: no se pudo inicializar el cliente: %s', e)
            return None

    # ------------------------------------------------------------------
    # Datos
    # ------------------------------------------------------------------
    @staticmethod
    def _hora_local(dt):
        """Datetime de Odoo (UTC, sin tz) como texto en hora de Colombia."""
        if not dt:
            return ''
        return pytz.utc.localize(dt).astimezone(TZ_COLOMBIA).strftime('%Y-%m-%d %H:%M')

    @staticmethod
    def _si_no(valor):
        return 'Sí' if valor else 'No'

    @api.model
    def _filas_pesajes(self):
        """Filas de la hoja principal: un pesaje de entrada por fila."""
        Pesaje = self.env['secadora.pesaje'].sudo()
        estados = dict(Pesaje._fields['state']._description_selection(self.env))
        filas = [COLUMNAS_PESAJES]
        pesajes = Pesaje.search([('direccion', '=', 'entrada')], order='fecha, name')
        for p in pesajes:
            filas.append([
                p.name,
                str(p.fecha) if p.fecha else '',
                self._hora_local(p.hora_entrada),
                self._hora_local(p.hora_salida),
                estados.get(p.state, p.state),
                p.tipo_operacion_id.name or '',
                p.origen_id.name or '',
                p.origen_id.tipo or '',
                p.origen_id.municipio or '',
                p.lote_id.name or '',
                p.lote_finca or '',
                self._si_no(p.carga_mixta),
                p.destino_id.name or '',
                p.producto_id.display_name or '',
                p.variedad_id.name or '',
                self._si_no(p.es_semilla),
                p.tercero_id.name or '',
                p.nit_tercero or '',
                p.empresa_arroz_id.name or '',
                p.vehiculo_id.placa or p.placa_texto or '',
                p.conductor_id.name or '',
                p.conductor_id.cedula or '',
                p.transportadora_id.name or '',
                p.peso_bruto,
                p.peso_tara,
                p.peso_neto,
                p.bultos,
                p.humedad,
                p.grano_partido,
                p.impurezas,
                p.precio,
                p.plazo or '',
                p.observaciones or '',
            ])
        return filas

    @api.model
    def _filas_mixtas(self):
        """Detalle finca/lote de las cargas mixtas de entrada."""
        lineas = self.env['secadora.pesaje.distribucion'].sudo().search(
            [('pesaje_id.direccion', '=', 'entrada')],
            order='pesaje_id, id')
        filas = [COLUMNAS_MIXTAS]
        for d in lineas:
            filas.append([
                d.pesaje_id.name,
                str(d.pesaje_id.fecha) if d.pesaje_id.fecha else '',
                d.finca_id.name or '',
                d.lote_id.name or '',
                d.bultos,
                d.peso_kg,
                d.porcentaje,
            ])
        return filas

    # ------------------------------------------------------------------
    # Escritura
    # ------------------------------------------------------------------
    @api.model
    def _asegurar_hojas(self, svc, spreadsheet_id, nombres):
        """Crea las pestañas que falten para que el update no falle."""
        meta = svc.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        existentes = {s['properties']['title'] for s in meta.get('sheets', [])}
        faltan = [n for n in nombres if n not in existentes]
        if faltan:
            svc.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={'requests': [
                    {'addSheet': {'properties': {'title': n}}} for n in faltan
                ]},
            ).execute()

    @api.model
    def _escribir_hoja(self, svc, spreadsheet_id, nombre, filas):
        # Borrar antes de escribir: si hoy hay menos filas que ayer, las
        # sobrantes del final quedarían como pesajes fantasma.
        svc.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id, range=nombre, body={}).execute()
        svc.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"'{nombre}'!A1",
            valueInputOption='RAW',
            body={'values': filas},
        ).execute()

    @api.model
    def _publicar(self, parametro, hojas, etiqueta):
        """Reescribe en la hoja indicada por `parametro` cada pestaña de
        `hojas` ({nombre: filas}) más la de Actualización. Devuelve el número
        de filas de la primera pestaña, o None si no se pudo (queda en el
        log; nunca lanza, porque corre desde un cron)."""
        spreadsheet_id = self.env['ir.config_parameter'].sudo().get_param(
            f'secadora_google_sheets.{parametro}')
        if not spreadsheet_id:
            _logger.info('Sheets: sin secadora_google_sheets.%s; no se '
                         'publica nada.', parametro)
            return None
        svc = self._cliente_sheets()
        if svc is None:
            return None

        info = [['Última actualización (Colombia)',
                 self._hora_local(fields.Datetime.now())]]
        info += [[nombre, len(filas) - 1] for nombre, filas in hojas.items()]
        info.append(['Fuente', f'Odoo, base {self.env.cr.dbname}. La hoja se '
                     'reescribe cada hora; lo que se edite aquí se pierde.'])
        try:
            self._asegurar_hojas(svc, spreadsheet_id, list(hojas) + [HOJA_INFO])
            for nombre, filas in hojas.items():
                self._escribir_hoja(svc, spreadsheet_id, nombre, filas)
            self._escribir_hoja(svc, spreadsheet_id, HOJA_INFO, info)
        except Exception as e:
            _logger.warning('Sheets: no se pudo publicar %s: %s', etiqueta, e)
            return None
        n = len(next(iter(hojas.values()))) - 1
        _logger.info('Sheets: publicadas %d filas de %s.', n, etiqueta)
        return n

    @api.model
    def publicar_pesajes(self):
        return self._publicar('spreadsheet_id', {
            HOJA_PESAJES: self._filas_pesajes(),
            HOJA_MIXTAS: self._filas_mixtas(),
        }, 'pesajes de entrada')

    @api.model
    def _cron_publicar_pesajes(self):
        self.publicar_pesajes()

    # ------------------------------------------------------------------
    # Horómetros
    # ------------------------------------------------------------------
    @api.model
    def _filas_horometros(self):
        """Una lectura por fila, de la más antigua a la más reciente, con la
        diferencia frente a la lectura anterior del mismo equipo."""
        lecturas = self.env['maintenance.horometro.reading'].sudo().search(
            [], order='equipment_id, date, id')
        filas = [COLUMNAS_HOROMETROS]
        anterior = {}
        for l in lecturas:
            eq = l.equipment_id
            prev = anterior.get(eq.id)
            horas = round(l.value - prev.value, 2) if prev else ''
            dias = (l.date - prev.date).days if prev else ''
            filas.append([
                str(l.date) if l.date else '',
                eq.complete_name or eq.name or '',
                eq.category_id.name or '',
                eq.serial_no or '',
                eq.lugar_id.name if 'lugar_id' in eq._fields else '',
                l.value,
                horas,
                dias,
                l.user_id.name or '',
                l.notes or '',
                l.triggered_request_id.name or '',
            ])
            anterior[eq.id] = l
        return filas

    @api.model
    def _filas_equipos(self):
        """Resumen por equipo con lectura actual y horas para el próximo
        mantenimiento (negativo = vencido)."""
        equipos = self.env['maintenance.equipment'].sudo().search(
            [('horometro_reading_ids', '!=', False)], order='name')
        filas = [COLUMNAS_EQUIPOS]
        for eq in equipos:
            ultima = eq.horometro_reading_ids.sorted(
                key=lambda r: (r.date, r.id), reverse=True)[:1]
            faltan = ''
            if eq.horometro_interval:
                faltan = round(eq.horometro_last_maintenance
                               + eq.horometro_interval - eq.horometro_current, 2)
            filas.append([
                eq.complete_name or eq.name or '',
                eq.category_id.name or '',
                eq.serial_no or '',
                eq.lugar_id.name if 'lugar_id' in eq._fields else '',
                eq.horometro_current,
                str(ultima.date) if ultima else '',
                eq.horometro_reading_count,
                eq.horometro_interval or '',
                eq.horometro_last_maintenance or '',
                faltan,
            ])
        return filas

    @api.model
    def publicar_horometros(self):
        return self._publicar('horometros_spreadsheet_id', {
            HOJA_HOROMETROS: self._filas_horometros(),
            HOJA_EQUIPOS: self._filas_equipos(),
        }, 'lecturas de horómetro')

    @api.model
    def _cron_publicar_horometros(self):
        self.publicar_horometros()

    # ------------------------------------------------------------------
    # Bultos empacados
    # ------------------------------------------------------------------
    @api.model
    def _filas_bultos(self):
        """Un registro de empaque por fila."""
        Registro = self.env['secadora.registro.bultos'].sudo()
        estados = dict(Registro._fields['state']._description_selection(self.env))
        origenes = dict(Registro._fields['origen']._description_selection(self.env))
        provee = dict(Registro._fields['proveedor_empaque']._description_selection(self.env))
        filas = [COLUMNAS_BULTOS]
        for r in Registro.search([], order='fecha, id'):
            filas.append([
                str(r.fecha) if r.fecha else '',
                r.name or '',
                r.orden_id.name or '',
                r.cliente_id.name or '',
                r.company_id.name or '',
                r.producto_id.display_name or '',
                r.variedad_id.name or '',
                r.codigo_variedad or '',
                self._si_no(r.es_semilla),
                r.bodega_id.name or '',
                r.producto_empaque_id.display_name or '',
                provee.get(r.proveedor_empaque, r.proveedor_empaque or ''),
                r.cantidad,
                r.peso_promedio,
                r.peso_total,
                r.cantidad_despachada,
                r.cantidad_pendiente,
                estados.get(r.state, r.state),
                origenes.get(r.origen, r.origen or ''),
                r.usuario_id.name or '',
                r.observaciones or '',
            ])
        return filas

    @api.model
    def _resumen_bultos(self, claves, columnas):
        """Suma empacados/despachados/pendientes/peso agrupando por las
        funciones de `claves` (una por columna de agrupación)."""
        acumulado = {}
        for r in self.env['secadora.registro.bultos'].sudo().search([]):
            k = tuple(f(r) for f in claves)
            a = acumulado.setdefault(k, [0, 0, 0, 0.0])
            a[0] += r.cantidad
            a[1] += r.cantidad_despachada
            a[2] += r.cantidad_pendiente
            a[3] += r.peso_total
        filas = [columnas]
        for k in sorted(acumulado):
            a = acumulado[k]
            filas.append(list(k) + [a[0], a[1], a[2], round(a[3], 2)])
        return filas

    @api.model
    def _filas_bultos_saldo(self):
        """Saldo por dueño, producto, variedad, semilla y bodega."""
        return self._resumen_bultos([
            lambda r: r.cliente_id.name or '',
            lambda r: r.producto_id.display_name or '',
            lambda r: r.variedad_id.name or '',
            lambda r: r.codigo_variedad or '',
            lambda r: self._si_no(r.es_semilla),
            lambda r: r.bodega_id.name or '(sin bodega)',
        ], COLUMNAS_BULTOS_SALDO)

    @api.model
    def _filas_bultos_mes(self):
        """Empacado por mes y dueño."""
        return self._resumen_bultos([
            lambda r: r.fecha.strftime('%Y-%m') if r.fecha else '',
            lambda r: r.cliente_id.name or '',
            lambda r: r.producto_id.display_name or '',
        ], COLUMNAS_BULTOS_MES)

    @api.model
    def publicar_bultos(self):
        return self._publicar('bultos_spreadsheet_id', {
            HOJA_BULTOS_SALDO: self._filas_bultos_saldo(),
            HOJA_BULTOS_MES: self._filas_bultos_mes(),
            HOJA_BULTOS: self._filas_bultos(),
        }, 'registros de bultos')

    @api.model
    def _cron_publicar_bultos(self):
        self.publicar_bultos()
