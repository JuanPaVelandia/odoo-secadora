# -*- coding: utf-8 -*-
"""Descarga de archivos de Google Drive mediante una cuenta de servicio.

Los documentos (facturas) están en Drive como PRIVADOS y se enlazan desde
account.move.x_webviewlink. Para que el servidor pueda leerlos sin exponer los
documentos públicamente, se usa una cuenta de servicio de Google a la que se le
comparten los archivos (permiso lector).

Requiere en el contenedor: google-api-python-client, google-auth.
La ruta de la clave JSON se guarda en el parámetro del sistema
'custom_webviewlink.drive_sa_json_path'.
"""

import io
import re
import logging

from odoo import models

_logger = logging.getLogger(__name__)

# Extrae el file id de las formas típicas de enlace de Drive:
#   https://drive.google.com/file/d/<ID>/view?usp=...
#   https://drive.google.com/open?id=<ID>
#   https://drive.google.com/uc?id=<ID>&export=download
_DRIVE_ID_RES = [
    re.compile(r'/file/d/([-\w]+)'),
    re.compile(r'[?&]id=([-\w]+)'),
]

DRIVE_SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

# Timeout (segundos) de las llamadas a Drive. Sin esto, una conexión colgada
# bloquearía el worker de Odoo indefinidamente al imprimir el reporte.
DRIVE_TIMEOUT = 30


class DriveDownloader(models.AbstractModel):
    _name = 'custom_webviewlink.drive_downloader'
    _description = 'Descargador de archivos de Google Drive (service account)'

    def _extraer_file_id(self, url):
        """Devuelve el file id de un enlace de Drive, o False si no se reconoce."""
        if not url:
            return False
        for rx in _DRIVE_ID_RES:
            m = rx.search(url)
            if m:
                return m.group(1)
        return False

    def _get_drive_service(self):
        """Construye el cliente de Drive con la cuenta de servicio.

        Devuelve None (sin lanzar) si faltan las librerías o la credencial, para
        que quien llame pueda degradar con gracia (mostrar el enlace en vez del
        PDF) en lugar de romper la impresión.
        """
        path = self.env['ir.config_parameter'].sudo().get_param(
            'custom_webviewlink.drive_sa_json_path'
        )
        if not path:
            _logger.warning(
                'Drive: no está configurado el parámetro '
                'custom_webviewlink.drive_sa_json_path (ruta de la clave JSON).'
            )
            return None
        try:
            import httplib2
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
            from google_auth_httplib2 import AuthorizedHttp
        except ImportError:
            _logger.warning(
                'Drive: faltan las librerías google-api-python-client / '
                'google-auth / google-auth-httplib2 en el entorno de Odoo.'
            )
            return None
        try:
            creds = service_account.Credentials.from_service_account_file(
                path, scopes=DRIVE_SCOPES
            )
            # http con timeout explícito: evita que una conexión colgada
            # bloquee el worker de Odoo (httplib2 hereda timeout None = infinito).
            authed_http = AuthorizedHttp(creds, http=httplib2.Http(timeout=DRIVE_TIMEOUT))
            return build('drive', 'v3', http=authed_http, cache_discovery=False)
        except Exception as e:
            _logger.warning('Drive: no se pudo inicializar el cliente: %s', e)
            return None

    def descargar_pdf(self, url, service=None):
        """Descarga el archivo de Drive apuntado por `url` y lo devuelve en
        bytes. Devuelve None si no se pudo (enlace no reconocido, sin permisos,
        sin credencial, error de red). Nunca lanza.

        `service`: cliente de Drive ya construido, para reutilizarlo entre
        varias descargas (evita leer la clave y crear el cliente por archivo).
        Si es None, se construye aquí."""
        try:
            file_id = self._extraer_file_id(url)
        except Exception:
            file_id = None
        if not file_id:
            return None
        if service is None:
            service = self._get_drive_service()
        if not service:
            return None
        try:
            from googleapiclient.http import MediaIoBaseDownload
            request = service.files().get_media(fileId=file_id)
            buf = io.BytesIO()
            downloader = MediaIoBaseDownload(buf, request)
            done = False
            while not done:
                _status, done = downloader.next_chunk()
            data = buf.getvalue()
            # Sanity check mínimo: un PDF empieza con %PDF. Solo se soportan
            # PDFs SUBIDOS a Drive; un Google Doc/Sheet NATIVO no se descarga
            # con get_media (da 403 y cae al except de abajo), no llega aquí.
            if not data.startswith(b'%PDF'):
                _logger.warning(
                    'Drive: el archivo %s se descargó pero no es un PDF '
                    '(primeros bytes: %r). Se omite.', file_id, data[:8]
                )
                return None
            return data
        except Exception as e:
            _logger.warning('Drive: falló la descarga de %s: %s', file_id, e)
            return None
