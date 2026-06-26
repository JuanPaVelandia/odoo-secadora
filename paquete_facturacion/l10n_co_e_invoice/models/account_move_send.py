# -*- coding: utf-8 -*-

from odoo import api, models


class AccountMoveSend(models.AbstractModel):
    _inherit = 'account.move.send'

    @api.model
    def _get_invoice_extra_attachments(self, move):
        """Adjunta (SOLO LECTURA) el ZIP DIAN ya generado, si existe.

        IMPORTANTE: el core llama este método no solo al enviar el correo, sino
        también para el menú "Imprimir", los documentos legales y al duplicar una
        factura. Por eso este método NO debe regenerar nada (renderizar PDF /
        borrar-crear adjuntos): hacerlo es lento (el menú se queda "cargando") y
        provoca SerializationFailure cuando dos peticiones tocan el mismo adjunto.

        La generación del ZIP ocurre en el envío real (action_send_dian_direct →
        _prepare_dian_zip_attachment); aquí solo se busca y se adjunta el que ya
        exista.
        """
        attachments = super()._get_invoice_extra_attachments(move)

        if move.move_type in ('out_invoice', 'out_refund'):
            zip_att = move.env['ir.attachment'].search([
                ('res_model', '=', 'account.move'),
                ('res_id', '=', move.id),
                ('mimetype', '=', 'application/zip'),
            ], order='id desc', limit=1)
            if zip_att:
                attachments |= zip_att

        # .exists() filtra cualquier adjunto ya eliminado, evitando el MissingError.
        return attachments.exists()
