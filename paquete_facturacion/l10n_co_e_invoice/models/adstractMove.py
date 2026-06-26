# -*- coding: utf-8 -*-
"""
Abstract DIAN Mixin - Lógica completa de firma digital DIAN Colombia
Versión completa con todos los métodos integrados de ambos archivos
"""
import logging
import base64
import zipfile
import hashlib
import uuid
import requests
import xmltodict
import re
import math
import pyqrcode
import png
import textwrap
import gzip
import json
from datetime import datetime, timedelta
from io import BytesIO
from lxml import etree
from pytz import timezone
from random import randint
from unidecode import unidecode
from odoo import api, fields, models, _, tools
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_repr, cleanup_xml_node, html_escape
from markupsafe import Markup
from . import xml_utils

# Importaciones para firma digital
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography import x509

try:
    import zlib
    compression = zipfile.ZIP_DEFLATED
except ImportError:
    compression = zipfile.ZIP_STORED

_logger = logging.getLogger(__name__)

# URLs DIAN
server_url = {
    "HABILITACION": "https://facturaelectronica.dian.gov.co/habilitacion/B2BIntegrationEngine/FacturaElectronica/facturaElectronica.wsdl",
    "PRODUCCION": "https://facturaelectronica.dian.gov.co/operacion/B2BIntegrationEngine/FacturaElectronica/facturaElectronica.wsdl",
    "HABILITACION_CONSULTA": "https://facturaelectronica.dian.gov.co/habilitacion/B2BIntegrationEngine/FacturaElectronica/consultaDocumentos.wsdl",
    "PRODUCCION_CONSULTA": "https://facturaelectronica.dian.gov.co/operacion/B2BIntegrationEngine/FacturaElectronica/consultaDocumentos.wsdl",
    "PRODUCCION_VP": "https://vpfe.dian.gov.co/WcfDianCustomerServices.svc?wsdl",
    "HABILITACION_VP": "https://vpfe-hab.dian.gov.co/WcfDianCustomerServices.svc?wsdl",
}

tipo_ambiente = {
    "PRODUCCION": "1",
    "PRUEBA": "2",
}

tributes = {
    "01": "IVA",
    "02": "IC",
    "03": "ICA",
    "04": "INC",
    "05": "ReteIVA",
    "06": "ReteFuente",
    "07": "ReteICA",
    "08": "ReteCREE",
    "20": "FtoHorticultura",
    "21": "Timbre",
    "22": "Bolsas",
    "23": "INCarbono",
    "24": "INCombustibles",
    "25": "Sobretasa Combustibles",
    "26": "Sordicom",
    "ZY": "No causa",
    "ZZ": "Nombre de la figura tributaria",
}

class AbstractDianMixin(models.AbstractModel):
    """
    Modelo abstracto que contiene toda la lógica de envío DIAN con firma digital completa
    """
    _name = 'abstract.dian.mixin'
    _description = 'DIAN Electronic Invoice Mixin with Complete Signing Logic'
    
    # -------------------------------------------------------------------------
    # CAMPOS
    # -------------------------------------------------------------------------
    
    dian_xml_attachment_id = fields.Many2one('ir.attachment', string="Adjunto XML")
    dian_response_attachment_id = fields.Many2one('ir.attachment', string="Respuesta")
    dian_attached_document_id = fields.Many2one('ir.attachment', string="Documento Adjunto DIAN")
    ZipKey = fields.Char(string="Identificador del documento enviado", readonly=True, copy=False)
    state_dian_document = fields.Selection([
        ('por_notificar', 'Por notificar'),
        ('error', 'Error'),
        ('por_validar', 'Por validar'),
        ('rechazado', 'Rechazado'),
        ('exitoso', 'Exitoso'),
    ], string='Estado documento DIAN', copy=False)
    response_message_dian = fields.Html(string='Mensaje DIAN', sanitize=False, copy=False)
    force_attached_document_recreation = fields.Boolean(
        string="Forzar Recreación de Documento Adjunto",
        help="Si está activo, se regenerará el documento adjunto aunque ya exista"
    )
    
    # -------------------------------------------------------------------------
    # MÉTODOS ABSTRACTOS
    # -------------------------------------------------------------------------
    
    def _collect_all_dian_data(self):
        """
        Recolecta todos los datos necesarios para DIAN
        Debe ser implementado en las clases hijas
        """
        raise NotImplementedError("Este método debe ser implementado en la clase hija")
    
    def generate_dian_xml(self):
        """
        Genera el XML del documento
        Debe ser implementado en las clases hijas
        """
        raise NotImplementedError("Este método debe ser implementado en la clase hija")
    
    # -------------------------------------------------------------------------
    # MÉTODO PRINCIPAL DE ENVÍO
    # -------------------------------------------------------------------------
    
    def dian_send_invoice(self):
        """Método principal para enviar factura a DIAN"""
        self.ensure_one()
        for rec in self:
            if not rec._is_dian_applicable():
                return False
            
            if rec.state_dian_document == 'exitoso':
                raise UserError(_("Este documento ya fue validado por DIAN"))
            
            try:
                # BUG-005: Validar que partner_id existe antes de llamar check_info_partner()
                if hasattr(rec, 'partner_id') and rec.partner_id:
                    rec.partner_id.check_info_partner()
                dian_constants = rec._collect_all_dian_data()
                
                xml_content = rec._get_or_generate_xml(dian_constants)
                if not xml_content:
                    raise UserError(_("No se pudo generar el XML DIAN"))
                
                # Firmar el documento XML con la lógica completa
                signed_xml = rec._sign_xml_document_complete(xml_content, dian_constants)
                
                rec._save_xml_attachment(signed_xml, dian_constants)
                
                response = rec._send_to_dian_service(signed_xml, dian_constants)
                
                rec._process_dian_response(response, dian_constants)
                
                dian_doc = rec._create_dian_document_record(dian_constants, response)

                if rec._is_regla_90_response(response):
                    rec._handle_regla_90_recovery(response, dian_doc)

                # Auto-envío de email: el hook en write() no puede dispararlo porque
                # diancode_id se crea DESPUÉS de que _process_dian_response ya escribió
                # state_dian_document = 'exitoso'. Se dispara aquí explícitamente.
                if (
                    rec.state_dian_document == 'exitoso'
                    and rec.journal_id.dian_email_enabled
                    and rec.move_type in ('out_invoice', 'out_refund')
                    and not (rec.diancode_id and rec.diancode_id.date_email_send)
                    and rec.diancode_id and getattr(rec.diancode_id, 'xml_file_name', False)
                ):
                    try:
                        zip_att = rec._l10n_co_dian_get_or_create_email_zip_attachment()
                        if zip_att:
                            rec.with_context(skip_dian_email_auto=True)._send_dian_email()
                    except Exception as e_email:
                        _logger.warning(
                            "Error en auto-envío email DIAN para %s: %s",
                            rec.name, str(e_email)
                        )

                return True
                
            except Exception as e:
                rec.state_dian_document = 'error'
                rec.response_message_dian = str(e)
                _logger.error(f"Error enviando a DIAN: {str(e)}", exc_info=True)
                raise

    # -------------------------------------------------------------------------
    # MÉTODOS DE CERTIFICADOS (del primer archivo)
    # -------------------------------------------------------------------------
    
    def get_key(self):
        """Obtiene la clave privada y certificado desde PKCS12"""
        company = self.env.company
        password = company.certificate_key
        try:
            archivo_key = base64.b64decode(company.certificate_file)
            
            private_key, certificate, additional_certificates = pkcs12.load_key_and_certificates(
                archivo_key, password.encode(), backend=default_backend()
            )
           
            return private_key, certificate
        except Exception as ex:
            raise UserError(_("Failed to load certificate: %s") % tools.ustr(ex))

    def get_pem(self):
        """Obtiene la clave pública del certificado PEM"""
        company = self.env.company
        try:
            archivo_pem = base64.b64decode(company.pem_file)
            certificate = x509.load_pem_x509_certificate(archivo_pem, default_backend())
            return certificate.public_key()
        except Exception as ex:
            raise UserError(_("Failed to load PEM file: %s") % tools.ustr(ex))

    # -------------------------------------------------------------------------
    # TEMPLATES DE FIRMA (del primer archivo)
    # -------------------------------------------------------------------------
    
    def _template_signature_data_xml(self):
        """Template para la estructura de firma XML"""
        template_signature_data_xml = """
                <ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#" Id="xmldsig-%(identifier)s">
                    <ds:SignedInfo>
                        <ds:CanonicalizationMethod Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"/>
                        <ds:SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"/>
                        <ds:Reference Id="xmldsig-%(identifier)s-ref0" URI="">
                            <ds:Transforms>
                                <ds:Transform Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature"/>
                            </ds:Transforms>
                            <ds:DigestMethod  Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
                            <ds:DigestValue>%(data_xml_signature_ref_zero)s</ds:DigestValue>
                        </ds:Reference>
                        <ds:Reference URI="#xmldsig-%(identifierkeyinfo)s-keyinfo">
                            <ds:DigestMethod  Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
                            <ds:DigestValue>%(data_xml_keyinfo_base)s</ds:DigestValue>
                        </ds:Reference>
                        <ds:Reference Type="http://uri.etsi.org/01903#SignedProperties" URI="#xmldsig-%(identifier)s-signedprops">
                            <ds:DigestMethod  Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
                            <ds:DigestValue>%(data_xml_SignedProperties_base)s</ds:DigestValue>
                        </ds:Reference>
                    </ds:SignedInfo>
                    <ds:SignatureValue Id="xmldsig-%(identifier)s-sigvalue">%(SignatureValue)s</ds:SignatureValue>
                    <ds:KeyInfo Id="xmldsig-%(identifierkeyinfo)s-keyinfo">
                        <ds:X509Data>
                            <ds:X509Certificate>%(data_public_certificate_base)s</ds:X509Certificate>
                        </ds:X509Data>
                    </ds:KeyInfo>
                    <ds:Object>
                        <xades:QualifyingProperties xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" xmlns:xades141="http://uri.etsi.org/01903/v1.4.1#" Target="#xmldsig-%(identifier)s">
                            <xades:SignedProperties Id="xmldsig-%(identifier)s-signedprops">
                                <xades:SignedSignatureProperties>
                                    <xades:SigningTime>%(data_xml_SigningTime)s</xades:SigningTime>
                                    <xades:SigningCertificate>
                                        <xades:Cert>
                                            <xades:CertDigest>
                                                <ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"/>
                                                <ds:DigestValue>%(CertDigestDigestValue)s</ds:DigestValue>
                                            </xades:CertDigest>
                                            <xades:IssuerSerial>
                                                <ds:X509IssuerName>%(IssuerName)s</ds:X509IssuerName>
                                                <ds:X509SerialNumber>%(SerialNumber)s</ds:X509SerialNumber>
                                            </xades:IssuerSerial>
                                        </xades:Cert>
                                    </xades:SigningCertificate>
                                    <xades:SignaturePolicyIdentifier>
                                        <xades:SignaturePolicyId>
                                            <xades:SigPolicyId>
                                                <xades:Identifier>https://facturaelectronica.dian.gov.co/politicadefirma/v2/politicadefirmav2.pdf</xades:Identifier>
                                                <xades:Description>Politica de firma para facturas electronicas de la Republica de Colombia</xades:Description>
                                            </xades:SigPolicyId>
                                            <xades:SigPolicyHash>
                                                <ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"/>
                                                <ds:DigestValue>%(data_xml_politics)s</ds:DigestValue>
                                            </xades:SigPolicyHash>
                                        </xades:SignaturePolicyId>
                                    </xades:SignaturePolicyIdentifier>
                                    <xades:SignerRole>
                                        <xades:ClaimedRoles>
                                            <xades:ClaimedRole>supplier</xades:ClaimedRole>
                                        </xades:ClaimedRoles>
                                    </xades:SignerRole>
                                </xades:SignedSignatureProperties>
                            </xades:SignedProperties>
                        </xades:QualifyingProperties>
                    </ds:Object>
                </ds:Signature>"""
        return template_signature_data_xml


    # -------------------------------------------------------------------------
    # MÉTODOS DE FIRMA COMPLETA
    # -------------------------------------------------------------------------
    
    def _sign_xml_document_complete(self, xml_content, dian_constants):
        """
        Firma el documento XML con la lógica completa del primer archivo
        """
        try:
            # Convertir a string si es necesario y remover declaración XML existente
            if isinstance(xml_content, bytes):
                xml_content = xml_content.decode('utf-8')
            
            # Remover cualquier declaración XML existente
            if xml_content.startswith('<?xml'):
                xml_start = xml_content.find('?>') + 2
                xml_content = xml_content[xml_start:].strip()
            
            # Obtener template de firma
            template_signature_data_xml = self._template_signature_data_xml()
            
            # Preparar el XML para firma
            data_xml_document = xml_content.replace(
                "<ext:ExtensionContent/>",
                "<ext:ExtensionContent></ext:ExtensionContent>",
            )
            
            # Generar la firma completa
            data_xml_signature = self._generate_signature_complete(
                data_xml_document,
                template_signature_data_xml,
                dian_constants,
                dian_constants,  # data_constants_document
            )
            
            # Parsear y limpiar la firma
            parser = etree.XMLParser(remove_blank_text=True)
            signature_element = etree.fromstring(data_xml_signature.encode('utf-8'), parser=parser)
            data_xml_signature = etree.tostring(
                signature_element,
                encoding='unicode',
                method='xml'
            )
            
            # Incorporar firma al documento
            data_xml_document = data_xml_document.replace(
                "<ext:ExtensionContent></ext:ExtensionContent>",
                f"<ext:ExtensionContent>{data_xml_signature}</ext:ExtensionContent>"
            )
            
            # Parsear el documento final sin agregar declaración XML primero
            parser = etree.XMLParser(remove_blank_text=True)
            root = etree.fromstring(data_xml_document.encode('utf-8'), parser=parser)
            
            # Generar el XML final con declaración
            final_xml = etree.tostring(
                root, 
                encoding='UTF-8', 
                xml_declaration=True, 
                method='xml'
            )
            
            return final_xml
            
        except Exception as e:
            _logger.error(f"Error firmando documento XML: {str(e)}", exc_info=True)
            raise UserError(_("Error al firmar el documento XML: %s") % str(e))

    def _generate_signature_complete(
        self,
        data_xml_document,
        template_signature_data_xml,
        dian_constants,
        data_constants_document,
    ):
        """Genera la firma completa usando la lógica del primer archivo"""
        data_xml_keyinfo_base = ""
        data_xml_politics = ""
        data_xml_SignedProperties_base = ""
        data_xml_SigningTime = ""
        data_xml_SignatureValue = ""
        
        # Generar certificado público para la firma del documento en el elemento keyinfo
        data_public_certificate_base = dian_constants["Certificate"]
        
        # Generar clave de política de firma
        data_xml_politics = self._generate_signature_politics(
            dian_constants["document_repository"]
        )
        
        # Obtener la hora de Colombia
        data_xml_SigningTime = datetime.now(tz=timezone('America/Bogota')).isoformat(timespec='milliseconds')
        
        # Generar clave de referencia 0 para la firma del documento (referencia ref0)
        data_xml_signature_ref_zero = self._generate_signature_ref0(
            data_xml_document,
            dian_constants["document_repository"],
            dian_constants["CertificateKey"],
        )
        
        # Actualizar signature con los valores iniciales
        data_xml_signature = self._update_signature(
            template_signature_data_xml,
            data_xml_signature_ref_zero,
            data_public_certificate_base,
            data_xml_keyinfo_base,
            data_xml_politics,
            data_xml_SignedProperties_base,
            data_xml_SigningTime,
            dian_constants,
            data_xml_SignatureValue,
            data_constants_document,
        )
        
        parser = etree.XMLParser(remove_blank_text=True)
        signature_element = etree.fromstring(data_xml_signature.encode('utf-8'), parser=parser)
        data_xml_signature = etree.tostring(signature_element, encoding='unicode', method='xml')
        
        # Actualizar KeyInfo (referencia 1)
        signature_tree = etree.fromstring(data_xml_signature.encode('utf-8'), parser=parser)
        KeyInfo = etree.tostring(signature_tree[2], encoding='unicode', method='xml')
        
        # Agregar namespaces según el tipo de documento
        KeyInfo = self._add_namespaces_to_keyinfo(KeyInfo, data_constants_document)
        
        data_xml_keyinfo_base = self._generate_signature_ref1(
            KeyInfo,
            dian_constants["document_repository"],
            dian_constants["CertificateKey"],
        )
        
        data_xml_signature = data_xml_signature.replace(
            "<ds:DigestValue/>",
            "<ds:DigestValue>%s</ds:DigestValue>" % data_xml_keyinfo_base,
            1,
        )
        
        # Actualizar SignedProperties (referencia 2)
        signature_tree = etree.fromstring(data_xml_signature.encode('utf-8'), parser=parser)
        signed_properties_parent = signature_tree[3]
        signed_properties_obj = signed_properties_parent[0]
        signed_properties_elem = signed_properties_obj[0]
        
        SignedProperties = etree.tostring(signed_properties_elem, encoding='unicode', method='xml')
        
        # Agregar namespaces según el tipo de documento
        SignedProperties = self._add_namespaces_to_signed_properties(SignedProperties, data_constants_document)
        
        data_xml_SignedProperties_base = self._generate_signature_ref2(SignedProperties)
        data_xml_signature = data_xml_signature.replace(
            "<ds:DigestValue/>",
            "<ds:DigestValue>%s</ds:DigestValue>" % data_xml_SignedProperties_base,
            1,
        )
        
        # Actualizar SignedInfo y generar SignatureValue
        signature_tree = etree.fromstring(data_xml_signature.encode('utf-8'), parser=parser)
        Signedinfo = etree.tostring(signature_tree[0], encoding='unicode', method='xml')
        
        # Agregar namespaces según el tipo de documento
        Signedinfo = self._add_namespaces_to_signed_info(Signedinfo, data_constants_document)
        
        data_xml_SignatureValue = self._generate_SignatureValue(Signedinfo)
        
        data_xml_signature = data_xml_signature.replace(
            '-sigvalue"/>',
            '-sigvalue">%s</ds:SignatureValue>' % data_xml_SignatureValue,
            1,
        )
        
        return data_xml_signature

    def _add_namespaces_to_keyinfo(self, keyinfo, data_constants_document):
        """Agrega namespaces al KeyInfo según el tipo de documento"""
        doc_code = data_constants_document.get("document_code")
        if not doc_code:
            return keyinfo
        if doc_code in ("01", "03"):  # Factura
            xmlns = (
                'xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2" '
                'xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" '
                'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" '
                'xmlns:ds="http://www.w3.org/2000/09/xmldsig#" '
                'xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" '
                'xmlns:sts="http://www.dian.gov.co/contratos/facturaelectronica/v1/Structures" '
                'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            )
        elif doc_code in ("05", "02"):  # Factura contingencia
            xmlns = (
                'xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2" '
                'xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" '
                'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" '
                'xmlns:ds="http://www.w3.org/2000/09/xmldsig#" '
                'xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" '
                'xmlns:sts="dian:gov:co:facturaelectronica:Structures-2-1" '
                'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
                'xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" '
                'xmlns:xades141="http://uri.etsi.org/01903/v1.4.1#"'
            )
        elif doc_code == "AR":  # ApplicationResponse (Eventos)
            xmlns = (
                'xmlns="urn:oasis:names:specification:ubl:schema:xsd:ApplicationResponse-2" '
                'xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" '
                'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" '
                'xmlns:ds="http://www.w3.org/2000/09/xmldsig#" '
                'xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" '
                'xmlns:sts="dian:gov:co:facturaelectronica:Structures-2-1" '
                'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
                'xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" '
                'xmlns:xades141="http://uri.etsi.org/01903/v1.4.1#"'
            )
        elif doc_code in ["91"]:  # Nota de crédito
            xmlns = (
                'xmlns="urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2" '
                'xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" '
                'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" '
                'xmlns:ds="http://www.w3.org/2000/09/xmldsig#" '
                'xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" '
                'xmlns:sts="http://www.dian.gov.co/contratos/facturaelectronica/v1/Structures" '
                'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            )
        elif doc_code in ["95"]:  # Nota de crédito contingencia
            xmlns = (
                'xmlns="urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2" '
                'xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" '
                'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" '
                'xmlns:ds="http://www.w3.org/2000/09/xmldsig#" '
                'xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" '
                'xmlns:sts="dian:gov:co:facturaelectronica:Structures-2-1" '
                'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
                'xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" '
                'xmlns:xades141="http://uri.etsi.org/01903/v1.4.1#"'
            )
        elif doc_code == "92":  # Nota de débito
            xmlns = (
                'xmlns="urn:oasis:names:specification:ubl:schema:xsd:DebitNote-2" '
                'xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" '
                'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" '
                'xmlns:ds="http://www.w3.org/2000/09/xmldsig#" '
                'xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" '
                'xmlns:sts="http://www.dian.gov.co/contratos/facturaelectronica/v1/Structures" '
                'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            )
        elif doc_code == "99":  # Attached document
            xmlns = (
                'xmlns="urn:oasis:names:specification:ubl:schema:xsd:AttachedDocument-2" '
                'xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" '
                'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" '
                'xmlns:ccts="urn:un:unece:uncefact:data:specification:CoreComponentTypeSchemaModule:2" '
                'xmlns:ds="http://www.w3.org/2000/09/xmldsig#" '
                'xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" '
                'xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" '
                'xmlns:xades141="http://uri.etsi.org/01903/v1.4.1#"'
            )
        else:
            return keyinfo
            
        return keyinfo.replace(
            'xmlns:ds="http://www.w3.org/2000/09/xmldsig#"', xmlns
        )

    def _add_namespaces_to_signed_properties(self, signed_properties, data_constants_document):
        """Agrega namespaces al SignedProperties según el tipo de documento"""
        doc_code = data_constants_document.get("document_code")
        if not doc_code:
            return signed_properties
        if doc_code in ("01", "03"):
            xmlns = (
                'xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2" '
                'xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" '
                'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" '
                'xmlns:ds="http://www.w3.org/2000/09/xmldsig#" '
                'xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" '
                'xmlns:sts="http://www.dian.gov.co/contratos/facturaelectronica/v1/Structures" '
                'xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" xmlns:xades141="http://uri.etsi.org/01903/v1.4.1#" '
                'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            )
        elif doc_code in ("05", "02"):
            xmlns = (
                'xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2" '
                'xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" '
                'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" '
                'xmlns:ds="http://www.w3.org/2000/09/xmldsig#" '
                'xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" '
                'xmlns:sts="dian:gov:co:facturaelectronica:Structures-2-1" '
                'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
                'xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" '
                'xmlns:xades141="http://uri.etsi.org/01903/v1.4.1#"'
            )
        elif doc_code == "AR":
            xmlns = (
                'xmlns="urn:oasis:names:specification:ubl:schema:xsd:ApplicationResponse-2" '
                'xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" '
                'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" '
                'xmlns:ds="http://www.w3.org/2000/09/xmldsig#" '
                'xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" '
                'xmlns:sts="dian:gov:co:facturaelectronica:Structures-2-1" '
                'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
                'xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" '
                'xmlns:xades141="http://uri.etsi.org/01903/v1.4.1#"'
            )
        elif doc_code in ["91"]:
            xmlns = (
                'xmlns="urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2" '
                'xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" '
                'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" '
                'xmlns:ds="http://www.w3.org/2000/09/xmldsig#" '
                'xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" '
                'xmlns:sts="http://www.dian.gov.co/contratos/facturaelectronica/v1/Structures" '
                'xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" xmlns:xades141="http://uri.etsi.org/01903/v1.4.1#" '
                'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            )
        elif doc_code in ["95"]:
            xmlns = (
                'xmlns="urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2" '
                'xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" '
                'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" '
                'xmlns:ds="http://www.w3.org/2000/09/xmldsig#" '
                'xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" '
                'xmlns:sts="dian:gov:co:facturaelectronica:Structures-2-1" '
                'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
                'xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" '
                'xmlns:xades141="http://uri.etsi.org/01903/v1.4.1#"'
            )
        elif doc_code == "92":
            xmlns = (
                'xmlns="urn:oasis:names:specification:ubl:schema:xsd:DebitNote-2" '
                'xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" '
                'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" '
                'xmlns:ds="http://www.w3.org/2000/09/xmldsig#" '
                'xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" '
                'xmlns:sts="http://www.dian.gov.co/contratos/facturaelectronica/v1/Structures" '
                'xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" xmlns:xades141="http://uri.etsi.org/01903/v1.4.1#" '
                'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            )
        elif doc_code == "99":
            xmlns = (
                'xmlns="urn:oasis:names:specification:ubl:schema:xsd:AttachedDocument-2" '
                'xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" '
                'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" '
                'xmlns:ccts="urn:un:unece:uncefact:data:specification:CoreComponentTypeSchemaModule:2" '
                'xmlns:ds="http://www.w3.org/2000/09/xmldsig#" '
                'xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" '
                'xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" '
                'xmlns:xades141="http://uri.etsi.org/01903/v1.4.1#"'
            )
        else:
            return signed_properties
            
        return signed_properties.replace(
            'xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" xmlns:xades141="http://uri.etsi.org/01903/v1.4.1#" '
            'xmlns:ds="http://www.w3.org/2000/09/xmldsig#"',
            xmlns,
        )

    def _add_namespaces_to_signed_info(self, signed_info, data_constants_document):
        """Agrega namespaces al SignedInfo según el tipo de documento"""
        doc_code = data_constants_document.get("document_code")
        if not doc_code:
            return signed_info
        if doc_code in ("01", "03"):
            xmlns = (
                'xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2" '
                'xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" '
                'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" '
                'xmlns:ds="http://www.w3.org/2000/09/xmldsig#" '
                'xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" '
                'xmlns:sts="http://www.dian.gov.co/contratos/facturaelectronica/v1/Structures" '
                'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            )
        elif doc_code in ("05", "02"):
            xmlns = (
                'xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2" '
                'xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" '
                'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" '
                'xmlns:ds="http://www.w3.org/2000/09/xmldsig#" '
                'xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" '
                'xmlns:sts="dian:gov:co:facturaelectronica:Structures-2-1" '
                'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
                'xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" '
                'xmlns:xades141="http://uri.etsi.org/01903/v1.4.1#"'
            )
        elif doc_code == "AR":
            xmlns = (
                'xmlns="urn:oasis:names:specification:ubl:schema:xsd:ApplicationResponse-2" '
                'xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" '
                'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" '
                'xmlns:ds="http://www.w3.org/2000/09/xmldsig#" '
                'xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" '
                'xmlns:sts="dian:gov:co:facturaelectronica:Structures-2-1" '
                'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
                'xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" '
                'xmlns:xades141="http://uri.etsi.org/01903/v1.4.1#"'
            )
        elif doc_code == "91":
            xmlns = (
                'xmlns="urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2" '
                'xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" '
                'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" '
                'xmlns:ds="http://www.w3.org/2000/09/xmldsig#" '
                'xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" '
                'xmlns:sts="http://www.dian.gov.co/contratos/facturaelectronica/v1/Structures" '
                'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            )
        elif doc_code == "92":
            xmlns = (
                'xmlns="urn:oasis:names:specification:ubl:schema:xsd:DebitNote-2" '
                'xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" '
                'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" '
                'xmlns:ds="http://www.w3.org/2000/09/xmldsig#" '
                'xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" '
                'xmlns:sts="http://www.dian.gov.co/contratos/facturaelectronica/v1/Structures" '
                'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            )
        elif doc_code == "95":
            xmlns = (
                'xmlns="urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2" '
                'xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" '
                'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" '
                'xmlns:ds="http://www.w3.org/2000/09/xmldsig#" '
                'xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" '
                'xmlns:sts="dian:gov:co:facturaelectronica:Structures-2-1" '
                'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
                'xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" '
                'xmlns:xades141="http://uri.etsi.org/01903/v1.4.1#"'
            )
        elif doc_code == "99":
            xmlns = (
                'xmlns="urn:oasis:names:specification:ubl:schema:xsd:AttachedDocument-2" '
                'xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" '
                'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" '
                'xmlns:ccts="urn:un:unece:uncefact:data:specification:CoreComponentTypeSchemaModule:2" '
                'xmlns:ds="http://www.w3.org/2000/09/xmldsig#" '
                'xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" '
                'xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" '
                'xmlns:xades141="http://uri.etsi.org/01903/v1.4.1#"'
            )
        else:
            return signed_info
            
        return signed_info.replace(
            'xmlns:ds="http://www.w3.org/2000/09/xmldsig#"', xmlns
        )

    def _generate_signature_ref0(self, data_xml_document, document_repository, password):
        """Genera la referencia 0 (documento completo)"""
        try:
            # Asegurar que el documento esté en formato string
            if isinstance(data_xml_document, bytes):
                data_xml_document = data_xml_document.decode('utf-8')
            
            # Parsear el documento
            parser = etree.XMLParser(remove_blank_text=True)
            xml_element = etree.fromstring(data_xml_document.encode('utf-8'), parser=parser)
            
            # Canonicalizar usando c14n
            template_basic_data_fe_xml = etree.tostring(
                xml_element,
                method="c14n",
                exclusive=False,
                with_comments=False,
                inclusive_ns_prefixes=None,
            )
            
            # Generar hash SHA256
            data_xml_sha256 = hashlib.new("sha256", template_basic_data_fe_xml)
            data_xml_digest = data_xml_sha256.digest()
            data_xml_signature_ref_zero = base64.b64encode(data_xml_digest)
            data_xml_signature_ref_zero = data_xml_signature_ref_zero.decode()
            return data_xml_signature_ref_zero
            
        except Exception as e:
            _logger.error(f"Error generando signature ref0: {str(e)}")
            raise UserError(_("Error generando referencia de firma: %s") % str(e))

    def _generate_signature_ref1(self, data_xml_keyinfo_generate, document_repository, password):
        """Genera la referencia 1 (KeyInfo)"""
        try:
            # Asegurar que el contenido esté en formato string
            if isinstance(data_xml_keyinfo_generate, bytes):
                data_xml_keyinfo_generate = data_xml_keyinfo_generate.decode('utf-8')
            
            # Parsear y canonicalizar
            parser = etree.XMLParser(remove_blank_text=True)
            xml_element = etree.fromstring(data_xml_keyinfo_generate.encode('utf-8'), parser=parser)
            data_xml_keyinfo_generate = etree.tostring(xml_element, method="c14n")
            
            # Generar hash
            data_xml_keyinfo_sha256 = hashlib.new("sha256", data_xml_keyinfo_generate)
            data_xml_keyinfo_digest = data_xml_keyinfo_sha256.digest()
            data_xml_keyinfo_base = base64.b64encode(data_xml_keyinfo_digest)
            data_xml_keyinfo_base = data_xml_keyinfo_base.decode()
            return data_xml_keyinfo_base
            
        except Exception as e:
            _logger.error(f"Error generando signature ref1: {str(e)}")
            raise UserError(_("Error generando referencia KeyInfo: %s") % str(e))

    def _generate_signature_ref2(self, data_xml_SignedProperties_generate):
        """Genera la referencia 2 (SignedProperties)"""
        try:
            # Asegurar que el contenido esté en formato string
            if isinstance(data_xml_SignedProperties_generate, bytes):
                data_xml_SignedProperties_generate = data_xml_SignedProperties_generate.decode('utf-8')
            
            # Parsear y canonicalizar
            parser = etree.XMLParser(remove_blank_text=True)
            xml_element = etree.fromstring(data_xml_SignedProperties_generate.encode('utf-8'), parser=parser)
            data_xml_SignedProperties_c14n = etree.tostring(xml_element, method="c14n")
            
            # Generar hash
            data_xml_SignedProperties_sha256 = hashlib.new("sha256", data_xml_SignedProperties_c14n)
            data_xml_SignedProperties_digest = data_xml_SignedProperties_sha256.digest()
            data_xml_SignedProperties_base = base64.b64encode(data_xml_SignedProperties_digest)
            data_xml_SignedProperties_base = data_xml_SignedProperties_base.decode()
            return data_xml_SignedProperties_base
            
        except Exception as e:
            _logger.error(f"Error generando signature ref2: {str(e)}")
            raise UserError(_("Error generando referencia SignedProperties: %s") % str(e))

    def _generate_signature_politics(self, document_repository):
        """Genera la política de firma"""
        data_xml_politics = "dMoMvtcG5aIzgYo0tIsSQeVJBDnUnfSOfBpxXrmor0Y="
        return data_xml_politics

    def _generate_CertDigestDigestValue(self):
        """Genera el digest value del certificado"""
        _, certificate = self.get_key()

        cert_der = certificate.public_bytes(encoding=serialization.Encoding.DER)
        digest = hashes.Hash(hashes.SHA256())
        digest.update(cert_der)
        cert_digest = digest.finalize()
        CertDigestDigestValue = base64.b64encode(cert_digest).decode()
        return CertDigestDigestValue

    def _get_certificate_info(self):
        """Recolecta datos del certificado para firma"""
        company = self.company_id

        if not company.digital_certificate or company.digital_certificate == "0":
            raise UserError(_("Falta configurar el certificado digital en la Compañía"))
        if not company.certificate_key or company.certificate_key == "0":
            raise UserError(_("Falta configurar la clave del certificado en la Compañía"))

        return {
            "Certificate": company.digital_certificate,
            "CertificateKey": company.certificate_key,
            "IssuerName": company.issuer_name or "",
            "SerialNumber": company.serial_number or "",
            "CertDigestDigestValue": self._generate_CertDigestDigestValue(),
            "document_repository": company.document_repository or "",
            "identifier": str(uuid.uuid4()),
            "identifierkeyinfo": str(uuid.uuid4()),
        }

    def _generate_SignatureValue(self, data_xml_SignedInfo_generate):
        """Genera el valor de la firma"""
        try:
            # Asegurar que el contenido esté en formato string
            if isinstance(data_xml_SignedInfo_generate, bytes):
                data_xml_SignedInfo_generate = data_xml_SignedInfo_generate.decode('utf-8')
            
            # Parsear y canonicalizar el SignedInfo
            parser = etree.XMLParser(remove_blank_text=True)
            xml_element = etree.fromstring(data_xml_SignedInfo_generate.encode('utf-8'), parser=parser)
            data_xml_SignatureValue_c14n = etree.tostring(
                xml_element,
                method="c14n",
                exclusive=False,
                with_comments=False,
            )
            
            # Obtener clave privada
            private_key, _ = self.get_key()
            
            try:
                # Firmar los datos
                signature = private_key.sign(
                    data_xml_SignatureValue_c14n,
                    padding.PKCS1v15(),
                    hashes.SHA256()
                )
            except Exception as ex:
                raise UserError(_("Failed to sign the document: %s") % tools.ustr(ex))
            
            SignatureValue = base64.b64encode(signature).decode()
            
            # Verificar la firma
            public_key = self.get_pem()
            try:
                public_key.verify(
                    signature,
                    data_xml_SignatureValue_c14n,
                    padding.PKCS1v15(),
                    hashes.SHA256()
                )
            except Exception:
                raise UserError(_("Signature was not successfully validated"))
            
            return SignatureValue
            
        except Exception as e:
            _logger.error(f"Error generando SignatureValue: {str(e)}")
            raise UserError(_("Error generando valor de firma: %s") % str(e))

    def _generate_SignatureValue_GetStatus(self, data_xml_SignedInfo_generate):
        """Genera la firma para GetStatus"""
        data_xml_SignatureValue_c14n = etree.tostring(
            etree.fromstring(data_xml_SignedInfo_generate), method="c14n"
        )
        
        private_key, _ = self.get_key() 
        
        try:
            signature = private_key.sign(
                data_xml_SignatureValue_c14n,
                padding.PKCS1v15(),
                hashes.SHA256()
            )
        except Exception as ex:
            raise UserError(_("Failed to sign the document: %s") % tools.ustr(ex))
        
        SignatureValue = base64.b64encode(signature).decode()
        
        public_key = self.get_pem() 
        
        try:
            public_key.verify(
                signature,
                data_xml_SignatureValue_c14n,
                padding.PKCS1v15(),
                hashes.SHA256()
            )
        except Exception:
            raise UserError(_("Firma para el GetStatus no fué validada exitosamente"))
        return SignatureValue

    def _update_signature(
        self,
        template_signature_data_xml,
        data_xml_signature_ref_zero,
        data_public_certificate_base,
        data_xml_keyinfo_base,
        data_xml_politics,
        data_xml_SignedProperties_base,
        data_xml_SigningTime,
        dian_constants,
        data_xml_SignatureValue,
        data_constants_document,
    ):
        """Actualiza el template de firma con los valores calculados"""
        data_xml_signature = template_signature_data_xml % {
            "data_xml_signature_ref_zero": data_xml_signature_ref_zero,
            "data_public_certificate_base": data_public_certificate_base,
            "data_xml_keyinfo_base": data_xml_keyinfo_base,
            "data_xml_politics": data_xml_politics,
            "data_xml_SignedProperties_base": data_xml_SignedProperties_base,
            "data_xml_SigningTime": data_xml_SigningTime,
            "CertDigestDigestValue": dian_constants["CertDigestDigestValue"],
            "IssuerName": dian_constants["IssuerName"],
            "SerialNumber": dian_constants["SerialNumber"],
            "SignatureValue": data_xml_SignatureValue,
            "identifier": data_constants_document["identifier"],
            "identifierkeyinfo": data_constants_document["identifierkeyinfo"],
        }
        return data_xml_signature

    def _generate_digestvalue_to(self, elementTo):
        """Generar el digestvalue de to"""
        try:
            # Asegurar que el contenido esté en formato correcto
            if isinstance(elementTo, str):
                elementTo = elementTo.encode('utf-8')
            
            # Parsear y canonicalizar
            parser = etree.XMLParser(remove_blank_text=True)
            xml_element = etree.fromstring(elementTo, parser=parser)
            elementTo = etree.tostring(xml_element, method="c14n")
            
            # Generar hash
            elementTo_sha256 = hashlib.new("sha256", elementTo)
            elementTo_digest = elementTo_sha256.digest()
            elementTo_base = base64.b64encode(elementTo_digest)
            elementTo_base = elementTo_base.decode()
            return elementTo_base
            
        except Exception as e:
            _logger.error(f"Error generando digestvalue_to: {str(e)}")
            raise UserError(_("Error generando digest value: %s") % str(e))

    # -------------------------------------------------------------------------
    # MÉTODOS DE ENVÍO A DIAN (de ambos archivos)
    # -------------------------------------------------------------------------

    def _send_to_dian_service(self, signed_xml, dian_constants):
        """Envía el XML firmado a DIAN"""
        # Comprimir XML
        zip_content = self._create_zip_content(signed_xml, dian_constants)
        
        # Determinar servicio según ambiente
        if not self.company_id.production:
            return self._send_test_set_async(zip_content, dian_constants)
        else:
            return self._send_bill_sync(zip_content, dian_constants)

    def _send_test_set_async(self, zip_content, dian_constants):
        """Envío asíncrono para ambiente de pruebas"""
        response = xml_utils._build_and_send_request(
            self,
            payload={
                'file_name': dian_constants['FileNameZIP'],
                'content_file': base64.b64encode(zip_content).decode(),
                'test_set_id': self.company_id.identificador_set_pruebas,
                'soap_body_template': "l10n_co_e_invoice.send_test_set_async",
            },
            service="SendTestSetAsync",
            company=self.company_id,
        )
        
        if response['status_code'] == 200:
            root = etree.fromstring(response['response'])
            zip_key = root.findtext('.//{*}ZipKey')
            
            return {
                'status': 'success',
                'zip_key': zip_key,
                'response': response['response'],
                'status_code': response['status_code']
            }
        else:
            return {
                'status': 'error',
                'response': response.get('response', ''),
                'status_code': response.get('status_code', 0)
            }

    def _send_bill_sync(self, zip_content, dian_constants):
        """Envío síncrono para producción"""
        response = xml_utils._build_and_send_request(
            self,
            payload={
                'file_name': dian_constants['FileNameZIP'],
                'content_file': base64.b64encode(zip_content).decode(),
                'soap_body_template': "l10n_co_e_invoice.send_bill_sync",
            },
            service="SendBillSync",
            company=self.company_id,
        )
        
        if response['status_code'] == 200:
            return self._parse_sync_response(response['response'])
        else:
            return {
                'status': 'error',
                'response': response.get('response', ''),
                'status_code': response.get('status_code', 0)
            }

    def _parse_sync_response(self, response_xml):
        """Parsea la respuesta síncrona de DIAN"""
        try:
            root = etree.fromstring(response_xml)
            namespaces = {
                's': 'http://www.w3.org/2003/05/soap-envelope',
                'b': 'http://schemas.datacontract.org/2004/07/DianResponse',
                'c': 'http://schemas.microsoft.com/2003/10/Serialization/Arrays'
            }
            
            # Extraer datos
            status_code = root.findtext('.//b:StatusCode', namespaces=namespaces)
            status_desc = root.findtext('.//b:StatusDescription', namespaces=namespaces)
            status_msg = root.findtext('.//b:StatusMessage', namespaces=namespaces)
            is_valid = root.findtext('.//b:IsValid', namespaces=namespaces) == 'true'
            document_key = root.findtext('.//b:XmlDocumentKey', namespaces=namespaces)
            xml_file_name = root.findtext('.//b:XmlFileName', namespaces=namespaces)
            
            # Errores si existen
            errors = []
            error_nodes = root.findall('.//b:ErrorMessage/c:string', namespaces=namespaces)
            for error in error_nodes:
                if error.text:
                    errors.append(error.text)
            
            # Si no hay errores en ErrorMessage, buscar en StatusMessage
            if not errors and status_msg and 'Regla' in status_msg:
                errors.append(status_msg)
            
            # StatusCode 98 = "Documento en proceso": la DIAN recibió el documento y
            # lo valida de forma asíncrona (IsValid llega en false, pero NO es un
            # rechazo). Se marca como 'processing' para poder consultar el estado
            # luego, en vez de tratarlo como error.
            if is_valid:
                sync_status = 'success'
            elif status_code == '98':
                sync_status = 'processing'
            else:
                sync_status = 'error'

            return {
                'status': sync_status,
                'status_code': status_code,
                'status_description': status_desc,
                'status_message': status_msg,
                'is_valid': is_valid,
                'document_key': document_key,
                'xml_file_name': xml_file_name,
                'errors': errors,
                'response': response_xml
            }
            
        except Exception as e:
            _logger.error(f"Error parseando respuesta DIAN: {str(e)}")
            return {
                'status': 'error',
                'errors': [str(e)],
                'response': response_xml
            }

    def _send_dian_request(self, company, doc_send_dian, data_xml_document, dian_constants, data_header_doc, data_constants_document):
        """
        Envía y procesa solicitudes a la DIAN (método del primer archivo)
        """
        self.ensure_one()
        parser = etree.XMLParser(remove_blank_text=True)
        
        # 1. Preparación y firma del XML
        if isinstance(data_xml_document, etree._Element):
            data_xml_document = etree.tostring(data_xml_document, encoding='unicode', method='xml')
            
        template_signature_data_xml = self._template_signature_data_xml()
        data_xml_document = data_xml_document.replace(
            "<ext:ExtensionContent/>",
            "<ext:ExtensionContent></ext:ExtensionContent>",
        )
        
        # 2. Generación de firma
        data_xml_signature = self._generate_signature_complete(
            data_xml_document,
            template_signature_data_xml,
            dian_constants,
            data_constants_document,
        )
        data_xml_signature = etree.tostring(
            etree.XML(data_xml_signature, parser=parser),
            encoding='unicode',
            method='xml'
        )
        data_xml_signature = html.unescape(data_xml_signature)
        
        # 3. Incorporación de firma al documento
        data_xml_document = data_xml_document.replace(
            "<ext:ExtensionContent></ext:ExtensionContent>",
            f"<ext:ExtensionContent>{data_xml_signature}</ext:ExtensionContent>"
        )
        data_xml_document = '<?xml version="1.0" encoding="UTF-8"?>' + data_xml_document
        root = etree.fromstring(data_xml_document.encode('UTF-8'), parser=parser)
        data_xml_document = etree.tostring(root, encoding='unicode', method='xml')
        
        # 4. Creación del attachment del documento
        invoice_attachment = self.env['ir.attachment'].create({
            'name': data_constants_document["FileNameXML"],
            'type': 'binary',
            'datas': base64.b64encode(data_xml_document.encode()),
            'res_model': self._name,
            'res_id': self.id,
        })
        
        # 5. Actualización del documento DIAN
        doc_send_dian.write({
            'dian_code': data_constants_document["InvoiceID"],
            'xml_file_name': data_constants_document["FileNameXML"],
            'xml_document': data_xml_document,
            'zip_file_name': data_constants_document["FileNameZIP"],
            'invoice_id': invoice_attachment.id
        })

        # 6. Envío a DIAN y procesamiento de respuesta
        dian_response = self._send_to_dian(data_xml_document, data_header_doc)
        
        # 7. Parseo de la respuesta
        response_root = etree.fromstring(dian_response['response'])
        namespaces = {
            's': 'http://www.w3.org/2003/05/soap-envelope',
            'b': 'http://schemas.datacontract.org/2004/07/DianResponse',
            'c': 'http://schemas.microsoft.com/2003/10/Serialization/Arrays'
        }
        
        # 8. Extracción de datos relevantes
        result = self._extract_dian_response_data(response_root, namespaces)
        
        if not result['base64_content']:
            return self._handle_invalid_response(doc_send_dian, dian_response['status_code'])
            
        # 9. Creación del attachment de respuesta
        response_attachment = self._create_response_attachment(
            doc_send_dian, 
            result['base64_content'], 
            result['file_name']
        )
        
        # 10. Actualización inicial del documento con la respuesta
        doc_send_dian.write({
            'response_id': response_attachment.id,
            'xml_response_dian': result['decoded_content']
        })

        # 11. Procesamiento de la respuesta según el caso
        return self._process_dian_response_result(
            doc_send_dian,
            response_root,
            result,
            data_header_doc
        )

    def _extract_dian_response_data(self, response_root, namespaces):
        """Extrae los datos relevantes de la respuesta DIAN."""
        return {
            'base64_content': response_root.xpath('//b:XmlBase64Bytes', namespaces=namespaces)[0].text if response_root.xpath('//b:XmlBase64Bytes', namespaces=namespaces) else None,
            'document_key': response_root.xpath('//b:XmlDocumentKey', namespaces=namespaces)[0].text if response_root.xpath('//b:XmlDocumentKey', namespaces=namespaces) else '',
            'file_name': response_root.xpath('//b:XmlFileName', namespaces=namespaces)[0].text if response_root.xpath('//b:XmlFileName', namespaces=namespaces) else 'DIAN_Response',
            'error_messages': [error.text for error in response_root.xpath('//b:ErrorMessage/c:string', namespaces=namespaces)],
            'status_code': response_root.xpath('//b:StatusCode', namespaces=namespaces)[0].text if response_root.xpath('//b:StatusCode', namespaces=namespaces) else '',
            'status_description': response_root.xpath('//b:StatusDescription', namespaces=namespaces)[0].text if response_root.xpath('//b:StatusDescription', namespaces=namespaces) else '',
            'status_message': response_root.xpath('//b:StatusMessage', namespaces=namespaces)[0].text if response_root.xpath('//b:StatusMessage', namespaces=namespaces) else '',
            'is_valid': response_root.findtext('.//{*}IsValid') == 'true',
            'decoded_content': base64.b64decode(response_root.xpath('//b:XmlBase64Bytes', namespaces=namespaces)[0].text) if response_root.xpath('//b:XmlBase64Bytes', namespaces=namespaces) else None
        }

    def _create_response_attachment(self, doc_send_dian, base64_content, file_name):
        """Crea el attachment para la respuesta DIAN."""
        if not file_name.lower().endswith('.xml'):
            file_name += '.xml'
        
        return self.env['ir.attachment'].create({
            'name': file_name,
            'type': 'binary',
            'datas': base64.b64encode(base64.b64decode(base64_content)),
            'res_model': doc_send_dian._name,
            'res_id': doc_send_dian.id,
        })

    def _process_dian_response_result(self, doc_send_dian, response_root, result, data_header_doc):
        """Procesa el resultado de la respuesta DIAN según diferentes casos."""
        
        # Caso 1: Documento procesado anteriormente
        if any('Regla: 90' in error and 'Documento procesado anteriormente' in error 
            for error in result['error_messages']):
            message_html = Markup(f'''
                <p>
                <strong>Estado:</strong> {result['status_description']}</p>
                <p>
                <strong>Errores:</strong>
                </p>
                <ul>
                <li>{result['error_messages'][0]}</li>
                </ul>''')
            
            self.write({
                'cufe': result['document_key'],
                'state': 'exitoso',
                'message_json': message_html
            })
            
            if hasattr(self, '_action_get__xml'):
               return self._action_get__xml(result['file_name'], result['document_key'])
            
            doc_send_dian._process_dian_response(response_root=response_root, doc=data_header_doc)
            
            return True
        
        # Caso 2: Documento rechazado
        if not result['is_valid']:
            error_list = ''.join([f'<li>{html_escape(error)}</li>' for error in result['error_messages']])
            message_html = Markup(f'''
                <p>
                <strong>Estado:</strong> {result['status_description']}</p>
                <p>
                <strong>Errores:</strong>
                </p>
                <ul>
                {error_list}
                </ul>''')
                
            doc_send_dian.write({
                'state': 'rechazado',
                'message_json': message_html
            })
            return True
        
        # Caso 3: Documento procesado exitosamente
        message_html = Markup(f'''
            <p>
            <strong>Estado:</strong> {result['status_description']}</p>
            <p>
            <strong>CUFE:</strong> {result['document_key']}</p>
        ''')
        
        doc_send_dian.write({
            'state': 'exitoso',
            'message_json': message_html,
            'cufe': result['document_key']
        })
        
        doc_send_dian._process_dian_response(response_root=response_root, doc=data_header_doc)
        return True

    def _handle_invalid_response(self, doc_send_dian, status_code):
        """Maneja respuestas inválidas de la DIAN."""
        message_html = Markup(f'''
            <p>
            <strong>Estado:</strong> Error en la respuesta DIAN</p>
            <p>
            <strong>Código de estado:</strong> {status_code}</p>
        ''')
        
        return doc_send_dian.write({
            'state': 'error',
            'message_json': message_html
        })

    def _handle_processing_error(self, doc_send_dian, error):
        """Maneja errores durante el procesamiento."""
        error_html = Markup(f'''
            <p>
            <strong>Estado:</strong> Error en el procesamiento</p>
            <p>
            <strong>Detalle:</strong> {html_escape(str(error))}</p>
        ''')
        
        doc_send_dian.write({
            'state': 'error',
            'message_json': error_html
        })
        return False

    # -------------------------------------------------------------------------
    # PROCESAMIENTO DE RESPUESTA
    # -------------------------------------------------------------------------
    
    def _process_dian_response(self, response, dian_constants):
        """Procesa la respuesta de DIAN y actualiza el documento"""
        
        if response['status'] == 'error' and response.get('errors'):
            regla_90_error = any(
                'Regla: 90' in error and 'Documento procesado anteriormente' in error 
                for error in response.get('errors', [])
            )
            
            if regla_90_error:
                _logger.info(f"Documento {dian_constants['InvoiceID']} ya procesado anteriormente en DIAN")
                
                document_key = None
                for error in response.get('errors', []):
                    if 'CUFE' in error or 'UUID' in error:
                        cufe_match = re.search(r'[0-9a-fA-F]{96}', error)
                        if cufe_match:
                            document_key = cufe_match.group(0)
                            break
                
                if not document_key and dian_constants.get('cufe'):
                    document_key = dian_constants['cufe']
                
                if document_key:
                    self.cufe = document_key
                    if hasattr(self, 'diancode_id') and self.diancode_id:
                        self.diancode_id.cufe = document_key
                    dian_constants["cufe"] = document_key
                    try:
                        result = self._action_get_xml(cufe=document_key)
                        if result.get('success'):
                            self.state_dian_document = 'exitoso'
                            self.response_message_dian = 'Documento procesado anteriormente. XML recuperado exitosamente.'
                            
                            self._format_regla_90_message(response, document_key)
                            
                            if response.get('response'):
                                self._save_response_attachment(response['response'], dian_constants)
                            
                            # El envío de email se maneja de forma centralizada al cambiar a 'exitoso'
                            
                            return
                    except Exception as e:
                        _logger.warning(f"No se pudo recuperar XML para documento procesado: {str(e)}")
                
                self.state_dian_document = 'exitoso'
                self.response_message_dian = 'Documento procesado anteriormente en DIAN'
                self._format_regla_90_message(response, document_key)
                
                if response.get('response'):
                    self._save_response_attachment(response['response'], dian_constants)
                
                # El envío de email se maneja de forma centralizada al cambiar a 'exitoso'
                
                return
        
        if response['status'] == 'success':
            if self.company_id.production:
                if response.get('is_valid'):
                    self.state_dian_document = 'exitoso'
                    self.cufe = response.get('document_key', '')
                    self.response_message_dian = response.get('status_description', 'Documento procesado exitosamente')
                    
                    # El envío de email se maneja de forma centralizada al cambiar a 'exitoso'
                else:
                    self.state_dian_document = 'rechazado'
                    self.response_message_dian = '\n'.join(response.get('errors', ['Documento rechazado']))
            else:
                # Modo PRUEBA / HABILITACIÓN
                self.state_dian_document = 'por_validar'
                self.ZipKey = response.get('zip_key', '')

                if response.get('response'):
                    self._save_response_attachment(response['response'], dian_constants)

                # Mensaje mejorado para modo prueba (establecer AL FINAL para no ser sobrescrito)
                mensaje = f"""
                <div style="padding: 10px; background-color: #fff3cd; border-left: 4px solid #ffc107;">
                    <h4 style="margin-top: 0; color: #856404;">
                        <i class="fa fa-info-circle"></i> Documento Enviado en Modo PRUEBA/HABILITACIÓN
                    </h4>
                    <p><strong>Estado:</strong> Pendiente de Validación por DIAN</p>
                    <p><strong>Código de Seguimiento:</strong> {self.ZipKey}</p>
                    <hr style="border-color: #ffc107;">
                    <p style="margin-bottom: 5px;">
                        <i class="fa fa-lightbulb-o"></i> <strong>¿Qué hacer ahora?</strong>
                    </p>
                    <ul style="margin-top: 5px;">
                        <li>El documento fue enviado correctamente al servidor DIAN en modo PRUEBA/HABILITACIÓN</li>
                        <li>La validación puede tardar algunos minutos</li>
                        <li>Use el botón <strong>"Recuperar Estado DIAN"</strong> para consultar el resultado de la validación</li>
                        <li>El botón aparecerá automáticamente en el encabezado de la factura</li>
                    </ul>
                </div>
                """
                self.response_message_dian = Markup(mensaje)
                return  # Retornar aquí para evitar que _format_response_message sobrescriba el mensaje
        elif response['status'] == 'processing':
            # StatusCode 98: documento en proceso en DIAN (validación asíncrona).
            # Queda 'por_validar' para que aparezca el botón "Recuperar Estado" y
            # el cron pueda consultar el resultado final. NO es un rechazo.
            self.state_dian_document = 'por_validar'
            if response.get('document_key'):
                self.cufe = response.get('document_key')
        else:
            self.state_dian_document = 'error'
            self.response_message_dian = '\n'.join(response.get('errors', ['Error en el envío']))

        if response.get('response'):
            self._save_response_attachment(response['response'], dian_constants)

        self._format_response_message(response)

    def _format_response_message(self, response):
        """Formatea el mensaje de respuesta en HTML"""
        if response['status'] == 'success':
            style = 'alert-success'
            title = 'Envío Exitoso'
        elif response['status'] == 'processing':
            style = 'alert-warning'
            title = 'Documento en proceso en DIAN'
        else:
            style = 'alert-danger'
            title = 'Error en el Envío'
        
        errors_html = ''
        if response.get('errors'):
            errors_html = '<ul>' + ''.join([f'<li>{e}</li>' for e in response['errors']]) + '</ul>'
        
        html_message = f'''
        <div class="alert {style}">
            <h4>{title}</h4>
            <p><strong>Estado:</strong> {response.get('status_description', 'N/A')}</p>
            {errors_html}
            {f"<p><strong>CUFE:</strong> {response.get('document_key', '')}</p>" if response.get('document_key') else ''}
        </div>
        '''
        
        self.response_message_dian = Markup(html_message)

    def _format_regla_90_message(self, response, document_key=None):
        """Formatea el mensaje HTML para error Regla 90"""
        errors_list = response.get('errors', [])
        error_90 = next((e for e in errors_list if 'Regla: 90' in e), errors_list[0] if errors_list else '')
        
        html_message = Markup(f'''
        <div class="alert alert-warning">
            <h4>Documento Procesado Anteriormente</h4>
            <p><strong>Estado:</strong> Exitoso (Regla 90)</p>
            <p><strong>Mensaje DIAN:</strong> {error_90}</p>
            {f'<p><strong>CUFE:</strong> {document_key}</p>' if document_key else ''}
            <p><em>Este documento ya fue procesado anteriormente en DIAN y se considera válido.</em></p>
        </div>
        ''')
        
        self.response_message_dian = html_message

    # -------------------------------------------------------------------------
    # MÉTODOS DE VALIDACIÓN Y GETSTATUS (del primer archivo)
    # -------------------------------------------------------------------------

    def action_GetStatus(self):
        """Acción para obtener estado"""
        return True

    def _generate_GetStatus_send_xml(self, template, identifier, Created, Expires, certificate, identifierSecurityToken, identifierTo, trackId):
        """Genera XML para GetStatus"""
        return template % {
            'identifier': identifier,
            'Created': Created,
            'Expires': Expires,
            'Certificate': certificate,
            'identifierSecurityToken': identifierSecurityToken,
            'identifierTo': identifierTo,
            'trackId': trackId
        }

    # -------------------------------------------------------------------------
    # MÉTODOS DE ATTACHED DOCUMENT (del primer archivo)
    # -------------------------------------------------------------------------

    def get_application_response(self, xml_response_dian):
        """Obtiene la respuesta de aplicación"""
        response_dict = xmltodict.parse(xml_response_dian)
        if "s:Envelope" in response_dict:
            if "s:Body" in response_dict["s:Envelope"]:
                if "GetStatusZipResponse" in response_dict["s:Envelope"]["s:Body"]:
                    result = response_dict["s:Envelope"]["s:Body"]["GetStatusZipResponse"]["GetStatusZipResult"]
                    if "b:XmlBase64Bytes" in result:
                        xml_base64 = result["b:XmlBase64Bytes"]
                        return base64.b64decode(xml_base64)
        return None

    def generate_attached_document(self, dian_constants, xml_document, application_response, data_header_doc, cufe):
        """Genera el documento adjunto"""
        # Implementación del attached document
        pass

    def enviar_email_attached_document_xml(
        self, xml_response_dian, dian_document, dian_constants, data_header_doc
    ):
        """Envía email con documento adjunto XML"""
        application_response = self.get_application_response(xml_response_dian)
        xml_attached_document = self.generate_attached_document(
            dian_constants,
            dian_document.xml_document,
            application_response=application_response,
            data_header_doc=data_header_doc,
            cufe=dian_document.cufe,
        )

        xml_file_name = (
            "ad%s" % (dian_document.xml_file_name[6:] if dian_document.xml_file_name else "000000.xml")
        )
        return unidecode(xml_attached_document), xml_file_name

    def enviar_email_attached_document_fe_xml(
        self, xml_response_dian, dian_document, dian_constants, data_header_doc
    ):
        """Envía email con documento adjunto FE XML"""
        xml_attached_document = self.generate_attached_document(
            dian_constants,
            dian_document.xml_document,
            application_response=xml_response_dian,
            data_header_doc=data_header_doc,
            cufe=dian_document.cufe,
        )

        xml_file_name = (
            "ad%s" % (dian_document.xml_file_name[6:] if dian_document.xml_file_name else "000000.xml")
        )
        return unidecode(xml_attached_document), xml_file_name


    def enviar_email(self, invoice):
        template = self.env.ref("l10n_co_e_invoice.email_template_edi_invoice_dian", False)
        if template:
            self.action_send_dian_direct()
            invoice.message_post(
                body=_("Email enviado con documentos electrónicos adjuntos"),
                subject=_("Envío de documentos electrónicos")
            )
        else:
            raise UserError(
                _(
                    "No existe la plantilla de correo email_template_edi_invoice_dian para el email"
                )
            )
        return True

    # -------------------------------------------------------------------------
    # MÉTODOS AUXILIARES Y UTILITARIOS (del primer archivo)
    # -------------------------------------------------------------------------

    def _get_identificador_set_pruebas(self):
        """Obtiene el identificador del set de pruebas"""
        company = (
            self.env["res.company"].sudo().search([("id", "=", self.env.company.id)])
        )
        return company.identificador_set_pruebas

    def send_pending_dian(self, document_id, document_type=None, invoice=None):
        """
        Procesa el documento para envío a DIAN
        """
        self.ensure_one()
        if document_type in ("d","c"):
            self._get_docs_send_dian(document_type,document_id)
        constants = self._generate_dian_constants(invoice, invoice.move_type, False)
        xml_content = self.env['dian.xml.builder'].generate_xml(invoice, constants)
        self.write({
            'QR_code': constants.get('qr'),
            'qr_data': constants.get('qr_code'),
            'cufe': constants.get('cufe'),
        })
        if isinstance(xml_content, str):
            xml_content = xml_content.encode('utf-8')
        parser = etree.XMLParser(remove_blank_text=True)
        xml_tree = etree.fromstring(xml_content, parser=parser)
        return self._send_dian_request(
            company=invoice.company_id,
            doc_send_dian=self,
            data_xml_document=xml_tree,
            dian_constants=constants,
            data_header_doc=invoice,
            data_constants_document=constants
        )

    def _get_docs_send_dian(self, document_type, document_id):
        """Obtiene documentos para envío DIAN"""
        if document_type == "c":
            by_validate_credit_notes = self.env["dian.document"].search([("id", "=", document_id.id), ("document_type", "=", document_type)])
            cn_with_validated_invoices_ids = []
            for by_validate_cn in by_validate_credit_notes:
                invoice_validated = self.env["account.move"].search([("name", "=", by_validate_cn.document_id.reversed_entry_id.name), ("move_type", "in", ["out_invoice", "in_invoice"]), ("state_dian_document", "=", "exitoso")])
                if invoice_validated:
                    cn_with_validated_invoices_ids.append(by_validate_cn.id)
                else:
                    cn_with_validated_invoices_ids.append(by_validate_cn.id)
                    if not self.document_id.cufe_cuds_other_system and not self.document_id.document_without_reference:
                        raise UserError(_("La factura a la que se le va a aplicar la nota de crédito, no ha sido enviada o aceptada por la DIAN"))
            return self.env["dian.document"].browse(cn_with_validated_invoices_ids)
        elif document_type == "d":
            by_validate_debit_notes = self.env["dian.document"].search([("id", "=", document_id.id), ("document_type", "=", document_type)])
            cn_with_validated_invoices_ids = []
            for by_validate_cn in by_validate_debit_notes:
                invoice_validated = self.env["account.move"].search([("name", "=", by_validate_cn.document_id.debit_origin_id.name), ("move_type", "in", ["out_invoice", "out_refund"]), ("company_id", "=", self.env.company.id), ("state_dian_document", "=", "exitoso")])
                if invoice_validated:
                    cn_with_validated_invoices_ids.append(by_validate_cn.id)
                else:
                    raise UserError(_("La factura a la que se le va a aplicar la nota de débito, no ha sido enviada o aceptada por la DIAN"))
            return self.env["dian.document"].browse(cn_with_validated_invoices_ids)
        return True

    def _get_software_identification_code(self):
        """Obtiene el código de identificación del software"""
        company = self.env.company
        return company.software_identification_code

    def _get_software_pin(self):
        """Obtiene el PIN del software"""
        company = self.env.company
        return company.software_pin

    def _get_password_environment(self):
        """Obtiene la contraseña del ambiente"""
        company = self.env.company
        return company.password_environment

    def _get_profile_id(self, data_header_doc):
        """Obtiene el Profile ID según el tipo de documento"""
        if data_header_doc.move_type == "out_invoice" and not data_header_doc.is_debit_note:
            return "DIAN 2.1: Factura Electrónica de Venta"
        elif data_header_doc.is_debit_note:
            return "DIAN 2.1: Nota Débito de Factura Electrónica de Venta"
        elif data_header_doc.move_type == 'out_refund':
            return "DIAN 2.1: Nota Crédito de Factura Electrónica de Venta"
        elif data_header_doc.move_type == 'in_invoice' and data_header_doc.is_debit_note == False:
            return "DIAN 2.1: documento soporte en adquisiciones efectuadas a no obligados a facturar."
        elif data_header_doc.move_type == 'in_invoice' and data_header_doc.is_debit_note or data_header_doc.debit_origin_id:
            raise UserError('Los documentos Soporte No tiene Nota Debito Habilitadas para su emisión a la DIAN, Por Favor Emitir Otro documento Soporte')
        elif data_header_doc.move_type == 'in_refund':
            return "DIAN 2.1: Nota de ajuste al documento soporte en adquisiciones efectuadas a sujetos no obligados a expedir factura o documento equivalente"

    def _get_customization_id(self, data_header_doc):
        """Obtiene el Customization ID"""
        if data_header_doc.move_type == "out_refund":
            return "22" if data_header_doc.document_without_reference else "20"
        elif data_header_doc.is_debit_note:
            return "32" if data_header_doc.document_without_reference else "30"
        elif data_header_doc.move_type in ('in_invoice', 'in_refund'):
            if data_header_doc.partner_id.type_residence == "si":
                return '10'
            elif self.document_id.partner_id.type_residence == "no":
                return '11'
            else:
                raise ValidationError('El proveedor {0} no tiene la informacion de residencia en su formulario'.format(self.document_id.partner_id.name))
        return data_header_doc.fe_operation_type

    def _get_url_qr_code(self, company):
        """Obtiene la URL del código QR"""
        if company.production:
            return 'https://catalogo-vpfe.dian.gov.co/document/searchqr?documentkey'
        else:
            return 'https://catalogo-vpfe-hab.dian.gov.co/document/searchqr?documentkey'

    def return_number_document_type(self, document_type):
        """Retorna el número del tipo de documento"""
        document_type_map = {
            "31": "31",
            "rut": "31",
            "national_citizen_id": "13",
            "civil_registration": "11",
            "id_card": "12",
            "21": "21",
            "foreign_id_card": "22",
            "passport": "41",
            "43": "43",
            'id_document': '',
            'external_id': '50',
            'residence_document': '47',
            'PEP': '47',
            'niup_id': '91',
            'foreign_colombian_card': '21',
            'foreign_resident_card': '22',
            'diplomatic_card': '',
            'PPT': '48',
            'vat': '50',
        }
        return str(document_type_map.get(document_type, "13"))

    def _generate_filename_data(self, data_resolution, NitSinDV, data_header_doc):
        """Genera los nombres de archivos"""
        return {
            "FileNameXML": self._generate_xml_filename(data_resolution, NitSinDV, data_header_doc.move_type, data_header_doc.debit_origin_id),
            "FileNameZIP": self._generate_zip_filename(data_resolution, NitSinDV, data_header_doc.move_type, data_header_doc.debit_origin_id),
        }

    def _generate_resolution_data(self, data_resolution, data_header_doc,document_type,dian_constants):
        """Genera los datos de resolución"""
        return {
            "InvoiceAuthorization": data_resolution["InvoiceAuthorization"],
            "StartDate": data_resolution["StartDate"],
            "EndDate": data_resolution["EndDate"],
            "Prefix": self._get_prefix(data_resolution, data_header_doc),
            "From": data_resolution["From"],
            "To": data_resolution["To"],
            "InvoiceID": data_resolution["InvoiceID"],
            "ContingencyID": data_resolution["ContingencyID"] if document_type == "contingency" else " ",
            "Nonce": self._generate_nonce(data_resolution["InvoiceID"], dian_constants["SeedCode"]),
            "TechnicalKey": data_resolution["TechnicalKey"],
        }

    def _generate_payment_data(self, data_header_doc):
        """Genera los datos de pago"""
        payment_data = {
            "PaymentMeansID": "1",
            "PaymentDueDate": data_header_doc.invoice_date,
            "PaymentMeansCode": data_header_doc.method_payment_id.code or "1",
        }
        if data_header_doc.payment_format == 'Credito':
            payment_data["PaymentMeansID"] = "2"
            payment_data["PaymentDueDate"] = data_header_doc.invoice_date_due

        if data_header_doc.invoice_payment_term_id.line_ids:
            for line_term_pago in data_header_doc.invoice_payment_term_id.line_ids:
                if line_term_pago.nb_days == 0:
                    payment_data["PaymentMeansID"] = "1"
                    payment_data["PaymentDueDate"] = data_header_doc.invoice_date
                else:
                    payment_data["PaymentMeansID"] = "2"
                    payment_data["PaymentDueDate"] = data_header_doc.invoice_date_due

        return payment_data

    def _generate_credit_debit_data(self, data_header_doc,in_contingency_4):
        """Genera los datos de crédito/débito"""
        credit_debit_data = {
            "credit_note_reason": data_header_doc.reversed_entry_id.narration or data_header_doc.ref,
            "billing_reference_id": data_header_doc.reversed_entry_id.name,
            "ResponseCodeCreditNote": data_header_doc.concepto_credit_note,
            "ResponseCodeDebitNote": data_header_doc.concept_debit_note,
            "DescriptionDebitCreditNote": dict(data_header_doc._fields['concepto_credit_note'].selection).get(data_header_doc.concepto_credit_note),
        }

        if self._get_doctype(data_header_doc.move_type, data_header_doc.debit_origin_id, in_contingency_4) in ("91", "92", "95"):
            invoice_cancel = data_header_doc.reversed_entry_id
            if data_header_doc.debit_origin_id:
                invoice_cancel = data_header_doc.debit_origin_id
            credit_debit_data["InvoiceReferenceDate"] = ''
            if data_header_doc.document_without_reference:
                credit_debit_data["InvoiceReferenceDate"] = data_header_doc.invoice_date

            if invoice_cancel and invoice_cancel.state_dian_document == 'exitoso':
                dian_document_cancel = self.env["dian.document"].search([
                    ("state", "=", "exitoso"),
                    ("document_type", "in", ["f", "c"]),
                    ("id", "=", invoice_cancel.diancode_id.id),
                ])
                if dian_document_cancel:
                    credit_debit_data["InvoiceReferenceID"] = dian_document_cancel.dian_code
                    credit_debit_data["InvoiceReferenceUUID"] = dian_document_cancel.cufe
                    credit_debit_data["InvoiceReferenceDate"] = invoice_cancel.invoice_date

            if (
                self.document_id.document_from_other_system
                and self.document_id.cufe_cuds_other_system
                and self.document_id.date_from_other_system
            ):
                credit_debit_data["InvoiceReferenceID"] = self.document_id.document_from_other_system
                credit_debit_data["InvoiceReferenceUUID"] = self.document_id.cufe_cuds_other_system
                credit_debit_data["InvoiceReferenceDate"] = str(self.document_id.date_from_other_system)

        return credit_debit_data

    def _generate_contingency_data(self, data_header_doc,in_contingency_4):
        """Genera los datos de contingencia"""
        contingency_data = {}

        if self._get_doctype(data_header_doc.move_type, data_header_doc.debit_origin_id, in_contingency_4)  == ("03"):
            contingency_data["ContingencyReferenceID"] = data_header_doc.contingency_invoice_number
            contingency_data["ContingencyIssueDate"] = data_header_doc.invoice_date
            contingency_data["ContingencyDocumentTypeCode"] = "FTC"

        return contingency_data

    def _generate_identifier_data(self):
        """Genera los datos de identificadores"""
        return {
            "identifier": uuid.uuid4(),
            "identifierkeyinfo": uuid.uuid4(),
        }

    def _get_prefix(self, data_resolution, data_header_doc):
        """Obtiene el prefijo según el tipo de documento"""
        prefix = data_resolution["Prefix"]
        if data_header_doc.move_type != "out_invoice" and data_header_doc.move_type != "in_invoice":
            prefix = data_resolution["PrefixNC"]
        if data_header_doc.is_debit_note:
            prefix = data_resolution["PrefixND"]
        return prefix

    def _get_calculation_rate(self, data_header_doc):
        """Obtiene la tasa de cálculo"""
        if data_header_doc.company_id.currency_id == data_header_doc.currency_id:
            return 1.00
        else:
            calculation_rate = self._get_rate_date(
                data_header_doc.company_id.id,
                data_header_doc.currency_id.id,
                data_header_doc.invoice_date,
            )
            return self._complements_second_decimal_total(calculation_rate)

    def _replace_character_especial(self, text):
        """Reemplaza caracteres especiales"""
        if text:
            for char, replacement in [('&', '&amp;'), ('<', '&lt;'), ('>', '&gt;'), ('"', '&quot;'), ("'", '&apos;')]:
                text = text.replace(char, replacement)
        return text

    def _get_partner_fiscal_responsability_code(self, partner_id):
        """Obtiene el código de responsabilidad fiscal del partner"""
        partner = self.env["res.partner"].browse(partner_id)
        return ";".join(partner.dian_obligation_type_ids.mapped('dian_code'))

    def _get_doctype(self, doctype, is_debit_note, in_contingency_4):
        """Obtiene el tipo de documento DIAN"""
        docdian = False
        if doctype == "out_invoice" and not is_debit_note:  # Es una factura
            if (
                not self.contingency_3
                and not self.contingency_4
                and not in_contingency_4
            ):
                docdian = "01"
            elif self.contingency_3 and not in_contingency_4:
                docdian = "03"
            elif self.contingency_4 and not in_contingency_4:
                docdian = "04"
            elif in_contingency_4:
                docdian = "04"
        if doctype == "out_refund":
            docdian = "91"
        if doctype == "out_invoice" and is_debit_note:
            docdian = "92"
        return docdian

    def _get_lines_invoice(self, invoice_id):
        """Obtiene el número de líneas de la factura"""
        lines = self.env["account.move.line"].search_count([
                ("move_id", "=", invoice_id),
                ("product_id", "!=", None),
                ("product_id.enable_charges", "!=", True),
                ("display_type", "=", 'product'),
                ("price_subtotal", "!=", 0.00),])
        return lines

    def _get_time(self):
        """Obtiene la hora actual"""
        fmt = "%H:%M:%S"
        now_utc = datetime.now(timezone("UTC"))
        now_time = now_utc.strftime(fmt)
        return now_time

    def _get_time_colombia(self):
        """Obtiene la hora de Colombia"""
        fmt = "%H:%M:%S-05:00"
        now_utc = datetime.now(timezone("UTC"))
        now_time = now_utc.strftime(fmt)
        return now_time

    def _generate_signature_signingtime(self):
        """Genera el tiempo de firma"""
        fmt = "%Y-%m-%dT%H:%M:%S"
        now_utc = datetime.now(timezone("UTC"))
        now_bogota = now_utc
        data_xml_SigningTime = now_bogota.strftime(fmt) + "-05:00"
        return data_xml_SigningTime

    def _generate_xml_filename(self, data_resolution, NitSinDV, doctype, is_debit_note):
        """Genera el nombre del archivo XML"""
        if doctype == "out_invoice" and not is_debit_note:
            docdian = "fv"
        elif doctype == "out_refund":
            docdian = "nc"
        elif doctype == "out_invoice" and is_debit_note:
            docdian = "nd"

        len_prefix = len(data_resolution["Prefix"])
        len_invoice = len(data_resolution["InvoiceID"])
        dian_code_int = int(data_resolution["InvoiceID"][len_prefix:len_invoice])
        dian_code_hex = self.IntToHex(dian_code_int)
        dian_code_hex.zfill(10)
        file_name_xml = docdian + NitSinDV.zfill(10) + dian_code_hex.zfill(10) + ".xml"
        return file_name_xml

    def IntToHex(self, dian_code_int):
        """Convierte entero a hexadecimal"""
        dian_code_hex = "%02x" % dian_code_int
        return dian_code_hex

    def _generate_zip_filename(self, data_resolution, NitSinDV, doctype, is_debit_note):
        """Genera el nombre del archivo ZIP"""
        if doctype == "out_invoice" and not is_debit_note:
            docdian = "fv"
        elif doctype == "out_refund":
            docdian = "nc"
        elif doctype == "out_invoice" and is_debit_note:
            docdian = "nd"
        secuenciador = data_resolution["InvoiceID"]
        dian_code_int = int(re.sub(r"\D", "", secuenciador))
        dian_code_hex = self.IntToHex(dian_code_int)
        dian_code_hex.zfill(10)
        file_name_zip = docdian + NitSinDV.zfill(10) + dian_code_hex.zfill(10) + ".zip"
        return file_name_zip

    def _generate_zip_content(
        self, FileNameXML, FileNameZIP, data_xml_document, document_repository
    ):
        """Genera el contenido ZIP"""
        # Almacena archivo XML
        xml_file = document_repository + "/" + FileNameXML
        f = open(xml_file, "w")
        f.write(str(data_xml_document))
        f.close()
        # Comprime archivo XML
        zip_file = document_repository + "/" + FileNameZIP
        zf = zipfile.ZipFile(zip_file, mode="w")
        try:
            zf.write(xml_file, compress_type=compression)
        finally:
            zf.close()
        # Obtiene datos comprimidos
        data_xml = zip_file
        data_xml = open(data_xml, "rb")
        data_xml = data_xml.read()
        contenido_data_xml_b64 = base64.b64encode(data_xml)
        contenido_data_xml_b64 = contenido_data_xml_b64.decode()
        return contenido_data_xml_b64

    @staticmethod
    def _generate_zip_multiple_files(files, zip_file_name):
        """
        Genera un ZIP con múltiples archivos
        @param: files: tuple((file_name, file_data))
        @return: base64 zip file
        """
        with zipfile.ZipFile(f"/tmp/{zip_file_name}", mode="w") as zf:
            for name, data in files:
                zf.writestr(name, data)
        with open(f"/tmp/{zip_file_name}", "rb") as zfile:
            data = zfile.read()
            return base64.b64encode(data)

    def _generate_nonce(self, InvoiceID, seed_code):
        """Genera el nonce"""
        nonce = randint(1, seed_code)
        nonce = base64.b64encode((InvoiceID + str(nonce)).encode())
        nonce = nonce.decode()
        return nonce

    def _generate_software_security_code(
        self, software_identification_code, software_pin, NroDocumento
    ):
        """Genera el código de seguridad del software"""
        software_security_code = hashlib.sha384(
            (software_identification_code + software_pin + NroDocumento).encode()
        )
        software_security_code = software_security_code.hexdigest()
        return software_security_code

    def _generate_datetime_timestamp(self):
        """Genera el timestamp de fecha y hora"""
        fmt = "%Y-%m-%dT%H:%M:%S.%f"
        now_bogota = datetime.now(timezone("UTC"))
        Created = now_bogota.strftime(fmt)[:-3] + "Z"
        now_bogota = now_bogota + timedelta(minutes=5)
        Expires = now_bogota.strftime(fmt)[:-3] + "Z"
        timestamp = {"Created": Created, "Expires": Expires}
        return timestamp

    def _generate_datetime_IssueDate(self):
        """Genera la fecha de emisión"""
        date_invoice_cufe = {}
        fmtSend = "%Y-%m-%dT%H:%M:%S"
        now_utc = datetime.now(timezone("UTC"))
        now_bogota = now_utc
        date_invoice_cufe["IssueDateSend"] = now_bogota.strftime(fmtSend)
        fmtCUFE = "%Y-%m-%d"
        date_invoice_cufe["IssueDateCufe"] = now_bogota.strftime(fmtCUFE)
        fmtInvoice = "%Y-%m-%d"
        date_invoice_cufe["IssueDate"] = now_bogota.strftime(fmtInvoice)
        return date_invoice_cufe

    def _complements_second_decimal(self, amount):
        """Complementa el segundo decimal"""
        amount_dec = round(((amount - int(amount)) * 100.0), 2)
        amount_int = int(amount_dec)
        if amount_int % 10 == 0:
            amount = str(amount) + "0"
        else:
            amount = str(amount)
        return amount

    def count_decimals(self, amount):
        """Cuenta los decimales"""
        if amount:
            return str(amount)[::-1].find(".")
        return amount

    def truncate(self, amount, decimals):
        """Trunca a un número específico de decimales"""
        if amount:
            return math.floor(amount * 10**decimals) / 10**decimals
        else:
            return "0.00"

    def _complements_second_decimal_total(
        self, amount, allow_more_than_two_decimals=False
    ):
        """Complementa el segundo decimal del total"""
        if amount:
            cant_decimals = self.count_decimals(amount)
            if cant_decimals >= 3:
                if allow_more_than_two_decimals:
                    return self.truncate(amount, 3)
                return str("{:.2f}".format(amount))
            return str("{:.2f}".format(amount))
        else:
            return "0.00"

    def _second_decimal_total(self, amount):
        """Formatea a segundo decimal"""
        if amount:
            return str("{:.2f}".format(str(amount)))
        else:
            return 0

    def _cron_validate_accept_email_invoice_dian(self):
        """Cron para validar aceptación de email de factura DIAN"""
        date_current = self._get_datetime()
        date_current = datetime.strptime(date_current, "%Y-%m-%d %H:%M:%S")
        rec_dian_documents = (
            self.env["dian.document"]
            .sudo()
            .search([("state", "=", "exitoso"), ("email_response", "=", "pending")])
        )
        for rec_dian_document in rec_dian_documents:
            if rec_dian_document.date_email_send:
                time_difference = date_current - rec_dian_document.date_email_send
                if time_difference.days > 3:
                    rec_dian_document.date_email_acknowledgment = fields.Datetime.now()
                    rec_dian_document.email_response = "accepted"

    def _get_rate_date(self, company_id, currency_id, date_invoice):
        """Obtiene la tasa de cambio por fecha"""
        Calculationrate = 0.00
        sql = """
        select max(name) as date
          from res_currency_rate
         where company_id = {}
           and currency_id = {}
           and name <= '{}'
         """.format(
            company_id,
            currency_id,
            date_invoice,
        )

        self.sudo().env.cr.execute(sql)
        resultado = self.sudo().env.cr.dictfetchall()
        if resultado[0]["date"] is not None:
            sql = """
            select rate as rate
              from res_currency_rate
             where company_id = {}
               and currency_id = {}
               and name = '{}'
             """.format(
                company_id,
                currency_id,
                resultado[0]["date"],
            )

            self.sudo().env.cr.execute(sql)
            resultado = self.sudo().env.cr.dictfetchall()
            rate = resultado[0]["rate"]
            Calculationrate = 1.00 / rate
        else:
            raise UserError(
                _(
                    "La divisa utilizada en la factura no tiene tasa de cambio registrada"
                )
            )
        return Calculationrate

    def reset_rejected_dian_data(self):
        """Resetea los datos rechazados de DIAN"""
        self.response_message_dian = " "
        self.xml_response_dian = " "
        self.xml_send_query_dian = " "
        self.response_message_dian = " "
        self.xml_document = " "
        self.xml_file_name = " "
        self.zip_file_name = " "
        self.cufe = " "
        self.date_document_dian = " "
        self.write({"state": "por_notificar", "resend": False})

    # -------------------------------------------------------------------------
    # MÉTODOS DEL SEGUNDO ARCHIVO - ATTACHED DOCUMENT
    # -------------------------------------------------------------------------
    
    def _get_attached_document_values(self, original_xml_etree, application_response_etree):
        """Obtiene los valores para generar el documento adjunto"""
        scheme_mapping = {
            'out_invoice': 'CUFE-SHA384',
            'out_refund': 'CUDE-SHA384',
            'in_invoice': 'CUDS-SHA384',
            'in_refund': 'CUDS-SHA384',
        }
        
        return {
            'profile_execution_id': original_xml_etree.findtext('./{*}ProfileExecutionID'),
            'id': original_xml_etree.findtext('./{*}ID'),
            'uuid': self.cufe,
            'uuid_attrs': {
                'schemeName': str(scheme_mapping.get(self.move_type, "CUFE-SHA384")),
            },
            'issue_date': original_xml_etree.findtext('./{*}IssueDate'),
            'issue_time': original_xml_etree.findtext('./{*}IssueTime'),
            'document_type': "Contenedor de Factura Electrónica",
            'parent_document_id': original_xml_etree.findtext('./{*}ID'),
            'parent_document': {
                'id': original_xml_etree.findtext('./{*}ID'),
                'uuid': self.cufe,
                'uuid_attrs': {
                    'schemeName': str(scheme_mapping.get(self.move_type, "CUFE-SHA384")),
                },
                'issue_date': application_response_etree.findtext('./{*}IssueDate'),
                'issue_time': application_response_etree.findtext('./{*}IssueTime'),
                'response_code': application_response_etree.findtext('.//{*}Response/{*}ResponseCode'),
                'validation_date': application_response_etree.findtext('./{*}IssueDate'),
                'validation_time': application_response_etree.findtext('./{*}IssueTime'),
            },
        }
    
    def _get_attached_document(self):
        """Retorna una tupla: (el xml del documento adjunto, mensaje de error)"""
        self.ensure_one()
        
        # Si ya existe el documento adjunto y no se fuerza recreación, devolverlo
        if self.dian_attached_document_id and not self.force_attached_document_recreation:
            return self.dian_attached_document_id.raw, ""
        
        # Llamar a GetStatus para obtener el ApplicationResponse
        status_response = self._get_status()
        if status_response['status_code'] != 200:
            return "", _(
                "Error %(code)s al llamar al servidor DIAN: %(response)s",
                code=status_response['status_code'],
                response=status_response['response'],
            )
        
        status_etree = etree.fromstring(status_response['response'])
        application_response = base64.b64decode(status_etree.findtext(".//{*}XmlBase64Bytes"))
        
        # Obtener el XML original
        original_xml = None
        if self.dian_xml_attachment_id:
            original_xml = base64.b64decode(self.dian_xml_attachment_id.datas)
        else:
            # Si no hay attachment, intentar recuperarlo
            xml_content = self._retrieve_xml_from_dian()
            if xml_content:
                original_xml = xml_content
        
        if not original_xml:
            return "", _("No se pudo obtener el XML original del documento")
        
        original_xml_etree = etree.fromstring(original_xml)
        
        # Renderizar el Documento Adjunto
        vals = self._get_attached_document_values(
            original_xml_etree=original_xml_etree,
            application_response_etree=etree.fromstring(application_response),
        )
        
        attached_document = self.env['ir.qweb']._render('l10n_co_e_invoice.attached_document_template', vals)
        attached_doc_etree = etree.fromstring(attached_document)
        
        supplier_node = original_xml_etree.find('./{*}AccountingSupplierParty//{*}PartyTaxScheme')
        customer_node = original_xml_etree.find('./{*}AccountingCustomerParty//{*}PartyTaxScheme')
        if supplier_node is not None:
            attached_doc_etree.find('./{*}SenderParty').append(supplier_node)
        if customer_node is not None:
            attached_doc_etree.find('./{*}ReceiverParty').append(customer_node)
        
        desc_original = attached_doc_etree.find('./{*}Attachment/{*}ExternalReference/{*}Description')
        if desc_original is not None:
            original_text = original_xml.decode() if isinstance(original_xml, bytes) else original_xml
            desc_original.text = original_text
        
        desc_response = attached_doc_etree.find('./{*}ParentDocumentLineReference//{*}Description')
        if desc_response is not None:
            response_text = application_response.decode() if isinstance(application_response, bytes) else application_response
            desc_response.text = response_text
        
        # Limpiar el XML
        attached_document_xml = etree.tostring(
            cleanup_xml_node(attached_doc_etree), 
            encoding="UTF-8", 
            xml_declaration=True
        )
        
        self._save_attached_document(attached_document_xml)
        
        if self.force_attached_document_recreation:
            self.force_attached_document_recreation = False
        
        return attached_document_xml, ""
    
    def _save_attached_document(self, attached_document_xml):
        """Guarda el documento adjunto como attachment"""
        if isinstance(attached_document_xml, str):
            attached_document_xml = attached_document_xml.encode('utf-8')
        
        vals = {
            'name': f'AD_{self.name}.xml',
            'type': 'binary',
            'datas': base64.b64encode(attached_document_xml),
            'raw': attached_document_xml,
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/xml',
        }
        
        if self.dian_attached_document_id:
            self.dian_attached_document_id.write(vals)
        else:
            self.dian_attached_document_id = self.env['ir.attachment'].create(vals)
    
    def _get_status(self):
        """Obtiene el estado del documento en DIAN"""
        return xml_utils._build_and_send_request(
            self,
            payload={
                'track_id': self.cufe,
                'soap_body_template': "l10n_co_e_invoice.get_status",
            },
            service="GetStatus",
            company=self.company_id,
        )
    
    def action_get_attached_document(self):
        """Acción para obtener manualmente el documento adjunto"""
        self.ensure_one()
        attached_document, error = self._get_attached_document()
        if error:
            raise UserError(error)
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Documento Adjunto'),
            'res_model': 'ir.attachment',
            'res_id': self.dian_attached_document_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # -------------------------------------------------------------------------
    # MÉTODOS DE EMAIL (completos de ambos archivos)
    # -------------------------------------------------------------------------
    
    def _send_dian_email(self):
        """Envía el email con los documentos electrónicos"""
        try:
            self.action_send_dian_direct()
            
            self.message_post(
                body=_("Email enviado con documentos electrónicos adjuntos"),
                subject=_("Envío de documentos electrónicos")
            )
            
            if self.diancode_id:
                self.diancode_id.date_email_send = fields.Datetime.now()
            
            return True
            
        except Exception as e:
            _logger.error(f"Error enviando email DIAN: {str(e)}", exc_info=True)
            return False

    def _send_dian_email_with_attached_document(self, attached_document_xml):
        """Envía el email con los documentos electrónicos incluyendo el attached document"""
        try:
            self.action_send_dian_direct()
            self.message_post(
                body=_("Email enviado con documentos electrónicos adjuntos (incluye Attached Document)"),
                subject=_("Envío de documentos electrónicos")
            )
            self.diancode_id.date_email_send = fields.Datetime.now()
            return True
        except Exception as e:
            _logger.error(f"Error enviando email DIAN con attached document: {str(e)}", exc_info=True)
            return False

    # -------------------------------------------------------------------------
    # MÉTODOS AUXILIARES FINALES
    # -------------------------------------------------------------------------
    
    def _get_or_generate_xml(self, dian_constants):
        """Obtiene o genera el XML"""
        # Si ya tiene CUFE, intentar recuperar de DIAN
        if self.cufe and not hasattr(self, 'xml_text'):
            xml_content = self._retrieve_xml_from_dian()
            if xml_content:
                return xml_content
        
        # Generar nuevo
        return self.generate_dian_xml()
    
    def _retrieve_xml_from_dian(self):
        """
        Recupera XML desde DIAN usando GetXmlByDocumentKey
        Usa el CUFE como track_id para consultar el XML del documento
        """
        if not self.cufe:
            _logger.warning("No se puede recuperar XML de DIAN: No hay CUFE disponible")
            return None

        try:
            response = xml_utils._build_and_send_request(
                self,
                payload={
                    'track_id': self.cufe,
                    'soap_body_template': "l10n_co_e_invoice.get_xml",
                },
                service="GetXmlByDocumentKey",
                company=self.company_id,
            )

            if response['status_code'] == 200:
                root = etree.fromstring(response['response'])
                namespaces = {
                    's': 'http://www.w3.org/2003/05/soap-envelope',
                    'b': 'http://schemas.datacontract.org/2004/07/EventResponse'
                }

                # Extraer código de respuesta
                code = root.xpath('//s:Body//b:Code/text()', namespaces=namespaces)
                if code:
                    _logger.info(f"GetXmlByDocumentKey - Código respuesta DIAN: {code[0]}")

                # Extraer XML del documento
                xml_bytes_base64 = root.xpath('//s:Body//b:XmlBytesBase64/text()', namespaces=namespaces)
                if xml_bytes_base64:
                    _logger.info(f"XML recuperado exitosamente desde DIAN para CUFE: {self.cufe[:20]}...")
                    return base64.b64decode(xml_bytes_base64[0])
                else:
                    _logger.warning(f"GetXmlByDocumentKey - No se encontró XML en la respuesta DIAN para CUFE: {self.cufe}")
            else:
                _logger.warning(f"GetXmlByDocumentKey - Error HTTP {response['status_code']}")

        except etree.XMLSyntaxError as xml_error:
            _logger.error(f"Error parseando respuesta XML de DIAN: {str(xml_error)}")
        except Exception as e:
            _logger.warning(f"No se pudo recuperar XML de DIAN: {str(e)}")

        return None
    
    def _action_get_xml(self, name=False, cufe=False):
        """Obtiene el XML desde DIAN usando GetXmlByDocumentKey"""
        self.ensure_one()
        
        if not cufe:
            cufe = self.cufe
            name = f'DIAN_{self._get_dian_document_type_dian()}_invoice.xml'
        
        response = xml_utils._build_and_send_request(
            self,
            payload={
                'track_id': cufe,
                'soap_body_template': "l10n_co_e_invoice.get_xml",
            },
            service="GetXmlByDocumentKey",
            company=self.company_id,
        )
        
        if response['status_code'] == 200:
            root = etree.fromstring(response['response'])
            namespaces = {
                's': 'http://www.w3.org/2003/05/soap-envelope',
                'b': 'http://schemas.datacontract.org/2004/07/EventResponse'
            }
            
            code = root.xpath('//s:Body//b:Code/text()', namespaces=namespaces)
            message = root.xpath('//s:Body//b:Message/text()', namespaces=namespaces)
            xml_bytes_base64 = root.xpath('//s:Body//b:XmlBytesBase64/text()', namespaces=namespaces)
            
            if xml_bytes_base64:
                base64_content = xml_bytes_base64[0]
                decoded_content = base64.b64decode(base64_content)
                
                # Crear o actualizar attachment
                attachment_vals = {
                    'name': name,
                    'type': 'binary',
                    'datas': base64.b64encode(decoded_content),
                    'res_model': self._name,
                    'res_id': self.id,
                    'mimetype': 'application/xml',
                }
                
                if self.dian_xml_attachment_id:
                    self.dian_xml_attachment_id.write(attachment_vals)
                else:
                    self.dian_xml_attachment_id = self.env['ir.attachment'].create(attachment_vals)
                
                # Actualizar el documento
                self.write({
                    'state_dian_document': 'exitoso',
                    'xml_text': decoded_content.decode('utf-8') if hasattr(self, 'xml_text') else False,
                })
                
                return {
                    'success': True,
                    'xml_content': decoded_content,
                    'attachment_id': self.dian_xml_attachment_id.id
                }
            else:
                return {
                    'success': False,
                    'error': message[0] if message else 'No se pudo obtener el XML'
                }
        
        elif response['status_code']:
            raise UserError(_("El servidor de la DIAN arrojó error (Código %s)") % response['status_code'])
        else:
            raise UserError(_("El servidor DIAN no respondió."))
    
    def _create_zip_content(self, xml_content, dian_constants):
        """Crea el contenido ZIP"""
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as zip_file:
            if isinstance(xml_content, str):
                xml_content = xml_content.encode('utf-8')
            zip_file.writestr(dian_constants['FileNameXML'], xml_content)
        return buffer.getvalue()
    
    def _save_xml_attachment(self, xml_content, dian_constants):
        """Guarda el XML como attachment"""
        if isinstance(xml_content, str):
            xml_content = xml_content.encode('utf-8')
        
        vals = {
            'name': dian_constants['FileNameXML'],
            'type': 'binary',
            'datas': base64.b64encode(xml_content),
            # Vincular al documento para respetar reglas de acceso
            'res_model': 'account.move',
            'res_id': self.id,
            'mimetype': 'application/xml',
        }
        
        if self.dian_xml_attachment_id:
            self.dian_xml_attachment_id.write(vals)
        else:
            self.dian_xml_attachment_id = self.env['ir.attachment'].create(vals)
    
    def _save_response_attachment(self, response_content, dian_constants):
        """Guarda la respuesta como attachment"""
        if isinstance(response_content, str):
            response_content = response_content.encode('utf-8')
        
        vals = {
            'name': f"RESP_{dian_constants['FileNameXML']}",
            'type': 'binary',
            'datas': base64.b64encode(response_content),
            # Vincular al documento para respetar reglas de acceso
            'res_model': 'account.move',
            'res_id': self.id,
            'mimetype': 'application/xml',
        }
        
        if self.dian_response_attachment_id:
            self.dian_response_attachment_id.write(vals)
        else:
            self.dian_response_attachment_id = self.env['ir.attachment'].create(vals)
    
    def _get_colombia_time_iso(self):
        """Obtiene la hora de Colombia en formato ISO"""
        tz_co = timezone('America/Bogota')
        now_co = datetime.now(tz=tz_co)
        return now_co.strftime('%Y-%m-%dT%H:%M:%S-05:00')
    
    def _get_dian_document_type_dian(self):
        """Retorna el tipo de documento DIAN"""
        if hasattr(self, 'is_debit_note') and self.is_debit_note:
            return 'd'
        elif self.move_type in ['out_refund', 'in_refund']:
            return 'c'
        return 'f'
    
    def _is_dian_applicable(self):
        """Verifica si aplica para DIAN"""
        return (
            self.state == 'posted' and
            self.journal_id.sequence_id.use_dian_control and
            self.move_type in ['out_invoice', 'out_refund', 'in_invoice', 'in_refund']
        )
    
    def _create_dian_document_record(self, dian_constants, response):
        """Crea el registro en dian.document con toda la información"""

        # Determinar si es un caso de Regla 90
        is_regla_90 = False
        if response.get('errors'):
            is_regla_90 = any(
                'Regla: 90' in error and 'Documento procesado anteriormente' in error 
                for error in response.get('errors', [])
            )
        
        vals = {
            'document_id': self.id,
            'document_type': self._get_dian_document_type_dian(),
            'state': self.state_dian_document,
            'dian_code': dian_constants['InvoiceID'],
            'cufe': self.cufe or dian_constants.get('cufe', ''),
            'cufe_seed': dian_constants.get('cufe_seed', ''),
            'QR_code': dian_constants.get('qr_code', False),
            'qr_data': dian_constants.get('qr_data', ''),
            'xml_file_name': dian_constants['FileNameXML'],
            'zip_file_name': dian_constants['FileNameZIP'],
            'response_message_dian': self.response_message_dian,
            'xml_response_dian': response.get('response', ''),
            'shipping_response': '200' if is_regla_90 else self._get_shipping_response_code(response),
            'date_document_dian': fields.Datetime.now(),
            'ZipKey': response.get('zip_key', ''),
            'contingency_3': self.contingency_3 if hasattr(self, 'contingency_3') else False,
            'contingency_4': self.contingency_4 if hasattr(self, 'contingency_4') else False,
        }
        
        # Attachments
        if self.dian_xml_attachment_id:
            vals['invoice_id'] = self.dian_xml_attachment_id.id
        if self.dian_response_attachment_id:
            vals['response_id'] = self.dian_response_attachment_id.id
        
        # Crear o actualizar
        if hasattr(self, 'diancode_id') and self.diancode_id:
            self.diancode_id.write(vals)
            return self.diancode_id
        else:
            dian_doc = self.env['dian.document'].create(vals)
            self.diancode_id = dian_doc
            return dian_doc
    
    def _get_shipping_response_code(self, response):
        """Determina el código de respuesta de envío"""
        if response['status'] == 'success':
            return '200'
        elif response.get('status_code') == '500':
            return '500'
        elif 'validación' in str(response.get('errors', '')):
            return '310'
        else:
            return '100'

    def _is_regla_90_response(self, response):
        """Verifica si la respuesta es un error de Regla 90"""
        if response.get('errors'):
            return any(
                'Regla: 90' in error and 'Documento procesado anteriormente' in error 
                for error in response.get('errors', [])
            )
        return False

    def _handle_regla_90_recovery(self, response, dian_doc):
        """Maneja la recuperación del XML para documentos con Regla 90"""
        try:
            document_key = self._extract_document_key_from_response(response)
            
            if document_key:
                _logger.info(f"Recuperando XML para documento Regla 90 con CUFE: {document_key}")
                
                if dian_doc:
                    dian_doc.cufe = document_key
                
                result = self._action_get_xml(
                    name=f"DIAN_{self._get_dian_document_type_dian()}_invoice.xml",
                    cufe=document_key
                )
                
                if result.get('success'):
                    _logger.info("XML recuperado exitosamente para documento Regla 90")
                    
                    html_message = Markup(f'''
                    <div class="alert alert-success">
                        <h4>Documento Procesado Anteriormente - XML Recuperado</h4>
                        <p><strong>Estado:</strong> Exitoso (Regla 90)</p>
                        <p><strong>CUFE:</strong> {document_key}</p>
                        <p><em>Este documento ya fue procesado anteriormente en DIAN. El XML ha sido recuperado exitosamente.</em></p>
                    </div>
                    ''')
                    
                    self.response_message_dian = html_message
                    if dian_doc:
                        dian_doc.response_message_dian = html_message
                else:
                    _logger.warning(f"No se pudo recuperar XML para documento Regla 90: {result.get('error', 'Error desconocido')}")
            else:
                _logger.warning("No se pudo extraer XmlDocumentKey de la respuesta Regla 90")
                
        except Exception as e:
            _logger.error(f"Error recuperando XML para Regla 90: {str(e)}", exc_info=True)

    def _extract_document_key_from_response(self, response):
        """Extrae el XmlDocumentKey de la respuesta XML"""
        try:
            if response.get('response'):
                root = etree.fromstring(response['response'].encode('utf-8') if isinstance(response['response'], str) else response['response'])
                
                namespaces = {
                    's': 'http://www.w3.org/2003/05/soap-envelope',
                    'b': 'http://schemas.datacontract.org/2004/07/DianResponse'
                }
                
                document_key = root.findtext('.//b:XmlDocumentKey', namespaces=namespaces)
                
                if document_key:
                    return document_key.strip()
                
                document_key = root.findtext('.//XmlDocumentKey')
                if document_key:
                    return document_key.strip()
                    
            if response.get('errors'):
                for error in response.get('errors', []):
                    if 'CUFE' in error or 'UUID' in error:
                        import re
                        cufe_match = re.search(r'[0-9a-fA-F]{96}', error)
                        if cufe_match:
                            return cufe_match.group(0)
                            
        except Exception as e:
            _logger.error(f"Error extrayendo XmlDocumentKey: {str(e)}")
        
        return None
