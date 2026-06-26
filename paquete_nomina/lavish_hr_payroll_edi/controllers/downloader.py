# -*- coding: utf-8 -*-
"""
Controller para descarga de archivos XML/ZIP de nomina electronica.
"""
import base64
import os

from odoo import http
from odoo.http import request


class PayslipEdiDownloader(http.Controller):

    @http.route('/payslip_edi/download/<int:payslip_id>/<string:file_type>',
                type='http', auth='user')
    def download_file(self, payslip_id, file_type, **kwargs):
        """Descarga archivo XML o ZIP de nomina electronica."""
        payslip = request.env['hr.payslip.edi'].browse(payslip_id)
        if not payslip.exists():
            return request.not_found()

        company = payslip.company_id
        repo = company.document_repository_payroll

        if file_type == 'xml':
            filename = payslip.name_xml
        elif file_type == 'zip':
            filename = payslip.name_zip
        else:
            return request.not_found()

        if not filename:
            return request.not_found()

        filepath = os.path.join(repo, filename)
        if not os.path.exists(filepath):
            return request.not_found()

        with open(filepath, 'rb') as f:
            content = f.read()

        if file_type == 'xml':
            content_type = 'application/xml'
        else:
            content_type = 'application/zip'

        return request.make_response(
            content,
            headers=[
                ('Content-Type', content_type),
                ('Content-Disposition', 'attachment; filename="%s"' % filename),
            ]
        )

    @http.route('/payslip_edi/download_content/<int:payslip_id>/<string:content_type_key>',
                type='http', auth='user')
    def download_content(self, payslip_id, content_type_key, **kwargs):
        """Descarga contenido XML almacenado en campos de texto del documento."""
        payslip = request.env['hr.payslip.edi'].browse(payslip_id)
        if not payslip.exists():
            return request.not_found()

        field_map = {
            'xml_enviado': ('xml_sended', 'xml_enviado_%s.xml'),
            'xml_respuesta': ('xml_response_dian', 'xml_respuesta_%s.xml'),
            'xml_consulta': ('xml_send_query_dian', 'xml_consulta_%s.xml'),
        }
        if content_type_key not in field_map:
            return request.not_found()

        field_name, filename_tpl = field_map[content_type_key]
        content = getattr(payslip, field_name, None)
        if not content:
            return request.not_found()

        filename = filename_tpl % (payslip.number or payslip.id)

        return request.make_response(
            content.encode('utf-8') if isinstance(content, str) else content,
            headers=[
                ('Content-Type', 'application/xml; charset=utf-8'),
                ('Content-Disposition', 'attachment; filename="%s"' % filename),
            ]
        )
