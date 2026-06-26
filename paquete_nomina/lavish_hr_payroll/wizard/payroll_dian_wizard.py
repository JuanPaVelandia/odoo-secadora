# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class PayrollDianSendWizard(models.TransientModel):
    _name = 'payroll.dian.send.wizard'
    _description = 'Wizard para Envío Masivo a DIAN'

    payroll_detail_ids = fields.Many2many(
        'hr.electronic.payroll.detail',
        string='Detalles de Nómina',
        required=True
    )
    
    environment = fields.Selection([
        ('test', 'Ambiente de Habilitación'),
        ('production', 'Ambiente de Producción'),
    ], string='Entorno', default='test', required=True)
    
    action_type = fields.Selection([
        ('generate', 'Solo Generar XML'),
        ('sign', 'Generar y Firmar XML'),
        ('send', 'Proceso Completo (Generar, Firmar y Enviar)'),
    ], string='Acción a Realizar', default='send', required=True)
    
    total_documents = fields.Integer('Total Documentos', readonly=True)
    
    @api.model
    def default_get(self, fields_list):
        result = super(PayrollDianSendWizard, self).default_get(fields_list)
        
        # Obtener registros seleccionados
        active_ids = self.env.context.get('active_ids', [])
        if active_ids:
            payroll_details = self.env['hr.electronic.payroll.detail'].browse(active_ids)
            result['payroll_detail_ids'] = [(6, 0, payroll_details.ids)]
            result['total_documents'] = len(payroll_details)
            
        return result
    
    @api.onchange('payroll_detail_ids')
    def _onchange_payroll_detail_ids(self):
        self.total_documents = len(self.payroll_detail_ids)

    def action_process_documents(self):
        """Procesa los documentos según la acción seleccionada"""
        if not self.payroll_detail_ids:
            raise UserError(_("No hay documentos seleccionados para procesar"))
        
        processed_count = 0
        error_count = 0
        errors = []
        
        for detail in self.payroll_detail_ids:
            try:
                # Verificar si ya existe un documento DIAN
                dian_doc = self.env['dian.payroll.document'].search([
                    ('payroll_detail_id', '=', detail.id)
                ], limit=1)
                
                if not dian_doc:
                    # Crear nuevo documento DIAN
                    dian_doc = self.env['dian.payroll.document'].create({
                        'payroll_detail_id': detail.id,
                        'company_id': detail.electronic_payroll_id.company_id.id,
                        'environment': self.environment,
                    })
                
                # Ejecutar acciones según el tipo seleccionado
                if self.action_type in ['generate', 'sign', 'send']:
                    if dian_doc.state == 'draft':
                        dian_doc.action_generate_xml()
                
                if self.action_type in ['sign', 'send']:
                    if dian_doc.state == 'generated':
                        dian_doc.action_sign_xml()
                
                if self.action_type == 'send':
                    if dian_doc.state == 'signed':
                        dian_doc.action_send_to_dian()
                
                processed_count += 1
                
            except Exception as e:
                error_count += 1
                error_msg = f"Error procesando {detail.employee_id.name}: {str(e)}"
                errors.append(error_msg)
                _logger.error(error_msg)
        
        # Mostrar resultado
        message = f"Procesamiento completado:\n"
        message += f"- Documentos procesados exitosamente: {processed_count}\n"
        message += f"- Documentos con errores: {error_count}\n"
        
        if errors:
            message += f"\nErrores encontrados:\n" + "\n".join(errors[:10])  # Limitar a 10 errores
            if len(errors) > 10:
                message += f"\n... y {len(errors) - 10} errores más."
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Resultado del Procesamiento'),
                'message': message,
                'type': 'success' if error_count == 0 else 'warning',
                'sticky': True,
            }
        }

    def action_validate_configuration(self):
        """Valida la configuración antes del envío"""
        company = self.env.company
        errors = []
        
        # Validar configuración general
        if not company.certificate_file:
            errors.append("- Certificado digital no configurado")
        
        if not company.certificate_password:
            errors.append("- Contraseña del certificado no configurada")
        
        # Validar configuración específica de nómina
        if self.action_type == 'send':
            if not company.payroll_software_id:
                errors.append("- ID del Software de Nómina DIAN no configurado")
            
            if not company.payroll_software_pin:
                errors.append("- PIN del Software de Nómina DIAN no configurado")
            
            if self.environment == 'test' and not company.payroll_test_set_id:
                errors.append("- Test Set ID de Nómina no configurado para ambiente de habilitación")
        
        if errors:
            error_message = "Configuración incompleta:\n" + "\n".join(errors)
            error_message += "\n\nPor favor complete la configuración en Configuración > Facturación Electrónica."
            
            raise UserError(_(error_message))
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Validación Exitosa'),
                'message': 'La configuración está completa. Puede proceder con el envío.',
                'type': 'success',
            }
        }

class PayrollDianStatusWizard(models.TransientModel):
    _name = 'payroll.dian.status.wizard'
    _description = 'Wizard para Consulta de Estado en DIAN'

    dian_document_ids = fields.Many2many(
        'dian.payroll.document',
        string='Documentos DIAN',
        required=True
    )
    
    total_documents = fields.Integer('Total Documentos', readonly=True)
    
    @api.model
    def default_get(self, fields_list):
        result = super(PayrollDianStatusWizard, self).default_get(fields_list)
        
        # Obtener documentos DIAN relacionados a los registros seleccionados
        active_ids = self.env.context.get('active_ids', [])
        if active_ids:
            payroll_details = self.env['hr.electronic.payroll.detail'].browse(active_ids)
            dian_docs = self.env['dian.payroll.document'].search([
                ('payroll_detail_id', 'in', payroll_details.ids),
                ('state', 'in', ['sent'])
            ])
            
            if dian_docs:
                result['dian_document_ids'] = [(6, 0, dian_docs.ids)]
                result['total_documents'] = len(dian_docs)
            
        return result
    
    @api.onchange('dian_document_ids')
    def _onchange_dian_document_ids(self):
        self.total_documents = len(self.dian_document_ids)

    def action_check_status(self):
        """Consulta el estado de los documentos en DIAN"""
        if not self.dian_document_ids:
            raise UserError(_("No hay documentos para consultar"))
        
        updated_count = 0
        error_count = 0
        errors = []
        
        for dian_doc in self.dian_document_ids:
            try:
                if dian_doc.dian_zip_key:
                    dian_doc.action_check_status()
                    updated_count += 1
                else:
                    error_count += 1
                    errors.append(f"Documento {dian_doc.name}: No tiene ZIP Key para consultar")
                    
            except Exception as e:
                error_count += 1
                errors.append(f"Documento {dian_doc.name}: {str(e)}")
                _logger.error(f"Error consultando estado: {e}")
        
        # Mostrar resultado
        message = f"Consulta de estado completada:\n"
        message += f"- Documentos actualizados: {updated_count}\n"
        message += f"- Documentos con errores: {error_count}\n"
        
        if errors:
            message += f"\nErrores encontrados:\n" + "\n".join(errors[:5])
            if len(errors) > 5:
                message += f"\n... y {len(errors) - 5} errores más."
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Resultado de la Consulta'),
                'message': message,
                'type': 'success' if error_count == 0 else 'warning',
                'sticky': True,
            }
        }
