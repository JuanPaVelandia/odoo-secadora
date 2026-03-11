# -*- coding: utf-8 -*-

import base64
import io
import logging
import zipfile

from lxml import etree

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Namespaces UBL 2.1 DIAN Colombia
NS = {
    'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
    'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
    'fe': 'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2',
    'cn': 'urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2',
    'dn': 'urn:oasis:names:specification:ubl:schema:xsd:DebitNote-2',
    'ext': 'urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2',
    'sts': 'dian:gov:co:facturaelectronica:Structures-2-1',
    'ds': 'http://www.w3.org/2000/09/xmldsig#',
}

# Mapeo de namespace raíz a tipo de documento Odoo
MOVE_TYPE_MAP = {
    '{urn:oasis:names:specification:ubl:schema:xsd:Invoice-2}Invoice': 'in_invoice',
    '{urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2}CreditNote': 'in_refund',
    '{urn:oasis:names:specification:ubl:schema:xsd:DebitNote-2}DebitNote': 'in_invoice',
}

# Tag de línea según tipo de documento
LINE_TAG_MAP = {
    '{urn:oasis:names:specification:ubl:schema:xsd:Invoice-2}Invoice': 'cac:InvoiceLine',
    '{urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2}CreditNote': 'cac:CreditNoteLine',
    '{urn:oasis:names:specification:ubl:schema:xsd:DebitNote-2}DebitNote': 'cac:DebitNoteLine',
}

# Tag de cantidad según tipo
QTY_TAG_MAP = {
    '{urn:oasis:names:specification:ubl:schema:xsd:Invoice-2}Invoice': 'cbc:InvoicedQuantity',
    '{urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2}CreditNote': 'cbc:CreditedQuantity',
    '{urn:oasis:names:specification:ubl:schema:xsd:DebitNote-2}DebitNote': 'cbc:DebitedQuantity',
}


class FacturaEmail(models.Model):
    _name = 'secadora.factura.email'
    _description = 'Factura Electrónica desde Correo'
    _inherit = ['mail.thread']
    _order = 'fecha_recepcion desc'
    _rec_name = 'name'

    name = fields.Char(
        string='Referencia',
        default='Nuevo',
        copy=False,
        index=True,
    )
    state = fields.Selection([
        ('pendiente', 'Pendiente'),
        ('procesado', 'Procesado'),
        ('error', 'Error'),
        ('duplicado', 'Duplicado'),
    ], string='Estado', default='pendiente', tracking=True, index=True)

    fecha_recepcion = fields.Datetime(
        string='Fecha Recepción',
        default=fields.Datetime.now,
        index=True,
    )
    emisor_nit = fields.Char(string='NIT Emisor', index=True)
    emisor_razon_social = fields.Char(string='Razón Social Emisor')
    numero_factura = fields.Char(string='Número Factura', index=True)
    cufe = fields.Char(string='CUFE', index=True, copy=False)
    fecha_emision = fields.Date(string='Fecha Emisión')
    fecha_vencimiento = fields.Date(string='Fecha Vencimiento')
    total_factura = fields.Float(string='Total Factura', digits='Product Price')
    tipo_documento = fields.Selection([
        ('invoice', 'Factura'),
        ('credit_note', 'Nota Crédito'),
        ('debit_note', 'Nota Débito'),
    ], string='Tipo Documento')

    factura_id = fields.Many2one(
        'account.move',
        string='Factura Creada',
        readonly=True,
        copy=False,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Proveedor',
        readonly=True,
    )
    error_msg = fields.Text(string='Mensaje de Error')
    xml_content = fields.Text(string='XML Crudo')
    pdf_content = fields.Binary(string='PDF Original', attachment=True)
    pdf_filename = fields.Char(string='Nombre PDF')

    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        default=lambda self: self.env.company,
        required=True,
    )

    # -------------------------------------------------------------------------
    # mail.thread: message_new — entrada desde fetchmail
    # -------------------------------------------------------------------------
    @api.model
    def message_new(self, msg_dict, custom_values=None):
        """Llamado por fetchmail cuando llega un correo nuevo."""
        defaults = {
            'fecha_recepcion': fields.Datetime.now(),
            'state': 'pendiente',
            'name': msg_dict.get('subject', 'Sin asunto')[:200],
        }
        if custom_values:
            defaults.update(custom_values)
        record = super().message_new(msg_dict, custom_values=defaults)
        try:
            record._procesar_adjuntos()
        except Exception as e:
            _logger.exception("Error procesando adjuntos del correo %s", record.id)
            record.write({
                'state': 'error',
                'error_msg': str(e),
            })
        return record

    # -------------------------------------------------------------------------
    # Procesamiento de adjuntos
    # -------------------------------------------------------------------------
    def _procesar_adjuntos(self):
        """Extrae adjuntos del mensaje, descomprime ZIPs, busca XML y PDF."""
        self.ensure_one()
        attachments = self.env['ir.attachment'].search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
        ])
        if not attachments:
            self.write({'state': 'error', 'error_msg': 'No se encontraron adjuntos en el correo.'})
            return

        xml_content = None
        pdf_data = None
        pdf_name = None

        for attach in attachments:
            fname = (attach.name or '').lower()
            raw_data = base64.b64decode(attach.datas) if attach.datas else b''

            if fname.endswith('.zip'):
                xml_content, pdf_data, pdf_name = self._extraer_zip(raw_data, xml_content, pdf_data, pdf_name)
            elif fname.endswith('.xml'):
                xml_content = raw_data.decode('utf-8', errors='replace')
            elif fname.endswith('.pdf'):
                pdf_data = raw_data
                pdf_name = attach.name

        if not xml_content:
            self.write({'state': 'error', 'error_msg': 'No se encontró archivo XML en los adjuntos.'})
            return

        self.xml_content = xml_content
        if pdf_data:
            self.pdf_content = base64.b64encode(pdf_data)
            self.pdf_filename = pdf_name

        # Parsear y crear factura
        self._procesar_xml(xml_content, pdf_data, pdf_name)

    def _extraer_zip(self, zip_bytes, xml_content, pdf_data, pdf_name):
        """Extrae XML y PDF de un archivo ZIP."""
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes), 'r') as zf:
                for zinfo in zf.infolist():
                    fname_lower = zinfo.filename.lower()
                    if fname_lower.endswith('.xml') and not xml_content:
                        xml_content = zf.read(zinfo.filename).decode('utf-8', errors='replace')
                    elif fname_lower.endswith('.pdf') and not pdf_data:
                        pdf_data = zf.read(zinfo.filename)
                        pdf_name = zinfo.filename
        except zipfile.BadZipFile:
            _logger.warning("Adjunto ZIP inválido, se ignora.")
        return xml_content, pdf_data, pdf_name

    # -------------------------------------------------------------------------
    # Parseo XML UBL/DIAN
    # -------------------------------------------------------------------------
    def _procesar_xml(self, xml_string, pdf_data, pdf_name):
        """Parsea el XML y crea la factura de proveedor."""
        self.ensure_one()
        try:
            datos = self._parsear_xml_dian(xml_string)
        except Exception as e:
            self.write({'state': 'error', 'error_msg': f'Error parseando XML: {e}'})
            return

        # Guardar datos extraídos en el registro
        self.write({
            'numero_factura': datos.get('numero_factura'),
            'cufe': datos.get('cufe'),
            'fecha_emision': datos.get('fecha_emision'),
            'fecha_vencimiento': datos.get('fecha_vencimiento'),
            'emisor_nit': datos.get('emisor_nit'),
            'emisor_razon_social': datos.get('emisor_razon_social'),
            'total_factura': datos.get('total'),
            'tipo_documento': datos.get('tipo_documento'),
            'name': datos.get('numero_factura') or self.name,
        })

        # Detectar duplicados por CUFE
        if datos.get('cufe'):
            existente = self.search([
                ('cufe', '=', datos['cufe']),
                ('state', '=', 'procesado'),
                ('id', '!=', self.id),
            ], limit=1)
            if existente:
                self.write({
                    'state': 'duplicado',
                    'error_msg': f"CUFE ya procesado en registro #{existente.id} ({existente.name})",
                })
                return

        # Buscar o crear proveedor
        try:
            partner = self._buscar_o_crear_partner(datos)
            self.partner_id = partner
        except Exception as e:
            self.write({'state': 'error', 'error_msg': f'Error buscando/creando proveedor: {e}'})
            return

        # Crear factura
        try:
            factura = self._crear_factura_proveedor(datos, partner, pdf_data, pdf_name)
            self.write({
                'factura_id': factura.id,
                'state': 'procesado',
                'error_msg': False,
            })
        except Exception as e:
            self.write({'state': 'error', 'error_msg': f'Error creando factura: {e}'})

    def _parsear_xml_dian(self, xml_string):
        """Parsea un XML de factura electrónica colombiana UBL 2.1."""
        root = etree.fromstring(xml_string.encode('utf-8'))

        # Determinar tipo de documento
        root_tag = root.tag
        move_type = MOVE_TYPE_MAP.get(root_tag)
        if not move_type:
            raise UserError(f'Tipo de documento XML no reconocido: {root_tag}')

        tipo_doc_map = {
            'in_invoice': 'invoice',
            'in_refund': 'credit_note',
        }
        # Nota débito es in_invoice pero tipo_documento distinto
        if 'DebitNote' in root_tag:
            tipo_doc = 'debit_note'
        else:
            tipo_doc = tipo_doc_map.get(move_type, 'invoice')

        datos = {
            'move_type': move_type,
            'tipo_documento': tipo_doc,
            'numero_factura': self._xml_text(root, './/cbc:ID'),
            'cufe': self._xml_text(root, './/cbc:UUID'),
            'fecha_emision': self._xml_text(root, './/cbc:IssueDate'),
            'fecha_vencimiento': self._xml_text(root, './/cbc:DueDate'),
            'moneda': self._xml_text(root, './/cbc:DocumentCurrencyCode'),
            'notas': self._xml_text(root, './/cbc:Note'),
        }

        # Emisor (Proveedor)
        supplier = root.find('.//cac:AccountingSupplierParty', NS)
        if supplier is not None:
            party = supplier.find('.//cac:Party', NS)
            datos['emisor_nit'] = self._xml_text(supplier, './/cbc:CompanyID')
            datos['emisor_razon_social'] = self._xml_text(
                supplier, './/cbc:RegistrationName'
            )
            if party is not None:
                datos['emisor_telefono'] = self._xml_text(party, './/cbc:Telephone')
                datos['emisor_email'] = self._xml_text(party, './/cbc:ElectronicMail')
                # Dirección
                address = party.find('.//cac:PhysicalLocation//cac:Address', NS)
                if address is None:
                    address = party.find('.//cac:PostalAddress', NS)
                if address is not None:
                    datos['emisor_direccion'] = self._xml_text(address, 'cbc:AddressLine/cbc:Line')
                    datos['emisor_ciudad'] = self._xml_text(address, 'cbc:CityName')
                    datos['emisor_departamento'] = self._xml_text(address, 'cbc:CountrySubentity')

        # Receptor (nosotros — para validación)
        receptor = root.find('.//cac:AccountingCustomerParty', NS)
        if receptor is not None:
            datos['receptor_nit'] = self._xml_text(receptor, './/cbc:CompanyID')

        # Total
        monetary = root.find('.//cac:LegalMonetaryTotal', NS)
        if monetary is not None:
            payable = self._xml_text(monetary, 'cbc:PayableAmount')
            datos['total'] = float(payable) if payable else 0.0
        else:
            datos['total'] = 0.0

        # Líneas de factura
        line_tag = LINE_TAG_MAP.get(root_tag, 'cac:InvoiceLine')
        qty_tag = QTY_TAG_MAP.get(root_tag, 'cbc:InvoicedQuantity')
        datos['items'] = []
        for line in root.findall(f'.//{line_tag}', NS):
            item = self._parsear_linea(line, qty_tag)
            if item:
                datos['items'].append(item)

        return datos

    def _parsear_linea(self, line_node, qty_tag):
        """Parsea una línea de factura UBL."""
        descripcion = self._xml_text(line_node, './/cac:Item//cbc:Description')
        if not descripcion:
            descripcion = self._xml_text(line_node, './/cac:Item//cbc:Name')
        if not descripcion:
            descripcion = 'Producto/Servicio'

        cantidad_str = self._xml_text(line_node, f'.//{qty_tag}')
        cantidad = float(cantidad_str) if cantidad_str else 1.0

        precio_str = self._xml_text(line_node, './/cac:Price//cbc:PriceAmount')
        precio_unitario = float(precio_str) if precio_str else 0.0

        # Impuestos de la línea
        porcentaje_iva = 0.0
        tax_subtotal = line_node.find('.//cac:TaxTotal//cac:TaxSubtotal', NS)
        if tax_subtotal is not None:
            pct = self._xml_text(tax_subtotal, './/cac:TaxCategory//cbc:Percent')
            if pct:
                porcentaje_iva = float(pct)

        return {
            'descripcion': descripcion,
            'cantidad': cantidad,
            'precio_unitario': precio_unitario,
            'porcentaje_iva': porcentaje_iva,
        }

    def _xml_text(self, node, xpath):
        """Extrae texto de un nodo XML de forma segura."""
        el = node.find(xpath, NS)
        return el.text.strip() if el is not None and el.text else None

    # -------------------------------------------------------------------------
    # Proveedor
    # -------------------------------------------------------------------------
    def _buscar_o_crear_partner(self, datos):
        """Busca proveedor por NIT, o lo crea si no existe."""
        nit = datos.get('emisor_nit')
        if not nit:
            raise UserError('El XML no contiene NIT del emisor.')

        # Limpiar NIT (quitar DV, guiones, puntos)
        nit_limpio = nit.replace('-', '').replace('.', '').strip()
        # Si tiene dígito de verificación (últimos dígitos después de guión), separar
        # El NIT en Colombia puede venir como 900123456-1
        nit_buscar = nit_limpio.split('-')[0] if '-' in nit else nit_limpio

        partner = self.env['res.partner'].search([
            '|',
            ('vat', '=', nit_buscar),
            ('vat', '=', nit),
        ], limit=1)

        if not partner:
            vals = {
                'name': datos.get('emisor_razon_social') or nit,
                'vat': nit_buscar,
                'supplier_rank': 1,
                'company_type': 'company',
            }
            if datos.get('emisor_email'):
                vals['email'] = datos['emisor_email']
            if datos.get('emisor_telefono'):
                vals['phone'] = datos['emisor_telefono']
            if datos.get('emisor_direccion'):
                vals['street'] = datos['emisor_direccion']
            if datos.get('emisor_ciudad'):
                vals['city'] = datos['emisor_ciudad']

            partner = self.env['res.partner'].create(vals)
            _logger.info("Proveedor creado: %s (NIT: %s)", partner.name, nit_buscar)

        return partner

    # -------------------------------------------------------------------------
    # Creación de factura
    # -------------------------------------------------------------------------
    def _crear_factura_proveedor(self, datos, partner, pdf_data, pdf_name):
        """Crea account.move (in_invoice o in_refund) con las líneas parseadas."""
        self.ensure_one()

        move_type = datos.get('move_type', 'in_invoice')

        invoice_lines = []
        for item in datos.get('items', []):
            line_vals = {
                'name': item['descripcion'],
                'quantity': item['cantidad'],
                'price_unit': item['precio_unitario'],
            }
            # Buscar impuesto por porcentaje
            if item.get('porcentaje_iva') and item['porcentaje_iva'] > 0:
                tax = self.env['account.tax'].search([
                    ('type_tax_use', '=', 'purchase'),
                    ('amount', '=', item['porcentaje_iva']),
                    ('company_id', '=', self.company_id.id),
                ], limit=1)
                if tax:
                    line_vals['tax_ids'] = [(6, 0, [tax.id])]

            invoice_lines.append((0, 0, line_vals))

        factura_vals = {
            'move_type': move_type,
            'partner_id': partner.id,
            'company_id': self.company_id.id,
            'invoice_date': datos.get('fecha_emision'),
            'invoice_date_due': datos.get('fecha_vencimiento'),
            'ref': datos.get('numero_factura'),
            'narration': datos.get('notas'),
            'invoice_line_ids': invoice_lines,
        }

        factura = self.env['account.move'].create(factura_vals)

        # Adjuntar PDF a la factura
        if pdf_data:
            self.env['ir.attachment'].create({
                'name': pdf_name or f"{datos.get('numero_factura', 'factura')}.pdf",
                'type': 'binary',
                'datas': base64.b64encode(pdf_data),
                'res_model': 'account.move',
                'res_id': factura.id,
            })

        _logger.info(
            "Factura %s creada desde correo: %s (proveedor: %s)",
            factura.name, datos.get('numero_factura'), partner.name
        )
        return factura

    # -------------------------------------------------------------------------
    # Reprocesar
    # -------------------------------------------------------------------------
    def action_reprocesar(self):
        """Reprocesa un registro en error usando el XML guardado."""
        self.ensure_one()
        if not self.xml_content:
            raise UserError('No hay contenido XML guardado para reprocesar.')

        pdf_data = base64.b64decode(self.pdf_content) if self.pdf_content else None
        pdf_name = self.pdf_filename

        self.write({'state': 'pendiente', 'error_msg': False, 'factura_id': False})
        self._procesar_xml(self.xml_content, pdf_data, pdf_name)

    def action_ver_factura(self):
        """Abre la factura creada en una ventana."""
        self.ensure_one()
        if not self.factura_id:
            raise UserError('No hay factura asociada.')
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.factura_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # -------------------------------------------------------------------------
    # Cron
    # -------------------------------------------------------------------------
    @api.model
    def _cron_reprocesar_pendientes(self):
        """Reprocesa registros que quedaron en estado pendiente (con XML)."""
        pendientes = self.search([
            ('state', '=', 'pendiente'),
            ('xml_content', '!=', False),
        ], limit=50)
        for rec in pendientes:
            try:
                pdf_data = base64.b64decode(rec.pdf_content) if rec.pdf_content else None
                rec._procesar_xml(rec.xml_content, pdf_data, rec.pdf_filename)
            except Exception as e:
                _logger.exception("Error reprocesando factura email %s", rec.id)
                rec.write({'state': 'error', 'error_msg': str(e)})
