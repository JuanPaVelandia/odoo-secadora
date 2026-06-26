# -*- coding: utf-8 -*-
import asyncio
import json
import logging
import os
import re
from datetime import datetime

import requests
import stdnum
from lxml import etree
from pytz import country_names
from stdnum.co.nit import calc_check_digit, compact, format, is_valid, validate

from odoo import SUPERUSER_ID, _, api, exceptions, fields, models
from odoo.exceptions import RedirectWarning, UserError, ValidationError

_logger = logging.getLogger(__name__)
import re

# Utilidad para dividir nombres completos
from odoo.addons.lavish_erp.utils.name_parser import (split_nombre_completo,
                                                      split_nombre_hispano)
from odoo.tools.sql import column_exists, create_column

#---------------------------Modelo RES-PARTNER / TERCEROS-------------------------------#
# Tipo de Contribuyente - Basado en códigos World Office
REGIMEN_TRIBUTATE = [
    ("1", "Todos"),
    ("2", "Persona Natural Responsable del IVA"),
    ("3", "Persona Jurídica"),
    ("4", "Grande Contribuyente No Autorretenedor"),
    ("5", "Grande Contribuyente Autorretenedor"),
    ("6", "Persona Natural No Responsable del IVA"),
    ("7", "Persona Jurídica Autorretenedor"),
    ("8", "Persona Natural Autorretenedor"),
    ("9", "Tercero del Exterior"),
    ("10", "Proveedor Sociedades de Comercio Internacional"),
    ("11", "Entidades Sin Ánimo De Lucro"),
    ("13", "Persona Natural Responsable del IVA Agente Retenedor"),
    ("14", "Persona Natural o Jurídica Ley 1429"),
    ("15", "Instituciones del Estado Públicos y Otros"),
    ("16", "Régimen Simple de Tributación Persona Jurídica"),
    ("17", "Régimen Simple de Tributación Persona Natural"),
]

# Clasificación DIAN
class_dian = [
    ("1", "Normal"),
    ("2", "Exportador"),
    ("3", "Importador"),
    ("4", "Autorretenedor"),
    ("5", "Agente de Retención"),
    ("6", "Gran Contribuyente"),
    ("7", "Tercero en Zona Franca"),
    ("8", "Importador en Zona Franca"),
    ("9", "Excluidos"),
]

PERSON_TYPE = [("1", "Persona Natural"), ("2", "Persona Jurídica")]

TYPE_COMPANY = [("person", "Persona Natural"), ("company", "Persona Jurídica")]
class ResPartnerBank(models.Model):
    _inherit = 'res.partner.bank'

    type_account = fields.Selection([('A', 'Ahorros'), ('C', 'Corriente')], 'Tipo de Cuenta', required=True, default='A')
    is_main = fields.Boolean('Es Principal')
    
class ResPartner(models.Model):
    _inherit = 'res.partner'
    _order = 'name'
    _rec_names_search = ['complete_name', 'email', 'ref', 'vat', 'company_registry','business_name']  # TODO vat must be sanitized the same way for storing/searching
    #TRACK VISIBILITY OLD FIELDS
    vat = fields.Char(tracking=True)
    street = fields.Char(tracking=True)
    country_id = fields.Many2one(tracking=True)
    state_id = fields.Many2one(tracking=True)
    zip = fields.Char(tracking=True)

    # Campos relacionados de configuración del país
    country_address_builder = fields.Boolean(
        related='country_id.address_builder_enabled',
        string='Constructor Direcciones Habilitado'
    )
    country_neighborhood_enabled = fields.Boolean(
        related='country_id.neighborhood_enabled',
        string='Barrios Habilitados'
    )
    country_zip_required = fields.Boolean(
        related='country_id.zip_required',
        string='CP Obligatorio'
    )

    postal_code_id = fields.Many2one(
        'res.city.postal',
        string='Codigo Postal',
        tracking=True,
        domain="[('city_id', '=', city_id)]",
        help='Seleccione el codigo postal correspondiente a la ciudad'
    )

    # ========== CAMPOS DE DIRECCIÓN ESTRUCTURADA COLOMBIANA ==========
    # Barrio (primer componente según estándar DANE/DIAN)
    neighborhood_id = fields.Many2one(
        'res.city.neighborhood',
        string='Barrio',
        domain="[('city_id', '=', city_id)]",
        help='Barrio o sector (primer componente de la dirección)'
    )
    barrio = fields.Char(
        string='Nombre Barrio',
        help='Nombre del barrio (se puede escribir directamente)'
    )

    # Vía Principal
    main_road = fields.Many2one(
        'account.nomenclature.code',
        string='Vía Principal',
        domain="[('type_code', '=', 'principal')]",
        help='Tipo de vía (ej: CALLE, CARRERA, AVENIDA)'
    )
    name_road = fields.Char(
        string='Número de Vía',
        help='Número o nombre de la vía principal (ej: 45, 26, etc)'
    )
    main_letter_road = fields.Many2one(
        'account.nomenclature.code',
        string='Letra Vía Principal',
        domain="[('type_code', '=', 'letter')]",
        help='Letra complementaria de la vía (ej: A, B, C)'
    )
    prefix_main_road = fields.Many2one(
        'account.nomenclature.code',
        string='Prefijo Vía Principal',
        domain="[('type_code', '=', 'qualifying'), ('abbreviation', '=', 'BIS')]",
        help='Prefijo BIS de la vía principal'
    )
    sector_main_road = fields.Many2one(
        'account.nomenclature.code',
        string='Sector Vía Principal',
        domain="[('type_code', '=', 'qualifying'), ('abbreviation', 'in', ['NORTE', 'SUR', 'ESTE', 'OESTE'])]",
        help='Sector cardinal de la vía (NORTE, SUR, ESTE, OESTE)'
    )

    # Vía Generadora (después del #)
    generator_road_number = fields.Integer(
        string='Número Generadora',
        help='Número de la vía generadora (después del #)'
    )
    generator_road_letter = fields.Many2one(
        'account.nomenclature.code',
        string='Letra Generadora',
        domain="[('type_code', '=', 'letter')]",
        help='Letra de la vía generadora'
    )
    generator_road_sector = fields.Many2one(
        'account.nomenclature.code',
        string='Sector Generadora',
        domain="[('type_code', '=', 'qualifying'), ('abbreviation', 'in', ['NORTE', 'SUR', 'ESTE', 'OESTE'])]",
        help='Sector cardinal de la generadora'
    )

    # Placa (después del -)
    generator_plate_number = fields.Integer(
        string='Número Placa',
        help='Número de placa (después del -)'
    )
    generator_plate_sector = fields.Many2one(
        'account.nomenclature.code',
        string='Sector Placa',
        domain="[('type_code', '=', 'qualifying'), ('abbreviation', 'in', ['NORTE', 'SUR', 'ESTE', 'OESTE'])]",
        help='Sector cardinal de la placa'
    )

    # Complementos
    complement_name_a = fields.Many2one(
        'account.nomenclature.code',
        string='Complemento A',
        domain="[('type_code', '=', 'additional')]",
        help='Tipo de complemento (ej: APARTAMENTO, TORRE, PISO)'
    )
    complement_number_a = fields.Char(
        string='Número Complemento A',
        help='Número o valor del complemento A'
    )
    complement_name_b = fields.Many2one(
        'account.nomenclature.code',
        string='Complemento B',
        domain="[('type_code', '=', 'additional')]",
        help='Segundo complemento'
    )
    complement_number_b = fields.Char(
        string='Número Complemento B',
        help='Número o valor del complemento B'
    )
    complement_name_c = fields.Many2one(
        'account.nomenclature.code',
        string='Complemento C',
        domain="[('type_code', '=', 'additional')]",
        help='Tercer complemento'
    )
    complement_text_c = fields.Char(
        string='Texto Complemento C',
        help='Texto libre para complemento adicional'
    )

    # Campo computado para dirección completa con ciudad
    full_address = fields.Char(
        string='Dirección Completa',
        compute='compute_full_address',
        store=True,
        help='Dirección completa incluyendo ciudad y país'
    )
    full_address_2 = fields.Char(
        string='Ciudad Completa',
        compute='_compute_full_city',
        store=True,
        help='País - Departamento - Ciudad'
    )
    # ========== FIN CAMPOS DE DIRECCIÓN ESTRUCTURADA ==========

    phone = fields.Char(tracking=True)
    mobile = fields.Char(tracking=True)
    email = fields.Char(tracking=True)
    website = fields.Char(tracking=True)
    lang = fields.Selection(tracking=True)
    category_id = fields.Many2many(tracking=True)
    user_id = fields.Many2one(tracking=True)    
    comment = fields.Text(tracking=True)
    name = fields.Char(tracking=True)
    city = fields.Char(string='Descripción ciudad')
    dv = fields.Char(
        string='DV',
        compute='_compute_dv',
        store=True,
    )
    #INFORMACION BASICA
    x_pn_retri = fields.Selection(REGIMEN_TRIBUTATE, string="Tipo de Contribuyente", default="3")
    class_dian = fields.Selection(class_dian, string="Clasificacion Dian", default="1")
    personType = fields.Selection(PERSON_TYPE, "Tipo de persona", default="1")
    company_type = fields.Selection(TYPE_COMPANY, string="Company Type")

    formatedNit = fields.Char(
        string="NIT Formatted",store=True
    )

    @api.model
    def _default_identification_type_co(self):
        """Default CO identification type: NIT (document code 'rut')."""
        nit = self.env['l10n_latam.identification.type'].search([
            ('l10n_co_document_code', '=', 'rut')
        ], limit=1)
        if nit:
            return nit
        return self.env['l10n_latam.identification.type'].search([
            ('dian_code', '=', '31')
        ], limit=1)

    @api.onchange('country_id')
    def _onchange_country_id(self):
        super()._onchange_country_id()
        co = self.env.ref('base.co', raise_if_not_found=False)
        nit = self._default_identification_type_co()
        if not co or not nit:
            return
        for partner in self:
            if partner.country_id and partner.country_id.id == co.id:
                partner.l10n_latam_identification_type_id = nit

    l10n_latam_identification_type_id = fields.Many2one(
        default=lambda self: self._default_identification_type_co()
    )
    vat_co = fields.Char(
        string="Numero RUT/NIT/CC",
    )
    vat_ref = fields.Char(
        string='NIT Formateado',
        compute='_compute_vat_ref',
        store=True,
    )
    vat_vd = fields.Char(
        string=u"Digito Verificación", size=1, tracking=True
    )
    # Campo deprecado - mantener por compatibilidad
    ciiu_id = fields.Many2one(
        string='Actividad CIIU Principal',
        comodel_name='lavish.ciiu',
        help=u'Actividad económica principal (campo legacy)'
    )

    taxes_ids = fields.Many2many(
        string="Customer taxes",
        comodel_name="account.tax",
        relation="partner_tax_sale_rel",
        column1="partner_id",
        column2="tax_id",
        domain="[('type_tax_use','=','sale')]",
        help="Taxes applied for sale.",
    )
    supplier_taxes_ids =  fields.Many2many(
        string="Supplier taxes",
        comodel_name="account.tax",
        relation="partner_tax_purchase_rel",
        column1="partner_id",
        column2="tax_id",
        domain="[('type_tax_use','=','purchase')]",
        help="Taxes applied for purchase.",
    )
    country_id = fields.Many2one('res.country', string='Country', ondelete='restrict', default=lambda self: self.env.company.country_id.id)
    business_name = fields.Char(string='Nombre Comercial', tracking=True)
    first_name = fields.Char(string='Primer nombre', tracking=True, compute=False)
    second_name = fields.Char(string='Segundo nombre', tracking=True)
    first_lastname = fields.Char(string='Primer apellido', tracking=True)
    second_lastname = fields.Char(string='Segundo apellido', tracking=True)
    is_ica = fields.Boolean(string='Aplicar ICA', tracking=True)
    # CIIU - Multiple actividades economicas (RUT puede tener varias)
    ciiu_ids = fields.Many2many(
        comodel_name='lavish.ciiu',
        relation='res_partner_ciiu_rel',
        column1='partner_id',
        column2='ciiu_id',
        string='Actividades Economicas CIIU',
        tracking=True,
        help=u'Códigos CIIU - Actividades económicas registradas en el RUT. Puede seleccionar múltiples actividades.'
    )
    #GRUPO EMPRESARIAL
    is_business_group = fields.Boolean(string='¿Es un Grupo Empresarial?', tracking=True)
    name_business_group = fields.Char(string='Nombre Grupo Empresarial', tracking=True)

    acceptance_data_policy = fields.Boolean(string='Acepta política de tratamiento de datos', tracking=True)
    acceptance_date = fields.Date(string='Fecha de aceptación', tracking=True)
    not_contacted_again = fields.Boolean(string='No volver a ser contactado', tracking=True)
    date_decoupling = fields.Date(string="Fecha de desvinculación", tracking=True)
    reason_desvinculation_text = fields.Text(string='Motivo desvinculación') 
    
    #INFORMACION FINANCIERA
    company_size = fields.Selection([   ('1', 'Mipyme'),
                                        ('2', 'Pyme'),
                                        ('3', 'Mediana'),
                                        ('4', 'Grande')
                                    ], string='Tamaño empresa', tracking=True)

    #INFORMACION FACTURACION ELECTRÓNICA
    email_invoice_electronic = fields.Char(string='Correo electrónico para recepción electrónica de facturas', tracking=True)

    def _auto_init(self):
        """
        Create compute stored fields dv and vat_ref
        here to avoid MemoryError on large databases.
        """
        if not column_exists(self.env.cr, 'res_partner', 'dv'):
            create_column(self.env.cr, 'res_partner', 'dv', 'varchar')
            _logger.info('Created column dv in res_partner')
        if not column_exists(self.env.cr, 'res_partner', 'vat_ref'):
            create_column(self.env.cr, 'res_partner', 'vat_ref', 'varchar')
            _logger.info('Created column vat_ref in res_partner')
        return super()._auto_init()




    @api.model
    def _names_order_default(self):
        return "first_last"

    @api.model
    def _get_names_order(self):
        """Get names order configuration from system parameters.
        You can override this method to read configuration from language,
        country, company or other"""
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("partner_names_order", self._names_order_default())
        )
        
        
    @api.depends('vat')
    def _compute_no_same_vat_partner_id(self):
        for partner in self:
            partner.same_vat_partner_id = ""
    
    def _address_fields(self):
        result = super(ResPartner, self)._address_fields()
        result = result + ['city_id', 'postal_code_id']
        return result

    # ========== MÉTODOS PARA DIRECCIÓN ESTRUCTURADA COLOMBIANA ==========

    # Constante con los campos de dirección estructurada
    ADDRESS_FIELDS = [
        'neighborhood_id', 'barrio',
        'main_road', 'name_road', 'main_letter_road', 'prefix_main_road', 'sector_main_road',
        'generator_road_number', 'generator_road_letter', 'generator_road_sector',
        'generator_plate_number', 'generator_plate_sector',
        'complement_name_a', 'complement_number_a',
        'complement_name_b', 'complement_number_b',
        'complement_name_c', 'complement_text_c'
    ]

    @api.model
    def _address_dependencies(self):
        """Retorna la lista de campos de dirección para @api.depends"""
        return self.ADDRESS_FIELDS

    def _build_native_address(self):
        """
        Construye la dirección en formato colombiano estándar DIAN
        Formato: CALLE 45 A BIS NORTE No. 23 A SUR - 15 ESTE APARTAMENTO 302
        Usa nombres COMPLETOS (no abreviaturas) y retorna en MAYÚSCULAS
        """
        self.ensure_one()

        # Vía Principal: "CALLE 45 A BIS NORTE"
        main_parts = []
        if self.main_road:
            main_parts.append(self.main_road.name)  # Nombre completo: "CALLE" no "CL"
        if self.name_road:
            main_parts.append(str(self.name_road))
        if self.main_letter_road:
            main_parts.append(self.main_letter_road.abbreviation)
        if self.prefix_main_road:
            main_parts.append(self.prefix_main_road.abbreviation)  # "BIS"
        if self.sector_main_road:
            main_parts.append(self.sector_main_road.abbreviation)  # "NORTE", "SUR", etc

        main_line = ' '.join(filter(None, main_parts))

        # Vía Generadora: "No. 23 A SUR"
        additional_parts = []
        if self.generator_road_number:
            additional_parts.append(f"No. {self.generator_road_number}")
        if self.generator_road_letter:
            additional_parts.append(self.generator_road_letter.abbreviation)
        if self.generator_road_sector:
            additional_parts.append(self.generator_road_sector.abbreviation)

        additional_line = ' '.join(filter(None, additional_parts))

        # Placa: "- 15 ESTE"
        plate_parts = []
        if self.generator_plate_number:
            plate_parts.append(f"- {self.generator_plate_number}")
        if self.generator_plate_sector:
            plate_parts.append(self.generator_plate_sector.abbreviation)

        plate_line = ' '.join(filter(None, plate_parts))

        # Complementos
        complements = []
        if self.complement_name_a and self.complement_number_a:
            complements.append(f"{self.complement_name_a.abbreviation} {self.complement_number_a}")
        elif self.complement_name_a:
            complements.append(self.complement_name_a.abbreviation)

        if self.complement_name_b and self.complement_number_b:
            complements.append(f"{self.complement_name_b.abbreviation} {self.complement_number_b}")
        elif self.complement_name_b:
            complements.append(self.complement_name_b.abbreviation)

        if self.complement_name_c and self.complement_text_c:
            complements.append(f"{self.complement_name_c.abbreviation} {self.complement_text_c}")
        elif self.complement_name_c:
            complements.append(self.complement_name_c.abbreviation)
        elif self.complement_text_c:
            complements.append(self.complement_text_c)

        # Unir todas las partes
        address_parts = []
        if main_line:
            address_parts.append(main_line)
        if additional_line:
            address_parts.append(additional_line)
        if plate_line:
            address_parts.append(plate_line)
        if complements:
            address_parts.append(' '.join(complements))

        address = ' '.join(filter(None, address_parts))
        return address.upper() if address else ''

    def _compute_street(self):
        """
        Método manual para computar street desde campos estructurados
        IMPORTANTE: NO usar @api.depends decorator
        Este método se llama manualmente, no automáticamente
        """
        for partner in self:
            if partner.country_id and partner.country_id.id == 49:  # Colombia
                # Solo construir si hay datos en campos estructurados
                if any([partner.main_road, partner.name_road, partner.generator_road_number]):
                    partner.street = partner._build_native_address()

    @api.depends(lambda self: self._address_dependencies() + ['city_id', 'state_id', 'country_id'])
    def compute_full_address(self):
        """Computa la dirección completa incluyendo ciudad, departamento y país"""
        for partner in self:
            address_parts = []

            # Dirección
            if partner.street:
                address_parts.append(partner.street)

            # Ciudad
            if partner.city_id:
                address_parts.append(partner.city_id.name)
            elif partner.city:
                address_parts.append(partner.city)

            # Departamento/Estado
            if partner.state_id:
                address_parts.append(partner.state_id.name)

            # País
            if partner.country_id:
                address_parts.append(partner.country_id.name)

            partner.full_address = ', '.join(filter(None, address_parts))

    @api.depends('city_id', 'state_id', 'country_id')
    def _compute_full_city(self):
        """Computa formato: País - Departamento - Ciudad"""
        for partner in self:
            parts = []
            if partner.country_id:
                parts.append(partner.country_id.name)
            if partner.state_id:
                parts.append(partner.state_id.name)
            if partner.city_id:
                parts.append(partner.city_id.name)
            elif partner.city:
                parts.append(partner.city)

            partner.full_address_2 = ' - '.join(filter(None, parts))

    @api.onchange(*ADDRESS_FIELDS)
    def _onchange_street_full(self):
        """
        Actualiza el campo street en tiempo real cuando cambian los campos estructurados
        Solo para Colombia
        """
        for partner in self:
            if partner.country_id and partner.country_id.id == 49:
                # Solo actualizar si hay datos en campos estructurados
                if any([partner.main_road, partner.name_road, partner.generator_road_number]):
                    partner.street = partner._build_native_address()

    # ========== FIN MÉTODOS DIRECCIÓN ESTRUCTURADA ==========

    @api.onchange('city_id')
    def _onchange_city_id_postal(self):
        """Al cambiar la ciudad, buscar el primer codigo postal disponible"""
        for partner in self:
            if partner.city_id:
                postal = self.env['res.city.postal'].search([
                    ('city_id', '=', partner.city_id.id)
                ], limit=1)
                if postal:
                    partner.postal_code_id = postal.id
                    partner.zip = postal.postal_code
                else:
                    partner.postal_code_id = False
            else:
                partner.postal_code_id = False

    @api.onchange('postal_code_id')
    def _onchange_postal_code_id(self):
        """Al seleccionar codigo postal, llenar el campo zip"""
        for partner in self:
            if partner.postal_code_id:
                partner.zip = partner.postal_code_id.postal_code

    @api.onchange('neighborhood_id')
    def _onchange_neighborhood_id(self):
        """Al seleccionar barrio, llenar el codigo postal si el barrio lo tiene"""
        for partner in self:
            if partner.neighborhood_id and partner.neighborhood_id.postal_code_id:
                partner.postal_code_id = partner.neighborhood_id.postal_code_id
                partner.zip = partner.neighborhood_id.postal_code_id.postal_code

    @api.depends('vat_co','vat', 'dv', 'l10n_latam_identification_type_id')
    def _compute_vat_ref(self):
        for partner in self:
            partner.vat_ref = ''
            if partner.l10n_latam_identification_type_id.l10n_co_document_code not in ('rut','national_citizen_id'):
                continue

            try:
                if partner.vat_co:
                    clean_number = ''.join(filter(str.isdigit, partner.vat_co))
                    if clean_number:
                        dv = calc_check_digit(clean_number)
                        partner.vat_ref = f"{clean_number}-{dv}"
            except Exception as e:
                _logger.error(f"Error formateando NIT para partner {partner.id}: {str(e)}")

    @api.depends('vat', 'vat_co', 'l10n_latam_identification_type_id')
    def _compute_dv(self):
        for partner in self:
            partner._onchange_vat_co()
            partner.dv = ''
            if partner.l10n_latam_identification_type_id.l10n_co_document_code not in ('rut','national_citizen_id'):
                continue
                
            try:
                if partner.vat and "-" in partner.vat:
                    partner.dv = partner.vat.split('-')[1]
                elif partner.vat_co:
                    clean_number = ''.join(filter(str.isdigit, partner.vat_co))
                    if clean_number:
                        partner.dv = calc_check_digit(clean_number)
            except Exception as e:
                _logger.error(f"Error calculando DV para partner {partner.id}: {str(e)}")             

    @api.onchange('vat')
    def _onchange_vat(self):
        for partner in self:
            if partner.l10n_latam_identification_type_id.l10n_co_document_code == 'rut' and partner.vat:
                try:
                    if '-' in partner.vat:
                        base_number, _ = partner.vat.split('-')
                        clean_base = ''.join(filter(str.isdigit, base_number))
                        if clean_base:
                            partner.vat_co = clean_base
                    else:
                        clean_number = ''.join(filter(str.isdigit, partner.vat))
                        if len(clean_number) > 9:
                            partner.vat_co = clean_number[:-1]
                except Exception as e:
                    _logger.error(f"Error procesando vat: {str(e)}")

    @api.onchange('vat_co', 'l10n_latam_identification_type_id')
    def _onchange_vat_co(self):
        for partner in self:
            if partner.l10n_latam_identification_type_id.l10n_co_document_code == 'rut' and partner.vat_co:
                try:
                    if '-' in partner.vat_co:
                        base_number, _ = partner.vat_co.split('-')
                        partner.vat_co = ''.join(filter(str.isdigit, base_number))
                    elif len(''.join(filter(str.isdigit, partner.vat_co))) > 9 and partner.is_company and partner.vat_co[0:1] in ['8','9']:
                        clean_number = ''.join(filter(str.isdigit, partner.vat_co))
                        partner.vat_co = clean_number[:-1]

                    clean_number = ''.join(filter(str.isdigit, partner.vat_co))
                    if clean_number:
                        dv = calc_check_digit(clean_number)
                        partner.vat = f"{clean_number}-{dv}"
                except Exception as e:
                    _logger.error(f"Error procesando vat_co: {str(e)}")





    def _check_vat(self, validation='error'):
        # In Odoo 19, VAT validation is performed through _check_vat.
        with_vat = self.filtered(
            lambda x: x.l10n_latam_identification_type_id.is_vat
            and x.country_id.code != "CO"
        )
        return super(ResPartner, with_vat)._check_vat(validation=validation)

    @api.model
    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        if self._context.get('search_by_vat', False):
            if name:
                domain = domain if domain else []
                domain.extend(['|', ['name', 'ilike', name], ['vat', 'ilike', name]])
                name = ''
        return super(ResPartner, self).name_search(name=name, domain=domain, operator=operator, limit=limit)

    @api.depends('complete_name', 'email', 'vat', 'state_id', 'country_id', 
                'commercial_company_name', 'business_name', 'company_type')
    @api.depends_context('show_address', 'partner_show_db_id', 'address_inline', 
                        'show_email', 'show_vat', 'lang')
    def _compute_display_name(self):
        for partner in self:
            name = partner.with_context(lang=self.env.lang)._get_complete_name()
            if partner.business_name:
                if partner.company_type == 'person':
                    name = f"{name} ({partner.business_name})"
                elif partner.company_type == 'company':
                    if name != partner.business_name:
                        name = f"{partner.business_name} [{name}]"
            if partner._context.get('show_address'):
                address = partner._display_address(without_company=True)
                if address:
                    name = f"{name}\n{address}"
            name = re.sub(r'\s+\n', '\n', name)
            if partner._context.get('partner_show_db_id'):
                name = f"{name} ({partner.id})"
            if partner._context.get('address_inline'):
                splitted_names = name.split("\n")
                name = ", ".join([n for n in splitted_names if n.strip()])
            if partner._context.get('show_email') and partner.email:
                name = f"{name} <{partner.email}>"
            if partner._context.get('show_vat') and partner.vat:
                name = f"{name} ‒ {partner.vat}"
            partner.display_name = name.strip()


    def _display_address(self, without_company=False):
        """
        The purpose of this function is to build and return an address formatted accordingly to the
        standards of the country where it belongs.
        :param address: browse record of the res.partner to format
        :returns: the address formatted in a display that fit its country habits (or the default ones
            if not country is specified)
        :rtype: string
        """
        # get the information that will be injected into the display format
        # get the address format
        address_format = self._get_address_format()
        args = {
            "state_code": self.state_id.code or "",
            "state_name": self.state_id.name or "",
            "country_code": self.country_id.code or "",
            "country_name": self._get_country_name(),
            "company_name": self.commercial_company_name or "",
        }
        for field in self._formatting_address_fields():
            args[field] = getattr(self, field) or ""
        if without_company:
            args["company_name"] = ""
        elif self.commercial_company_name:
            address_format = "%(company_name)s\n" + address_format

        args["city"] = args["city"].capitalize() + ","
        return address_format % args

    @api.onchange('first_name', 'second_name', 'first_lastname', 'second_lastname')
    def _onchange_person_names(self):
        if self.company_type == 'person':
            self.name = self._get_computed_name()

    def split_full_name(self, full_name=None):
        """
        Divide un nombre completo en sus componentes y los asigna a los campos.

        Args:
            full_name: Nombre completo a dividir. Si no se proporciona, usa self.name

        Returns:
            dict con los valores asignados
        """
        self.ensure_one()
        name_to_split = full_name or self.name

        if not name_to_split:
            return {}

        # Solo para personas naturales
        if self.company_type != 'person':
            return {'name': name_to_split}

        # Dividir el nombre usando la utilidad
        name_parts = split_nombre_completo(name_to_split)

        # Asignar valores
        self.first_name = name_parts.get('first_name', '')
        self.second_name = name_parts.get('second_name', '')
        self.first_lastname = name_parts.get('first_lastname', '')
        self.second_lastname = name_parts.get('second_lastname', '')

        # Recalcular el nombre completo segun el orden configurado
        self.name = self._get_computed_name()

        return name_parts

    def action_split_name(self):
        """Accion para dividir el nombre desde la vista."""
        for partner in self:
            if partner.company_type == 'person' and partner.name:
                partner.split_full_name()
        return True


    def _l10n_co_dian_update_data(self, company):
        """Wrapper para compatibilidad con l10n_co_dian."""
        return self._lavish_update_partner_from_dian(company)

    def _lavish_process_dian_name(self, name):
        """
        Procesa un nombre recibido de DIAN y lo divide en componentes.

        Este metodo puede ser llamado directamente por modulos de facturacion
        electronica para procesar nombres de respuestas DIAN.

        Args:
            name: Nombre completo recibido de DIAN

        Returns:
            dict: Diccionario con first_name, second_name, first_lastname, second_lastname
        """
        if not name or self.company_type != 'person':
            return {}

        return self.split_full_name(name)

    def _get_computed_name(self):
        """Calcula el nombre completo segun la configuracion de orden."""
        names_order = self._get_names_order()
        first_names = ' '.join(filter(None, [self.first_name, self.second_name]))
        last_names = ' '.join(filter(None, [self.first_lastname, self.second_lastname]))

        if names_order == 'last_first_comma':
            # Apellidos, Nombres
            parts = [last_names, first_names]
            return ', '.join(filter(None, parts))
        elif names_order == 'last_first':
            # Apellidos Nombres
            parts = [last_names, first_names]
            return ' '.join(filter(None, parts))
        else:
            # first_last (default): Nombres Apellidos
            parts = [first_names, last_names]
            return ' '.join(filter(None, parts))

    @api.depends('company_type', 'name', 'first_name', 'second_name', 'first_lastname', 'second_lastname')
    def copy(self, default=None):
        default = default or {}
        if self.company_type == 'person':
            default.update({
                'first_name': self.first_name and self.first_name + _('(copy)') or '',
                'second_name': self.second_name and self.second_name + _('(copy)') or '',
                'first_lastname': self.first_lastname and self.first_lastname + _('(copy)') or '',
                'second_lastname': self.second_lastname and self.second_lastname + _('(copy)') or '',
            })
        return super(ResPartner, self).copy(default=default)


    @api.constrains('bank_ids')
    def _check_bank_ids(self):
        for record in self:
            if len(record.bank_ids) > 0:
                count_main = 0
                for bank in record.bank_ids:
                    count_main += 1 if bank.is_main else 0
                #if count_main > 1:
                #    raise ValidationError(_('No puede tener más de una cuenta principal, por favor verificar.'))

    @api.model
    def ___fields_view_get_address(self, arch):
        arch = super(ResPartner, self)._fields_view_get_address(arch)
        # render the partner address accordingly to address_view_id
        doc = etree.fromstring(arch)
        def _arch_location(node):
            in_subview = False
            view_type = False
            parent = node.getparent()
            while parent is not None and (not view_type or not in_subview):
                if parent.tag == "field":
                    in_subview = True
                elif parent.tag in ["form"]:
                    view_type = parent.tag
                parent = parent.getparent()
            return {
                "view_type": view_type,
                "in_subview": in_subview,
            }

        for city_node in doc.xpath("//field[@name='city']"):
            location = _arch_location(city_node)
            if location["view_type"] == "form" or not location["in_subview"]:
                parent = city_node.getparent()
                parent.remove(city_node)

        arch = etree.tostring(doc, encoding="unicode")
        return arch


class ResCountry(models.Model):
    _inherit = 'res.country'

    # Campos ISO
    name_iso = fields.Char(string='Nombre ISO')
    three_iso = fields.Char(string='Codigo ISO 3')
    numeric_code = fields.Char(string='Codigo Numerico', size=3)
    dian_code = fields.Char(string='Codigo DIAN', size=3)

    # Configuracion de direcciones
    address_builder_enabled = fields.Boolean(
        string='Constructor de Direcciones',
        default=False,
        help='Habilita el constructor de direcciones estructuradas'
    )
    zip_required = fields.Boolean(
        string='Codigo Postal Obligatorio',
        default=False,
        help='Hace obligatorio el codigo postal'
    )
    neighborhood_enabled = fields.Boolean(
        string='Usar Barrios',
        default=False,
        help='Habilita el campo de barrio/vecindario. Si no esta activo, se usa street2 manualmente'
    )

    # Relacion con ciudades
    city_ids = fields.One2many(
        'res.city', 'country_id',
        string='Ciudades'
    )
    postal_code_count = fields.Integer(
        string='Codigos Postales',
        compute='_compute_postal_count'
    )

    def _compute_postal_count(self):
        for country in self:
            country.postal_code_count = self.env['res.city.postal'].search_count([
                ('city_id.country_id', '=', country.id)
            ])

    def action_view_postal_codes(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Codigos Postales - {self.name}',
            'res_model': 'res.city.postal',
            'view_mode': 'list,form',
            'domain': [('city_id.country_id', '=', self.id)],
            'context': {'default_country_id': self.id},
        }
    

class ResCountryState(models.Model):
    _inherit = 'res.country.state'


    @api.depends('name', 'code')
    def _compute_display_name(self):
        for template in self:
            template.display_name = False if not template.name else (
                '{}{}'.format(
                    template.code and '[%s] ' % template.code or '', template.name
                ))
    @api.model
    def name_search(self, name='', domain=None, operator='ilike', limit=100, order=None):
        """
        Se hereda metodo name search y se sobreescribe para hacer la busqueda 
        por el codigo del estado/departamento
        """
        if not domain:
            domain = []
        domain = domain[:]
        ids = []
        if name:
            ids = self.search([('code', '=like', name + "%")] + domain, limit=limit)
            if not ids:
                ids = self.search([('name', operator, name)] + domain, limit=limit)
        else:
            ids = self.search(domain, limit=100)

        records = ids if ids else self
        return [(r.id, r.display_name) for r in records]

class ResCity(models.Model):
    _inherit = 'res.city'

    name = fields.Char(translate=False)
    code_dian = fields.Char(string="Code")

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for template in self:
            template.display_name = False if not template.name else (
                '{}{}'.format(
                    template.code and '[%s] ' % template.code or '', template.name
                ))
    @api.model
    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        """
        Se hereda metodo name search y se sobreescribe para hacer la busqueda
        por el codigo de la ciudad
        """
        if not domain:
            domain = []
        domain = domain[:]
        ids = []
        if name:
            ids = self.search([('code', '=like', name + "%")] + domain, limit=limit)
            if not ids:
                ids = self.search([('name', operator, name)] + domain, limit=limit)
        else:
            ids = self.search(domain, limit=100)

        records = ids if ids else self
        return [(r.id, r.display_name) for r in records]

class ResBank(models.Model):
    _inherit = 'res.bank'

    city_id = fields.Many2one('res.city', string="City of Address")
    bank_code = fields.Char(string='Bank Code')            

class ResCompany(models.Model):
    _inherit = 'res.company'

    def _get_default_partner(self):
        res_partner = self.env['res.partner'].sudo()
        partner_id = res_partner.browse(1)
        return partner_id.id

    city_id = fields.Many2one('res.city', string="City of Address")
    vat_vd = fields.Integer(string="Verification digit")
    default_partner_id = fields.Many2one('res.partner', string="Default partner", required=True, default=_get_default_partner)

    default_taxes_ids = fields.Many2many(
        string="Customer taxes",
        comodel_name="account.tax",
        relation="company_default_taxes_rel",
        column1="product_id",
        column2="tax_id",
        domain="[('type_tax_use','=','sale')]",
        help="Taxes applied for sale.",
    )
    default_supplier_taxes_ids = fields.Many2many(
        string="Supplier taxes",
        comodel_name="account.tax",
        relation="company_default_supplier_taxes_rel",
        column1="product_id",
        column2="tax_id",
        domain="[('type_tax_use','=','purchase')]",
        help="Taxes applied for purchase.",
    )

    def _get_company_address_fields(self, partner):
        result = super(ResCompany, self)._get_company_address_fields(partner)
        result['city_id'] = partner.city_id.id
        result['vat_vd'] = partner.vat_vd
        return result

    def _inverse_vat_vd(self):
        for company in self:
            company.partner_id.vat_vd = company.vat_vd
            company.default_partner_id.vat_vd = company.vat_vd


    def _inverse_city_id(self):
        for company in self:
            company.partner_id.city_id = company.city_id
            company.default_partner_id.city_id = company.city_id

    def _inverse_street(self):
        result = super(ResCompany, self)._inverse_street()
        for company in self:
            company.default_partner_id.street = company.street

    def _inverse_country(self):
        result = super(ResCompany, self)._inverse_country()
        for company in self:
            company.default_partner_id.country_id = company.country_id    
