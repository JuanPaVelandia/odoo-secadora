import base64
import logging
import tempfile
import xmltodict
import xml.etree.ElementTree as ET
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from odoo import  _, api, fields, models, tools
from odoo.exceptions import ValidationError
from zipfile import ZipFile
_logger = logging.getLogger(__name__)


class RecepcionFacturaDian(models.Model):
    _name = 'recepcion.factura.dian'
    _description = 'Recepcion Factura Dian'
    _inherit = ['mail.thread']

    name = fields.Char('Nombre')
    cufe = fields.Char('Cufe')
    company_id = fields.Many2one('res.company', string='Compañia',  default=lambda self: self.env.company)
    supplier_id = fields.Many2one('res.partner','Proveedor')
    state = fields.Selection([('draft', 'Borrador'), ('read', 'Leido'), ('procces', 'Procesado'), ('send', 'Enviado')],'State',default='draft')
    zip_file = fields.Binary('Archivo Zip')
    pdf_file = fields.Binary('Factura')
    xml_text = fields.Text('Contenido XML')
    invoice_xml = fields.Text('Factura XML')
    file_name = fields.Char('File name')
    date_invoice = fields.Date('Fecha de factura')
    order_line_ids = fields.One2many('recepcion.factura.dian.line','recepcion_id','Lineas de factura')
    tax_ids = fields.One2many('recepcion.factura.dian.tax', 'recepcion_id', 'Impuestos')
    n_invoice = fields.Char('Nº Factura')
    total_untax = fields.Float('Total sin impuestos')
    total_tax = fields.Float('Total impuestos')
    total = fields.Float('Total')
    application_response_ids = fields.Many2many('dian.application.response')
    tiene_eventos = fields.Boolean(compute='_compute_tiene_eventos', store=True)

    @api.depends('application_response_ids')
    def _compute_tiene_eventos(self):
        for rec in self:
            rec.tiene_eventos = bool(rec.application_response_ids)

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        if custom_values is None:
            for attachement_id in msg_dict.get('attachments'):
                if attachement_id.fname[-3:].lower() == 'zip':
                    custom_values = {
                        'zip_file': base64.b64encode(attachement_id.content)
                    }
            if 'zip_file' in custom_values:
                recepcion_id = super(RecepcionFacturaDian, self).message_new(msg_dict, custom_values)
                recepcion_id.read_zip()
                recepcion_id.process_xml()
            return False
        else:
            return False

    def return_inverse_number_document_type(self, document_type):
        documento = 'no_identification'
        if document_type:
            document_type = int(document_type)
            document_types = {
                31: 'rut',
                13: 'national_citizen_id',
                11: 'civil_registration',
                12: 'id_card',
                22: 'foreign_id_card',
                41: 'passport',
            }
            documento = document_types.get(document_type)
        return documento




    def process_xml(self):
        try:
            # Preservar el CUFE que ya fue extraído
            cufe_original = self.cufe
            
            dict_data_xml = xmltodict.parse(self.xml_text)
            dict_xml_invoice = xmltodict.parse(self.invoice_xml)
            
            # Validar estructura del XML
            if 'AttachedDocument' not in dict_data_xml and 'Invoice' not in dict_xml_invoice:
                raise ValidationError(_('El XML no contiene una estructura de AttachedDocument o Invoice válida.'))
            
            # Extraer datos del proveedor
            supplier = None
            supplier_vat = None
            supplier_name = None
            
            if 'AttachedDocument' in dict_data_xml:
                try:
                    supplier_vat = dict_data_xml['AttachedDocument']['cac:SenderParty']['cac:PartyTaxScheme']['cbc:CompanyID']['#text']
                    supplier_name = dict_data_xml['AttachedDocument']['cac:SenderParty']['cac:PartyTaxScheme']['cbc:RegistrationName']
                    supplier = self.env['res.partner'].search([('vat_co', '=', supplier_vat)], limit=1)
                except (KeyError, TypeError) as e:
                    _logger.warning(f'Error al extraer datos del proveedor: {e}')
            
            # Crear proveedor si no existe
            if not supplier and supplier_vat:
                try:
                    respon_fiscal = []
                    tax_level = dict_data_xml['AttachedDocument']['cac:SenderParty']['cac:PartyTaxScheme']['cbc:TaxLevelCode']["#text"]
                    for f in tax_level.split(';'):
                        respon_fiscal.append((4, self.env['dian.fiscal.responsability'].search([('code', '=', f)]).id))
                    
                    documento = self.return_inverse_number_document_type(
                        dict_data_xml['AttachedDocument']['cac:SenderParty']['cac:PartyTaxScheme']['cbc:CompanyID'].get('@schemeName')
                    )
                    
                    supplier = self.env['res.partner'].create({
                        'name': supplier_name,
                        'is_company': True,
                        'vat_co': supplier_vat,
                        'personType': '2',
                        'l10n_latam_identification_type_id': self.env['l10n_latam.identification.type'].search([
                            ('l10n_co_document_code', '=', documento)
                        ]).id,
                        'companyName': supplier_name,
                        'fiscal_responsability_ids': respon_fiscal,
                    })
                except (KeyError, TypeError) as e:
                    _logger.warning(f'Error al crear proveedor: {e}')
            
            if supplier:
                self.supplier_id = supplier
            
            # Procesar factura
            if 'Invoice' in dict_xml_invoice:
                invoice_data = dict_xml_invoice['Invoice']
                
                # Fecha de factura
                try:
                    self.date_invoice = datetime.strptime(invoice_data['cbc:IssueDate'], '%Y-%m-%d')
                except (KeyError, ValueError):
                    _logger.warning('No se encontró fecha de factura válida')
                
                # Líneas de factura
                try:
                    invoice_lines = invoice_data.get('cac:InvoiceLine', [])
                    if not isinstance(invoice_lines, list):
                        invoice_lines = [invoice_lines]
                    
                    self.order_line_ids = False  # Limpiar líneas existentes
                    
                    for line in invoice_lines:
                        try:
                            qty = float(line['cbc:InvoicedQuantity']['#text']) if isinstance(line['cbc:InvoicedQuantity'], dict) else float(line['cbc:InvoicedQuantity'])
                            total_line = float(line['cbc:LineExtensionAmount']['#text']) if isinstance(line['cbc:LineExtensionAmount'], dict) else float(line['cbc:LineExtensionAmount'])
                            # Calcular precio unitario dividiendo el total entre la cantidad
                            price_unit = total_line / qty if qty > 0 else 0
                            
                            # Crear línea
                            line_obj = self.env['recepcion.factura.dian.line'].create({
                                'recepcion_id': self.id,
                                'name': line['cac:Item']['cbc:Description'],
                                'qty': qty,
                                'uom': line['cbc:InvoicedQuantity'].get('@unitCode', 'unidad') if isinstance(line['cbc:InvoicedQuantity'], dict) else 'unidad',
                                'price': price_unit,
                                'total': total_line,
                            })
                            
                            # Procesar impuestos de la línea
                            line_taxes = line.get('cac:TaxTotal', [])
                            if not isinstance(line_taxes, list):
                                line_taxes = [line_taxes] if line_taxes else []
                            
                            for tax_total in line_taxes:
                                tax_subtotals = tax_total.get('cac:TaxSubtotal', [])
                                if not isinstance(tax_subtotals, list):
                                    tax_subtotals = [tax_subtotals] if tax_subtotals else []
                                
                                for subtotal in tax_subtotals:
                                    try:
                                        taxable = subtotal.get('cbc:TaxableAmount')
                                        taxable_val = float(taxable.get('#text', 0)) if isinstance(taxable, dict) else float(taxable) if taxable else 0
                                        
                                        tax_amt = subtotal.get('cbc:TaxAmount')
                                        tax_amt_val = float(tax_amt.get('#text', 0)) if isinstance(tax_amt, dict) else float(tax_amt) if tax_amt else 0
                                        
                                        tax_category = subtotal.get('cac:TaxCategory', {})
                                        percent = tax_category.get('cbc:Percent', '0')
                                        
                                        tax_scheme = tax_category.get('cac:TaxScheme', {})
                                        tax_id = tax_scheme.get('cbc:ID', '')
                                        tax_name = tax_scheme.get('cbc:Name', 'Impuesto')
                                        
                                        self.env['recepcion.factura.dian.line.tax'].create({
                                            'line_id': line_obj.id,
                                            'name': tax_name,
                                            'tax_id': tax_id,
                                            'tax_type': 'tax',
                                            'percentage': float(percent),
                                            'taxable_amount': taxable_val,
                                            'tax_amount': tax_amt_val,
                                        })
                                    except (KeyError, ValueError, TypeError) as e:
                                        _logger.warning(f'Error al procesar impuesto de línea: {e}')
                            
                            # Procesar retenciones de la línea
                            line_withholdings = line.get('cac:WithholdingTaxTotal', [])
                            if not isinstance(line_withholdings, list):
                                line_withholdings = [line_withholdings] if line_withholdings else []
                            
                            for withholding_total in line_withholdings:
                                with_subtotals = withholding_total.get('cac:TaxSubtotal', [])
                                if not isinstance(with_subtotals, list):
                                    with_subtotals = [with_subtotals] if with_subtotals else []
                                
                                for subtotal in with_subtotals:
                                    try:
                                        taxable = subtotal.get('cbc:TaxableAmount')
                                        taxable_val = float(taxable.get('#text', 0)) if isinstance(taxable, dict) else float(taxable) if taxable else 0
                                        
                                        with_amt = subtotal.get('cbc:TaxAmount')
                                        with_amt_val = float(with_amt.get('#text', 0)) if isinstance(with_amt, dict) else float(with_amt) if with_amt else 0
                                        
                                        tax_category = subtotal.get('cac:TaxCategory', {})
                                        percent = tax_category.get('cbc:Percent', '0')
                                        
                                        tax_scheme = tax_category.get('cac:TaxScheme', {})
                                        tax_id = tax_scheme.get('cbc:ID', '')
                                        tax_name = tax_scheme.get('cbc:Name', 'Retención')
                                        
                                        self.env['recepcion.factura.dian.line.tax'].create({
                                            'line_id': line_obj.id,
                                            'name': tax_name,
                                            'tax_id': tax_id,
                                            'tax_type': 'withholding',
                                            'percentage': float(percent),
                                            'taxable_amount': taxable_val,
                                            'tax_amount': with_amt_val,
                                        })
                                    except (KeyError, ValueError, TypeError) as e:
                                        _logger.warning(f'Error al procesar retención de línea: {e}')
                        except (KeyError, ValueError) as e:
                            _logger.warning(f'Error al procesar línea de factura: {e}')
                except (KeyError, TypeError) as e:
                    _logger.warning(f'Error al procesar líneas: {e}')
                
                # Número de factura
                try:
                    self.n_invoice = invoice_data.get('cbc:ID', '')
                except KeyError:
                    pass
                
                # Totales y extracción de impuestos desglosados
                total_tax = 0
                tax_total_amount = 0
                withholding_total_amount = 0
                try:
                    # Procesar impuestos (TaxTotal)
                    tax_list = invoice_data.get('cac:TaxTotal', [])
                    if not isinstance(tax_list, list):
                        tax_list = [tax_list] if tax_list else []
                    
                    self.tax_ids = False  # Limpiar impuestos existentes
                    
                    for tax_total in tax_list:
                        try:
                            # Monto total del impuesto
                            tax_amount_val = tax_total.get('cbc:TaxAmount')
                            if isinstance(tax_amount_val, dict):
                                tax_amount_val = float(tax_amount_val.get('#text', 0))
                            else:
                                tax_amount_val = float(tax_amount_val) if tax_amount_val else 0
                            total_tax += tax_amount_val
                            tax_total_amount += tax_amount_val
                            
                            # Procesar subtotales (cada impuesto individual)
                            tax_subtotals = tax_total.get('cac:TaxSubtotal', [])
                            if not isinstance(tax_subtotals, list):
                                tax_subtotals = [tax_subtotals] if tax_subtotals else []
                            
                            for subtotal in tax_subtotals:
                                try:
                                    taxable = subtotal.get('cbc:TaxableAmount')
                                    taxable_val = float(taxable.get('#text', 0)) if isinstance(taxable, dict) else float(taxable) if taxable else 0
                                    
                                    tax_amt = subtotal.get('cbc:TaxAmount')
                                    tax_amt_val = float(tax_amt.get('#text', 0)) if isinstance(tax_amt, dict) else float(tax_amt) if tax_amt else 0
                                    
                                    tax_category = subtotal.get('cac:TaxCategory', {})
                                    percent = tax_category.get('cbc:Percent', '0')
                                    
                                    tax_scheme = tax_category.get('cac:TaxScheme', {})
                                    tax_id = tax_scheme.get('cbc:ID', '')
                                    tax_name = tax_scheme.get('cbc:Name', 'Impuesto')
                                    
                                    # Crear registro de impuesto
                                    self.env['recepcion.factura.dian.tax'].create({
                                        'recepcion_id': self.id,
                                        'name': tax_name,
                                        'tax_id': tax_id,
                                        'tax_type': 'tax',
                                        'percentage': float(percent),
                                        'taxable_amount': taxable_val,
                                        'tax_amount': tax_amt_val,
                                    })
                                except (KeyError, ValueError, TypeError) as e:
                                    _logger.warning(f'Error al procesar subtotal de impuesto: {e}')
                        except (KeyError, ValueError, TypeError) as e:
                            _logger.warning(f'Error al procesar TaxTotal: {e}')
                    
                    # Procesar retenciones (WithholdingTaxTotal)
                    withholding_list = invoice_data.get('cac:WithholdingTaxTotal', [])
                    if not isinstance(withholding_list, list):
                        withholding_list = [withholding_list] if withholding_list else []
                    
                    for withholding_total in withholding_list:
                        try:
                            # Monto total de retención
                            with_amount_val = withholding_total.get('cbc:TaxAmount')
                            if isinstance(with_amount_val, dict):
                                with_amount_val = float(with_amount_val.get('#text', 0))
                            else:
                                with_amount_val = float(with_amount_val) if with_amount_val else 0
                            total_tax += with_amount_val
                            withholding_total_amount += with_amount_val
                            
                            # Procesar subtotales de retenciones
                            with_subtotals = withholding_total.get('cac:TaxSubtotal', [])
                            if not isinstance(with_subtotals, list):
                                with_subtotals = [with_subtotals] if with_subtotals else []
                            
                            for subtotal in with_subtotals:
                                try:
                                    taxable = subtotal.get('cbc:TaxableAmount')
                                    taxable_val = float(taxable.get('#text', 0)) if isinstance(taxable, dict) else float(taxable) if taxable else 0
                                    
                                    with_amt = subtotal.get('cbc:TaxAmount')
                                    with_amt_val = float(with_amt.get('#text', 0)) if isinstance(with_amt, dict) else float(with_amt) if with_amt else 0
                                    
                                    tax_category = subtotal.get('cac:TaxCategory', {})
                                    percent = tax_category.get('cbc:Percent', '0')
                                    
                                    tax_scheme = tax_category.get('cac:TaxScheme', {})
                                    tax_id = tax_scheme.get('cbc:ID', '')
                                    tax_name = tax_scheme.get('cbc:Name', 'Retención')
                                    
                                    # Crear registro de retención
                                    self.env['recepcion.factura.dian.tax'].create({
                                        'recepcion_id': self.id,
                                        'name': tax_name,
                                        'tax_id': tax_id,
                                        'tax_type': 'withholding',
                                        'percentage': float(percent),
                                        'taxable_amount': taxable_val,
                                        'tax_amount': with_amt_val,
                                    })
                                except (KeyError, ValueError, TypeError) as e:
                                    _logger.warning(f'Error al procesar subtotal de retención: {e}')
                        except (KeyError, ValueError, TypeError) as e:
                            _logger.warning(f'Error al procesar WithholdingTaxTotal: {e}')
                    
                    self.total_tax = total_tax
                except (KeyError, ValueError, TypeError) as e:
                    _logger.warning(f'Error al procesar impuestos: {e}')
                    self.total_tax = 0
                
                try:
                    untax_amount = invoice_data['cac:LegalMonetaryTotal']['cbc:LineExtensionAmount']
                    self.total_untax = float(untax_amount['#text']) if isinstance(untax_amount, dict) else float(untax_amount)
                except (KeyError, ValueError):
                    _logger.warning('No se encontró total sin impuestos')
                
                try:
                    total_amount = invoice_data['cac:LegalMonetaryTotal']['cbc:PayableAmount']
                    self.total = float(total_amount['#text']) if isinstance(total_amount, dict) else float(total_amount)
                except (KeyError, ValueError):
                    _logger.warning('No se encontró total pagable')

                # Validar consistencia entre base y total de impuestos
                if self.total_untax and self.total:
                    currency = self.company_id.currency_id or self.env.company.currency_id
                    rounding = currency.rounding if currency else 0.01
                    quant = Decimal(str(rounding))

                    expected_tax = (Decimal(str(self.total)) - Decimal(str(self.total_untax))).quantize(
                        quant, rounding=ROUND_HALF_UP
                    )
                    tax_total_only = Decimal(str(tax_total_amount)).quantize(
                        quant, rounding=ROUND_HALF_UP
                    )
                    withholding_total = Decimal(str(withholding_total_amount)).quantize(
                        quant, rounding=ROUND_HALF_UP
                    )
                    total_tax_all = (tax_total_only + withholding_total).quantize(
                        quant, rounding=ROUND_HALF_UP
                    )

                    _logger.info(
                        'Impuestos: base=%s, total=%s, esperado=%s, impuestos=%s, retenciones=%s, impuestos+retenciones=%s',
                        self.total_untax, self.total, expected_tax, tax_total_only, withholding_total, total_tax_all
                    )

                    # Selección de impuestos que cuadran con el total (solo impuestos, sin retenciones)
                    selected_tax_ids = self.env['recepcion.factura.dian.tax']
                    taxes = self.tax_ids.filtered(lambda t: t.tax_type == 'tax')
                    expected_tax_float = float(expected_tax)

                    if taxes:
                        # 1) Coincidencia individual exacta
                        for tax in taxes:
                            if Decimal(str(tax.tax_amount)).quantize(quant, rounding=ROUND_HALF_UP) == expected_tax:
                                selected_tax_ids = tax
                                break

                        # 2) Suma acumulada (orden descendente) hasta cuadrar
                        if not selected_tax_ids and len(taxes) > 1:
                            running = Decimal('0.0')
                            picked = self.env['recepcion.factura.dian.tax']
                            for tax in taxes.sorted(key=lambda t: t.tax_amount or 0.0, reverse=True):
                                running = (running + Decimal(str(tax.tax_amount))).quantize(quant, rounding=ROUND_HALF_UP)
                                picked |= tax
                                if running == expected_tax:
                                    selected_tax_ids = picked
                                    break

                    # Si encontramos combinación, dejamos solo esos impuestos
                    if selected_tax_ids:
                        (taxes - selected_tax_ids).unlink()
                        self.total_tax = sum(selected_tax_ids.mapped('tax_amount'))
                        _logger.info(
                            'Impuestos: selección aplicada. esperado=%s, impuestos_seleccionados=%s',
                            expected_tax_float, self.total_tax
                        )
                    else:
                        _logger.warning(
                            'Impuestos: no se encontró combinación exacta. '
                            'base=%s, total=%s, esperado=%s, impuestos=%s',
                            self.total_untax, self.total, expected_tax_float, tax_total_amount
                        )
                
                # Actualizar nombre y estado
                if supplier:
                    self.name = f"{supplier.name} - {self.n_invoice}"
                
                self.state = 'procces'
            else:
                raise ValidationError(_('No se encontró información de factura en el XML procesado.'))
            
            # Restaurar CUFE si fue extraído en read_zip
            if cufe_original and not self.cufe:
                self.cufe = cufe_original
        
        except ValidationError:
            raise
        except Exception as e:
            raise ValidationError(_('Error al procesar XML: %s') % str(e))

    def add_application_response(self):
        response_code = self._context.get('response_code')
        if not response_code:
            raise ValidationError(_('Debe seleccionar un tipo de evento (response_code).'))
        if not self.xml_text:
            raise ValidationError(_('El contenido XML del documento no está disponible. Asegúrese de cargar y procesar el archivo ZIP.'))
        
        try:
            company = self.env.company
            
            # doc_adq: adquiriente (cliente en ventas, empresa propia en compras)
            # BUG-003: Pasar datos del proveedor para ReceiverParty
            # BUG-004: Pasar CUFE e fecha de factura
            ar = self.env['dian.application.response'].create({
                'response_code': response_code,
                'document_referenced': self.n_invoice or self.name,
                'doc_adq': company.partner_id.vat_co,
                # BUG-003: Datos del ReceiverParty (proveedor)
                'invoice_receiver_name': self.supplier_id.name if self.supplier_id else '',
                'invoice_receiver_vat': self.supplier_id.vat_co if self.supplier_id else '',
                'invoice_receiver_dv': self.supplier_id.dv if self.supplier_id and hasattr(self.supplier_id, 'dv') else '',
                'invoice_receiver_scheme': '31',
                # BUG-004: CUFE e fecha de la factura
                'invoice_cufe': self.cufe,
                'invoice_issue_date': str(self.date_invoice) if self.date_invoice else '',
            })
            self.application_response_ids = [(4, ar.id)]
            
            # BUG-001: Enviar el evento a DIAN inmediatamente
            ar.action_send_dian()
            self.state = 'send'
            
        except Exception as e:
            raise ValidationError(_('Error al crear el evento: %s') % str(e))

    def action_register_event(self):
        action = self.env.ref('l10n_co_e_invoice.action_register_event_dian').sudo().read()[0]
        return action

    def read_zip(self):
        if not self.zip_file:
            raise ValidationError(_('Debe cargar un archivo ZIP antes de extraer su contenido.'))
        file = base64.decodebytes(self.zip_file)
        fobj = tempfile.NamedTemporaryFile(delete=False)
        fname = fobj.name
        fobj.write(file)
        fobj.close()
        f = open(fname, 'r+b')

        attached_document_xml = None
        invoice_xml = None

        with ZipFile(f, 'r') as zip_file:
            for nombre in zip_file.namelist():
                if nombre[-4:] == '.xml':
                    _contenido = zip_file.open(nombre).read()
                    # Decodificar bytes a string si es necesario
                    if isinstance(_contenido, bytes):
                        _contenido = _contenido.decode('utf-8')
                    
                    # Identificar tipo de XML
                    if 'AttachedDocument' in nombre or 'attachmentDocument' in nombre:
                        attached_document_xml = _contenido
                        self.xml_text = _contenido
                    elif 'Invoice' in nombre:
                        invoice_xml = _contenido
                    else:
                        # Por defecto, usar el que sea
                        if not attached_document_xml:
                            self.xml_text = _contenido
                    
                    self.name = nombre[:-4]
                
                if nombre[-4:] == '.pdf':
                    self.pdf_file = base64.b64encode(zip_file.open(nombre).read())
            f.close()

        # Validar que se encontró el XML correcto
        if not self.xml_text:
            raise ValidationError(_('No se encontró archivo XML válido en el ZIP.'))
        
        # Parsear y asignar invoice_xml con validación
        try:
            parsed = xmltodict.parse(self.xml_text)
            
            # Buscar la estructura correcta
            if 'AttachedDocument' in parsed:
                self.invoice_xml = parsed['AttachedDocument']['cac:Attachment']['cac:ExternalReference']['cbc:Description']
                # Extraer CUFE del AttachedDocument
                try:
                    # Buscar CUFE en la factura embebida (dentro de cbc:Description)
                    invoice_parsed = xmltodict.parse(self.invoice_xml)
                    if 'Invoice' in invoice_parsed:
                        cufe_data = invoice_parsed['Invoice'].get('cbc:UUID', '')
                        if isinstance(cufe_data, dict):
                            self.cufe = cufe_data.get('#text', '')
                        else:
                            self.cufe = cufe_data
                    else:
                        _logger.warning('No se encontró factura embebida en el AttachedDocument')
                except (KeyError, TypeError) as e:
                    _logger.warning(f'Error al extraer CUFE del AttachedDocument: {e}')
            elif 'Invoice' in parsed:
                self.invoice_xml = self.xml_text
                # Extraer CUFE de factura
                try:
                    cufe_data = parsed['Invoice'].get('cbc:UUID', '') or parsed['Invoice'].get('cbc:UBLVersionID', '')
                    if isinstance(cufe_data, dict):
                        self.cufe = cufe_data.get('#text', '')
                    else:
                        self.cufe = cufe_data
                except (KeyError, TypeError):
                    _logger.warning('No se encontró CUFE en la factura')
            else:
                raise ValidationError(_('El XML no tiene la estructura esperada (AttachedDocument o Invoice).'))
        except Exception as e:
            raise ValidationError(_('Error al procesar el XML: %s') % str(e))

        # Cambiamos estado
        self.state = 'read'
        return


class RecepcionFacturaDianTax(models.Model):
    _name = 'recepcion.factura.dian.tax'
    _description = 'Impuesto en factura DIAN recibida'

    name = fields.Char('Nombre del impuesto')
    recepcion_id = fields.Many2one('recepcion.factura.dian', 'Recepción de factura DIAN')
    tax_id = fields.Char('ID de impuesto (DIAN)', help='Ejemplo: 01 para IVA, 08 para ICA, etc.')
    tax_type = fields.Selection([
        ('tax', 'Impuesto'),
        ('withholding', 'Retención')
    ], string='Tipo de impuesto', default='tax')
    percentage = fields.Float('Porcentaje (%)')
    taxable_amount = fields.Float('Monto gravable')
    tax_amount = fields.Float('Monto de impuesto')


class RecepcionFacturaDianLineTax(models.Model):
    _name = 'recepcion.factura.dian.line.tax'
    _description = 'Impuesto en línea de factura DIAN recibida'

    name = fields.Char('Nombre del impuesto')
    line_id = fields.Many2one('recepcion.factura.dian.line', 'Línea de recepción')
    tax_id = fields.Char('ID de impuesto (DIAN)')
    tax_type = fields.Selection([
        ('tax', 'Impuesto'),
        ('withholding', 'Retención')
    ], string='Tipo de impuesto', default='tax')
    percentage = fields.Float('Porcentaje (%)')
    taxable_amount = fields.Float('Monto gravable')
    tax_amount = fields.Float('Monto de impuesto')


class RecepcionFacturaDianLine(models.Model):
    _name = 'recepcion.factura.dian.line'
    _description = 'Linea recepcion factura DIAN'

    name = fields.Char('Producto')
    recepcion_id = fields.Many2one('recepcion.factura.dian','Recepcion de factura DIAN')
    uom = fields.Char('Unidad de Medida')
    qty = fields.Float('Cantidad')
    price = fields.Float('Precio')
    total = fields.Float('Total')
    tax_ids = fields.One2many('recepcion.factura.dian.line.tax', 'line_id', 'Impuestos')
