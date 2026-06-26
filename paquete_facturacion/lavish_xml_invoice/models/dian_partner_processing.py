# -*- coding: utf-8 -*-
import logging
from odoo import models, api, _

_logger = logging.getLogger(__name__)


class DianPartnerProcessingMixin(models.AbstractModel):
    """Mixin para procesamiento de terceros/partners DIAN"""
    _name = 'dian.partner.processing.mixin'
    _description = 'Mixin de Procesamiento de Terceros DIAN'

    def _process_parties(self, document):
        """Procesa información de terceros del documento XML"""
        supplier_party = document.get('cac:AccountingSupplierParty', {})
        customer_party = document.get('cac:AccountingCustomerParty', {})

        _logger.info("=== PROCESANDO PARTIES ===")
        _logger.info(f"Tiene AccountingSupplierParty: {bool(supplier_party)}")
        _logger.info(f"Tiene AccountingCustomerParty: {bool(customer_party)}")

        company_vat = self.env.company.vat
        company_vat_co = self.env.company.vat_co if hasattr(self.env.company, 'vat_co') else None

        _logger.info(f"VAT empresa: {company_vat}, VAT_CO: {company_vat_co}")

        is_purchase_doc = self.document_type == '05'

        supplier_vat = None
        if not is_purchase_doc and (company_vat or company_vat_co):
            if supplier_party:
                party = supplier_party.get('cac:Party', {})
                party_tax = party.get('cac:PartyTaxScheme', {})
                if not isinstance(party_tax, list):
                    party_tax = [party_tax] if party_tax else []
                for tax_scheme in party_tax:
                    company_id = tax_scheme.get('cbc:CompanyID')
                    if company_id:
                        supplier_vat = ''.join(filter(str.isalnum, self._get_value(company_id)))
                        break

            _logger.info(f"VAT emisor: {supplier_vat}")

            company_vat_clean = ''.join(filter(str.isalnum, company_vat)) if company_vat else None
            company_vat_co_clean = ''.join(filter(str.isalnum, company_vat_co)) if company_vat_co else None

            if supplier_vat:
                is_our_vat = (company_vat_clean and supplier_vat == company_vat_clean) or \
                            (company_vat_co_clean and supplier_vat == company_vat_co_clean)

                _logger.info(f"Emisor somos nosotros: {is_our_vat}")

                if not is_our_vat:
                    is_purchase_doc = True

        _logger.info(f"DECISIÓN: {'COMPRA' if is_purchase_doc else 'VENTA'}")

        if is_purchase_doc:
            _logger.info(f">>> Procesando COMPRA - Tipo: {self.document_type}")
            if supplier_party:
                supplier = self._get_or_create_partner(supplier_party, is_supplier=True)
                if supplier:
                    self.supplier_id = supplier.id
                    _logger.info(f"Proveedor asignado: {supplier.name} (ID: {supplier.id})")
        else:
            _logger.info(f">>> Procesando VENTA - Tipo: {self.document_type}")
            if customer_party:
                customer = self._get_or_create_partner(customer_party, is_customer=True)
                if customer:
                    self.customer_id = customer.id
                    _logger.info(f"Cliente asignado: {customer.name} (ID: {customer.id})")
            elif supplier_party:
                _logger.warning("FALLBACK: Usando SupplierParty como cliente")
                customer = self._get_or_create_partner(supplier_party, is_customer=True)
                if customer:
                    self.customer_id = customer.id

        _logger.info(f"=== RESULTADO: supplier={self.supplier_id.id if self.supplier_id else None}, customer={self.customer_id.id if self.customer_id else None} ===")

        if hasattr(self, '_chatter_messages') and self._chatter_messages:
            for msg in self._chatter_messages:
                self.message_post(body=msg)
            self._chatter_messages = []

        delivery_party = document.get('cac:Delivery', {}).get('cac:DeliveryParty', {})
        if delivery_party:
            partner = self._get_or_create_partner({'cac:Party': delivery_party})
            if partner:
                self.delivery_partner_id = partner.id

        payee_party = document.get('cac:PayeeParty', {})
        if payee_party:
            payee = self._get_or_create_partner({'cac:Party': payee_party})
            if payee:
                self.payee_partner_id = payee.id
                _logger.info(f"Beneficiario asignado: {payee.name}")

        delivery = document.get('cac:Delivery', {})
        if delivery:
            shipment = delivery.get('cac:Shipment', {})
            if shipment:
                consignment = shipment.get('cac:Consignment', {})
                carrier_party = consignment.get('cac:CarrierParty', {})
                if carrier_party:
                    carrier = self._get_or_create_partner({'cac:Party': carrier_party})
                    if carrier:
                        self.carrier_partner_id = carrier.id
                        _logger.info(f"Transportista asignado: {carrier.name}")

    def _extract_partner_dict_from_xml(self, party):
        """Extrae datos del partner del XML"""
        partner_dict = {'country_code': 'CO'}

        party_tax_schemes = party.get('cac:PartyTaxScheme', {})
        if not isinstance(party_tax_schemes, list):
            party_tax_schemes = [party_tax_schemes] if party_tax_schemes else []

        for tax_scheme in party_tax_schemes:
            company_id = tax_scheme.get('cbc:CompanyID')
            if company_id:
                vat = self._get_value(company_id)
                if vat:
                    partner_dict['vat'] = ''.join(filter(str.isalnum, str(vat)))
                    break

        party_name = party.get('cac:PartyName', {})
        party_legal = party.get('cac:PartyLegalEntity', [])
        if not isinstance(party_legal, list):
            party_legal = [party_legal] if party_legal else []

        if party_legal:
            partner_dict['name'] = self._get_value(party_legal[0].get('cbc:RegistrationName'))
        if not partner_dict.get('name') and party_name:
            partner_dict['name'] = self._get_value(party_name.get('cbc:Name'))

        contact = party.get('cac:Contact', {})
        if contact:
            email = self._get_value(contact.get('cbc:ElectronicMail'))
            phone = self._get_value(contact.get('cbc:Telephone'))
            if email:
                partner_dict['email'] = email
            if phone:
                partner_dict['phone'] = phone

        address = party.get('cac:PartyPhysicalLocation', {}).get('cac:Address', {})
        if not address:
            address = party.get('cac:PartyPostalAddress', {})

        if address:
            country_code = self._get_value(address.get('cac:Country', {}).get('cbc:IdentificationCode'))
            if country_code:
                partner_dict['country_code'] = country_code

            state_code = self._get_value(address.get('cbc:CountrySubentityCode'))
            if state_code:
                partner_dict['state_code'] = state_code

        return partner_dict

    def _get_or_create_partner(self, party_data, is_supplier=False, is_customer=False):
        """Obtiene o crea un partner basado en los datos del XML"""
        party = party_data.get('cac:Party', {})
        if not party:
            _logger.warning("No se encontró información de Party")
            return self.env['res.partner']

        partner_dict = self._extract_partner_dict_from_xml(party)
        chatter_msg = []

        _logger.info(f"Buscando partner VAT: {partner_dict.get('vat')}, supplier={is_supplier}, customer={is_customer}")

        partner_type = 'supplier' if is_supplier else ('customer' if is_customer else False)
        partner = self._match_partner(
            partner_dict,
            chatter_msg,
            partner_type=partner_type,
            raise_exception=False
        )

        if partner:
            # Si el XML trae VAT, exigir coincidencia exacta para evitar falsos positivos por nombre/email
            vat_clean = (partner_dict.get('vat') or '').replace(' ', '').replace('-', '').upper()
            if vat_clean:
                partner_vat = partner.vat_co or partner.vat or ''
                partner_vat_clean = ''.join(filter(str.isalnum, partner_vat)).upper()
                if partner_vat_clean and partner_vat_clean != vat_clean:
                    _logger.warning(
                        "Partner encontrado por heurística no coincide con VAT del XML. "
                        "XML VAT=%s vs Partner VAT=%s. Se ignorará el match.",
                        vat_clean,
                        partner_vat_clean,
                    )
                    partner = False
            if partner:
                _logger.info(f"Partner encontrado: {partner.name} (ID: {partner.id})")
                return partner

        vat_clean = partner_dict.get('vat')
        if vat_clean and 'vat_co' in self.env['res.partner']._fields:
            partner = self.env['res.partner'].search([('vat_co', '=', vat_clean)], limit=1)
            if partner:
                _logger.info(f"Partner por VAT_CO: {partner.name}")
                return partner

        _logger.info(f"Creando partner con VAT: {vat_clean}")

        if not partner:
            party_name_data = party.get('cac:PartyName', {})
            party_legal_data = party.get('cac:PartyLegalEntity', [])
            if not isinstance(party_legal_data, list):
                party_legal_data = [party_legal_data] if party_legal_data else []

            name = None
            legal_name = None
            if party_legal_data:
                legal_name = self._get_value(party_legal_data[0].get('cbc:RegistrationName'))
                name = legal_name
            if not name and party_name_data:
                name = self._get_value(party_name_data.get('cbc:Name'))
            if not name:
                name = f'Partner {vat_clean}' if vat_clean else _('Partner sin nombre')

            name_value = name if name and name != '' else f'Partner {vat_clean}' if vat_clean else _('Partner sin nombre')

            address_data = party.get('cac:PartyPhysicalLocation', {}).get('cac:Address', {})
            if not address_data:
                address_data = party.get('cac:PartyPostalAddress', {})

            vals = {
                'name': name_value,
                'vat': vat_clean if vat_clean else False,
                'supplier_rank': 1 if is_supplier else 0,
                'customer_rank': 1 if is_customer else 0,
                'country_id': self.env.ref('base.co').id,
            }

            if vat_clean and 'vat_co' in self.env['res.partner']._fields:
                vals['vat_co'] = vat_clean

            if legal_name and legal_name != name_value:
                vals['legal_name'] = legal_name

            _logger.info(f"Creando: {name_value} (Razón social: {legal_name})")

            if address_data:
                street = None
                address_line = address_data.get('cac:AddressLine')
                if address_line:
                    if isinstance(address_line, list):
                        street = ' '.join([self._get_value(line.get('cbc:Line')) for line in address_line if line.get('cbc:Line')])
                    else:
                        street = self._get_value(address_line.get('cbc:Line'))

                if not street:
                    street = self._get_value(address_data.get('cbc:StreetName'))

                if street:
                    vals['street'] = street

                zip_code = self._get_value(address_data.get('cbc:PostalZone'))
                if zip_code:
                    vals['zip'] = zip_code

                country_code = self._get_value(address_data.get('cac:Country', {}).get('cbc:IdentificationCode'))
                if country_code:
                    country = self.env['res.country'].search([('code', '=', country_code)], limit=1)
                    if country:
                        vals['country_id'] = country.id

                city_code = self._get_value(address_data.get('cbc:ID'))
                city_name = self._get_value(address_data.get('cbc:CityName'))
                state_code = self._get_value(address_data.get('cbc:CountrySubentityCode'))
                state_name = self._get_value(address_data.get('cbc:CountrySubentity'))

                if city_code and vals.get('country_id'):
                    city = self.env['res.city'].search([
                        ('code', '=', city_code),
                        ('country_id', '=', vals['country_id'])
                    ], limit=1)

                    if city:
                        vals['city_id'] = city.id
                        vals['city'] = city.name
                        if city.state_id:
                            vals['state_id'] = city.state_id.id
                        _logger.info(f"Ciudad: {city.name}")
                    elif city_name:
                        city = self.env['res.city'].search([
                            ('name', 'ilike', city_name),
                            ('country_id', '=', vals['country_id'])
                        ], limit=1)
                        if city:
                            vals['city_id'] = city.id
                            vals['city'] = city.name
                            if city.state_id:
                                vals['state_id'] = city.state_id.id
                        else:
                            vals['city'] = city_name

                if not vals.get('state_id') and state_code and vals.get('country_id'):
                    state = self.env['res.country.state'].search([
                        ('code', '=', state_code),
                        ('country_id', '=', vals['country_id'])
                    ], limit=1)
                    if state:
                        vals['state_id'] = state.id
                    elif state_name:
                        state = self.env['res.country.state'].search([
                            ('name', 'ilike', state_name),
                            ('country_id', '=', vals['country_id'])
                        ], limit=1)
                        if state:
                            vals['state_id'] = state.id

            contact = party.get('cac:Contact', {})
            if contact:
                phone = self._get_value(contact.get('cbc:Telephone'))
                mobile = self._get_value(contact.get('cbc:Telefax'))
                email = self._get_value(contact.get('cbc:ElectronicMail'))

                if phone:
                    vals['phone'] = phone
                if mobile:
                    vals['mobile'] = mobile
                if email:
                    vals['email'] = email

            tax_scheme_list = party.get('cac:PartyTaxScheme', [])
            if not isinstance(tax_scheme_list, list):
                tax_scheme_list = [tax_scheme_list] if tax_scheme_list else []

            fiscal_responsibilities = []
            for tax_scheme in tax_scheme_list:
                tax_level_code = self._get_value(tax_scheme.get('cbc:TaxLevelCode'))
                if tax_level_code:
                    fiscal_responsibilities.append(tax_level_code)

            fiscal_field = None
            if 'dian_fiscal_regimen' in self.env['res.partner']._fields:
                fiscal_field = 'dian_fiscal_regimen'
            elif 'l10n_co_edi_fiscal_regimen' in self.env['res.partner']._fields:
                fiscal_field = 'l10n_co_edi_fiscal_regimen'

            if fiscal_responsibilities and fiscal_field:
                regimen_map = {
                    'R-99-PN': '49',
                    'O-13': '48',
                    'O-15': '49',
                    'O-23': '48',
                    'O-47': '49',
                }

                for resp_code in fiscal_responsibilities:
                    if resp_code in regimen_map:
                        vals[fiscal_field] = regimen_map[resp_code]
                        break

            person_type = self._get_value(party.get('cbc:AdditionalAccountID'))
            if person_type and 'company_type' in self.env['res.partner']._fields:
                vals['company_type'] = 'company' if person_type == '1' else 'person'

            try:
                partner = self.env['res.partner'].create(vals)
                _logger.info(f"Partner creado: {partner.name} (ID: {partner.id})")
            except Exception as e:
                _logger.error(f"Error creando partner: {str(e)}")
                _logger.error(f"Valores: {vals}")
                raise

        return partner
