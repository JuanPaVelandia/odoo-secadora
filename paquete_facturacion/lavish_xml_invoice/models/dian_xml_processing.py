# -*- coding: utf-8 -*-
import base64
import logging
import xmltodict
import zipfile
import io
from odoo import models, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class DianXmlProcessingMixin(models.AbstractModel):
    """Mixin para procesamiento de archivos XML, ZIP y correos electrónicos DIAN"""
    _name = 'dian.xml.processing.mixin'
    _description = 'Mixin de Procesamiento XML/ZIP DIAN'

    @api.onchange('zip_file')
    def _onchange_zip_file(self):
        """Extrae automaticamente XML y PDF cuando se sube un archivo ZIP"""
        if not self.zip_file:
            return

        try:
            zip_data = base64.b64decode(self.zip_file)
            zip_archive = zipfile.ZipFile(io.BytesIO(zip_data))
            xml_found = False
            pdf_found = False
            messages = []

            for file_info in zip_archive.filelist:
                filename = file_info.filename.lower()

                if filename.endswith('.xml') and not xml_found:
                    xml_content = zip_archive.read(file_info.filename)
                    self.xml_content = base64.b64encode(xml_content)
                    self.xml_filename = file_info.filename
                    xml_found = True
                    messages.append(f"XML: {file_info.filename}")
                    _logger.info(f"XML extraido de ZIP (onchange): {file_info.filename}")

                elif filename.endswith('.pdf') and not pdf_found:
                    pdf_content = zip_archive.read(file_info.filename)
                    self.pdf_file = base64.b64encode(pdf_content)
                    self.pdf_filename = file_info.filename
                    pdf_found = True
                    messages.append(f"PDF: {file_info.filename}")
                    _logger.info(f"PDF extraido de ZIP (onchange): {file_info.filename}")

                if xml_found and pdf_found:
                    break

            zip_archive.close()

            if messages:
                return {
                    'warning': {
                        'title': _('ZIP Procesado'),
                        'message': _('Archivos extraidos: %s') % ', '.join(messages),
                        'type': 'notification'
                    }
                }
            else:
                return {
                    'warning': {
                        'title': _('ZIP sin archivos validos'),
                        'message': _('No se encontraron archivos XML o PDF en el ZIP'),
                        'type': 'warning'
                    }
                }

        except zipfile.BadZipFile:
            return {
                'warning': {
                    'title': _('Error'),
                    'message': _('El archivo no es un ZIP valido'),
                    'type': 'danger'
                }
            }
        except Exception as e:
            _logger.error(f"Error al procesar ZIP (onchange): {str(e)}")
            return {
                'warning': {
                    'title': _('Error'),
                    'message': _('Error al procesar ZIP: %s') % str(e),
                    'type': 'danger'
                }
            }

    @api.onchange('xml_content')
    def _onchange_xml_content(self):
        """Valida y extrae informacion basica cuando se sube un XML"""
        if not self.xml_content:
            return

        try:
            xml_string = base64.b64decode(self.xml_content).decode('utf-8')
            dict_data = xmltodict.parse(xml_string)

            valid_doc_types = ['Invoice', 'CreditNote', 'DebitNote', 'AttachedDocument']
            doc_type_found = None

            for doc_type in valid_doc_types:
                if doc_type in dict_data:
                    doc_type_found = doc_type
                    break

            if not doc_type_found:
                return {
                    'warning': {
                        'title': _('XML no valido'),
                        'message': _('El XML no es un documento DIAN valido. Raiz: %s') % ', '.join(dict_data.keys()),
                        'type': 'warning'
                    }
                }

            if doc_type_found == 'AttachedDocument':
                attached = dict_data['AttachedDocument']
                attachment = attached.get('cac:Attachment', {})
                external_ref = attachment.get('cac:ExternalReference', {})
                invoice_xml = external_ref.get('cbc:Description')
                if invoice_xml:
                    dict_data = xmltodict.parse(invoice_xml)
                    for dt in ['Invoice', 'CreditNote', 'DebitNote']:
                        if dt in dict_data:
                            doc_type_found = dt
                            break

            if doc_type_found in dict_data:
                doc_root = dict_data[doc_type_found]
                doc_number = doc_root.get('cbc:ID')
                cufe = doc_root.get('cbc:UUID')

                if doc_number:
                    doc_number_value = doc_number.get('#text') if isinstance(doc_number, dict) else doc_number
                    if not self.document_number:
                        self.document_number = doc_number_value

                if cufe:
                    cufe_value = cufe.get('#text') if isinstance(cufe, dict) else cufe
                    if not self.cufe:
                        self.cufe = cufe_value

                type_names = {
                    'Invoice': 'Factura',
                    'CreditNote': 'Nota Credito',
                    'DebitNote': 'Nota Debito'
                }

                return {
                    'warning': {
                        'title': _('XML Cargado'),
                        'message': _('%s detectada: %s. Presione "Procesar XML" para extraer toda la informacion.') % (
                            type_names.get(doc_type_found, doc_type_found),
                            doc_number_value if doc_number else 'Sin numero'
                        ),
                        'type': 'notification'
                    }
                }

        except xmltodict.expat.ExpatError as e:
            return {
                'warning': {
                    'title': _('XML Malformado'),
                    'message': _('El archivo XML tiene errores de sintaxis: %s') % str(e),
                    'type': 'danger'
                }
            }
        except Exception as e:
            _logger.error(f"Error al validar XML (onchange): {str(e)}")
            return {
                'warning': {
                    'title': _('Error'),
                    'message': _('Error al leer XML: %s') % str(e),
                    'type': 'danger'
                }
            }

    def message_post(self, **kwargs):
        """Override para procesar archivos ZIP automáticamente"""
        result = super(DianXmlProcessingMixin, self).message_post(**kwargs)
        if kwargs.get('attachment_ids'):
            self._process_zip_attachments()
        return result

    def _process_zip_attachments(self):
        """Extrae XML y PDF de archivos ZIP adjuntados en el chatter"""
        Attachment = self.env['ir.attachment']
        zip_attachments = Attachment.search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('mimetype', 'in', ['application/zip', 'application/x-zip-compressed']),
        ])

        for attachment in zip_attachments:
            try:
                zip_data = base64.b64decode(attachment.datas)
                zip_file = zipfile.ZipFile(io.BytesIO(zip_data))
                xml_found = False
                pdf_found = False

                for file_info in zip_file.filelist:
                    filename = file_info.filename.lower()

                    if filename.endswith('.xml') and not xml_found:
                        xml_content = zip_file.read(file_info.filename)
                        self.write({
                            'xml_content': base64.b64encode(xml_content),
                            'xml_filename': file_info.filename,
                        })
                        xml_found = True
                        _logger.info(f"XML extraído de ZIP: {file_info.filename}")

                    elif filename.endswith('.pdf') and not pdf_found:
                        pdf_content = zip_file.read(file_info.filename)
                        pdf_base64 = base64.b64encode(pdf_content)
                        self.write({
                            'pdf_file': pdf_base64,
                            'pdf_filename': file_info.filename,
                        })

                        existing_pdf = Attachment.search([
                            ('res_model', '=', self._name),
                            ('res_id', '=', self.id),
                            ('name', '=', file_info.filename),
                            ('mimetype', '=', 'application/pdf'),
                        ], limit=1)

                        if not existing_pdf:
                            attachment_vals = {
                                'name': file_info.filename,
                                'datas': pdf_base64,
                                'res_model': self._name,
                                'res_id': self.id,
                                'mimetype': 'application/pdf',
                                'type': 'binary',
                                'description': 'PDF del documento DIAN',
                                'public': False,
                            }
                            pdf_attachment = Attachment.create(attachment_vals)
                            self.message_post(
                                body='<p>PDF del documento DIAN adjunto</p>',
                                attachment_ids=[pdf_attachment.id]
                            )
                            _logger.info(f"PDF adjuntado al chatter: {file_info.filename}")

                        pdf_found = True
                        _logger.info(f"PDF extraído de ZIP: {file_info.filename}")

                    if xml_found and pdf_found:
                        break

                zip_file.close()

                if xml_found:
                    self.message_post(
                        body=_("Archivo ZIP procesado: se extrajo XML y PDF automáticamente"),
                        message_type='notification'
                    )
                    if self.state == 'draft':
                        self.process_xml()

            except Exception as e:
                _logger.error(f"Error al procesar ZIP {attachment.name}: {str(e)}")
                self.message_post(
                    body=_("Error al procesar archivo ZIP: %s") % str(e),
                    message_type='notification'
                )

    def action_extract_from_zip(self):
        """Acción manual para extraer archivos de ZIP del chatter"""
        Attachment = self.env['ir.attachment']
        zip_attachments = Attachment.search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('mimetype', 'in', ['application/zip', 'application/x-zip-compressed']),
        ])

        if not zip_attachments:
            raise UserError(_("No se encontraron archivos ZIP en el chatter."))

        self._process_zip_attachments()

        if self.xml_content and self.state == 'draft':
            try:
                self.process_xml()
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': _('ZIP extraído y XML procesado correctamente'),
                        'type': 'success',
                        'sticky': False,
                    }
                }
            except Exception as e:
                _logger.error(f"Error al procesar XML: {str(e)}")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': _('ZIP extraído pero error al procesar XML: %s') % str(e),
                        'type': 'warning',
                        'sticky': True,
                    }
                }

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': _('Archivos extraídos del ZIP correctamente'),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_process_zip_file(self):
        """Procesa el archivo ZIP subido directamente en el campo zip_file"""
        if not self.zip_file:
            raise UserError(_("Por favor sube un archivo ZIP primero"))

        try:
            zip_data = base64.b64decode(self.zip_file)
            zip_file = zipfile.ZipFile(io.BytesIO(zip_data))
            xml_found = False
            pdf_found = False

            for file_info in zip_file.filelist:
                filename = file_info.filename.lower()

                if filename.endswith('.xml') and not xml_found:
                    xml_content = zip_file.read(file_info.filename)
                    self.xml_content = base64.b64encode(xml_content)
                    self.xml_filename = file_info.filename
                    xml_found = True
                    _logger.info(f"XML extraído de ZIP: {file_info.filename}")

                elif filename.endswith('.pdf') and not pdf_found:
                    pdf_content = zip_file.read(file_info.filename)
                    self.pdf_file = base64.b64encode(pdf_content)
                    self.pdf_filename = file_info.filename
                    pdf_found = True
                    _logger.info(f"PDF extraído de ZIP: {file_info.filename}")

                if xml_found and pdf_found:
                    break

            zip_file.close()

            if not xml_found and not pdf_found:
                raise UserError(_("No se encontraron archivos XML o PDF en el ZIP"))

            message = []
            if xml_found:
                message.append('XML')
            if pdf_found:
                message.append('PDF')

            self.message_post(
                body=_("ZIP procesado exitosamente. Se extrajo: %s") % ', '.join(message)
            )

            if xml_found and self.state == 'draft':
                self.process_xml()
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': _('ZIP procesado y XML cargado'),
                        'type': 'success',
                        'sticky': False,
                    }
                }

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': _('ZIP procesado. Extraídos: %s') % ', '.join(message),
                    'type': 'success',
                    'sticky': False,
                }
            }

        except zipfile.BadZipFile:
            raise UserError(_("El archivo no es un ZIP válido"))
        except Exception as e:
            _logger.error(f"Error al procesar ZIP: {str(e)}")
            raise UserError(_("Error al procesar ZIP: %s") % str(e))

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        """Procesa correos entrantes automáticamente con adjuntos XML/ZIP"""
        _logger.info(f"Correo entrante: {msg_dict.get('subject', 'Sin asunto')}")

        if custom_values is None:
            custom_values = {}

        defaults = {
            'state': 'draft',
            'notes': f"Documento desde correo: {msg_dict.get('subject', '')}",
        }
        defaults.update(custom_values)

        record = super(DianXmlProcessingMixin, self).message_new(msg_dict, custom_values=defaults)
        record._process_email_attachments(msg_dict)
        return record

    def _process_email_attachments(self, msg_dict):
        """Procesa automáticamente archivos ZIP y XML del correo"""
        self.ensure_one()

        attachments = msg_dict.get('attachments', [])
        if not attachments:
            _logger.info("No se encontraron adjuntos en el correo")
            self.message_post(
                body='<p>Correo sin adjuntos. Envíe un archivo ZIP o XML.</p>',
                message_type='notification'
            )
            return

        _logger.info(f"Analizando {len(attachments)} adjunto(s)")

        valid_attachments = []
        for attachment in attachments:
            filename = attachment[0].lower() if attachment and len(attachment) > 0 else ''
            if filename.endswith('.zip') or filename.endswith('.xml'):
                valid_attachments.append(attachment)

        if not valid_attachments:
            _logger.info("No se encontraron archivos ZIP o XML")
            self.message_post(
                body='<p><strong>Sin archivos válidos</strong></p>'
                     '<p>Solo se procesan archivos .zip o .xml</p>',
                message_type='notification'
            )
            return

        xml_processed = False

        for attachment in valid_attachments:
            try:
                filename = attachment[0]
                filename_lower = filename.lower()
                file_content = attachment[1] if len(attachment) > 1 else None

                if not file_content:
                    continue

                if filename_lower.endswith('.zip'):
                    _logger.info(f"Procesando ZIP: {filename}")
                    self._process_zip_from_email(filename, file_content)
                    xml_processed = True

                elif filename_lower.endswith('.xml') and not xml_processed:
                    _logger.info(f"Procesando XML: {filename}")
                    xml_base64 = base64.b64encode(file_content) if isinstance(file_content, bytes) else file_content
                    self.write({
                        'xml_content': xml_base64,
                        'xml_filename': filename,
                    })
                    xml_processed = True

            except Exception as e:
                _logger.error(f"Error procesando {filename}: {str(e)}")
                self.message_post(
                    body=f'<p><strong>Error: {filename}</strong></p><p>{str(e)}</p>',
                    message_type='notification'
                )
                continue

        if xml_processed:
            self._validate_and_process_xml()

    def _validate_and_process_xml(self):
        """Valida el XML antes de procesarlo automáticamente"""
        self.ensure_one()

        if not self.xml_content:
            _logger.error("No hay contenido XML para validar")
            self.message_post(
                body='<p><strong>Error:</strong> No se encontró contenido XML</p>',
                message_type='notification'
            )
            return

        try:
            _logger.info("Validando estructura del XML")
            xml_string = base64.b64decode(self.xml_content).decode('utf-8')
            dict_data = xmltodict.parse(xml_string)

            valid_doc_types = ['Invoice', 'CreditNote', 'DebitNote', 'AttachedDocument']
            doc_type_found = None

            for doc_type in valid_doc_types:
                if doc_type in dict_data:
                    doc_type_found = doc_type
                    break

            if not doc_type_found:
                _logger.warning(f"XML no válido. Raíz: {list(dict_data.keys())}")
                self.message_post(
                    body='<p><strong>Documento no válido</strong></p>'
                         '<p>Raíz: {}</p>'.format(', '.join(dict_data.keys())),
                    message_type='notification'
                )
                self.state = 'error'
                self.error_log = f"XML no válido. Raíz: {list(dict_data.keys())}"
                return

            if doc_type_found == 'AttachedDocument':
                attached = dict_data['AttachedDocument']
                attachment = attached.get('cac:Attachment', {})
                external_ref = attachment.get('cac:ExternalReference', {})
                invoice_xml = external_ref.get('cbc:Description')
                if not invoice_xml:
                    raise ValueError("AttachedDocument sin XML interno válido")
                dict_data = xmltodict.parse(invoice_xml)
                if 'Invoice' in dict_data:
                    doc_type_found = 'Invoice'
                elif 'CreditNote' in dict_data:
                    doc_type_found = 'CreditNote'
                elif 'DebitNote' in dict_data:
                    doc_type_found = 'DebitNote'

            _logger.info(f"Documento válido: {doc_type_found}")

            if doc_type_found == 'Invoice':
                doc_root = dict_data['Invoice']
            elif doc_type_found == 'CreditNote':
                doc_root = dict_data['CreditNote']
            elif doc_type_found == 'DebitNote':
                doc_root = dict_data['DebitNote']
            else:
                doc_root = {}

            cufe = doc_root.get('cbc:UUID')
            doc_number = doc_root.get('cbc:ID')

            if not cufe:
                _logger.warning("XML sin CUFE/CUDE")
                self.message_post(
                    body='<p><strong>Advertencia:</strong> XML sin CUFE/CUDE</p>',
                    message_type='notification'
                )

            if cufe:
                existing = self.search([
                    ('cufe', '=', cufe),
                    ('id', '!=', self.id)
                ], limit=1)

                if existing:
                    _logger.warning(f"Duplicado CUFE {cufe}: {existing.id}")
                    self.message_post(
                        body=f'<p><strong>Documento duplicado</strong></p>'
                             f'<p>CUFE: {cufe}</p>'
                             f'<p>Existente: {existing.document_number or existing.id}</p>',
                        message_type='notification'
                    )
                    self.state = 'draft'
                    self.error_log = f"Duplicado. CUFE: {cufe}"
                    return

            _logger.info(f"Procesando documento {doc_number}")
            self.process_xml()

            self.message_post(
                body=f'<p><strong>Documento procesado desde correo</strong></p>'
                     f'<p><strong>Tipo:</strong> {doc_type_found}</p>'
                     f'<p><strong>Número:</strong> {self.document_number}</p>'
                     f'<p><strong>CUFE:</strong> {self.cufe[:20] if self.cufe else "N/A"}...</p>'
                     f'<p><strong>Proveedor:</strong> {self.supplier_id.name if self.supplier_id else "N/A"}</p>'
                     f'<p><strong>Total:</strong> {self.amount_total:,.2f}</p>',
                message_type='notification'
            )
            _logger.info(f"Documento {self.document_number} procesado exitosamente")

        except xmltodict.expat.ExpatError as e:
            _logger.error(f"XML malformado: {str(e)}")
            self.message_post(
                body=f'<p><strong>Error: XML malformado</strong></p><p>{str(e)}</p>',
                message_type='notification'
            )
            self.state = 'error'
            self.error_log = f"XML malformado: {str(e)}"

        except Exception as e:
            _logger.error(f"Error procesando XML: {str(e)}")
            self.message_post(
                body=f'<p><strong>Error al procesar</strong></p><p>{str(e)}</p>',
                message_type='notification'
            )
            self.state = 'error'
            self.error_log = str(e)

    def _process_zip_from_email(self, filename, file_content):
        """Extrae XML y PDF de un archivo ZIP recibido por correo"""
        self.ensure_one()

        try:
            if isinstance(file_content, str):
                zip_data = base64.b64decode(file_content)
            else:
                zip_data = file_content

            zip_file = zipfile.ZipFile(io.BytesIO(zip_data))
            xml_found = False
            pdf_found = False

            for file_info in zip_file.filelist:
                file_name_lower = file_info.filename.lower()

                if file_name_lower.endswith('.xml') and not xml_found:
                    xml_content = zip_file.read(file_info.filename)
                    self.write({
                        'xml_content': base64.b64encode(xml_content),
                        'xml_filename': file_info.filename,
                    })
                    xml_found = True
                    _logger.info(f"XML del ZIP: {file_info.filename}")

                elif file_name_lower.endswith('.pdf') and not pdf_found:
                    pdf_content = zip_file.read(file_info.filename)
                    self.write({
                        'pdf_file': base64.b64encode(pdf_content),
                        'pdf_filename': file_info.filename,
                    })
                    pdf_found = True
                    _logger.info(f"PDF del ZIP: {file_info.filename}")

                if xml_found and pdf_found:
                    break

            zip_file.close()

            if xml_found or pdf_found:
                files = []
                if xml_found:
                    files.append("XML")
                if pdf_found:
                    files.append("PDF")
                _logger.info(f"Extraídos: {', '.join(files)}")

        except Exception as e:
            _logger.error(f"Error extrayendo ZIP {filename}: {str(e)}")
            raise
