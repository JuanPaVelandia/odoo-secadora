# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import AccessError, ValidationError
from dateutil.relativedelta import relativedelta

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # Portal - Campos específicos del portal
    # Nota: Los campos de tallas y productos se heredan del módulo base lavish_hr_employee
    show_in_portal = fields.Boolean('Mostrar en Portal', default=True)
    portal_access_token = fields.Char('Token de Acceso Portal', copy=False)
    
    def action_view_medical_certificates(self):
        """Ver certificados médicos"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Certificados Médicos',
            'res_model': 'hr.medical.certificate',
            'view_mode': 'list,form,calendar',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id}
        }
    
    def action_view_epp_requests(self):
        """Ver solicitudes EPP/Dotación"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Solicitudes EPP/Dotación',
            'res_model': 'hr.epp.request',
            'view_mode': 'list,form,kanban',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id}
        }
    
    def action_request_epp(self):
        """Crear nueva solicitud EPP/Dotación"""
        self.ensure_one()
        
        # Buscar configuración activa
        config = self.env['hr.epp.configuration'].search([
            ('active', '=', True),
            ('type', '=', 'dotacion')
        ], limit=1)
        
        if not config:
            config = self.env['hr.epp.configuration'].create_default_configuration()
        
        # Crear solicitud
        request = self.env['hr.epp.request'].create({
            'employee_id': self.id,
            'configuration_id': config.id,
            'type': 'dotacion',
            'state': 'draft',
        })
        
        # Agregar items del kit con tallas
        for line in config.kit_line_ids:
            size = False
            if line.item_type == 'shirt':
                size = self.shirt_size
            elif line.item_type == 'pants':
                size = self.pants_size
            elif line.item_type == 'shoes':
                size = self.shoe_size
            
            self.env['hr.epp.request.line'].create({
                'request_id': request.id,
                'item_type': line.item_type,
                'product_id': line.product_id.id if line.product_id else False,
                'name': line.name,
                'quantity': line.quantity,
                'size': size,
            })
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.epp.request',
            'res_id': request.id,
            'view_mode': 'form',
        }
    
    def action_schedule_medical_exam(self):
        """Programar examen médico"""
        self.ensure_one()
        
        # Buscar proveedor predeterminado
        provider = self.env['hr.medical.provider'].search([
            ('provider_type', 'in', ['clinic', 'laboratory'])
        ], limit=1)
        
        if not provider:
            raise ValueError(_('No hay proveedores médicos configurados'))
        
        # Crear certificado
        cert = self.env['hr.medical.certificate'].create({
            'employee_id': self.id,
            'provider_id': provider.id,
            'certificate_type': 'periodic',
            'expiry_date': fields.Date.today() + relativedelta(years=1),
        })
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.medical.certificate',
            'res_id': cert.id,
            'view_mode': 'form',
        }
    
    def get_portal_data(self):
        """Obtener datos para el portal del empleado"""
        self.ensure_one()

        # Verificar acceso
        if self.user_id != self.env.user and not self.env.user.has_group('hr.group_hr_user'):
            raise AccessError(_('No tiene acceso a esta información'))

        # Datos básicos
        data = {
            'employee': {
                'id': self.id,
                'name': self.name or '',
                'job': self.job_id.name if self.job_id else '',
                'department': self.department_id.name if self.department_id else '',
                'photo': self.image_1920 if self.image_1920 else False,
                'phone': self.work_phone or '',
                'email': self.work_email or '',
                'manager': self.parent_id.name if self.parent_id else '',
                'manager_id': self.parent_id.id if self.parent_id else False,
                'manager_job': self.parent_id.job_id.name if self.parent_id and self.parent_id.job_id else '',
                'manager_photo': self.parent_id.image_128 if self.parent_id and self.parent_id.image_128 else False,
                'identification': self.identification_id or '',
                'contract_date': self.contract_id.date_start if self.contract_id else False,
                'sizes': {
                    'shirt': self.shirt_size or '',
                    'pants': self.pants_size or '',
                    'shoes': self.shoe_size or '',
                }
            }
        }

        # Datos del contrato actual
        contract = self.contract_id
        if contract:
            data['contract'] = {
                'id': contract.id,
                'name': contract.name,
                'date_start': contract.date_start,
                'date_end': contract.date_end,
                'state': contract.state,
                'state_label': dict(contract._fields['state'].selection).get(contract.state) if hasattr(contract._fields['state'], 'selection') else contract.state,
                'wage': contract.wage,
                'job': contract.job_id.name if contract.job_id else '',
                'department': contract.department_id.name if contract.department_id else '',
                'resource_calendar': contract.resource_calendar_id.name if contract.resource_calendar_id else '',
                'work_hours_per_week': contract.resource_calendar_id.hours_per_day * 5 if contract.resource_calendar_id else 40,
                'trial_date_end': contract.trial_date_end if hasattr(contract, 'trial_date_end') else False,
                'contract_type': contract.contract_type_id.name if hasattr(contract, 'contract_type_id') and contract.contract_type_id else 'Indefinido',
            }
        else:
            data['contract'] = None

        # Organigrama - Jefe directo y compañeros de equipo
        data['org_chart'] = {
            'manager': None,
            'peers': [],
            'subordinates': []
        }

        if self.parent_id:
            data['org_chart']['manager'] = {
                'id': self.parent_id.id,
                'name': self.parent_id.name,
                'job': self.parent_id.job_id.name if self.parent_id.job_id else '',
                'photo': self.parent_id.image_128 if self.parent_id.image_128 else False,
                'email': self.parent_id.work_email or '',
                'phone': self.parent_id.work_phone or '',
            }

            # Compañeros de equipo (empleados con el mismo jefe)
            peers = self.env['hr.employee'].search([
                ('parent_id', '=', self.parent_id.id),
                ('id', '!=', self.id),
                ('active', '=', True)
            ], limit=5)

            data['org_chart']['peers'] = [{
                'id': peer.id,
                'name': peer.name,
                'job': peer.job_id.name if peer.job_id else '',
                'photo': peer.image_128 if peer.image_128 else False,
            } for peer in peers]

        # Subordinados directos
        subordinates = self.env['hr.employee'].search([
            ('parent_id', '=', self.id),
            ('active', '=', True)
        ], limit=10)

        data['org_chart']['subordinates'] = [{
            'id': sub.id,
            'name': sub.name,
            'job': sub.job_id.name if sub.job_id else '',
            'photo': sub.image_128 if sub.image_128 else False,
        } for sub in subordinates]

        # Mensajes del chatter (últimos 10)
        messages = self.message_ids.filtered(
            lambda m: m.message_type in ['email', 'comment'] and not m.is_internal
        ).sorted('date', reverse=True)[:10]

        data['chatter'] = {
            'can_post': True,  # El empleado puede postear en su propio perfil
            'messages': [{
                'id': msg.id,
                'body': msg.body,
                'author': msg.author_id.name if msg.author_id else 'Sistema',
                'date': msg.date,
                'attachments': [{
                    'id': att.id,
                    'name': att.name,
                    'mimetype': att.mimetype,
                    'file_size': att.file_size,
                } for att in msg.attachment_ids]
            } for msg in messages]
        }

        # Certificados médicos
        medical_certs = self.medical_certificate_ids.filtered(lambda c: c.state in ['valid', 'expiring'])
        data['medical'] = {
            'count': len(medical_certs),
            'has_valid': self.has_valid_medical,
            'certificates': [{
                'id': cert.id,
                'type': cert.certificate_type,
                'type_label': dict(cert._fields['certificate_type'].selection).get(cert.certificate_type),
                'provider': cert.provider_id.name if cert.provider_id else '',
                'expiry_date': cert.expiry_date,
                'state': cert.state,
                'state_label': dict(cert._fields['state'].selection).get(cert.state),
                'result': cert.result,
                'result_label': dict(cert._fields['result'].selection).get(cert.result) if cert.result else '',
                'can_print': cert.result == 'apt' and cert.state == 'valid',
            } for cert in medical_certs[:5]]
        }

        # EPP/Dotación
        epp_requests = self.epp_request_ids.sorted('create_date', reverse=True)

        # Obtener configuraciones disponibles
        epp_configurations = self.env['hr.epp.configuration'].search([
            ('active', '=', True),
            '|',
            ('department_ids', '=', False),
            ('department_ids', 'in', [self.department_id.id] if self.department_id else []),
            '|',
            ('job_ids', '=', False),
            ('job_ids', 'in', [self.job_id.id] if self.job_id else [])
        ])

        data['epp'] = {
            'count': len(epp_requests),
            'last_delivery': self.last_dotacion_date,
            'requests': [{
                'id': req.id,
                'name': req.name,
                'type': req.type,
                'type_label': dict(req._fields['type'].selection).get(req.type),
                'state': req.state,
                'state_label': dict(req._fields['state'].selection).get(req.state),
                'request_date': req.request_date,
                'delivery_date': req.delivery_date,
                'can_print': req.state == 'delivered',
            } for req in epp_requests[:5]]
        }

        # Agregar configuraciones disponibles para el formulario de solicitud
        data['epp_configurations'] = [{
            'id': config.id,
            'name': config.name,
            'type': config.type,
            'type_label': dict(config._fields['type'].selection).get(config.type),
        } for config in epp_configurations]

        # Nómina - desprendibles de pago
        payslips = self.env['hr.payslip'].sudo().search([
            ('employee_id', '=', self.id),
            ('state', 'in', ['done', 'paid'])
        ], order='date_to desc')

        payslips_data = []
        for slip in payslips:
            # Calcular devengado (categorías TOTALDEV)
            devengado_lines = slip.line_ids.filtered(
                lambda l: l.category_id.code in ['TOTALDEV',] and l.total > 0
            )
            devengado = sum(devengado_lines.mapped('total'))

            # Calcular deducciones (categoría TOTALDED)
            deduccion_lines = slip.line_ids.filtered(
                lambda l: l.category_id.code in ['TOTALDED'] and l.total < 0
            )
            deduccion = abs(sum(deduccion_lines.mapped('total')))

            # Buscar línea NETO
            net_line = slip.line_ids.filtered(lambda l: l.code in ['NET', 'NETO'])
            total = net_line[0].total if net_line else (devengado - deduccion)

            # Preparar detalle de líneas de nómina
            earnings_detail = []
            deductions_detail = []

            earning_categories = [
                'BASIC', 'AUX', 'AUS', 'ALW', 'ACCIDENTE_TRABAJO',
                'DEV_NO_SALARIAL', 'DEV_SALARIAL', 'HEYREC',
                'COMISIONES', 'INCAPACIDAD', 'LICENCIA_MATERNIDAD',
                'LICENCIA_NO_REMUNERADA', 'LICENCIA_REMUNERADA',
                'PRESTACIONES_SOCIALES', 'PRIMA', 'VACACIONES',
                'COMP', 'DEV'  # Agregados por compatibilidad
            ]

            deduction_categories = [
                'DED', 'DEDUCCIONES', 'SANCIONES',
                'DESCUENTO_AFC', 'SSOCIAL', 'DEDUC'
            ]

            total_codes = ['TOTALDEV', 'TOTALDED', 'NET', 'NETO']

            for line in slip.line_ids.filtered(lambda l: l.category_id.code in earning_categories):
                # Excluir líneas de totales y líneas sin valor
                if line.total != 0 and line.code not in total_codes:
                    earnings_detail.append({
                        'name': line.name,
                        'code': line.code,
                        'category': line.category_id.name if line.category_id else '',
                        'category_code': line.category_id.code if line.category_id else '',
                        'quantity': line.quantity,
                        'rate': line.rate,
                        'amount': line.amount,
                        'total': line.total,
                    })

            # Procesar líneas de deducciones
            for line in slip.line_ids.filtered(lambda l: l.category_id.code in deduction_categories):
                # Excluir líneas de totales y líneas sin valor
                if line.total != 0 and line.code not in total_codes:
                    deductions_detail.append({
                        'name': line.name,
                        'code': line.code,
                        'category': line.category_id.name if line.category_id else '',
                        'category_code': line.category_id.code if line.category_id else '',
                        'quantity': line.quantity,
                        'rate': line.rate,
                        'amount': line.amount,
                        'total': abs(line.total),  # Valor absoluto para mostrar
                    })

            # Ausencias del período (novedades)
            absences = []
            for absence in slip.leave_ids:
                absences.append({
                    'type': absence.leave_id.holiday_status_id.name if absence.leave_id else 'Ausencia',
                    'days_used': absence.days_used,
                    'date_from': absence.leave_id.date_from if absence.leave_id else None,
                    'date_to': absence.leave_id.date_to if absence.leave_id else None,
                })

            # Horas extras del período (solo si el contrato permite pagar horas extras)
            overtime_hours = []
            if not (slip.contract_id and slip.contract_id.not_pay_overtime):
                for overtime in slip.extrahours_ids:
                    overtime_hours.append({
                        'date': overtime.date,
                        'hours': overtime.hours,
                        'type': overtime.overtime_type_id.name if overtime.overtime_type_id else 'Hora Extra',
                        'type_code': overtime.overtime_type_id.type_overtime if overtime.overtime_type_id else '',
                        'value': overtime.value,
                    })

            # Novedades de conceptos diferentes
            novelties = []
            for novelty in slip.novedades_ids:
                novelties.append({
                    'name': novelty.name or '',
                    'concept': novelty.salary_rule_id.name if novelty.salary_rule_id else '',
                    'value': novelty.amount,  # El campo correcto es 'amount' no 'value'
                })

            payslips_data.append({
                'id': slip.id,
                'name': slip.name,
                'number': slip.number or slip.name,
                'period': f"{slip.date_from.strftime('%d/%m/%Y')} - {slip.date_to.strftime('%d/%m/%Y')}",
                'date_from': slip.date_from,
                'date_to': slip.date_to,
                'struct': slip.struct_id.name if slip.struct_id else 'Nómina',
                'struct_type': slip.struct_id.process if slip.struct_id else 'nomina',
                'devengado': devengado,
                'deduccion': deduccion,
                'total': total,
                'earnings_detail': earnings_detail,
                'deductions_detail': deductions_detail,
                'absences': absences,
                'overtime_hours': overtime_hours,
                'novelties': novelties,
            })

        data['payroll'] = {
            'count': len(payslips),
            'payslips': payslips_data
        }

        # Ausencias/Permisos - usando hr.leave
        leaves = self.env['hr.leave'].search([
            ('employee_id', '=', self.id),
            ('state', 'in', ['validate', 'validate1', 'refuse'])
        ], order='date_from desc', limit=10)

        data['leaves'] = {
            'count': len(leaves),
            'items': [{
                'id': leave.id,
                'name': leave.name,
                'type': leave.holiday_status_id.name,
                'date_from': leave.date_from,
                'date_to': leave.date_to,
                'number_of_days': leave.number_of_days,
                'state': leave.state,
                'state_label': dict(leave._fields['state'].selection).get(leave.state),
            } for leave in leaves]
        }

        # Tipos de ausencia disponibles para solicitar
        leave_types = self.env['hr.leave.type'].search([
            ('requires_allocation', '=', 'no'),
            ('active', '=', True)
        ])
        data['leave_types'] = [{
            'id': lt.id,
            'name': lt.name,
            'code': lt.code,
        } for lt in leave_types]

        # Certificados laborales disponibles
        data['labor_certificates'] = {
            'can_request': True,
            'template_exists': bool(self.env['hr.labor.certificate.template'].search([
                ('company_id', '=', self.company_id.id)
            ], limit=1))
        }

        # Certificados de Ingresos y Retenciones
        income_cert_requests = self.env['hr.income.certificate.request'].sudo().search([
            ('employee_id', '=', self.id)
        ], order='request_date desc', limit=10)

        # Obtener años disponibles para certificados (últimos 5 años)
        from datetime import date
        current_year = date.today().year
        available_years = []
        for year in range(current_year - 4, current_year + 1):
            header = self.env['hr.certificate.income.header'].sudo().search([
                ('year', '=', year),
                ('company_id', '=', self.company_id.id)
            ], limit=1)
            if header:
                available_years.append(year)

        data['income_certificates'] = {
            'count': len(income_cert_requests),
            'items': [{
                'id': req.id,
                'year': req.year,
                'date_from': req.date_from,
                'date_to': req.date_to,
                'request_date': req.request_date,
                'generation_date': req.generation_date,
                'state': req.state,
                'state_label': dict(req._fields['state'].selection).get(req.state),
                'notes': req.notes or '',
            } for req in income_cert_requests]
        }

        data['income_cert_years'] = available_years

        # Préstamos
        loan_requests = self.env['hr.loan.request'].sudo().search([
            ('employee_id', '=', self.id)
        ], order='request_date desc', limit=10)

        data['loans'] = {
            'count': len(loan_requests),
            'items': [{
                'id': loan.id,
                'name': loan.name,
                'loan_type': loan.loan_type,
                'type_label': dict(loan._fields['loan_type'].selection).get(loan.loan_type),
                'amount': loan.amount,
                'approved_amount': loan.approved_amount,
                'total_installments': loan.installments,
                'paid_installments': loan.paid_installments,
                'balance': loan.balance,
                'request_date': loan.request_date,
                'approval_date': loan.approval_date,
                'state': loan.state,
                'state_label': dict(loan._fields['state'].selection).get(loan.state),
            } for loan in loan_requests]
        }

        return data
    
    def action_open_portal(self):
        """Abrir portal del empleado"""
        self.ensure_one()

        # Generar token si no existe
        if not self.portal_access_token:
            import secrets
            self.portal_access_token = secrets.token_urlsafe(32)

        # URL del portal
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        portal_url = f"{base_url}/my/employee/{self.id}?token={self.portal_access_token}"

        return {
            'type': 'ir.actions.act_url',
            'url': portal_url,
            'target': 'new',
        }

    def portal_request_leave(self, leave_type_id, date_from, date_to, description=''):
        """Solicitar ausencia/permiso desde el portal"""
        self.ensure_one()

        # Verificar acceso
        if self.user_id != self.env.user and not self.env.user.has_group('hr.group_hr_user'):
            raise AccessError(_('No tiene permiso para solicitar ausencias'))

        # Validar fechas
        try:
            date_from_dt = fields.Datetime.from_string(date_from)
            date_to_dt = fields.Datetime.from_string(date_to)
        except:
            raise ValidationError(_('Formato de fecha inválido'))

        if date_from_dt > date_to_dt:
            raise ValidationError(_('La fecha de inicio no puede ser posterior a la fecha de fin'))

        # Crear solicitud de ausencia
        leave = self.env['hr.leave'].create({
            'employee_id': self.id,
            'holiday_status_id': leave_type_id,
            'date_from': date_from_dt,
            'date_to': date_to_dt,
            'name': description or 'Solicitud desde portal',
            'state': 'confirm',  # Estado inicial
        })

        # Enviar a aprobación si tiene manager
        if self.parent_id:
            leave.action_approve()

        return {
            'success': True,
            'leave_id': leave.id,
            'message': _('Su solicitud ha sido enviada correctamente')
        }

    def portal_generate_labor_certificate(self, directed_to='A QUIEN INTERESE'):
        """Generar certificado laboral desde el portal

        Args:
            directed_to: Dirigido a (por defecto 'A QUIEN INTERESE')
        """
        self.ensure_one()

        # Verificar acceso
        if self.user_id != self.env.user and not self.env.user.has_group('hr.group_hr_user'):
            raise AccessError(_('No tiene permiso para generar certificados'))

        # Buscar plantilla de certificado
        template = self.env['hr.labor.certificate.template'].search([
            ('company_id', '=', self.company_id.id)
        ], limit=1)

        if not template:
            raise ValidationError(_('No existe una plantilla de certificado laboral configurada'))

        # Obtener el contrato activo del empleado
        contract = self.contract_id
        if not contract:
            raise ValidationError(_('El empleado no tiene un contrato activo'))

        # Crear historial de certificado
        certificate = self.env['hr.labor.certificate.history'].create({
            'contract_id': contract.id,
            'date_generation': fields.Date.today(),
            'info_to': directed_to or 'A QUIEN INTERESE',
        })

        # Generar el PDF del certificado
        certificate.generate_report()

        return {
            'success': True,
            'certificate_id': certificate.id,
            'message': _('Certificado laboral generado correctamente')
        }

    def portal_download_payslip(self, payslip_id):
        """Descargar desprendible de pago desde el portal"""
        self.ensure_one()

        # Verificar acceso
        if self.user_id != self.env.user and not self.env.user.has_group('hr.group_hr_user'):
            raise AccessError(_('No tiene permiso para descargar desprendibles'))

        # Verificar que el desprendible pertenece al empleado
        payslip = self.env['hr.payslip'].browse(payslip_id)

        if not payslip.exists() or payslip.employee_id != self:
            raise AccessError(_('No tiene acceso a este desprendible de pago'))

        if payslip.state != 'done':
            raise ValidationError(_('El desprendible de pago aún no está disponible'))

        # Retornar referencia al reporte
        return self.env.ref('lavish_hr_payroll.action_report_payslip').report_action(payslip)

    def portal_download_medical_certificate(self, certificate_id):
        """Descargar certificado médico desde el portal"""
        self.ensure_one()

        # Verificar acceso
        if self.user_id != self.env.user and not self.env.user.has_group('hr.group_hr_user'):
            raise AccessError(_('No tiene permiso para descargar certificados'))

        # Verificar que el certificado pertenece al empleado
        certificate = self.env['hr.medical.certificate'].browse(certificate_id)

        if not certificate.exists() or certificate.employee_id != self:
            raise AccessError(_('No tiene acceso a este certificado'))

        if certificate.state != 'valid' or certificate.result != 'apt':
            raise ValidationError(_('El certificado no está disponible para descarga'))

        # Retornar referencia al reporte
        return self.env.ref('lavish_hr_employee.action_report_medical_certificate').report_action(certificate)

    def portal_download_epp_delivery(self, request_id):
        """Descargar comprobante de entrega EPP desde el portal"""
        self.ensure_one()

        # Verificar acceso
        if self.user_id != self.env.user and not self.env.user.has_group('hr.group_hr_user'):
            raise AccessError(_('No tiene permiso para descargar comprobantes'))

        # Verificar que la solicitud pertenece al empleado
        request = self.env['hr.epp.request'].browse(request_id)

        if not request.exists() or request.employee_id != self:
            raise AccessError(_('No tiene acceso a este comprobante'))

        if request.state != 'delivered':
            raise ValidationError(_('La dotación aún no ha sido entregada'))

        # Retornar referencia al reporte
        return self.env.ref('lavish_hr_employee.action_report_epp_delivery').report_action(request)

    def portal_post_message(self, message_body, attachment_ids=None):
        """Publicar mensaje en el chatter desde el portal

        Args:
            message_body: Cuerpo del mensaje (HTML)
            attachment_ids: Lista de IDs de adjuntos ya subidos

        Returns:
            dict: Información del mensaje creado
        """
        self.ensure_one()

        # Verificar acceso
        if self.user_id != self.env.user and not self.env.user.has_group('hr.group_hr_user'):
            raise AccessError(_('No tiene permiso para publicar mensajes'))

        if not message_body or not message_body.strip():
            raise ValidationError(_('El mensaje no puede estar vacío'))

        # Crear mensaje en el chatter
        message = self.message_post(
            body=message_body,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
            attachment_ids=attachment_ids or [],
        )

        return {
            'success': True,
            'message_id': message.id,
            'message': _('Mensaje publicado correctamente')
        }

    def portal_upload_attachment(self, filename, file_content):
        """Subir adjunto al chatter desde el portal

        Args:
            filename: Nombre del archivo
            file_content: Contenido del archivo en base64

        Returns:
            dict: Información del adjunto subido
        """
        self.ensure_one()

        # Verificar acceso
        if self.user_id != self.env.user and not self.env.user.has_group('hr.group_hr_user'):
            raise AccessError(_('No tiene permiso para subir adjuntos'))

        # Validar tamaño (máximo 10MB)
        import base64
        file_size = len(base64.b64decode(file_content))
        max_size = 10 * 1024 * 1024  # 10MB

        if file_size > max_size:
            raise ValidationError(_('El archivo es demasiado grande. Máximo 10MB'))

        # Crear adjunto
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'datas': file_content,
            'res_model': 'hr.employee',
            'res_id': self.id,
            'type': 'binary',
        })

        return {
            'success': True,
            'attachment_id': attachment.id,
            'filename': filename,
            'file_size': file_size,
        }


class HrEmployeePublic(models.Model):
    _inherit = 'hr.employee.public'
    
    # Campos visibles en el portal público
    shirt_size = fields.Selection(related='employee_id.shirt_size', readonly=True)
    pants_size = fields.Selection(related='employee_id.pants_size', readonly=True)
    shoe_size = fields.Selection(related='employee_id.shoe_size', readonly=True)
    
    has_valid_medical = fields.Boolean(related='employee_id.has_valid_medical', readonly=True)
    last_dotacion_date = fields.Date(related='employee_id.last_dotacion_date', readonly=True)