"""Lee adjuntos del filestore de Odoo para enviarlos por WhatsApp.

Odoo guarda los archivos en disco (`ir_attachment.store_fname` apunta a una
ruta relativa dentro del filestore) y solo los metadatos en la base.

Restringido a los modelos de negocio: la tabla `ir_attachment` también guarda
iconos, JavaScript y CSS de la propia interfaz de Odoo, que no tiene sentido
mandar por WhatsApp — y documentos de otros módulos que no queremos exponer.
"""

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

FILESTORE = os.environ.get("ODOO_FILESTORE", "/odoo-filestore")

# Modelos cuyos adjuntos puede enviar el bot. Todo lo demás queda fuera,
# incluidos los recursos internos de Odoo (ir.ui.view, payment.method...).
MODELOS_PERMITIDOS = {
    "secadora.pesaje",
    "secadora.analisis.lab",
    "secadora.orden.secado",
    "secadora.embolsado",
    "maintenance.equipment",
    "maintenance.request",
    "account.move",
    "res.partner",
    "product.template",
    "product.product",
    "stock.picking",
}

# WhatsApp rechaza envíos grandes y a nadie le sirve recibir 40 MB al celular.
MAX_BYTES = 15 * 1024 * 1024

TIPOS_ENVIABLES = (
    "image/",
    "application/pdf",
    "application/vnd.openxmlformats",
    "application/vnd.ms-excel",
    "text/csv",
)


class AdjuntoError(RuntimeError):
    """Fallo al leer un adjunto, ya redactado para el usuario."""


def leer(store_fname: str, res_model: str, file_size: int, mimetype: str) -> str:
    """Devuelve el contenido en base64, validando antes de tocar el disco."""
    if res_model not in MODELOS_PERMITIDOS:
        raise AdjuntoError(
            f"No puedo enviar adjuntos de {res_model!r}: no está entre los "
            "modelos permitidos."
        )

    if not any(mimetype.startswith(t) for t in TIPOS_ENVIABLES):
        raise AdjuntoError(f"No envío archivos de tipo {mimetype!r}.")

    if file_size and file_size > MAX_BYTES:
        raise AdjuntoError(
            f"El archivo pesa {file_size / 1024 / 1024:.1f} MB; el máximo son "
            f"{MAX_BYTES // 1024 // 1024} MB."
        )

    ruta = _ruta_segura(store_fname)
    try:
        datos = ruta.read_bytes()
    except FileNotFoundError:
        raise AdjuntoError(
            "El archivo está registrado en Odoo pero no aparece en el disco."
        ) from None
    except PermissionError:
        raise AdjuntoError(
            "No tengo permiso para leer ese archivo del filestore."
        ) from None
    except OSError as exc:
        raise AdjuntoError(f"No pude leer el archivo: {exc}") from exc

    if len(datos) > MAX_BYTES:
        raise AdjuntoError("El archivo es demasiado grande para WhatsApp.")

    return base64.b64encode(datos).decode("ascii")


def _ruta_segura(store_fname: str) -> Path:
    """Resuelve la ruta y verifica que no se salga del filestore.

    `store_fname` sale de la base de datos: si alguien lograra escribir ahí un
    '../../etc/passwd', sin esta comprobación el bot lo leería y lo enviaría.
    """
    if not store_fname or not store_fname.strip():
        raise AdjuntoError("Ese adjunto no tiene archivo asociado.")

    base = Path(FILESTORE).resolve()
    candidata = (base / store_fname.strip()).resolve()

    if not candidata.is_relative_to(base):
        log.warning("intento de salir del filestore: %r", store_fname)
        raise AdjuntoError("Ruta de archivo inválida.")

    if candidata.is_symlink() or (candidata.exists() and not candidata.is_file()):
        raise AdjuntoError("Ruta de archivo inválida.")

    return candidata


def filestore_disponible() -> bool:
    """Para el diagnóstico de /salud."""
    try:
        return Path(FILESTORE).is_dir()
    except OSError:
        return False
