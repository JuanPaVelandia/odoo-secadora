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

        if not res_ids:
            return pdf_content, report_type

        facturas = self.env['account.move'].browse(res_ids)
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
        """Devuelve la lista de contenidos PDF (bytes) de los adjuntos de las
        facturas, en el mismo orden en que aparecen en el reporte."""
        Attachment = self.env['ir.attachment'].sudo()
        pdfs = []
        for factura in facturas:
            adjuntos = Attachment.search([
                ('res_model', '=', 'account.move'),
                ('res_id', '=', factura.id),
                ('mimetype', '=', 'application/pdf'),
            ], order='id')
            for adj in adjuntos:
                if adj.datas:
                    pdfs.append(base64.b64decode(adj.datas))
        return pdfs
