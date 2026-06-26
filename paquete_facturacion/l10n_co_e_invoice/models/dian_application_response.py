# -*- coding: utf-8 -*-
"""
DIAN Application Response - Gestión de Eventos DIAN
Versión mejorada con firma correcta y recuperación de datos
"""
import json
import uuid
import hashlib
import base64
import requests
import xmltodict
from datetime import datetime
from dateutil.relativedelta import relativedelta
from lxml import etree
from lxml.builder import ElementMaker
import pytz
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from markupsafe import Markup
import logging

_logger = logging.getLogger(__name__)
LOCALTZ = pytz.timezone('America/Bogota')

# Colores para estados
STATE_COLORS = {
    'por_notificar': 7,  # Gris
    'error': 1,          # Rojo
    'por_validar': 3,    # Amarillo
    'exitoso': 10,       # Verde
    'rechazado': 2,      # Naranja
}

class DianApplicationResponse(models.Model):
    """Application Response mejorado con Abstract Mixin"""
    _name = 'dian.application.response'
    _description = 'DIAN Application Response - Eventos'
    _inherit = ['abstract.dian.mixin', 'mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'
    _rec_name = 'display_name'
    
 
    name = fields.Char(
        string="Número",
        required=True,
        copy=False,
        readonly=True,
        default='/',
        tracking=True
    )
    
    display_name = fields.Char(
        string="Nombre",
        compute='_compute_display_name',
        store=True
    )
    
    # Campos de identificación
    cude = fields.Char(
        string='CUDE',
        compute='_compute_cude',
        store=True,
        readonly=True,
        tracking=True,
        help='Código Único de Documento Electrónico'
    )
    
    # Relaciones
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
        tracking=True
    )
    
    user_id = fields.Many2one(
        'res.users',
        string='Usuario',
        required=True,
        default=lambda self: self.env.user,
        tracking=True
    )
    
    move_id = fields.Many2one(
        'account.move',
        string='Factura',
        tracking=True,
        ondelete='cascade'
    )
    
    # Tipo de evento
    response_code = fields.Selection([
        ('030', '[030] Acuse de recibo'),
        ('031', '[031] Reclamo'),
        ('032', '[032] Recibo del bien'),
        ('033', '[033] Aceptación expresa'),
        ('034', '[034] Aceptación Tácita'),
        ('035', '[035] Aval'),
        ('036', '[036] Inscripción título valor - RADIAN'),
        ('037', '[037] Endoso en Propiedad'),
        ('038', '[038] Endoso en Garantía'),
        ('039', '[039] Endoso en Procuración'),
        ('040', '[040] Cancelación de endoso'),
        ('041', '[041] Limitaciones a la circulación'),
        ('042', '[042] Terminación de limitaciones'),
        ('043', '[043] Mandatos'),
        ('044', '[044] Terminación del Mandato'),
        ('045', '[045] Pago título valor'),
        ('046', '[046] Informe para el pago'),
        ('047', '[047] Endoso con cesión ordinaria'),
        ('048', '[048] Protesto'),
        ('049', '[049] Transferencia derechos económicos'),
        ('050', '[050] Notificación transferencia'),
        ('051', '[051] Pago de transferencia'),
    ], string="Tipo de Evento", required=True, tracking=True)
    
    # Documento referenciado
    doc_adq = fields.Char(
        string='NIT Receptor',
        help='NIT de quien recibe este evento',
        tracking=True
    )
    
    document_referenced = fields.Char(
        string='Documento Referenciado',
        required=True,
        tracking=True
    )
    
    document_type_code = fields.Selection(
        [('01', 'Factura Electrónica')],
        string='Tipo Documento',
        default='01',
        required=True
    )
    
    # Estados
    status = fields.Selection([
        ('por_notificar', 'Por Notificar'),
        ('error', 'Error'),
        ('por_validar', 'Por Validar'),
        ('exitoso', 'Exitoso'),
        ('rechazado', 'Rechazado'),
    ], default='por_notificar', string='Estado', tracking=True, copy=False)
    
    state_dian_document = fields.Selection(
        selection_add=[
            ('por_notificar', 'Por notificar'),
            ('error', 'Error'),
            ('por_validar', 'Por validar'),
            ('exitoso', 'Exitoso'),
            ('rechazado', 'Rechazado'),
        ],
        ondelete={
            'por_notificar': 'cascade',
            'error': 'cascade',
            'por_validar': 'cascade',
            'exitoso': 'cascade',
            'rechazado': 'cascade',
        },
        default='por_notificar', string='Estado DIAN', tracking=True,
    )
    
    # Campos planos para datos
    invoice_number = fields.Char(
        string='Número Factura',
        compute='_compute_invoice_data',
        store=True
    )
    
    partner_name = fields.Char(
        string='Cliente/Proveedor',
        compute='_compute_invoice_data',
        store=True
    )
    
    partner_vat = fields.Char(
        string='NIT',
        compute='_compute_invoice_data',
        store=True
    )
    
    invoice_amount = fields.Float(
        string='Monto',
        compute='_compute_invoice_data',
        store=True
    )
    
    invoice_currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        compute='_compute_invoice_data',
        store=True
    )
    
    # Fechas
    issue_date = fields.Char(compute='_compute_date_time', store=True)
    issue_time = fields.Char(compute='_compute_date_time', store=True)
    
    # XML y respuestas
    response_xml = fields.Text('XML Generado')
    response_dian = fields.Text('Respuesta DIAN')
    response_message_dian = fields.Html('Mensaje DIAN', sanitize=False)
    xml_text = fields.Text('Contenido XML')
    notes_xml = fields.Text('Notas del Evento')
    
    # Control de envío de email
    send_email = fields.Boolean(
        string='Enviar Email',
        default=True,
        help='Indica si se debe enviar email al crear el evento'
    )
    
    email_sent = fields.Boolean(
        string='Email Enviado',
        copy=False,
        tracking=True
    )
    
    # Recuperación
    was_recovered = fields.Boolean(
        string='Evento Recuperado',
        help='Este evento fue recuperado desde DIAN',
        copy=False
    )
    
    recovery_date = fields.Datetime(
        string='Fecha Recuperación',
        copy=False
    )
    
    # Color para vistas
    color = fields.Integer(
        string='Color',
        compute='_compute_color'
    )
    
    # Tipo de pago
    payment_type = fields.Selection([
        ('cash', 'Contado'),
        ('credit', 'Crédito'),
        ('unknown', 'Desconocido')
    ], string='Tipo de Pago', compute='_compute_payment_type', store=True)
    
    # Control de eventos
    requires_event = fields.Boolean(
        string='Requiere Evento DIAN',
        compute='_compute_requires_event',
        store=True
    )
    
    is_titulo_valor = fields.Boolean(
        string='Es Título Valor',
        compute='_compute_is_titulo_valor',
        store=True
    )
    
    # Campos del mixin
    cufe = fields.Char(string='CUFE/CUDE', related='cude', store=True)
    ZipKey = fields.Char(string='ZipKey')
    diancode_id = fields.Many2one('dian.document', string='Documento DIAN')
    contingency_3 = fields.Boolean(string='Contingencia 3')
    contingency_4 = fields.Boolean(string='Contingencia 4')
    
    # Archivos
    dian_xml_attachment_id = fields.Many2one(
        'ir.attachment',
        string='XML Adjunto',
        copy=False
    )
    
    dian_response_attachment_id = fields.Many2one(
        'ir.attachment',
        string='Respuesta Adjunta',
        copy=False
    )
    
    # Datos extraídos del XML de factura
    invoice_cufe = fields.Char(string='CUFE Factura')
    invoice_issue_date = fields.Char(string='Fecha Emisión Factura')
    invoice_issue_time = fields.Char(string='Hora Emisión Factura')
    invoice_receiver_name = fields.Char(string='Receptor Factura')
    invoice_receiver_vat = fields.Char(string='NIT Receptor Factura')
    invoice_receiver_dv = fields.Char(string='DV Receptor')
    invoice_receiver_scheme = fields.Char(string='Tipo ID Receptor')
    
    # =============================================================================
    # COMPUTE METHODS
    # =============================================================================
    
    @api.depends('name', 'response_code', 'move_id.name')
    def _compute_display_name(self):
        """Calcula el nombre a mostrar"""
        for record in self:
            if record.move_id:
                event_name = dict(record._fields['response_code'].selection).get(record.response_code, '')
                record.display_name = f"{record.name} - {event_name} ({record.move_id.name})"
            else:
                record.display_name = record.name
    
    @api.depends('move_id', 'move_id.name', 'move_id.partner_id', 'move_id.amount_total')
    def _compute_invoice_data(self):
        """Extrae y guarda datos planos de la factura"""
        for record in self:
            if record.move_id:
                record.invoice_number = record.move_id.name
                record.partner_name = record.move_id.partner_id.name
                record.partner_vat = record.move_id.partner_id.vat
                record.invoice_amount = record.move_id.amount_total
                record.invoice_currency_id = record.move_id.currency_id
            else:
                record.invoice_number = False
                record.partner_name = False
                record.partner_vat = False
                record.invoice_amount = 0.0
                record.invoice_currency_id = False
    
    @api.depends('status', 'response_code')
    def _compute_color(self):
        """Asigna colores según estado"""
        for record in self:
            record.color = STATE_COLORS.get(record.status, 0)
    
    @api.depends('create_date')
    def _compute_date_time(self):
        """Calcula fecha y hora en formato DIAN"""
        for rec in self:
            if rec.create_date:
                local_date = rec.create_date.astimezone(LOCALTZ)
                rec.issue_date = local_date.date().isoformat()
                rec.issue_time = local_date.strftime('%H:%M:%S-05:00')
    
    @api.depends('company_id', 'response_code', 'doc_adq', 'document_referenced',
                 'document_type_code', 'name', 'issue_date', 'issue_time')
    def _compute_cude(self):
        """Calcula CUDE del evento"""
        for rec in self:
            if rec.was_recovered:
                continue
                
            if all([rec.name, rec.issue_date, rec.issue_time, rec.company_id,
                   rec.response_code, rec.document_referenced]):
                
                Num_DE = rec.name
                Fec_Emi = rec.issue_date
                Hor_Emi = rec.issue_time
                NitFe = rec.company_id.partner_id.vat_co or ''
                ID = rec.document_referenced
                software_pin = rec.company_id.software_pin or ''
                doc_adq = rec.doc_adq or ''
                
                CUDE = f'{Num_DE}{Fec_Emi}{Hor_Emi}{NitFe}{doc_adq}{rec.response_code}{ID}{rec.document_type_code}{software_pin}'
                CUDE_hash = hashlib.sha384(CUDE.encode())
                rec.cude = CUDE_hash.hexdigest()
    
    @api.depends('move_id', 'move_id.invoice_date', 'move_id.invoice_date_due')
    def _compute_payment_type(self):
        """Determina el tipo de pago"""
        for record in self:
            if record.move_id:
                if record.move_id.invoice_date == record.move_id.invoice_date_due:
                    record.payment_type = 'cash'
                elif record.move_id.invoice_date_due > record.move_id.invoice_date:
                    record.payment_type = 'credit'
                else:
                    record.payment_type = 'unknown'
            else:
                record.payment_type = 'unknown'
    
    @api.depends('payment_type', 'response_code', 'move_id.move_type')
    def _compute_requires_event(self):
        """Determina si requiere evento según lógica de negocio"""
        for record in self:
            # Ventas de contado con aceptación no requieren evento
            if (record.payment_type == 'cash' and 
                record.response_code in ['033', '034'] and
                record.move_id and 
                record.move_id.move_type == 'out_invoice'):
                record.requires_event = False
            else:
                record.requires_event = True
    
    @api.depends('response_code', 'status')
    def _compute_is_titulo_valor(self):
        """Determina si el evento convierte en título valor"""
        titulo_valor_events = ['033', '034']
        for record in self:
            record.is_titulo_valor = (
                record.response_code in titulo_valor_events and 
                record.status == 'exitoso'
            )
    
    # =============================================================================
    # MÉTODOS PRINCIPALES
    # =============================================================================
    
    @api.model_create_multi
    def create(self, vals_list):
        """Crea evento con secuencia automática"""
        if isinstance(vals_list, dict):
            vals_list = [vals_list]

        for vals in vals_list:
            if vals.get('name', '/') == '/':
                response_code = vals.get('response_code', '')
                sequence = self.env['ir.sequence'].next_by_code(
                    f'dian.application.response.{response_code}'
                )
                if not sequence:
                    sequence = self.env['ir.sequence'].next_by_code('dian.application.response')
                vals['name'] = sequence or f"AR{datetime.now().strftime('%Y%m%d%H%M%S')}"

        records = super().create(vals_list)

        for record in records:
            if not record.requires_event:
                record._mark_as_not_required()

        return records
    
    def write(self, vals):
        """Override write para tracking"""
        # Si cambia el estado a exitoso, marcar como título valor en factura
        if vals.get('status') == 'exitoso':
            self._update_invoice_titulo_valor()
        
        return super().write(vals)
    
    @api.model
    def generate_from_invoice(self, invoice_id, response_code, context_data=None):
        """Genera evento desde factura con contexto"""
        invoice = self.env['account.move'].browse(invoice_id)
        if not invoice.exists():
            raise UserError(_("No se encontró la factura"))
        
        # Validar factura
        # Permitir si existe CUFE/CUDE aunque no esté validada por DIAN
        if invoice.move_type in ('in_invoice', 'in_refund'):
            # Para compras, siempre usar CUFE/CUDS del proveedor (otro sistema)
            cufe_value = getattr(invoice, 'cufe_cuds_other_system', False)
        else:
            cufe_value = invoice.cufe or getattr(invoice, 'cufe_cuds_other_system', False)
        if invoice.state_dian_document != 'exitoso' and not cufe_value:
            raise UserError(_("La factura debe estar validada por DIAN"))
        
        # Verificar si ya existe
        existing = self.search([
            ('move_id', '=', invoice.id),
            ('response_code', '=', response_code),
            ('status', '=', 'exitoso')
        ], limit=1)
        
        if existing:
            raise UserError(_("Ya existe un evento %s exitoso para esta factura") % response_code)
        
        # Preparar valores
        # doc_adq: receptor del evento (customer en ventas, supplier en compras)
        if invoice.move_type in ('in_invoice', 'in_refund'):
            doc_ref_number = invoice.ref or invoice.payment_reference or invoice.name
            if doc_ref_number == invoice.name:
                _logger.warning(
                    "Factura %s: no se encontró ref con número FEV, usando name=%s. "
                    "Verificar que lavish_xml_invoice procesó el XML.",
                    invoice.id,
                    invoice.name,
                )
        else:
            doc_ref_number = invoice.name

        vals = {
            'response_code': response_code,
            'move_id': invoice.id,
            'doc_adq': invoice.partner_id.vat_co if invoice.partner_id else '',
            'document_referenced': doc_ref_number,
            'send_email': context_data.get('send_email', True) if context_data else True,
            # BUG-003: Datos del receptor (partner de la factura)
            'invoice_receiver_name': invoice.partner_id.name if invoice.partner_id else '',
            'invoice_receiver_vat': invoice.partner_id.vat_co if invoice.partner_id else '',
            'invoice_receiver_dv': invoice.partner_id.dv if invoice.partner_id and hasattr(invoice.partner_id, 'dv') else '',
            'invoice_receiver_scheme': '31',
            # BUG-004: CUFE e fecha de la factura
            'invoice_cufe': cufe_value or '',
            'invoice_issue_date': str(invoice.invoice_date) if invoice.invoice_date else '',
        }
        
        # Notas especiales según evento
        if response_code == '031':  # Reclamo
            vals['notes_xml'] = context_data.get('notes', '') if context_data else ''
                
        elif response_code == '034':  # Aceptación tácita
            vals['notes_xml'] = self._get_tacit_acceptance_note(invoice)
        
        # Crear evento
        event = self.create(vals)
        
        # Intentar recuperar y extraer datos del XML si existe
        if invoice.cufe:
            event._try_retrieve_and_extract_invoice_data()
        
        # Enviar a DIAN solo si se solicita explícitamente
        send_now = context_data.get('send_now', True) if context_data else True
        if event.requires_event and send_now:
            event.action_send_dian()
        
        return event
    
    def _mark_as_not_required(self):
        """Marca evento como no requerido"""
        self.ensure_one()
        self.write({
            'status': 'exitoso',
            'state_dian_document': 'exitoso',
            'response_message_dian': Markup(
                '<div class="alert alert-info">'
                '<i class="fa fa-info-circle"/> Evento no requerido para facturas de contado'
                '</div>'
            )
        })
    
    def _update_invoice_titulo_valor(self):
        """Actualiza estado de título valor en factura"""
        for record in self:
            if record.is_titulo_valor and record.move_id:
                # Guardar datos planos en factura
                record.move_id.write({
                    'last_event_code': record.response_code,
                    'last_event_date': fields.Datetime.now(),
                    'last_event_cude': record.cude
                })

    def _update_invoice_last_event(self):
        """Actualiza el último evento en la factura (para todos los eventos)."""
        for record in self:
            if record.move_id:
                record.move_id.write({
                    'last_event_code': record.response_code,
                    'last_event_date': fields.Datetime.now(),
                    'last_event_cude': record.cude
                })
    
    # =============================================================================
    # MÉTODOS DE RECUPERACIÓN Y EXTRACCIÓN DE DATOS
    # =============================================================================
    
    def _try_retrieve_and_extract_invoice_data(self):
        """Intenta recuperar XML de factura y extraer datos"""
        self.ensure_one()
        if not self.move_id or not self.move_id.cufe:
            return False
        
        try:
            # Primero intentar con el XML ya almacenado
            if self.move_id.xml_text:
                self._extract_data_from_invoice_xml(self.move_id.xml_text)
                return True
            
            # Si no hay XML, intentar recuperarlo
            from . import xml_utils
            response = xml_utils._build_and_send_request(
                self,
                payload={
                    'track_id': self.move_id.cufe,
                    'soap_body_template': "l10n_co_e_invoice.get_xml",
                },
                service="GetXmlByDocumentKey",
                company=self.company_id,
            )
            
            if response['status_code'] == 200:
                root = etree.fromstring(response['response'])
                xml_base64 = root.findtext('.//{*}XmlBytesBase64')
                
                if xml_base64:
                    xml_content = base64.b64decode(xml_base64)
                    xml_text = xml_content.decode('utf-8')
                    self.move_id.xml_text = xml_text
                    self._extract_data_from_invoice_xml(xml_text)
                    _logger.info(f"XML recuperado y datos extraídos para {self.move_id.name}")
                    return True
                    
        except Exception as e:
            _logger.warning(f"No se pudo recuperar/extraer datos del XML: {str(e)}")
        
        return False
    
    def _extract_data_from_invoice_xml(self, xml_text):
        """Extrae datos del XML de factura"""
        self.ensure_one()
        try:
            # Parsear XML
            root = etree.fromstring(xml_text.encode('utf-8'))
            
            # Namespaces comunes
            nsmap = {
                'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
                'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
            }
            
            # Extraer CUFE
            cufe = root.findtext('.//cbc:UUID', namespaces=nsmap)
            if cufe:
                self.invoice_cufe = cufe
            
            # Extraer fechas
            issue_date = root.findtext('.//cbc:IssueDate', namespaces=nsmap)
            issue_time = root.findtext('.//cbc:IssueTime', namespaces=nsmap)
            if issue_date:
                self.invoice_issue_date = issue_date
            if issue_time:
                self.invoice_issue_time = issue_time
            
            # Extraer datos del receptor (AccountingCustomerParty)
            customer_party = root.find('.//cac:AccountingCustomerParty/cac:Party', namespaces=nsmap)
            if customer_party is not None:
                # Nombre
                reg_name = customer_party.findtext('.//cbc:RegistrationName', namespaces=nsmap)
                if reg_name:
                    self.invoice_receiver_name = reg_name
                
                # NIT y DV
                company_id = customer_party.find('.//cbc:CompanyID', namespaces=nsmap)
                if company_id is not None:
                    vat = company_id.text
                    if vat:
                        self.invoice_receiver_vat = vat
                        self.doc_adq = vat  # Actualizar doc_adq
                    
                    # DV
                    dv = company_id.get('schemeID')
                    if dv:
                        self.invoice_receiver_dv = dv
                    
                    # Tipo identificación
                    scheme_name = company_id.get('schemeName')
                    if scheme_name:
                        self.invoice_receiver_scheme = scheme_name
            
            _logger.info(f"Datos extraídos del XML para evento {self.name}")
            
        except Exception as e:
            _logger.warning(f"Error extrayendo datos del XML: {str(e)}")
    
    def _try_recover_existing_event(self):
        """Intenta recuperar evento existente desde DIAN"""
        self.ensure_one()
        
        try:
            # Buscar el evento en DIAN
            from . import xml_utils
            response = xml_utils._build_and_send_request(
                self,
                payload={
                    'track_id': self.cude,
                    'soap_body_template': "l10n_co_e_invoice.get_status",
                },
                service="GetStatus",
                company=self.company_id,
            )
            
            if response['status_code'] == 200:
                # Extraer datos de la respuesta
                root = etree.fromstring(response['response'])
                is_valid = root.findtext('.//{*}IsValid')
                status_code = root.findtext('.//{*}StatusCode')
                status_description = root.findtext('.//{*}StatusDescription')
                
                # Actualizar registro
                self.write({
                    'was_recovered': True,
                    'recovery_date': fields.Datetime.now(),
                    'status': 'exitoso' if is_valid == 'true' else 'rechazado',
                    'state_dian_document': 'exitoso' if is_valid == 'true' else 'rechazado',
                    'response_dian': response['response'],
                    'response_message_dian': Markup(
                        f'<div class="alert alert-warning">'
                        f'<i class="fa fa-download"/> Evento recuperado desde DIAN<br/>'
                        f'Estado: {status_code} - {status_description}'
                        f'</div>'
                    )
                })
                if is_valid == 'true':
                    self._update_invoice_last_event()
                
                _logger.info(f"Evento {self.name} recuperado exitosamente desde DIAN")
                return True
                
        except Exception as e:
            _logger.warning(f"No se pudo recuperar evento desde DIAN: {str(e)}")
            # Marcar como recuperado aunque no se obtengan detalles
            self.write({
                'was_recovered': True,
                'recovery_date': fields.Datetime.now(),
                'status': 'exitoso',
                'state_dian_document': 'exitoso',
                'response_message_dian': Markup(
                    '<div class="alert alert-warning">'
                    '<i class="fa fa-download"/> Evento recuperado (sin detalles disponibles)'
                    '</div>'
                )
            })
        
        return False
    
    # =============================================================================
    # IMPLEMENTACIÓN AbstractDianMixin
    # =============================================================================
    
    def _collect_all_dian_data(self):
        """Recolecta todos los datos para generar XML"""
        # Validaciones
        self._validate_required_data()
        
        # Certificados
        cert_info = self._get_certificate_info()
        
        # Software
        software_id = self.company_id.software_identification_code
        software_pin = self.company_id.software_pin
        software_security_code = self._generate_software_security_code(
            software_id, software_pin, self.name
        )
        
        # Ambiente
        ambiente = "1" if self.company_id.production else "2"
        
        sender_partner = self.company_id.partner_id
        sender_fiscal_resp = ';'.join(
            sender_partner.fiscal_responsability_ids.mapped('code')
        ) if sender_partner.fiscal_responsability_ids else 'R-99-PN'

        if self.move_id and self.move_id.move_type in ('in_invoice', 'in_refund'):
            # Para compras, siempre usar el CUFE/CUDS del proveedor
            cufe_value = getattr(self.move_id, 'cufe_cuds_other_system', '') or ''
        else:
            cufe_value = (
                self.invoice_cufe
                or (self.move_id.cufe if self.move_id else '')
                or (getattr(self.move_id, 'cufe_cuds_other_system', '') if self.move_id else '')
            )
        if not cufe_value:
            raise UserError(_(
                "No se encontró el CUFE de la factura referenciada. "
                "Verifique que el XML del proveedor fue procesado correctamente."
            ))

        # Asegurar CUDE antes de construir el QR
        if not self.cude:
            self._compute_cude()
        if not self.cude:
            raise UserError(_("No se pudo calcular el CUDE para el evento."))

        qr_base = (
            "https://catalogo-vpfe.dian.gov.co"
            if self.company_id.production
            else "https://catalogo-vpfe-hab.dian.gov.co"
        )

        data = {
            # Identificación
            'InvoiceID': self.name,
            'UUID': self.cude,
            'IssueDate': self.issue_date,
            'IssueTime': self.issue_time,
            'ProfileExecutionID': ambiente,
            # Tipo documento para firmas (ApplicationResponse)
            'document_code': 'AR',
            
            # Evento
            'ResponseCode': self.response_code,
            'ResponseDescription': {
                '030': 'Acuse de recibo de Factura Electrónica de Venta',
                '031': 'Reclamo de la Factura Electrónica de Venta',
                '032': 'Recibo del bien y/o prestación del servicio',
                '033': 'Aceptación expresa',
                '034': 'Aceptación tácita',
            }.get(self.response_code, self.response_code),
            'DocumentTypeCode': self.document_type_code,
            'Notes': self.notes_xml or '',
            
            # Software
            'SoftwareProviderID': self.company_id.partner_id.vat_co,
            'SoftwareProviderSchemeID': '9',  # Identificación NIT en DIAN (no usar DV)
            'SoftwareID': software_id,
            'SoftwareSecurityCode': software_security_code,
            
            # Emisor
            'SenderPartyName': self._escape_xml(sender_partner.name),
            'SenderSchemeID': sender_partner.dv or '',
            'SenderSchemeName': sender_partner.l10n_latam_identification_type_id.dian_code,
            'SenderIDtext': sender_partner.vat_co,
            'SenderTaxSchemeID': sender_partner.tribute_id.code,
            'SenderTaxSchemeName': sender_partner.tribute_id.name,
            'SenderTaxLevelCode': sender_fiscal_resp,
            'SenderListName': '48',
            
            # Receptor (usar datos extraídos del XML si están disponibles)
            'CustomerPartyName': '',
            'CustomerschemeID': '',
            'CustomerID': '31',
            'CustomercompanyIDtext': self.doc_adq or '',
            'CustomerTaxSchemeID': '01',
            'CustomerTaxSchemeName': 'IVA',
            'CustomerTaxLevelCode': 'R-99-PN',
            'CustomerListName': '48',
            
            # Referencia
            'InvoiceReferenceID': self.document_referenced,
            'UUIDinvoice': cufe_value,
            
            # Persona
            'PersonSchemeID': self.user_id.partner_id.dv or '',
            'PersonSchemeName': self.user_id.partner_id.l10n_latam_identification_type_id.dian_code,
            'PersonID': self.user_id.partner_id.vat_co,
            # Compatibility: some DBs/modules used a typo `firs_name`; lavish_erp uses `first_name`.
            'PersonFirstName': self._escape_xml(
                (getattr(self.user_id.partner_id, 'first_name', False)
                 or getattr(self.user_id.partner_id, 'firs_name', False)
                 or self.user_id.partner_id.name)
            ),
            'PersonFamilyName': self._escape_xml(self.user_id.partner_id.first_lastname or ''),
            'PersonJobTitle': self._escape_xml(self.user_id.partner_id.function or 'Auxiliar'),
            'PersonOrganizationDepartment': 'Contabilidad',
            
            # Certificados
            **cert_info,
            
            # Archivos
            'FileNameXML': f'ar{self.name}.xml',
            'FileNameZIP': f'ar{self.name}.zip',
            
            # Tipo documento para firma
            'InvoiceTypeCode': 'AR',  # Application Response
            
            # QR (según Anexo Técnico, el ApplicationResponse referencia el CUFE del documento)
            'QRCode': f"{qr_base}/document/searchqr?documentkey={cufe_value}",
        }
        
        # Completar datos del receptor
        if self.invoice_receiver_name:
            # Usar datos extraídos del XML
            customer_partner = self.move_id.partner_id if self.move_id else False
            customer_fiscal_resp = ';'.join(
                customer_partner.fiscal_responsability_ids.mapped('code')
            ) if customer_partner and customer_partner.fiscal_responsability_ids else 'R-99-PN'
            data.update({
                'CustomerPartyName': self._escape_xml(self.invoice_receiver_name),
                'CustomerschemeID': self.invoice_receiver_dv or '',
                'CustomerID': self.invoice_receiver_scheme or '31',
                'CustomercompanyIDtext': self.invoice_receiver_vat or self.doc_adq or '',
                'CustomerTaxLevelCode': customer_fiscal_resp,
                'UUIDinvoice': cufe_value,
            })
        elif self.move_id:
            # Usar datos de la factura
            data.update(self._get_invoice_party_data())
        
        return data
    
    def generate_dian_xml(self):
        """Genera el XML del ApplicationResponse"""
        self.ensure_one()
        
        try:
            # Recolectar datos
            data = self._collect_all_dian_data()
            
            # Construir XML
            xml_element = self._build_xml_structure(data)
            
            # Convertir a string
            xml_string = etree.tostring(
                xml_element,
                encoding='unicode',
                method='xml',
                pretty_print=True
            )
            
            # Agregar declaración
            if not xml_string.startswith('<?xml'):
                xml_string = '<?xml version="1.0" encoding="UTF-8"?>' + xml_string
            
            # Guardar
            self.response_xml = xml_string
            self.xml_text = xml_string
            
            return xml_string
            
        except Exception as e:
            _logger.error(f"Error generando XML: {str(e)}", exc_info=True)
            raise UserError(f"Error al generar XML: {str(e)}")
    
    def _build_xml_structure(self, data):
        """Construye estructura XML usando lxml.builder"""
        # Namespaces
        nsmap = {
            None: "urn:oasis:names:specification:ubl:schema:xsd:ApplicationResponse-2",
            'cac': "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
            'cbc': "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
            'ext': "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
            'sts': "dian:gov:co:facturaelectronica:Structures-2-1",
            'xsi': "http://www.w3.org/2001/XMLSchema-instance",
            'ds': "http://www.w3.org/2000/09/xmldsig#",
            'xades': "http://uri.etsi.org/01903/v1.3.2#",
            'xades141': "http://uri.etsi.org/01903/v1.4.1#",
        }
        
        # Element makers
        CAC = ElementMaker(namespace=nsmap['cac'], nsmap=nsmap)
        CBC = ElementMaker(namespace=nsmap['cbc'], nsmap=nsmap)
        EXT = ElementMaker(namespace=nsmap['ext'], nsmap=nsmap)
        STS = ElementMaker(namespace=nsmap['sts'], nsmap=nsmap)
        
        # Root
        root = etree.Element(
            "{urn:oasis:names:specification:ubl:schema:xsd:ApplicationResponse-2}ApplicationResponse",
            nsmap=nsmap
        )
        
        root.set(
            "{http://www.w3.org/2001/XMLSchema-instance}schemaLocation",
            "urn:oasis:names:specification:ubl:schema:xsd:ApplicationResponse-2 "
            "http://docs.oasis-open.org/ubl/os-UBL-2.1/xsd/maindoc/UBL-ApplicationResponse-2.1.xsd"
        )
        
        # UBL Extensions
        extensions = EXT.UBLExtensions(
            EXT.UBLExtension(
                EXT.ExtensionContent(
                    STS.DianExtensions(
                        STS.InvoiceSource(
                            CBC.IdentificationCode(
                                "CO",
                                listAgencyID="6",
                                listAgencyName="United Nations Economic Commission for Europe",
                                listSchemeURI="urn:oasis:names:specification:ubl:codelist:gc:CountryIdentificationCode-2.1"
                            )
                        ),
                        STS.SoftwareProvider(
                            STS.ProviderID(
                                data['SoftwareProviderID'],
                                schemeID=data['SoftwareProviderSchemeID'],
                                schemeName="31",
                                schemeAgencyID="195",
                                schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)"
                            ),
                            STS.SoftwareID(
                                data['SoftwareID'],
                                schemeAgencyID="195",
                                schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)"
                            )
                        ),
                        STS.SoftwareSecurityCode(
                            data['SoftwareSecurityCode'],
                            schemeAgencyID="195",
                            schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)"
                        ),
                        STS.AuthorizationProvider(
                            STS.AuthorizationProviderID(
                                "800197268",
                                schemeID="4",
                                schemeName="31",
                                schemeAgencyID="195",
                                schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)"
                            )
                        ),
                        STS.QRCode(data['QRCode'])
                    )
                )
            ),
            EXT.UBLExtension(EXT.ExtensionContent())  # Para firma
        )
        root.append(extensions)
        
        # Header
        root.append(CBC.UBLVersionID("UBL 2.1"))
        root.append(CBC.CustomizationID("1"))
        root.append(CBC.ProfileID("DIAN 2.1: ApplicationResponse de la Factura Electrónica de Venta"))
        root.append(CBC.ProfileExecutionID(data['ProfileExecutionID']))
        root.append(CBC.ID(data['InvoiceID']))
        root.append(CBC.UUID(
            data['UUID'],
            schemeID=data['ProfileExecutionID'],
            schemeName="CUDE-SHA384"
        ))
        root.append(CBC.IssueDate(data['IssueDate']))
        root.append(CBC.IssueTime(data['IssueTime']))
        
        if data.get('Notes'):
            root.append(CBC.Note(data['Notes']))
        
        # SenderParty
        sender = CAC.SenderParty(
            CAC.PartyTaxScheme(
                CBC.RegistrationName(data['SenderPartyName']),
                CBC.CompanyID(
                    data['SenderIDtext'],
                    schemeAgencyID="195",
                    schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)",
                    schemeID=data['SenderSchemeID'],
                    schemeName=data['SenderSchemeName'],
                    schemeVersionID="1"
                ),
                CBC.TaxLevelCode(
                    data['SenderTaxLevelCode'],
                    listName=data['SenderListName']
                ),
                CAC.TaxScheme(
                    CBC.ID(data['SenderTaxSchemeID']),
                    CBC.Name(data['SenderTaxSchemeName'])
                )
            )
        )
        root.append(sender)
        
        # ReceiverParty
        receiver = CAC.ReceiverParty(
            CAC.PartyTaxScheme(
                CBC.RegistrationName(data['CustomerPartyName']),
                CBC.CompanyID(
                    data['CustomercompanyIDtext'],
                    schemeAgencyID="195",
                    schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)",
                    schemeID=data['CustomerschemeID'],
                    schemeName=data['CustomerID'],
                    schemeVersionID="1"
                ),
                CBC.TaxLevelCode(
                    data['CustomerTaxLevelCode'],
                    listName=data['CustomerListName']
                ),
                CAC.TaxScheme(
                    CBC.ID(data['CustomerTaxSchemeID']),
                    CBC.Name(data['CustomerTaxSchemeName'])
                )
            )
        )
        root.append(receiver)
        
        # DocumentResponse
        doc_response = CAC.DocumentResponse(
            CAC.Response(
                CBC.ResponseCode(data['ResponseCode']),
                CBC.Description(data['ResponseDescription'])
            ),
            CAC.DocumentReference(
                CBC.ID(data['InvoiceReferenceID']),
                CBC.UUID(data['UUIDinvoice'], schemeName="CUFE-SHA384"),
                CBC.DocumentTypeCode(data['DocumentTypeCode'])
            ),
            CAC.IssuerParty(
                CAC.Person(
                    CBC.ID(
                        data['PersonID'],
                        schemeID=data['PersonSchemeID'],
                        schemeName=data['PersonSchemeName']
                    ),
                    CBC.FirstName(data['PersonFirstName']),
                    CBC.FamilyName(data['PersonFamilyName']),
                    CBC.JobTitle(data['PersonJobTitle']),
                    CBC.OrganizationDepartment(data['PersonOrganizationDepartment'])
                )
            )
        )
        root.append(doc_response)
        
        return root
    
    def _sign_xml_document_complete(self, xml_content, dian_constants):
        """
        Override para firmar Application Response correctamente.
        El ApplicationResponse requiere la firma en el segundo UBLExtension.
        """
        try:
            # Convertir a string si es necesario
            if isinstance(xml_content, bytes):
                xml_content = xml_content.decode('utf-8')

            # Remover declaración XML existente
            if xml_content.startswith('<?xml'):
                xml_start = xml_content.find('?>') + 2
                xml_content = xml_content[xml_start:].strip()

            # IMPORTANTE: El método parent _sign_xml_document_complete busca
            # "<ext:ExtensionContent/>" para insertar la firma.
            # Odoo la genera para las facturas, buscando el PRIMER ExtensionContent vacío.
            # Para ApplicationResponse, tenemos 2 ExtensionContent:
            # - Primero: Datos DIAN (con QRCode, etc)
            # - Segundo: VACÍO para la firma

            # El método parent firmará el PRIMERO que encuentre vacío.
            # Eso es exactamente lo que queremos: el segundo UBLExtension

            # Llamar al método parent que maneja toda la firma
            signed_xml = super()._sign_xml_document_complete(xml_content, dian_constants)

            return signed_xml

        except Exception as e:
            _logger.error(f"Error firmando ApplicationResponse XML: {str(e)}", exc_info=True)
            raise UserError(_("Error al firmar el ApplicationResponse: %s") % str(e))

    # =============================================================================
    # ENVÍO A DIAN (EVENTOS RADIAN)
    # =============================================================================

    def _send_to_dian_service(self, signed_xml, dian_constants):
        """Override: eventos RADIAN usan SendEventUpdateStatus (hab y prod)."""
        zip_content = self._create_zip_content(signed_xml, dian_constants)
        return self._send_event_update_status(zip_content, dian_constants)

    def _send_event_update_status(self, zip_content, dian_constants):
        """Envía evento a DIAN usando SendEventUpdateStatus."""
        from . import xml_utils
        response = xml_utils._build_and_send_request(
            self,
            payload={
                'content_file': base64.b64encode(zip_content).decode(),
                'soap_body_template': 'l10n_co_e_invoice.send_event_update_status',
            },
            service='SendEventUpdateStatus',
            company=self.company_id,
        )

        if response['status_code'] == 200:
            return self._parse_sync_response(response['response'])
        return {
            'status': 'error',
            'response': response.get('response', ''),
            'status_code': response.get('status_code', 0),
        }
    
    # =============================================================================
    # MÉTODOS DE ACCIÓN
    # =============================================================================
    
    def action_send_dian(self):
        """Envía evento a DIAN"""
        self.ensure_one()
        
        if not self.requires_event:
            self._mark_as_not_required()
            return True
        
        try:
            # Enviar usando mixin
            self.dian_send_invoice()
            
            # Alinear status con estado DIAN si fue exitoso
            if self.state_dian_document == 'exitoso' and self.status != 'exitoso':
                self.status = 'exitoso'
            
            # Si es exitoso y debe enviar email
            if self.state_dian_document == 'exitoso' and self.send_email:
                self._send_event_email()
                
        except Exception as e:
            # Verificar si ya existe
            error_msg = str(e).lower()
            if 'ya existe' in error_msg or 'already exists' in error_msg or 'duplicado' in error_msg:
                self._try_recover_existing_event()
            else:
                raise
    
    def action_send_all_events(self):
        """Envía todos los eventos pendientes"""
        # Buscar eventos pendientes
        pending_events = self.search([
            ('status', '=', 'por_notificar'),
            ('requires_event', '=', True)
        ], order='create_date asc')
        
        if not pending_events:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sin eventos pendientes'),
                    'message': _('No hay eventos pendientes por enviar.'),
                    'type': 'warning',
                    'sticky': False,
                }
            }
        
        # Contadores
        sent = 0
        errors = 0
        recovered = 0
        
        for event in pending_events:
            try:
                event.action_send_dian()
                if event.was_recovered:
                    recovered += 1
                else:
                    sent += 1
            except Exception as e:
                errors += 1
                _logger.error(f"Error enviando evento {event.name}: {str(e)}")
        
        # Mensaje de resultado
        message_parts = []
        if sent:
            message_parts.append(f"{sent} eventos enviados")
        if recovered:
            message_parts.append(f"{recovered} eventos recuperados")
        if errors:
            message_parts.append(f"{errors} errores")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Proceso completado'),
                'message': ', '.join(message_parts),
                'type': 'success' if not errors else 'warning',
                'sticky': False,
            }
        }
    
    def action_send_email(self):
        """Acción manual para enviar email"""
        self.ensure_one()
        self._send_event_email(force=True)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Email Enviado'),
                'message': _('El email del evento ha sido enviado.'),
                'type': 'success',
                'sticky': False,
            }
        }
    
    def action_view_invoice(self):
        """Abre la factura relacionada"""
        self.ensure_one()
        if not self.move_id:
            raise UserError(_("No hay factura asociada"))
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Factura'),
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_download_xml(self):
        """Descarga el XML del evento"""
        self.ensure_one()
        if not self.dian_xml_attachment_id:
            raise UserError(_("No hay XML disponible"))
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{self.dian_xml_attachment_id.id}?download=true',
            'target': 'self',
        }
    
    def dian_preview(self):
        """Vista previa en portal DIAN"""
        self.ensure_one()
        if self.cude:
            return {
                'type': 'ir.actions.act_url',
                'target': 'new',
                'url': f"{'https://catalogo-vpfe.dian.gov.co' if self.company_id.production else 'https://catalogo-vpfe-hab.dian.gov.co'}/document/searchqr?documentkey={self.cude}",
            }
    
    # =============================================================================
    # EMAIL METHODS
    # =============================================================================
    
    def _send_event_email(self, force=False):
        """Envía email del evento con lógica contextual"""
        self.ensure_one()
        
        # Validar si debe enviar
        if not force and (self.email_sent or not self.send_email):
            return
        
        # Determinar template y destinatario
        if self._context.get('from_invoice') and self.move_id:
            # Usar template de contabilidad
            self._send_from_invoice_context()
        else:
            # Usar template propio
            self._send_standalone_email()
        
        # Marcar como enviado
        self.email_sent = True
    
    def _send_from_invoice_context(self):
        """Envía email usando contexto de factura"""
        template = self.env.ref('account.email_template_edi_invoice', False)
        if template and self.move_id:
            # Agregar contexto del evento
            ctx = {
                'event_data': {
                    'code': self.response_code,
                    'name': dict(self._fields['response_code'].selection).get(self.response_code),
                    'cude': self.cude,
                }
            }
            template.with_context(ctx).send_mail(self.move_id.id, force_send=True)
    
    def _send_standalone_email(self):
        """Envía email standalone del evento"""
        template = self.env.ref('l10n_co_e_invoice.email_template_application_response', False)
        if template:
            template.send_mail(self.id, force_send=True)
    
    # =============================================================================
    # MÉTODOS AUXILIARES
    # =============================================================================
    
    def _validate_required_data(self):
        """Valida datos requeridos"""
        errors = []
        
        if not self.user_id.partner_id.vat_co:
            errors.append(f'Falta NIT en {self.user_id.partner_id.name}')
        
        if not self.user_id.partner_id.function:
            errors.append(f'Falta cargo/función en {self.user_id.partner_id.name}')
        
        if errors:
            raise ValidationError('\n'.join(errors))
    
    def _get_invoice_party_data(self):
        """Obtiene datos del tercero desde la factura"""
        data = {}
        if self.move_id:
            partner = self.move_id.partner_id
            fiscal_resp = ';'.join(
                partner.fiscal_responsability_ids.mapped('code')
            ) if partner.fiscal_responsability_ids else 'R-99-PN'
            if self.move_id.move_type in ('in_invoice', 'in_refund'):
                cufe_value = getattr(self.move_id, 'cufe_cuds_other_system', '') or ''
            else:
                cufe_value = (
                    self.invoice_cufe
                    or self.move_id.cufe
                    or getattr(self.move_id, 'cufe_cuds_other_system', '')
                )
            data.update({
                'CustomerPartyName': self._escape_xml(partner.name),
                'CustomerschemeID': partner.dv or '',
                'CustomerID': partner.l10n_latam_identification_type_id.dian_code or "31",
                'CustomercompanyIDtext': partner.vat_co or '',
                'CustomerTaxSchemeID': partner.tribute_id.code if partner.tribute_id else '01',
                'CustomerTaxSchemeName': partner.tribute_id.name if partner.tribute_id else 'IVA',
                'CustomerTaxLevelCode': fiscal_resp,
                'CustomerListName': '48',
                'UUIDinvoice': cufe_value or '',
            })
        return data
    
    def _get_tacit_acceptance_note(self, invoice):
        """Genera nota para aceptación tácita"""
        partner_name = invoice.partner_id.name
        doc_adq = invoice.partner_id.vat_co
        
        return (
            f'Manifiesto bajo la gravedad de juramento que transcurridos 3 días hábiles '
            f'siguientes a la fecha de recepción de la mercancía o del servicio en la referida '
            f'factura de este evento, el adquirente {partner_name} identificado con NIT '
            f'{doc_adq} no manifestó expresamente la aceptación o rechazo de la referida factura, '
            f'ni reclamó en contra de su contenido.'
        )
    
    def _escape_xml(self, text):
        """Escapa caracteres especiales para XML"""
        if not text:
            return ''
        
        replacements = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&apos;',
        }
        
        for char, replacement in replacements.items():
            text = str(text).replace(char, replacement)
        
        return text
    
    def _generate_software_security_code(self, software_id, pin, invoice_name):
        """Genera código de seguridad del software"""
        h = hashlib.sha384()
        h.update((software_id + pin + invoice_name).encode('utf-8'))
        return h.hexdigest()
    
    # =============================================================================
    # OVERRIDE MIXIN METHODS
    # =============================================================================
    
    def _get_dian_document_type_dian(self):
        """Tipo de documento para DIAN"""
        return 'ar'
    
    def _is_dian_applicable(self):
        """Verifica si aplica para DIAN"""
        return (
            self.status == 'por_notificar' and
            self.response_code and
            self.doc_adq and
            self.document_referenced and
            self.requires_event
        )
    
    def _process_dian_response(self, response, dian_constants):
        """Procesa respuesta con manejo de duplicados"""
        # Verificar si ya existe
        if response.get('errors'):
            for error in response['errors']:
                error_str = str(error).lower()
                if any(keyword in error_str for keyword in ['ya existe', 'already exists', 'duplicado']):
                    self._try_recover_existing_event()
                    return
        
        # Proceso normal
        super()._process_dian_response(response, dian_constants)
        if self.state_dian_document == 'exitoso':
            self._update_invoice_last_event()


class AccountMove(models.Model):
    """Extiende account.move con funcionalidad de eventos"""
    _inherit = 'account.move'
 
    # Relación con eventos
    event_ids = fields.One2many(
        'dian.application.response',
        'move_id',
        string='Eventos DIAN'
    )
    
    event_count = fields.Integer(
        string='# Eventos',
        compute='_compute_event_count',
        store=True
    )
    
    # Campos planos para último evento
    last_event_code = fields.Char('Último Evento')
    last_event_date = fields.Datetime('Fecha Último Evento')
    last_event_cude = fields.Char('CUDE Último Evento')
    
    # Control para nota crédito
    requires_credit_note = fields.Boolean(
        string='Requiere Nota Crédito',
        tracking=True,
        help='Se marca cuando se genera un reclamo'
    )
    
    # Campo legacy para compatibilidad
    tiene_eventos = fields.Boolean(
        string='Tiene Eventos',
        compute='_compute_tiene_eventos',
        store=True
    )
    
    # Campo legacy titulo_state para compatibilidad con vistas existentes
    titulo_state = fields.Selection(selection_add=[
        ('grey', 'Sin Eventos'),
        ('yellow', 'Con Eventos'),
        ('green', 'Título Valor'),
    ], ondelete={'grey': 'cascade', 'yellow': 'cascade', 'green': 'cascade'},
        string='Estado Título (Legacy)', compute='_compute_titulo_state', store=True)
    
    # Campo legacy para flujo de eventos
    last_event_status = fields.Char(
        string='Último Estado Evento',
        compute='_compute_last_event_status',
        store=True
    )
    
    # Estado título valor
    is_titulo_valor = fields.Boolean(
        string='Es Título Valor',
        compute='_compute_titulo_valor',
        search='_search_titulo_valor',
        store=True
    )
    
    titulo_valor_state = fields.Selection([
        ('none', 'Sin Eventos'),
        ('partial', 'Con Eventos'),
        ('complete', 'Título Valor')
    ], compute='_compute_titulo_valor_state', store=True, string='Estado Título Valor')

    can_apply_aceptacion_tacita = fields.Boolean(
        string='Puede aplicar Aceptación Tácita',
        compute='_compute_can_apply_aceptacion_tacita',
        store=False
    )
    
    @api.depends('event_ids')
    def _compute_event_count(self):
        for record in self:
            record.event_count = len(record.event_ids)
    
    @api.depends('event_ids')
    def _compute_tiene_eventos(self):
        for record in self:
            record.tiene_eventos = bool(record.event_ids)
    
    @api.depends('event_ids', 'event_ids.is_titulo_valor')
    def _compute_titulo_valor(self):
        for record in self:
            record.is_titulo_valor = any(
                event.is_titulo_valor for event in record.event_ids
            )
    
    def _search_titulo_valor(self, operator, value):
        """Permite buscar por título valor"""
        if operator == '=' and value:
            # Buscar facturas con eventos de título valor exitosos
            events = self.env['dian.application.response'].search([
                ('response_code', 'in', ['033', '034']),
                ('status', '=', 'exitoso')
            ])
            return [('id', 'in', events.mapped('move_id').ids)]
        return []
    
    @api.depends('event_ids', 'is_titulo_valor')
    def _compute_titulo_valor_state(self):
        for record in self:
            if record.is_titulo_valor:
                record.titulo_valor_state = 'complete'
            elif record.event_ids:
                record.titulo_valor_state = 'partial'
            else:
                record.titulo_valor_state = 'none'
    
    @api.depends('titulo_valor_state')
    def _compute_titulo_state(self):
        """Mapeo para campo legacy titulo_state"""
        for record in self:
            mapping = {
                'none': 'grey',
                'partial': 'yellow', 
                'complete': 'green'
            }
            record.titulo_state = mapping.get(record.titulo_valor_state, 'grey')
    
    @api.depends('event_ids', 'event_ids.response_code', 'event_ids.status')
    def _compute_last_event_status(self):
        """Calcula el último estado del evento para compatibilidad con flujo"""
        for record in self:
            # Buscar el último evento exitoso
            last_event = record.event_ids.filtered(
                lambda e: e.status == 'exitoso'
            ).sorted('create_date', reverse=True)[:1]
            
            if last_event:
                record.last_event_status = last_event.response_code
            else:
                record.last_event_status = False

    @api.depends('event_ids', 'event_ids.response_code', 'event_ids.status', 'move_type')
    def _compute_can_apply_aceptacion_tacita(self):
        """Solo habilita 034 después de 3 días hábiles desde el 032 y solo para ventas."""
        for record in self:
            # Debe existir 030 y 032 exitosos y no debe existir 031/033/034
            has_030 = record._has_success_event('030')
            has_032 = record._has_success_event('032')
            has_031 = record._has_success_event('031')
            has_033 = record._has_success_event('033')
            has_034 = record._has_success_event('034')

            if not has_030 or not has_032 or has_031 or has_033 or has_034:
                record.can_apply_aceptacion_tacita = False
                continue

            last_032 = record._get_last_success_event('032')
            last_032_dt = last_032.create_date if last_032 else False
            days = record._business_days_between(last_032_dt, fields.Datetime.now())
            record.can_apply_aceptacion_tacita = days >= 3

    def _reverse_moves(self, default_values_list=None, cancel=False):
        """Bloquea NC/ND si hay aceptación (033/034) exitosa."""
        for move in self:
            if move.event_ids.filtered(lambda e: e.status == 'exitoso' and e.response_code in ('033', '034')):
                raise UserError(_("No se pueden crear Notas Crédito/Débito si la factura ya fue aceptada (033/034)."))
        return super()._reverse_moves(default_values_list=default_values_list, cancel=cancel)

    # =============================================================================
    # VALIDACIONES DE FLUJO DIAN
    # =============================================================================

    def _get_last_success_event(self, code):
        self.ensure_one()
        return self.event_ids.filtered(
            lambda e: e.status == 'exitoso' and e.response_code == code
        ).sorted('create_date', reverse=True)[:1]

    def _has_success_event(self, code):
        self.ensure_one()
        return bool(self._get_last_success_event(code))

    def _business_days_between(self, start_dt, end_dt):
        """Cuenta días hábiles entre dos fechas (lunes-viernes)."""
        if not start_dt or not end_dt:
            return 0
        start_date = fields.Datetime.to_datetime(start_dt).date()
        end_date = fields.Datetime.to_datetime(end_dt).date()
        if end_date < start_date:
            start_date, end_date = end_date, start_date
        days = 0
        cur = start_date
        while cur < end_date:
            cur = cur + relativedelta(days=1)
            if cur.weekday() < 5:
                days += 1
        return days

    def _validate_dian_event_flow(self, event_code):
        """Valida el flujo DIAN para eventos 030/031/032/033/034."""
        self.ensure_one()

        # Solo aplica para facturas (in/out)
        if self.move_type not in ('in_invoice', 'in_refund', 'out_invoice', 'out_refund'):
            return

        # Debe ser a crédito (fecha vencimiento mayor a fecha factura)
        if not (self.invoice_date and self.invoice_date_due and self.invoice_date_due > self.invoice_date):
            raise UserError(_("Solo se permiten eventos DIAN para facturas a crédito (con fecha de vencimiento)."))

        # Debe estar validada por DIAN o tener CUFE/CUDS
        if self.move_type in ('in_invoice', 'in_refund'):
            cufe_value = getattr(self, 'cufe_cuds_other_system', False)
        else:
            cufe_value = self.cufe or getattr(self, 'cufe_cuds_other_system', False)
        if self.state_dian_document != 'exitoso' and not cufe_value:
            raise UserError(_("La factura debe estar validada por DIAN o tener CUFE/CUDS."))

        # Reglas de secuencia
        has_030 = self._has_success_event('030')
        has_032 = self._has_success_event('032')
        has_031 = self._has_success_event('031')
        has_033 = self._has_success_event('033')
        has_034 = self._has_success_event('034')

        if event_code == '030':
            return

        if event_code == '032':
            if not has_030:
                raise UserError(_("Debe registrar primero el Acuse de Recibo (030)."))
            return

        if event_code == '031':
            if not has_030 or not has_032:
                raise UserError(_("El Reclamo (031) solo puede registrarse después del Acuse (030) y Recibo del bien (032)."))
            return

        if event_code in ('033', '034'):
            if not has_030 or not has_032:
                raise UserError(_("La Aceptación requiere Acuse (030) y Recibo del bien (032)."))
            if has_031:
                raise UserError(_("No se puede aceptar una factura que ya tiene Reclamo (031)."))
            if has_033 or has_034:
                raise UserError(_("Ya existe una Aceptación registrada para esta factura."))

            # Validar ventana de tiempo vs evento 032
            last_032 = self._get_last_success_event('032')
            last_032_dt = last_032.create_date if last_032 else False
            days = self._business_days_between(last_032_dt, fields.Datetime.now())

            if event_code == '033' and days > 3:
                raise UserError(_("La Aceptación Expresa (033) debe registrarse dentro de los 3 días hábiles posteriores al Recibo del bien (032)."))

            if event_code == '034':
                # La aceptación tácita la genera el emisor (ventas)
                if self.move_type not in ('out_invoice', 'out_refund'):
                    raise UserError(_("La Aceptación Tácita (034) solo puede generarse por el emisor (facturas de venta)."))
                if days < 3:
                    raise UserError(_("La Aceptación Tácita (034) solo puede registrarse después de 3 días hábiles desde el Recibo del bien (032)."))

            return
    
    # =============================================================================
    # BOTONES DE ACCIÓN
    # =============================================================================
    
    def action_create_event(self, event_code, notes=None):
        """Crea un evento desde la factura"""
        self.ensure_one()

        # Validar flujo DIAN
        self._validate_dian_event_flow(event_code)
        
        # Determinar si enviar email
        send_email = self._context.get('send_email', True)
        
        # Contexto para el evento
        context_data = {
            'send_email': send_email,
            'notes': notes
        }
        
        # Crear evento
        event = self.env['dian.application.response'].with_context(
            from_invoice=True,
            send_email=send_email
        ).generate_from_invoice(
            self.id,
            event_code,
            context_data
        )
        
        # Abrir evento creado
        return {
            'type': 'ir.actions.act_window',
            'name': _('Evento DIAN'),
            'res_model': 'dian.application.response',
            'res_id': event.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_dian_acuse_recibo(self):
        """Botón: Acuse de recibo"""
        return self.action_create_event('030')
    
    def action_dian_reclamo(self):
        """Botón: Reclamo"""
        # Pedir motivo del reclamo
        notes = self._context.get('reclamo_notes', 'Inconformidad con el documento')
        # Marcar factura como requiere NC
        if self.move_type == 'out_invoice':
            self.requires_credit_note = True
        return self.action_create_event('031', notes=notes)
    
    def action_dian_recibo_bien(self):
        """Botón: Recibo del bien"""
        return self.with_context(send_email=False).action_create_event('032')
    
    def action_dian_aceptacion_expresa(self):
        """Botón: Aceptación expresa"""
        return self.action_create_event('033')
    
    def action_dian_aceptacion_tacita(self):
        """Botón: Aceptación tácita"""
        return self.action_create_event('034')
    
    def action_view_events(self):
        """Ver todos los eventos"""
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Eventos DIAN'),
            'res_model': 'dian.application.response',
            'view_mode': 'list,form,kanban',
            'domain': [('move_id', '=', self.id)],
            'context': {
                'default_move_id': self.id,
                'search_default_group_by_status': 1,
            }
        }
    
    def _reverse_moves(self, default_values_list=None, cancel=False):
        """Override para manejar requires_credit_note"""
        # Crear notas crédito
        reverse_moves = super()._reverse_moves(default_values_list,cancel)
        
        # Desmarcar flag en facturas originales
        for move in self:
            if move.requires_credit_note:
                move.requires_credit_note = False
        
        return reverse_moves
