# -*- coding: utf-8 -*-

import base64
import io
import logging

from odoo import models
from odoo.tools.pdf import merge_pdf

_logger = logging.getLogger(__name__)

REPORT_VIAJES = 'secadora_transporte.report_viajes_por_pagar_document'


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        """Reporte 'Viajes Facturados por Pagar' con el PDF físico de cada
        factura INTERCALADO justo después del grupo de fletes de esa factura.

        wkhtmltopdf no puede embeber un PDF en el HTML ni sabe en qué página
        termina cada factura. Para intercalar de forma fiable, se renderiza el
        reporte QWeb factura POR factura y se concatena:
            [reporte factura A, PDF A, reporte factura B, PDF B, ...]
        seguido de una hoja final con el total general y las firmas.
        Si el modo intercalado falla, cae al render normal (todo junto).
        """
        report = self._get_report(report_ref)
        es_viajes = report and report.report_name == REPORT_VIAJES

        if not es_viajes:
            return super()._render_qweb_pdf(report_ref, res_ids=res_ids, data=data)

        ids = res_ids or (data or {}).get('ids') or (data or {}).get('docids')
        if not ids:
            return super()._render_qweb_pdf(report_ref, res_ids=res_ids, data=data)

        try:
            return self._render_viajes_intercalado(report_ref, ids, data)
        except Exception as e:
            _logger.warning(
                'Reporte viajes por pagar: falló el modo intercalado (%s). '
                'Se genera el reporte sin intercalar.', e
            )
            return super()._render_qweb_pdf(report_ref, res_ids=ids, data=data)

    def _render_viajes_intercalado(self, report_ref, ids, data):
        """Construye el PDF intercalando factura por factura. Devuelve
        (bytes, 'pdf').

        Los flags que controlan qué pinta cada render (viajes_solo_grupos /
        viajes_solo_cierre) se pasan por `data`, no por contexto: las claves de
        `data` se inyectan directamente en el namespace del template QWeb, que
        es la vía fiable en Odoo 18 (el contexto no siempre llega íntegro al
        render del sub-reporte)."""
        facturas = self.env['account.move'].browse(ids)
        partes = []  # lista de PDFs en bytes, en orden

        # Validación temprana: cada PDF que entre al merge debe empezar por
        # %PDF. Un adjunto corrupto no debe tumbar el intercalado entero — se
        # omite (la factura ya muestra su enlace de Drive como respaldo).
        def _pdf_valido(b):
            return isinstance(b, (bytes, bytearray)) and b[:4] == b'%PDF'

        for factura in facturas:
            # Render QWeb del grupo de fletes de esta sola factura (sin
            # total/firmas globales).
            data_grupo = dict(data or {}, viajes_solo_grupos=True)
            pdf_grupo, _ = super()._render_qweb_pdf(
                report_ref, res_ids=[factura.id], data=data_grupo
            )
            partes.append(pdf_grupo)
            # PDF físico de la factura, justo detrás. Solo se anexan los
            # válidos; uno corrupto se omite (con warning) sin tumbar el resto.
            for pdf in self._recolectar_pdfs_facturas(factura):
                if _pdf_valido(pdf):
                    partes.append(pdf)
                else:
                    _logger.warning(
                        'Viajes por pagar: el PDF de la factura %s no es válido, '
                        'se omite del intercalado (queda su enlace en el reporte).',
                        factura.name
                    )

        # Hoja final: solo total general + firmas (sin los grupos).
        data_cierre = dict(data or {}, viajes_solo_cierre=True)
        pdf_cierre, _ = super()._render_qweb_pdf(
            report_ref, res_ids=ids, data=data_cierre
        )
        partes.append(pdf_cierre)

        # Certificaciones bancarias al final, como respaldo de los datos de
        # cuenta que el reporte ya imprime. Si algo falla aquí se sigue sin
        # ellas: el giro no puede quedarse sin su orden por un anexo.
        try:
            for pdf in self._recolectar_certificaciones(facturas):
                if _pdf_valido(pdf):
                    partes.append(pdf)
                else:
                    _logger.warning(
                        'Viajes por pagar: la certificación bancaria no es un '
                        'PDF válido, se omite del anexo.'
                    )
        except Exception:
            # Con el traceback completo: sin él, un fallo aquí solo se veía
            # como un reporte sin certificaciones, sin pista de por qué.
            _logger.exception(
                'Viajes por pagar: no se pudieron anexar las certificaciones '
                'bancarias. El reporte sale sin ellas.'
            )

        return merge_pdf(partes), 'pdf'

    def _recolectar_certificaciones(self, facturas):
        """PDFs de certificación bancaria de los beneficiarios del giro.

        Se toma el partner de cada factura —a quien realmente se le consigna,
        el mismo del bloque "Datos para inscripción del beneficiario"— y no la
        transportadora del flete, que puede ser un tercero distinto.

        `mapped` ya devuelve cada partner una sola vez, así que un proveedor
        con varias facturas en el mismo giro aporta UNA certificación.
        """
        pdfs = []
        partners = facturas.mapped('partner_id')
        if 'certificacion_bancaria' not in partners._fields:
            return pdfs
        # sudo: el adjunto vive en el filestore y quien imprime el giro puede
        # no tener permiso de lectura sobre el contacto; sin esto la
        # certificación se omitiría en silencio.
        for partner in partners.sudo():
            datos = partner.certificacion_bancaria
            if not datos:
                _logger.info(
                    'Viajes por pagar: %s no tiene certificación bancaria '
                    'cargada; no se anexa.', partner.display_name)
                continue
            # El campo es `attachment=True`: en lectura devuelve el contenido
            # en base64 —que en Python también es `bytes`, así que mirar el
            # tipo no basta para saber si ya viene decodificado—. Se decodifica
            # salvo que el dato ya se vea como archivo crudo.
            contenido = datos
            if not self._parece_archivo(contenido):
                try:
                    contenido = base64.b64decode(datos, validate=True)
                except (ValueError, TypeError):
                    _logger.warning(
                        'Viajes por pagar: no se pudo decodificar la '
                        'certificación de %s. Se omite del anexo.',
                        partner.display_name)
                    continue
            if contenido[:4] != b'%PDF':
                # La certificación suele llegar por WhatsApp como foto: se
                # convierte a una hoja para poder unirla al giro.
                contenido = self._imagen_a_pdf(contenido, partner)
                if not contenido:
                    continue
            pdfs.append(contenido)
            _logger.info(
                'Viajes por pagar: se anexa la certificación bancaria de %s.',
                partner.display_name)
        return pdfs

    def _parece_archivo(self, datos):
        """¿El dato ya es el archivo crudo, o viene en base64?

        No basta con mirar el tipo: base64 en Python también es `bytes`. Se
        reconoce por la firma de los formatos que aquí interesan.
        """
        if not isinstance(datos, (bytes, bytearray)):
            return False
        firmas = (
            b'%PDF',           # PDF
            b'\xff\xd8\xff',   # JPEG
            b'\x89PNG',        # PNG
            b'GIF8',           # GIF
            b'BM',             # BMP
            b'II*\x00',        # TIFF little endian
            b'MM\x00*',        # TIFF big endian
        )
        return any(bytes(datos[:8]).startswith(f) for f in firmas)

    def _imagen_a_pdf(self, contenido, partner):
        """Convierte una imagen a una página PDF tamaño carta.

        Devuelve None si el archivo no es una imagen legible; el giro se
        imprime igual sin esa certificación.
        """
        try:
            from PIL import Image
        except ImportError:
            _logger.warning(
                'Viajes por pagar: falta Pillow, no se puede convertir la '
                'certificación de %s (no es PDF). Se omite.',
                partner.display_name)
            return None
        try:
            imagen = Image.open(io.BytesIO(contenido))
            # El PDF no admite transparencia ni paleta: se aplana a RGB.
            if imagen.mode not in ('RGB', 'L'):
                imagen = imagen.convert('RGB')
            salida = io.BytesIO()
            # 72 dpi = puntos PDF, así una foto de móvil entra en la hoja.
            imagen.save(salida, format='PDF', resolution=72.0)
            return salida.getvalue()
        except Exception:
            _logger.exception(
                'Viajes por pagar: la certificación de %s no es un PDF ni una '
                'imagen legible. Se omite del anexo.', partner.display_name)
            return None

    def _recolectar_pdfs_facturas(self, facturas):
        """Devuelve la lista de contenidos PDF (bytes) de las facturas, en el
        mismo orden en que aparecen en el reporte.

        Por cada factura se toma UN solo PDF, en este orden de preferencia:
        1. El adjunto PDF local (principal, o el más reciente).
        2. Si no hay adjunto pero la factura tiene enlace a Drive
           (x_webviewlink), se descarga el PDF de Drive vía cuenta de servicio.
        Si nada de lo anterior da un PDF, la factura se omite (el reporte
        muestra igualmente el enlace de Drive como respaldo).
        """
        Attachment = self.env['ir.attachment'].sudo()
        downloader = self.env.get('custom_webviewlink.drive_downloader')
        # Construir el cliente de Drive UNA vez y reutilizarlo para todas las
        # facturas (evita leer la clave JSON y crear el cliente por factura).
        drive_service = downloader._get_drive_service() if downloader is not None else None
        pdfs = []
        for factura in facturas:
            adjuntos = Attachment.search([
                ('res_model', '=', 'account.move'),
                ('res_id', '=', factura.id),
                '|', ('mimetype', 'in', ('application/pdf', 'application/x-pdf')),
                     ('name', '=ilike', '%.pdf'),
            ], order='id desc')
            if adjuntos:
                principal = factura.message_main_attachment_id
                elegido = principal if principal in adjuntos else adjuntos[:1]
                if elegido.datas:
                    pdfs.append(base64.b64decode(elegido.datas))
                    continue
            # Sin adjunto local: intentar Drive.
            enlace = getattr(factura, 'x_webviewlink', False)
            if enlace and downloader is not None:
                data = downloader.descargar_pdf(enlace, service=drive_service)
                if data:
                    pdfs.append(data)
        return pdfs
