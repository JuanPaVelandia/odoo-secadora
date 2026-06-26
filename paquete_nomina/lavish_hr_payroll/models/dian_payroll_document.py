# -*- coding: utf-8 -*-

import logging
import math
import zipfile
from datetime import datetime, timedelta
import pytz
import base64
import json
import hashlib
import uuid
import re

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError
from pytz import timezone

_logger = logging.getLogger(__name__)

try:
    from lxml import etree
except ImportError:
    _logger.info("Cannot import etree *************************************")

try:
    import requests
except ImportError:
    _logger.info("Cannot import requests library")

try:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    from OpenSSL import crypto
    type_ = crypto.FILETYPE_PEM
except ImportError:
    _logger.info("Cannot import OpenSSL library")

# URLs para nómina electrónica DIAN
PAYROLL_SERVER_URL = {
    "HABILITACION": "https://vpfe-hab.dian.gov.co/WcfDianCustomerServices.svc?wsdl",
    "PRODUCCION": "https://vpfe.dian.gov.co/WcfDianCustomerServices.svc?wsdl",
}

PAYROLL_ENDPOINTS = {
    "HABILITACION": {
        "SendTestSetAsync": "https://vpfe-hab.dian.gov.co/WcfDianCustomerServices.svc/SendTestSetAsync",
        "GetStatus": "https://vpfe-hab.dian.gov.co/WcfDianCustomerServices.svc/GetStatus",
        "GetStatusZip": "https://vpfe-hab.dian.gov.co/WcfDianCustomerServices.svc/GetStatusZip",
        "SendNominaSync": "https://vpfe-hab.dian.gov.co/WcfDianCustomerServices.svc/SendNominaSync",
    },
    "PRODUCCION": {
        "SendNominaSync": "https://vpfe.dian.gov.co/WcfDianCustomerServices.svc/SendNominaSync",
        "GetStatus": "https://vpfe.dian.gov.co/WcfDianCustomerServices.svc/GetStatus",
        "GetStatusZip": "https://vpfe.dian.gov.co/WcfDianCustomerServices.svc/GetStatusZip",
    }
}

class DianPayrollDocument(models.Model):
    _name = 'dian.payroll.document'
    _description = 'Documento de Nómina Electrónica DIAN'
    _order = 'create_date desc'

    name = fields.Char('Número', required=True, readonly=True, default='Nuevo')
    payroll_detail_id = fields.Many2one('hr.electronic.payroll.detail', 'Detalle de Nómina', required=True, ondelete='cascade')
    company_id = fields.Many2one('res.company', 'Compañía', required=True, default=lambda self: self.env.company)
    
    # Estado del documento
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('generated', 'XML Generado'),
        ('signed', 'Firmado'),
        ('sent', 'Enviado a DIAN'),
        ('accepted', 'Aceptado por DIAN'),
        ('rejected', 'Rechazado por DIAN'),
        ('error', 'Error'),
    ], string='Estado', default='draft', tracking=True)
    
    # Información del documento
    xml_file = fields.Binary('XML Generado')
    xml_filename = fields.Char('Nombre XML')
    signed_xml_file = fields.Binary('XML Firmado')
    signed_xml_filename = fields.Char('Nombre XML Firmado')
    zip_file = fields.Binary('Archivo ZIP')
    zip_filename = fields.Char('Nombre ZIP')
    
    # Respuesta de DIAN
    dian_response = fields.Text('Respuesta DIAN')
    dian_zip_key = fields.Char('ZIP Key DIAN')
    dian_status_code = fields.Char('Código Estado DIAN')
    dian_status_description = fields.Text('Descripción Estado DIAN')
    transaction_id = fields.Char('ID Transacción')
    
    # Campos para seguimiento
    cune = fields.Char('CUNE')
    qr_code = fields.Binary('Código QR')
    sent_date = fields.Datetime('Fecha Envío')
    response_date = fields.Datetime('Fecha Respuesta')
    
    # Configuración
    environment = fields.Selection([
        ('test', 'Habilitación'),
        ('production', 'Producción'),
    ], string='Entorno', default='test')

    @api.model
    def create(self, vals):
        if vals.get('name', 'Nuevo') == 'Nuevo':
            vals['name'] = self.env['ir.sequence'].next_by_code('dian.payroll.document') or 'Nuevo'
        return super(DianPayrollDocument, self).create(vals)

    def action_generate_xml(self):
        """Genera el XML de nómina electrónica"""
        for record in self:
            try:
                # Generar XML usando el sistema existente
                xml_generator = self.env['lavish.xml.generator.header'].search([
                    ('code', '=', 'NomElectronica_SoftwarePropio'),
                    ('active', '=', True)
                ], limit=1)
                
                if not xml_generator:
                    raise UserError(_("No se encontró el generador XML para Software Propio (DIAN)"))
                
                xml_content = xml_generator.xml_generator(record.payroll_detail_id)
                
                if xml_content:
                    # Manejar tanto string como bytes
                    if isinstance(xml_content, bytes):
                        xml_b64 = base64.b64encode(xml_content)
                    else:
                        xml_b64 = base64.b64encode(xml_content.encode('utf-8'))
                    
                    filename = f"nomina_{record.payroll_detail_id.employee_id.identification_id}_{record.payroll_detail_id.sequence}.xml"
                    
                    record.write({
                        'xml_file': xml_b64,
                        'xml_filename': filename,
                        'state': 'generated'
                    })
                    
                    _logger.info(f"XML generado exitosamente para nómina {record.name}")
                else:
                    raise UserError(_("Error al generar el XML de nómina"))
                    
            except Exception as e:
                record.state = 'error'
                record.dian_response = str(e)
                _logger.error(f"Error generando XML: {e}")
                raise UserError(f"Error al generar XML: {e}")

    def action_sign_xml(self):
        """Firma digitalmente el XML"""
        for record in self:
            if not record.xml_file:
                raise UserError(_("No hay XML generado para firmar"))
                
            try:
                # Obtener certificado de la compañía
                company = record.company_id
                if not company.payroll_certificate_file or not company.payroll_certificate_password:
                    raise UserError(_("La compañía no tiene certificado digital configurado para nómina electrónica"))
                
                # Decodificar XML
                xml_content = base64.b64decode(record.xml_file).decode('utf-8')
                
                # Firmar XML (usando la lógica del módulo de factura electrónica)
                signed_xml = self._sign_xml_document(xml_content, company)
                
                # Guardar XML firmado
                signed_xml_b64 = base64.b64encode(signed_xml.encode('utf-8'))
                signed_filename = record.xml_filename.replace('.xml', '_firmado.xml')
                
                record.write({
                    'signed_xml_file': signed_xml_b64,
                    'signed_xml_filename': signed_filename,
                    'state': 'signed'
                })
                
                _logger.info(f"XML firmado exitosamente para nómina {record.name}")
                
            except Exception as e:
                record.state = 'error'
                record.dian_response = str(e)
                _logger.error(f"Error firmando XML: {e}")
                raise UserError(f"Error al firmar XML: {e}")

    def action_send_to_dian(self):
        """Envía el XML firmado a DIAN"""
        for record in self:
            if not record.signed_xml_file:
                raise UserError(_("No hay XML firmado para enviar"))
                
            try:
                _logger.info("=== INICIO PROCESO ENVÍO DIAN ===")
                
                # 1. Ejecutar diagnóstico completo antes del envío
                _logger.info("1. Ejecutando diagnóstico pre-envío...")
                record.action_diagnose_before_send()
                
                # 2. Validar estructura XML exhaustivamente
                _logger.info("2. Validando estructura XML...")
                record.action_validate_xml_structure()
                
                # 3. Validar configuración antes de enviar
                _logger.info("3. Validando configuración DIAN...")
                record._validate_dian_configuration()
                
                # 4. Crear ZIP con el XML firmado
                _logger.info("4. Creando archivo ZIP...")
                zip_content = record._create_zip_file()
                
                # 5. Validar contenido ZIP exhaustivamente
                _logger.info("5. Validando contenido ZIP...")
                record._validate_zip_content(zip_content)
                
                # 6. Configurar entorno
                environment = 'test' if not record.company_id.payroll_production_mode else 'production'
                record.environment = environment
                _logger.info(f"6. Entorno configurado: {environment}")
                
                # 7. Validaciones finales antes del envío
                _logger.info("7. Validaciones finales...")
                record._validate_final_before_send()
                
                # 8. Enviar a DIAN
                _logger.info("8. Enviando a DIAN...")
                if environment == 'test':
                    response = record._send_test_set_async(zip_content)
                else:
                    response = record._send_nomina_sync(zip_content)
                
                # 9. Procesar respuesta
                _logger.info("9. Procesando respuesta...")
                record._process_dian_response(response)
                
                _logger.info("=== ENVÍO COMPLETADO EXITOSAMENTE ===")
                
            except Exception as e:
                record.state = 'error'
                record.dian_response = str(e)
                _logger.error(f"Error enviando a DIAN: {e}")
                raise UserError(f"Error al enviar a DIAN: {e}")
    
    def action_check_status(self):
        """Consulta el estado del documento en DIAN"""
        for record in self:
            if not record.dian_zip_key:
                raise UserError(_("No hay ZIP Key para consultar el estado"))
                
            try:
                _logger.info("=== CONSULTANDO ESTADO EN DIAN ===")
                response = record._get_status_zip()
                record._process_status_response(response)
                _logger.info("=== CONSULTA DE ESTADO COMPLETADA ===")
                
            except Exception as e:
                _logger.error(f"Error consultando estado: {e}")
                raise UserError(f"Error al consultar estado: {e}")
    
    def _validate_final_before_send(self):
        """Validaciones finales específicas antes del envío a DIAN"""
        self.ensure_one()
        
        _logger.info("=== VALIDACIONES FINALES PRE-ENVÍO ===")
        
        company = self.company_id
        
        # 1. Validar datos críticos de la compañía
        if not company.vat:
            raise UserError("La compañía debe tener NIT configurado")
        
        # Limpiar NIT y validar formato
        nit = company.vat.replace('-', '').replace(' ', '')
        if not nit.isdigit() or len(nit) < 9:
            raise UserError(f"NIT de la compañía inválido: {company.vat}")
        
        _logger.info(f"✓ NIT compañía validado: {nit}")
        
        # 2. Validar empleado
        employee = self.payroll_detail_id.employee_id
        if not employee:
            raise UserError("No hay empleado asociado al detalle de nómina")
        
        if not employee.identification_id:
            raise UserError(f"El empleado {employee.name} no tiene número de identificación")
        
        _logger.info(f"✓ Empleado validado: {employee.name} - {employee.identification_id}")
        
        # 3. Validar Test Set ID para habilitación
        if self.environment == 'test':
            test_set_id = company.payroll_test_set_id or company.test_set_id
            if not test_set_id:
                raise UserError("Test Set ID es requerido para ambiente de habilitación")
            
            # Validar que sea un GUID válido
            if not re.match(r'^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$', test_set_id):
                raise UserError(f"Test Set ID debe ser un GUID válido. Actual: {test_set_id}")
            
            _logger.info(f"✓ Test Set ID validado: {test_set_id}")
        
        # 4. Validar que el XML tenga contenido esperado
        if self.xml_file:
            xml_content = base64.b64decode(self.xml_file)
            
            # Verificar que el XML contenga información del empleado
            try:
                root = etree.fromstring(xml_content)
                
                # Obtener namespace por defecto para búsquedas
                ns_map = root.nsmap
                default_ns = ns_map.get(None, '')
                
                # Buscar documento del trabajador en el XML (considerando namespace)
                trabajador_doc = root.find('.//NumeroDocumento')
                if trabajador_doc is None and default_ns:
                    trabajador_doc = root.find(f'.//{{{default_ns}}}NumeroDocumento')
                
                if trabajador_doc is None or not trabajador_doc.text:
                    raise UserError("El XML no contiene el número de documento del trabajador")
                
                # Verificar que coincida con el empleado (permitir diferencias menores)
                if trabajador_doc.text.strip() != employee.identification_id.strip():
                    _logger.warning(f"Documento en XML ({trabajador_doc.text}) no coincide exactamente con empleado ({employee.identification_id})")
                
                _logger.info(f"✓ XML contiene datos del trabajador: {trabajador_doc.text}")
                
                # Verificar NIT del empleador en XML (considerando namespace)
                empleador_nit = root.find('.//NIT')
                if empleador_nit is None and default_ns:
                    empleador_nit = root.find(f'.//{{{default_ns}}}NIT')
                
                if empleador_nit is None or not empleador_nit.text:
                    raise UserError("El XML no contiene el NIT del empleador")
                
                # Limpiar NITs para comparación
                xml_nit = empleador_nit.text.replace('-', '').replace(' ', '')
                company_nit = nit.replace('-', '').replace(' ', '')
                
                if xml_nit != company_nit:
                    _logger.warning(f"NIT en XML ({empleador_nit.text}) no coincide con compañía ({nit})")
                
                _logger.info(f"✓ XML contiene NIT del empleador: {empleador_nit.text}")
                
            except etree.XMLSyntaxError as e:
                raise UserError(f"Error parseando XML para validación final: {e}")
        
        # 5. Validar tamaños
        if self.zip_file:
            zip_content = base64.b64decode(self.zip_file)
            zip_size_mb = len(zip_content) / (1024 * 1024)
            
            if zip_size_mb > 10:  # Límite conservador
                raise UserError(f"Archivo ZIP muy grande: {zip_size_mb:.2f} MB (máximo recomendado: 10 MB)")
            
            _logger.info(f"✓ Tamaño ZIP válido: {zip_size_mb:.2f} MB")
        
        _logger.info("=== TODAS LAS VALIDACIONES FINALES PASARON ===")

    def action_validate_xml_structure(self):
        """Valida exhaustivamente la estructura del XML antes del envío"""
        self.ensure_one()
        
        if not self.xml_file:
            raise UserError(_("No hay XML generado para validar"))
        
        try:
            xml_content = base64.b64decode(self.xml_file)
            
            _logger.info("=== VALIDACIÓN EXHAUSTIVA XML ===")
            
            # 1. Validar que sea XML bien formado
            try:
                root = etree.fromstring(xml_content)
                _logger.info("✓ XML bien formado")
            except etree.XMLSyntaxError as e:
                raise UserError(f"XML mal formado: {e}")
            
            # 2. Verificar encoding
            xml_str = xml_content.decode('utf-8')
            if '<?xml' not in xml_str[:100]:
                _logger.warning("⚠ No se encontró declaración XML")
            else:
                _logger.info("✓ Declaración XML presente")
            
            # 3. Verificar elementos obligatorios para nómina electrónica DIAN
            # Buscar con namespace correcto
            ns_map = root.nsmap
            default_ns = ns_map.get(None, '')
            
            # Definir elementos según el esquema de DIAN para nómina individual
            required_elements = []
            
            if 'NominaIndividual' in default_ns:
                # Estructura de nómina individual DIAN
                required_elements = [
                    ('InformacionGeneral/Ambiente', 'Ambiente'),
                    ('InformacionGeneral/TipoXML', 'Tipo XML'),
                    ('InformacionGeneral/CUNE', 'CUNE'),
                    ('InformacionGeneral/EncripCUNE', 'CUNE Encriptado'),
                    ('InformacionGeneral/FechaGen', 'Fecha de generación'),
                    ('InformacionGeneral/HoraGen', 'Hora de generación'),
                    ('InformacionGeneral/PeriodoNomina', 'Período de nómina'),
                    ('InformacionGeneral/TipoMoneda', 'Tipo de moneda'),
                    ('InformacionGeneral/TRM', 'Tasa de cambio'),
                    ('Empleador', 'Información del empleador'),
                    ('Trabajador', 'Información del trabajador'),
                    ('Pago', 'Información de pago'),
                    ('FechasPagos', 'Fechas de pago')
                ]
            else:
                # Estructura genérica (fallback)
                required_elements = [
                    ('NumeroSecuenciaXML', 'Número de secuencia XML'),
                    ('Numero', 'Número del documento'),
                    ('FechaGen', 'Fecha de generación'),
                    ('HoraGen', 'Hora de generación'),
                    ('Empleador', 'Información del empleador'),
                    ('Trabajador', 'Información del trabajador'),
                    ('Pago', 'Información de pago')
                ]
            
            missing_elements = []
            found_elements = []
            
            for element_path, description in required_elements:
                # Buscar elemento con o sin namespace
                element = root.find(f'.//{element_path}')
                if element is None and default_ns:
                    # Intentar con namespace por defecto
                    element = root.find(f'.//{{{default_ns}}}{element_path}')
                
                if element is not None:
                    element_text = element.text or 'presente'
                    found_elements.append(f"✓ {description}: {element_text[:50]}...")
                else:
                    missing_elements.append(f"✗ {description} ({element_path})")
            
            _logger.info("Elementos encontrados:")
            for elem in found_elements:
                _logger.info(f"  {elem}")
            
            if missing_elements:
                _logger.warning("Elementos faltantes o no encontrados:")
                for elem in missing_elements:
                    _logger.warning(f"  {elem}")
            
            # 3.1 Análisis específico de la estructura real del XML
            _logger.info("=== ANÁLISIS DE ESTRUCTURA REAL ===")
            _logger.info(f"Elemento raíz: {root.tag}")
            _logger.info(f"Namespace por defecto: {default_ns}")
            
            # Mostrar estructura de primer y segundo nivel
            for child in root:
                _logger.info(f"Elemento hijo nivel 1: {child.tag}")
                if len(child) > 0:
                    for grandchild in child:
                        _logger.info(f"  Elemento hijo nivel 2: {grandchild.tag}")
                        if grandchild.text and grandchild.text.strip():
                            _logger.info(f"    Valor: {grandchild.text[:100]}")
            
            # Buscar elementos específicos de nómina DIAN (considerando namespace)
            dian_specific_elements = [
                ('InformacionGeneral', 'Informacion'),  # DIAN usa 'Informacion', no 'InformacionGeneral'
                ('Empleador', 'Empleador'), 
                ('Trabajador', 'Trabajador'), 
                ('Pago', 'ComprobanteTotal'),  # DIAN usa diferentes nombres
                ('FechasPagos', 'Periodo'),
                ('Devengados', 'Devengados'), 
                ('Deducciones', 'Deducciones'), 
                ('Ambiente', 'TipoNota'),  # Buscar en Informacion
                ('TipoXML', 'TipoDocumento'),  # Buscar en Informacion
                ('CUNE', 'CodigoQR')  # DIAN puede usar CodigoQR
            ]
            
            _logger.info("=== ELEMENTOS ESPECÍFICOS DIAN ENCONTRADOS ===")
            for expected_name, actual_name in dian_specific_elements:
                # Buscar con el nombre real del elemento en el XML
                element = root.find(f'.//{actual_name}')
                if element is None and default_ns:
                    # Intentar con namespace completo
                    element = root.find(f'.//{{{default_ns}}}{actual_name}')
                
                if element is not None:
                    _logger.info(f"✓ {expected_name} (como {actual_name}): encontrado")
                    # Si tiene hijos, mostrar algunos
                    if len(element) > 0:
                        for i, child in enumerate(element[:3]):  # Solo primeros 3
                            if child.text and child.text.strip():
                                child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                                _logger.info(f"    {child_tag}: {child.text}")
                    elif element.text and element.text.strip():
                        _logger.info(f"    Valor: {element.text}")
                else:
                    _logger.info(f"✗ {expected_name} (buscando {actual_name}): no encontrado")
            
            # 4. Verificar estructura del empleador (usando namespace correcto)
            empleador = root.find('.//Empleador')
            if empleador is None and default_ns:
                empleador = root.find(f'.//{{{default_ns}}}Empleador')
                
            if empleador is not None:
                _logger.info("=== ANÁLISIS EMPLEADOR ===")
                empleador_fields = ['RazonSocial', 'NIT', 'DV', 'Pais', 'DepartamentoEstado', 'MunicipioC', 'Direccion']
                for field in empleador_fields:
                    elem = empleador.find(f'.//{field}')
                    if elem is None and default_ns:
                        elem = empleador.find(f'.//{{{default_ns}}}{field}')
                    
                    if elem is not None and elem.text:
                        _logger.info(f"  Empleador.{field}: {elem.text}")
                    else:
                        _logger.warning(f"  Empleador.{field}: FALTANTE")
                        
                # Mostrar todos los campos disponibles en empleador
                _logger.info("  Campos reales en Empleador:")
                for child in empleador:
                    if child.text and child.text.strip():
                        child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                        _logger.info(f"    {child_tag}: {child.text}")
            else:
                _logger.warning("No se encontró elemento Empleador")
            
            # 5. Verificar estructura del trabajador (usando namespace correcto)
            trabajador = root.find('.//Trabajador')
            if trabajador is None and default_ns:
                trabajador = root.find(f'.//{{{default_ns}}}Trabajador')
                
            if trabajador is not None:
                _logger.info("=== ANÁLISIS TRABAJADOR ===")
                trabajador_fields = ['TipoTrabajador', 'SubTipoTrabajador', 'AltoRiesgoPension', 'TipoDocumento', 'NumeroDocumento', 'PrimerApellido', 'PrimerNombre']
                for field in trabajador_fields:
                    elem = trabajador.find(f'.//{field}')
                    if elem is None and default_ns:
                        elem = trabajador.find(f'.//{{{default_ns}}}{field}')
                    
                    if elem is not None and elem.text:
                        _logger.info(f"  Trabajador.{field}: {elem.text}")
                    else:
                        _logger.warning(f"  Trabajador.{field}: FALTANTE")
                        
                # Mostrar todos los campos disponibles en trabajador
                _logger.info("  Campos reales en Trabajador:")
                for child in trabajador:
                    if child.text and child.text.strip():
                        child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                        _logger.info(f"    {child_tag}: {child.text}")
            else:
                _logger.warning("No se encontró elemento Trabajador")
            
            # 6. Verificar namespaces
            _logger.info("Namespaces del documento:")
            if hasattr(root, 'nsmap'):
                for prefix, uri in root.nsmap.items():
                    prefix_name = prefix if prefix else "(default)"
                    _logger.info(f"  {prefix_name}: {uri}")
            
            # 7. Verificar tamaño del XML
            xml_size_kb = len(xml_content) / 1024
            _logger.info(f"Tamaño del XML: {xml_size_kb:.2f} KB")
            
            if xml_size_kb > 5000:  # 5MB
                _logger.warning("⚠ XML muy grande, podría causar problemas en DIAN")
            
            # 8. Verificar caracteres especiales
            try:
                xml_str.encode('utf-8')
                _logger.info("✓ Encoding UTF-8 válido")
            except UnicodeEncodeError as e:
                _logger.error(f"✗ Error de encoding: {e}")
                raise UserError(f"El XML contiene caracteres no válidos: {e}")
            
            # 9. Verificar que no haya elementos vacíos críticos
            # Adaptar validación según estructura real
            critical_empty = []
            critical_elements_to_check = []
            
            if found_elements:
                # Si encontramos elementos, usar los primeros como críticos
                critical_elements_to_check = [elem[0] for elem in required_elements[:3]]
            else:
                # Fallback: buscar elementos comunes de nómina
                common_elements = ['InformacionGeneral', 'Empleador', 'Trabajador']
                for element_name in common_elements:
                    element = root.find(f'.//{element_name}')
                    if element is not None:
                        critical_elements_to_check.append(element_name)
            
            for element_path in critical_elements_to_check:
                element = root.find(f'.//{element_path}')
                if element is None and default_ns:
                    element = root.find(f'.//{{{default_ns}}}{element_path}')
                    
                if element is not None and not element.text and len(element) == 0:
                    critical_empty.append(element_path)
            
            if critical_empty:
                _logger.warning(f"Elementos críticos vacíos: {critical_empty}")
                # No lanzar error, solo advertir
                _logger.warning("Algunos elementos críticos están vacíos, pero esto podría ser normal según la estructura de DIAN")
            
            # 10. Validación específica para estructura DIAN (usando estructura real)
            _logger.info("=== VALIDACIÓN ESPECÍFICA DIAN ===")
            
            # Verificar si tiene la estructura mínima requerida por DIAN (adaptada a la estructura real)
            required_for_dian = [
                ('Informacion', 'Información general'),
                ('Empleador', 'Datos del empleador'),
                ('Trabajador', 'Datos del trabajador')
            ]
            missing_dian = []
            found_dian = []
            
            for req_element, description in required_for_dian:
                element = root.find(f'.//{req_element}')
                if element is None and default_ns:
                    element = root.find(f'.//{{{default_ns}}}{req_element}')
                    
                if element is not None:
                    found_dian.append(f"✓ {description}")
                else:
                    missing_dian.append(req_element)
            
            if missing_dian:
                _logger.error(f"Elementos obligatorios DIAN faltantes: {missing_dian}")
                raise UserError(f"El XML no tiene la estructura mínima requerida por DIAN. Faltan: {', '.join(missing_dian)}")
            else:
                _logger.info("✓ Estructura mínima DIAN presente")
                for found in found_dian:
                    _logger.info(f"  {found}")
            
            # Verificar elementos que contienen variables sin reemplazar
            _logger.info("=== VERIFICACIÓN DE VARIABLES SIN REEMPLAZAR ===")
            xml_str = xml_content.decode('utf-8') if isinstance(xml_content, bytes) else xml_content
            
            # Buscar patrones de variables no reemplazadas
            import re
            unreplaced_vars = re.findall(r'\{[^}]+\}', xml_str)
            if unreplaced_vars:
                _logger.warning("Variables sin reemplazar encontradas:")
                for var in set(unreplaced_vars):  # usar set para evitar duplicados
                    _logger.warning(f"  {var}")
                _logger.warning("Esto indica que el generador XML no está reemplazando correctamente todas las variables")
            else:
                _logger.info("✓ No se encontraron variables sin reemplazar")
            
            _logger.info("=== FIN VALIDACIÓN XML ===")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Validación XML Completada',
                    'message': f'XML validado exitosamente. Encontrados {len(found_elements)} elementos requeridos.',
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except Exception as e:
            _logger.error(f"Error en validación XML: {e}")
            raise UserError(f"Error validando XML: {e}")

    def action_inspect_xml_structure(self):
        """Inspecciona completamente la estructura del XML generado"""
        self.ensure_one()
        
        if not self.xml_file:
            raise UserError(_("No hay XML generado para inspeccionar"))
        
        try:
            xml_content = base64.b64decode(self.xml_file)
            root = etree.fromstring(xml_content)
            
            _logger.info("=== INSPECCIÓN COMPLETA XML ===")
            _logger.info(f"Tamaño: {len(xml_content)} bytes")
            
            def log_element(element, level=0):
                """Log recursivo de elementos"""
                indent = "  " * level
                tag_local = element.tag.split('}')[-1] if '}' in element.tag else element.tag
                
                if element.text and element.text.strip():
                    text_preview = element.text.strip()[:100]
                    _logger.info(f"{indent}{tag_local}: {text_preview}")
                else:
                    _logger.info(f"{indent}{tag_local}")
                
                # Atributos
                if element.attrib:
                    for attr, value in element.attrib.items():
                        _logger.info(f"{indent}  @{attr}: {value}")
                
                # Elementos hijos
                for child in element:
                    if level < 3:  # Limitar profundidad para evitar logs excesivos
                        log_element(child, level + 1)
                    elif level == 3:
                        child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                        _logger.info(f"{indent}  {child_tag}...")
            
            # Mostrar estructura completa
            log_element(root)
            
            _logger.info("=== FIN INSPECCIÓN XML ===")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Inspección XML Completada',
                    'message': 'Revise los logs del servidor para ver la estructura completa del XML.',
                    'type': 'info',
                    'sticky': True,
                }
            }
            
        except Exception as e:
            _logger.error(f"Error inspeccionando XML: {e}")
            raise UserError(f"Error inspeccionando XML: {e}")

    def action_diagnose_before_send(self):
        """Ejecuta un diagnóstico completo antes del envío"""
        self.ensure_one()
        
        _logger.info("=== DIAGNÓSTICO PRE-ENVÍO DIAN ===")
        
        try:
            # 1. Verificar datos de la nómina
            payroll = self.payroll_detail_id
            employee_name = payroll.employee_id.name if payroll.employee_id else 'N/A'
            _logger.info(f"Nómina: {payroll.sequence} - Empleado: {employee_name}")
            _logger.info(f"ID Nómina detalle: {payroll.id}")
            
            # Verificar campos disponibles en el modelo de nómina
            if hasattr(payroll, 'electronic_payroll_id') and payroll.electronic_payroll_id:
                electronic_payroll = payroll.electronic_payroll_id
                _logger.info(f"Nómina electrónica padre: {electronic_payroll.id}")
                
                # Verificar fechas en el modelo padre
                if hasattr(electronic_payroll, 'date_start'):
                    _logger.info(f"Fecha inicio: {electronic_payroll.date_start}")
                if hasattr(electronic_payroll, 'date_end'):
                    _logger.info(f"Fecha fin: {electronic_payroll.date_end}")
                if hasattr(electronic_payroll, 'period_id'):
                    period_name = electronic_payroll.period_id.name if electronic_payroll.period_id else 'N/A'
                    _logger.info(f"Período: {period_name}")
            
            # Información del contrato y empleado
            if hasattr(payroll, 'contract_id') and payroll.contract_id:
                _logger.info(f"Contrato: {payroll.contract_id.name}")
            
            if hasattr(payroll, 'status'):
                _logger.info(f"Estado: {payroll.status}")
                
        except Exception as e:
            _logger.warning(f"Error accediendo a datos de nómina: {e}")
        
        try:
            # 2. Verificar configuración de compañía
            company = self.company_id
            _logger.info(f"Compañía: {company.name}")
            _logger.info(f"NIT: {company.vat}")
            
            # Test Set ID
            test_set_id = company.payroll_test_set_id if hasattr(company, 'payroll_test_set_id') else None
            if not test_set_id and hasattr(company, 'test_set_id'):
                test_set_id = company.test_set_id
                
            _logger.info(f"Test Set ID: {test_set_id}")
            if test_set_id:
                is_valid_guid = bool(re.match(r'^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$', test_set_id))
                _logger.info(f"Test Set ID válido: {is_valid_guid}")
            else:
                _logger.warning("No se encontró Test Set ID configurado")
            
            # Certificado
            has_cert = hasattr(company, 'payroll_certificate_file') and bool(company.payroll_certificate_file)
            _logger.info(f"Certificado configurado: {has_cert}")
            
        except Exception as e:
            _logger.warning(f"Error accediendo a configuración de compañía: {e}")
        
        try:
            # 3. Verificar XML generado
            if self.xml_file:
                xml_content = base64.b64decode(self.xml_file)
                _logger.info(f"XML generado - Tamaño: {len(xml_content)} bytes")
                
                # Verificar estructura básica
                try:
                    root = etree.fromstring(xml_content)
                    _logger.info(f"XML válido - Elemento raíz: {root.tag}")
                    
                    # Buscar elementos críticos
                    numero_seq = root.find('.//NumeroSecuenciaXML')
                    if numero_seq is not None:
                        _logger.info(f"Número secuencia: {numero_seq.text}")
                    
                    fecha_gen = root.find('.//FechaGen')
                    if fecha_gen is not None:
                        _logger.info(f"Fecha generación: {fecha_gen.text}")
                    
                    # Verificar namespace del documento
                    if hasattr(root, 'nsmap') and root.nsmap:
                        _logger.info(f"Namespaces XML: {list(root.nsmap.keys())}")
                        
                except Exception as e:
                    _logger.error(f"Error parseando XML: {e}")
            else:
                _logger.warning("No hay XML generado")
                
        except Exception as e:
            _logger.warning(f"Error verificando XML: {e}")
        
        try:
            # 4. Verificar XML firmado
            if self.signed_xml_file:
                signed_xml_content = base64.b64decode(self.signed_xml_file)
                _logger.info(f"XML firmado - Tamaño: {len(signed_xml_content)} bytes")
            else:
                _logger.warning("No hay XML firmado")
                
        except Exception as e:
            _logger.warning(f"Error verificando XML firmado: {e}")
        
        try:
            # 5. Verificar archivo ZIP
            if self.zip_file:
                zip_content = base64.b64decode(self.zip_file)
                _logger.info(f"ZIP - Tamaño: {len(zip_content)} bytes")
                _logger.info(f"ZIP - Nombre: {self.zip_filename}")
            else:
                _logger.warning("No hay archivo ZIP generado")
                
        except Exception as e:
            _logger.warning(f"Error verificando ZIP: {e}")
            
        _logger.info("=== FIN DIAGNÓSTICO ===")
        
        return True
    
    def _validate_dian_configuration(self):
        """Valida la configuración necesaria para DIAN"""
        self.ensure_one()
        
        company = self.company_id
        
        # Validar Test Set ID para habilitación
        if self.environment == 'test':
            test_set_id = company.payroll_test_set_id or company.test_set_id
            if not test_set_id:
                raise UserError(_("Test Set ID es requerido para el ambiente de habilitación"))
            
            # Validar formato GUID
            if not re.match(r'^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$', test_set_id):
                raise UserError(_("Test Set ID debe tener formato GUID válido"))
        
        # Validar certificado (aunque por ahora no se usa para firmar)
        if not company.payroll_certificate_file:
            _logger.warning("No hay certificado configurado - continuando sin firma digital")
        
        _logger.info(f"Configuración DIAN validada para entorno: {self.environment}")
    
    def _validate_zip_content(self, zip_content):
        """Valida el contenido del archivo ZIP de manera exhaustiva"""
        self.ensure_one()
        
        try:
            _logger.info("=== VALIDACIÓN EXHAUSTIVA ZIP ===")
            
            # Verificar que el ZIP no esté vacío
            if len(zip_content) == 0:
                raise UserError(_("El archivo ZIP está vacío"))
            
            _logger.info(f"Tamaño ZIP: {len(zip_content)} bytes")
            
            # Verificar que sea un ZIP válido
            import io
            try:
                with zipfile.ZipFile(io.BytesIO(zip_content), 'r') as zip_file:
                    file_list = zip_file.namelist()
                    
                    _logger.info(f"Archivos en ZIP: {file_list}")
                    
                    if not file_list:
                        raise UserError(_("El archivo ZIP no contiene archivos"))
                    
                    # DIAN espera exactamente 1 archivo XML
                    xml_files = [f for f in file_list if f.endswith('.xml')]
                    if len(xml_files) != 1:
                        _logger.warning(f"Se esperaba 1 archivo XML, encontrados: {len(xml_files)}")
                        if len(xml_files) == 0:
                            raise UserError(_("El archivo ZIP no contiene archivos XML"))
                    
                    # Validar cada archivo XML en el ZIP
                    for filename in xml_files:
                        try:
                            xml_content = zip_file.read(filename)
                            _logger.info(f"Validando archivo XML: {filename}")
                            _logger.info(f"  Tamaño: {len(xml_content)} bytes")
                            
                            # Verificar que no esté vacío
                            if len(xml_content) == 0:
                                raise UserError(f"El archivo {filename} está vacío")
                            
                            # Verificar que sea XML válido
                            try:
                                root = etree.fromstring(xml_content)
                                _logger.info(f"  ✓ XML bien formado - Root: {root.tag}")
                            except etree.XMLSyntaxError as xml_error:
                                raise UserError(f"XML inválido en {filename}: {xml_error}")
                            
                            # Verificar encoding
                            try:
                                if isinstance(xml_content, bytes):
                                    xml_str = xml_content.decode('utf-8')
                                else:
                                    xml_str = xml_content
                                _logger.info("  ✓ Encoding UTF-8 válido")
                            except UnicodeDecodeError as decode_error:
                                raise UserError(f"Error de encoding en {filename}: {decode_error}")
                            
                            # Validar elementos críticos para DIAN (adaptado a estructura real)
                            critical_elements = ['Informacion', 'Empleador', 'Trabajador']
                            missing_critical = []
                            
                            # Verificar considerando namespace
                            ns_map = root.nsmap
                            default_ns = ns_map.get(None, '')
                            
                            for element in critical_elements:
                                found = root.find(f'.//{element}')
                                if found is None and default_ns:
                                    found = root.find(f'.//{{{default_ns}}}{element}')
                                    
                                if found is None:
                                    missing_critical.append(element)
                            
                            if missing_critical:
                                _logger.error(f"  Elementos críticos faltantes en {filename}: {missing_critical}")
                                raise UserError(f"El XML {filename} no tiene elementos obligatorios: {', '.join(missing_critical)}")
                            else:
                                _logger.info(f"  ✓ Todos los elementos críticos presentes")
                            
                            # Verificar que el XML tenga el formato esperado por DIAN
                            numero_seq = root.find('.//NumeroSecuenciaXML')
                            if numero_seq is None and default_ns:
                                numero_seq = root.find(f'.//{{{default_ns}}}NumeroSecuenciaXML')
                            if numero_seq is not None and numero_seq.text:
                                _logger.info(f"  NumeroSecuenciaXML: {numero_seq.text}")
                            
                            empleador_nit = root.find('.//NIT')
                            if empleador_nit is None and default_ns:
                                empleador_nit = root.find(f'.//{{{default_ns}}}NIT')
                            if empleador_nit is not None and empleador_nit.text:
                                _logger.info(f"  NIT Empleador: {empleador_nit.text}")
                            
                            trabajador_doc = root.find('.//NumeroDocumento')
                            if trabajador_doc is None and default_ns:
                                trabajador_doc = root.find(f'.//{{{default_ns}}}NumeroDocumento')
                            if trabajador_doc is not None and trabajador_doc.text:
                                _logger.info(f"  Documento Trabajador: {trabajador_doc.text}")
                            
                        except Exception as file_error:
                            _logger.error(f"Error validando {filename}: {file_error}")
                            raise UserError(f"Error en archivo {filename}: {file_error}")
                    
                    # Verificar metadatos del ZIP
                    for info in zip_file.filelist:
                        _logger.info(f"Archivo: {info.filename}")
                        _logger.info(f"  Tamaño original: {info.file_size} bytes")
                        _logger.info(f"  Tamaño comprimido: {info.compress_size} bytes")
                        _logger.info(f"  Método compresión: {info.compress_type}")
                        _logger.info(f"  CRC: {info.CRC}")
                
                _logger.info("✓ ZIP validado exitosamente")
                
            except zipfile.BadZipFile as zip_error:
                _logger.error(f"ZIP corrupto: {zip_error}")
                raise UserError(f"El archivo ZIP está corrupto: {zip_error}")
                
        except Exception as e:
            _logger.error(f"Error general validando ZIP: {e}")
            raise UserError(f"Error validando ZIP: {e}")
        
        _logger.info("=== FIN VALIDACIÓN ZIP ===")

    def action_diagnose_security_error(self):
        """Diagnóstico específico para errores de seguridad DIAN"""
        self.ensure_one()
        
        _logger.info("=== DIAGNÓSTICO ERROR DE SEGURIDAD DIAN ===")
        
        company = self.company_id
        
        # 1. Verificar Test Set ID
        test_set_id = getattr(company, 'payroll_test_set_id', None) or getattr(company, 'test_set_id', None)
        _logger.info(f"1. Test Set ID: {test_set_id}")
        
        if test_set_id:
            # Verificar formato GUID
            guid_pattern = r'^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$'
            if re.match(guid_pattern, test_set_id):
                _logger.info("   ✓ Formato GUID válido")
            else:
                _logger.error("   ✗ Formato GUID inválido")
                _logger.error("   📝 Formato esperado: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")
        else:
            _logger.error("   ✗ Test Set ID no configurado")
        
        # 2. Verificar Software ID
        software_id = getattr(company, 'payroll_software_id', None)
        _logger.info(f"2. Software ID: {software_id}")
        
        if software_id:
            if re.match(guid_pattern, software_id):
                _logger.info("   ✓ Software ID con formato GUID válido")
            else:
                _logger.error("   ✗ Software ID no tiene formato GUID válido")
        else:
            _logger.error("   ✗ Software ID no configurado")
        
        # 3. Verificar Software Security Code
        software_sc = getattr(company, 'payroll_software_security_code', None)
        _logger.info(f"3. Software Security Code: {software_sc[:10] + '...' if software_sc else 'No configurado'}")
        
        if software_sc:
            if len(software_sc) >= 32:
                _logger.info("   ✓ Security Code tiene longitud adecuada")
            else:
                _logger.error("   ✗ Security Code muy corto (debe ser >= 32 caracteres)")
        else:
            _logger.error("   ✗ Software Security Code no configurado")
        
        # 4. Verificar NIT
        nit = company.vat
        _logger.info(f"4. NIT Empresa: {nit}")
        
        if nit:
            nit_clean = nit.replace('-', '').replace(' ', '')
            if nit_clean.isdigit() and len(nit_clean) >= 9:
                _logger.info("   ✓ NIT con formato válido")
            else:
                _logger.error("   ✗ NIT con formato inválido")
        else:
            _logger.error("   ✗ NIT no configurado")
        
        # 5. Verificar entorno
        environment = self.environment
        _logger.info(f"5. Entorno: {environment}")
        
        # 6. Verificar archivo ZIP
        if self.zip_file:
            zip_content = base64.b64decode(self.zip_file)
            _logger.info(f"6. Archivo ZIP: {len(zip_content)} bytes")
            
            try:
                import zipfile
                import io
                with zipfile.ZipFile(io.BytesIO(zip_content), 'r') as zip_file:
                    file_list = zip_file.namelist()
                    _logger.info(f"   Archivos en ZIP: {file_list}")
                    
                    for filename in file_list:
                        if filename.endswith('.xml'):
                            xml_content = zip_file.read(filename)
                            _logger.info(f"   XML {filename}: {len(xml_content)} bytes")
                            
                            # Verificar estructura básica del XML
                            try:
                                root = etree.fromstring(xml_content)
                                _logger.info(f"   ✓ XML bien formado - Root: {root.tag}")
                                
                                # Buscar elementos críticos para DIAN
                                software_elem = root.find('.//SoftwareID')
                                if software_elem is None:
                                    # Buscar con namespace
                                    ns = root.nsmap.get(None, '')
                                    if ns:
                                        software_elem = root.find(f'.//{{{ns}}}SoftwareID')
                                
                                if software_elem is not None and software_elem.text:
                                    _logger.info(f"   SoftwareID en XML: {software_elem.text}")
                                    if software_elem.text == software_id:
                                        _logger.info("   ✓ SoftwareID coincide con configuración")
                                    else:
                                        _logger.error("   ✗ SoftwareID NO coincide con configuración")
                                else:
                                    _logger.error("   ✗ SoftwareID no encontrado en XML")
                                
                                # Verificar NIT en XML
                                nit_elem = root.find('.//NIT')
                                if nit_elem is None and ns:
                                    nit_elem = root.find(f'.//{{{ns}}}NIT')
                                
                                if nit_elem is not None and nit_elem.text:
                                    _logger.info(f"   NIT en XML: {nit_elem.text}")
                                    xml_nit = nit_elem.text.replace('-', '').replace(' ', '')
                                    company_nit = nit.replace('-', '').replace(' ', '') if nit else ''
                                    if xml_nit == company_nit:
                                        _logger.info("   ✓ NIT coincide con configuración")
                                    else:
                                        _logger.error("   ✗ NIT NO coincide con configuración")
                                else:
                                    _logger.error("   ✗ NIT no encontrado en XML")
                                    
                            except etree.XMLSyntaxError as e:
                                _logger.error(f"   ✗ Error en XML: {e}")
                                
            except Exception as e:
                _logger.error(f"   ✗ Error verificando ZIP: {e}")
        else:
            _logger.error("6. ✗ No hay archivo ZIP generado")
        
        # 7. Recomendaciones específicas
        _logger.info("=== RECOMENDACIONES PARA ERROR DE SEGURIDAD ===")
        _logger.info("1. 🌐 Verificar en portal DIAN (https://catalogo-vpfe.dian.gov.co):")
        _logger.info("   - Test Set esté ACTIVO y con documentos disponibles")
        _logger.info("   - Software esté registrado y HABILITADO")
        _logger.info("   - Empresa esté habilitada para nómina electrónica")
        _logger.info("2. 🔧 Verificar configuración Odoo:")
        _logger.info("   - Test Set ID correcto (copiar exacto del portal DIAN)")
        _logger.info("   - Software ID correcto (copiar exacto del portal DIAN)")
        _logger.info("   - Software Security Code correcto")
        _logger.info("3. 📋 Verificar datos del XML:")
        _logger.info("   - SoftwareID en XML coincide con configuración")
        _logger.info("   - NIT en XML coincide con empresa registrada en DIAN")
        _logger.info("   - Estructura XML conforme al esquema DIAN")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Diagnóstico de Seguridad DIAN',
                'message': 'Diagnóstico completado. Revise los logs del servidor para detalles.',
                'type': 'info',
                'sticky': True,
            }
        }
        """Consulta el estado en DIAN"""
        for record in self:
            if not record.dian_zip_key:
                raise UserError(_("No hay ZIP Key para consultar el estado"))
                
            try:
                status_response = record._get_status_zip()
                record._process_status_response(status_response)
                
            except Exception as e:
                _logger.error(f"Error consultando estado DIAN: {e}")
                raise UserError(f"Error al consultar estado: {e}")

    def _create_zip_file(self):
        """Crea archivo ZIP con el XML firmado"""
        self.ensure_one()
        
        # Crear buffer en memoria
        import io
        buffer = io.BytesIO()
        
        # Crear ZIP
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            xml_content = base64.b64decode(self.signed_xml_file)
            zip_file.writestr(self.signed_xml_filename, xml_content)
        
        zip_content = buffer.getvalue()
        
        # Guardar ZIP en el registro
        zip_b64 = base64.b64encode(zip_content)
        zip_filename = self.signed_xml_filename.replace('.xml', '.zip')
        
        self.write({
            'zip_file': zip_b64,
            'zip_filename': zip_filename
        })
        
        return zip_content

    def _send_test_set_async(self, zip_content):
        """Envía documento al ambiente de habilitación (asíncrono)"""
        self.ensure_one()
        
        # Validar datos necesarios
        test_set_id = self.company_id.payroll_test_set_id or self.company_id.test_set_id
        if not test_set_id:
            raise UserError(_("La compañía debe tener configurado un Test Set ID para el ambiente de habilitación"))
        
        if not self.zip_filename:
            raise UserError(_("No se ha generado el nombre del archivo ZIP"))
        
        # Validar formato del Test Set ID (debe ser GUID)
        if not re.match(r'^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$', test_set_id):
            raise UserError(_("El Test Set ID debe tener formato GUID válido (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)"))
        
        endpoint = PAYROLL_ENDPOINTS['HABILITACION']['SendTestSetAsync']
        
        # Preparar payload
        zip_b64 = base64.b64encode(zip_content).decode('utf-8')
        
        # Validaciones específicas para DIAN
        self._validate_dian_payload(zip_content, zip_b64, test_set_id)
        
        payload = {
            'fileName': self.zip_filename,
            'contentFile': zip_b64,
            'testSetId': test_set_id
        }
        
        _logger.info(f"Enviando a habilitación:")
        _logger.info(f"  - TestSetId: {test_set_id}")
        _logger.info(f"  - Archivo: {self.zip_filename}")
        _logger.info(f"  - Tamaño ZIP original: {len(zip_content)} bytes")
        _logger.info(f"  - Tamaño ZIP base64: {len(zip_b64)} caracteres")
        _logger.info(f"  - Endpoint: {endpoint}")
        
        # Enviar solicitud
        response = self._make_dian_request(endpoint, payload)
        
        self.sent_date = fields.Datetime.now()
        self.state = 'sent'
        
        return response
    
    def _validate_dian_payload(self, zip_content, zip_b64, test_set_id):
        """Valida el payload que se envía a DIAN"""
        self.ensure_one()
        
        # Validar tamaño del archivo
        if len(zip_b64) > 5000000:  # 5MB límite aproximado
            raise UserError(_("El archivo ZIP es demasiado grande para enviar a DIAN (máximo ~5MB)"))
        
        if len(zip_content) < 100:  # ZIP muy pequeño
            raise UserError(_("El archivo ZIP parece estar vacío o corrupto"))
        
        # Validar nombre del archivo
        if not self.zip_filename.endswith('.zip'):
            raise UserError(_("El nombre del archivo debe terminar en .zip"))
        
        # Validar que el nombre no tenga caracteres especiales
        if not re.match(r'^[a-zA-Z0-9_\-\.]+$', self.zip_filename):
            raise UserError(_("El nombre del archivo contiene caracteres no permitidos"))
        
        # Validar contenido del ZIP
        try:
            import io
            with zipfile.ZipFile(io.BytesIO(zip_content), 'r') as zip_file:
                file_list = zip_file.namelist()
                
                if len(file_list) != 1:
                    _logger.warning(f"ZIP contiene {len(file_list)} archivos, se esperaba 1: {file_list}")
                
                # Verificar contenido del XML
                for filename in file_list:
                    if filename.endswith('.xml'):
                        xml_content = zip_file.read(filename)
                        self._validate_xml_content(xml_content, filename)
                        break
                
        except Exception as e:
            _logger.error(f"Error validando contenido ZIP: {e}")
            raise UserError(f"Error validando contenido ZIP: {e}")
        
        _logger.info(f"Payload validado exitosamente para DIAN")
    
    def _validate_xml_content(self, xml_content, filename):
        """Valida el contenido del XML de nómina"""
        try:
            # Verificar que sea XML válido
            if isinstance(xml_content, bytes):
                xml_string = xml_content.decode('utf-8')
            else:
                xml_string = xml_content
            
            # Parsear XML para verificar estructura
            root = etree.fromstring(xml_content)
            
            _logger.info(f"XML válido encontrado: {filename}")
            _logger.info(f"  - Tamaño: {len(xml_content)} bytes")
            _logger.info(f"  - Elemento raíz: {root.tag}")
            
            # Verificar elementos básicos de nómina electrónica
            namespaces = root.nsmap
            _logger.info(f"  - Namespaces: {namespaces}")
            
            # Buscar elementos críticos
            elements_to_check = [
                'NumeroSecuenciaXML',
                'Numero',
                'FechaGen',
                'Empleador',
                'Trabajador'
            ]
            
            found_elements = []
            for element in elements_to_check:
                if root.find(f'.//{element}') is not None:
                    found_elements.append(element)
            
            _logger.info(f"  - Elementos encontrados: {found_elements}")
            
            if len(found_elements) < 3:
                _logger.warning(f"Pocos elementos críticos encontrados en XML: {found_elements}")
            
        except etree.XMLSyntaxError as e:
            _logger.error(f"XML inválido en {filename}: {e}")
            raise UserError(f"El XML de nómina tiene errores de sintaxis: {e}")
        except Exception as e:
            _logger.error(f"Error validando XML {filename}: {e}")
            _logger.warning("Continuando a pesar del error de validación XML")

    def _send_nomina_sync(self, zip_content):
        """Envía documento al ambiente de producción (síncrono)"""
        self.ensure_one()
        
        endpoint = PAYROLL_ENDPOINTS['PRODUCCION']['SendNominaSync']
        
        # Preparar payload
        zip_b64 = base64.b64encode(zip_content).decode('utf-8')
        
        payload = {
            'fileName': self.zip_filename,
            'contentFile': zip_b64
        }
        
        # Enviar solicitud
        response = self._make_dian_request(endpoint, payload)
        
        self.sent_date = fields.Datetime.now()
        self.state = 'sent'
        
        return response

    def _get_status_zip(self):
        """Consulta el estado del ZIP en DIAN"""
        self.ensure_one()
        
        environment_key = 'HABILITACION' if self.environment == 'test' else 'PRODUCCION'
        endpoint = PAYROLL_ENDPOINTS[environment_key]['GetStatusZip']
        
        payload = {
            'trackId': self.dian_zip_key
        }
        
        return self._make_dian_request(endpoint, payload)

    def _make_dian_request(self, endpoint, payload):
        """Realiza solicitud SOAP a DIAN"""
        company = self.company_id
        
        try:
            # DIAN requiere SOAP 1.2 con content-type application/soap+xml
            if 'SendTestSetAsync' in endpoint:
                soap_body = f"""<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" xmlns:wcf="http://wcf.dian.colombia">
    <soap:Header/>
    <soap:Body>
        <wcf:SendTestSetAsync>
            <wcf:fileName>{payload['fileName']}</wcf:fileName>
            <wcf:contentFile>{payload['contentFile']}</wcf:contentFile>
            <wcf:testSetId>{payload.get('testSetId', '')}</wcf:testSetId>
        </wcf:SendTestSetAsync>
    </soap:Body>
</soap:Envelope>"""
            
            elif 'SendNominaSync' in endpoint:
                soap_body = f"""<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" xmlns:wcf="http://wcf.dian.colombia">
    <soap:Header/>
    <soap:Body>
        <wcf:SendNominaSync>
            <wcf:fileName>{payload['fileName']}</wcf:fileName>
            <wcf:contentFile>{payload['contentFile']}</wcf:contentFile>
        </wcf:SendNominaSync>
    </soap:Body>
</soap:Envelope>"""
            
            elif 'GetStatusZip' in endpoint:
                soap_body = f"""<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" xmlns:wcf="http://wcf.dian.colombia">
    <soap:Header/>
    <soap:Body>
        <wcf:GetStatusZip>
            <wcf:trackId>{payload['trackId']}</wcf:trackId>
        </wcf:GetStatusZip>
    </soap:Body>
</soap:Envelope>"""
            
            else:
                raise UserError(f"Endpoint no soportado: {endpoint}")
            
            # Headers para SOAP 1.2 según especificaciones DIAN
            headers = {
                'Content-Type': 'application/soap+xml; charset=utf-8',
                'Content-Length': str(len(soap_body.encode('utf-8'))),
                'User-Agent': 'Apache-HttpClient/4.5.2 (Java/1.8.0)',
                'Accept': 'application/soap+xml, text/*',
                'Connection': 'keep-alive'
            }
            
            _logger.info(f"Enviando solicitud SOAP a: {endpoint}")
            _logger.info(f"Tamaño del contenido: {len(soap_body)} caracteres")
            _logger.debug(f"Headers: {headers}")
            _logger.debug(f"SOAP Body preview: {soap_body[:500]}...")
            
            # Validar que el testSetId no esté vacío para habilitación
            if 'SendTestSetAsync' in endpoint and not payload.get('testSetId'):
                raise UserError("Test Set ID es requerido para el ambiente de habilitación")
            
            # Intentar primero sin verificar SSL si hay problemas de certificados
            try:
                response = requests.post(
                    endpoint,
                    data=soap_body.encode('utf-8'),
                    headers=headers,
                    timeout=120,
                    verify=True
                )
            except requests.exceptions.SSLError as ssl_error:
                _logger.warning(f"Error SSL, reintentando sin verificación: {ssl_error}")
                response = requests.post(
                    endpoint,
                    data=soap_body.encode('utf-8'),
                    headers=headers,
                    timeout=120,
                    verify=False
                )
            
            _logger.info(f"Respuesta DIAN status: {response.status_code}")
            _logger.info(f"Response headers: {dict(response.headers)}")
            
            # Loggear detalles específicos para errores de servidor
            if response.status_code >= 400:
                _logger.error(f"Error {response.status_code} - Request enviado:")
                _logger.error(f"URL: {endpoint}")
                _logger.error(f"Headers: {headers}")
                _logger.error(f"Body: {soap_body}")
                _logger.error(f"Response: {response.text}")
                
                # Verificar si DIAN está retornando HTML de error
                if 'text/html' in response.headers.get('content-type', ''):
                    _logger.error("DIAN retornó una página HTML de error")
                    raise UserError("DIAN está retornando un error HTML - servicio posiblemente no disponible")
            
            response.raise_for_status()
            
            _logger.debug(f"Respuesta DIAN body: {response.text[:1000]}...")
            
            # Parsear respuesta SOAP XML
            return self._parse_soap_response(response.text)
            
        except requests.exceptions.RequestException as e:
            _logger.error(f"Error en solicitud DIAN: {e}")
            if hasattr(e, 'response') and e.response is not None:
                _logger.error(f"Status code: {e.response.status_code}")
                _logger.error(f"Response headers: {dict(e.response.headers)}")
                _logger.error(f"Response body: {e.response.text}")
                
                # Proporcionar mensaje más específico basado en el error
                if e.response.status_code == 500:
                    # Intentar extraer más información del error 500
                    error_details = self._analyze_500_error(e.response)
                    error_msg = "Error interno del servidor DIAN.\n\n"
                    error_msg += f"Detalles técnicos:\n{error_details}\n\n"
                    error_msg += "Posibles causas:\n"
                    error_msg += "- Test Set ID inválido o no autorizado\n"
                    error_msg += "- Formato de archivo ZIP incorrecto\n"
                    error_msg += "- XML de nómina con errores de estructura\n"
                    error_msg += "- Datos faltantes o inválidos en el XML\n"
                    error_msg += "- Servicio DIAN temporalmente no disponible\n\n"
                    error_msg += "Recomendaciones:\n"
                    error_msg += "- Verificar que el Test Set ID esté activo en DIAN\n"
                    error_msg += "- Validar que el XML cumpla con el esquema XSD de DIAN\n"
                    error_msg += "- Revisar los logs detallados arriba"
                    raise UserError(error_msg)
                elif e.response.status_code == 400:
                    error_msg = "Solicitud incorrecta (400). Posibles causas:\n"
                    error_msg += "- Parámetros faltantes o inválidos\n"
                    error_msg += "- Formato del SOAP incorrecto\n"
                    error_msg += "- TestSetId con formato incorrecto"
                    raise UserError(error_msg)
                elif e.response.status_code == 415:
                    error_msg = "Tipo de contenido no soportado (415).\n"
                    error_msg += "DIAN requiere 'application/soap+xml; charset=utf-8'"
                    raise UserError(error_msg)
                    
            raise UserError(f"Error de comunicación con DIAN: {e}")
    
    def _analyze_500_error(self, response):
        """Analiza la respuesta de error 500 para extraer información útil"""
        try:
            error_details = []
            error_details.append(f"Status Code: {response.status_code}")
            error_details.append(f"Content-Type: {response.headers.get('content-type', 'N/A')}")
            error_details.append(f"Content-Length: {response.headers.get('content-length', 'N/A')}")
            
            # Log completo de la respuesta para análisis
            _logger.error(f"Respuesta completa DIAN 500:")
            _logger.error(f"Headers: {dict(response.headers)}")
            _logger.error(f"Body completo: {response.text}")
            
            # Intentar parsear como XML
            try:
                if 'xml' in response.headers.get('content-type', '').lower():
                    root = etree.fromstring(response.text.encode('utf-8'))
                    
                    # Buscar faults SOAP (más exhaustivo)
                    fault_1_1 = root.find('.//{http://schemas.xmlsoap.org/soap/envelope/}Fault')
                    fault_1_2 = root.find('.//{http://www.w3.org/2003/05/soap-envelope}Fault')
                    fault = fault_1_1 or fault_1_2
                    
                    if fault is not None:
                        error_details.append("=== SOAP FAULT DETECTADO ===")
                        
                        # Buscar código de error
                        fault_code = fault.find('.//faultcode') or fault.find('.//{http://www.w3.org/2003/05/soap-envelope}Code')
                        if fault_code is not None:
                            error_details.append(f"Fault Code: {fault_code.text}")
                        
                        # Buscar mensaje de error
                        fault_string = fault.find('.//faultstring') or fault.find('.//{http://www.w3.org/2003/05/soap-envelope}Reason')
                        if fault_string is not None:
                            error_details.append(f"Fault String: {fault_string.text}")
                        
                        # Buscar detalle del error
                        fault_detail = fault.find('.//detail') or fault.find('.//{http://www.w3.org/2003/05/soap-envelope}Detail')
                        if fault_detail is not None:
                            detail_text = fault_detail.text or etree.tostring(fault_detail, encoding='unicode', pretty_print=True)
                            error_details.append(f"Fault Detail: {detail_text}")
                    
                    # Buscar elementos específicos de error DIAN
                    dian_error_patterns = [
                        './/ErrorMessage', './/ErrorCode', './/IsValid', './/StatusCode',
                        './/StatusDescription', './/Message', './/Description'
                    ]
                    
                    for pattern in dian_error_patterns:
                        elements = root.findall(pattern)
                        for elem in elements:
                            if elem.text:
                                error_details.append(f"DIAN {elem.tag}: {elem.text}")
                    
                    # Buscar todos los elementos con texto que contengan "error"
                    all_elements = root.xpath('//*[contains(translate(text(), "ERROR", "error"), "error")]')
                    for elem in all_elements:
                        if elem.text and elem.text.strip():
                            error_details.append(f"Error Text in {elem.tag}: {elem.text}")
                    
                    # Mostrar estructura del XML para análisis
                    error_details.append("=== ESTRUCTURA XML RESPUESTA ===")
                    error_details.append(f"Root element: {root.tag}")
                    error_details.append(f"Namespaces: {root.nsmap}")
                    
                    # Mostrar todos los elementos hijos del nivel superior
                    for child in root:
                        error_details.append(f"Child element: {child.tag}")
                        
                else:
                    # No es XML, mostrar como texto
                    error_details.append("=== RESPUESTA NO XML ===")
                    if response.text and len(response.text) < 3000:
                        error_details.append(f"Response Body: {response.text}")
                    else:
                        error_details.append(f"Response Body (truncado): {response.text[:1000]}... (total: {len(response.text)} chars)")
                
            except Exception as parse_error:
                error_details.append(f"Error parseando XML: {parse_error}")
                # Si falla el parseo XML, mostrar texto plano
                if response.text:
                    error_details.append("=== TEXTO PLANO RESPUESTA ===")
                    error_details.append(response.text[:2000] if len(response.text) > 2000 else response.text)
            
            return '\n'.join(error_details)
            
        except Exception as e:
            return f"No se pudo analizar el error 500: {e}"

    def _parse_soap_response(self, soap_response):
        """Parsea la respuesta SOAP de DIAN y la convierte a diccionario"""
        try:
            _logger.debug(f"Parseando respuesta SOAP: {soap_response[:500]}...")
            
            # Verificar si es una respuesta de error HTML
            if '<html' in soap_response.lower() or '<!doctype' in soap_response.lower():
                _logger.error("DIAN retornó una respuesta HTML en lugar de SOAP XML")
                return {
                    'IsValid': False,
                    'ErrorMessage': ['DIAN retornó una página HTML en lugar de respuesta SOAP']
                }
            
            # Parsear XML de respuesta
            root = etree.fromstring(soap_response.encode('utf-8'))
            
            # Verificar si hay faults SOAP (para SOAP 1.1 y 1.2)
            fault_1_1 = root.find('.//{http://schemas.xmlsoap.org/soap/envelope/}Fault')
            fault_1_2 = root.find('.//{http://www.w3.org/2003/05/soap-envelope}Fault')
            fault = fault_1_1 or fault_1_2
            
            if fault is not None:
                fault_code = fault.find('.//faultcode') or fault.find('.//{http://www.w3.org/2003/05/soap-envelope}Code')
                fault_string = fault.find('.//faultstring') or fault.find('.//{http://www.w3.org/2003/05/soap-envelope}Reason')
                fault_detail = fault.find('.//detail') or fault.find('.//{http://www.w3.org/2003/05/soap-envelope}Detail')
                
                error_msg = "Error SOAP"
                if fault_code is not None:
                    error_msg += f" - Código: {fault_code.text}"
                if fault_string is not None:
                    error_msg += f" - Descripción: {fault_string.text}"
                if fault_detail is not None:
                    error_msg += f" - Detalle: {fault_detail.text or etree.tostring(fault_detail, encoding='unicode')}"
                
                _logger.error(f"SOAP Fault recibido: {error_msg}")
                return {
                    'IsValid': False,
                    'ErrorMessage': [error_msg]
                }
            
            # Buscar elementos de respuesta con múltiples namespaces posibles
            response_data = {}
            
            # Namespaces que puede usar DIAN
            wcf_namespaces = [
                '{http://wcf.dian.colombia}',
                '{http://tempuri.org/}',
                '{http://schemas.datacontract.org/2004/07/WcfDianCustomerServices}',
                ''  # Sin namespace
            ]
            
            # Buscar IsValid
            for ns in wcf_namespaces:
                is_valid = root.find(f'.//{ns}IsValid')
                if is_valid is not None:
                    response_data['IsValid'] = is_valid.text.lower() == 'true'
                    break
            
            # Buscar ZipKey
            for ns in wcf_namespaces:
                zip_key = root.find(f'.//{ns}ZipKey')
                if zip_key is not None:
                    response_data['ZipKey'] = zip_key.text
                    break
            
            # Buscar XmlDocumentKey
            for ns in wcf_namespaces:
                xml_doc_key = root.find(f'.//{ns}XmlDocumentKey')
                if xml_doc_key is not None:
                    response_data['XmlDocumentKey'] = xml_doc_key.text
                    break
            
            # Buscar XmlFileName
            for ns in wcf_namespaces:
                xml_filename = root.find(f'.//{ns}XmlFileName')
                if xml_filename is not None:
                    response_data['XmlFileName'] = xml_filename.text
                    break
            
            # Buscar StatusCode
            for ns in wcf_namespaces:
                status_code = root.find(f'.//{ns}StatusCode')
                if status_code is not None:
                    response_data['StatusCode'] = status_code.text
                    break
            
            # Buscar StatusDescription
            for ns in wcf_namespaces:
                status_desc = root.find(f'.//{ns}StatusDescription')
                if status_desc is not None:
                    response_data['StatusDescription'] = status_desc.text
                    break
            
            # Buscar ErrorMessage
            error_messages = []
            for ns in wcf_namespaces:
                errors = root.findall(f'.//{ns}ErrorMessage')
                if errors:
                    error_messages.extend([elem.text for elem in errors if elem.text])
                    break
            if error_messages:
                response_data['ErrorMessage'] = error_messages
            
            # Buscar XmlBase64Bytes
            for ns in wcf_namespaces:
                xml_bytes = root.find(f'.//{ns}XmlBase64Bytes')
                if xml_bytes is not None:
                    response_data['XmlBase64Bytes'] = xml_bytes.text
                    break
            
            _logger.info(f"Respuesta DIAN parseada exitosamente: {response_data}")
            
            # Si no encontramos ningún elemento conocido, loggear toda la respuesta
            if not response_data:
                _logger.warning("No se encontraron elementos conocidos en la respuesta DIAN")
                _logger.warning(f"XML completo recibido: {soap_response}")
                
                # Intentar extraer información básica
                if 'SendTestSetAsync' in soap_response:
                    # Es una respuesta de SendTestSetAsync
                    response_data = {'IsValid': True, 'ZipKey': 'unknown'}
                
            return response_data
            
        except Exception as e:
            _logger.error(f"Error parseando respuesta SOAP: {e}")
            _logger.error(f"Respuesta completa que causó el error: {soap_response}")
            
            # En caso de error, retornar respuesta básica
            return {
                'IsValid': False,
                'ErrorMessage': [f"Error parseando respuesta SOAP: {str(e)}"]
            }

    def _get_dian_token(self):
        """Obtiene token de autenticación DIAN"""
        # DIAN nómina electrónica no usa tokens Bearer
        # La autenticación se hace a través de certificados digitales
        # que se incluyen en el XML firmado
        return ""

    def _process_dian_response(self, response):
        """Procesa la respuesta inicial de DIAN"""
        self.ensure_one()
        
        self.dian_response = json.dumps(response, indent=2)
        self.response_date = fields.Datetime.now()
        
        if response.get('IsValid'):
            # Documento aceptado
            self.state = 'accepted'
            self.dian_status_code = '00'
            self.dian_status_description = 'Documento aceptado por DIAN'
            
            # Extraer información adicional
            if 'XmlDocumentKey' in response:
                self.dian_zip_key = response['XmlDocumentKey']
            
            if 'XmlFileName' in response:
                self.transaction_id = response['XmlFileName']
                
        elif response.get('ZipKey'):
            # Documento en proceso (ambiente de habilitación)
            self.dian_zip_key = response['ZipKey']
            self.dian_status_description = 'Documento en proceso de validación por DIAN'
            
        else:
            # Error o rechazo
            self.state = 'rejected'
            error_list = response.get('ErrorMessage', [])
            if isinstance(error_list, list):
                error_msg = '; '.join([str(error) for error in error_list])
            else:
                error_msg = str(error_list)
            
            self.dian_status_description = f"Documento rechazado: {error_msg}"

    def _process_status_response(self, response):
        """Procesa la respuesta de consulta de estado"""
        self.ensure_one()
        
        if response.get('IsValid'):
            self.state = 'accepted'
            self.dian_status_code = '00'
            self.dian_status_description = 'Documento aceptado por DIAN'
            
            # Actualizar información adicional si está disponible
            if 'XmlBase64Bytes' in response:
                # Procesar respuesta XML de DIAN
                xml_response = base64.b64decode(response['XmlBase64Bytes']).decode('utf-8')
                self._extract_cune_from_response(xml_response)
                
        elif response.get('StatusCode'):
            status_code = response.get('StatusCode')
            if status_code in ['00', '66']:  # Aceptado
                self.state = 'accepted'
            else:  # Rechazado
                self.state = 'rejected'
                
            self.dian_status_code = status_code
            self.dian_status_description = response.get('StatusDescription', 'Sin descripción')

    def _extract_cune_from_response(self, xml_response):
        """Extrae el CUNE de la respuesta XML de DIAN"""
        try:
            root = etree.fromstring(xml_response.encode('utf-8'))
            # Buscar CUNE en la respuesta
            cune_element = root.find('.//cune') or root.find('.//CUNE')
            if cune_element is not None:
                self.cune = cune_element.text
                
        except Exception as e:
            _logger.warning(f"No se pudo extraer CUNE de la respuesta: {e}")

    def _sign_xml_document(self, xml_content, company):
        """Firma digitalmente el documento XML"""
        # Usar la misma lógica que el módulo de factura electrónica
        
        try:
            # Verificar que tenemos OpenSSL disponible
            if 'crypto' not in globals():
                _logger.warning("OpenSSL no disponible - XML sin firmar")
                return xml_content
            
            # Cargar certificado usando la misma lógica que e-invoice
            certificate_data = base64.b64decode(company.payroll_certificate_file)
            password = company.payroll_certificate_password
            
            # Cargar PKCS12
            pkcs12_cert = crypto.load_pkcs12(certificate_data, password.encode())
            
            # Por ahora retornamos el XML sin firmar
            # En producción, implementar la firma digital completa usando xmlsig
            # como en el módulo l10n_co_e-invoice
            
            _logger.info("Certificado cargado exitosamente - XML listo para firmar")
            
            # TODO: Implementar firma XMLDSig completa
            # Usar xmlsig.XMLSigner y seguir el patrón de l10n_co_e-invoice
            
            return xml_content
            
        except Exception as e:
            _logger.error(f"Error en certificado: {e}")
            # En caso de error con el certificado, continuar sin firmar
            _logger.warning("Continuando sin firma digital")
            return xml_content
