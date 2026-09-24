# -*- coding: utf-8 -*-
"""Publica los pesajes de entrada en una hoja de Google Sheets.

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


class GoogleSheetsSync(models.AbstractModel):
    _name = 'secadora.google.sheets.sync'
    _description = 'Publicación de pesajes en Google Sheets'

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
    def publicar_pesajes(self):
        """Reescribe la hoja completa. Devuelve el número de pesajes
        publicados, o None si no se pudo (queda en el log)."""
        spreadsheet_id = self.env['ir.config_parameter'].sudo().get_param(
            'secadora_google_sheets.spreadsheet_id')
        if not spreadsheet_id:
            _logger.info('Sheets: sin secadora_google_sheets.spreadsheet_id; '
                         'no se publica nada.')
            return None
        svc = self._cliente_sheets()
        if svc is None:
            return None

        pesajes = self._filas_pesajes()
        mixtas = self._filas_mixtas()
        ahora = fields.Datetime.now()
        info = [
            ['Última actualización (Colombia)', self._hora_local(ahora)],
            ['Pesajes de entrada', len(pesajes) - 1],
            ['Líneas de cargas mixtas', len(mixtas) - 1],
            ['Fuente', f'Odoo, base {self.env.cr.dbname}. '
                       'La hoja se reescribe cada hora; lo que se edite aquí se pierde.'],
        ]
        try:
            self._asegurar_hojas(svc, spreadsheet_id,
                                 [HOJA_PESAJES, HOJA_MIXTAS, HOJA_INFO])
            self._escribir_hoja(svc, spreadsheet_id, HOJA_PESAJES, pesajes)
            self._escribir_hoja(svc, spreadsheet_id, HOJA_MIXTAS, mixtas)
            self._escribir_hoja(svc, spreadsheet_id, HOJA_INFO, info)
        except Exception as e:
            _logger.warning('Sheets: no se pudo publicar los pesajes: %s', e)
            return None
        _logger.info('Sheets: publicados %d pesajes de entrada.', len(pesajes) - 1)
        return len(pesajes) - 1

    @api.model
    def _cron_publicar_pesajes(self):
        self.publicar_pesajes()
