# -*- coding: utf-8 -*-
import base64
import logging
import traceback
import xmltodict
import requests
from datetime import datetime, timedelta
from lxml import etree
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_round
from . import xml_utils

_logger = logging.getLogger(__name__)

class DianDocumentProcessor(models.Model):
    _name = 'dian.document.processor'
    _description = 'Procesador de Documentos Electrónicos DIAN'
    _inherit = [
        'mail.thread',
        'mail.activity.mixin',
        'business.document.import',
        'dian.xml.processing.mixin',
        'dian.partner.processing.mixin',
        'dian.tax.processing.mixin',
    ]
    _rec_name = 'document_number'
    
    # ========== IDENTIFICACIÓN ==========
    cufe = fields.Char('CUFE/CUDE', index=True, tracking=True)
    document_number = fields.Char('Número de Documento', tracking=True)
    document_type = fields.Selection([
        ('01', 'Factura electrónica de Venta'),
        ('02', 'Factura de Venta - Exportación'),
        ('03', 'Factura Contingencia Facturador'),
        ('04', 'Factura Contingencia DIAN'),
        ('05', 'Documento Soporte'),
        ('91', 'Nota Crédito'),
        ('92', 'Nota Débito'),
        ('95', 'Nota Ajuste Documento Soporte'),
        ('96', 'Eventos (ApplicationResponse)'),
    ], string='Tipo de Documento', tracking=True)
    operation_type = fields.Selection([
        # Factura electrónica
        ('09', 'AIU'),
        ('10', 'Estándar'),
        ('11', 'Mandatos bienes y/o servicios'),
        ('12', 'Transporte'),
        ('13', 'Cambiario'),
        ('14', 'Notarios'),
        ('15', 'Compra divisas'),
        ('16', 'Venta divisas'),
        # Nota Crédito
        ('20', 'NC referencia factura electrónica'),
        ('22', 'NC sin referencia a facturas'),
        ('23', 'NC para FE V1 (Decreto 2242)'),
        # Nota Débito
        ('30', 'ND referencia factura electrónica'),
        ('32', 'ND sin referencia a facturas'),
        ('33', 'ND para FE V1 (Decreto 2242)'),
        # Sector Salud
        ('SS-CUFE', 'Salud - Factura con CUFE'),
        ('SS-CUDE', 'Salud - Doc Soporte con CUDE'),
        ('SS-POS', 'Salud - Factura POS'),
        ('SS-SNum', 'Salud - Sin numeración DIAN'),
        ('SS-Recaudo', 'Salud - LPS Recaudo'),
        ('SS-Reporte', 'Salud - LPS Reporte'),
        ('SS-SinAporte', 'Salud - Sin Aporte Operador'),
    ], string='Tipo de Operación', tracking=True)
    discrepancy_code = fields.Selection([
        ('1', 'Devolución parcial de bienes / No aceptación parcial del servicio'),
        ('2', 'Anulación de factura electrónica'),
        ('3', 'Rebaja total aplicada'),
        ('4', 'Descuento total aplicado'),
        ('5', 'Rescisión: nulidad por acuerdo de las partes'),
        ('6', 'Otros'),
    ], string='Concepto Corrección NC', tracking=True)
    debit_discrepancy_code = fields.Selection([
        ('1', 'Intereses'),
        ('2', 'Gastos por cobrar'),
        ('3', 'Cambio del valor'),
        ('4', 'Otro'),
    ], string='Concepto Corrección ND', tracking=True)

    # ========== FECHAS ==========
    issue_date = fields.Date('Fecha de Emisión', tracking=True)
    due_date = fields.Date('Fecha de Vencimiento', tracking=True)
    invoice_period_start = fields.Date('Periodo Facturación Desde')
    invoice_period_end = fields.Date('Periodo Facturación Hasta')
    
    # ========== MONEDA Y TASA DE CAMBIO ==========
    currency_id = fields.Many2one('res.currency', 'Moneda', default=lambda self: self.env.company.currency_id)
    exchange_rate = fields.Float('Tasa de Cambio', digits=(12, 6), tracking=True,
                                help="Tasa de cambio del día. Si está vacío, se obtiene automáticamente")
    exchange_rate_date = fields.Date('Fecha Tasa de Cambio', tracking=True)
    document_currency_id = fields.Many2one('res.currency', 'Moneda del Documento')
    
    # ========== REFERENCIAS ==========
    order_reference = fields.Char('Orden de Compra')
    despatch_reference = fields.Char('Referencia de Despacho')
    receipt_reference = fields.Char('Referencia de Recibo')
    contract_reference = fields.Char('Referencia de Contrato')
    
    # Referencias para NC/ND
    billing_reference_id = fields.Char('Factura de Referencia')
    billing_reference_cufe = fields.Char('CUFE de Referencia')
    billing_reference_date = fields.Date('Fecha Documento Referencia')
    credit_note_reason = fields.Text('Motivo Nota Crédito')
    debit_note_reason = fields.Text('Motivo Nota Débito')
    discrepancy_response_code = fields.Char('Código de Discrepancia')
    
    # ========== PAGOS ==========
    payment_means_code = fields.Selection([
        ('1', 'Instrumento no definido'),
        ('2', 'Crédito ACH'),
        ('3', 'Débito ACH'),
        ('4', 'Reversión débito de demanda ACH'),
        ('5', 'Reversión crédito de demanda ACH'),
        ('6', 'Crédito de demanda ACH'),
        ('7', 'Débito de demanda ACH'),
        ('8', 'Retención'),
        ('9', 'Cámara de compensación nacional'),
        ('10', 'Efectivo'),
        ('12', 'Giro'),
        ('13', 'Cámara de compensación nacional urgente'),
        ('14', 'Nota promisoria con fecha del mismo día'),
        ('15', 'Pago posterior con cuenta de depósito'),
        ('16', 'Pago posterior con Débito ACH'),
        ('17', 'Pago posterior con Crédito ACH'),
        ('18', 'Pago posterior con cuenta especial de depósito'),
        ('19', 'Pago posterior con depósito de cuenta corriente'),
        ('20', 'Cheque'),
        ('21', 'Cheque propio'),
        ('22', 'Cheque certificado'),
        ('23', 'Cheque del banco'),
        ('25', 'Cheque certificado del banco'),
        ('26', 'Cheque de factura de banco'),
        ('28', 'Cheque en dólares canadienses'),
        ('30', 'Transferencia crédito'),
        ('31', 'Transferencia débito'),
        ('32', 'Cuenta concentrada de efectivo'),
        ('33', 'Cuenta de concentración de efectivo / Desembolso'),
        ('34', 'Cuenta de concentración de efectivo (CCD) más adenda'),
        ('35', 'Transacción de pago corporativo comercial (CTP)'),
        ('38', 'Crédito ACH Sector Corporativo (CTX)'),
        ('39', 'Crédito ACH Sector Corporativo Plus (CTX)'),
        ('40', 'Pago ACH a la demanda'),
        ('41', 'Pago ACH urgente'),
        ('42', 'Débito en línea'),
        ('43', 'Crédito en línea'),
        ('44', 'Pago ACH sector comercial (CCD)'),
        ('45', 'Reversión del débito ACH sector comercial CCD'),
        ('46', 'Reversión del crédito ACH sector comercial CCD+'),
        ('47', 'Pago ACH sector comercial más adenda (CCD+)'),
        ('48', 'Tarjeta de Crédito'),
        ('49', 'Tarjeta Débito'),
        ('50', 'Postgiro'),
        ('51', 'Telex estándar bancario'),
        ('53', 'Giro de pago urgente'),
        ('54', 'Giro garantizado de banco a banco'),
        ('57', 'Efectos comerciales'),
        ('60', 'Nota promisoria'),
        ('61', 'Nota promisoria firmada por el acreedor'),
        ('62', 'Nota promisoria firmada por el acreedor, endosada por banco'),
        ('65', 'Nota promisoria firmada por el acreedor, endosada por tercero'),
        ('67', 'Letra de cambio firmada por el acreedor'),
        ('70', 'Letra de cambio firmada por el acreedor endosada por banco'),
        ('91', 'Nota bancaria transferible'),
        ('92', 'Cheque local'),
        ('93', 'Giro en moneda extranjera'),
        ('94', 'Orden de pago'),
        ('95', 'Carta de crédito'),
        ('96', 'Cheque de viajero'),
        ('97', 'Compensación entre socios'),
        ('ZZZ', 'Mutuamente definido'),
    ], string='Medio de Pago')
    payment_method_code = fields.Selection([
        ('1', 'Contado'),
        ('2', 'Crédito'),
    ], string='Método de Pago')
    payment_instruction_id = fields.Char('ID Instrucción de Pago',
                                        help='Identificador de la instrucción de pago del proveedor')
    
    # ========== TERCEROS ==========
    supplier_id = fields.Many2one('res.partner', 'Proveedor')
    customer_id = fields.Many2one('res.partner', 'Cliente')
    delivery_partner_id = fields.Many2one('res.partner', 'Tercero de Entrega')
    payee_partner_id = fields.Many2one('res.partner', 'Beneficiario/Mandato',
                                      help='Beneficiario del pago (para facturas con mandato)')
    carrier_partner_id = fields.Many2one('res.partner', 'Transportista',
                                        help='Empresa transportadora')
    
    # ========== TOTALES EN MONEDA DOCUMENTO ==========
    amount_untaxed = fields.Monetary('Base Imponible', currency_field='document_currency_id')
    amount_discount = fields.Monetary('Total Descuentos', currency_field='document_currency_id')
    amount_charges = fields.Monetary('Total Cargos', currency_field='document_currency_id')
    amount_prepaid = fields.Monetary('Total Anticipos', currency_field='document_currency_id')
    amount_tax = fields.Monetary('Total Impuestos', currency_field='document_currency_id')
    amount_withholding = fields.Monetary('Total Retenciones', currency_field='document_currency_id')
    amount_rounding = fields.Monetary('Redondeo', currency_field='document_currency_id',
                                      help='PayableRoundingAmount - Ajuste por redondeo')
    amount_total = fields.Monetary('Total Documento', currency_field='document_currency_id',
                                   help='TaxInclusiveAmount - Total con impuestos')
    payable_amount = fields.Monetary('Total a Pagar', currency_field='document_currency_id',
                                     help='PayableAmount - Monto final a pagar')
    
    # ========== TOTALES EN MONEDA LOCAL ==========
    amount_untaxed_local = fields.Monetary('Base Imponible (Local)', 
                                          currency_field='currency_id',
                                          compute='_compute_local_amounts', store=True)
    amount_total_local = fields.Monetary('Total (Local)', 
                                        currency_field='currency_id',
                                        compute='_compute_local_amounts', store=True)
    
    # ========== VALIDACIÓN ==========
    total_difference = fields.Monetary('Diferencia en Total', 
                                     currency_field='document_currency_id',
                                     compute='_compute_total_validation', store=True)
    has_validation_warning = fields.Boolean('Tiene Advertencia', 
                                           compute='_compute_total_validation', store=True)
    validation_message = fields.Text('Mensaje de Validación')
    
    # ========== LÍNEAS Y RESÚMENES ==========
    line_ids = fields.One2many('dian.document.processor.line', 'processor_id', 'Líneas')
    tax_summary_ids = fields.One2many('dian.document.processor.tax', 'processor_id', 'Resumen Impuestos')
    allowance_charge_ids = fields.One2many('dian.document.processor.allowance', 'processor_id', 'Descuentos/Cargos')
    prepaid_ids = fields.One2many('dian.document.processor.prepaid', 'processor_id', 'Anticipos')
    
    # ========== DOCUMENTOS RELACIONADOS ==========
    invoice_id = fields.Many2one('account.move', 'Factura en Odoo')
    related_credit_note_ids = fields.One2many('dian.document.processor', 
        compute='_compute_related_documents', string='Notas Crédito Relacionadas')
    related_debit_note_ids = fields.One2many('dian.document.processor',
        compute='_compute_related_documents', string='Notas Débito Relacionadas')
    
    # ========== XML Y ARCHIVOS ==========
    xml_content = fields.Binary('XML Original', attachment=True)
    xml_filename = fields.Char('Nombre XML')
    xml_invoice = fields.Text('XML Factura')
    pdf_file = fields.Binary('PDF Adjunto')
    pdf_filename = fields.Char('Nombre PDF')
    zip_file = fields.Binary('Archivo ZIP', help='Sube un archivo ZIP que contenga XML y PDF')
    zip_filename = fields.Char('Nombre ZIP')
    xml_retrieved_from_dian = fields.Boolean('XML Recuperado de DIAN', readonly=True)
    xml_retrieval_date = fields.Datetime('Fecha Recuperación XML', readonly=True)
    
    # ========== CONFIGURACIÓN ==========
    auto_predict_products = fields.Boolean('Predecir Productos Automáticamente', 
                                          default=lambda self: self.env.company.dian_auto_predict_products)
    update_product_codes = fields.Boolean('Actualizar Códigos de Productos', default=True)
    
    # ========== ESTADO ==========
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('xml_loaded', 'XML Cargado'),
        ('processed', 'Procesado'),
        ('validated', 'Validado'),
        ('invoiced', 'Facturado'),
        ('error', 'Error')
    ], default='draft', tracking=True)
    
    notes = fields.Text('Notas')
    error_log = fields.Text('Log de Errores')

    # ========== MÉTODOS DE EXTRACCIÓN ZIP Y PDF ==========
    def write(self, vals):
        """Override para adjuntar PDF al chatter cuando se actualiza el campo pdf_file"""
        result = super(DianDocumentProcessor, self).write(vals)

        # Si se actualizó el campo pdf_file, adjuntarlo al chatter
        if 'pdf_file' in vals and vals.get('pdf_file'):
            for record in self:
                if record.pdf_file and record.pdf_filename:
                    # Buscar si ya existe un adjunto con el mismo nombre
                    Attachment = self.env['ir.attachment']
                    existing_pdf = Attachment.search([
                        ('res_model', '=', self._name),
                        ('res_id', '=', record.id),
                        ('name', '=', record.pdf_filename),
                        ('mimetype', '=', 'application/pdf'),
                    ], limit=1)

                    if not existing_pdf:
                        # Crear adjunto con previsualización habilitada
                        attachment_vals = {
                            'name': record.pdf_filename,
                            'datas': record.pdf_file,
                            'res_model': self._name,
                            'res_id': record.id,
                            'mimetype': 'application/pdf',
                            'type': 'binary',
                            'description': 'PDF del documento DIAN',
                            'public': False,
                        }
                        pdf_attachment = Attachment.create(attachment_vals)

                        # Crear mensaje en chatter con el adjunto para preview
                        record.message_post(
                            body='<p>PDF del documento DIAN adjunto</p>',
                            attachment_ids=[pdf_attachment.id]
                        )
                        _logger.info(f"PDF adjuntado al chatter con preview: {record.pdf_filename}")

        return result

    # ========== CAMPOS COMPUTADOS ==========
    @api.depends('document_currency_id', 'exchange_rate', 'amount_untaxed', 'amount_total')
    def _compute_local_amounts(self):
        """Calcula montos en moneda local"""
        for record in self:
            if record.document_currency_id and record.document_currency_id != record.currency_id:
                if record.exchange_rate:
                    record.amount_untaxed_local = record.amount_untaxed * record.exchange_rate
                    record.amount_total_local = record.amount_total * record.exchange_rate
                else:
                    # Obtener tasa del sistema
                    rate = record.document_currency_id._get_conversion_rate(
                        record.document_currency_id,
                        record.currency_id,
                        record.env.company,
                        record.issue_date or fields.Date.today()
                    )
                    record.amount_untaxed_local = record.amount_untaxed * rate
                    record.amount_total_local = record.amount_total * rate
            else:
                record.amount_untaxed_local = record.amount_untaxed
                record.amount_total_local = record.amount_total
    
    @api.depends('line_ids', 'line_ids.price_total', 'amount_total', 'tax_summary_ids.tax_amount')
    def _compute_total_validation(self):
        """Valida que los totales calculados coincidan con el XML"""
        for record in self:
            # Calcular total desde líneas
            lines_subtotal = sum(record.line_ids.mapped('price_subtotal'))
            lines_tax = sum(record.tax_summary_ids.filtered(lambda x: not x.is_withholding).mapped('tax_amount'))
            lines_withholding = sum(record.tax_summary_ids.filtered('is_withholding').mapped('tax_amount'))
            lines_discount = sum(record.line_ids.mapped('discount_amount'))
            calculated_total = lines_subtotal + lines_tax - lines_withholding - lines_discount
            
            # Comparar con total del documento
            record.total_difference = calculated_total - record.amount_total
            
            # Verificar si hay diferencia significativa (más de 1 peso)
            precision = record.document_currency_id.decimal_places if record.document_currency_id else 2
            if float_compare(abs(record.total_difference), 1.0, precision_digits=precision) > 0:
                record.has_validation_warning = True
                record.validation_message = _(
                    "ADVERTENCIA: Diferencia en totales\n"
                    "Total XML: %s\n"
                    "Total Calculado: %s\n"
                    "Diferencia: %s\n"
                    "Posibles causas:\n"
                    "- Redondeo en cálculos\n"
                    "- Descuentos no aplicados correctamente\n"
                    "- Impuestos mal configurados"
                ) % (record.amount_total, calculated_total, record.total_difference)
            else:
                record.has_validation_warning = False
                record.validation_message = False
    
    @api.depends('billing_reference_cufe')
    def _compute_related_documents(self):
        """Busca documentos relacionados (NC/ND)"""
        for record in self:
            if record.cufe and record.document_type in ['01', '02', '03', '04', '05']:
                record.related_credit_note_ids = self.search([
                    ('billing_reference_cufe', '=', record.cufe),
                    ('document_type', '=', '91')
                ])
                record.related_debit_note_ids = self.search([
                    ('billing_reference_cufe', '=', record.cufe),
                    ('document_type', '=', '92')
                ])
            else:
                record.related_credit_note_ids = False
                record.related_debit_note_ids = False
    
    # ========== MÉTODOS PRINCIPALES ==========

    def _clean_existing_data(self):
        """Limpia toda la información existente antes de procesar para evitar duplicados"""
        self.ensure_one()

        _logger.info(f"Limpiando datos existentes del procesador {self.id}")

        # Eliminar líneas existentes
        if self.line_ids:
            self.line_ids.unlink()

        # Eliminar resumen de impuestos
        if self.tax_summary_ids:
            self.tax_summary_ids.unlink()

        # Eliminar descuentos/cargos globales
        if self.allowance_charge_ids:
            self.allowance_charge_ids.unlink()

        # Eliminar anticipos
        if self.prepaid_ids:
            self.prepaid_ids.unlink()

        # Resetear campos monetarios y de partners
        self.write({
            # Terceros
            'supplier_id': False,
            'customer_id': False,
            'delivery_partner_id': False,
            # Montos
            'amount_untaxed': 0.0,
            'amount_discount': 0.0,
            'amount_charges': 0.0,
            'amount_prepaid': 0.0,
            'amount_tax': 0.0,
            'amount_withholding': 0.0,
            'amount_total': 0.0,
            'payable_amount': 0.0,
            'amount_untaxed_local': 0.0,
            'amount_total_local': 0.0,
            # Validación
            'total_difference': 0.0,
            'has_validation_warning': False,
            'validation_message': False,
            'error_log': False,
            # Referencias
            'order_reference': False,
            'despatch_reference': False,
            'receipt_reference': False,
            'contract_reference': False,
            # Notas
            'notes': False,
        })

        _logger.info(f"Datos limpiados exitosamente para procesador {self.id}")

    def process_xml_content(self):
        """Alias para process_xml - procesa el XML y extrae toda la información"""
        return self.process_xml()

    def process_xml(self):
        """Procesa el XML y extrae toda la información"""
        self.ensure_one()

        if not self.xml_content and not self.cufe:
            raise UserError(_("Debe proporcionar un XML o un CUFE"))

        # Limpiar datos existentes para evitar duplicados
        self._clean_existing_data()

        try:
            # Si solo tenemos CUFE, intentar descargar
            if not self.xml_content and self.cufe:
                self.retrieve_xml_from_dian()
            
            # Parsear XML (decodificar si es Binary)
            if isinstance(self.xml_content, bytes):
                xml_string = base64.b64decode(self.xml_content).decode('utf-8')
            else:
                xml_string = base64.b64decode(self.xml_content).decode('utf-8') if self.xml_content else ''

            dict_data = xmltodict.parse(xml_string)
            
            # Detectar si es AttachedDocument
            if 'AttachedDocument' in dict_data:
                attached = dict_data['AttachedDocument']
                # Extraer el XML interno
                attachment = attached.get('cac:Attachment', {})
                external_ref = attachment.get('cac:ExternalReference', {})
                invoice_xml = external_ref.get('cbc:Description')
                if invoice_xml:
                    dict_data = xmltodict.parse(invoice_xml)
                    self.xml_invoice = invoice_xml
            
            # Procesar según tipo
            if 'Invoice' in dict_data:
                self._process_invoice(dict_data['Invoice'])
            elif 'CreditNote' in dict_data:
                self._process_credit_note(dict_data['CreditNote'])
            elif 'DebitNote' in dict_data:
                self._process_debit_note(dict_data['DebitNote'])
            
            # Validar totales
            self._validate_totals()
            
            # Actualizar tasa de cambio si no está definida
            self._update_exchange_rate()

            # Buscar y asociar impuestos automáticamente
            self._auto_match_taxes()

            self.state = 'validated' if not self.has_validation_warning else 'processed'

        except Exception as e:
            self.state = 'error'
            tb = traceback.format_exc()
            self.error_log = f"{str(e)}\n\nTraceback:\n{tb}"
            _logger.error(f"Error procesando XML: {str(e)}\n{tb}")
            raise UserError(f"Error procesando XML: {str(e)}\n\nDetalle:\n{tb}")
    
    def _update_exchange_rate(self):
        """Actualiza la tasa de cambio si no está definida"""
        if self.document_currency_id and self.document_currency_id != self.currency_id:
            if not self.exchange_rate:
                # Obtener tasa de cambio del día
                self.exchange_rate_date = self.issue_date or fields.Date.today()
                
                # Primero intentar obtener del sistema de Odoo
                rate = self.document_currency_id._get_conversion_rate(
                    self.document_currency_id,
                    self.currency_id,
                    self.env.company,
                    self.exchange_rate_date
                )
                
                if rate:
                    self.exchange_rate = rate
                else:
                    # Si no hay tasa, intentar obtener de servicio externo
                    self._fetch_exchange_rate_external()
    
    def _fetch_exchange_rate_external(self):
        """Obtiene tasa de cambio de servicio externo"""
        try:
            # Ejemplo con API del Banco de la República de Colombia
            if self.document_currency_id.name == 'USD' and self.currency_id.name == 'COP':
                date_str = self.exchange_rate_date.strftime('%Y-%m-%d')
                url = f"https://www.datos.gov.co/resource/mcec-87by.json?vigenciadesde={date_str}"
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    if data:
                        self.exchange_rate = float(data[0].get('valor', 0))
        except Exception as e:
            _logger.warning(f"No se pudo obtener tasa de cambio externa: {str(e)}")

    def _auto_match_taxes(self):
        """Busca y asocia automáticamente los impuestos de Odoo para todos los impuestos del documento"""
        self.ensure_one()

        if not self.tax_summary_ids:
            return

        _logger.info(f"Buscando impuestos automáticamente para documento {self.document_number}")

        matched_count = 0
        created_count = 0

        for tax_line in self.tax_summary_ids:
            if not tax_line.tax_id:
                try:
                    # Buscar impuesto existente
                    tax_line.find_odoo_tax()

                    if tax_line.tax_id:
                        matched_count += 1
                        _logger.info(f"Impuesto asociado: {tax_line.tax_code} -> {tax_line.tax_id.name}")
                    else:
                        created_count += 1
                        _logger.info(f"Impuesto creado: {tax_line.tax_code}")

                except Exception as e:
                    _logger.warning(f"Error al buscar/crear impuesto {tax_line.tax_code}: {str(e)}")
                    continue

        if matched_count > 0 or created_count > 0:
            message = []
            if matched_count > 0:
                message.append(f"{matched_count} impuesto(s) asociado(s) automáticamente")
            if created_count > 0:
                message.append(f"{created_count} impuesto(s) creado(s)")

            self.message_post(
                body=f"<p>Impuestos procesados: {', '.join(message)}</p>",
                message_type='notification'
            )

    def _process_invoice(self, invoice):
        """Procesa datos de factura"""
        # Información básica
        self.document_type = self._get_value(invoice.get('cbc:InvoiceTypeCode')) or '01'
        self.document_number = self._get_value(invoice.get('cbc:ID'))
        self.cufe = self._get_value(invoice.get('cbc:UUID'))
        self.issue_date = self._get_value(invoice.get('cbc:IssueDate'))

        # Moneda
        currency_code = self._get_value(invoice.get('cbc:DocumentCurrencyCode')) or 'COP'
        self.document_currency_id = self.env['res.currency'].search([('name', '=', currency_code)], limit=1).id
        
        # Periodo de facturación
        period = invoice.get('cac:InvoicePeriod', {})
        if period:
            self.invoice_period_start = period.get('cbc:StartDate')
            self.invoice_period_end = period.get('cbc:EndDate')
        
        # Referencias
        self._process_references(invoice)
        
        # Términos de pago
        self._process_payment_terms(invoice)
        
        # Notas
        self._process_notes(invoice)
        
        # Procesar terceros
        self._process_parties(invoice)
        
        # Procesar totales
        self._process_monetary_total(invoice.get('cac:LegalMonetaryTotal'))
        
        # Procesar descuentos/cargos globales
        self._process_allowance_charges(invoice.get('cac:AllowanceCharge', []))
        
        # Procesar anticipos
        self._process_prepaid_payments(invoice.get('cac:PrepaidPayment', []))
        
        # Procesar impuestos
        self._process_tax_totals(invoice.get('cac:TaxTotal', []))

        # Procesar retenciones (WithholdingTaxTotal)
        self._process_withholding_tax_totals(invoice.get('cac:WithholdingTaxTotal', []))

        # Procesar líneas
        self._process_lines(invoice.get('cac:InvoiceLine', []))
        
        # Predecir productos si está habilitado
        if self.auto_predict_products:
            self._predict_products_full([])
    
    def _process_credit_note(self, credit_note):
        """Procesa nota crédito"""
        self.document_type = '91'
        self.document_number = self._get_value(credit_note.get('cbc:ID'))
        self.cufe = self._get_value(credit_note.get('cbc:UUID'))
        self.issue_date = self._get_value(credit_note.get('cbc:IssueDate'))

        # Moneda
        currency_code = self._get_value(credit_note.get('cbc:DocumentCurrencyCode')) or 'COP'
        self.document_currency_id = self.env['res.currency'].search([('name', '=', currency_code)], limit=1).id

        # Referencia a factura
        billing_ref = credit_note.get('cac:BillingReference', {})
        if billing_ref:
            invoice_ref = billing_ref.get('cac:InvoiceDocumentReference', {})
            self.billing_reference_id = self._get_value(invoice_ref.get('cbc:ID'))
            self.billing_reference_cufe = self._get_value(invoice_ref.get('cbc:UUID'))
            self.billing_reference_date = self._get_value(invoice_ref.get('cbc:IssueDate'))

        # Motivo y código de discrepancia
        response = credit_note.get('cac:DiscrepancyResponse', {})
        if response:
            if isinstance(response, list):
                response = response[0]
            self.credit_note_reason = self._get_value(response.get('cbc:Description'))
            self.discrepancy_response_code = self._get_value(response.get('cbc:ResponseCode'))
        
        # Procesar resto igual que factura
        self._process_parties(credit_note)
        self._process_monetary_total(credit_note.get('cac:LegalMonetaryTotal'))
        self._process_tax_totals(credit_note.get('cac:TaxTotal', []))
        self._process_withholding_tax_totals(credit_note.get('cac:WithholdingTaxTotal', []))
        self._process_lines(credit_note.get('cac:CreditNoteLine', []), is_credit_note=True)
        
        if self.auto_predict_products:
            self._predict_products_full([])

    def _process_debit_note(self, debit_note):
        """Procesa nota débito"""
        self.document_type = '92'
        self.document_number = self._get_value(debit_note.get('cbc:ID'))
        self.cufe = self._get_value(debit_note.get('cbc:UUID'))
        self.issue_date = self._get_value(debit_note.get('cbc:IssueDate'))

        # Moneda
        currency_code = self._get_value(debit_note.get('cbc:DocumentCurrencyCode')) or 'COP'
        self.document_currency_id = self.env['res.currency'].search([('name', '=', currency_code)], limit=1).id

        # Referencia a factura
        billing_ref = debit_note.get('cac:BillingReference', {})
        if billing_ref:
            invoice_ref = billing_ref.get('cac:InvoiceDocumentReference', {})
            self.billing_reference_id = self._get_value(invoice_ref.get('cbc:ID'))
            self.billing_reference_cufe = self._get_value(invoice_ref.get('cbc:UUID'))
            self.billing_reference_date = self._get_value(invoice_ref.get('cbc:IssueDate'))

        # Motivo
        response = debit_note.get('cac:DiscrepancyResponse', {})
        if response:
            if isinstance(response, list):
                response = response[0]
            self.debit_note_reason = self._get_value(response.get('cbc:Description'))
            self.discrepancy_response_code = self._get_value(response.get('cbc:ResponseCode'))
        
        # Procesar resto
        self._process_parties(debit_note)
        self._process_monetary_total(debit_note.get('cac:LegalMonetaryTotal'))
        self._process_tax_totals(debit_note.get('cac:TaxTotal', []))
        self._process_withholding_tax_totals(debit_note.get('cac:WithholdingTaxTotal', []))
        self._process_lines(debit_note.get('cac:RequestedDebitNoteLine', []), is_debit_note=True)

        if self.auto_predict_products:
            self._predict_products_full([])

    def _process_lines(self, lines, is_credit_note=False, is_debit_note=False):
        """Procesa líneas del documento con múltiples estrategias para calcular precio unitario"""
        if not isinstance(lines, list):
            lines = [lines] if lines else []
        
        for line_data in lines:
            line_vals = self._prepare_line_vals(line_data, is_credit_note, is_debit_note)
            
            # Estrategias para calcular precio unitario correcto
            line_vals = self._calculate_correct_unit_price(line_vals, line_data)
            
            self.line_ids = [(0, 0, line_vals)]
    
    def _calculate_correct_unit_price(self, line_vals, line_data):
        """
        Calcula el precio unitario correcto usando múltiples estrategias
        """
        quantity = line_vals.get('quantity', 0)
        if quantity == 0:
            return line_vals
        
        # Estrategia 1: Precio desde el tag Price
        price_from_tag = line_vals.get('price_unit', 0)
        
        # Estrategia 2: Precio calculado desde el total de línea
        line_extension = line_vals.get('price_subtotal', 0)
        price_calculated = line_extension / quantity if quantity else 0
        
        # Estrategia 3: Precio con descuento incluido
        discount_amount = line_vals.get('discount_amount', 0)
        price_with_discount = (line_extension + discount_amount) / quantity if quantity else 0
        
        # Estrategia 4: Precio base desde BaseAmount
        price_base = 0
        if 'cac:Price' in line_data:
            price_data = line_data['cac:Price']
            if 'cbc:BaseQuantity' in price_data:
                base_qty = float(self._get_value(price_data.get('cbc:BaseQuantity', {})) or 1)
                if base_qty != 1:
                    price_base = price_from_tag * base_qty
        
        # Validar cuál precio es más coherente
        # Primero verificar si el precio del tag genera el total correcto
        calculated_total_from_tag = price_from_tag * quantity
        
        # Tolerancia para comparación (0.01)
        tolerance = 0.01
        
        # Seleccionar el mejor precio
        if abs(calculated_total_from_tag - line_extension) < tolerance:
            # El precio del tag es correcto
            final_price = price_from_tag
            strategy_used = "Tag Price"
        elif abs(price_calculated * quantity - line_extension) < tolerance:
            # El precio calculado es correcto
            final_price = price_calculated
            strategy_used = "Calculated from Total"
        elif price_base and abs(price_base * quantity - line_extension) < tolerance:
            # El precio base es correcto
            final_price = price_base
            strategy_used = "Base Price"
        else:
            # Usar precio calculado como última opción
            final_price = price_calculated
            strategy_used = "Default Calculated"
        
        line_vals['price_unit'] = final_price
        line_vals['price_calculation_method'] = strategy_used
        
        # Calcular porcentaje de descuento si aplica
        if discount_amount > 0 and price_with_discount > 0:
            discount_percentage = (discount_amount / (price_with_discount * quantity)) * 100
            line_vals['discount_percentage'] = discount_percentage
        
        return line_vals
    
    def _prepare_line_vals(self, line_data, is_credit_note=False, is_debit_note=False):
        """Prepara valores de línea con información completa"""
        item = line_data.get('cac:Item', {})
        
        # Determinar cantidad y monto según tipo de documento
        if is_credit_note:
            quantity_data = line_data.get('cbc:CreditedQuantity', {})
            line_amount = line_data.get('cbc:LineExtensionAmount', {})
        elif is_debit_note:
            quantity_data = line_data.get('cbc:DebitedQuantity', {})
            line_amount = line_data.get('cbc:LineExtensionAmount', {})
        else:
            quantity_data = line_data.get('cbc:InvoicedQuantity', {})
            line_amount = line_data.get('cbc:LineExtensionAmount', {})
        
        quantity = float(self._get_value(quantity_data) or 0)
        
        # Unidad de medida
        uom_code = quantity_data.get('@unitCode') if isinstance(quantity_data, dict) else None
        
        # Precio
        price_data = line_data.get('cac:Price', {})
        price = float(self._get_value(price_data.get('cbc:PriceAmount', {})) or 0)
        
        # Información del producto
        seller_identification = item.get('cac:SellersItemIdentification', {})
        standard_identification = item.get('cac:StandardItemIdentification', {})
        
        # Extraer código estándar y determinar su tipo
        standard_code = None
        standard_code_type = 'unknown'
        if standard_identification:
            standard_id_data = standard_identification.get('cbc:ID', {})
            standard_code = self._get_value(standard_id_data)

            # Determinar tipo de código basado en @schemeID
            if isinstance(standard_id_data, dict):
                scheme_id = standard_id_data.get('@schemeID', '')
                scheme_name = standard_id_data.get('@schemeName', '')

                # 010 = GTIN/EAN (código de barras real)
                # 999 = Estándar de adopción del contribuyente (código personalizado)
                if scheme_id == '010' or 'GTIN' in scheme_name.upper():
                    standard_code_type = 'gtin'
                elif scheme_id == '999' or 'adopción' in scheme_name.lower():
                    standard_code_type = 'custom'

        vals = {
            'sequence': int(self._get_value(line_data.get('cbc:ID', 1)) or 1),
            'product_code': seller_identification.get('cbc:ID'),
            'product_ean': standard_code,
            'product_ean_type': standard_code_type,
            'product_name': item.get('cbc:Description'),
            'quantity': quantity,
            'uom_code': uom_code,
            'price_unit': price,
            'price_subtotal': float(self._get_value(line_amount) or 0),
        }
        
        # Información adicional del producto
        additional_info = item.get('cac:AdditionalItemProperty', [])
        if not isinstance(additional_info, list):
            additional_info = [additional_info] if additional_info else []
        
        for info in additional_info:
            name = info.get('cbc:Name')
            value = info.get('cbc:Value')
            if name == 'MARCA':
                vals['product_brand'] = value
            elif name == 'MODELO':
                vals['product_model'] = value
        
        # Tercero en línea (para mandatos)
        if 'cac:SubInvoiceLine' in line_data:
            sub_line = line_data['cac:SubInvoiceLine']
            if 'cac:Party' in sub_line:
                vals['mandatary_partner_id'] = self._get_or_create_partner(
                    {'cac:Party': sub_line['cac:Party']}
                ).id
        
        # Descuentos/cargos en línea
        allowances = line_data.get('cac:AllowanceCharge', [])
        if not isinstance(allowances, list):
            allowances = [allowances] if allowances else []
        
        total_discount = 0
        total_charges = 0
        for allowance in allowances:
            is_charge = allowance.get('cbc:ChargeIndicator') == 'true'
            amount = float(self._get_value(allowance.get('cbc:Amount', {})) or 0)
            
            if is_charge:
                total_charges += amount
            else:
                total_discount += amount
        
        vals['discount_amount'] = total_discount
        vals['charge_amount'] = total_charges
        
        # Impuestos en línea
        tax_total = line_data.get('cac:TaxTotal', {})
        if tax_total:
            vals['tax_amount'] = float(self._get_value(tax_total.get('cbc:TaxAmount', {})) or 0)

            # Detalle de impuestos
            subtotals = tax_total.get('cac:TaxSubtotal', [])
            if not isinstance(subtotals, list):
                subtotals = [subtotals] if subtotals else []

            tax_details = []
            odoo_tax_ids = []
            for subtotal in subtotals:
                category = subtotal.get('cac:TaxCategory', {})
                scheme = category.get('cac:TaxScheme', {})

                tax_code = self._get_value(scheme.get('cbc:ID', {})) or 'ZZ'
                tax_name = self._get_value(scheme.get('cbc:Name', {}))
                tax_percentage = float(self._get_value(category.get('cbc:Percent', {})) or 0)

                tax_details.append({
                    'code': tax_code,
                    'name': tax_name,
                    'percentage': tax_percentage
                })

                # Buscar impuesto Odoo correspondiente
                odoo_tax = self._find_or_suggest_odoo_tax(
                    tax_code=tax_code,
                    tax_name=tax_name,
                    tax_percentage=tax_percentage,
                    is_purchase=True
                )

                if odoo_tax:
                    odoo_tax_ids.append(odoo_tax.id)

            vals['tax_details'] = str(tax_details)
            vals['tax_ids'] = [(6, 0, odoo_tax_ids)] if odoo_tax_ids else False
        
        # Información de lote y vencimiento (cac:ItemInstance)
        item_instance = item.get('cac:ItemInstance', {})
        if item_instance:
            lot_identification = item_instance.get('cac:LotIdentification', {})
            if lot_identification:
                lot_number = lot_identification.get('cbc:LotNumberID')
                expiry_date = lot_identification.get('cbc:ExpiryDate')

                if lot_number:
                    vals['lot_number'] = self._get_value(lot_number)
                    _logger.info(f"Lote detectado: {vals['lot_number']}")

                if expiry_date:
                    vals['expiry_date'] = self._get_value(expiry_date)
                    _logger.info(f"Fecha vencimiento: {vals['expiry_date']}")

        # Referencias de orden de compra en línea
        order_line_ref = line_data.get('cac:OrderLineReference', {})
        if order_line_ref:
            # Referencia a línea de OC
            line_id = order_line_ref.get('cbc:LineID')
            if line_id:
                vals['order_line_reference'] = self._get_value(line_id)

            # Referencia a orden completa en línea (si difiere de la del documento)
            order_ref = order_line_ref.get('cac:OrderReference', {})
            if order_ref:
                order_id = order_ref.get('cbc:ID')
                if order_id:
                    vals['order_reference'] = self._get_value(order_id)

        # Tercero/Mandato en línea (cac:PartyIdentification)
        party_identification = line_data.get('cac:PartyIdentification', {})
        if party_identification:
            party_id = party_identification.get('cbc:ID')
            if party_id:
                # Buscar o crear partner basado en el ID
                partner_vat = self._get_value(party_id)
                if partner_vat:
                    partner = self.env['res.partner'].search([('vat', '=', partner_vat)], limit=1)
                    if partner:
                        vals['mandatary_partner_id'] = partner.id
                        _logger.info(f"Tercero/Mandato en línea: {partner.name}")

        # Información de entrega
        delivery = line_data.get('cac:Delivery', {})
        if delivery:
            vals['delivery_date'] = delivery.get('cbc:ActualDeliveryDate')

        return vals

    def _validate_totals(self):
        """Valida que los totales coincidan con las fórmulas UBL 2.1"""
        currency = self.document_currency_id or self.env.company.currency_id
        precision = currency.decimal_places if currency else 2

        validations = []
        has_errors = False

        # 1. Validación: Σ LineExtensionAmount(líneas) = LineExtensionAmount(documento)
        lines_subtotal = sum(self.line_ids.mapped('price_subtotal'))
        if float_compare(abs(lines_subtotal - self.amount_untaxed), 1.0, precision_digits=precision) > 0:
            has_errors = True
            validations.append(_(
                "✗ Suma subtotales líneas (%.2f) ≠ Base Imponible documento (%.2f)"
            ) % (lines_subtotal, self.amount_untaxed))
        else:
            validations.append(_(
                "✓ Suma subtotales líneas = Base Imponible documento (%.2f)"
            ) % lines_subtotal)

        # 2. Validación: Σ TaxAmount(líneas) = TotalImpuestos(documento)
        lines_tax = sum(self.line_ids.mapped('tax_amount'))
        tax_summary_total = sum(self.tax_summary_ids.filtered(lambda x: not x.is_withholding).mapped('tax_amount'))

        if float_compare(abs(lines_tax - tax_summary_total), 1.0, precision_digits=precision) > 0:
            has_errors = True
            validations.append(_(
                "✗ Suma impuestos líneas (%.2f) ≠ Total impuestos documento (%.2f)"
            ) % (lines_tax, tax_summary_total))
        else:
            validations.append(_(
                "✓ Suma impuestos líneas = Total impuestos documento (%.2f)"
            ) % lines_tax)

        # 3. Validación: LineExtensionAmount + TotalImpuestos = TaxInclusiveAmount (amount_total)
        calculated_with_tax = self.amount_untaxed + self.amount_tax
        if float_compare(abs(calculated_with_tax - self.amount_total), 1.0, precision_digits=precision) > 0:
            has_errors = True
            validations.append(_(
                "✗ Base (%.2f) + Impuestos (%.2f) = %.2f ≠ Total documento (%.2f)"
            ) % (self.amount_untaxed, self.amount_tax, calculated_with_tax, self.amount_total))
        else:
            validations.append(_(
                "✓ Base + Impuestos = Total documento (%.2f)"
            ) % self.amount_total)

        # 4. Validacion UBL 2.1 completa:
        # PayableAmount = TaxInclusiveAmount - AllowanceTotalAmount + ChargeTotalAmount - PrepaidAmount + PayableRoundingAmount
        calculated_payable = (
            self.amount_total
            - self.amount_discount
            + self.amount_charges
            - self.amount_prepaid
            + self.amount_rounding
        )
        if float_compare(abs(calculated_payable - self.payable_amount), 1.0, precision_digits=precision) > 0:
            has_errors = True
            validations.append(_(
                "X Total (%.2f) - Desc (%.2f) + Cargos (%.2f) - Anticipos (%.2f) + Redondeo (%.2f) = %.2f != A Pagar (%.2f)"
            ) % (self.amount_total, self.amount_discount, self.amount_charges,
                 self.amount_prepaid, self.amount_rounding, calculated_payable, self.payable_amount))
        else:
            validations.append(_(
                "V Total - Descuentos + Cargos - Anticipos + Redondeo = A Pagar (%.2f)"
            ) % self.payable_amount)

        # Generar mensaje
        if has_errors:
            message = _(
                "<b>VALIDACION DE TOTALES</b><br/><br/>"
                "Se detectaron diferencias en los calculos:<br/>"
                "--------------------------------<br/>"
                "%s<br/><br/>"
                "<b>Desglose:</b><br/>"
                "- Subtotal lineas: %.2f<br/>"
                "- Impuestos lineas: %.2f<br/>"
                "- Total impuestos: %.2f<br/>"
                "- Retenciones: %.2f<br/>"
                "- Descuentos globales: %.2f<br/>"
                "- Cargos globales: %.2f<br/>"
                "- Anticipos: %.2f<br/>"
                "- Redondeo: %.2f<br/>"
            ) % (
                '<br/>'.join(validations),
                lines_subtotal,
                lines_tax,
                self.amount_tax,
                self.amount_withholding,
                self.amount_discount,
                self.amount_charges,
                self.amount_prepaid,
                self.amount_rounding
            )
            self.message_post(body=message, message_type='notification')
        else:
            _logger.info(f"Validacion de totales OK para documento {self.document_number}")
    
    def _get_value(self, data):
        """Obtiene el valor de un campo XML considerando la estructura del diccionario"""
        if isinstance(data, dict):
            # Si el diccionario está vacío, retornar cadena vacía
            if not data:
                return ''
            # Si tiene el atributo #text, es el valor
            if '#text' in data:
                return data['#text']
            # Si tiene @value, también puede ser el valor
            elif '@value' in data:
                return data['@value']
            # Si solo tiene atributos (empiezan con @), retornar cadena vacía
            elif all(k.startswith('@') for k in data.keys()):
                return ''
            # Si no tiene atributos especiales y tiene contenido, convertir a string
            elif not any(k.startswith('@') for k in data.keys()):
                return str(data)
        return str(data) if data else ''
    
    def _attach_files_to_invoice(self, invoice):
        """Adjunta el PDF y XML a la factura creada"""
        self.ensure_one()

        Attachment = self.env['ir.attachment']

        # Adjuntar XML
        if self.xml_content:
            xml_attachment = Attachment.create({
                'name': self.xml_filename or f'DIAN_{self.document_number}.xml',
                'type': 'binary',
                'datas': self.xml_content,
                'res_model': 'account.move',
                'res_id': invoice.id,
                'mimetype': 'application/xml',
                'description': f'XML DIAN - {self.document_type} {self.document_number}',
            })
            _logger.info(f"XML adjuntado a factura {invoice.name}: {xml_attachment.name}")

        # Adjuntar PDF
        if self.pdf_file:
            pdf_attachment = Attachment.create({
                'name': self.pdf_filename or f'DIAN_{self.document_number}.pdf',
                'type': 'binary',
                'datas': self.pdf_file,
                'res_model': 'account.move',
                'res_id': invoice.id,
                'mimetype': 'application/pdf',
                'description': f'PDF DIAN - {self.document_type} {self.document_number}',
            })
            _logger.info(f"PDF adjuntado a factura {invoice.name}: {pdf_attachment.name}")

        # Adjuntar ZIP si existe
        if self.zip_file:
            zip_attachment = Attachment.create({
                'name': self.zip_filename or f'DIAN_{self.document_number}.zip',
                'type': 'binary',
                'datas': self.zip_file,
                'res_model': 'account.move',
                'res_id': invoice.id,
                'mimetype': 'application/zip',
                'description': f'ZIP DIAN - {self.document_type} {self.document_number}',
            })
            _logger.info(f"ZIP adjuntado a factura {invoice.name}: {zip_attachment.name}")

    def action_unify_lines_to_product(self):
        """Wizard para unificar todas las líneas en una sola con un producto específico"""
        self.ensure_one()

        if not self.line_ids:
            raise UserError(_("No hay líneas para unificar"))

        return {
            'name': _('Unificar Líneas en un Producto'),
            'type': 'ir.actions.act_window',
            'res_model': 'dian.unify.lines.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_processor_id': self.id,
                'default_total_amount': self.amount_total,
                'default_line_count': len(self.line_ids),
            }
        }

    def create_invoice(self):
        """Crea la factura en Odoo con validación completa"""
        self.ensure_one()
        
        if self.state not in ['processed', 'validated']:
            raise UserError(_("Primero debe procesar el XML"))
        
        if self.invoice_id:
            raise UserError(_("Ya existe una factura creada"))
        
        # Mostrar advertencia si hay problemas de validación
        if self.has_validation_warning:
            message = _(
                "ADVERTENCIA: Existen diferencias en los totales.\n"
                "%s\n\n"
                "¿Desea continuar con la creación de la factura?"
            ) % self.validation_message
            
            # Aquí podrías implementar un wizard de confirmación
            # Por ahora, solo registramos la advertencia
            self.message_post(body=message, message_type='notification')
        
        # Verificar duplicados
        domain = [
            ('move_type', '=', self._get_invoice_type()),
            ('ref', '=', self.document_number),
            ('partner_id', '=', self.supplier_id.id if self._is_purchase() else self.customer_id.id),
            ('state', '!=', 'cancel')
        ]
        
        existing = self.env['account.move'].search(domain, limit=1)
        if existing:
            raise UserError(_(
                "Ya existe una factura con esta referencia: %s") % existing.name)
        
        vals = self._prepare_invoice_vals()
        invoice = self.env['account.move'].create(vals)

        self.invoice_id = invoice
        self.state = 'invoiced'

        # Adjuntar archivos PDF y XML a la factura
        self._attach_files_to_invoice(invoice)

        # Mensaje de éxito
        self.message_post(
            body=_("Factura creada exitosamente: %s") % invoice.name,
            message_type='notification'
        )

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': invoice.id,
            'view_mode': 'form',
        }

    # ========== MÉTODOS DE RECUPERACIÓN DIAN ==========

    def retrieve_xml_from_dian(self, cufe=None):
        """
        Recupera el XML desde DIAN usando el CUFE/CUDE
        Utiliza los métodos nativos del módulo l10n_co_e_invoice

        Args:
            cufe: CUFE a consultar (opcional, usa el del registro si no se proporciona)

        Returns:
            str: Contenido del XML o False si hay error
        """
        self.ensure_one()

        track_id = cufe or self.cufe
        if not track_id:
            raise UserError(_("No se ha especificado un CUFE/CUDE para consultar"))

        try:
            # Usar la función extendida que llama al método nativo
            xml_content = xml_utils.retrieve_xml_from_dian_extended(
                track_id=track_id,
                company=self.company_id or self.env.company
            )

            if xml_content:
                # Guardar el XML recuperado en el campo antes de procesarlo
                self.xml_content = base64.b64encode(xml_content.encode('utf-8'))
                self.xml_filename = f"DIAN_{track_id}.xml"
                self.xml_retrieved_from_dian = True
                self.xml_retrieval_date = fields.Datetime.now()

                # Guardar el estado para indicar que tenemos XML pero no está procesado
                if self.state == 'draft':
                    self.state = 'xml_loaded'

                # Extraer datos básicos del XML sin procesarlo completamente
                extracted_data = xml_utils.extract_data_from_invoice_xml(xml_content)
                if extracted_data:
                    # Actualizar solo campos básicos con datos extraídos
                    update_vals = {}
                    if 'document_number' in extracted_data and not self.document_number:
                        update_vals['document_number'] = extracted_data['document_number']
                    if 'issue_date' in extracted_data and not self.issue_date:
                        update_vals['issue_date'] = extracted_data['issue_date']
                    if 'amount_total' in extracted_data and not self.amount_total:
                        update_vals['amount_total'] = extracted_data['amount_total']
                    if 'supplier_vat' in extracted_data:
                        update_vals['supplier_vat'] = extracted_data.get('supplier_vat')
                    if 'supplier_name' in extracted_data:
                        update_vals['supplier_name'] = extracted_data.get('supplier_name')

                    if update_vals:
                        self.write(update_vals)

                # NO procesar automáticamente - solo guardar para procesar después
                # El procesamiento se hace manualmente con el botón "Procesar XML"

                self.message_post(
                    body=_("XML recuperado exitosamente desde DIAN"),
                    message_type='notification'
                )

                return xml_content
            else:
                self.message_post(
                    body=_("No se pudo recuperar el XML desde DIAN para el CUFE: %s") % track_id,
                    message_type='notification'
                )
                return False

        except Exception as e:
            _logger.error(f"Error recuperando XML de DIAN: {str(e)}")
            self.message_post(
                body=_("Error al recuperar XML desde DIAN: %s") % str(e),
                message_type='notification'
            )
            return False

    def action_retrieve_xml_from_dian(self):
        """Acción de botón para recuperar XML desde DIAN y guardarlo antes de procesar"""
        self.ensure_one()

        if not self.cufe:
            raise UserError(_("Debe ingresar un CUFE/CUDE para poder consultar en DIAN"))

        # Recuperar y guardar el XML
        xml_content = self.retrieve_xml_from_dian()

        if xml_content:
            # El XML ya se guardó en el método retrieve_xml_from_dian
            # Ahora procesarlo automáticamente
            try:
                self.process_xml_content()
                message = _('XML recuperado desde DIAN y procesado exitosamente')
                msg_type = 'success'
            except Exception as e:
                _logger.warning(f"XML recuperado pero error al procesar: {str(e)}")
                message = _('XML recuperado desde DIAN. Puede procesarlo manualmente.')
                msg_type = 'warning'

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Éxito'),
                    'message': message,
                    'type': msg_type,
                    'sticky': False,
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('No se pudo recuperar el XML desde DIAN'),
                    'type': 'danger',
                    'sticky': False,
                }
            }

    def batch_retrieve_from_dian(self, cufe_list):
        """
        Recupera múltiples documentos desde DIAN

        Args:
            cufe_list: Lista de CUFEs a consultar

        Returns:
            dict: Resumen de documentos recuperados
        """
        results = {
            'success': [],
            'failed': [],
            'created': []
        }

        for cufe in cufe_list:
            try:
                # Buscar si ya existe
                existing = self.search([('cufe', '=', cufe)], limit=1)

                if existing:
                    # Actualizar el existente
                    xml_content = existing.retrieve_xml_from_dian()
                    if xml_content:
                        results['success'].append(cufe)
                    else:
                        results['failed'].append(cufe)
                else:
                    # Crear nuevo registro
                    new_doc = self.create({'cufe': cufe})
                    xml_content = new_doc.retrieve_xml_from_dian()

                    if xml_content:
                        results['created'].append(cufe)
                    else:
                        results['failed'].append(cufe)
                        new_doc.unlink()

            except Exception as e:
                _logger.error(f"Error procesando CUFE {cufe}: {str(e)}")
                results['failed'].append(cufe)

        return results

    def _process_references(self, invoice):
        """Procesa referencias de órdenes y otros documentos"""
        # Orden de compra
        order_refs = invoice.get('cac:OrderReference', [])
        if not isinstance(order_refs, list):
            order_refs = [order_refs] if order_refs else []

        for order_ref in order_refs:
            if order_ref:
                self.order_reference = order_ref.get('cbc:ID')
                break

        # Otras referencias
        additional_refs = invoice.get('cac:AdditionalDocumentReference', [])
        if not isinstance(additional_refs, list):
            additional_refs = [additional_refs] if additional_refs else []

        for ref in additional_refs:
            doc_type = ref.get('cbc:DocumentTypeCode')
            if doc_type == '6':  # Despatch
                self.despatch_reference = ref.get('cbc:ID')
            elif doc_type == '3':  # Receipt
                self.receipt_reference = ref.get('cbc:ID')
            elif doc_type == '2':  # Contract
                self.contract_reference = ref.get('cbc:ID')

    def _process_payment_terms(self, invoice):
        """Procesa términos de pago y fecha de vencimiento"""
        _logger.info("=== PROCESANDO TÉRMINOS DE PAGO ===")

        # Medios de pago
        payment_means = invoice.get('cac:PaymentMeans', {})
        if payment_means:
            payment_code = payment_means.get('cbc:PaymentMeansCode')
            # Validar que el código esté en la lista de selección
            valid_codes = [code[0] for code in self._fields['payment_means_code'].selection]
            if payment_code and payment_code in valid_codes:
                self.payment_means_code = payment_code
                _logger.info(f"Medio de pago: {payment_code}")
            elif payment_code:
                # Si no está en la lista, usar 'ZZZ' (Otro) y guardar el código real en payment_method_code
                self.payment_means_code = 'ZZZ'
                self.payment_method_code = f"Code: {payment_code}"
                _logger.warning(f"Código de medio de pago desconocido: {payment_code}, usando 'ZZZ' (Otro)")

            # Si viene PaymentID, guardar como instrucción/ID de pago del proveedor
            payment_id = payment_means.get('cbc:PaymentID')
            if payment_id:
                payment_id_value = self._get_value(payment_id)
                # No asignar a payment_method_code (Selection 1/2)
                if self.payment_instruction_id:
                    self.payment_instruction_id = f"{self.payment_instruction_id} - ID: {payment_id_value}"
                else:
                    self.payment_instruction_id = payment_id_value

            # Instrucción de pago (para referencias de pago del proveedor)
            instruction_id = payment_means.get('cbc:InstructionID')
            if instruction_id:
                self.payment_instruction_id = self._get_value(instruction_id)
                _logger.info(f"Instrucción de pago: {self.payment_instruction_id}")

        # Fecha de vencimiento - buscar en múltiples lugares
        due_date = None

        # 1. Buscar en PaymentTerms
        payment_terms = invoice.get('cac:PaymentTerms', {})
        if payment_terms:
            if isinstance(payment_terms, list):
                payment_terms = payment_terms[0]  # Tomar el primero si es lista

            payment_due_date = payment_terms.get('cbc:PaymentDueDate')
            if payment_due_date:
                due_date = self._get_value(payment_due_date)
                _logger.info(f"✓ Fecha vencimiento encontrada en PaymentTerms: {due_date}")

        # 2. Si no se encontró, buscar en PaymentMeans
        if not due_date and payment_means:
            payment_due_date = payment_means.get('cbc:PaymentDueDate')
            if payment_due_date:
                due_date = self._get_value(payment_due_date)
                _logger.info(f"✓ Fecha vencimiento encontrada en PaymentMeans: {due_date}")

        # 3. Si no se encontró, buscar en DueDate directamente
        if not due_date:
            due_date_direct = invoice.get('cbc:DueDate')
            if due_date_direct:
                due_date = self._get_value(due_date_direct)
                _logger.info(f"✓ Fecha vencimiento encontrada en DueDate: {due_date}")

        # 4. Si aún no hay, buscar fecha de pago (PayDate)
        if not due_date:
            pay_date = invoice.get('cbc:PayDate')
            if pay_date:
                due_date = self._get_value(pay_date)
                _logger.info(f"✓ Fecha vencimiento encontrada en PayDate: {due_date}")

        if due_date:
            self.due_date = due_date
            _logger.info(f">>> Fecha de vencimiento final: {self.due_date}")
        else:
            _logger.warning("⚠ No se encontró fecha de vencimiento en el XML")

    def _process_notes(self, invoice):
        """Procesa notas del documento"""
        notes = invoice.get('cbc:Note', [])
        if not isinstance(notes, list):
            notes = [notes] if notes else []

        note_text = []
        for note in notes:
            if note:
                note_value = self._get_value(note)
                if note_value:
                    note_text.append(note_value)

        if note_text:
            self.notes = '\n'.join(note_text)

    def _process_monetary_total(self, monetary_total):
        """Procesa los totales monetarios del documento"""
        if not monetary_total:
            return

        self.amount_untaxed = float(self._get_value(monetary_total.get('cbc:LineExtensionAmount', {})) or 0)

        # TaxInclusiveAmount = Total con impuestos (antes de descuentos globales y anticipos)
        self.amount_total = float(self._get_value(monetary_total.get('cbc:TaxInclusiveAmount', {})) or 0)

        # PayableAmount = Monto final a pagar
        self.payable_amount = float(self._get_value(monetary_total.get('cbc:PayableAmount', {})) or 0)

        # Anticipos
        self.amount_prepaid = float(self._get_value(monetary_total.get('cbc:PrepaidAmount', {})) or 0)

        # Descuentos globales (AllowanceTotalAmount)
        self.amount_discount = float(self._get_value(monetary_total.get('cbc:AllowanceTotalAmount', {})) or 0)

        # Cargos globales (ChargeTotalAmount)
        self.amount_charges = float(self._get_value(monetary_total.get('cbc:ChargeTotalAmount', {})) or 0)

        # Redondeo (PayableRoundingAmount)
        self.amount_rounding = float(self._get_value(monetary_total.get('cbc:PayableRoundingAmount', {})) or 0)

    def _process_allowance_charges(self, allowances):
        """Procesa descuentos y cargos globales"""
        if not isinstance(allowances, list):
            allowances = [allowances] if allowances else []

        for allowance in allowances:
            is_charge = allowance.get('cbc:ChargeIndicator') == 'true'

            vals = {
                'type': 'charge' if is_charge else 'discount',
                'reason': allowance.get('cbc:AllowanceChargeReason'),
                'reason_code': allowance.get('cbc:AllowanceChargeReasonCode'),
                'amount': float(self._get_value(allowance.get('cbc:Amount', {})) or 0),
                'base_amount': float(self._get_value(allowance.get('cbc:BaseAmount', {})) or 0),
                'percentage': float(allowance.get('cbc:MultiplierFactorNumeric', 0)),
            }

            self.allowance_charge_ids = [(0, 0, vals)]

    def _process_prepaid_payments(self, prepaids):
        """Procesa anticipos"""
        if not isinstance(prepaids, list):
            prepaids = [prepaids] if prepaids else []

        for prepaid in prepaids:
            vals = {
                'payment_id': prepaid.get('cbc:ID'),
                'paid_amount': float(self._get_value(prepaid.get('cbc:PaidAmount', {})) or 0),
                'paid_date': prepaid.get('cbc:PaidDate'),
                'paid_time': prepaid.get('cbc:PaidTime'),
                'instruction_id': prepaid.get('cbc:InstructionID'),
            }

            self.prepaid_ids = [(0, 0, vals)]

    def _process_tax_totals(self, tax_totals):
        """Procesa TaxTotal del documento"""
        if not tax_totals:
            return

        if not isinstance(tax_totals, list):
            tax_totals = [tax_totals]

        tax_lines = []
        total_tax = 0.0

        for tax_total in tax_totals:
            subtotals = tax_total.get('cac:TaxSubtotal', [])
            if not isinstance(subtotals, list):
                subtotals = [subtotals] if subtotals else []

            for subtotal in subtotals:
                category = subtotal.get('cac:TaxCategory', {})
                scheme = category.get('cac:TaxScheme', {})

                tax_code = self._get_value(scheme.get('cbc:ID', {})) or 'ZZ'
                tax_name = self._get_value(scheme.get('cbc:Name', {}))
                tax_percentage = float(self._get_value(category.get('cbc:Percent', {})) or 0)
                taxable_amount = float(self._get_value(subtotal.get('cbc:TaxableAmount', {})) or 0)
                tax_amount = float(self._get_value(subtotal.get('cbc:TaxAmount', {})) or 0)

                vals = {
                    'tax_code': tax_code,
                    'tax_name': tax_name,
                    'tax_percentage': tax_percentage,
                    'tax_base': taxable_amount,
                    'tax_amount': tax_amount,
                }

                tax_lines.append(vals)
                total_tax += tax_amount

        if tax_lines:
            self.tax_summary_ids = [(0, 0, vals) for vals in tax_lines]
        self.amount_tax = total_tax

    def _process_withholding_tax_totals(self, withholding_totals):
        """Procesa WithholdingTaxTotal del documento"""
        if not withholding_totals:
            return

        if not isinstance(withholding_totals, list):
            withholding_totals = [withholding_totals]

        withholding_lines = []
        total_withholding = self.amount_withholding or 0.0

        for withholding in withholding_totals:
            subtotals = withholding.get('cac:TaxSubtotal', [])
            if not isinstance(subtotals, list):
                subtotals = [subtotals] if subtotals else []

            for subtotal in subtotals:
                category = subtotal.get('cac:TaxCategory', {})
                scheme = category.get('cac:TaxScheme', {})

                tax_code = self._get_value(scheme.get('cbc:ID', {})) or 'ZZ'
                tax_name = self._get_value(scheme.get('cbc:Name', {}))
                tax_percentage = float(self._get_value(category.get('cbc:Percent', {})) or 0)
                taxable_amount = float(self._get_value(subtotal.get('cbc:TaxableAmount', {})) or 0)
                tax_amount = float(self._get_value(subtotal.get('cbc:TaxAmount', {})) or 0)

                vals = {
                    'tax_code': tax_code,
                    'tax_name': tax_name,
                    'tax_percentage': tax_percentage,
                    'tax_base': taxable_amount,
                    'tax_amount': tax_amount,
                }

                withholding_lines.append(vals)
                total_withholding += tax_amount

        if withholding_lines:
            keep_existing = [(4, tax.id) for tax in self.tax_summary_ids]
            add_withholding = [(0, 0, vals) for vals in withholding_lines]
            self.tax_summary_ids = add_withholding + keep_existing
        self.amount_withholding = total_withholding

    def _prepare_invoice_vals(self):
        """Prepara valores para crear la factura en Odoo"""
        self.ensure_one()

        # Determinar tipo de factura
        move_type = self._get_invoice_type()

        # Partner
        partner = self.supplier_id if self._is_purchase() else self.customer_id
        if not partner:
            raise UserError(_("Debe especificar un proveedor o cliente"))

        # Preparar líneas
        invoice_lines = []
        total_line_subtotal = sum(self.line_ids.mapped('price_subtotal'))
        use_scale = bool(
            self.amount_untaxed
            and total_line_subtotal
            and abs(total_line_subtotal - self.amount_untaxed) > 0.01
        )
        scale = (self.amount_untaxed / total_line_subtotal) if use_scale else 1.0

        default_tax_ids = self.tax_summary_ids.filtered(
            lambda t: not t.is_withholding and t.tax_id
        ).mapped('tax_id').ids

        for line in self.line_ids:
            if not line.product_id:
                raise UserError(_("Todas las líneas deben tener un producto asociado. Línea: %s") % line.product_name)

            # Construir descripción de línea
            line_description = line.product_name or line.product_id.name

            # Si es una línea unificada, agregar información de las líneas originales
            if line.is_unified and line.notes and 'Líneas unificadas:' in line.notes:
                try:
                    import json
                    # Extract JSON from notes
                    json_start = line.notes.find('[')
                    if json_start >= 0:
                        json_data = line.notes[json_start:]
                        original_lines = json.loads(json_data)
                        unified_info = f"\n\nLíneas unificadas ({len(original_lines)}):"
                        for orig_line in original_lines:
                            unified_info += f"\n  - {orig_line['product_name']}: {orig_line['quantity']} x {orig_line['price_unit']:,.2f}"
                        line_description += unified_info
                except:
                    pass  # If parsing fails, just use regular description

            # Recalcular precio unitario si el subtotal de líneas no cuadra con el total base
            base_subtotal = line.price_subtotal * scale if line.price_subtotal else 0.0
            unit_price = (base_subtotal / line.quantity) if line.quantity else line.price_unit

            line_vals = {
                'product_id': line.product_id.id,
                'name': line_description,
                'quantity': line.quantity,
                'product_uom_id': line.uom_id.id if line.uom_id else line.product_id.uom_id.id,
                'price_unit': unit_price,
                'discount': line.discount_percentage,
            }

            # Impuestos: usar impuestos detectados en línea; si no hay, usar resumen (sin retenciones)
            line_tax_ids = line.tax_ids.ids if line.tax_ids else default_tax_ids
            line_vals['tax_ids'] = [(6, 0, line_tax_ids)] if line_tax_ids is not None else [(6, 0, [])]

            invoice_lines.append((0, 0, line_vals))

        # Preparar referencia con todos los detalles
        ref_parts = [self.document_number]

        if self.order_reference:
            ref_parts.append(f"OC: {self.order_reference}")

        if self.despatch_reference:
            ref_parts.append(f"Despacho: {self.despatch_reference}")

        if self.receipt_reference:
            ref_parts.append(f"Recibo: {self.receipt_reference}")

        if self.contract_reference:
            ref_parts.append(f"Contrato: {self.contract_reference}")

        reference = " | ".join(ref_parts)

        # Preparar narración con notas, CUFE y líneas pendientes de OC
        narration_parts = []
        if self.notes:
            narration_parts.append(self.notes)

        if self.cufe:
            narration_parts.append(f"\nCUFE: {self.cufe}")

        if self.payment_means_code:
            payment_means_name = dict(self._fields['payment_means_code'].selection).get(self.payment_means_code, self.payment_means_code)
            narration_parts.append(f"Medio de pago: {payment_means_name}")

        # Agregar información de líneas pendientes de Órdenes de Compra
        if hasattr(self, 'suggested_po_ids') and self.suggested_po_ids:
            pending_lines = []
            for po in self.suggested_po_ids:
                for po_line in po.order_line:
                    # Verificar si hay cantidad pendiente de facturar o recibir
                    qty_to_invoice = po_line.product_qty - po_line.qty_invoiced
                    qty_to_receive = po_line.product_qty - po_line.qty_received

                    if qty_to_invoice > 0 or qty_to_receive > 0:
                        pending_info = f"{po.partner_id.name} | {po.name} | {po_line.product_id.display_name}"
                        if qty_to_invoice > 0:
                            pending_info += f" | Pendiente facturar: {qty_to_invoice}"
                        if qty_to_receive > 0:
                            pending_info += f" | Pendiente recibir: {qty_to_receive}"
                        pending_lines.append(pending_info)

            if pending_lines:
                narration_parts.append("\n\n=== LÍNEAS PENDIENTES EN ÓRDENES DE COMPRA ===")
                for line_info in pending_lines:
                    narration_parts.append(line_info)

        narration = "\n".join(narration_parts) if narration_parts else False

        vals = {
            'move_type': move_type,
            'partner_id': partner.id,
            'invoice_date': self.issue_date,
            'invoice_date_due': self.due_date if self.due_date else self.issue_date,
            'ref': reference,
            'currency_id': self.document_currency_id.id if self.document_currency_id else self.currency_id.id,
            'invoice_line_ids': invoice_lines,
            'narration': narration,
        }

        # Propagar CUFE/CUDE a la factura si el campo existe
        if self.cufe and 'cufe' in self.env['account.move']._fields:
            vals['cufe'] = self.cufe
        if 'state_dian_document' in self.env['account.move']._fields:
            vals['state_dian_document'] = 'exitoso'

        # Agregar origen del documento
        if hasattr(self.env['account.move'], 'invoice_origin'):
            vals['invoice_origin'] = f"DIAN XML - {self.document_type}"

        return vals

    def _get_invoice_type(self):
        """Determina el tipo de factura en Odoo según el documento DIAN"""
        if self._is_purchase():
            if self.document_type == '91':  # Nota Crédito
                return 'in_refund'
            elif self.document_type == '92':  # Nota Débito
                return 'in_invoice'  # En Odoo las ND de proveedor son facturas regulares
            else:
                return 'in_invoice'
        else:
            if self.document_type == '91':
                return 'out_refund'
            elif self.document_type == '92':
                return 'out_invoice'
            else:
                return 'out_invoice'

    def _is_purchase(self):
        """Determina si es un documento de compra o venta"""
        # Si tiene proveedor, es compra
        if self.supplier_id:
            return True
        # Si tiene cliente, es venta
        if self.customer_id:
            return False
        # Por defecto, documento soporte (05) es compra
        if self.document_type == '05':
            return True
        # Por defecto, es venta
        return False

    def validate_xml_signature(self):
        """Valida el XML con DIAN usando el servicio nativo"""
        self.ensure_one()

        if not self.xml_content:
            raise UserError(_("No hay contenido XML para validar"))

        try:
            xml_content = base64.b64decode(self.xml_content).decode('utf-8')

            # Usar la función de validación extendida
            validation_result = xml_utils.validate_xml_with_dian(
                xml_content,
                self.company_id or self.env.company
            )

            if validation_result['is_valid']:
                self.message_post(
                    body=_("XML validado correctamente"),
                    message_type='notification'
                )
            else:
                error_msg = _("El XML tiene los siguientes problemas:\n")
                if validation_result['errors']:
                    error_msg += _("\nErrores:\n") + "\n".join(f"- {e}" for e in validation_result['errors'])
                if validation_result['warnings']:
                    error_msg += _("\nAdvertencias:\n") + "\n".join(f"- {w}" for w in validation_result['warnings'])

                self.message_post(
                    body=error_msg,
                    message_type='notification'
                )

            return validation_result['is_valid']

        except Exception as e:
            _logger.error(f"Error validando XML: {str(e)}")
            raise UserError(_("Error al validar el XML: %s") % str(e))

    def action_upload_and_process(self):
        """Guarda el registro y procesa el XML desde el wizard de carga rapida"""
        self.ensure_one()

        if not self.xml_content and not self.cufe:
            raise UserError(_("Debe cargar un archivo ZIP, XML o ingresar un CUFE"))

        if self.cufe and not self.xml_content:
            self.retrieve_xml_from_dian()

        if self.xml_content:
            self.process_xml()

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'dian.document.processor',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }
