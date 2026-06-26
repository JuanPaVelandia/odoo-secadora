# -*- coding: utf-8 -*-
"""
Generador XML de Nómina Electrónica vía Qweb Templates + SOAP
===============================================================

Consolida TODA la lógica de nómina electrónica en un solo lugar:
  - Validación pre-envío
  - Generación de CUNE (SHA-384)
  - Constantes DIAN
  - NominaIndividual y NominaIndividualDeAjuste → Qweb templates
  - Firma digital ds:Signature (XAdES-EPES)
  - ZIP/Packaging
  - SOAP envelopes → Python string template (por namespaces complejos)
  - Comunicación con DIAN (SendNominaSync, SendTestSetAsync, GetStatus)
  - Parsing de respuestas DIAN
  - Status checking

Uso:
    generator = env['nomina.xml.generator']
    generator.send_to_dian(payslip)
    generator.check_status(payslip)
    generator.validate_all(payslip)
"""

import base64
import hashlib
import io
import logging
import os
import uuid
import zipfile
from datetime import datetime, timedelta

from lxml import etree
from pytz import timezone

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization.pkcs12 import load_key_and_certificates
from cryptography.exceptions import InvalidSignature

from odoo import _, api, models, tools
from odoo.exceptions import UserError, ValidationError

try:
    import requests
except ImportError:
    pass

try:
    import xmltodict
except ImportError:
    pass

_logger = logging.getLogger(__name__)

try:
    compression = zipfile.ZIP_DEFLATED
except Exception:
    compression = zipfile.ZIP_STORED

# =========================================================================
# CONSTANTES
# =========================================================================

TIPO_AMBIENTE = {
    "PRODUCCION": "1",
    "PRUEBA": "2",
}

SERVER_URL = {
    "TEST": "https://vpfe-hab.dian.gov.co/WcfDianCustomerServices.svc?wsdl",
    "PRODUCCION": "https://vpfe.dian.gov.co/WcfDianCustomerServices.svc?wsdl",
}

TEMPLATE_NOMINA_INDIVIDUAL = 'lavish_hr_payroll_edi.nomina_individual'
TEMPLATE_NOMINA_AJUSTE = 'lavish_hr_payroll_edi.nomina_individual_ajuste'

# =========================================================================
# SOAP ENVELOPE - Python string template
# =========================================================================
_SOAP_ENVELOPE = """\
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" xmlns:wcf="http://wcf.dian.colombia">
<soap:Header xmlns:wsa="http://www.w3.org/2005/08/addressing">
<wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">
<wsu:Timestamp wsu:Id="TS-%(identifier)s">
<wsu:Created>%(Created)s</wsu:Created>
<wsu:Expires>%(Expires)s</wsu:Expires>
</wsu:Timestamp>
<wsse:BinarySecurityToken
EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary"
ValueType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-x509-token-profile-1.0#X509v3"
wsu:Id="BAKENDEVS-%(identifierSecurityToken)s">%(Certificate)s</wsse:BinarySecurityToken>
<ds:Signature Id="SIG-%(identifier)s" xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
<ds:SignedInfo>
<ds:CanonicalizationMethod Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#">
<ec:InclusiveNamespaces PrefixList="wsa soap wcf" xmlns:ec="http://www.w3.org/2001/10/xml-exc-c14n#"/>
</ds:CanonicalizationMethod>
<ds:SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"/>
<ds:Reference URI="#ID-%(identifierTo)s">
<ds:Transforms>
<ds:Transform Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#">
<ec:InclusiveNamespaces PrefixList="soap wcf" xmlns:ec="http://www.w3.org/2001/10/xml-exc-c14n#"/>
</ds:Transform>
</ds:Transforms>
<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
<ds:DigestValue></ds:DigestValue>
</ds:Reference>
</ds:SignedInfo>
<ds:SignatureValue></ds:SignatureValue>
<ds:KeyInfo Id="KI-%(identifier)s">
<wsse:SecurityTokenReference wsu:Id="STR-%(identifier)s">
<wsse:Reference URI="#BAKENDEVS-%(identifierSecurityToken)s"
ValueType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-x509-token-profile-1.0#X509v3"/>
</wsse:SecurityTokenReference>
</ds:KeyInfo>
</ds:Signature>
</wsse:Security>
<wsa:Action>%(SoapAction)s</wsa:Action>
<wsa:To wsu:Id="ID-%(identifierTo)s"
xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">
%(Endpoint)s
</wsa:To>
</soap:Header>
<soap:Body>
%(SoapBody)s
</soap:Body>
</soap:Envelope>"""

# Cuerpos SOAP por acción
_SOAP_BODIES = {
    'SendNominaSync': """\
<wcf:SendNominaSync>
<wcf:fileName>%(fileName)s</wcf:fileName>
<wcf:contentFile>%(contentFile)s</wcf:contentFile>
</wcf:SendNominaSync>""",
    'SendTestSetAsync': """\
<wcf:SendTestSetAsync>
<wcf:fileName>%(fileName)s</wcf:fileName>
<wcf:contentFile>%(contentFile)s</wcf:contentFile>
<wcf:testSetId>%(testSetId)s</wcf:testSetId>
</wcf:SendTestSetAsync>""",
    'GetStatusZip': """\
<wcf:GetStatusZip>
<wcf:trackId>%(trackId)s</wcf:trackId>
</wcf:GetStatusZip>""",
    'GetStatus': """\
<wcf:GetStatus>
<wcf:trackId>%(trackId)s</wcf:trackId>
</wcf:GetStatus>""",
}

# Acciones SOAP
_SOAP_ACTIONS = {
    'SendNominaSync': 'http://wcf.dian.colombia/IWcfDianCustomerServices/SendNominaSync',
    'SendTestSetAsync': 'http://wcf.dian.colombia/IWcfDianCustomerServices/SendTestSetAsync',
    'GetStatusZip': 'http://wcf.dian.colombia/IWcfDianCustomerServices/GetStatusZip',
    'GetStatus': 'http://wcf.dian.colombia/IWcfDianCustomerServices/GetStatus',
}

# =========================================================================
# FIRMA DIGITAL - ds:Signature template (XAdES-EPES)
# =========================================================================
_SIGNATURE_TEMPLATE = """\
<ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#" Id="xmldsig-%(identifier)s">
<ds:SignedInfo>
<ds:CanonicalizationMethod Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"/>
<ds:SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"/>
<ds:Reference Id="xmldsig-%(identifier)s-ref0" URI="">
<ds:Transforms>
<ds:Transform Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature"/>
</ds:Transforms>
<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
<ds:DigestValue>%(data_xml_signature_ref_zero)s</ds:DigestValue>
</ds:Reference>
<ds:Reference URI="#xmldsig-%(identifierkeyinfo)s-keyinfo">
<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
<ds:DigestValue>%(data_xml_keyinfo_base)s</ds:DigestValue>
</ds:Reference>
<ds:Reference Type="http://uri.etsi.org/01903#SignedProperties" URI="#xmldsig-%(identifier)s-signedprops">
<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
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
<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
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
<xades:Description>Politica de firma para nominas electronicas de la Republica de Colombia</xades:Description>
</xades:SigPolicyId>
<xades:SigPolicyHash>
<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
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


class NominaXMLGenerator(models.AbstractModel):
    """
    Generador XML para Nómina Electrónica DIAN Colombia.
    Consolida en un solo lugar TODA la lógica electrónica.
    """
    _name = 'nomina.xml.generator'
    _description = 'Generador XML Nomina Electronica DIAN'

    # ================================================================
    # SECCIÓN 1: VALIDACIÓN PRE-ENVÍO
    # ================================================================

    @api.model
    def validate_company_config(self, company):
        """Valida configuración de la empresa para nómina electrónica."""
        errors = []
        partner = company.partner_id
        if not partner.vat_co:
            errors.append(_("El NIT del emisor del documento es requerido"))
        if not partner.dv and type(partner.dv) == "bool":
            errors.append(_("Falta configurar el DV en el emisor"))
        if not company.country_id.code:
            errors.append(_("Se debe configurar el código del país en la compañía"))
        if not partner.city_id:
            errors.append(_("Se debe configurar la ciudad de la compañía"))
        if not partner.state_id or not partner.state_id.code_dian:
            errors.append(_("Se debe configurar el código DIAN de la provincia de la compañía"))
        if not company.software_identification_code_payroll:
            errors.append(_("Falta el código de identificación del software (SoftwareID)"))
        if not company.software_pin_payroll:
            errors.append(_("Falta el PIN del software de nómina"))
        if not company.certificate_file_payroll:
            errors.append(_("Falta el archivo del certificado digital"))
        if not company.certificate_key_payroll:
            errors.append(_("Falta la contraseña del certificado digital"))
        if not company.digital_certificate_payroll:
            errors.append(_("Falta el certificado digital público"))
        if not company.serial_number_payroll:
            errors.append(_("Falta el número serial del certificado"))
        if not company.document_repository_payroll:
            errors.append(_("Falta la ruta del repositorio de documentos"))
        if not company.pem_file_payroll:
            errors.append(_("Falta el archivo PEM del certificado"))
        # NIE038 - Dirección física del empleador
        if not partner.street:
            errors.append(_("[NIE038] Falta la dirección física del empleador"))
        # NIE032 - Razón social del empleador
        if not partner.name:
            errors.append(_("[NIE032] Falta la Razón Social del empleador"))
        # NIE034 - DV debe ser string numérico
        if partner.dv and not str(partner.dv).strip().isdigit():
            errors.append(_("[NIE034] El DV del empleador debe ser un valor numérico"))
        # NIE210-212 - Nombres del empleador (proveedor) persona natural
        if not partner.first_lastname and not partner.name:
            errors.append(_("[NIE210] Falta el Primer Apellido del empleador (persona natural)"))
        # NIE037 - Código DIAN de la ciudad del empleador
        if partner.city_id and not partner.city_id.code:
            errors.append(_("[NIE037] La ciudad de la compañía no tiene código DIAN configurado"))
        # NIE036 - Código DIAN del departamento del empleador
        if partner.state_id and not partner.state_id.code_dian:
            errors.append(_("[NIE036] El departamento de la compañía no tiene código DIAN configurado"))
        return errors

    @api.model
    def validate_employee_data(self, employee):
        """Valida datos del empleado contra XSD DIAN V1.0.6.

        Todos los campos vienen del work_contact_id (res.partner). Cubre los
        atributos del nodo Trabajador que el XSD marca como use="required".
        """
        errors = []
        contact = employee.work_contact_id
        if not contact:
            errors.append(_("El empleado %s no tiene tercero (work_contact_id) configurado") % employee.name)
            return errors

        # Identificacion (NIE044 / NumeroDocumento)
        if not contact.vat_co:
            errors.append(_("El numero de identificacion del empleado %s es requerido") % employee.name)
        if not contact.l10n_latam_identification_type_id:
            errors.append(_("[NIE044] Falta el tipo de documento del empleado %s") % employee.name)

        # Tipo / SubTipo de trabajador (codigos requeridos por XSD)
        if not employee.tipo_coti_id:
            errors.append(_("Falta el tipo de trabajador (tipo_coti_id) del empleado %s") % employee.name)
        elif not employee.tipo_coti_id.code:
            errors.append(_("El tipo de trabajador del empleado %s no tiene codigo") % employee.name)
        if not employee.subtipo_coti_id:
            errors.append(_("Falta el subtipo de trabajador (subtipo_coti_id) del empleado %s") % employee.name)
        elif not getattr(employee.subtipo_coti_id, 'code', False):
            errors.append(_("El subtipo de trabajador del empleado %s no tiene codigo") % employee.name)

        # Nombres (XSD: PrimerApellido, SegundoApellido y PrimerNombre son required)
        if not contact.first_lastname:
            errors.append(_("[NIE046] Falta el Primer Apellido del empleado %s") % employee.name)
        if not contact.second_lastname:
            errors.append(_("[NIE047] Falta el Segundo Apellido del empleado %s (XSD V1.0.6 lo marca required)") % employee.name)
        if not contact.first_name:
            errors.append(_("[NIE048] Falta el Primer Nombre del empleado %s") % employee.name)

        # LugarTrabajo (Pais, Departamento, Municipio y Direccion son required)
        if not contact.country_id or not contact.country_id.code:
            errors.append(_("Se debe registrar el codigo del pais del empleado %s") % employee.name)
        if not contact.state_id:
            errors.append(_("Se debe registrar la provincia del empleado %s") % employee.name)
        elif not contact.state_id.code_dian:
            errors.append(_("[NIE051] El departamento del empleado %s no tiene codigo DIAN") % employee.name)
        if not contact.city_id:
            errors.append(_("Se debe registrar la ciudad del empleado %s") % employee.name)
        elif not contact.city_id.code:
            errors.append(_("[NIE052] La ciudad del empleado %s no tiene codigo DIAN") % employee.name)
        if not contact.street:
            errors.append(_("[NIE053] Falta la direccion del lugar de trabajo del empleado %s") % employee.name)
        return errors

    @api.model
    def validate_contract_data(self, contract):
        """Valida datos del contrato para nómina electrónica."""
        errors = []
        if not contract:
            errors.append(_("No hay contrato definido"))
            return errors
        if not contract.way_pay_id:
            errors.append(_("Falta la forma de pago en el contrato"))
        if not contract.payment_method_dian_id:
            errors.append(_("Falta el método de pago en el contrato"))
        # NIE062 - Sueldo debe ser mayor a cero
        if not contract.wage or contract.wage <= 0:
            errors.append(_("[NIE062] El sueldo del contrato debe ser mayor a cero"))
        # NIE061 - Tipo de contrato requerido
        if not (contract.contract_type_id and contract.contract_type_id.contract_category):
            errors.append(_("[NIE061] Falta el tipo de contrato"))
        return errors

    @api.model
    def validate_payslip_data(self, payslip):
        """Valida datos de la nómina para envío electrónico."""
        errors = []
        if not payslip.payment_date:
            errors.append(_("Debe configurar la fecha de pago"))
        if not payslip.number:
            errors.append(_("Se debe configurar la referencia/número de la nómina"))
        if payslip.credit_note:
            if not payslip.previous_cune:
                errors.append(_("Debe ingresar el identificador CUNE de la nómina a afectar"))
            if not payslip.type_note:
                errors.append(_("Debe seleccionar el tipo de nota (Reemplazar o Eliminar)"))
        # VLR01 - Valores monetarios positivos
        try:
            dev_total = float(payslip._get_total_devengados())
            if dev_total < 0:
                errors.append(_("[VLR01] El total de devengados no puede ser negativo (%.2f)") % dev_total)
        except Exception:
            pass
        try:
            ded_total = float(payslip._get_total_deducciones())
            if ded_total < 0:
                errors.append(_("[VLR01] El total de deducciones no puede ser negativo (%.2f)") % ded_total)
        except Exception:
            pass
        # NIE010 - Prefijo de secuencia
        try:
            sequence = payslip._get_sequence()
            if sequence and not sequence.prefix:
                errors.append(_("[NIE010] Falta el prefijo en la secuencia de nómina electrónica"))
        except Exception:
            pass
        return errors

    @api.model
    def validate_all(self, payslip, raise_error=True):
        """Ejecuta todas las validaciones.

        Args:
            payslip: Documento de nómina electrónica
            raise_error: Si True, lanza UserError. Si False, retorna lista de errores.

        Returns:
            Lista de errores si raise_error=False, None si no hay errores.
        """
        errors = []
        errors += self.validate_company_config(payslip.company_id)
        errors += self.validate_employee_data(payslip.employee_id)
        errors += self.validate_contract_data(payslip.version_id)
        errors += self.validate_payslip_data(payslip)
        if errors:
            if raise_error:
                raise UserError("\n".join(errors))
            return errors
        return None

    # ================================================================
    # SECCIÓN 2: CUNE GENERATION
    # ================================================================

    @api.model
    def generate_cune(self, payslip, dian_constants):
        """
        Genera CUNE según Anexo Técnico Sección 8.1:
        SHA384(NumNE + FecNE + HorNE + ValDev + ValDed + ValTol + NitNE + DocEmp + TipoXML + Pin + TipAmb)
        """
        number = payslip._get_number()
        fecha_gen = dian_constants.get('FechaGen')
        hora_gen = dian_constants.get('HoraGen')
        val_dev = payslip._get_total_devengados()
        val_ded = payslip._get_total_deducciones()
        val_tol = payslip._get_total_pagado()
        nit = payslip._get_emisor().vat_co
        doc_emp = payslip._get_employee().vat_co
        tipo_xml = payslip._get_tipo_xml()
        pin = payslip.company_id.software_pin_payroll
        tip_amb = payslip._get_tipo_ambiente()

        cadena = "{}{}{}{}{}{}{}{}{}{}{}".format(
            number, fecha_gen, hora_gen, val_dev, val_ded, val_tol,
            nit, doc_emp, tipo_xml, pin, tip_amb
        )
        return hashlib.sha384(cadena.encode()).hexdigest()

    @api.model
    def generate_cune_ajuste_eliminar(self, values):
        """
        CUNE para Nota de Ajuste Eliminar (Anexo Técnico Sección 8.1):
        ValDev=0.00, ValDed=0.00, ValTol=0.00, DocEmp=0
        """
        cadena = "{}{}{}{}{}{}{}{}{}{}{}".format(
            values['numNIAE'], values['FecNIAE'], values.get('HorNIAE'),
            '0.00', '0.00', '0.00',
            values['NitNIAE'], '0',
            values['TipoXML'], values['SoftwarePin'], values['TipAmb']
        )
        return hashlib.sha384(cadena.encode()).hexdigest()

    @api.model
    def generate_software_security_code(self, software_id, pin, numero):
        """
        SoftwareSC según Anexo Técnico Sección 8.2:
        SHA384(SoftwareID + Pin + NroDocumento)
        """
        return hashlib.sha384((software_id + pin + numero).encode()).hexdigest()

    # ================================================================
    # SECCIÓN 3: DIAN CONSTANTS
    # ================================================================

    @api.model
    def get_dian_constants(self, payslip):
        """Construye el diccionario completo de constantes DIAN."""
        company = payslip.company_id
        sequence = payslip._get_sequence()
        consecutivo = payslip._get_consecutivo()
        number = payslip._get_number()

        dc = {
            "document_repository": company.document_repository_payroll,
            "Username": company.software_identification_code_payroll,
            "Password": hashlib.new(
                "sha256", company.password_environment_payroll.encode()
            ).hexdigest(),
            "SoftwareID": company.software_identification_code_payroll,
            "SoftwareSecurityCode": self.generate_software_security_code(
                company.software_identification_code_payroll,
                company.software_pin_payroll,
                number,
            ),
            "Number": number,
            "Prefix": sequence.prefix,
            "Consecutivo": consecutivo,
            "PINSoftware": company.software_pin_payroll,
            "SeedCode": company.seed_code_payroll,
            "ProfileExecutionID": (
                TIPO_AMBIENTE["PRODUCCION"]
                if company.production_payroll
                else TIPO_AMBIENTE["PRUEBA"]
            ),
            "CertificateKey": company.certificate_key_payroll,
            "archivo_certificado": company.certificate_file_payroll,
            "CertDigestDigestValue": self.generate_cert_digest(company),
            "IssuerName": company.issuer_name or '',
            "SerialNumber": company.serial_number_payroll,
            "Certificate": company.digital_certificate_payroll,
            "HoraGen": self._get_time_colombia(),
            "FechaGen": self._get_generation_date(),
        }
        return dc

    @api.model
    def generate_data_constants_document(self, payslip, dian_constants):
        """Genera UUIDs y filenames para el documento."""
        return {
            "identifier": uuid.uuid4(),
            "identifierkeyinfo": uuid.uuid4(),
            "InvoiceTypeCode": payslip._get_tipo_xml(),
            "FileNameXML": self.generate_xml_filename(payslip),
            "FileNameZIP": self.generate_zip_filename(payslip),
        }

    @api.model
    def _get_generation_date(self):
        now_utc = datetime.now(timezone("UTC"))
        return now_utc.strftime("%Y-%m-%d")

    @api.model
    def _get_time_colombia(self):
        now_utc = datetime.now(timezone("UTC"))
        return now_utc.strftime("%H:%M:%S-05:00")

    @api.model
    def _generate_datetime_timestamp(self):
        fmt = "%Y-%m-%dT%H:%M:%S.%f"
        now = datetime.now(timezone("UTC"))
        Created = now.strftime(fmt)[:-3] + "Z"
        expires = now + timedelta(minutes=5)
        Expires = expires.strftime(fmt)[:-3] + "Z"
        return {"Created": Created, "Expires": Expires}

    # ================================================================
    # SECCIÓN 4: XML GENERATION (Qweb) - NÓMINA INDIVIDUAL
    # ================================================================

    @api.model
    def generate_nomina_individual(self, payslip, dian_constants):
        """Genera XML de NominaIndividual usando template Qweb."""
        vals = self._prepare_nomina_values(payslip, dian_constants)
        return self._render_template(TEMPLATE_NOMINA_INDIVIDUAL, vals)

    @api.model
    def generate_nomina_ajuste(self, payslip, dian_constants, previous_payslip):
        """Genera XML de NominaIndividualDeAjuste usando template Qweb."""
        vals = self._prepare_nomina_values(payslip, dian_constants)
        vals['Version'] = 'V1.0: Nota de Ajuste de Documento Soporte de Pago de Nómina Electrónica'
        vals['TipoNota'] = payslip.type_note
        vals['Predecesor'] = {
            'NumeroPred': previous_payslip.number,
            'CUNEPred': previous_payslip.current_cune,
            'FechaGenPred': str(previous_payslip.payment_date),
        }
        return self._render_template(TEMPLATE_NOMINA_AJUSTE, vals)

    # ================================================================
    # SECCIÓN 5: VALORES DEL XML PREVIO (para ajustes)
    # ================================================================

    @api.model
    def get_values_from_previous_xml(self, xml_string):
        """
        Parsea el XML anteriormente enviado para recuperar parámetros.
        Se usa para notas de ajuste que necesitan datos del documento original.
        """
        xml = xmltodict.parse(xml_string)
        return {
            "Prefix": xml["NominaIndividual"]["NumeroSecuenciaXML"]["@Prefijo"],
            "consecutivo": xml["NominaIndividual"]["NumeroSecuenciaXML"]["@Consecutivo"],
            "numero": xml["NominaIndividual"]["NumeroSecuenciaXML"]["@Numero"],
            "pais": xml["NominaIndividual"]["LugarGeneracionXML"]["@Pais"],
            "departamento": xml["NominaIndividual"]["LugarGeneracionXML"]["@DepartamentoEstado"],
            "idioma": xml["NominaIndividual"]["LugarGeneracionXML"].get("@Idioma", "es"),
            "municipio": xml["NominaIndividual"]["LugarGeneracionXML"]["@MunicipioCiudad"],
            "softwareid": xml["NominaIndividual"]["ProveedorXML"]["@SoftwareID"],
            "softwaresc": xml["NominaIndividual"]["ProveedorXML"]["@SoftwareSC"],
            "codeqr": xml["NominaIndividual"]["CodigoQR"],
            "cune": xml["NominaIndividual"]["InformacionGeneral"]["@CUNE"],
            "fechagen": xml["NominaIndividual"]["InformacionGeneral"]["@FechaGen"],
            "horagen": xml["NominaIndividual"]["InformacionGeneral"]["@HoraGen"],
            "NitNIAE": xml["NominaIndividual"]["Empleador"]["@NIT"],
            "TipoXML": xml["NominaIndividual"]["InformacionGeneral"]["@TipoXML"],
            "TipAmb": xml["NominaIndividual"]["InformacionGeneral"]["@Ambiente"],
        }

    # ================================================================
    # SECCIÓN 6: FIRMA DIGITAL (ds:Signature - XAdES-EPES)
    # ================================================================

    @api.model
    def sign_document(self, data_xml_document, dian_constants, data_constants_document):
        """
        Firma completa del documento XML de nómina electrónica.
        Implementa XAdES-EPES según Anexo Técnico Sección 7.
        """
        template_signature = _SIGNATURE_TEMPLATE
        data_public_certificate_base = dian_constants["Certificate"]
        data_xml_politics = self._generate_signature_politics()
        data_xml_SigningTime = self._generate_signature_signingtime()

        # Ref0: digest del documento completo
        data_xml_signature_ref_zero = self._generate_signature_ref0(data_xml_document)

        # Primera actualización de firma
        data_xml_signature = template_signature % {
            "data_xml_signature_ref_zero": data_xml_signature_ref_zero,
            "data_public_certificate_base": data_public_certificate_base,
            "data_xml_keyinfo_base": "",
            "data_xml_politics": data_xml_politics,
            "data_xml_SignedProperties_base": "",
            "data_xml_SigningTime": data_xml_SigningTime,
            "CertDigestDigestValue": dian_constants["CertDigestDigestValue"],
            "IssuerName": dian_constants["IssuerName"],
            "SerialNumber": dian_constants["SerialNumber"],
            "SignatureValue": "",
            "identifier": data_constants_document["identifier"],
            "identifierkeyinfo": data_constants_document["identifierkeyinfo"],
        }

        parser = etree.XMLParser(remove_blank_text=True)
        data_xml_signature = etree.tostring(
            etree.XML(data_xml_signature, parser=parser)
        ).decode()

        # Ref1: digest de KeyInfo
        invoice_type = data_constants_document.get("InvoiceTypeCode", "102")
        KeyInfo = etree.fromstring(data_xml_signature)
        KeyInfo = etree.tostring(KeyInfo[2]).decode()
        KeyInfo = self._inject_namespaces(KeyInfo, invoice_type)

        data_xml_keyinfo_base = self._generate_signature_ref1(KeyInfo)
        data_xml_signature = data_xml_signature.replace(
            "<ds:DigestValue/>",
            "<ds:DigestValue>%s</ds:DigestValue>" % data_xml_keyinfo_base,
            1,
        )

        # Ref2: digest de SignedProperties
        SignedProperties = etree.fromstring(data_xml_signature)
        SignedProperties = etree.tostring(SignedProperties[3])
        SignedProperties = etree.tostring(etree.fromstring(SignedProperties)[0])
        SignedProperties = etree.tostring(etree.fromstring(SignedProperties)[0]).decode()
        SignedProperties = self._inject_namespaces_signed_props(SignedProperties, invoice_type)

        data_xml_SignedProperties_base = self._generate_signature_ref2(SignedProperties)
        data_xml_signature = data_xml_signature.replace(
            "<ds:DigestValue/>",
            "<ds:DigestValue>%s</ds:DigestValue>" % data_xml_SignedProperties_base,
            1,
        )

        # SignatureValue: firma RSA-SHA256 de SignedInfo
        Signedinfo = etree.fromstring(data_xml_signature)
        Signedinfo = etree.tostring(Signedinfo[0]).decode()
        Signedinfo = self._inject_namespaces_signedinfo(Signedinfo, invoice_type)

        company = self.env.company
        data_xml_SignatureValue = self._generate_signature_value(
            Signedinfo, company, exclusive=False
        )
        data_xml_signature = data_xml_signature.replace(
            '-sigvalue"/>',
            '-sigvalue">%s</ds:SignatureValue>' % data_xml_SignatureValue,
            1,
        )
        return data_xml_signature

    @api.model
    def _inject_namespaces(self, xml_string, invoice_type):
        """Inyecta los namespaces correctos según tipo de documento."""
        if invoice_type == "102":
            ns = 'dian:gov:co:facturaelectronica:NominaIndividual'
        else:
            ns = 'dian:gov:co:facturaelectronica:NominaIndividualDeAjuste'
        xmlns = (
            'xmlns="%s" '
            'xmlns:xs="http://www.w3.org/2001/XMLSchema-instance" '
            'xmlns:ds="http://www.w3.org/2000/09/xmldsig#" '
            'xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" '
            'xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" '
            'xmlns:xades141="http://uri.etsi.org/01903/v1.4.1#" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
        ) % ns
        return xml_string.replace(
            'xmlns:ds="http://www.w3.org/2000/09/xmldsig#"', xmlns
        )

    @api.model
    def _inject_namespaces_signedinfo(self, xml_string, invoice_type):
        """Inyecta namespaces completos en SignedInfo para nómina electrónica."""
        if invoice_type == "102":
            ns = 'dian:gov:co:facturaelectronica:NominaIndividual'
        else:
            ns = 'dian:gov:co:facturaelectronica:NominaIndividualDeAjuste'
        xmlns = (
            'xmlns="%s" '
            'xmlns:xs="http://www.w3.org/2001/XMLSchema-instance" '
            'xmlns:ds="http://www.w3.org/2000/09/xmldsig#" '
            'xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" '
            'xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" '
            'xmlns:xades141="http://uri.etsi.org/01903/v1.4.1#" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
        ) % ns
        return xml_string.replace(
            'xmlns:ds="http://www.w3.org/2000/09/xmldsig#"', xmlns
        )

    @api.model
    def _inject_namespaces_signed_props(self, xml_string, invoice_type):
        """Inyecta namespaces en SignedProperties."""
        if invoice_type == "102":
            ns = 'dian:gov:co:facturaelectronica:NominaIndividual'
        else:
            ns = 'dian:gov:co:facturaelectronica:NominaIndividualDeAjuste'
        xmlns = (
            'xmlns="%s" '
            'xmlns:xs="http://www.w3.org/2001/XMLSchema-instance" '
            'xmlns:ds="http://www.w3.org/2000/09/xmldsig#" '
            'xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" '
            'xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" '
            'xmlns:xades141="http://uri.etsi.org/01903/v1.4.1#" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
        ) % ns
        return xml_string.replace(
            'xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" '
            'xmlns:xades141="http://uri.etsi.org/01903/v1.4.1#" '
            'xmlns:ds="http://www.w3.org/2000/09/xmldsig#"',
            xmlns,
        )

    @api.model
    def _generate_signature_ref0(self, data_xml_document):
        """Ref0: SHA256 digest del documento completo (c14n)."""
        xml_c14n = etree.tostring(
            etree.fromstring(data_xml_document),
            method="c14n", exclusive=False, with_comments=False,
            inclusive_ns_prefixes=None,
        )
        digest = hashlib.new("sha256", xml_c14n).digest()
        return base64.b64encode(digest).decode()

    @api.model
    def _generate_signature_ref1(self, data_xml_keyinfo):
        """Ref1: SHA256 digest de KeyInfo (c14n)."""
        xml_c14n = etree.tostring(etree.fromstring(data_xml_keyinfo), method="c14n")
        digest = hashlib.new("sha256", xml_c14n).digest()
        return base64.b64encode(digest).decode()

    @api.model
    def _generate_signature_ref2(self, data_xml_signed_properties):
        """Ref2: SHA256 digest de SignedProperties (c14n)."""
        xml_c14n = etree.tostring(
            etree.fromstring(data_xml_signed_properties), method="c14n"
        )
        digest = hashlib.new("sha256", xml_c14n).digest()
        return base64.b64encode(digest).decode()

    @api.model
    def _generate_signature_value(self, signed_info_xml, company, exclusive=False):
        """Genera SignatureValue: RSA-SHA256 de SignedInfo canonicalizado."""
        xml_c14n = etree.tostring(
            etree.fromstring(signed_info_xml),
            method="c14n", exclusive=exclusive, with_comments=False,
        )
        key, _, _ = self.get_certificate_key(company)
        try:
            signature = key.sign(xml_c14n, padding.PKCS1v15(), hashes.SHA256())
        except Exception as ex:
            raise UserError(tools.ustr(ex))

        sig_value = base64.b64encode(signature).decode()

        # Verificar firma
        pem = self.get_certificate_pem(company)
        try:
            pem.public_key().verify(
                signature, xml_c14n, padding.PKCS1v15(), hashes.SHA256()
            )
        except InvalidSignature:
            raise ValidationError(_("Firma no fue validada exitosamente"))
        return sig_value

    @api.model
    def _generate_signature_politics(self):
        """Hash de la política de firma DIAN (constante)."""
        return "dMoMvtcG5aIzgYo0tIsSQeVJBDnUnfSOfBpxXrmor0Y="

    @api.model
    def _generate_signature_signingtime(self):
        """Hora de firma en zona horaria Colombia."""
        now_utc = datetime.now(timezone("UTC"))
        return now_utc.strftime("%Y-%m-%dT%H:%M:%S") + "-05:00"

    # ================================================================
    # SECCIÓN 7: CERTIFICADOS
    # ================================================================

    @api.model
    def get_certificate_key(self, company):
        """Carga la clave privada y certificado desde PKCS12."""
        password = company.certificate_key_payroll
        try:
            archivo = base64.b64decode(company.certificate_file_payroll)
            key, cert, additional = load_key_and_certificates(
                archivo, password.encode(), backend=default_backend()
            )
            return key, cert, additional
        except Exception as ex:
            raise UserError(tools.ustr(ex))

    @api.model
    def get_certificate_pem(self, company):
        """Carga el certificado PEM público."""
        try:
            archivo = base64.b64decode(company.pem_file_payroll)
            return x509.load_pem_x509_certificate(archivo, default_backend())
        except Exception as ex:
            raise UserError(tools.ustr(ex))

    @api.model
    def generate_cert_digest(self, company):
        """SHA256 digest del certificado DER para CertDigestDigestValue."""
        pem = self.get_certificate_pem(company)
        cert_der = pem.public_bytes(serialization.Encoding.DER)
        digest = hashlib.sha256(cert_der).digest()
        return base64.b64encode(digest).decode()

    # ================================================================
    # SECCIÓN 8: ZIP / PACKAGING
    # ================================================================

    @api.model
    def create_zip_package(self, xml_filename, zip_filename, xml_content, repo_path):
        """Crea el ZIP con el XML y retorna el contenido en base64."""
        xml_path = os.path.join(repo_path, xml_filename)
        zip_path = os.path.join(repo_path, zip_filename)
        with open(xml_path, "w") as f:
            f.write(str(xml_content))
        zf = zipfile.ZipFile(zip_path, mode="w")
        try:
            zf.write(xml_path, xml_filename, compress_type=compression)
        finally:
            zf.close()
        with open(zip_path, "rb") as f:
            return base64.b64encode(f.read()).decode()

    @api.model
    def generate_xml_filename(self, payslip):
        """Genera nombre del archivo XML según Anexo Técnico Sección 3.3/3.4."""
        if not payslip.name_xml:
            seq = (
                self.env["ir.sequence"].next_by_code("hr.payslip.sequence_documents_xml")
                or "00000001"
            )
            code_hex = ("%02x" % int(seq)).zfill(10)
            emisor_vat = payslip._get_emisor().vat_co
            year = payslip.date_to.strftime("%y")
            if payslip._get_tipo_xml() == "102":
                name = "nie{}{}{}.xml".format(emisor_vat, year, code_hex)
            else:
                name = "niae{}{}{}.xml".format(emisor_vat, year, code_hex)
            payslip.name_xml = name
        return payslip.name_xml

    @api.model
    def generate_zip_filename(self, payslip):
        """Genera nombre del archivo ZIP."""
        seq = (
            self.env["ir.sequence"].next_by_code("hr.payslip.sequence_documents_zip")
            or "00000001"
        )
        code_hex = ("%02x" % int(seq)).zfill(10)
        return "z{}{}{}.zip".format(
            payslip._get_emisor().vat_co,
            payslip.date_to.strftime("%y"),
            code_hex,
        )

    # ================================================================
    # SECCIÓN 9: SOAP COMMUNICATION
    # ================================================================

    @api.model
    def generate_soap_envelope(self, action, endpoint, vals):
        """Genera SOAP envelope parametrizado por action + endpoint."""
        if action not in _SOAP_BODIES:
            raise UserError(_("Acción SOAP no válida: %s") % action)
        soap_vals = dict(vals)
        soap_vals['SoapAction'] = _SOAP_ACTIONS[action]
        soap_vals['Endpoint'] = endpoint
        soap_vals['SoapBody'] = _SOAP_BODIES[action] % vals
        return _SOAP_ENVELOPE % soap_vals

    @api.model
    def sign_soap_envelope(self, soap_xml, company):
        """
        Firma el envelope SOAP: genera DigestValue del To y SignatureValue.
        """
        parser = etree.XMLParser(remove_blank_text=True)
        soap_xml = etree.tostring(etree.XML(soap_xml, parser=parser)).decode()

        # DigestValue del elemento To
        root = etree.fromstring(soap_xml)
        header = etree.tostring(root[0])
        header_el = etree.fromstring(header)
        element_to = etree.tostring(header_el[2])
        digest_to = self._generate_digestvalue_to(element_to)
        soap_xml = soap_xml.replace(
            "<ds:DigestValue/>",
            "<ds:DigestValue>%s</ds:DigestValue>" % digest_to,
        )

        # SignatureValue de SignedInfo
        root = etree.fromstring(soap_xml)
        signed_info = etree.tostring(root[0])
        signed_info = etree.tostring(etree.fromstring(signed_info)[0])
        signed_info = etree.tostring(etree.fromstring(signed_info)[2])
        signed_info = etree.tostring(etree.fromstring(signed_info)[0]).decode()

        # Normalizar namespaces del SignedInfo
        signed_info = signed_info.replace(
            '<ds:SignedInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#" '
            'xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd" '
            'xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd" '
            'xmlns:wsa="http://www.w3.org/2005/08/addressing" '
            'xmlns:soap="http://www.w3.org/2003/05/soap-envelope" '
            'xmlns:wcf="http://wcf.dian.colombia">',
            '<ds:SignedInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#" '
            'xmlns:soap="http://www.w3.org/2003/05/soap-envelope" '
            'xmlns:wcf="http://wcf.dian.colombia" '
            'xmlns:wsa="http://www.w3.org/2005/08/addressing">',
        )

        sig_value = self._generate_signature_value(
            signed_info, company, exclusive=False
        )
        soap_xml = soap_xml.replace(
            "<ds:SignatureValue/>",
            "<ds:SignatureValue>%s</ds:SignatureValue>" % sig_value,
        )
        return soap_xml

    @api.model
    def _generate_digestvalue_to(self, element_to):
        """SHA256 digest del elemento To (c14n)."""
        c14n = etree.tostring(etree.fromstring(element_to), method="c14n")
        digest = hashlib.new("sha256", c14n).digest()
        return base64.b64encode(digest).decode()

    @api.model
    def _get_dian_url(self, company):
        """Retorna URL del web service DIAN según ambiente."""
        return (
            SERVER_URL["PRODUCCION"]
            if company.production_payroll
            else SERVER_URL["TEST"]
        )

    @api.model
    def _send_http_request(self, url, data):
        """Envía HTTP POST al web service DIAN."""
        headers = {"content-type": "application/soap+xml"}
        try:
            response = requests.post(url, data=data, headers=headers)
        except Exception:
            raise ValidationError(
                _("No existe comunicación con la DIAN. "
                  "Por favor, revise su red o el acceso a internet.")
            )
        if response.status_code != 200:
            error_map = {
                500: "Error 500 = Error de servidor interno.",
                503: "Error 503 = Servicio no disponible.",
                507: "Error 507 = Espacio insuficiente.",
                508: "Error 508 = Ciclo detectado.",
            }
            msg = error_map.get(
                response.status_code,
                "Se ha producido un error de comunicación con la DIAN."
            )
            raise ValidationError(_(msg))
        return response

    # ================================================================
    # SECCIÓN 10: FLUJO COMPLETO DE ENVÍO
    # ================================================================

    @api.model
    def send_to_dian(self, payslip):
        """
        Flujo completo de envío de nómina electrónica a la DIAN.
        Orquesta todo: validación → XML → firma → ZIP → SOAP → envío → respuesta.
        """
        company = payslip.company_id

        # 1. Validar
        self.validate_all(payslip)

        # 2. Verificar si ya fue enviado exitosamente
        if payslip.ZipKey:
            result = self.check_existence(payslip)
            if result.get("result_verify_status"):
                return

        # 3. Constantes DIAN
        dian_constants = self.get_dian_constants(payslip)

        # 4. Generar CUNE
        cune = self.generate_cune(payslip, dian_constants)
        dian_constants['CUNE'] = cune
        payslip.current_cune = cune

        # 5. Generar XML del documento
        if payslip.credit_note:
            previous_payslip = self._find_previous_payslip(payslip)
            data_xml = self.generate_nomina_ajuste(
                payslip, dian_constants, previous_payslip
            )
        else:
            data_xml = self.generate_nomina_individual(payslip, dian_constants)

        # 6. Preparar para firma
        parser = etree.XMLParser(remove_blank_text=True)
        data_xml = etree.tostring(
            etree.XML(data_xml.encode('utf-8'), parser=parser)
        ).decode()

        data_xml = data_xml.replace(
            "<ext:ExtensionContent/>",
            "<ext:ExtensionContent></ext:ExtensionContent>",
        )

        # 7. Firmar documento
        data_constants_doc = self.generate_data_constants_document(payslip, dian_constants)
        signature = self.sign_document(data_xml, dian_constants, data_constants_doc)
        # NO reformatear la firma - puede cambiar el SignedInfo y romper la verificación

        data_xml = data_xml.replace(
            "<ext:ExtensionContent></ext:ExtensionContent>",
            "<ext:ExtensionContent>%s</ext:ExtensionContent>" % signature,
        )
        data_xml = '<?xml version="1.0" encoding="UTF-8"?>' + data_xml

        # 8. Crear ZIP
        zip_content = self.create_zip_package(
            data_constants_doc["FileNameXML"],
            data_constants_doc["FileNameZIP"],
            data_xml,
            dian_constants["document_repository"],
        )
        payslip.name_xml = data_constants_doc["FileNameXML"]
        payslip.name_zip = data_constants_doc["FileNameZIP"]

        # 9. Preparar SOAP
        timestamp = self._generate_datetime_timestamp()
        soap_vals = {
            'identifier': str(data_constants_doc["identifier"]),
            'Created': timestamp["Created"],
            'Expires': timestamp["Expires"],
            'Certificate': dian_constants["Certificate"],
            'identifierSecurityToken': str(uuid.uuid4()),
            'identifierTo': str(uuid.uuid4()),
            'fileName': data_constants_doc["FileNameZIP"][:-4],
            'contentFile': zip_content,
            'testSetId': company.identificador_set_pruebas_payroll or '',
        }

        is_production = company.production_payroll
        action = 'SendNominaSync' if is_production else 'SendTestSetAsync'
        endpoint = self._get_dian_url(company)
        soap_xml = self.generate_soap_envelope(action, endpoint, soap_vals)

        # 10. Firmar SOAP
        soap_xml = self.sign_soap_envelope(soap_xml, company)

        # 11. Enviar
        response = self._send_http_request(endpoint, soap_xml)

        # 12. Parsear respuesta
        result = self.parse_send_response(response, is_production)

        # 13. Actualizar payslip
        payslip.xml_sended = data_xml
        payslip.xml_response_dian = response.content
        payslip.xml_send_query_dian = soap_xml
        payslip.response_message_dian = result.get('message', '')
        if result.get('ZipKey'):
            payslip.ZipKey = result['ZipKey']
        payslip.write({
            'state_dian': result.get('state_dian', 'error'),
            'resend': result.get('resend', False),
        })
        if result.get('state_dian') == 'exitoso':
            payslip.write({'state': 'done'})

        # 14. Registrar log
        EdiLog = self.env['hr.payslip.edi.log']
        dian_code = result.get('dian_code', '')
        if dian_code:
            EdiLog.log_dian_response_with_help(
                payslip, dian_code, result.get('message', ''),
                raw_response=response.content.decode('utf-8', errors='replace')[:5000]
                if isinstance(response.content, bytes) else str(response.content)[:5000],
            )
        else:
            EdiLog.log_send(
                payslip,
                success=result.get('state_dian') in ('exitoso', 'por_validar'),
                message=result.get('message', ''),
            )

    @api.model
    def _find_previous_payslip(self, payslip):
        """Busca la nómina anterior por previous_cune."""
        model = self.env[payslip._name]
        previous = model.search(
            [("current_cune", "=", payslip.previous_cune)], limit=1
        )
        if not previous:
            raise UserError(_("No se encontró ninguna nómina asociada al CUNE anterior"))
        return previous

    # ================================================================
    # SECCIÓN 11: STATUS CHECKING
    # ================================================================

    @api.model
    def check_status(self, payslip):
        """
        Consulta estado del documento en DIAN (GetStatusZip).
        Actualiza state_dian según respuesta.
        """
        company = payslip.company_id
        dian_constants = self.get_dian_constants(payslip)
        endpoint = self._get_dian_url(company)

        timestamp = self._generate_datetime_timestamp()
        soap_vals = {
            'identifier': str(uuid.uuid4()),
            'Created': timestamp["Created"],
            'Expires': timestamp["Expires"],
            'Certificate': dian_constants["Certificate"],
            'identifierSecurityToken': str(uuid.uuid4()),
            'identifierTo': str(uuid.uuid4()),
            'trackId': payslip.ZipKey,
        }

        soap_xml = self.generate_soap_envelope('GetStatusZip', endpoint, soap_vals)
        soap_xml = self.sign_soap_envelope(soap_xml, company)

        response = self._send_http_request(endpoint, soap_xml)
        response_dict = xmltodict.parse(response.content)

        status_code = (
            response_dict["s:Envelope"]["s:Body"]["GetStatusZipResponse"]
            ["GetStatusZipResult"]["b:DianResponse"]["b:StatusCode"]
        )

        if status_code == "00":
            payslip.response_message_dian = (
                (payslip.response_message_dian or "")
                + "- Respuesta consulta estado: Procesado correctamente\n"
            )
            payslip.write({"state_dian": "exitoso", "resend": False, 'state': 'done'})
        elif status_code == "90":
            payslip.response_message_dian = (
                (payslip.response_message_dian or "")
                + "- Respuesta consulta estado: TrackId no encontrado\n"
            )
            payslip.write({"state_dian": "por_validar", "resend": False})
        elif status_code == "99":
            payslip.response_message_dian = (
                (payslip.response_message_dian or "")
                + "- Respuesta consulta estado: Errores en campos mandatorios\n"
            )
            payslip.write({"state_dian": "rechazado", "resend": True})
        elif status_code == "66":
            payslip.response_message_dian = (
                (payslip.response_message_dian or "")
                + "- Respuesta consulta estado: NSU no encontrado\n"
            )
            payslip.write({"state_dian": "por_validar", "resend": False})

        payslip.xml_response_dian = response.content
        payslip.xml_send_query_dian = soap_xml

    @api.model
    def check_existence(self, payslip):
        """Verifica si el documento ya existe en DIAN (GetStatus)."""
        company = payslip.company_id
        dian_constants = self.get_dian_constants(payslip)
        endpoint = self._get_dian_url(company)

        timestamp = self._generate_datetime_timestamp()
        soap_vals = {
            'identifier': str(uuid.uuid4()),
            'Created': timestamp["Created"],
            'Expires': timestamp["Expires"],
            'Certificate': dian_constants["Certificate"],
            'identifierSecurityToken': str(uuid.uuid4()),
            'identifierTo': str(uuid.uuid4()),
            'trackId': payslip.ZipKey,
        }

        soap_xml = self.generate_soap_envelope('GetStatus', endpoint, soap_vals)
        soap_xml = self.sign_soap_envelope(soap_xml, company)
        response = self._send_http_request(endpoint, soap_xml)
        response_dict = xmltodict.parse(response.content)

        result = {"result_verify_status": False}
        status_code = (
            response_dict["s:Envelope"]["s:Body"]["GetStatusResponse"]
            ["GetStatusResult"]["b:StatusCode"]
        )
        result["result_verify_status"] = (status_code == "00")
        result["response_message_dian"] = (
            status_code + " "
            + response_dict["s:Envelope"]["s:Body"]["GetStatusResponse"]
              ["GetStatusResult"]["b:StatusDescription"] + "\n"
        )
        result["ZipKey"] = (
            response_dict["s:Envelope"]["s:Body"]["GetStatusResponse"]
            ["GetStatusResult"]["b:XmlDocumentKey"]
        )
        return result

    # ================================================================
    # SECCIÓN 12: RESPONSE HANDLING
    # ================================================================

    @api.model
    def parse_send_response(self, response, is_production):
        """Parsea la respuesta del envío a DIAN.

        Mapea codigos de respuesta del proveedor y DIAN:
        200/299 = Exitoso | 201/208 = Por validar | 202-204 = Inconsistencia
        101/109-111 = Error formato | 99/2/63 = Rechazado DIAN
        """
        from odoo.addons.lavish_hr_payroll_edi.models.hr_payslip_edi_log import DIAN_RESPONSE_CODES

        response_dict = xmltodict.parse(response.content)
        result = {'message': '', 'state_dian': 'error', 'resend': True}

        if is_production:
            body = response_dict["s:Envelope"]["s:Body"]
            sync = body["SendNominaSyncResponse"]["SendNominaSyncResult"]
            status_code = str(sync.get("b:StatusCode", "")).strip()
            status_desc = sync.get("b:StatusDescription", "")
            status_msg = sync.get("b:StatusMessage", "")

            result['message'] = "{} {}\n{}".format(
                status_code, status_desc, status_msg,
            )
            result['ZipKey'] = sync.get("b:XmlDocumentKey")
            result['dian_code'] = status_code

            # Buscar en mapeo de codigos conocidos
            code_info = DIAN_RESPONSE_CODES.get(status_code)
            if code_info:
                result['state_dian'] = code_info['state_dian']
                result['resend'] = code_info['state_dian'] not in ('exitoso', 'por_validar')
                if code_info['state_dian'] == 'exitoso' and "ha sido autorizada" in status_msg:
                    result['message'] = status_msg
            elif status_code == "00":
                result['state_dian'] = 'exitoso'
                result['resend'] = False
                if "ha sido autorizada" in status_msg:
                    result['message'] = status_msg
            else:
                result['state_dian'] = 'rechazado'
                result['resend'] = True
        else:
            body = response_dict["s:Envelope"]["s:Body"]
            async_result = body["SendTestSetAsyncResponse"]["SendTestSetAsyncResult"]
            error_list = async_result.get("b:ErrorMessageList", {})
            zip_key = async_result.get("b:ZipKey")

            is_nil = False
            if isinstance(error_list, dict):
                is_nil = error_list.get("@i:nil") == "true" or error_list.get("i:nil") == "true"

            if is_nil:
                result['message'] = "- Respuesta envío: Documento enviado con éxito. Falta validar su estado\n"
                result['state_dian'] = 'por_validar'
                result['resend'] = False
            else:
                result['message'] = "- Respuesta envío: Documento enviado con errores\n"
                result['state_dian'] = 'por_notificar'
                result['resend'] = True

            if zip_key:
                result['ZipKey'] = zip_key

        return result

    # ================================================================
    # SECCIÓN 13: RENDERIZADO QWEB
    # ================================================================

    def _render_template(self, template_id, vals):
        """Renderiza un template Qweb y limpia el XML resultante."""
        try:
            xml_content = self.env['ir.qweb'].render(template_id, vals)
            if isinstance(xml_content, str):
                xml_content = xml_content.encode('utf-8')
            parser = etree.XMLParser(remove_blank_text=True)
            root = etree.fromstring(xml_content, parser=parser)
            for elem in root.iter():
                if elem.text is not None:
                    elem.text = elem.text.strip()
                if elem.tail is not None:
                    elem.tail = elem.tail.strip()
            return etree.tostring(
                root, encoding='UTF-8', xml_declaration=True
            ).decode('UTF-8')
        except Exception as e:
            _logger.exception("Error generando XML nómina: %s", str(e))
            raise UserError(
                _("Error generando XML de nómina electrónica: %s") % str(e)
            )

    # ================================================================
    # SECCIÓN 14: PREPARACIÓN DE VALORES PARA TEMPLATES
    # ================================================================

    def _prepare_nomina_values(self, payslip, dc):
        """Construye el diccionario completo de valores para los templates Qweb."""
        employee = payslip._get_employee()
        employee_obj = payslip._get_employee_object()
        contract = payslip._get_contract()
        company = payslip._get_company_id()
        emisor = payslip._get_emisor()

        number_days = abs((contract.date_start - payslip.date_to).days)

        # FechaRetiro: se reporta a DIAN cuando hay liquidacion de contrato.
        # Es liquidacion si:
        # - is_liquidacion (contract.date_end dentro del periodo del slip), o
        # - alguna nomina de payslip_ids es de struct_process='contrato'
        slip_origen = payslip.parent_edi_id if payslip.credit_note and payslip.parent_edi_id else payslip
        es_liquidacion = slip_origen.is_liquidacion or any(
            p.struct_process == 'contrato' for p in slip_origen.payslip_ids
        )
        fecha_retiro = slip_origen.date_end_contract if es_liquidacion else None

        vals = {
            # === Periodo ===
            'FechaIngreso': str(contract.date_start),
            'FechaRetiro': str(fecha_retiro) if fecha_retiro else None,
            'FechaLiquidacionInicio': str(payslip.date_from),
            'FechaLiquidacionFin': str(payslip.date_to),
            'TiempoLaborado': str(number_days),
            'FechaGen': dc.get('FechaGen'),

            # === NumeroSecuenciaXML ===
            'CodigoTrabajador': employee.vat_co,
            'Prefijo': dc.get('Prefix'),
            'Consecutivo': dc.get('Consecutivo'),
            'Numero': dc.get('Number'),

            # === LugarGeneracionXML ===
            'PaisGeneracion': str(company.partner_id.country_id.code or ''),
            'DepartamentoGeneracion': str(company.partner_id.state_id.code_dian),
            'MunicipioGeneracion': str(company.partner_id.city_id.code),

            # === ProveedorXML ===
            'ProveedorRazonSocial': emisor.name,
            'ProveedorPrimerApellido': emisor.first_lastname,
            'ProveedorSegundoApellido': emisor.second_lastname,
            'ProveedorPrimerNombre': emisor.first_name,
            'ProveedorOtrosNombres': emisor.second_name,
            'ProveedorNIT': emisor.vat_co,
            'ProveedorDV': emisor.dv,
            'SoftwareID': dc.get('SoftwareID'),
            'SoftwareSC': dc.get('SoftwareSecurityCode'),

            # === CodigoQR ===
            'CodigoQR': payslip._get_url_qr() + dc.get('CUNE', ''),

            # === InformacionGeneral ===
            'Version': 'V1.0: Documento Soporte de Pago de Nómina Electrónica',
            'Ambiente': payslip._get_tipo_ambiente(),
            'TipoXML': payslip._get_tipo_xml(),
            'CUNE': dc.get('CUNE', ''),
            'HoraGen': dc.get('HoraGen'),
            'PeriodoNomina': '5',
            'TipoMoneda': 'COP',
            'TRM': '0',

            # === Notas ===
            'Notas': str(payslip._get_notes()),

            # === Empleador ===
            'EmpleadorRazonSocial': emisor.name,
            'EmpleadorPrimerApellido': emisor.first_lastname,
            'EmpleadorSegundoApellido': emisor.second_lastname,
            'EmpleadorPrimerNombre': emisor.first_name,
            'EmpleadorOtrosNombres': emisor.second_name,
            'EmpleadorNIT': emisor.vat_co,
            'EmpleadorDV': str(emisor.dv),
            'EmpleadorPais': str(emisor.country_id.code),
            'EmpleadorDepartamento': str(emisor.state_id.code_dian),
            'EmpleadorMunicipio': str(company.partner_id.city_id.code),
            'EmpleadorDireccion': str(emisor.street),

            # === Trabajador ===
            'TipoTrabajador': employee_obj.tipo_coti_id.code,
            'SubTipoTrabajador': payslip.get_subtipo_trabajador(),
            'AltoRiesgoPension': 'false',
            'TipoDocumento': payslip.return_number_document_type(
                employee.l10n_latam_identification_type_id.l10n_co_document_code),
            'NumeroDocumento': employee.vat_co,
            'TrabajadorPrimerApellido': employee.first_lastname,
            'TrabajadorSegundoApellido': employee.second_lastname,
            'TrabajadorPrimerNombre': employee.first_name,
            'TrabajadorOtrosNombres': employee.second_name,
            'LugarTrabajoPais': employee.country_id.code,
            'LugarTrabajoDepartamento': employee.state_id.code_dian,
            'LugarTrabajoMunicipio': employee.city_id.code,
            'LugarTrabajoDireccion': employee.street,
            'SalarioIntegral': payslip._integral(contract.modality_salary),
            'TipoContrato': payslip.type_contract_e(
                contract.contract_type_id.contract_category
                if contract.contract_type_id else False),
            'Sueldo': '{:.2f}'.format(contract.wage),

            # === Pago ===
            'PagoForma': contract.way_pay_id.code,
            'PagoMetodo': contract.payment_method_dian_id.code,
            'PagoBanco': self._get_banco(payslip, contract),
            'PagoTipoCuenta': self._get_tipo_cuenta(payslip, contract),
            'PagoNumeroCuenta': self._get_numero_cuenta(payslip, contract),

            # === FechasPagos ===
            'FechaPago': str(payslip.payment_date),
            'FechasPagos': [str(payslip.payment_date)],

            # === Novedad ===
            'Novedad': None,

            # === Totales ===
            'DevengadosTotal': abs(float(payslip._get_total_devengados())),
            'DeduccionesTotal': abs(float(payslip._get_total_deducciones())),
            'ComprobanteTotal': abs(float(payslip._get_total_pagado())),
            'Redondeo': None,
        }

        vals.update(self._build_devengados(payslip))
        vals.update(self._build_deducciones(payslip))
        vals.update(self._build_informativos(payslip))
        return vals

    # ================================================================
    # SECCIÓN 15: CONSTRUCCIÓN DE DEVENGADOS
    # ================================================================

    def _build_devengados(self, payslip):
        """Transforma nes_dev_line_ids en diccionarios para el template Qweb."""
        result = {
            'Basico': None, 'Transporte': None,
            'HEDs': [], 'HENs': [], 'HRNs': [],
            'HEDDFs': [], 'HRDDFs': [], 'HENDFs': [], 'HRNDFs': [],
            'VacacionesComunes': [], 'VacacionesCompensadas': [],
            'Primas': None, 'Cesantias': None,
            'Incapacidades': [], 'LicenciasMP': [], 'LicenciasR': [],
            'LicenciasNR': [],
            'Bonificaciones': [], 'Auxilios': [],
            'HuelgasLegales': [], 'OtrosConceptos': [],
            'Compensaciones': [], 'BonoEPCTVs': [],
            'Comisiones': [], 'DevPagosTerceros': [],
            'DevAnticipos': [],
            'Dotacion': None, 'ApoyoSost': None, 'Teletrabajo': None,
            'BonifRetiro': None, 'Indemnizacion': None, 'DevReintegro': None,
        }

        bogota = timezone('America/Bogota')
        hora_inicio = (
            datetime.combine(payslip.date_from, datetime.min.time())
            .astimezone(bogota).strftime("%Y-%m-%dT%H:%M:%S")
            if payslip.date_from else None
        )
        hora_fin = (
            datetime.combine(payslip.date_to, datetime.min.time())
            .astimezone(bogota).strftime("%Y-%m-%dT%H:%M:%S")
            if payslip.date_to else None
        )

        transporte_data = {}

        for dev in payslip.nes_dev_line_ids.filtered(lambda l: l.line_type != 'informativo'):
            # Usar codigo de la regla de devengado DIAN, no el codigo de la regla salarial
            devengado_rule = dev.salary_rule_id.devengado_rule_id
            code = devengado_rule.code if devengado_rule else dev.code
            total = abs(dev.total or 0)
            qty = dev.quantity or 0

            if code in ('Basico', 'Sueldo'):
                # XSD V1.0.6: <Basico>. Nuestra rule data usa code='Sueldo'
                # (mapping SALARY_TO_DIAN_ACCRUED['BASIC*']='Sueldo').
                result['Basico'] = {
                    'DiasTrabajados': str(int(min(qty, 30))),
                    'SueldoTrabajado': '{:.2f}'.format(total),
                }
            elif code in ('Transporte', 'AuxilioTransporte', 'AUX-TRANSP',
                          'Viaticos', 'ViaticoManuAlojS', 'ViaticoManutAlojS',
                          'ViaticosNS', 'ViaticoManuAlojNS', 'ViaticoManutAlojNS'):
                # XSD V1.0.6: <Transporte> con atributos AuxilioTransporte,
                # ViaticoManuAlojS, ViaticoManuAlojNS. Acepta variantes de
                # codigo de regla (Transporte vs AUX-TRANSP heredado).
                if code in ('Transporte', 'AuxilioTransporte', 'AUX-TRANSP'):
                    transporte_data['AuxilioTransporte'] = '{:.2f}'.format(total)
                elif code in ('Viaticos', 'ViaticoManuAlojS', 'ViaticoManutAlojS'):
                    transporte_data['ViaticoManuAlojS'] = '{:.2f}'.format(total)
                elif code in ('ViaticosNS', 'ViaticoManuAlojNS', 'ViaticoManutAlojNS'):
                    transporte_data['ViaticoManuAlojNS'] = '{:.2f}'.format(total)
            elif code == 'HED':
                result['HEDs'].append(self._hora_extra(dev, hora_inicio, hora_fin, '25.00'))
            elif code == 'HEN':
                result['HENs'].append(self._hora_extra(dev, hora_inicio, hora_fin, '75.00'))
            elif code == 'HRN':
                result['HRNs'].append(self._hora_extra(dev, hora_inicio, hora_fin, '35.00'))
            elif code == 'HEDDF':
                result['HEDDFs'].append(self._hora_extra(dev, hora_inicio, hora_fin, '100.00'))
            elif code == 'HRDDF':
                result['HRDDFs'].append(self._hora_extra(dev, hora_inicio, hora_fin, '75.00'))
            elif code == 'HENDF':
                result['HENDFs'].append(self._hora_extra(dev, hora_inicio, hora_fin, '150.00'))
            elif code == 'HRNDF':
                result['HRNDFs'].append(self._hora_extra(dev, hora_inicio, hora_fin, '110.00'))
            elif code == 'VacacionesComunes':
                vac = {'Cantidad': str(int(qty)), 'Pago': '{:.2f}'.format(total)}
                if dev.leave_id:
                    vac['FechaInicio'] = str(dev.leave_id.request_date_from or payslip.date_from)
                    vac['FechaFin'] = str(dev.leave_id.request_date_to or payslip.date_to)
                else:
                    vac['FechaInicio'] = str(payslip.date_from)
                    vac['FechaFin'] = str(payslip.date_to)
                result['VacacionesComunes'].append(vac)
            elif code == 'VacacionesCompensadas':
                result['VacacionesCompensadas'].append({
                    'Cantidad': str(int(qty)), 'Pago': '{:.2f}'.format(total),
                })
            elif code == 'Primas':
                result['Primas'] = {
                    'Cantidad': str(int(qty)), 'Pago': '{:.2f}'.format(total),
                    'PagoNS': '{:.2f}'.format(dev.total_2) if dev.total_2 else None,
                }
            elif code == 'Cesantias':
                # Porcentaje del nodo Cesantias = % intereses cesantias del periodo.
                # hr.payslip.interest_cesantias_percentage esta en decimal
                # (ej: 0.1207 = 12.07%). DIAN espera multiplo de 100 -> *100.
                pcts = payslip.payslip_ids.mapped('interest_cesantias_percentage')
                pct_intereses = (max(pcts) if pcts else 0) * 100
                if result['Cesantias'] is None:
                    result['Cesantias'] = {
                        'Pago': '{:.2f}'.format(total),
                        'Porcentaje': '{:.2f}'.format(pct_intereses),
                        'PagoIntereses': '{:.2f}'.format(abs(round(dev.total_2 or 0))),
                    }
                else:
                    # Acumular si ya existe (multiples lineas cesantias)
                    pago_actual = float(result['Cesantias']['Pago'])
                    result['Cesantias']['Pago'] = '{:.2f}'.format(pago_actual + total)
                    if dev.total_2:
                        int_actual = float(result['Cesantias']['PagoIntereses'])
                        result['Cesantias']['PagoIntereses'] = '{:.2f}'.format(
                            int_actual + abs(round(dev.total_2 or 0)))
            elif code == 'IntCesantias':
                # Intereses de cesantias: fusionar en nodo Cesantias como PagoIntereses
                # Normalmente ya fusionado por _consolidate_lines, pero por seguridad.
                # Porcentaje en decimal -> *100 para DIAN.
                pcts = payslip.payslip_ids.mapped('interest_cesantias_percentage')
                pct_intereses = (max(pcts) if pcts else 0) * 100
                if result['Cesantias'] is None:
                    result['Cesantias'] = {
                        'Pago': '0.00',
                        'Porcentaje': '{:.2f}'.format(pct_intereses),
                        'PagoIntereses': '{:.2f}'.format(total),
                    }
                else:
                    int_actual = float(result['Cesantias'].get('PagoIntereses', '0.00'))
                    result['Cesantias']['PagoIntereses'] = '{:.2f}'.format(int_actual + total)
                    if not float(result['Cesantias'].get('Porcentaje', '0')):
                        result['Cesantias']['Porcentaje'] = '{:.2f}'.format(pct_intereses)
            elif code == 'Incapacidades':
                try:
                    tipo_inc = str(dev.salary_rule_id.type_incapacidad or '1')
                except (AttributeError, KeyError):
                    tipo_inc = '1'
                inc = {
                    'Cantidad': str(int(qty)),
                    'Tipo': tipo_inc,
                    'Pago': '{:.2f}'.format(total),
                }
                if dev.leave_id:
                    inc['FechaInicio'] = str(dev.leave_id.request_date_from or payslip.date_from)
                    inc['FechaFin'] = str(dev.leave_id.request_date_to or payslip.date_to)
                result['Incapacidades'].append(inc)
            elif code in ('Licencias', 'LicenciaNR', 'LicenciaR', 'LicenciaMP'):
                cat_code = (dev.salary_rule_id.category_id.code
                            if dev.salary_rule_id.category_id else '')
                rule_code = dev.salary_rule_id.code or ''
                is_nr = (code == 'LicenciaNR'
                         or cat_code == 'LICENCIA_NO_REMUNERADA'
                         or 'NO_REMUNERADA' in rule_code.upper())
                if is_nr:
                    lic = {'Cantidad': str(int(qty))}
                    if dev.leave_id:
                        lic['FechaInicio'] = str(dev.leave_id.request_date_from or payslip.date_from)
                        lic['FechaFin'] = str(dev.leave_id.request_date_to or payslip.date_to)
                    result['LicenciasNR'].append(lic)
                else:
                    lic = {'Cantidad': str(int(qty)), 'Pago': '{:.2f}'.format(total)}
                    if dev.leave_id:
                        lic['FechaInicio'] = str(dev.leave_id.request_date_from or payslip.date_from)
                        lic['FechaFin'] = str(dev.leave_id.request_date_to or payslip.date_to)
                    if cat_code == 'LICENCIA_MATERNIDAD' or code == 'LicenciaMP':
                        result['LicenciasMP'].append(lic)
                    else:
                        result['LicenciasR'].append(lic)
            elif code in ('BonificacionS', 'BonificacionNS'):
                bon = {}
                if code == 'BonificacionS':
                    bon['BonificacionS'] = '{:.2f}'.format(total)
                else:
                    bon['BonificacionNS'] = '{:.2f}'.format(total)
                result['Bonificaciones'].append(bon)
            elif code in ('AuxilioS', 'AuxilioNS'):
                aux = {}
                if code == 'AuxilioS':
                    aux['AuxilioS'] = '{:.2f}'.format(total)
                else:
                    aux['AuxilioNS'] = '{:.2f}'.format(total)
                result['Auxilios'].append(aux)
            elif code in ('ConceptoS', 'ConceptoNS', 'OtrosConceptos'):
                oc = {'DescripcionConcepto': dev.name or dev.salary_rule_id.name or ''}
                if code == 'ConceptoNS':
                    oc['ConceptoNS'] = '{:.2f}'.format(total)
                else:
                    oc['ConceptoS'] = '{:.2f}'.format(total)
                result['OtrosConceptos'].append(oc)
            elif code == 'Comision':
                result['Comisiones'].append(total)
            elif code == 'PagoTercero':
                result['DevPagosTerceros'].append(total)
            elif code == 'Anticipo':
                result['DevAnticipos'].append(total)
            elif code == 'Dotacion':
                result['Dotacion'] = total
            elif code == 'ApoyoSost':
                result['ApoyoSost'] = total
            elif code == 'Teletrabajo':
                result['Teletrabajo'] = total
            elif code == 'BonifRetiro':
                result['BonifRetiro'] = total
            elif code == 'Indemnizacion':
                result['Indemnizacion'] = total
            elif code == 'Reintegro':
                result['DevReintegro'] = total

        if transporte_data:
            result['Transporte'] = transporte_data

        for key in list(result.keys()):
            if isinstance(result[key], list) and not result[key]:
                result[key] = None

        return result

    # ================================================================
    # SECCIÓN 16: CONSTRUCCIÓN DE DEDUCCIONES
    # ================================================================

    def _build_deducciones(self, payslip):
        """Transforma nes_ded_line_ids en diccionarios para el template."""
        result = {
            'Salud': {'Porcentaje': '0.00', 'Deduccion': '0.00'},
            'FondoPension': {'Porcentaje': '0.00', 'Deduccion': '0.00'},
            'FondoSP': None, 'Sindicatos': [], 'Sanciones': [],
            'Libranzas': [], 'DedPagosTerceros': [], 'DedAnticipos': [],
            'OtrasDeducciones': [], 'PensionVoluntaria': None,
            'RetencionFuente': None, 'AFC': None, 'Cooperativa': None,
            'EmbargoFiscal': None, 'PlanComplementarios': None,
            'Educacion': None, 'DedReintegro': None, 'Deuda': None,
        }

        fondosp_porcentaje = fondosp_deduccion = 0.0
        fondosp_porcentaje_sub = fondosp_deduccion_sub = 0.0
        has_fondosp = False

        for ded in payslip.nes_ded_line_ids.filtered(lambda l: l.line_type != 'informativo'):
            # Usar codigo de la regla de deduccion DIAN, no el codigo de la regla salarial
            deduccion_rule = ded.salary_rule_id.deduccion_rule_id
            code = deduccion_rule.code if deduccion_rule else ded.code
            total = abs(ded.total or 0)
            rate = ded.rate_2

            if code in ('Salud', 'SSOCIAL001'):
                result['Salud'] = {
                    'Porcentaje': '{:.2f}'.format(abs(min(float(ded.rate or rate or 4.0), 4.00))),
                    'Deduccion': '{:.2f}'.format(total),
                }
            elif code in ('FondoPension', 'SSOCIAL002'):
                result['FondoPension'] = {
                    'Porcentaje': '{:.2f}'.format(abs(min(float(ded.rate or rate or 4.0), 4.00))),
                    'Deduccion': '{:.2f}'.format(total),
                }
            elif code in ('FondoSP', 'FondoSub'):
                has_fondosp = True
                is_fondosp = ded.salary_rule_id.deduccion_rule_id.code == 'FondoSP'
                if is_fondosp:
                    fondosp_porcentaje = max(fondosp_porcentaje, abs(ded.rate or 0))
                    fondosp_deduccion += abs(ded.total or 0)
                    fondosp_porcentaje_sub = max(fondosp_porcentaje_sub, abs(rate or 0))
                    fondosp_deduccion_sub += abs(ded.total_2 or 0)
                else:
                    fondosp_porcentaje = max(fondosp_porcentaje, abs(rate or 0))
                    fondosp_deduccion += abs(ded.total_2 or 0)
                    fondosp_porcentaje_sub = max(fondosp_porcentaje_sub, abs(ded.rate or 0))
                    fondosp_deduccion_sub += abs(ded.total or 0)
            elif code == 'Sindicatos':
                result['Sindicatos'].append({
                    'Porcentaje': '{:.2f}'.format(rate or 0),
                    'Deduccion': '{:.2f}'.format(total),
                })
            elif code == 'Libranza':
                result['Libranzas'].append({
                    'Descripcion': ded.name or '', 'Deduccion': '{:.2f}'.format(total),
                })
            elif code == 'PagoTercero':
                result['DedPagosTerceros'].append(total)
            elif code == 'Anticipo':
                result['DedAnticipos'].append(total)
            elif code == 'OtraDeduccion':
                result['OtrasDeducciones'].append(total)
            elif code == 'PensionVoluntaria':
                result['PensionVoluntaria'] = total
            elif code == 'RetencionFuente':
                result['RetencionFuente'] = total
            elif code == 'AFC':
                result['AFC'] = total
            elif code == 'Cooperativa':
                result['Cooperativa'] = total
            elif code == 'EmbargoFiscal':
                result['EmbargoFiscal'] = total
            elif code == 'PlanComplementarios':
                result['PlanComplementarios'] = total
            elif code == 'Educacion':
                result['Educacion'] = total
            elif code == 'Reintegro':
                result['DedReintegro'] = total
            elif code == 'Deuda':
                result['Deuda'] = total

        if has_fondosp:
            result['FondoSP'] = {
                'Porcentaje': '{:.2f}'.format(fondosp_porcentaje),
                'DeduccionSP': '{:.2f}'.format(fondosp_deduccion),
                'PorcentajeSub': '{:.2f}'.format(fondosp_porcentaje_sub),
                'DeduccionSub': '{:.2f}'.format(fondosp_deduccion_sub),
            }

        # Agregar sindicatos desde líneas informativas
        info_sindicatos = payslip.line_ids.filtered(
            lambda l: l.line_type == 'informativo' and l.info_type == 'sindicato' and l.amount
        )
        for info in info_sindicatos:
            result['Sindicatos'].append({
                'Porcentaje': '{:.2f}'.format(info.info_percentage or 0),
                'Deduccion': '{:.2f}'.format(abs(info.amount or 0)),
            })

        for key in list(result.keys()):
            if isinstance(result[key], list) and not result[key]:
                result[key] = None

        return result

    # ================================================================
    # SECCIÓN 16B: CONSTRUCCIÓN DE INFORMATIVOS
    # ================================================================

    def _build_informativos(self, payslip):
        """Construye información adicional desde líneas informativas."""
        result = {
            'InfoSindicatos': [],
            'InfoFondos': [],
            'InfoEntidades': [],
            'InfoAdicional': [],
        }

        # Obtener líneas informativas
        info_lines = payslip.line_ids.filtered(lambda l: l.line_type == 'informativo')

        for info in info_lines:
            info_type = info.info_type or 'otro'

            if info_type == 'sindicato':
                # Información de sindicato - puede usarse en deducciones
                result['InfoSindicatos'].append({
                    'Nombre': info.info_value or info.name,
                    'NIT': info.info_code or '',
                    'Porcentaje': '{:.2f}'.format(info.info_percentage or 0),
                    'Deduccion': '{:.2f}'.format(abs(info.amount or 0)),
                })
            elif info_type in ('fondo_pension', 'fondo_cesantias'):
                result['InfoFondos'].append({
                    'Tipo': 'Pensión' if info_type == 'fondo_pension' else 'Cesantías',
                    'Nombre': info.info_value or info.name,
                    'Codigo': info.info_code or '',
                })
            elif info_type in ('eps', 'arl', 'caja_compensacion'):
                result['InfoEntidades'].append({
                    'Tipo': info_type.upper().replace('_', ' '),
                    'Nombre': info.info_value or info.name,
                    'Codigo': info.info_code or '',
                })
            else:
                # Otros informativos
                result['InfoAdicional'].append({
                    'Descripcion': info.name,
                    'Valor': info.info_value or '',
                    'Codigo': info.info_code or '',
                    'Monto': '{:.2f}'.format(abs(info.amount or 0)) if info.amount else None,
                    'Notas': info.info_notes or '',
                })

        # Limpiar listas vacías
        for key in list(result.keys()):
            if isinstance(result[key], list) and not result[key]:
                result[key] = None

        return result

    # ================================================================
    # SECCIÓN 17: HELPERS
    # ================================================================

    def _hora_extra(self, dev, hora_inicio, hora_fin, porcentaje_default):
        """Construye dict para un elemento de hora extra.
        Si la linea NES tiene overtime_id, usa las fechas reales del registro de hora extra.
        """
        bogota = timezone('America/Bogota')
        # Usar fechas del registro de hora extra si existe
        if dev.overtime_id and dev.overtime_id.date:
            hora_inicio = dev.overtime_id.date.astimezone(bogota).strftime("%Y-%m-%dT%H:%M:%S")
        if dev.overtime_id and dev.overtime_id.date_end:
            hora_fin = dev.overtime_id.date_end.astimezone(bogota).strftime("%Y-%m-%dT%H:%M:%S")
        return {
            'HoraInicio': hora_inicio,
            'HoraFin': hora_fin,
            'Cantidad': str(int(dev.quantity or 0)),
            'Porcentaje': '{:.2f}'.format(
                dev.rate_2 if dev.rate_2 else float(porcentaje_default)),
            'Pago': '{:.2f}'.format(abs(dev.total or 0)),
        }

    def _get_banco(self, payslip, contract):
        if contract.payment_method_dian_id.code == '10':
            return None
        return payslip.get_bank_information(r_bank=1) or None

    def _get_tipo_cuenta(self, payslip, contract):
        if contract.payment_method_dian_id.code == '10':
            return None
        return payslip.get_bank_information(r_type=1) or None

    def _get_numero_cuenta(self, payslip, contract):
        if contract.payment_method_dian_id.code == '10':
            return None
        return payslip.get_bank_information(r_account=1) or None

    # ================================================================
    # SECCIÓN 18: MÉTODOS PÚBLICOS LEGACY (compatibilidad)
    # ================================================================

    @api.model
    def get_signature_template(self):
        """Retorna el template de firma digital."""
        return _SIGNATURE_TEMPLATE

    @api.model
    def generate_signature(self, vals):
        """Genera el bloque ds:Signature con los valores dados."""
        return _SIGNATURE_TEMPLATE % vals
