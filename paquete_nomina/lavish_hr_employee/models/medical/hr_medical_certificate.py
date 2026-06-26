# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

class HrMedicalProvider(models.Model):
    _name = 'hr.medical.provider'
    _description = 'Proveedor Médico'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    
    name = fields.Char('Nombre', required=True)
    provider_type = fields.Selection([
        ('laboratory', 'Laboratorio'),
        ('clinic', 'Clínica'),
        ('hospital', 'Hospital'),
        ('medical_center', 'Centro Médico'),
        ('specialist', 'Especialista'),
    ], string='Tipo', required=True)
    
    partner_id = fields.Many2one('res.partner', 'Contacto', required=True)
    nit = fields.Char('NIT', related='partner_id.vat')
    phone = fields.Char('Teléfono', related='partner_id.phone')
    email = fields.Char('Email', related='partner_id.email')
    street = fields.Char('Dirección', related='partner_id.street')
    city = fields.Char('Ciudad', related='partner_id.city')
    
    # Servicios que ofrece
    service_ids = fields.Many2many('hr.medical.service', string='Servicios')
    
    # Plantillas de exámenes
    template_ids = fields.One2many('hr.medical.template', 'provider_id', 'Plantillas')
    
    active = fields.Boolean('Activo', default=True)


class HrMedicalService(models.Model):
    _name = 'hr.medical.service'
    _description = 'Servicio Médico'
    
    name = fields.Char('Nombre', required=True)
    code = fields.Char('Código')
    description = fields.Text('Descripción')
    
    service_type = fields.Selection([
        ('blood_test', 'Exámenes de Sangre'),
        ('urine_test', 'Exámenes de Orina'),
        ('xray', 'Rayos X'),
        ('ultrasound', 'Ecografía'),
        ('electrocardiogram', 'Electrocardiograma'),
        ('spirometry', 'Espirometría'),
        ('audiometry', 'Audiometría'),
        ('optometry', 'Optometría'),
        ('psychology', 'Psicología'),
        ('occupational', 'Medicina Ocupacional'),
        ('height_work', 'Trabajo en Alturas'),
        ('confined_spaces', 'Espacios Confinados'),
        ('other', 'Otro'),
    ], string='Tipo', required=True)
    
    price = fields.Float('Precio')
    product_id = fields.Many2one('product.product', 'Producto')


class HrMedicalTemplate(models.Model):
    _name = 'hr.medical.template'
    _description = 'Plantilla de Examen Médico'
    
    name = fields.Char('Nombre', required=True)
    provider_id = fields.Many2one('hr.medical.provider', 'Proveedor')
    
    exam_type = fields.Selection([
        ('ingress', 'Ingreso'),
        ('periodic', 'Periódico'),
        ('retirement', 'Retiro'),
        ('post_incapacity', 'Post Incapacidad'),
        ('special', 'Especial'),
        ('height_work', 'Trabajo en Alturas'),
        ('confined_spaces', 'Espacios Confinados'),
    ], string='Tipo de Examen', required=True)
    
    # Servicios incluidos
    service_ids = fields.Many2many('hr.medical.service', string='Servicios Incluidos')
    
    # Instrucciones
    preparation_instructions = fields.Html('Instrucciones de Preparación')
    duration_hours = fields.Float('Duración (horas)', default=2.0)
    
    # Vigencia
    validity_months = fields.Integer('Vigencia (meses)', default=12)
    
    active = fields.Boolean('Activo', default=True)


class HrMedicalCertificate(models.Model):
    _name = 'hr.medical.certificate'
    _description = 'Certificado Médico'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'expiry_date desc'
    
    name = fields.Char('Referencia', required=True, copy=False, default='New')
    employee_id = fields.Many2one('hr.employee', 'Empleado', required=True, tracking=True)

    # Lote de exámenes
    batch_id = fields.Many2one(
        'hr.epp.batch',
        string='Lote',
        help='Lote de exámenes médicos al que pertenece',
        index=True
    )

    # Proveedor
    provider_id = fields.Many2one('hr.medical.provider', 'Proveedor', required=True)
    provider_type = fields.Selection(related='provider_id.provider_type', string='Tipo de Proveedor')
    
    # Tipo y plantilla
    certificate_type = fields.Selection([
        ('aptitude', 'Certificado de Aptitud Laboral'),
        ('height_work', 'Trabajo en Alturas'),
        ('confined_spaces', 'Espacios Confinados'),
        ('psychosensory', 'Psicosensométrico'),
        ('occupational', 'Examen Ocupacional'),
        ('periodic', 'Examen Periódico'),
        ('retirement', 'Examen de Retiro'),
        ('drug_test', 'Prueba de Drogas'),
        ('other', 'Otro')
    ], string='Tipo', required=True, tracking=True)
    
    template_id = fields.Many2one('hr.medical.template', 'Plantilla Usada')
    
    # Fechas
    schedule_date = fields.Datetime('Fecha Programada')
    exam_date = fields.Date('Fecha del Examen')
    issue_date = fields.Date('Fecha de Emisión', required=True, default=fields.Date.today)
    expiry_date = fields.Date('Fecha de Vencimiento', required=True)
    
    # Estado
    state = fields.Selection([
        ('scheduled', 'Programado'),
        ('in_process', 'En Proceso'),
        ('waiting_results', 'Esperando Resultados'),
        ('valid', 'Vigente'),
        ('expiring', 'Por Vencer'),
        ('expired', 'Vencido'),
        ('cancelled', 'Cancelado')
    ], string='Estado', compute='_compute_state', store=True, tracking=True, default='scheduled')
    
    # Resultados
    result = fields.Selection([
        ('apt', 'Apto'),
        ('apt_restrictions', 'Apto con Restricciones'),
        ('not_apt', 'No Apto'),
        ('pending', 'Pendiente')
    ], string='Resultado', default='pending', tracking=True)
    
    restrictions = fields.Text('Restricciones')
    recommendations = fields.Text('Recomendaciones')
    observations = fields.Text('Observaciones')
    
    # Documentos - Integración con módulo documents
    document_ids = fields.Many2many('documents.document', string='Documentos')
    attachment_ids = fields.Many2many('ir.attachment', string='Adjuntos')
    
    # Resultados específicos
    result_line_ids = fields.One2many('hr.medical.certificate.result', 'certificate_id', 'Resultados Detallados')
    
    # Control
    purchase_order_id = fields.Many2one('purchase.order', 'Orden de Compra')
    invoice_id = fields.Many2one('account.move', 'Factura')
    
    # Alertas
    days_to_alert = fields.Integer('Días para Alerta', default=30)
    alert_sent = fields.Boolean('Alerta Enviada')
    
    # Ubicación del examen
    location = fields.Char('Ubicación del Examen')

    # Doctor y costos
    doctor_name = fields.Char('Nombre del Doctor')
    cost = fields.Monetary('Costo', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='Moneda', default=lambda self: self.env.company.currency_id)

    # Servicios realizados
    service_ids = fields.Many2many('hr.medical.service', 'hr_medical_certificate_service_rel',
                                   'certificate_id', 'service_id', string='Servicios Realizados')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('hr.medical.certificate') or 'MED/001'
        return super().create(vals_list)
    
    @api.depends('expiry_date', 'exam_date', 'result')
    def _compute_state(self):
        today = fields.Date.today()
        for cert in self:
            if not cert.exam_date:
                cert.state = 'scheduled'
            elif cert.exam_date and cert.result == 'pending':
                cert.state = 'waiting_results'
            elif cert.expiry_date:
                days_diff = (cert.expiry_date - today).days
                if days_diff < 0:
                    cert.state = 'expired'
                elif days_diff <= cert.days_to_alert:
                    cert.state = 'expiring'
                else:
                    cert.state = 'valid'
            else:
                cert.state = 'in_process'
    
    def action_schedule(self):
        """Programar examen"""
        self.ensure_one()
        self.state = 'scheduled'
        return True

    def action_start(self):
        """Iniciar examen"""
        self.ensure_one()
        self.state = 'in_process'
        return True

    def action_waiting_results(self):
        """Marcar como esperando resultados"""
        self.ensure_one()
        self.state = 'waiting_results'
        return True

    def action_validate(self):
        """Validar certificado"""
        self.ensure_one()
        if self.result == 'pending':
            raise UserError(_('Debe ingresar el resultado del examen antes de validar'))
        self.state = 'valid'
        return True

    def action_cancel(self):
        """Cancelar certificado"""
        self.ensure_one()
        self.state = 'cancelled'
        return True

    def action_upload_results(self):
        """Subir resultados"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Subir Resultados',
            'res_model': 'hr.medical.upload.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_certificate_id': self.id,
            }
        }
    
    def action_print_certificate(self):
        """Imprimir certificado"""
        return self.env.ref('lavish_hr_employee.action_report_medical_certificate').report_action(self)
    
    def action_create_purchase_order(self):
        """Crear orden de compra"""
        if not self.provider_id:
            raise UserError(_('Debe seleccionar un proveedor'))
        
        # Obtener servicios de la plantilla o crear genérico
        lines = []
        if self.template_id:
            for service in self.template_id.service_ids:
                if service.product_id:
                    lines.append((0, 0, {
                        'product_id': service.product_id.id,
                        'name': service.name,
                        'product_qty': 1,
                        'price_unit': service.price,
                    }))
        
        if not lines:
            # Crear producto genérico
            product = self.env['product.product'].search([
                ('name', 'ilike', 'examen médico')
            ], limit=1)
            
            if not product:
                product = self.env['product.product'].create({
                    'name': 'Examen Médico - %s' % dict(self._fields['certificate_type'].selection).get(self.certificate_type),
                    'type': 'service',
                    'purchase_ok': True,
                })
            
            lines = [(0, 0, {
                'product_id': product.id,
                'name': 'Examen Médico - %s para %s' % (
                    dict(self._fields['certificate_type'].selection).get(self.certificate_type),
                    self.employee_id.name
                ),
                'product_qty': 1,
            })]
        
        po = self.env['purchase.order'].create({
            'partner_id': self.provider_id.partner_id.id,
            'origin': self.name,
            'order_line': lines,
        })
        
        self.purchase_order_id = po
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'res_id': po.id,
            'view_mode': 'form',
        }
    
    @api.model
    def check_expiring_certificates(self):
        """Cron para verificar certificados por vencer"""
        today = fields.Date.today()
        
        # Buscar certificados por vencer
        expiring_certs = self.search([
            ('state', '=', 'expiring'),
            ('alert_sent', '=', False)
        ])
        
        for cert in expiring_certs:
            days_remaining = (cert.expiry_date - today).days
            
            # Notificar
            cert.message_post(
                body=_('El certificado médico %s de %s vence en %s días') % (
                    dict(cert._fields['certificate_type'].selection).get(cert.certificate_type),
                    cert.employee_id.name,
                    days_remaining
                ),
                message_type='notification',
                partner_ids=cert.employee_id.parent_id.user_id.partner_id.ids if cert.employee_id.parent_id else []
            )
            
            cert.alert_sent = True
            
            # Crear actividad
            self.env['mail.activity'].create({
                'summary': _('Renovar Certificado Médico'),
                'note': _('El certificado %s vence el %s') % (cert.name, cert.expiry_date),
                'date_deadline': cert.expiry_date - timedelta(days=7),
                'user_id': cert.employee_id.parent_id.user_id.id if cert.employee_id.parent_id else self.env.user.id,
                'res_model_id': self.env.ref('lavish_hr_employee.model_hr_medical_certificate').id,
                'res_id': cert.id,
            })


class HrMedicalCertificateResult(models.Model):
    _name = 'hr.medical.certificate.result'
    _description = 'Resultado de Certificado Médico'
    
    certificate_id = fields.Many2one('hr.medical.certificate', 'Certificado', ondelete='cascade')
    
    service_id = fields.Many2one('hr.medical.service', 'Servicio/Examen')
    name = fields.Char('Examen', required=True)
    
    result = fields.Text('Resultado')
    value = fields.Char('Valor')
    unit = fields.Char('Unidad')
    reference_range = fields.Char('Rango de Referencia')
    
    status = fields.Selection([
        ('normal', 'Normal'),
        ('abnormal', 'Anormal'),
        ('critical', 'Crítico')
    ], string='Estado', default='normal')
    
    observations = fields.Text('Observaciones')
    attachment_ids = fields.Many2many('ir.attachment', string='Adjuntos')