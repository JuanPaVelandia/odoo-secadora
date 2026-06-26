import logging
from datetime import datetime, timedelta
import uuid
import base64
import hashlib
import xmltodict
import requests
from lxml import etree
from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, ValidationError
from pytz import timezone
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa, ec
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12, load_pem_private_key, Encoding
from cryptography.hazmat.backends import default_backend
# Importaciones para compatibilidad con diferentes versiones
# from importlib import metadata ya no es necesario

_logger = logging.getLogger(__name__)

server_url = {
    "HABILITACION": "https://facturaelectronica.dian.gov.co/habilitacion/B2BIntegrationEngine/FacturaElectronica/facturaElectronica.wsdl",
    "PRODUCCION": "https://facturaelectronica.dian.gov.co/operacion/B2BIntegrationEngine/FacturaElectronica/facturaElectronica.wsdl",
    "HABILITACION_CONSULTA": "https://facturaelectronica.dian.gov.co/habilitacion/B2BIntegrationEngine/FacturaElectronica/consultaDocumentos.wsdl",
    "PRODUCCION_CONSULTA": "https://facturaelectronica.dian.gov.co/operacion/B2BIntegrationEngine/FacturaElectronica/consultaDocumentos.wsdl",
    "PRODUCCION_VP": "https://vpfe.dian.gov.co/WcfDianCustomerServices.svc?wsdl",
    "HABILITACION_VP": "https://vpfe-hab.dian.gov.co/WcfDianCustomerServices.svc?wsdl",
}

class ResCompanyInherit(models.Model):
    _inherit = "res.company"

    OPERATION_TYPE = [("09", "AIU"), ("10", "Estandar *"), ("11", "Mandatos")]

    def _get_dian_sequence(self):
        list_dian_sequence = []
        rec_dian_sequence = self.env["ir.sequence"].search(
            [
                ("company_id", "=", self.env.company.id),
                ("use_dian_control", "=", True),
                ("active", "=", True),
            ]
        )
        for sequence in rec_dian_sequence:
            list_dian_sequence.append((str(sequence.id), sequence.name))
        return list_dian_sequence

    # ===================================================================
    # CAMPOS PRINCIPALES DIAN
    # ===================================================================
    trade_name = fields.Char(string="Razón social", default="0")
    software_identification_code = fields.Char(string="Código de identificación del software", default="0")
    identificador_set_pruebas = fields.Char(string="Identificador del SET de pruebas")
    software_pin = fields.Char(string="PIN del software", default="0")
    password_environment = fields.Char(string="Clave de ambiente", default="0")
    seed_code = fields.Integer(string="Código de semilla", default=5000000)
    document_repository = fields.Char(string="Ruta de almacenamiento de archivos", default="0")
    in_use_dian_sequence = fields.Selection("_get_dian_sequence", "Secuenciador DIAN a utilizar", required=False)
    operation_type = fields.Selection(OPERATION_TYPE, string="Tipo de operación DIAN")
    production = fields.Boolean(string="Pase a producción", default=False)
    
    # ===================================================================
    # CAMPOS DE CERTIFICADOS (HOMOLOGADOS CON AUTO-EXTRACCIÓN)
    # ===================================================================
    digital_certificate = fields.Text(
        string="Certificado digital público", 
        compute="_compute_certificate_data", 
        store=True,
        help="Certificado en formato DER base64 (se extrae automáticamente del archivo P12)"
    )
    issuer_name = fields.Char(
        string="Ente emisor del certificado", 
        compute="_compute_certificate_data", 
        store=True,
        help="Nombre del emisor del certificado (se extrae automáticamente)"
    )
    serial_number = fields.Char(
        string="Serial del certificado", 
        compute="_compute_certificate_data", 
        store=True,
        help="Número de serie del certificado (se extrae automáticamente)"
    )
    certificate_key = fields.Char(string="Clave del certificado P12", default="0")
    certificate = fields.Char(string="Nombre del archivo del certificado", default="0")
    certificate_file = fields.Binary("Archivo del certificado (.p12/.pfx)")
    pem = fields.Char(
        string="Nombre del archivo PEM del certificado", 
        compute="_compute_certificate_data", 
        store=True,
        default="Certificate.pem"
    )
    pem_file = fields.Binary(
        "Archivo PEM", 
        compute="_compute_certificate_data", 
        store=True,
        help="Certificado en formato PEM (se extrae automáticamente del P12)"
    )
    
    # ===================================================================
    # CAMPOS ADICIONALES DE CERTIFICADO (COMPUTADOS)
    # ===================================================================
    certificate_subject_name = fields.Char(
        string="Nombre del Sujeto (CN)",
        compute='_compute_certificate_data',
        store=True,
        help="Nombre común extraído del certificado"
    )
    
    certificate_date_start = fields.Datetime(
        string="Válido Desde",
        compute='_compute_certificate_data',
        store=True,
        help="Fecha de inicio de validez del certificado (UTC)"
    )
    
    certificate_date_end = fields.Datetime(
        string="Válido Hasta", 
        compute='_compute_certificate_data',
        store=True,
        help="Fecha de expiración del certificado (UTC)"
    )
    
    certificate_is_valid = fields.Boolean(
        string="Certificado Válido",
        compute='_compute_certificate_validity',
        help="Indica si el certificado está dentro de su período de validez"
    )
    
    certificate_loading_error = fields.Text(
        string="Error de Carga",
        compute='_compute_certificate_data',
        store=True,
        help="Mensaje de error si el certificado no pudo ser cargado"
    )
    
    # ===================================================================
    # CAMPOS RESTANTES
    # ===================================================================
    xml_response_numbering_range = fields.Text(
        string="Contenido XML de la respuesta DIAN a la consulta de rangos",
        readonly=True,
    )
    numbering_ranges_html = fields.Html(
        string="Resoluciones DIAN (Tabla)",
        compute="_compute_numbering_ranges_html",
        store=False,
        help="Tabla HTML con las resoluciones DIAN configuradas"
    )
    in_contingency_4 = fields.Boolean(string="En contingencia", default=False)
    date_init_contingency_4 = fields.Datetime(string="Fecha de inicio de contingencia 4")
    date_end_contingency_4 = fields.Datetime(string="Fecha de fin de contingencia 4")
    exists_invoice_contingency_4 = fields.Boolean(
        string="Cantidad de facturas con contingencia 4 sin reportar a la DIAN",
        default=False,
    )
    sales_discount_account = fields.Many2one('account.account', string="Cuenta Descuento ventas")
    purchase_discount_account = fields.Many2one('account.account', string="Cuenta Descuento Compras")

    # ===================================================================
    # MÉTODOS DE AUTO-EXTRACCIÓN DE CERTIFICADOS
    # ===================================================================
    
    @api.depends('certificate_file', 'certificate_key')
    def _compute_certificate_data(self):
        """
        Método que extrae automáticamente todos los datos del certificado
        Homologado con el método button_extract_certificate del otro archivo
        """
        for record in self:
            if not record.certificate_file or not record.certificate_key or record.certificate_key == "0":
                record.digital_certificate = "0"
                record.issuer_name = "0"
                record.serial_number = "0"
                record.pem = "Certificate.pem"
                record.pem_file = False
                record.certificate_subject_name = None
                record.certificate_date_start = None
                record.certificate_date_end = None
                record.certificate_loading_error = ""
                continue

            try:
                password = record.certificate_key.encode('utf-8')

                # Validar y limpiar el base64 antes de decodificar
                cert_b64 = record.certificate_file
                if isinstance(cert_b64, str):
                    cert_b64 = cert_b64.strip()
                    # Remover espacios, saltos de línea y otros caracteres no base64
                    cert_b64 = ''.join(cert_b64.split())

                # Validar longitud base64 (debe ser múltiplo de 4)
                if len(cert_b64) % 4 != 0:
                    padding_needed = 4 - (len(cert_b64) % 4)
                    cert_b64 += '=' * padding_needed

                try:
                    p12_data = base64.b64decode(cert_b64)
                except Exception as decode_error:
                    record.certificate_loading_error = f"Error decodificando base64: {str(decode_error)}. Verifique que el archivo cargado sea un certificado P12/PFX válido."
                    record.digital_certificate = "0"
                    record.issuer_name = "0"
                    record.serial_number = "0"
                    record.pem = "Certificate.pem"
                    record.pem_file = False
                    record.certificate_subject_name = None
                    record.certificate_date_start = None
                    record.certificate_date_end = None
                    continue
                
                try:
                    private_key, certificate, additional_certificates = pkcs12.load_key_and_certificates(
                        p12_data,
                        password,
                        default_backend()
                    )
                except ValueError as ve:
                    # Error de contraseña incorrecta
                    record.certificate_loading_error = "Contraseña incorrecta del certificado P12. Verifique la 'Clave del certificado P12'."
                    record.digital_certificate = "0"
                    record.issuer_name = "0"
                    record.serial_number = "0"
                    record.pem = "Certificate.pem"
                    record.pem_file = False
                    record.certificate_subject_name = None
                    record.certificate_date_start = None
                    record.certificate_date_end = None
                    continue
                except Exception as pkcs_error:
                    # Otro error al cargar el PKCS12
                    record.certificate_loading_error = f"Error al cargar archivo P12/PFX: {str(pkcs_error)}"
                    record.digital_certificate = "0"
                    record.issuer_name = "0"
                    record.serial_number = "0"
                    record.pem = "Certificate.pem"
                    record.pem_file = False
                    record.certificate_subject_name = None
                    record.certificate_date_start = None
                    record.certificate_date_end = None
                    continue

                if not certificate:
                    record.certificate_loading_error = "No se pudo extraer el certificado del archivo. El archivo P12 puede estar vacío o corrupto."
                    record.digital_certificate = "0"
                    record.issuer_name = "0"
                    record.serial_number = "0"
                    record.pem = "Certificate.pem"
                    record.pem_file = False
                    record.certificate_subject_name = None
                    record.certificate_date_start = None
                    record.certificate_date_end = None
                    continue
                
                def get_reversed_rdns_name(rdns):
                    OID_NAMES = {
                        x509.NameOID.COMMON_NAME: 'CN',
                        x509.NameOID.COUNTRY_NAME: 'C',
                        x509.NameOID.DOMAIN_COMPONENT: 'DC',
                        x509.NameOID.EMAIL_ADDRESS: 'E',
                        x509.NameOID.GIVEN_NAME: 'G',
                        x509.NameOID.LOCALITY_NAME: 'L',
                        x509.NameOID.ORGANIZATION_NAME: 'O',
                        x509.NameOID.ORGANIZATIONAL_UNIT_NAME: 'OU',
                        x509.NameOID.SURNAME: 'SN'
                    }
                    name = ''
                    for rdn in reversed(rdns):
                        for attr in rdn:
                            if len(name) > 0:
                                name = name + ','
                            if attr.oid in OID_NAMES:
                                name = name + OID_NAMES[attr.oid]
                            else:
                                name = name + attr.oid._name
                            name = name + '=' + attr.value
                    return name
                
                issuer = get_reversed_rdns_name(certificate.issuer.rdns)
                
                der_data = base64.b64encode(
                    certificate.public_bytes(encoding=serialization.Encoding.DER)
                )
                record.digital_certificate = der_data.decode('utf-8')
                record.issuer_name = issuer
                record.serial_number = str(certificate.serial_number)
                
                pem_data = certificate.public_bytes(encoding=serialization.Encoding.PEM)
                record.pem = "Certificate.pem"
                record.pem_file = base64.b64encode(pem_data)
                
                try:
                    common_name = certificate.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)
                    record.certificate_subject_name = common_name[0].value if common_name else ""
                except ValueError:
                    record.certificate_subject_name = None
                
                try:
                    record.certificate_date_start = certificate.not_valid_before_utc.replace(tzinfo=None)
                    record.certificate_date_end = certificate.not_valid_after_utc.replace(tzinfo=None)
                except AttributeError:
                    record.certificate_date_start = certificate.not_valid_before
                    record.certificate_date_end = certificate.not_valid_after
                
                record.certificate_loading_error = ""
                
                x509.load_pem_x509_certificate(pem_data, default_backend())
                
            except Exception as e:
                # Mantener valores por defecto en caso de error
                record.digital_certificate = "0"
                record.issuer_name = "0" 
                record.serial_number = "0"
                record.pem = "Certificate.pem"
                record.pem_file = False
                record.certificate_subject_name = None
                record.certificate_date_start = None
                record.certificate_date_end = None
                record.certificate_loading_error = f"Error cargando certificado: {str(e)}"
    
    @api.depends('certificate_date_start', 'certificate_date_end', 'certificate_loading_error')
    def _compute_certificate_validity(self):
        """Verifica si el certificado está válido"""
        for record in self:
            if not record.certificate_date_start or not record.certificate_date_end or record.certificate_loading_error:
                record.certificate_is_valid = False
            else:
                now = datetime.now()
                record.certificate_is_valid = record.certificate_date_start <= now <= record.certificate_date_end
    
    def button_extract_certificate(self):
        """
        Método de compatibilidad que fuerza la re-extracción
        Mantiene el nombre original del botón
        """
        self.ensure_one()
        self._compute_certificate_data()
        
        if self.certificate_loading_error:
            raise ValidationError(_(self.certificate_loading_error))
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Certificado Procesado'),
                'message': _('Información del certificado extraída: CN={}, Serial={}, Válido hasta={}'.format(
                    self.certificate_subject_name or 'N/A',
                    self.serial_number,
                    self.certificate_date_end.strftime('%Y-%m-%d') if self.certificate_date_end else 'N/A'
                )),
                'type': 'success',
            }
        }
    
    # ===================================================================
    # MÉTODOS AUXILIARES DE FIRMA DIGITAL
    # ===================================================================
    
    def get_certificate_der_bytes(self, formatting='base64'):
        """Obtiene certificado en formato DER"""
        self.ensure_one()
        if self.certificate_loading_error:
            raise UserError(_(self.certificate_loading_error))
        
        if formatting == 'base64':
            return self.digital_certificate
        else:
            return base64.b64decode(self.digital_certificate)
    
    def get_certificate_pem_bytes(self, formatting='base64'):
        """Obtiene certificado en formato PEM"""  
        self.ensure_one()
        if self.certificate_loading_error:
            raise UserError(_(self.certificate_loading_error))
        
        if formatting == 'base64':
            return base64.b64encode(base64.b64decode(self.pem_file)).decode()
        else:
            return base64.b64decode(self.pem_file)
    
    def sign_data(self, data, hash_algorithm='sha256', formatting='base64'):
        """
        Firma datos usando la llave privada del certificado
        Integrado con el método get_key() existente
        """
        self.ensure_one()
        
        if not self.certificate_is_valid:
            raise UserError(_("El certificado no es válido o ha expirado"))
        
        try:
            private_key, certificate = self.get_key()
            
            # Convertir datos a bytes si es necesario
            if isinstance(data, str):
                data = data.encode('utf-8')
            
            # Seleccionar algoritmo de hash
            if hash_algorithm == 'sha1':
                hash_algo = hashes.SHA1()
            elif hash_algorithm == 'sha256':
                hash_algo = hashes.SHA256()
            else:
                raise UserError(_("Algoritmo de hash no soportado. Use 'sha1' o 'sha256'"))
            
            # Firmar los datos
            signature = private_key.sign(data, padding.PKCS1v15(), hash_algo)
            
            # Formatear la firma
            if formatting == 'base64':
                return base64.b64encode(signature).decode()
            elif formatting == 'hex':
                return signature.hex()
            else:
                return signature
                
        except Exception as e:
            raise UserError(_(f"Error firmando datos: {str(e)}"))

    def query_numbering_range(self):
        identifier = uuid.uuid4()
        identifierTo = uuid.uuid4()
        identifierSecurityToken = uuid.uuid4()
        timestamp = self._generate_datetime_timestamp()
        Created = timestamp["Created"]
        Expires = timestamp["Expires"]
        Certificate = self.digital_certificate
        ProviderID = self.partner_id.vat_co
        SoftwareID = self.software_identification_code
        template_GetNumberingRange_xml = self._template_GetNumberingRange_xml()
        data_xml_send = self._generate_GetNumberingRange_send_xml(
            template_GetNumberingRange_xml,
            identifier,
            Created,
            Expires,
            Certificate,
            ProviderID,
            ProviderID,
            SoftwareID,
            identifierSecurityToken,
            identifierTo,
        )

        parser = etree.XMLParser(remove_blank_text=True)
        data_xml_send = etree.tostring(etree.XML(data_xml_send, parser=parser))
        data_xml_send = data_xml_send.decode()
        ElementTO = etree.fromstring(data_xml_send)
        ElementTO = etree.tostring(ElementTO[0])
        ElementTO = etree.fromstring(ElementTO)
        ElementTO = etree.tostring(ElementTO[2])
        DigestValueTO = self._generate_digestvalue_to(ElementTO)
        data_xml_send = data_xml_send.replace(
            "<ds:DigestValue/>", "<ds:DigestValue>%s</ds:DigestValue>" % DigestValueTO
        )
        Signedinfo = etree.fromstring(data_xml_send)
        Signedinfo = etree.tostring(Signedinfo[0])
        Signedinfo = etree.fromstring(Signedinfo)
        Signedinfo = etree.tostring(Signedinfo[0])
        Signedinfo = etree.fromstring(Signedinfo)
        Signedinfo = etree.tostring(Signedinfo[2])
        Signedinfo = etree.fromstring(Signedinfo)
        Signedinfo = etree.tostring(Signedinfo[0])
        Signedinfo = Signedinfo.decode()
        Signedinfo = Signedinfo.replace(
            '<ds:SignedInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#" xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd" xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd" xmlns:wsa="http://www.w3.org/2005/08/addressing" xmlns:soap="http://www.w3.org/2003/05/soap-envelope" xmlns:wcf="http://wcf.dian.colombia">',
            '<ds:SignedInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#" xmlns:soap="http://www.w3.org/2003/05/soap-envelope" xmlns:wcf="http://wcf.dian.colombia" xmlns:wsa="http://www.w3.org/2005/08/addressing">',
        )

        SignatureValue = self._generate_SignatureValue_GetNumberingRange(Signedinfo)
        data_xml_send = data_xml_send.replace(
            "<ds:SignatureValue/>",
            "<ds:SignatureValue>%s</ds:SignatureValue>" % SignatureValue,
        )
        headers = {"content-type": "application/soap+xml"}
        if self.production:
            try:
                response = requests.post(
                    server_url["PRODUCCION_VP"], data=data_xml_send, headers=headers
                )
            except Exception:
                raise ValidationError(
                    _("No existe comunicación con la DIAN para el servicio de consulta de rangos de numeración")
                )
        else:
            try:
                response = requests.post(
                    server_url["HABILITACION_VP"], data=data_xml_send, headers=headers
                )
            except Exception:
                raise ValidationError(
                    _("No existe comunicación con la DIAN para el servicio de consulta de rangos de numeración")
                )
        if response.status_code != 200:
            if response.status_code == 500:
                raise ValidationError(_("Error 500 = Error de servidor interno"))
            if response.status_code == 503:
                raise ValidationError(_("Error 503 = Servicio no disponible"))
        response_dict = xmltodict.parse(response.content)
        self.xml_response_numbering_range = response.content
        try:
            result = response_dict["s:Envelope"]["s:Body"]["GetNumberingRangeResponse"]["GetNumberingRangeResult"]
        except Exception:
            raise UserError(
                _(
                    "Respuesta DIAN inesperada. Revise el campo 'Contenido XML de la respuesta DIAN a la consulta de rangos'."
                )
            )

        operation_code = result.get("b:OperationCode")
        if operation_code != "100":
            details = []
            for key in ("b:OperationDescription", "b:OperationMessage", "b:ResponseMessage", "b:ErrorMessage"):
                val = result.get(key)
                if val:
                    details.append(str(val))
            detail_txt = " - ".join(details) if details else _("Sin detalle adicional")
            raise UserError(_("DIAN respondió OperationCode %s: %s") % (operation_code, detail_txt))

        response_list = (result.get("b:ResponseList") or {}).get("c:NumberRangeResponse")
        if not response_list:
            raise UserError(
                _("DIAN no devolvió rangos de numeración en la respuesta. Revise el XML almacenado en la compañía.")
            )

        # Normalizar: DIAN puede devolver dict (un rango) o list (varios rangos)
        if isinstance(response_list, dict):
            ranges = [response_list]
        elif isinstance(response_list, list):
            ranges = response_list
        else:
            raise UserError(
                _("Formato de rangos DIAN no soportado. Revise el XML almacenado en la compañía.")
            )

        def _norm_prefix(val):
            return (val or "").strip()

        def _matches_dian_prefix(sequence_prefix, dian_prefix):
            sp = _norm_prefix(sequence_prefix)
            dp = _norm_prefix(dian_prefix)
            if not sp or not dp:
                return False
            if sp == dp:
                return True
            if not sp.startswith(dp):
                return False
            rest = sp[len(dp):]
            # Permitir prefijos "plantilla" usados por Odoo (ej: BOG/%(range_year)s/)
            return rest.startswith(("/", "-", "_"))

        for dic in ranges:
            dian_prefix = _norm_prefix(dic.get("c:Prefix"))
            if not dian_prefix:
                continue

            # Buscar secuencia DIAN (activa) cuyo prefijo coincida con el prefijo DIAN (exacto o plantilla)
            candidate_sequences = self.env["ir.sequence"].search([
                ("company_id", "=", self.id),
                ("use_dian_control", "=", True),
                ("active", "=", True),
            ])
            matching_sequences = candidate_sequences.filtered(lambda s: _matches_dian_prefix(s.prefix, dian_prefix))

            if not matching_sequences:
                raise UserError(
                    _(
                        "No existe una secuencia DIAN activa para la compañía con el prefijo '%s'. "
                        "Cree/ajuste una secuencia (ir.sequence) con 'Usar resoluciones DIAN' y ese prefijo, "
                        "y asígnela a un diario activo."
                    )
                    % dian_prefix
                )
            if len(matching_sequences) > 1:
                seq_list = ", ".join(
                    "%s[%s]" % (s.display_name, (s.prefix or "")) for s in matching_sequences[:10]
                )
                raise UserError(
                    _(
                        "Hay más de una secuencia DIAN que coincide con el prefijo '%s': %s. "
                        "Deje solo una para evitar asignaciones ambiguas."
                    )
                    % (dian_prefix, seq_list)
                )

            sequence_id = matching_sequences[0]

            # Verificar que la secuencia esté asociada a un diario activo (si no, no se configura nada)
            journal_seq_fields = self.env["account.journal"]._fields
            seq_match_fields = ["sequence_id"]
            # Soportar secuencias de NC (lavish_erp): account.journal.refund_sequence_id
            if "refund_sequence_id" in journal_seq_fields:
                seq_match_fields.append("refund_sequence_id")
            # Soportar secuencias de ND (Odoo/otros): account.journal.debit_note_sequence_id
            if "debit_note_sequence_id" in journal_seq_fields:
                seq_match_fields.append("debit_note_sequence_id")

            # Domain OR: (field1=seq) OR (field2=seq) OR ...
            or_domain = ["|"] * (len(seq_match_fields) - 1) + [
                (f, "=", sequence_id.id) for f in seq_match_fields
            ]
            journal_using_sequence = self.env["account.journal"].search(
                [("company_id", "=", self.id), ("active", "=", True)] + or_domain,
                limit=1,
            )
            if not journal_using_sequence:
                raise UserError(
                    _(
                        "La secuencia '%s' (prefijo '%s') no está asociada a ningún diario activo. "
                        "Asóciela a un diario (account.journal.sequence_id / refund_sequence_id / debit_note_sequence_id) y vuelva a intentar."
                    )
                    % (sequence_id.display_name, (sequence_id.prefix or ""))
                )

            resolution_number = dic.get("c:ResolutionNumber")
            from_number = dic.get("c:FromNumber")
            to_number = dic.get("c:ToNumber")
            valid_from = dic.get("c:ValidDateFrom")
            valid_to = dic.get("c:ValidDateTo")
            technical_key = dic.get("c:TechnicalKey") or ""

            existing_resolution = self.env["ir.sequence.dian_resolution"].search([
                ("sequence_id", "=", sequence_id.id),
                ("resolution_number", "=", resolution_number),
            ], limit=1)

            # Desactivar todas las resoluciones de esta secuencia
            for resolution_id in sequence_id.dian_resolution_ids:
                resolution_id.active_resolution = False

            # Activar/crear la resolución actual
            if existing_resolution:
                existing_resolution.active_resolution = True
                _logger.info(
                    "Resolución %s activada para secuencia %s (diario: %s)",
                    resolution_number,
                    sequence_id.name,
                    journal_using_sequence.name,
                )
            else:
                vals_resolution = {
                    "resolution_number": resolution_number,
                    "number_from": from_number,
                    "number_to": to_number,
                    "number_next": from_number,
                    "date_from": valid_from,
                    "date_to": valid_to,
                    "technical_key": technical_key,
                    "active_resolution": True,
                }
                sequence_id.write({
                    "use_dian_control": True,
                    "dian_resolution_ids": [(0, 0, vals_resolution)],
                })
                _logger.info(
                    "Nueva resolución %s creada para secuencia %s (diario: %s) - Rango: %s a %s",
                    resolution_number,
                    sequence_id.name,
                    journal_using_sequence.name,
                    from_number,
                    to_number,
                )

    def _generate_SignatureValue_GetNumberingRange(self, data_xml_SignedInfo_generate):
        data_xml_SignatureValue_c14n = etree.tostring(
            etree.fromstring(data_xml_SignedInfo_generate), method="c14n"
        )
        password = self.certificate_key.encode('utf-8')
        try:
            p12 = pkcs12.load_key_and_certificates(
                base64.b64decode(self.certificate_file),
                password,
                default_backend()
            )
            private_key = p12[0]
        except Exception as ex:
            raise UserError(tools.ustr(ex))
        try:
            signature = private_key.sign(
                data_xml_SignatureValue_c14n,
                padding.PKCS1v15(),
                hashes.SHA256()
            )
        except Exception as ex:
            raise UserError(tools.ustr(ex))
        SignatureValue = base64.b64encode(signature).decode()
        pem_cert = x509.load_pem_x509_certificate(base64.b64decode(self.pem_file), default_backend())
        
        # Verificar la firma solo si la clave pública soporta verificación
        try:
            public_key = pem_cert.public_key()
            # Solo verificar si es una clave RSA o EC (que soportan verify)
            if isinstance(public_key, (rsa.RSAPublicKey, ec.EllipticCurvePublicKey)):
                public_key.verify(
                    signature,
                    data_xml_SignatureValue_c14n,
                    padding.PKCS1v15(),
                    hashes.SHA256()
                )
            else:
                _logger.warning("Tipo de clave pública no soporta verificación de firma: %s", type(public_key))
        except Exception:
            raise ValidationError(
                _("Signature for GetStatus was not validated successfully")
            )
        return SignatureValue

    def _generate_digestvalue_to(self, elementTo):
        elementTo = etree.tostring(etree.fromstring(elementTo), method="c14n")
        elementTo_sha256 = hashlib.sha256(elementTo)
        elementTo_digest = elementTo_sha256.digest()
        elementTo_base = base64.b64encode(elementTo_digest)
        return elementTo_base.decode()

    def _generate_datetime_timestamp(self):
        fmt = "%Y-%m-%dT%H:%M:%S.%f"
        now_bogota = datetime.now(timezone("UTC"))
        Created = now_bogota.strftime(fmt)[:-3] + "Z"
        now_bogota = now_bogota + timedelta(minutes=5)
        Expires = now_bogota.strftime(fmt)[:-3] + "Z"
        timestamp = {"Created": Created, "Expires": Expires}
        return timestamp

    def _template_GetNumberingRange_xml(self):
        template_GetNumberingRange_xml = """
        <soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" xmlns:wcf="http://wcf.dian.colombia">
                <soap:Header xmlns:wsa="http://www.w3.org/2005/08/addressing">
                        <wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
                xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">
                                <wsu:Timestamp wsu:Id="TS-%(identifier)s">
                                        <wsu:Created>%(Created)s</wsu:Created>
                                        <wsu:Expires>%(Expires)s</wsu:Expires>
                                </wsu:Timestamp>
                                <wsse:BinarySecurityToken EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary"
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
                        <wsa:Action>http://wcf.dian.colombia/IWcfDianCustomerServices/GetNumberingRange</wsa:Action>
                        <wsa:To wsu:Id="ID-%(identifierTo)s"
                xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">
                https://vpfe.dian.gov.co/WcfDianCustomerServices.svc</wsa:To>
                </soap:Header>
                <soap:Body>
                        <wcf:GetNumberingRange>
                                <wcf:accountCode>%(accountCode)s</wcf:accountCode>
                                <wcf:accountCodeT>%(accountCodeT)s</wcf:accountCodeT>
                                <wcf:softwareCode>%(softwareCode)s</wcf:softwareCode>
                        </wcf:GetNumberingRange>
                </soap:Body>
        </soap:Envelope>
        """
        return template_GetNumberingRange_xml

    @api.model
    def _generate_GetNumberingRange_send_xml(
        self,
        template_getstatus_send_data_xml,
        identifier,
        Created,
        Expires,
        Certificate,
        accountCode,
        accountCodeT,
        softwareCode,
        identifierSecurityToken,
        identifierTo,
    ):
        data_consult_numbering_range_send_xml = template_getstatus_send_data_xml % {
            "identifier": identifier,
            "Created": Created,
            "Expires": Expires,
            "Certificate": Certificate,
            "accountCode": accountCode,
            "accountCodeT": accountCodeT,
            "softwareCode": softwareCode,
            "identifierSecurityToken": identifierSecurityToken,
            "identifierTo": identifierTo,
        }
        return data_consult_numbering_range_send_xml




    def get_key(self):
        self.ensure_one()
        if not self.certificate_file:
            raise UserError(_("Certificado digital no encontrado"))
        if not self.certificate_key:
            raise UserError(_("Clave del certificado no configurada"))

        try:
            # Validar y limpiar el base64
            cert_b64 = self.certificate_file
            if isinstance(cert_b64, str):
                cert_b64 = cert_b64.strip()
                cert_b64 = ''.join(cert_b64.split())

            # Validar longitud base64
            if len(cert_b64) % 4 != 0:
                padding_needed = 4 - (len(cert_b64) % 4)
                cert_b64 += '=' * padding_needed

            p12_data = base64.b64decode(cert_b64)
            private_key, certificate, _ = pkcs12.load_key_and_certificates(
                p12_data,
                self.certificate_key.encode('utf-8'),
                backend=default_backend()
            )
            if not private_key or not certificate:
                raise UserError(_("No se pudo extraer la llave privada o el certificado"))
            return private_key, certificate
        except ValueError as ve:
            raise UserError(_("Clave del certificado incorrecta. Verifique la 'Clave del certificado P12'."))
        except Exception as e:
            raise UserError(_(f"Error cargando certificado: {str(e)}"))


    @api.constrains('certificate_file')
    def _check_certificate_format(self):
        """Valida el formato del certificado"""
        for record in self:
            if record.certificate_file:
                try:
                    # Validar y limpiar el base64
                    cert_b64 = record.certificate_file
                    if isinstance(cert_b64, str):
                        cert_b64 = cert_b64.strip()
                        cert_b64 = ''.join(cert_b64.split())

                    # Validar longitud base64
                    if len(cert_b64) % 4 != 0:
                        padding_needed = 4 - (len(cert_b64) % 4)
                        cert_b64 += '=' * padding_needed

                    p12_data = base64.b64decode(cert_b64)

                    # Validar que es un archivo PKCS12 válido (la contraseña dummy no importa)
                    pkcs12.load_key_and_certificates(
                        p12_data,
                        b'dummy',
                        backend=default_backend()
                    )
                except ValueError:
                    # ValueError es esperado con contraseña incorrecta, pero indica formato P12 válido
                    continue
                except Exception as e:
                    # Otros errores indican formato inválido
                    raise ValidationError(_("Formato de certificado inválido. Debe ser un archivo .p12 o .pfx válido. Error: %s") % str(e))
    
    @api.depends('xml_response_numbering_range')
    def _compute_numbering_ranges_html(self):
        """Genera tabla HTML con las resoluciones DIAN configuradas"""
        for record in self:
            html_table = record._generate_resolutions_html_table()
            record.numbering_ranges_html = html_table
    
    def _generate_resolutions_html_table(self):
        """Genera tabla HTML con resoluciones activas de todas las secuencias DIAN"""
        self.ensure_one()
        
        # Buscar todas las secuencias DIAN activas de la compañía
        sequences = self.env['ir.sequence'].search([
            ('company_id', '=', self.id),
            ('use_dian_control', '=', True),
            ('active', '=', True)
        ])
        
        if not sequences:
            return '''
            <div class="alert alert-info">
                <strong>Información:</strong> No hay secuencias DIAN configuradas para esta compañía.
                <br/>Ejecute "Consultar Rangos DIAN" para obtener y configurar las resoluciones.
            </div>
            '''
        
        html = '''
        <style>
            .dian-resolutions-table {
                width: 100%;
                border-collapse: collapse;
                margin: 10px 0;
                font-family: Arial, sans-serif;
            }
            .dian-resolutions-table th {
                background-color: #875A7B;
                color: white;
                padding: 12px 8px;
                text-align: left;
                font-weight: bold;
                border: 1px solid #ddd;
            }
            .dian-resolutions-table td {
                padding: 8px;
                border: 1px solid #ddd;
                vertical-align: top;
            }
            .dian-resolutions-table tr:nth-child(even) {
                background-color: #f9f9f9;
            }
            .dian-resolutions-table tr:hover {
                background-color: #f5f5f5;
            }
            .status-active {
                color: #28a745;
                font-weight: bold;
            }
            .status-inactive {
                color: #6c757d;
            }
            .journal-info {
                font-size: 0.9em;
                color: #6c757d;
                font-style: italic;
            }
            .resolution-alert {
                background-color: #fff3cd;
                border: 1px solid #ffeaa7;
                border-radius: 4px;
                padding: 8px;
                margin: 5px 0;
            }
        </style>
        
        <table class="dian-resolutions-table">
            <thead>
                <tr>
                    <th>Prefijo</th>
                    <th>Resolución</th>
                    <th>Rango</th>
                    <th>Próximo</th>
                    <th>Vigencia</th>
                    <th>Estado</th>
                    <th>Diario</th>
                    <th>Clave Técnica</th>
                </tr>
            </thead>
            <tbody>
        '''
        
        total_resolutions = 0
        active_resolutions = 0
        
        for sequence in sequences:
            # Buscar diario asociado
            journal_seq_fields = self.env["account.journal"]._fields
            seq_match_fields = ["sequence_id"]
            if "refund_sequence_id" in journal_seq_fields:
                seq_match_fields.append("refund_sequence_id")
            if "debit_note_sequence_id" in journal_seq_fields:
                seq_match_fields.append("debit_note_sequence_id")

            or_domain = ["|"] * (len(seq_match_fields) - 1) + [
                (f, "=", sequence.id) for f in seq_match_fields
            ]
            journal = self.env["account.journal"].search(
                [("company_id", "=", self.id)] + or_domain,
                limit=1,
            )
            
            journal_name = journal.name if journal else '<span style="color:red;">Sin diario asociado</span>'
            
            if sequence.dian_resolution_ids:
                for resolution in sequence.dian_resolution_ids:
                    total_resolutions += 1
                    if resolution.active_resolution:
                        active_resolutions += 1
                    
                    status_class = "status-active" if resolution.active_resolution else "status-inactive"
                    status_text = "Activa" if resolution.active_resolution else "Inactiva"
                    
                    # Calcular progreso del rango
                    if resolution.number_to and resolution.number_from:
                        range_used = resolution.number_next - resolution.number_from
                        range_total = resolution.number_to - resolution.number_from + 1
                        progress_percent = (range_used / range_total) * 100 if range_total > 0 else 0
                        progress_color = "green" if progress_percent < 70 else "orange" if progress_percent < 90 else "red"
                        range_display = f'''{resolution.number_from:,} - {resolution.number_to:,}
                        <br/><small style="color:{progress_color};">Progreso: {progress_percent:.1f}%</small>'''
                    else:
                        range_display = "No definido"
                    
                    html += f'''
                    <tr>
                        <td><strong>{sequence.prefix or 'N/A'}</strong></td>
                        <td>{resolution.resolution_number or 'N/A'}</td>
                        <td>{range_display}</td>
                        <td><strong>{resolution.number_next:,}</strong></td>
                        <td>
                            {resolution.date_from or 'N/A'}<br/>
                            <small>hasta: {resolution.date_to or 'N/A'}</small>
                        </td>
                        <td class="{status_class}">{status_text}</td>
                        <td class="journal-info">{journal_name}</td>
                        <td><small>{resolution.technical_key or 'N/A'}</small></td>
                    </tr>
                    '''
            else:
                html += f'''
                <tr>
                    <td><strong>{sequence.prefix or 'N/A'}</strong></td>
                    <td colspan="6" class="resolution-alert">
                        <strong>Sin resoluciones configuradas</strong><br/>
                        Ejecute "Consultar Rangos DIAN" para obtener las resoluciones.
                    </td>
                    <td class="journal-info">{journal_name}</td>
                </tr>
                '''
        
        html += '''
            </tbody>
        </table>
        '''
        
        # Agregar resumen
        html += f'''
        <div style="margin-top: 15px; padding: 10px; background-color: #e9ecef; border-radius: 5px;">
            <strong>Resumen:</strong> 
            {len(sequences)} secuencia(s) DIAN configurada(s) • 
            {active_resolutions} de {total_resolutions} resolución(es) activa(s)
        </div>
        '''
        
        return html
    
    def show_resolutions_html(self):
        """Acción para mostrar/refrescar la tabla de resoluciones"""
        self.ensure_one()
        # Forzar recálculo del campo computado
        self._compute_numbering_ranges_html()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Resoluciones Actualizadas'),
                'message': _('La tabla de resoluciones ha sido actualizada con la información más reciente.'),
                'type': 'info',
            }
        }
