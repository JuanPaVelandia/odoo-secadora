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
        """Anexa al final del reporte 'Viajes Facturados por Pagar' el PDF
        físico de cada factura de proveedor (adjunto de account.move).

        wkhtmltopdf no puede embeber un PDF dentro del HTML, así que primero se
        genera el reporte QWeb normal y luego se hace merge con los PDFs de las
        facturas usando la utilidad de Odoo.
        """
        pdf_content, report_type = super()._render_qweb_pdf(
            report_ref, res_ids=res_ids, data=data
        )

        # Solo actuar sobre nuestro reporte de viajes.
        report = self._get_report(report_ref)
        if not report or report.report_name != REPORT_VIAJES or report_type != 'pdf':
            return pdf_content, report_type

        # res_ids normalmente llega poblado (el wizard usa report_action con el
        # recordset), pero si el reporte se invoca pasando los ids dentro de
        # data, tomarlos de ahí como respaldo.
        ids = res_ids or (data or {}).get('ids') or (data or {}).get('docids')
        if not ids:
            return pdf_content, report_type

        facturas = self.env['account.move'].browse(ids)
        pdfs_facturas = self._recolectar_pdfs_facturas(facturas)
        if not pdfs_facturas:
            return pdf_content, report_type

        try:
            merged = merge_pdf([pdf_content] + pdfs_facturas)
            return merged, report_type
        except Exception as e:
            # Si el merge falla (PDF corrupto, etc.), devolver al menos el
            # reporte base en vez de romper la impresión.
            _logger.warning(
                'No se pudieron anexar los PDF de facturas al reporte de '
                'viajes por pagar: %s', e
            )
            return pdf_content, report_type

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
