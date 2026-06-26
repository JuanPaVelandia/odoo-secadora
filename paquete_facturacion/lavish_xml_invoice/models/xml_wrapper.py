# -*- coding: utf-8 -*-
"""
XML Wrapper - Clase para facilitar el acceso a datos del XML DIAN
Convierte el diccionario XML en un objeto más fácil de manipular
"""

import logging

_logger = logging.getLogger(__name__)


class XMLWrapper:
    """Envuelve un diccionario XML para facilitar el acceso a sus datos"""

    def __init__(self, data):
        self._data = data if data else {}

    def get_value(self, data=None):
        """Extrae el valor de un elemento XML que puede ser dict o string"""
        if data is None:
            data = self._data

        if isinstance(data, dict):
            return data.get('#text', '')
        return data or ''

    def get(self, key, default=None):
        """Obtiene un valor del diccionario"""
        return self._data.get(key, default)

    def get_text(self, key, default=''):
        """Obtiene el texto de un elemento"""
        value = self._data.get(key, default)
        return self.get_value(value)

    def get_attr(self, key, attr_name, default=''):
        """Obtiene un atributo de un elemento"""
        element = self._data.get(key, {})
        if isinstance(element, dict):
            return element.get(f'@{attr_name}', default)
        return default

    def get_list(self, key):
        """Asegura que un elemento sea una lista"""
        value = self._data.get(key, [])
        if not isinstance(value, list):
            return [value] if value else []
        return value

    def get_wrapper(self, key):
        """Obtiene un sub-elemento envuelto en XMLWrapper"""
        value = self._data.get(key, {})
        return XMLWrapper(value)

    def get_wrappers(self, key):
        """Obtiene una lista de sub-elementos envueltos"""
        items = self.get_list(key)
        return [XMLWrapper(item) for item in items]

    def has(self, key):
        """Verifica si existe una clave"""
        return key in self._data

    def to_dict(self):
        """Retorna el diccionario original"""
        return self._data


class InvoiceWrapper(XMLWrapper):
    """Wrapper específico para facturas DIAN"""

    @property
    def document_number(self):
        return self.get_text('cbc:ID')

    @property
    def cufe(self):
        return self.get_text('cbc:UUID')

    @property
    def issue_date(self):
        return self.get_text('cbc:IssueDate')

    @property
    def invoice_type_code(self):
        return self.get_text('cbc:InvoiceTypeCode')

    @property
    def currency_code(self):
        return self.get_text('cbc:DocumentCurrencyCode', 'COP')

    @property
    def order_reference(self):
        """Orden de compra del documento"""
        order_ref = self.get_wrapper('cac:OrderReference')
        return order_ref.get_text('cbc:ID')

    @property
    def supplier_party(self):
        """AccountingSupplierParty"""
        return self.get_wrapper('cac:AccountingSupplierParty').get_wrapper('cac:Party')

    @property
    def customer_party(self):
        """AccountingCustomerParty"""
        return self.get_wrapper('cac:AccountingCustomerParty').get_wrapper('cac:Party')

    @property
    def payee_party(self):
        """Beneficiario/Mandato"""
        return self.get_wrapper('cac:PayeeParty').get_wrapper('cac:Party')

    @property
    def payment_means(self):
        """Medio de pago"""
        return self.get_wrapper('cac:PaymentMeans')

    @property
    def lines(self):
        """Líneas de la factura"""
        items = self.get_list('cac:InvoiceLine')
        return [InvoiceLineWrapper(item) for item in items]

    @property
    def tax_totals(self):
        """Resumen de impuestos"""
        return self.get_wrappers('cac:TaxTotal')

    @property
    def legal_monetary_total(self):
        """Totales monetarios"""
        return self.get_wrapper('cac:LegalMonetaryTotal')


class InvoiceLineWrapper(XMLWrapper):
    """Wrapper específico para líneas de factura"""

    @property
    def sequence(self):
        return int(self.get_text('cbc:ID', '1'))

    @property
    def quantity(self):
        qty_data = self.get('cbc:InvoicedQuantity', {})
        return float(self.get_value(qty_data) or 0)

    @property
    def uom_code(self):
        qty_data = self.get('cbc:InvoicedQuantity', {})
        if isinstance(qty_data, dict):
            return qty_data.get('@unitCode')
        return None

    @property
    def line_extension_amount(self):
        return float(self.get_text('cbc:LineExtensionAmount', '0'))

    @property
    def item(self):
        """Item de la línea"""
        return ItemWrapper(self.get('cac:Item', {}))

    @property
    def price(self):
        """Precio"""
        price_data = self.get_wrapper('cac:Price')
        return float(price_data.get_text('cbc:PriceAmount', '0'))

    @property
    def allowances(self):
        """Descuentos/Cargos"""
        return self.get_wrappers('cac:AllowanceCharge')

    @property
    def tax_total(self):
        """Impuestos de la línea"""
        return self.get_wrapper('cac:TaxTotal')

    @property
    def order_line_reference(self):
        """Referencia a orden de compra"""
        return self.get_wrapper('cac:OrderLineReference')


class ItemWrapper(XMLWrapper):
    """Wrapper para información del producto"""

    @property
    def description(self):
        return self.get_text('cbc:Description')

    @property
    def seller_code(self):
        seller_id = self.get_wrapper('cac:SellersItemIdentification')
        return seller_id.get_text('cbc:ID')

    @property
    def standard_code(self):
        """Código estándar (EAN)"""
        std_id = self.get_wrapper('cac:StandardItemIdentification')
        return std_id.get_text('cbc:ID')

    @property
    def lots(self):
        """Información de lotes"""
        instance = self.get_wrapper('cac:ItemInstance')
        if not instance.has('cac:LotIdentification'):
            return []

        # Puede ser un solo lote o múltiples
        lot_data = instance.get('cac:LotIdentification')
        if isinstance(lot_data, list):
            return [LotWrapper(lot) for lot in lot_data]
        else:
            return [LotWrapper(lot_data)] if lot_data else []

    @property
    def additional_properties(self):
        """Propiedades adicionales del item"""
        return self.get_wrappers('cac:AdditionalItemProperty')


class LotWrapper(XMLWrapper):
    """Wrapper para información de lote"""

    @property
    def lot_number(self):
        return self.get_text('cbc:LotNumberID')

    @property
    def expiry_date(self):
        return self.get_text('cbc:ExpiryDate')

    @property
    def quantity(self):
        """Si el lote tiene cantidad específica"""
        return float(self.get_text('cbc:Quantity', '0'))


class PartyWrapper(XMLWrapper):
    """Wrapper para información de terceros"""

    @property
    def identification(self):
        """ID del tercero"""
        party_id = self.get('cac:PartyIdentification', {})
        if isinstance(party_id, list):
            party_id = party_id[0] if party_id else {}

        return XMLWrapper(party_id).get_text('cbc:ID')

    @property
    def name(self):
        """Nombre legal del tercero"""
        legal = self.get('cac:PartyLegalEntity', {})
        if isinstance(legal, list):
            legal = legal[0] if legal else {}

        return XMLWrapper(legal).get_text('cbc:RegistrationName')

    @property
    def vat(self):
        """NIT del tercero"""
        tax_scheme = self.get('cac:PartyTaxScheme', {})
        if isinstance(tax_scheme, list):
            tax_scheme = tax_scheme[0] if tax_scheme else {}

        return XMLWrapper(tax_scheme).get_text('cbc:CompanyID')
