#!/usr/bin/env python3
"""Sube los respaldos del dia a Google Drive y borra los viejos de alla.

Los respaldos locales (/var/backups/odoo) viven en el mismo servidor que
protegen: si el VPS se pierde, se pierden con el. Esto los saca afuera.

Usa la cuenta de servicio que ya existe para leer facturas de Drive, pero
pidiendo permiso de escritura sobre la carpeta compartida de respaldos.
"""
import os
import sys
import datetime
import logging

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SA_JSON = '/opt/odoo19/config/drive-sa.json'
CARPETA_DRIVE = '1TNh0WtDgt9-pjmhZBdiELHNC7a6LjBLB'
DIR_RESPALDOS = '/var/backups/odoo'
DIAS_A_CONSERVAR = 14
SCOPES = ['https://www.googleapis.com/auth/drive']

logging.basicConfig(
    format='%(asctime)s %(levelname)s %(message)s',
    level=logging.INFO,
)
log = logging.getLogger('respaldo-drive')


def servicio():
    cred = service_account.Credentials.from_service_account_file(
        SA_JSON, scopes=SCOPES)
    return build('drive', 'v3', credentials=cred, cache_discovery=False)


def ya_esta(drive, nombre):
    """Evita subir dos veces el mismo archivo si el cron se repite."""
    q = (f"name = '{nombre}' and '{CARPETA_DRIVE}' in parents "
         f"and trashed = false")
    r = drive.files().list(q=q, fields='files(id)', pageSize=1).execute()
    return bool(r.get('files'))


def subir(drive, ruta):
    nombre = os.path.basename(ruta)
    if ya_esta(drive, nombre):
        log.info('%s ya estaba en Drive, no se vuelve a subir', nombre)
        return
    media = MediaFileUpload(ruta, resumable=True)
    drive.files().create(
        body={'name': nombre, 'parents': [CARPETA_DRIVE]},
        media_body=media,
        fields='id',
        # La carpeta es del usuario, no de la cuenta de servicio.
        supportsAllDrives=True,
    ).execute()
    mb = os.path.getsize(ruta) / 1024 / 1024
    log.info('Subido %s (%.1f MB)', nombre, mb)


def limpiar_viejos(drive):
    """Borra de Drive lo que supere los dias a conservar.

    Sin esto la carpeta crece sin limite y termina llenando la cuota de
    Google del usuario.
    """
    corte = (datetime.datetime.now(datetime.timezone.utc)
             - datetime.timedelta(days=DIAS_A_CONSERVAR))
    q = f"'{CARPETA_DRIVE}' in parents and trashed = false"
    r = drive.files().list(
        q=q, fields='files(id,name,createdTime)', pageSize=1000).execute()
    for f in r.get('files', []):
        creado = datetime.datetime.fromisoformat(
            f['createdTime'].replace('Z', '+00:00'))
        if creado < corte:
            drive.files().delete(fileId=f['id'], supportsAllDrives=True).execute()
            log.info('Borrado de Drive por antiguedad: %s', f['name'])


def main():
    hoy = datetime.date.today().isoformat()
    archivos = [
        os.path.join(DIR_RESPALDOS, f'secadora_2_{hoy}.dump'),
        os.path.join(DIR_RESPALDOS, f'filestore_{hoy}.tar.gz'),
    ]
    presentes = [a for a in archivos if os.path.exists(a)]
    if not presentes:
        log.error('No hay respaldos de hoy (%s) en %s', hoy, DIR_RESPALDOS)
        return 1

    drive = servicio()
    for ruta in presentes:
        subir(drive, ruta)
    limpiar_viejos(drive)
    log.info('Listo: %d archivo(s) respaldados fuera del servidor', len(presentes))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        # El cron manda la salida al log; con el traceback se puede
        # diagnosticar sin tener que reproducir el fallo.
        log.exception('Fallo la subida del respaldo a Drive')
        sys.exit(1)
