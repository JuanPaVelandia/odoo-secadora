# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class LavishXmlGeneratorHeader(models.Model):
    _name = 'lavish.xml.generator.header'
    _description = 'Generador de XML para Documentos Electrónicos'

    name = fields.Char('Nombre', required=True)
    code = fields.Char('Código', required=True, help="Identificador único para el tipo de XML")
    active = fields.Boolean('Activo', default=True)
    xml_template = fields.Text('Template XML', help="Template base para generar el XML")
    details_ids = fields.One2many('lavish.xml.generator.detail', 'header_id', string='Detalles')
    
    def xml_generator(self, electronic_payroll_detail=None):
        """
        Genera el XML de nómina electrónica usando el template configurado
        """
        from datetime import datetime
        import logging
        _logger = logging.getLogger(__name__)
        
        # Obtener los datos de la nómina electrónica
        if electronic_payroll_detail:
            try:
                # electronic_payroll_detail es un objeto hr.electronic.payroll.detail
                payroll = electronic_payroll_detail
            except (KeyError, AttributeError):
                payroll = None
        else:
            payroll = None

        # Si tenemos template configurado, usarlo
        if self.xml_template and self.xml_template.strip():
            # Obtener fecha y hora actuales
            now = datetime.now()
            fecha_generacion = now.strftime('%Y-%m-%d')
            hora_generacion = now.strftime('%H:%M:%S-05:00')

            # Preparar los datos para reemplazar en el template
            if payroll:
                # Obtener company datos de forma segura
                company = getattr(payroll, 'electronic_payroll_id', None)
                company = getattr(company, 'company_id', None) if company else None
                
                # Obtener employee datos de forma segura  
                employee = getattr(payroll, 'employee_id', None)
                
                # Log para debug
                _logger.info(f"=== DEBUG GENERADOR XML ===")
                _logger.info(f"Payroll ID: {payroll.id if payroll else 'None'}")
                _logger.info(f"Company: {company.name if company else 'None'}")
                _logger.info(f"Employee: {employee.name if employee else 'None'}")
                _logger.info(f"Employee ID: {employee.identification_id if employee else 'None'}")
                
                # Parsear el nombre completo del empleado
                employee_name = getattr(employee, 'name', 'Nombre Apellido') if employee else 'Nombre Apellido'
                name_parts = employee_name.split()
                
                # Extraer nombres y apellidos (formato común: Nombre1 Nombre2 Apellido1 Apellido2)
                if len(name_parts) >= 4:
                    primer_nombre = name_parts[0]
                    segundo_nombre = name_parts[1] if len(name_parts) > 1 else ''
                    primer_apellido = name_parts[-2] if len(name_parts) >= 2 else 'Apellido1'
                    segundo_apellido = name_parts[-1] if len(name_parts) >= 1 else 'Apellido2'
                elif len(name_parts) >= 3:
                    primer_nombre = name_parts[0]
                    segundo_nombre = ''
                    primer_apellido = name_parts[1]
                    segundo_apellido = name_parts[2]
                elif len(name_parts) >= 2:
                    primer_nombre = name_parts[0]
                    segundo_nombre = ''
                    primer_apellido = name_parts[1]
                    segundo_apellido = ''
                else:
                    primer_nombre = name_parts[0] if name_parts else 'Nombre1'
                    segundo_nombre = ''
                    primer_apellido = 'Apellido1'
                    segundo_apellido = 'Apellido2'
                
                _logger.info(f"Nombres parseados - Primer: {primer_nombre}, Segundo: {segundo_nombre}, Apellido1: {primer_apellido}, Apellido2: {segundo_apellido}")
                
                replacement_data = {
                    # Fechas y tiempos
                    'fecha_generacion': fecha_generacion,
                    'hora_generacion': hora_generacion,
                    'fecha_inicio_periodo': payroll.get_dates_process(end=0) if hasattr(payroll, 'get_dates_process') else fecha_generacion,
                    'fecha_fin_periodo': payroll.get_dates_process(end=1) if hasattr(payroll, 'get_dates_process') else fecha_generacion,
                    'tiempo_laborado': '30',
                    
                    # Consecutivo y secuencia
                    'consecutivo': str(getattr(payroll, 'item', 1)).zfill(6),
                    'prefijo': 'NE',
                    
                    # Datos del empleador
                    'razon_social_empleador': getattr(company, 'name', 'Empresa Test') if company else 'Empresa Test',
                    'nit_empleador': (getattr(company, 'vat', '900123456') if company else '900123456').replace('-', '').replace(' ', ''),
                    'dv_empleador': '1',
                    'direccion_empleador': getattr(company, 'street', 'Dirección Test') if company else 'Dirección Test',
                    
                    # Software DIAN (obtener de configuración de company)
                    'software_id': getattr(company, 'payroll_software_id', '12345678-1234-1234-1234-123456789012') if company else '12345678-1234-1234-1234-123456789012',
                    'software_security_code': getattr(company, 'payroll_software_security_code', 'abcd1234567890abcdef1234567890abcdef12') if company else 'abcd1234567890abcdef1234567890abcdef12',
                    
                    # Datos del trabajador (usando nombres correctos del template)
                    'tipo_trabajador': '01',
                    'subtipo_trabajador': '00',
                    'alto_riesgo_pension': 'false',
                    'tipo_documento_trabajador': '13',  # CC - Cédula de Ciudadanía
                    'numero_documento_trabajador': getattr(employee, 'identification_id', '12345678') if employee else '12345678',
                    'primer_apellido_trabajador': primer_apellido,
                    'segundo_apellido_trabajador': segundo_apellido,
                    'primer_nombre_trabajador': primer_nombre,
                    'otros_nombres_trabajador': segundo_nombre,                    # Lugar de trabajo
                    'departamento_trabajo': '11',  # Bogotá D.C.
                    'municipio_trabajo': '11001',  # Bogotá D.C.
                    'direccion_trabajo': getattr(company, 'street', 'Dirección Trabajo') if company else 'Dirección Trabajo',
                    
                    # Contrato y salario
                    'tipo_contrato': '1',  # Término indefinido
                    'sueldo_trabajador': '1000000.00',
                    'codigo_trabajador': str(getattr(employee, 'id', 1)) if employee else '1',
                    
                    # Bancarios (no están en template pero por si se necesitan)
                    'banco': '001',
                    'tipo_cuenta': 'AHORROS', 
                    'numero_cuenta': '1234567890',
                    'fecha_pago': fecha_generacion,
                    
                    # Devengados y deducciones
                    'dias_trabajados': '30',
                    'sueldo_trabajado': '1000000.00',
                    'auxilio_transporte': '140606.00',  # Auxilio de transporte 2024
                    'devengados_total': '1140606.00',   # sueldo + auxilio transporte
                    'deduccion_salud': '40000.00',      # 4% del sueldo
                    'deduccion_pension': '40000.00',    # 4% del sueldo  
                    'deducciones_total': '80000.00',    # salud + pensión
                    'comprobante_total': '1060606.00'   # devengados - deducciones
                }
                
                # Log de las variables que se van a reemplazar
                _logger.info(f"=== VARIABLES DE REEMPLAZO ===")
                for key, value in replacement_data.items():
                    _logger.info(f"{key}: {value}")
                    
            else:
                # Datos de ejemplo usando variables correctas del template
                replacement_data = {
                    # Fechas y tiempos
                    'fecha_generacion': fecha_generacion,
                    'hora_generacion': hora_generacion,
                    'fecha_inicio_periodo': fecha_generacion,
                    'fecha_fin_periodo': fecha_generacion,
                    'tiempo_laborado': '30',
                    
                    # Consecutivo y secuencia
                    'consecutivo': '000001',
                    'prefijo': 'NE',
                    
                    # Datos del empleador
                    'razon_social_empleador': 'Empresa Test',
                    'nit_empleador': '900123456',
                    'dv_empleador': '1',
                    'direccion_empleador': 'Dirección Test',
                    
                    # Software DIAN
                    'software_id': '12345678-1234-1234-1234-123456789012',
                    'software_security_code': 'abcd1234567890abcdef1234567890abcdef12',
                    
                    # Datos del trabajador (usando nombres correctos del template)
                    'tipo_trabajador': '01',
                    'subtipo_trabajador': '00',
                    'alto_riesgo_pension': 'false',
                    'tipo_documento_trabajador': '13',  # CC - Cédula de Ciudadanía
                    'numero_documento_trabajador': '12345678',
                    'primer_apellido_trabajador': 'Apellido1',
                    'segundo_apellido_trabajador': 'Apellido2',
                    'primer_nombre_trabajador': 'Nombre1',
                    'otros_nombres_trabajador': '',
                    
                    # Lugar de trabajo
                    'departamento_trabajo': '11',  # Bogotá D.C.
                    'municipio_trabajo': '11001',  # Bogotá D.C.
                    'direccion_trabajo': 'Dirección Trabajo',
                    
                    # Contrato y salario
                    'tipo_contrato': '1',  # Término indefinido
                    'sueldo_trabajador': '1000000.00',
                    'codigo_trabajador': '1',
                    
                    # Bancarios (no están en template pero por si se necesitan)
                    'banco': '001',
                    'tipo_cuenta': 'AHORROS',
                    'numero_cuenta': '1234567890',
                    'fecha_pago': fecha_generacion,
                    
                    # Devengados y deducciones
                    'dias_trabajados': '30',
                    'sueldo_trabajado': '1000000.00',
                    'auxilio_transporte': '140606.00',  # Auxilio de transporte 2024
                    'devengados_total': '1140606.00',   # sueldo + auxilio transporte
                    'deduccion_salud': '40000.00',      # 4% del sueldo
                    'deduccion_pension': '40000.00',    # 4% del sueldo
                    'deducciones_total': '80000.00',    # salud + pensión
                    'comprobante_total': '1060606.00'   # devengados - deducciones
                }

            # Generar el XML reemplazando las variables en el template
            xml_content = self.xml_template
            for key, value in replacement_data.items():
                xml_content = xml_content.replace('{' + key + '}', str(value))

            # Verificar variables sin reemplazar
            import re
            unreplaced_vars = re.findall(r'\{[^}]+\}', xml_content)
            if unreplaced_vars:
                _logger.warning(f"=== VARIABLES SIN REEMPLAZAR ===")
                for var in set(unreplaced_vars):
                    _logger.warning(f"Variable sin reemplazar: {var}")
            else:
                _logger.info("✓ Todas las variables han sido reemplazadas correctamente")

            # Validar que el XML generado sea válido
            if not xml_content.strip():
                raise ValidationError(_("El template XML está vacío después del reemplazo."))
                
            if not xml_content.strip().startswith('<?xml'):
                xml_content = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_content

            return xml_content.encode('utf-8')

        # Si no hay template, usar XML básico original
        if not payroll:
            # XML básico para nómina electrónica colombiana
            xml_basic = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<NominaIndividual xmlns="dian:gov:co:facturaelectronica:NominaIndividual" 
                  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <Informacion>
        <Empleado>
            <Identificacion>12345678</Identificacion>
            <Nombres>Juan Pérez</Nombres>
        </Empleado>
        <Periodo>
            <Año>2024</Año>
            <Mes>12</Mes>
        </Periodo>
        <Consecutivo>000001</Consecutivo>
    </Informacion>
    <Devengados>
        <Basico>0</Basico>
    </Devengados>
    <Deducciones>
        <Salud>0</Salud>
        <Pension>0</Pension>
    </Deducciones>
</NominaIndividual>'''
            return xml_basic.encode('utf-8')
        
        # Si hay payroll pero no template
        xml_basic = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<NominaIndividual xmlns="dian:gov:co:facturaelectronica:NominaIndividual" 
                  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <Informacion>
        <Empleado>
            <Identificacion>{}</Identificacion>
            <Nombres>{}</Nombres>
        </Empleado>
        <Periodo>
            <Año>{}</Año>
            <Mes>{}</Mes>
        </Periodo>
        <Consecutivo>{}</Consecutivo>
    </Informacion>
    <Devengados>
        <Basico>0</Basico>
    </Devengados>
    <Deducciones>
        <Salud>0</Salud>
        <Pension>0</Pension>
    </Deducciones>
</NominaIndividual>'''.format(
            payroll.employee_id.identification_id or '12345678',
            payroll.employee_id.name or 'Sin Nombre',
            payroll.electronic_payroll_id.year or 2024,
            payroll.electronic_payroll_id.month or 12,
            payroll.sequence or '000001'
        )
        return xml_basic.encode('utf-8')

class LavishXmlGeneratorDetail(models.Model):
    _name = 'lavish.xml.generator.detail'
    _description = 'Detalles del Generador XML'

    header_id = fields.Many2one('lavish.xml.generator.header', string='Header', ondelete='cascade')
    name = fields.Char('Nombre', required=True)
    code_python = fields.Text('Código Python')
    attributes_code_python = fields.Text('Atributos Código Python')
    sequence = fields.Integer('Secuencia', default=10)
