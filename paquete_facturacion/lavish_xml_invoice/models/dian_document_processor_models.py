# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)

class DianDocumentProcessorLot(models.Model):
    _name = 'dian.document.processor.lot'
    _description = 'Lote de Producto en Documento DIAN'
    _order = 'line_id, sequence'

    line_id = fields.Many2one('dian.document.processor.line', string='Línea', required=True, ondelete='cascade')
    sequence = fields.Integer('Secuencia', default=10)

    lot_number = fields.Char('Número de Lote', required=True)
    expiry_date = fields.Date('Fecha de Vencimiento')
    quantity = fields.Float('Cantidad del Lote', digits='Product Unit of Measure',
                           help='Cantidad específica de este lote')
    notes = fields.Char('Notas')


class DianDocumentProcessorLine(models.Model):
    _name = 'dian.document.processor.line'
    _description = 'Línea de Documento DIAN'
    _order = 'sequence, id'
    
    processor_id = fields.Many2one('dian.document.processor', required=True, ondelete='cascade')
    sequence = fields.Integer('Secuencia', default=10)
    
    # ========== IDENTIFICACIÓN PRODUCTO ==========
    product_code = fields.Char('Código Producto Proveedor',
                              help='Código interno del proveedor (SellersItemIdentification)')
    product_ean = fields.Char('Código Estándar',
                             help='Código EAN/GTIN o código personalizado del proveedor')
    product_ean_type = fields.Selection([
        ('gtin', 'GTIN/EAN (Código de Barras)'),
        ('custom', 'Código Personalizado'),
        ('unknown', 'Desconocido')
    ], string='Tipo Código Estándar', default='unknown',
       help='010/GTIN = Código de barras real, 999 = Código personalizado del contribuyente')
    product_name = fields.Char('Descripción')
    product_brand = fields.Char('Marca')
    product_model = fields.Char('Modelo')
    product_id = fields.Many2one('product.product', 'Producto Odoo')
    
    # ========== CANTIDADES Y PRECIOS ==========
    quantity = fields.Float('Cantidad', digits='Product Unit of Measure')
    uom_code = fields.Char('Código UOM')
    uom_id = fields.Many2one('uom.uom', 'Unidad de Medida', compute='_compute_uom', store=True)
    
    price_unit = fields.Float('Precio Unitario', digits='Product Price')
    price_calculation_method = fields.Char('Método Cálculo Precio')
    
    # ========== DESCUENTOS Y CARGOS ==========
    discount_percentage = fields.Float('% Descuento')
    discount_amount = fields.Float('Monto Descuento', digits='Product Price')
    charge_amount = fields.Float('Monto Cargo', digits='Product Price')
    
    # ========== SUBTOTALES ==========
    price_subtotal = fields.Float('Subtotal', digits='Product Price')
    tax_amount = fields.Float('Impuestos', digits='Product Price')
    tax_details = fields.Text('Detalle Impuestos')
    tax_ids = fields.Many2many('account.tax', string='Impuestos Odoo', help='Impuestos extraídos del XML')
    price_total = fields.Float('Total Línea', compute='_compute_total', store=True)
    
    # ========== PARA MANDATOS ==========
    mandatary_partner_id = fields.Many2one('res.partner', 'Tercero Mandato')

    # ========== REFERENCIAS DE ORDEN ==========
    order_line_reference = fields.Char('Referencia Línea OC',
                                      help='Referencia a la línea de orden de compra del proveedor')
    order_reference = fields.Char('Referencia Orden Compra',
                                  help='Orden de compra referenciada en esta línea (si difiere del documento)')

    # ========== INFORMACIÓN DE LOTE Y TRAZABILIDAD ==========
    lot_number = fields.Char('Número de Lote', help='Lote principal (cuando hay un solo lote)')
    expiry_date = fields.Date('Fecha de Vencimiento', help='Fecha de vencimiento (cuando hay un solo lote)')
    lot_ids = fields.One2many('dian.document.processor.lot', 'line_id', string='Lotes',
                             help='Múltiples lotes para esta línea')

    # ========== INFORMACIÓN ADICIONAL ==========
    delivery_date = fields.Date('Fecha Entrega')
    notes = fields.Text('Notas')
    
    # ========== VALIDACIÓN ==========
    has_product_match = fields.Boolean('Producto Identificado', compute='_compute_has_match', store=True)
    match_confidence = fields.Float('Confianza Coincidencia', compute='_compute_match_confidence')

    # ========== UNIFICACIÓN DE LÍNEAS ==========
    is_unified = fields.Boolean('Línea Unificada', default=False,
                                help='Indica si esta línea fue creada al unificar múltiples líneas')
    unified_from_line_ids = fields.Many2many(
        'dian.document.processor.line',
        'dian_line_unification_rel',
        'unified_line_id',
        'original_line_id',
        string='Líneas Originales Unificadas',
        help='Líneas originales que fueron consolidadas en esta línea'
    )
    unified_line_count = fields.Integer('Cantidad de Líneas Unificadas',
                                       compute='_compute_unified_line_count')

    @api.depends('unified_from_line_ids')
    def _compute_unified_line_count(self):
        for line in self:
            line.unified_line_count = len(line.unified_from_line_ids)
    
    @api.depends('price_subtotal', 'tax_amount', 'discount_amount', 'charge_amount')
    def _compute_total(self):
        for line in self:
            line.price_total = line.price_subtotal + line.tax_amount + line.charge_amount - line.discount_amount
    
    @api.depends('product_id')
    def _compute_has_match(self):
        for line in self:
            line.has_product_match = bool(line.product_id)
    
    @api.depends('uom_code')
    def _compute_uom(self):
        """Mapea código UOM DIAN usando UNSPSC, UNECE y fallback manual"""
        UnspscCode = self.env['product.unspsc.code']
        UomUom = self.env['uom.uom']
        default_uom = self.env.ref('uom.product_uom_unit', raise_if_not_found=False)

        # Fallback: mapeo manual para códigos comunes no estándar
        uom_mapping_fallback = {
            '94': 'uom.product_uom_unit',
            'BX': 'uom.product_uom_unit',
            'NIU': 'uom.product_uom_unit',
        }

        for line in self:
            uom_found = False

            if line.uom_code:
                # 1. Buscar via código UNSPSC (más completo para Colombia)
                unspsc = UnspscCode.search([
                    ('code', '=', line.uom_code),
                    ('applies_to', '=', 'uom'),
                    ('active', '=', True)
                ], limit=1)

                if unspsc:
                    uom = UomUom.search([
                        ('unspsc_code_id', '=', unspsc.id)
                    ], limit=1)
                    if uom:
                        line.uom_id = uom
                        uom_found = True

                # 2. Buscar por código UNECE en uom.uom (si tiene el campo)
                if not uom_found and 'unece_code' in UomUom._fields:
                    uom = UomUom.search([
                        ('unece_code', '=', line.uom_code)
                    ], limit=1)
                    if uom:
                        line.uom_id = uom
                        uom_found = True

                # 3. Fallback: mapeo manual
                if not uom_found and line.uom_code in uom_mapping_fallback:
                    uom = self.env.ref(uom_mapping_fallback[line.uom_code], raise_if_not_found=False)
                    if uom:
                        line.uom_id = uom
                        uom_found = True

            # 4. Usar UoM del producto o default
            if not uom_found:
                if line.product_id:
                    line.uom_id = line.product_id.uom_id
                else:
                    line.uom_id = default_uom
    
    @api.depends('product_id', 'product_code', 'product_name')
    def _compute_match_confidence(self):
        """Calcula la confianza de coincidencia del producto"""
        for line in self:
            if not line.product_id:
                line.match_confidence = 0
                continue
            
            confidence = 0
            
            # Coincidencia por código exacto
            if line.product_code and line.product_id.default_code == line.product_code:
                confidence = 100
            # Coincidencia por EAN
            elif line.product_ean and line.product_id.barcode == line.product_ean:
                confidence = 95
            # Coincidencia por código de proveedor
            elif line.product_code and line.processor_id.supplier_id:
                supplier_info = self.env['product.supplierinfo'].search([
                    ('partner_id', '=', line.processor_id.supplier_id.id),
                    ('product_id', '=', line.product_id.id),
                    ('product_code', '=', line.product_code)
                ], limit=1)
                if supplier_info:
                    confidence = 90
            # Coincidencia por nombre
            else:
                import difflib
                if line.product_name and line.product_id.name:
                    matcher = difflib.SequenceMatcher(
                        None, 
                        line.product_name.lower(), 
                        line.product_id.name.lower()
                    )
                    confidence = matcher.ratio() * 100
            
            line.match_confidence = confidence
    
    def find_product(self):
        """Busca y asocia el producto manualmente"""
        self.ensure_one()
        
        # Abrir wizard de búsqueda
        return {
            'type': 'ir.actions.act_window',
            'name': _('Buscar Producto'),
            'res_model': 'dian.document.product.search.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_line_id': self.id,
                'default_search_term': self.product_name or self.product_code,
            }
        }
    
    def create_product(self):
        """Crea un producto nuevo basado en la información de la línea"""
        self.ensure_one()
        
        if self.product_id:
            raise UserError(_("Esta línea ya tiene un producto asociado"))
        
        vals = {
            'name': self.product_name or _('Producto sin nombre'),
            'default_code': self.product_code,
            'barcode': self.product_ean,
            'type': 'product',
            'purchase_ok': True,
            'sale_ok': True,
            'list_price': self.price_unit,
        }
        
        product = self.env['product.product'].create(vals)
        
        # Si hay proveedor, crear información de proveedor
        if self.processor_id.supplier_id:
            self.env['product.supplierinfo'].create({
                'partner_id': self.processor_id.supplier_id.id,
                'product_id': product.id,
                'product_code': self.product_code,
                'product_name': self.product_name,
                'price': self.price_unit,
                'currency_id': self.processor_id.document_currency_id.id,
            })
        
        self.product_id = product
        
        # Mensaje de éxito
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Éxito'),
                'message': _('Producto creado: %s') % product.display_name,
                'type': 'success',
                'sticky': False,
            }
        }


class DianDocumentProcessorTax(models.Model):
    _name = 'dian.document.processor.tax'
    _description = 'Resumen de Impuestos DIAN'
    _order = 'tax_code, id'
    
    processor_id = fields.Many2one('dian.document.processor', required=True, ondelete='cascade')
    
    tax_code = fields.Selection([
        ('01', 'IVA'),
        ('02', 'IC - Impuesto al Consumo'),
        ('03', 'ICA - Industria y Comercio'),
        ('04', 'INC - Impuesto Nacional al Consumo'),
        ('05', 'ReteIVA'),
        ('06', 'ReteFuente'),
        ('07', 'ReteICA'),
        ('08', 'IC Porcentual'),
        ('20', 'FtoHorticultura'),
        ('21', 'Timbre'),
        ('22', 'INC Bolsas'),
        ('23', 'INCarbono'),
        ('24', 'INCombustibles'),
        ('25', 'Sobretasa Combustibles'),
        ('26', 'Sordicom'),
        ('30', 'IC Datos'),
        ('32', 'InVerde'),
        ('33', 'IZC'),
        ('34', 'IBUA'),
        ('35', 'ICUI'),
        ('36', 'IAS'),
        ('ZA', 'IVA e INC'),
        ('ZZ', 'Otro'),
    ], string='Código Impuesto')
    
    tax_name = fields.Char('Nombre')
    tax_base = fields.Float('Base Gravable', digits='Product Price')
    tax_amount = fields.Float('Monto', digits='Product Price')
    tax_percentage = fields.Float('Porcentaje %', digits=(5, 2))
    
    is_withholding = fields.Boolean('Es Retención', compute='_compute_is_withholding', store=True)
    tax_id = fields.Many2one('account.tax', 'Impuesto Odoo')
    
    @api.depends('tax_code')
    def _compute_is_withholding(self):
        withholding_codes = ['05', '06', '07']
        for tax in self:
            tax.is_withholding = tax.tax_code in withholding_codes
    
    def find_odoo_tax(self):
        """Busca y asocia el impuesto de Odoo correspondiente"""
        self.ensure_one()
        
        # Buscar impuesto por porcentaje y tipo
        domain = [
            ('type_tax_use', '=', 'purchase' if self.processor_id._is_purchase() else 'sale'),
            ('amount', '=', self.tax_percentage),
        ]
        
        if self.is_withholding:
            domain.append(('amount', '<', 0))  # Las retenciones son negativas
        
        tax = self.env['account.tax'].search(domain, limit=1)
        
        if tax:
            self.tax_id = tax
        else:
            # Crear impuesto si no existe
            self.create_odoo_tax()
    
    def create_odoo_tax(self):
        """Crea un impuesto en Odoo basado en los datos DIAN"""
        self.ensure_one()
        
        vals = {
            'name': f"{self.tax_name or self.tax_code} {self.tax_percentage}%",
            'amount_type': 'percent',
            'amount': -self.tax_percentage if self.is_withholding else self.tax_percentage,
            'type_tax_use': 'purchase' if self.processor_id._is_purchase() else 'sale',
            'description': self.tax_code,
        }
        
        self.tax_id = self.env['account.tax'].create(vals)


class DianDocumentProcessorAllowance(models.Model):
    _name = 'dian.document.processor.allowance'
    _description = 'Descuentos y Cargos Globales DIAN'
    
    processor_id = fields.Many2one('dian.document.processor', required=True, ondelete='cascade')
    
    type = fields.Selection([
        ('discount', 'Descuento'),
        ('charge', 'Cargo')
    ], required=True)
    
    reason = fields.Char('Motivo')
    reason_code = fields.Char('Código de Motivo')
    amount = fields.Float('Monto', digits='Product Price')
    base_amount = fields.Float('Monto Base', digits='Product Price')
    percentage = fields.Float('Porcentaje', digits=(5, 2))
    
    apply_to_lines = fields.Boolean('Aplicar a Líneas', default=False,
                                   help="Si está marcado, el descuento/cargo se distribuirá entre las líneas")


class DianDocumentProcessorPrepaid(models.Model):
    _name = 'dian.document.processor.prepaid'
    _description = 'Anticipos DIAN'
    
    processor_id = fields.Many2one('dian.document.processor', required=True, ondelete='cascade')
    
    payment_id = fields.Char('ID Pago')
    paid_amount = fields.Float('Monto Pagado', digits='Product Price')
    paid_date = fields.Date('Fecha Pago')
    paid_time = fields.Char('Hora Pago')
    
    instruction_id = fields.Char('ID Instrucción')
    
    # Conversión a moneda local
    paid_amount_local = fields.Float('Monto Pagado (Local)', 
                                    compute='_compute_local_amount',
                                    digits='Product Price')
    
    @api.depends('paid_amount', 'processor_id.exchange_rate')
    def _compute_local_amount(self):
        for prepaid in self:
            if prepaid.processor_id.exchange_rate:
                prepaid.paid_amount_local = prepaid.paid_amount * prepaid.processor_id.exchange_rate
            else:
                prepaid.paid_amount_local = prepaid.paid_amount


class DianDocumentProcessWizard(models.TransientModel):
    _name = 'dian.document.process.wizard'
    _description = 'Asistente Procesamiento DIAN'
    
    input_type = fields.Selection([
        ('cufe', 'CUFE/CUDE'),
        ('xml', 'Archivo XML'),
        ('folder', 'Carpeta con XMLs')
    ], default='cufe', required=True, string="Tipo de Entrada")
    
    cufe = fields.Char('CUFE/CUDE', help="Código único del documento electrónico")
    xml_file = fields.Binary('Archivo XML')
    xml_filename = fields.Char('Nombre Archivo')
    folder_path = fields.Char('Ruta de Carpeta', help="Ruta completa a la carpeta con archivos XML")
    
    # Opciones de procesamiento
    create_product = fields.Boolean('Crear productos faltantes', default=False,
                                   help="Crear automáticamente productos que no existan")
    auto_predict_products = fields.Boolean('Predecir productos automáticamente', default=True,
                                          help="Intentar asociar productos existentes automáticamente")
    update_product_codes = fields.Boolean('Actualizar códigos de productos', default=True,
                                         help="Actualizar códigos de productos y órdenes de compra")
    update_exchange_rate = fields.Boolean('Actualizar tasa de cambio', default=True,
                                         help="Obtener tasa de cambio automáticamente si no está definida")
    
    # Filtros
    date_from = fields.Date('Fecha Desde')
    date_to = fields.Date('Fecha Hasta')
    supplier_id = fields.Many2one('res.partner', 'Proveedor', domain=[('supplier_rank', '>', 0)])
    
    def process_document(self):
        """Procesa el documento según el tipo de entrada"""
        Processor = self.env['dian.document.processor']
        
        context = {
            'create_product': self.create_product,
            'auto_predict_products': self.auto_predict_products,
            'update_product_codes': self.update_product_codes,
            'update_exchange_rate': self.update_exchange_rate,
        }
        
        if self.input_type == 'cufe':
            if not self.cufe:
                raise UserError(_("Ingrese el CUFE/CUDE"))
            
            # Buscar existente
            processor = Processor.search([('cufe', '=', self.cufe)], limit=1)
            if not processor:
                processor = Processor.create({
                    'cufe': self.cufe,
                    'auto_predict_products': self.auto_predict_products,
                    'update_product_codes': self.update_product_codes,
                })
            
            processor.with_context(**context).process_xml()
            
            return self._open_processor(processor)
            
        elif self.input_type == 'xml':
            if not self.xml_file:
                raise UserError(_("Seleccione un archivo XML"))
            
            import base64
            xml_content = base64.b64decode(self.xml_file)
            
            processor = Processor.create({
                'xml_content': xml_content,
                'auto_predict_products': self.auto_predict_products,
                'update_product_codes': self.update_product_codes,
            })
            
            processor.with_context(**context).process_xml()
            
            return self._open_processor(processor)
            
        elif self.input_type == 'folder':
            if not self.folder_path:
                raise UserError(_("Ingrese la ruta de la carpeta"))
            
            # Procesar múltiples archivos
            processed_ids = self._process_folder()
            
            if len(processed_ids) == 1:
                return self._open_processor(self.env['dian.document.processor'].browse(processed_ids[0]))
            else:
                return self._open_processors_list(processed_ids)
    
    def _process_folder(self):
        """Procesa todos los XMLs de una carpeta"""
        import os
        import base64
        
        if not os.path.exists(self.folder_path):
            raise UserError(_("La carpeta especificada no existe"))
        
        processed_ids = []
        errors = []
        
        for filename in os.listdir(self.folder_path):
            if filename.lower().endswith('.xml'):
                filepath = os.path.join(self.folder_path, filename)
                
                try:
                    with open(filepath, 'rb') as f:
                        xml_content = f.read()
                    
                    processor = self.env['dian.document.processor'].create({
                        'xml_content': base64.b64encode(xml_content).decode(),
                        'auto_predict_products': self.auto_predict_products,
                        'update_product_codes': self.update_product_codes,
                    })
                    
                    processor.process_xml()
                    processed_ids.append(processor.id)
                    
                except Exception as e:
                    errors.append(f"{filename}: {str(e)}")
        
        if errors:
            message = _("Se procesaron %d archivos con %d errores:\n%s") % (
                len(processed_ids), len(errors), '\n'.join(errors)
            )
            raise UserError(message)
        
        return processed_ids
    
    def _open_processor(self, processor):
        """Abre un procesador específico"""
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'dian.document.processor',
            'res_id': processor.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def _open_processors_list(self, processor_ids):
        """Abre lista de procesadores"""
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'dian.document.processor',
            'view_mode': 'list,form',
            'domain': [('id', 'in', processor_ids)],
            'target': 'current',
        }


class DianDocumentProductSearchWizard(models.TransientModel):
    _name = 'dian.document.product.search.wizard'
    _description = 'Buscar Producto para Línea DIAN'
    
    line_id = fields.Many2one('dian.document.processor.line', 'Línea', required=True)
    search_term = fields.Char('Buscar', required=True)
    product_ids = fields.Many2many('product.product', string='Productos Encontrados',
                                  compute='_compute_products')
    selected_product_id = fields.Many2one('product.product', 'Producto Seleccionado')
    
    @api.depends('search_term')
    def _compute_products(self):
        for wizard in self:
            if wizard.search_term:
                # Buscar productos
                domain = [
                    '|', '|', '|',
                    ('name', 'ilike', wizard.search_term),
                    ('default_code', 'ilike', wizard.search_term),
                    ('barcode', '=', wizard.search_term),
                    ('product_tmpl_id.name', 'ilike', wizard.search_term)
                ]
                
                wizard.product_ids = self.env['product.product'].search(domain, limit=20)
            else:
                wizard.product_ids = False
    
    def action_confirm(self):
        """Asigna el producto seleccionado a la línea"""
        self.ensure_one()
        
        if not self.selected_product_id:
            raise UserError(_("Seleccione un producto"))
        
        self.line_id.product_id = self.selected_product_id
        
        # Si hay proveedor, crear/actualizar información
        if self.line_id.processor_id.supplier_id and self.line_id.product_code:
            supplier_info = self.env['product.supplierinfo'].search([
                ('partner_id', '=', self.line_id.processor_id.supplier_id.id),
                ('product_id', '=', self.selected_product_id.id)
            ], limit=1)
            
            if not supplier_info:
                self.env['product.supplierinfo'].create({
                    'partner_id': self.line_id.processor_id.supplier_id.id,
                    'product_id': self.selected_product_id.id,
                    'product_code': self.line_id.product_code,
                    'product_name': self.line_id.product_name,
                    'price': self.line_id.price_unit,
                    'currency_id': self.line_id.processor_id.document_currency_id.id,
                })
        
        return {'type': 'ir.actions.act_window_close'}


class ResCompany(models.Model):
    _inherit = 'res.company'

    # Configuración DIAN
    dian_auto_predict_products = fields.Boolean(
        'Predecir Productos Automáticamente',
        default=True,
        help="Intentar asociar productos existentes automáticamente al procesar documentos DIAN"
    )
    dian_auto_update_exchange_rate = fields.Boolean(
        'Actualizar Tasa de Cambio Automáticamente',
        default=True,
        help="Obtener tasa de cambio automáticamente si no está definida"
    )
    dian_create_missing_products = fields.Boolean(
        'Crear Productos Faltantes',
        default=False,
        help="Crear automáticamente productos que no existan al procesar documentos"
    )

    # DIAN Credentials and Configuration
    dian_test_mode = fields.Boolean(
        string='Test Mode',
        default=False,
        help="Enable test mode for DIAN electronic invoicing"
    )
    dian_certificate_file = fields.Binary(
        string='Certificate File',
        help="Upload the DIAN certificate file"
    )
    dian_certificate_filename = fields.Char(
        string='Certificate Filename'
    )
    dian_certificate_password = fields.Char(
        string='Certificate Password',
        help="Password for the DIAN certificate"
    )
    dian_software_id = fields.Char(
        string='Software ID',
        help="DIAN software identification code"
    )
    dian_software_pin = fields.Char(
        string='Software PIN',
        help="DIAN software PIN code"
    )
    dian_test_set_id = fields.Char(
        string='Test Set ID',
        help="DIAN test set identification"
    )
