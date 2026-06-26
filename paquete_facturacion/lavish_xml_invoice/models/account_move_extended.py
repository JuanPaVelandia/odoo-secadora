# -*- coding: utf-8 -*-
"""
Account Move Extension for DIAN XML Processing
Extiende el modelo account.move para agregar funcionalidad de recuperación XML desde DIAN
"""
import base64
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from . import xml_utils

_logger = logging.getLogger(__name__)

class AccountMoveExtended(models.Model):
    _inherit = 'account.move'

    # Campos adicionales para XML recuperado
    dian_xml_retrieved = fields.Boolean(
        string='XML Recuperado de DIAN',
        readonly=True,
        help='Indica si el XML fue recuperado desde DIAN'
    )
    dian_xml_retrieval_date = fields.Datetime(
        string='Fecha de Recuperación',
        readonly=True,
        help='Fecha y hora en que se recuperó el XML desde DIAN'
    )

    def action_retrieve_xml_from_dian(self):
        """
        Recupera el XML desde DIAN para facturas que tienen CUFE
        Extiende la funcionalidad del módulo l10n_co_e_invoice
        """
        self.ensure_one()

        if not self.cufe:
            raise UserError(_("Esta factura no tiene CUFE registrado"))

        try:
            # Intentar recuperar el XML usando el método nativo extendido
            xml_content = xml_utils.retrieve_xml_from_dian_extended(
                track_id=self.cufe,
                company=self.company_id
            )

            if xml_content:
                # Guardar el XML recuperado
                self.xml_text = xml_content
                self.dian_xml_retrieved = True
                self.dian_xml_retrieval_date = fields.Datetime.now()

                # Extraer y actualizar datos adicionales si es necesario
                extracted_data = xml_utils.extract_data_from_invoice_xml(xml_content)

                # Verificar coherencia de datos
                if extracted_data.get('document_number') and self.ref:
                    if extracted_data['document_number'] != self.ref:
                        self.message_post(
                            body=_("Advertencia: El número de documento del XML (%s) no coincide con la referencia de la factura (%s)")
                                % (extracted_data['document_number'], self.ref),
                            message_type='notification'
                        )

                self.message_post(
                    body=_("XML recuperado exitosamente desde DIAN"),
                    message_type='notification',
                    attachment_ids=[(0, 0, {
                        'name': f'DIAN_{self.cufe}.xml',
                        'datas': base64.b64encode(xml_content.encode('utf-8')),
                        'mimetype': 'application/xml'
                    })]
                )

                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Éxito'),
                        'message': _('XML recuperado exitosamente desde DIAN'),
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                raise UserError(_("No se pudo recuperar el XML desde DIAN"))

        except Exception as e:
            _logger.error(f"Error recuperando XML de DIAN para factura {self.name}: {str(e)}")
            raise UserError(_("Error al recuperar XML desde DIAN: %s") % str(e))

    def _try_retrieve_and_extract_invoice_data(self):
        """
        Intenta recuperar XML de factura y extraer datos
        Sobrescribe el método del módulo l10n_co_e_invoice para usar el método extendido
        """
        self.ensure_one()

        if not self.cufe:
            return False

        try:
            # Primero intentar con el XML ya almacenado
            if self.xml_text:
                # Procesar el XML existente si es necesario
                _logger.info(f"XML ya existe para {self.name}")
                return True

            # Si no hay XML, intentar recuperarlo desde DIAN usando el método extendido
            xml_content = xml_utils.retrieve_xml_from_dian_extended(
                track_id=self.cufe,
                company=self.company_id
            )

            if xml_content:
                self.xml_text = xml_content
                self.dian_xml_retrieved = True
                self.dian_xml_retrieval_date = fields.Datetime.now()

                _logger.info(f"XML recuperado y almacenado para {self.name}")
                return True

        except Exception as e:
            _logger.warning(f"No se pudo recuperar/extraer datos del XML: {str(e)}")

        return False

    @api.model
    def cron_retrieve_missing_xml(self, limit=10):
        """
        Tarea programada para recuperar XMLs faltantes de DIAN
        """
        # Buscar facturas con CUFE pero sin XML
        domain = [
            ('cufe', '!=', False),
            ('xml_text', '=', False),
            ('move_type', 'in', ['in_invoice', 'in_refund']),
            ('state', '!=', 'cancel')
        ]

        invoices = self.search(domain, limit=limit)

        success_count = 0
        failed_count = 0

        for invoice in invoices:
            try:
                if invoice._try_retrieve_and_extract_invoice_data():
                    success_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                _logger.error(f"Error procesando factura {invoice.name}: {str(e)}")
                failed_count += 1

        _logger.info(f"Recuperación de XML completada. Exitosos: {success_count}, Fallidos: {failed_count}")

        return {
            'success': success_count,
            'failed': failed_count
        }