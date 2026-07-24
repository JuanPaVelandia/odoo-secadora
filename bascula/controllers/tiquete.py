# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request, content_disposition


class TiquetePesaje(http.Controller):
    """Sirve el tiquete PDF con nombre de archivo basado en el pesaje.

    La ruta estándar /report/pdf/... no envía Content-Disposition, así que
    al descargar desde el visor del navegador el archivo queda con el id
    numérico del registro. Esta ruta entrega el mismo PDF inline (se abre
    en el visor para imprimir) pero con filename "Tiquete - PESAJE-XXXX.pdf".
    """

    @http.route('/bascula/tiquete/<int:pesaje_id>', type='http', auth='user')
    def tiquete_pdf(self, pesaje_id, **kwargs):
        pesaje = request.env['secadora.pesaje'].browse(pesaje_id)
        pesaje.check_access('read')
        pdf, _dummy = request.env['ir.actions.report']._render_qweb_pdf(
            'bascula.action_report_pesaje_tiquete', [pesaje.id],
        )
        filename = f'Tiquete - {pesaje.name}.pdf'
        return request.make_response(pdf, headers=[
            ('Content-Type', 'application/pdf'),
            ('Content-Length', len(pdf)),
            ('Content-Disposition', content_disposition(filename, 'inline')),
        ])
