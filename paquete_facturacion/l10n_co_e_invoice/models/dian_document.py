# -*- coding: utf-8 -*-
from odoo import api, fields, models
server_url = {
    "HABILITACION": "https://facturaelectronica.dian.gov.co/habilitacion/B2BIntegrationEngine/FacturaElectronica/facturaElectronica.wsdl",
    "PRODUCCION": "https://facturaelectronica.dian.gov.co/operacion/B2BIntegrationEngine/FacturaElectronica/facturaElectronica.wsdl",
    "HABILITACION_CONSULTA": "https://facturaelectronica.dian.gov.co/habilitacion/B2BIntegrationEngine/FacturaElectronica/consultaDocumentos.wsdl",
    "PRODUCCION_CONSULTA": "https://facturaelectronica.dian.gov.co/operacion/B2BIntegrationEngine/FacturaElectronica/consultaDocumentos.wsdl",
    "PRODUCCION_VP": "https://vpfe.dian.gov.co/WcfDianCustomerServices.svc?wsdl",
    # 'PRODUCCION_VP':'https://vpfe-hab.dian.gov.co/WcfDianCustomerServices.svc?wsdl',
    "HABILITACION_VP": "https://vpfe-hab.dian.gov.co/WcfDianCustomerServices.svc?wsdl",
}

tipo_ambiente = {
    "PRODUCCION": "1",
    "PRUEBA": "2",
}

class DianDocument(models.Model):
    _name = "dian.document"
    _rec_name = "dian_code"
    _description = "Dian Document"


    document_id = fields.Many2one(
        "account.move", string="Número de documento", required=True
    )
    state = fields.Selection(
        [
            ("por_notificar", "Por notificar"),
            ("error", "Error"),
            ("por_validar", "Por validar"),
            ("exitoso", "Exitoso"),
            ("rechazado", "Rechazado"),
        ],
        string="Estatus",
        readonly=True,
        default="por_notificar",
        required=True,
    )
    date_document_dian = fields.Char(string="Fecha envio al DIAN", readonly=True)
    shipping_response = fields.Selection(
        [
            ("100", "100 Error al procesar la solicitud WS entrante"),
            ("101","101 El formato de los datos del ejemplar recibido no es correcto"),
            ("102","102 El formato de los datos del ejemplar recibido no es correcto"),
            ("103","103 Tamaño de archivo comprimido zip es 0 o desconocido"),
            ("104","104 Sólo un archivo es permitido por archivo Zip"),
            ("200","200 Ejemplar recibido exitosamente pasará a verificación"),
            ("300","300 Archivo no soportado"),
            ("310", "310 El ejemplar contiene errores de validación semantica"),
            ("320", "320 Parámetros de solicitud de servicio web, no coincide contra el archivo"),
            ("500", "500 Error interno del servicio intentar nuevamente"),
        ],
        string="Respuesta de envío",
    )
    transaction_code = fields.Integer(string="Código de la Transacción de validación")
    transaction_description = fields.Char(string="Descripción de la transacción de validación")
    response_document_dian = fields.Selection(
        [
            ("7200001", "7200001 Recibida"),
            ("7200002", "7200002 Exitosa"),
            ("7200003", "7200003 En proceso de validación"),
            ("7200004", "7200004 Fallida"),
            ("7200005", "7200005 Error"),
        ],
        string="Respuesta de consulta")
    dian_code = fields.Char(string="Código DIAN")
    xml_document = fields.Text(string="Contenido XML del documento")
    xml_file_name = fields.Char(string="Nombre archivo xml")
    zip_file_name = fields.Char(string="Nombre archivo zip")
    cufe_seed = fields.Char(string="CUFE SEED")
    date_request_dian = fields.Datetime(string="Fecha consulta DIAN", readonly=True)
    cufe = fields.Char(string="CUFE")
    QR_code = fields.Binary(string="Código QR", readonly=True)
    date_email_send = fields.Datetime(string="Fecha envío email", readonly=True)
    date_email_acknowledgment = fields.Datetime(string="Fecha acuse email")
    response_message_dian = fields.Text(string="Respuesta DIAN (mensaje)", readonly=True)
    last_shipping = fields.Boolean(string="Ultimo envío", default=True)
    customer_name = fields.Char(
        string="Cliente", readonly=True, related="document_id.partner_id.name"
    )
    date_document = fields.Date(
        string="Fecha documento", readonly=True, related="document_id.invoice_date"
    )
    customer_email = fields.Char(
        string="Email cliente", readonly=True, related="document_id.partner_id.email"
    )
    document_type = fields.Selection(
        [("f", "Factura"), ("c", "Nota/Credito"), ("d", "Nota/Debito"), ("ar", "Application Response")],
        string="Tipo de documento",
        readonly=True,
    )
    resend = fields.Boolean(string="Autorizar reenvio?", default=False)
    email_response = fields.Selection(
        [("accepted", "ACEPTADA"), ("rejected", "RECHAZADA"), ("pending", "PENDIENTE")],
        string="Decisión del cliente",
        required=True,
        default="pending",
        readonly=True,
    )
    email_reject_reason = fields.Char(string="Motivo del rechazo", readonly=True)
    ZipKey = fields.Char(string="Identificador del documento enviado", readonly=True)
    xml_response_dian = fields.Text(
        string="Contenido XML de la respuesta DIAN", readonly=True
    )
    xml_send_query_dian = fields.Text(
        string="Contenido XML de envío de consulta de documento DIAN", readonly=True
    )
    xml_response_contingency_dian = fields.Text(
        string="Mensaje de respuesta DIAN al envío de la contigencia", 
    )
    state_contingency = fields.Selection(
        [
            ("por_notificar", "por_notificar"),
            ("exitosa", "Exitosa"),
            ("rechazada", "Rechazada"),
        ],
        string="Estatus de contingencia",
        default="por_notificar",
        required=True,
    )
    contingency_3 = fields.Boolean(
        string="Contingencia tipo 3", related="document_id.contingency_3"
    )
    contingency_4 = fields.Boolean(
        string="Contingencia tipo 4", related="document_id.contingency_4"
    )
    count_error_DIAN = fields.Integer(
        string="contador de intentos fallidos por problemas de la DIAN", default=0
    )
    date_error_DIAN_1 = fields.Datetime(string="Fecha del 1er. mensaje de error DIAN")
    message_error_DIAN_1 = fields.Text(
        string="Mensaje del 1er. error de respuesta DIAN"
    )
    date_error_DIAN_2 = fields.Datetime(string="Fecha del 2do. mensaje de error DIAN")
    message_error_DIAN_2 = fields.Text(
        string="Mensaje del 2do. error de respuesta DIAN"
    )
    date_error_DIAN_3 = fields.Datetime(string="Fecha del 3er. mensaje de error DIAN")
    message_error_DIAN_3 = fields.Text(
        string="Mensaje del 3er. error de respuesta DIAN"
    )
    qr_data = fields.Text(string="qr Data")
    
    # Campos nuevos del modelo heredado
    message_json = fields.Html(string="Mensaje JSON")
    invoice_id = fields.Many2one(comodel_name='ir.attachment', string="XML Factura")
    response_id = fields.Many2one(comodel_name='ir.attachment', string="Respuesta DIAN")
    attachment_id = fields.Many2one(comodel_name='ir.attachment', string="Attached DIAN")
    email_state = fields.Selection([
        ('pending', 'Pendiente'),
        ('sent', 'Enviado'),
        ('failed', 'Fallido')
    ], string='Estado Email', default='pending')
    email_retry_count = fields.Integer('Intentos de Envío', default=0)
    last_email_try = fields.Datetime('Último Intento de Envío')
    email_error = fields.Text('Error de Envío')
    email_cron = fields.Boolean('Envío Por Cron')

    def action_GetStatusZip_dian_document(self):
        """
        Consulta el estado del documento en DIAN usando GetStatusZip
        Usa el ZipKey (trackId) para consultar el estado
        """
        from odoo.exceptions import UserError
        from odoo.tools.translate import _

        self.ensure_one()

        if not self.ZipKey:
            raise UserError(_("No hay ZipKey (Track ID) disponible para este documento. "
                            "El documento debe haber sido enviado primero a DIAN."))

        # Llamar al método que hace la consulta GetStatusZip
        # Este método está en adstractMove que es heredado por account.move
        try:
            result = self.document_id.request_validating_dian(self.id)

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Consulta GetStatusZip Exitosa'),
                    'message': _('La consulta de estado ha sido enviada a DIAN. '
                               'Revise el campo "Respuesta DIAN" y "Estado" para ver el resultado.'),
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            raise UserError(_("Error al consultar estado en DIAN: %s") % str(e))

    def action_GetXmlByDocumentKey_dian_document(self):
        """
        Recupera el XML del documento desde DIAN usando GetXmlByDocumentKey
        Usa el CUFE (Código Único de Factura Electrónica) como track_id
        """
        from odoo.exceptions import UserError
        from odoo.tools.translate import _

        self.ensure_one()

        if not self.cufe:
            raise UserError(_("No hay CUFE disponible para este documento. "
                            "El documento debe haber sido validado primero por DIAN."))

        # Llamar al método que hace la consulta GetXmlByDocumentKey
        # Este método está en adstractMove que es heredado por account.move
        try:
            # El método _action_get_xml crea el attachment con el XML recuperado
            name = f'DIAN_{self.document_id._get_dian_document_type_dian()}_invoice.xml'
            result = self.document_id._action_get_xml(name=name, cufe=self.cufe)

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('XML Recuperado desde DIAN'),
                    'message': _('El XML ha sido descargado exitosamente desde DIAN. '
                               'Revise los adjuntos del documento para verlo.'),
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            raise UserError(_("Error al recuperar XML desde DIAN: %s") % str(e))

    def process_pending_emails(self):
        """
        Procesa emails pendientes de envío
        Este método es llamado por el cron job
        """
        # Disabled on purpose: this job was posting an HTML-like body as plain text in chatter
        # (Odoo 18 escapes str bodies) and effectively spamming customers/internal chatter.
        # Keep the method to avoid cron/callers crashing, but do nothing.
        return True

        import logging
        _logger = logging.getLogger(__name__)

        # Buscar documentos con emails pendientes o fallidos con menos de 3 intentos
        pending_docs = self.search([
            '|',
            ('email_state', '=', 'pending'),
            '&',
            ('email_state', '=', 'failed'),
            ('email_retry_count', '<', 3)
        ], limit=50)

        _logger.info(f'Procesando {len(pending_docs)} emails pendientes de documentos DIAN')

        for doc in pending_docs:
            try:
                # Si el documento tiene una factura asociada y email válido
                if not doc.document_id or not doc.document_id.partner_id.email:
                    _logger.warning(f'Documento {doc.dian_code} sin factura o email del cliente')
                    continue

                invoice = doc.document_id
                partner = invoice.partner_id

                # Actualizar contador de intentos
                doc.write({
                    'last_email_try': fields.Datetime.now(),
                    'email_retry_count': doc.email_retry_count + 1,
                })

                # Preparar adjuntos
                attachment_ids = []

                # Adjuntar XML de la factura si existe
                if doc.invoice_id:
                    attachment_ids.append(doc.invoice_id.id)

                # Adjuntar respuesta de DIAN si existe
                if doc.response_id:
                    attachment_ids.append(doc.response_id.id)

                # Adjuntar documento DIAN si existe
                if doc.attachment_id:
                    attachment_ids.append(doc.attachment_id.id)

                # Preparar asunto y cuerpo del email
                doc_type = 'Factura' if doc.document_type == 'f' else ('Nota Crédito' if doc.document_type == 'c' else ('Nota Débito' if doc.document_type == 'd' else 'Application Response'))
                subject = f'{doc_type} Electrónica {invoice.name}'

                body = f"""
                <p>Estimado(a) {partner.name},</p>
                <p>Adjunto encontrará la {doc_type} Electrónica <strong>{invoice.name}</strong> correspondiente a su compra.</p>
                <p><strong>Detalles del documento:</strong></p>
                <ul>
                    <li>Número DIAN: {doc.dian_code or 'N/A'}</li>
                    <li>CUFE: {doc.cufe or 'N/A'}</li>
                    <li>Fecha: {invoice.invoice_date}</li>
                    <li>Total: {invoice.currency_id.symbol} {invoice.amount_total:,.2f}</li>
                </ul>
                <p>Gracias por su preferencia.</p>
                <br/>
                <p>Este es un email automático, por favor no responder.</p>
                """

                # Enviar email usando el método de Odoo
                invoice.with_context(no_new_invoice=True).message_post(
                    body=body,
                    subject=subject,
                    partner_ids=[partner.id],
                    attachment_ids=attachment_ids,
                    message_type='comment',
                    subtype_xmlid='mail.mt_comment',
                    email_layout_xmlid='mail.mail_notification_light',
                )

                # Marcar como enviado exitosamente
                doc.write({
                    'email_state': 'sent',
                    'date_email_send': fields.Datetime.now(),
                    'email_error': False,
                })

                _logger.info(f'Email enviado exitosamente para documento {doc.dian_code} a {partner.email}')

            except Exception as e:
                error_msg = str(e)
                _logger.error(f'Error procesando email para documento {doc.dian_code}: {error_msg}')
                doc.write({
                    'email_state': 'failed',
                    'email_error': error_msg,
                })

        return True
