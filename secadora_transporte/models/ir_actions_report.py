# -*- coding: utf-8 -*-

import base64
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

        for factura in facturas:
            # Render QWeb del grupo de fletes de esta sola factura (sin
            # total/firmas globales).
            data_grupo = dict(data or {}, viajes_solo_grupos=True)
            pdf_grupo, _ = super()._render_qweb_pdf(
                report_ref, res_ids=[factura.id], data=data_grupo
            )
            partes.append(pdf_grupo)
            # PDF físico de la factura, justo detrás.
            partes.extend(self._recolectar_pdfs_facturas(factura))

        # Hoja final: solo total general + firmas (sin los grupos).
        data_cierre = dict(data or {}, viajes_solo_cierre=True)
        pdf_cierre, _ = super()._render_qweb_pdf(
            report_ref, res_ids=ids, data=data_cierre
        )
        partes.append(pdf_cierre)

        return merge_pdf(partes), 'pdf'

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
                data = downloader.descargar_pdf(enlace)
                if data:
                    pdfs.append(data)
        return pdfs
