# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request
from odoo.exceptions import AccessError, ValidationError
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
import json
import logging

_logger = logging.getLogger(__name__)


class EmployeePortalController(CustomerPortal):
    """Controlador para el portal de empleado - Extiende CustomerPortal"""

    def _prepare_home_portal_values(self, counters):
        """Agregar contador de empleado al portal"""
        values = super()._prepare_home_portal_values(counters)

        # Buscar empleado del usuario actual
        employee = request.env['hr.employee'].sudo().search([
            ('user_id', '=', request.env.user.id)
        ], limit=1)

        if employee:
            values['employee'] = employee

            if 'payslip_count' in counters:
                values['payslip_count'] = request.env['hr.payslip'].sudo().search_count([
                    ('employee_id', '=', employee.id),
                    ('state', 'in', ('done', 'paid'))
                    ])

            if 'leave_count' in counters:
                values['leave_count'] = request.env['hr.leave'].sudo().search_count([
                    ('employee_id', '=', employee.id)
                ])

        return values

    @http.route(['/my/employee'], type='http', auth='user', website=True)
    def portal_my_employee(self, **kwargs):
        """Página principal del empleado en el portal /my"""

        # Buscar empleado del usuario actual
        employee = request.env['hr.employee'].search([
            ('user_id', '=', request.env.user.id)
        ], limit=1)

        if not employee:
            return request.render('lavish_hr_employee_portal.portal_no_employee')

        # Generar token si no existe
        if not employee.portal_access_token:
            import secrets
            employee.sudo().portal_access_token = secrets.token_urlsafe(32)

        # Redirigir a la página del portal con token
        return request.redirect(f'/my/employee/{employee.id}?token={employee.portal_access_token}')


class EmployeePortalPublicController(http.Controller):
    """Controlador público para el portal de empleado (con token)"""

    def _validate_employee_access(self, employee_id, token):
        """Validar acceso al portal del empleado"""
        employee = request.env['hr.employee'].sudo().browse(employee_id)

        if not employee.exists():
            return None

        # Validar token
        if employee.portal_access_token != token:
            return None

        # Validar que show_in_portal esté activo
        if not employee.show_in_portal:
            return None

        return employee

    @http.route('/my/employee/<int:employee_id>', type='http', auth='public', website=True)
    def employee_portal_home(self, employee_id, token=None, **kwargs):
        """Página principal del portal del empleado"""

        # Validar acceso
        employee = self._validate_employee_access(employee_id, token)
        if not employee:
            return request.render('lavish_hr_employee_portal.portal_access_denied')

        # Obtener datos del portal
        try:
            portal_data = employee.get_portal_data()
        except Exception as e:
            _logger.error(f"Error in download method: {str(e)}")
            # Retornar respuesta HTML simple sin usar plantilla del portal
            error_html = f"""
            <html>
                <head><title>Error</title></head>
                <body style="font-family: Arial; padding: 20px;">
                    <h2>Error al descargar el archivo</h2>
                    <p>{str(e)}</p>
                    <a href="/my/employee/{employee_id}?token={token}">Volver al portal</a>
                </body>
            </html>
            """
            return request.make_response(error_html, headers=[('Content-Type', 'text/html')])

        # Renderizar template
        values = {
            'employee': employee,
            'portal_data': portal_data,
            'token': token,
        }

        return request.render('lavish_hr_employee_portal.employee_portal_template', values)

    # NOTA: Rutas de páginas separadas comentadas - El portal usa tabs en una sola página
    # Si se necesitan páginas separadas, crear las plantillas correspondientes primero

    # @http.route('/my/employee/<int:employee_id>/payslips', type='http', auth='public', website=True)
    # def employee_portal_payslips(self, employee_id, token=None, page=1, **kwargs):
    #     pass

    # @http.route('/my/employee/<int:employee_id>/leaves', type='http', auth='public', website=True)
    # def employee_portal_leaves(self, employee_id, token=None, **kwargs):
    #     pass

    @http.route('/my/employee/<int:employee_id>/request_leave', type='http', auth='public',
                methods=['POST'], website=True, csrf=True)
    def employee_portal_request_leave(self, employee_id, token=None, **post):
        """Procesar solicitud de ausencia/permiso desde el portal"""

        # Validar acceso
        employee = self._validate_employee_access(employee_id, token)
        if not employee:
            return request.redirect(f'/my/employee/{employee_id}?token={token}&error=access_denied')

        try:
            result = employee.sudo().portal_request_leave(
                leave_type_id=int(post.get('leave_type_id')),
                date_from=post.get('date_from'),
                date_to=post.get('date_to'),
                description=post.get('description', '')
            )
            return request.redirect(f'/my/employee/{employee_id}?token={token}&leave_success=1')

        except Exception as e:
            _logger.error(f"Error creating leave request: {str(e)}")
            return request.redirect(f'/my/employee/{employee_id}?token={token}&leave_error={str(e)}')

    @http.route('/my/employee/<int:employee_id>/download/payslip/<int:payslip_id>',
                type='http', auth='public')
    def download_payslip(self, employee_id, payslip_id, token=None, **kwargs):
        """Descargar desprendible de pago"""

        # Validar acceso
        employee = self._validate_employee_access(employee_id, token)
        if not employee:
            return request.render('lavish_hr_employee_portal.portal_access_denied')

        try:
            # Validar que el desprendible pertenece al empleado
            payslip = request.env['hr.payslip'].sudo().browse(payslip_id)

            if not payslip.exists() or payslip.employee_id.id != employee_id:
                raise AccessError(_('No tiene acceso a este desprendible'))

            # Permitir descargar nóminas en estado 'done' o 'paid'
            if payslip.state not in ('done', 'paid'):
                raise ValidationError(_('El desprendible no está disponible. Estado actual: %s') % payslip.state)

            # Obtener reporte y generar PDF
            report = self._get_payslip_report(payslip)
            if not report:
                raise ValidationError(_('No se encontró el reporte configurado'))

            # Generar PDF usando el modelo ir.actions.report (Odoo 19 pattern)
            pdf_content, dummy = request.env['ir.actions.report'].sudo().\
                with_context(lang=payslip.employee_id.lang or payslip.env.lang).\
                _render_qweb_pdf(report, payslip_id)

            # Generar nombre de archivo
            filename = payslip._get_report_base_filename() if hasattr(payslip, '_get_report_base_filename') else f'Nomina_{payslip.number}'

            pdfhttpheaders = [
                ('Content-Type', 'application/pdf'),
                ('Content-Length', len(pdf_content)),
                ('Content-Disposition', f'attachment; filename="{filename}.pdf"')
            ]

            return request.make_response(pdf_content, headers=pdfhttpheaders)

        except Exception as e:
            _logger.error(f"Error downloading payslip {payslip_id}: {str(e)}", exc_info=True)
            # Retornar respuesta HTML simple sin usar plantilla del portal
            error_html = f"""
            <html>
                <head><title>Error</title></head>
                <body style="font-family: Arial; padding: 20px;">
                    <h2>Error al descargar el desprendible</h2>
                    <p>{str(e)}</p>
                    <a href="/my/employee/{employee_id}?token={token}">Volver al portal</a>
                </body>
            </html>
            """
            return request.make_response(error_html, headers=[('Content-Type', 'text/html')])

    @http.route('/my/employee/<int:employee_id>/payslip/<int:payslip_id>',
                type='http', auth='public', website=True)
    def employee_portal_payslip_detail(self, employee_id, payslip_id, token=None,
                                        report_type=None, download=False, **kw):
        """Vista detallada de una nómina con iframe y descarga"""

        # Validar acceso
        employee = self._validate_employee_access(employee_id, token)
        if not employee:
            return request.render('lavish_hr_employee_portal.portal_access_denied')

        try:
            # Validar que el desprendible pertenece al empleado
            payslip = request.env['hr.payslip'].sudo().browse(payslip_id)

            if not payslip.exists() or payslip.employee_id.id != employee_id:
                raise AccessError(_('No tiene acceso a este desprendible'))

            # Permitir descargar nóminas en estado 'done' o 'paid'
            if payslip.state not in ('done', 'paid'):
                raise ValidationError(_('El desprendible no está disponible. Estado actual: %s') % payslip.state)

            # Obtener reporte
            report = self._get_payslip_report(payslip)
            if not report:
                raise ValidationError(_('No se encontró el reporte configurado para este tipo de nómina'))

            # Descarga de PDF
            if report_type == 'pdf' and download:
                try:
                    # Renderizar PDF usando el modelo ir.actions.report (Odoo 19 pattern)
                    pdf_content, dummy = request.env['ir.actions.report'].sudo().\
                        with_context(lang=payslip.employee_id.lang or payslip.env.lang).\
                        _render_qweb_pdf(report, payslip_id)

                    # Generar nombre de archivo
                    filename = payslip._get_report_base_filename() if hasattr(payslip, '_get_report_base_filename') else f'Nomina_{payslip.number}'

                    headers = [
                        ('Content-Type', 'application/pdf'),
                        ('Content-Length', len(pdf_content)),
                        ('Content-Disposition', f'attachment; filename="{filename}.pdf"')
                    ]

                    return request.make_response(pdf_content, headers=headers)

                except Exception as e:
                    _logger.error(f"Error generando PDF para nómina {payslip_id}: {str(e)}", exc_info=True)
                    return request.redirect(f'/my/employee/{employee_id}/payslip/{payslip_id}?token={token}&error=pdf_generation')

            # Vista HTML del reporte (para iframe)
            elif report_type == 'html':
                try:
                    # Renderizar HTML usando el modelo ir.actions.report (Odoo 19 pattern)
                    html_content = request.env['ir.actions.report'].sudo().\
                        with_context(lang=payslip.employee_id.lang or payslip.env.lang).\
                        _render_qweb_html(report, payslip_id)[0]
                    return request.make_response(html_content, headers=[
                        ('Content-Type', 'text/html; charset=utf-8')
                    ])

                except Exception as e:
                    _logger.error(f"Error generando HTML para nómina {payslip_id}: {str(e)}", exc_info=True)
                    error_html = f"""
                    <html>
                        <head>
                            <title>Error</title>
                            <meta charset="utf-8">
                        </head>
                        <body style="font-family: Arial; padding: 20px;">
                            <h2>Error al generar la vista previa</h2>
                            <p>{str(e)}</p>
                        </body>
                    </html>
                    """
                    return request.make_response(error_html, headers=[
                        ('Content-Type', 'text/html; charset=utf-8')
                    ])

            # Vista del portal con sidebar + iframe
            values = {
                'employee': employee,
                'payslip': payslip,
                'token': token,
                'page_name': 'payslip_detail',
            }
            return request.render("lavish_hr_employee_portal.employee_portal_payslip_detail", values)

        except (AccessError, ValidationError) as e:
            _logger.warning(f"Access error in payslip detail {payslip_id}: {str(e)}")
            error_html = f"""
            <html>
                <head><title>Acceso Denegado</title></head>
                <body style="font-family: Arial; padding: 20px;">
                    <h2>Acceso Denegado</h2>
                    <p>{str(e)}</p>
                    <a href="/my/employee/{employee_id}?token={token}">Volver al portal</a>
                </body>
            </html>
            """
            return request.make_response(error_html, headers=[('Content-Type', 'text/html')])
        except Exception as e:
            _logger.error(f"Error in payslip detail: {str(e)}", exc_info=True)
            error_html = f"""
            <html>
                <head><title>Error</title></head>
                <body style="font-family: Arial; padding: 20px;">
                    <h2>Error al cargar el desprendible</h2>
                    <p>{str(e)}</p>
                    <a href="/my/employee/{employee_id}?token={token}">Volver al portal</a>
                </body>
            </html>
            """
            return request.make_response(error_html, headers=[('Content-Type', 'text/html')])

    def _get_payslip_report(self, payslip):
        """
        Obtiene el reporte adecuado según el tipo de nómina
        Sigue el mismo patrón que Odoo 19 enterprise hr_payroll._get_pdf_reports()
        """

        # 1. Primero: obtener reporte de la estructura salarial (ODOO STANDARD)
        # Este es el método estándar de Odoo 19 enterprise
        if payslip.struct_id and payslip.struct_id.report_id:
            _logger.info(f"Usando reporte de estructura salarial (Odoo standard): {payslip.struct_id.report_id.report_name}")
            return payslip.struct_id.report_id.sudo()

        # 2. Segundo: obtener reporte de plantilla personalizada (LAVISH CUSTOM)
        # Este es el método personalizado de lavish_hr_payroll
        try:
            if hasattr(payslip, 'get_hr_payslip_reports_template'):
                template = payslip.get_hr_payslip_reports_template()
                if template and hasattr(template, 'report_id') and template.report_id:
                    _logger.info(f"Usando reporte de plantilla personalizada: {template.report_id.report_name}")
                    return template.report_id.sudo()
        except Exception as e:
            _logger.warning(f"Error obteniendo plantilla personalizada: {str(e)}")

        # 3. Tercero: usar reporte por defecto según tipo de proceso
        report_xmlid = 'lavish_hr_payroll.report_views_computes'

        try:
            report = request.env.ref(report_xmlid, raise_if_not_found=False)
            if report:
                _logger.info(f"Usando reporte por defecto: {report_xmlid}")
                return report.sudo()
        except Exception as e:
            _logger.warning(f"Error obteniendo reporte por defecto: {str(e)}")

        # 4. Cuarto: fallback a reporte estándar de Odoo (como enterprise)
        try:
            default_report = request.env.ref('hr_payroll.action_report_payslip', raise_if_not_found=False)
            if default_report:
                _logger.info("Usando reporte estándar de Odoo: hr_payroll.action_report_payslip")
                return default_report.sudo()
        except Exception as e:
            _logger.warning(f"Error obteniendo reporte estándar de Odoo: {str(e)}")

        # 5. Último intento: buscar cualquier reporte de nómina
        try:
            report = request.env['ir.actions.report'].sudo().search([
                ('model', '=', 'hr.payslip'),
                ('report_type', '=', 'qweb-pdf')
            ], limit=1)
            if report:
                _logger.info(f"Usando primer reporte encontrado: {report.report_name}")
                return report
            else:
                _logger.error("No se encontró ningún reporte de nómina en el sistema")
                return None
        except Exception as e:
            _logger.error(f"Error en búsqueda de último recurso: {str(e)}", exc_info=True)
            return None

    @http.route('/my/employee/<int:employee_id>/download/medical/<int:certificate_id>',
                type='http', auth='public')
    def download_medical_certificate(self, employee_id, certificate_id, token=None, **kwargs):
        """Descargar certificado médico"""

        # Validar acceso
        employee = self._validate_employee_access(employee_id, token)
        if not employee:
            return request.render('lavish_hr_employee_portal.portal_access_denied')

        try:
            # Validar que el certificado pertenece al empleado
            certificate = request.env['hr.medical.certificate'].sudo().browse(certificate_id)

            if not certificate.exists() or certificate.employee_id.id != employee_id:
                raise AccessError(_('No tiene acceso a este certificado'))

            if certificate.state != 'valid' or certificate.result != 'apt':
                raise ValidationError(_('El certificado no está disponible'))

            # Obtener reporte
            try:
                report = request.env.ref('lavish_hr_employee.action_report_medical_certificate', raise_if_not_found=False)
                if not report:
                    # Buscar cualquier reporte de certificados médicos
                    report = request.env['ir.actions.report'].sudo().search([
                        ('model', '=', 'hr.medical.certificate'),
                        ('report_type', '=', 'qweb-pdf')
                    ], limit=1)
                    if not report:
                        raise ValidationError(_('No se encontró el reporte de certificados médicos'))
            except Exception as e:
                _logger.error(f"Error buscando reporte médico: {str(e)}", exc_info=True)
                raise ValidationError(_('No se pudo cargar el reporte de certificados médicos'))

            # Generar PDF usando el modelo ir.actions.report (Odoo 19 pattern)
            pdf_content, dummy = request.env['ir.actions.report'].sudo()._render_qweb_pdf(report, certificate_id)

            # Generar nombre seguro
            safe_name = certificate.name.replace('/', '_').replace('\\', '_') if certificate.name else 'Certificado'
            filename = f'Certificado_Medico_{safe_name}.pdf'

            pdfhttpheaders = [
                ('Content-Type', 'application/pdf'),
                ('Content-Length', len(pdf_content)),
                ('Content-Disposition', f'attachment; filename="{filename}"')
            ]

            return request.make_response(pdf_content, headers=pdfhttpheaders)

        except (AccessError, ValidationError) as e:
            _logger.warning(f"Access/validation error downloading medical certificate {certificate_id}: {str(e)}")
            error_html = f"""
            <html>
                <head><title>Error</title></head>
                <body style="font-family: Arial; padding: 20px;">
                    <h2>Error al descargar el certificado</h2>
                    <p>{str(e)}</p>
                    <a href="/my/employee/{employee_id}?token={token}">Volver al portal</a>
                </body>
            </html>
            """
            return request.make_response(error_html, headers=[('Content-Type', 'text/html')])
        except Exception as e:
            _logger.error(f"Error downloading medical certificate {certificate_id}: {str(e)}", exc_info=True)
            error_html = f"""
            <html>
                <head><title>Error</title></head>
                <body style="font-family: Arial; padding: 20px;">
                    <h2>Error al descargar el archivo</h2>
                    <p>{str(e)}</p>
                    <a href="/my/employee/{employee_id}?token={token}">Volver al portal</a>
                </body>
            </html>
            """
            return request.make_response(error_html, headers=[('Content-Type', 'text/html')])

    @http.route('/my/employee/<int:employee_id>/download/epp/<int:request_id>',
                type='http', auth='public')
    def download_epp_delivery(self, employee_id, request_id, token=None, **kwargs):
        """Descargar comprobante de entrega EPP"""

        # Validar acceso
        employee = self._validate_employee_access(employee_id, token)
        if not employee:
            return request.render('lavish_hr_employee_portal.portal_access_denied')

        try:
            # Validar que la solicitud pertenece al empleado
            epp_request = request.env['hr.epp.request'].sudo().browse(request_id)

            if not epp_request.exists() or epp_request.employee_id.id != employee_id:
                raise AccessError(_('No tiene acceso a este comprobante'))

            if epp_request.state != 'delivered':
                raise ValidationError(_('La dotación no ha sido entregada'))

            # Obtener reporte
            try:
                report = request.env.ref('lavish_hr_employee.action_report_epp_delivery', raise_if_not_found=False)
                if not report:
                    # Buscar cualquier reporte de EPP
                    report = request.env['ir.actions.report'].sudo().search([
                        ('model', '=', 'hr.epp.request'),
                        ('report_type', '=', 'qweb-pdf')
                    ], limit=1)
                    if not report:
                        raise ValidationError(_('No se encontró el reporte de entregas EPP'))
            except Exception as e:
                _logger.error(f"Error buscando reporte EPP: {str(e)}", exc_info=True)
                raise ValidationError(_('No se pudo cargar el reporte de entregas EPP'))

            # Generar PDF usando el modelo ir.actions.report (Odoo 19 pattern)
            pdf_content, dummy = request.env['ir.actions.report'].sudo()._render_qweb_pdf(report, request_id)

            # Generar nombre seguro
            safe_name = epp_request.name.replace('/', '_').replace('\\', '_') if epp_request.name else 'EPP'
            filename = f'Entrega_EPP_{safe_name}.pdf'

            pdfhttpheaders = [
                ('Content-Type', 'application/pdf'),
                ('Content-Length', len(pdf_content)),
                ('Content-Disposition', f'attachment; filename="{filename}"')
            ]

            return request.make_response(pdf_content, headers=pdfhttpheaders)

        except (AccessError, ValidationError) as e:
            _logger.warning(f"Access/validation error downloading EPP {request_id}: {str(e)}")
            error_html = f"""
            <html>
                <head><title>Error</title></head>
                <body style="font-family: Arial; padding: 20px;">
                    <h2>Error al descargar el comprobante</h2>
                    <p>{str(e)}</p>
                    <a href="/my/employee/{employee_id}?token={token}">Volver al portal</a>
                </body>
            </html>
            """
            return request.make_response(error_html, headers=[('Content-Type', 'text/html')])
        except Exception as e:
            _logger.error(f"Error downloading EPP delivery {request_id}: {str(e)}", exc_info=True)
            error_html = f"""
            <html>
                <head><title>Error</title></head>
                <body style="font-family: Arial; padding: 20px;">
                    <h2>Error al descargar el archivo</h2>
                    <p>{str(e)}</p>
                    <a href="/my/employee/{employee_id}?token={token}">Volver al portal</a>
                </body>
            </html>
            """
            return request.make_response(error_html, headers=[('Content-Type', 'text/html')])

    @http.route('/my/employee/<int:employee_id>/generate/labor_certificate',
                type='http', auth='public', methods=['POST'], csrf=True)
    def generate_labor_certificate(self, employee_id, token=None, **kwargs):
        """Generar y descargar certificado laboral"""

        # Validar acceso
        employee = self._validate_employee_access(employee_id, token)
        if not employee:
            return request.render('lavish_hr_employee_portal.portal_access_denied')

        try:
            # Obtener el campo 'directed_to' del formulario
            directed_to = kwargs.get('directed_to', 'A QUIEN INTERESE')

            # Generar el certificado
            result = employee.portal_generate_labor_certificate(directed_to=directed_to)

            if result.get('success') and result.get('certificate_id'):
                # Redirigir a la descarga directa del certificado
                return request.redirect(f'/my/employee/{employee_id}/download/labor_certificate/{result["certificate_id"]}?token={token}')
            else:
                return request.redirect(f'/my/employee/{employee_id}?token={token}&error=generation_failed')

        except Exception as e:
            _logger.error(f"Error generando certificado laboral: {str(e)}", exc_info=True)
            return request.redirect(f'/my/employee/{employee_id}?token={token}&error={str(e)}')

    @http.route('/my/employee/<int:employee_id>/download/labor_certificate/<int:certificate_id>',
                type='http', auth='public')
    def download_labor_certificate(self, employee_id, certificate_id, token=None, **kwargs):
        """Descargar certificado laboral"""

        # Validar acceso
        employee = self._validate_employee_access(employee_id, token)
        if not employee:
            return request.render('lavish_hr_employee_portal.portal_access_denied')

        try:
            # Validar que el certificado pertenece al empleado
            certificate = request.env['hr.labor.certificate.history'].sudo().browse(certificate_id)

            if not certificate.exists() or certificate.contract_id.employee_id.id != employee_id:
                raise AccessError(_('No tiene acceso a este certificado'))

            # Obtener reporte
            try:
                report = request.env.ref('lavish_hr_employee.action_report_labor_certificate', raise_if_not_found=False)
                if not report:
                    # Buscar cualquier reporte de certificados laborales
                    report = request.env['ir.actions.report'].sudo().search([
                        ('model', '=', 'hr.labor.certificate.history'),
                        ('report_type', '=', 'qweb-pdf')
                    ], limit=1)
                    if not report:
                        raise ValidationError(_('No se encontró el reporte de certificados laborales'))
            except Exception as e:
                _logger.error(f"Error buscando reporte laboral: {str(e)}", exc_info=True)
                raise ValidationError(_('No se pudo cargar el reporte de certificados laborales'))

            # Generar PDF usando el modelo ir.actions.report (Odoo 19 pattern)
            pdf_content, dummy = request.env['ir.actions.report'].sudo()._render_qweb_pdf(report, certificate_id)

            # Generar nombre seguro
            safe_name = employee.name.replace('/', '_').replace('\\', '_')
            filename = f'Certificado_Laboral_{safe_name}.pdf'

            pdfhttpheaders = [
                ('Content-Type', 'application/pdf'),
                ('Content-Length', len(pdf_content)),
                ('Content-Disposition', f'attachment; filename="{filename}"')
            ]

            return request.make_response(pdf_content, headers=pdfhttpheaders)

        except (AccessError, ValidationError) as e:
            _logger.warning(f"Access/validation error downloading labor certificate {certificate_id}: {str(e)}")
            error_html = f"""
            <html>
                <head><title>Error</title></head>
                <body style="font-family: Arial; padding: 20px;">
                    <h2>Error al descargar el certificado</h2>
                    <p>{str(e)}</p>
                    <a href="/my/employee/{employee_id}?token={token}">Volver al portal</a>
                </body>
            </html>
            """
            return request.make_response(error_html, headers=[('Content-Type', 'text/html')])
        except Exception as e:
            _logger.error(f"Error downloading labor certificate {certificate_id}: {str(e)}", exc_info=True)
            error_html = f"""
            <html>
                <head><title>Error</title></head>
                <body style="font-family: Arial; padding: 20px;">
                    <h2>Error al descargar el archivo</h2>
                    <p>{str(e)}</p>
                    <a href="/my/employee/{employee_id}?token={token}">Volver al portal</a>
                </body>
            </html>
            """
            return request.make_response(error_html, headers=[('Content-Type', 'text/html')])

    @http.route('/my/employee/<int:employee_id>/request_epp', type='http', auth='public',
                methods=['POST'], website=True, csrf=True)
    def employee_portal_request_epp(self, employee_id, token=None, **post):
        """Procesar solicitud de EPP/Dotación desde portal"""

        # Validar acceso
        employee = self._validate_employee_access(employee_id, token)
        if not employee:
            return json.dumps({'error': 'Acceso denegado'})

        try:
            # Crear solicitud de EPP/Dotación
            epp_type = post.get('type', 'dotacion')
            configuration_id = int(post.get('configuration_id')) if post.get('configuration_id') else False

            request_vals = {
                'employee_id': employee.id,
                'type': epp_type,
                'state': 'draft',
                'request_date': fields.Date.today(),
                'delivery_location': post.get('delivery_location', 'office'),
                'delivery_location_detail': post.get('delivery_location_detail', ''),
                'notes': post.get('notes', ''),
            }

            if configuration_id:
                request_vals['configuration_id'] = configuration_id

            epp_request = request.env['hr.epp.request'].sudo().create(request_vals)

            # Si tiene configuración, cargar items automáticamente
            if configuration_id:
                config = request.env['hr.epp.configuration'].sudo().browse(configuration_id)
                for line in config.kit_line_ids:
                    size = False
                    if line.item_type == 'shirt':
                        size = employee.shirt_size or 'M'
                    elif line.item_type == 'pants':
                        size = employee.pants_size or '32'
                    elif line.item_type == 'shoes':
                        size = employee.shoe_size or '40'

                    # Buscar producto por defecto del empleado si está configurado
                    product_id = line.product_id.id if line.product_id else False
                    if hasattr(employee, 'default_shirt_product_id') and line.item_type == 'shirt' and employee.default_shirt_product_id:
                        product_id = employee.default_shirt_product_id.id
                    elif hasattr(employee, 'default_pants_product_id') and line.item_type == 'pants' and employee.default_pants_product_id:
                        product_id = employee.default_pants_product_id.id
                    elif hasattr(employee, 'default_shoes_product_id') and line.item_type == 'shoes' and employee.default_shoes_product_id:
                        product_id = employee.default_shoes_product_id.id

                    request.env['hr.epp.request.line'].sudo().create({
                        'request_id': epp_request.id,
                        'item_type': line.item_type,
                        'product_id': product_id,
                        'name': line.name,
                        'quantity': line.quantity,
                        'size': size,
                    })
            else:
                # Agregar líneas manuales del formulario
                line_counter = 0
                while f'line_{line_counter}_type' in post:
                    item_type = post.get(f'line_{line_counter}_type')
                    name = post.get(f'line_{line_counter}_name')
                    quantity = float(post.get(f'line_{line_counter}_quantity', 1.0))
                    size = post.get(f'line_{line_counter}_size', '')

                    if item_type and name:
                        request.env['hr.epp.request.line'].sudo().create({
                            'request_id': epp_request.id,
                            'item_type': item_type,
                            'name': name,
                            'quantity': quantity,
                            'size': size if size else False,
                        })

                    line_counter += 1

            # Enviar a solicitud automáticamente si hay líneas
            if epp_request.line_ids:
                epp_request.action_request()

            return request.redirect(f'/my/employee/{employee_id}?token={token}&epp_requested=1')

        except Exception as e:
            return request.redirect(f'/my/employee/{employee_id}?token={token}&error={str(e)}')

    @http.route('/my/employee/<int:employee_id>/load_epp_config/<int:config_id>', type='jsonrpc', auth='public')
    def employee_load_epp_config(self, employee_id, config_id, token=None, **kwargs):
        """Cargar items de configuración EPP vía AJAX"""

        # Validar acceso
        employee = request.env['hr.employee'].sudo().browse(employee_id)
        if not employee.exists() or employee.portal_access_token != token:
            return {'error': 'Acceso denegado'}

        try:
            config = request.env['hr.epp.configuration'].sudo().browse(config_id)
            if not config.exists():
                return {'error': 'Configuración no encontrada'}

            items = []
            for line in config.kit_line_ids:
                size = ''
                if line.item_type == 'shirt':
                    size = employee.shirt_size or 'M'
                elif line.item_type == 'pants':
                    size = employee.pants_size or '32'
                elif line.item_type == 'shoes':
                    size = employee.shoe_size or '40'

                items.append({
                    'item_type': line.item_type,
                    'name': line.name,
                    'quantity': line.quantity,
                    'size': size,
                    'requires_size': line.requires_size,
                })

            return {'success': True, 'items': items}

        except Exception as e:
            return {'error': str(e)}

    # ========== CERTIFICADOS DE INGRESOS Y RETENCIONES ==========

    @http.route('/my/employee/<int:employee_id>/request_income_certificate',
                type='http', auth='public', methods=['POST'], csrf=True)
    def employee_request_income_certificate(self, employee_id, token=None, **post):
        """Procesar solicitud de certificado de ingresos y retenciones"""

        # Validar acceso
        employee = self._validate_employee_access(employee_id, token)
        if not employee:
            return json.dumps({'error': 'Acceso denegado'})

        try:
            from datetime import datetime

            year = int(post.get('year'))
            date_from = post.get('date_from')
            date_to = post.get('date_to')
            notes = post.get('notes', '')

            # Si no hay fechas específicas, usar todo el año
            if not date_from or not date_to:
                date_from = f"{year}-01-01"
                date_to = f"{year}-12-31"

            # Convertir a objetos date
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()

            # Buscar configuración del año
            header = request.env['hr.certificate.income.header'].sudo().search([
                ('year', '=', year),
                ('company_id', '=', employee.company_id.id)
            ], limit=1)

            if not header:
                raise ValidationError(_(f'No existe configuración de certificado para el año {year}'))

            # Crear solicitud (registro histórico)
            cert_request = request.env['hr.income.certificate.request'].sudo().create({
                'employee_id': employee.id,
                'header_id': header.id,
                'year': year,
                'date_from': date_from_obj,
                'date_to': date_to_obj,
                'notes': notes,
                'state': 'draft',
                'request_date': datetime.now(),
            })

            # Auto-generar el certificado (opcional: podría requerir aprobación)
            cert_request.action_generate()

            return request.redirect(f'/my/employee/{employee_id}?token={token}&income_cert_requested=1')

        except Exception as e:
            return request.redirect(f'/my/employee/{employee_id}?token={token}&error={str(e)}')

    @http.route('/my/employee/<int:employee_id>/download/income_certificate/<int:request_id>',
                type='http', auth='public')
    def download_income_certificate(self, employee_id, request_id, token=None, **kwargs):
        """Descargar certificado de ingresos y retenciones en PDF"""

        # Validar acceso
        employee = self._validate_employee_access(employee_id, token)
        if not employee:
            return request.render('lavish_hr_employee_portal.portal_access_denied')

        try:
            # Validar que el certificado pertenece al empleado
            cert_request = request.env['hr.income.certificate.request'].sudo().browse(request_id)

            if not cert_request.exists() or cert_request.employee_id.id != employee_id:
                raise AccessError(_('No tiene acceso a este certificado'))

            if cert_request.state != 'done':
                raise ValidationError(_('El certificado no está disponible para descarga'))

            # Obtener reporte
            try:
                report = request.env.ref('lavish_hr_payroll.report_withholding_and_income_certificate', raise_if_not_found=False)
                if not report:
                    # Buscar cualquier reporte del wizard
                    report = request.env['ir.actions.report'].sudo().search([
                        ('model', '=', 'hr.certificate.income.wizard'),
                        ('report_type', '=', 'qweb-pdf')
                    ], limit=1)
                    if not report:
                        raise ValidationError(_('No se encontró el reporte de certificados de ingresos'))
            except Exception as e:
                _logger.error(f"Error buscando reporte de ingresos: {str(e)}", exc_info=True)
                raise ValidationError(_('No se pudo cargar el reporte de certificados'))

            # Generar PDF usando el wizard
            wizard = request.env['hr.certificate.income.wizard'].sudo().create({
                'header_id': cert_request.header_id.id if cert_request.header_id else False,
                'employee_ids': [(6, 0, [employee.id])],
                'date_from': cert_request.date_from,
                'date_to': cert_request.date_to,
            })

            # Generar PDF usando el modelo ir.actions.report (Odoo 19 pattern)
            pdf_content, dummy = request.env['ir.actions.report'].sudo()._render_qweb_pdf(report, wizard.id)

            # Generar nombre seguro
            safe_name = employee.name.replace('/', '_').replace('\\', '_')
            year = getattr(cert_request, 'year', cert_request.date_from.year if cert_request.date_from else '')
            filename = f'Certificado_Ingresos_{safe_name}_{year}.pdf'

            pdfhttpheaders = [
                ('Content-Type', 'application/pdf'),
                ('Content-Length', len(pdf_content)),
                ('Content-Disposition', f'attachment; filename="{filename}"')
            ]

            return request.make_response(pdf_content, headers=pdfhttpheaders)

        except (AccessError, ValidationError) as e:
            _logger.warning(f"Access/validation error downloading income certificate {request_id}: {str(e)}")
            error_html = f"""
            <html>
                <head><title>Error</title></head>
                <body style="font-family: Arial; padding: 20px;">
                    <h2>Error al descargar el certificado</h2>
                    <p>{str(e)}</p>
                    <a href="/my/employee/{employee_id}?token={token}">Volver al portal</a>
                </body>
            </html>
            """
            return request.make_response(error_html, headers=[('Content-Type', 'text/html')])
        except Exception as e:
            _logger.error(f"Error downloading income certificate {request_id}: {str(e)}", exc_info=True)
            error_html = f"""
            <html>
                <head><title>Error</title></head>
                <body style="font-family: Arial; padding: 20px;">
                    <h2>Error al descargar el archivo</h2>
                    <p>{str(e)}</p>
                    <a href="/my/employee/{employee_id}?token={token}">Volver al portal</a>
                </body>
            </html>
            """
            return request.make_response(error_html, headers=[('Content-Type', 'text/html')])

    # ========== PRÉSTAMOS ==========

    @http.route('/my/employee/<int:employee_id>/request_loan',
                type='http', auth='public', methods=['POST'], csrf=True)
    def employee_request_loan(self, employee_id, token=None, **post):
        """Procesar solicitud de préstamo"""

        # Validar acceso
        employee = self._validate_employee_access(employee_id, token)
        if not employee:
            return json.dumps({'error': 'Acceso denegado'})

        try:
            from datetime import datetime
            from odoo import fields

            loan_type = post.get('loan_type')
            amount = float(post.get('amount', 0))
            installments = int(post.get('installments', 1))
            justification = post.get('justification', '')

            if amount <= 0:
                raise ValidationError(_('El monto debe ser mayor a 0'))

            # Crear solicitud de préstamo
            loan_request = request.env['hr.loan.request'].sudo().create({
                'employee_id': employee.id,
                'loan_type': loan_type,
                'amount': amount,
                'installments': installments,
                'justification': justification,
                'state': 'draft',
                'request_date': fields.Date.today(),
            })

            return request.redirect(f'/my/employee/{employee_id}?token={token}&loan_requested=1')

        except Exception as e:
            return request.redirect(f'/my/employee/{employee_id}?token={token}&error={str(e)}')

    # ========== SIMULACIÓN / TESTING ==========

    @http.route('/my/employee/simulate', type='http', auth='user', website=True)
    def employee_portal_simulate_selector(self, **kwargs):
        """
        Página de selección de empleado para simulación
        SOLO para usuarios con permisos de HR Manager
        """

        # Verificar permisos de HR Manager
        if not request.env.user.has_group('hr.group_hr_manager'):
            return request.render('lavish_hr_employee_portal.portal_access_denied')

        # Obtener todos los empleados
        employees = request.env['hr.employee'].sudo().search([], order='name')

        # Preparar datos de empleados
        employees_data = []
        for emp in employees:
            employees_data.append({
                'id': emp.id,
                'name': emp.name,
                'identification': emp.identification_id or '',
                'job': emp.job_id.name if emp.job_id else '',
                'job_id': emp.job_id.id if emp.job_id else False,
                'department': emp.department_id.name if emp.department_id else '',
                'department_id': emp.department_id.id if emp.department_id else False,
                'active': emp.active,
                'show_in_portal': emp.show_in_portal,
                'image_128': emp.image_128 if emp.image_128 else False,
            })

        # Obtener departamentos y cargos únicos para filtros
        departments = request.env['hr.department'].sudo().search([])
        jobs = request.env['hr.job'].sudo().search([])

        departments_data = [{'id': d.id, 'name': d.name} for d in departments]
        jobs_data = [{'id': j.id, 'name': j.name} for j in jobs]

        values = {
            'employees': employees_data,
            'departments': departments_data,
            'jobs': jobs_data,
        }

        return request.render('lavish_hr_employee_portal.employee_portal_simulation_selector', values)

    @http.route('/my/employee/simulate/<int:employee_id>',
                type='http', auth='user', website=True)
    def employee_portal_simulate(self, employee_id, **kwargs):
        """
        Endpoint de simulación para probar el portal con un empleado específico
        SOLO para usuarios con permisos de HR Manager
        """

        # Verificar permisos de HR Manager
        if not request.env.user.has_group('hr.group_hr_manager'):
            return request.render('lavish_hr_employee_portal.portal_access_denied')

        # Buscar empleado
        employee = request.env['hr.employee'].sudo().browse(employee_id)

        if not employee.exists():
            return request.render('lavish_hr_employee_portal.portal_error', {
                'error_message': 'Empleado no encontrado'
            })

        # Activar show_in_portal si no está activo
        if not employee.show_in_portal:
            employee.sudo().show_in_portal = True

        # Generar token si no existe
        if not employee.portal_access_token:
            import secrets
            employee.sudo().portal_access_token = secrets.token_urlsafe(32)

        # Redirigir al portal del empleado con token
        return request.redirect(f'/my/employee/{employee.id}?token={employee.portal_access_token}&simulate=1')

    @http.route('/my/employee/<int:employee_id>/post_message',
                type='http', auth='public', methods=['POST'], csrf=True)
    def employee_portal_post_message(self, employee_id, token=None, **post):
        """Publicar mensaje en el chatter desde el portal"""

        # Validar acceso
        employee = self._validate_employee_access(employee_id, token)
        if not employee:
            return json.dumps({'error': 'Acceso denegado'})

        try:
            message_body = post.get('message_body', '')

            # Procesar adjuntos si existen
            attachment_ids = []
            if 'attachment' in request.httprequest.files:
                file = request.httprequest.files['attachment']
                if file and file.filename:
                    import base64
                    file_content = base64.b64encode(file.read())

                    result = employee.sudo().portal_upload_attachment(
                        filename=file.filename,
                        file_content=file_content
                    )

                    if result.get('success'):
                        attachment_ids = [(4, result['attachment_id'])]

            # Publicar mensaje
            result = employee.sudo().portal_post_message(
                message_body=message_body,
                attachment_ids=attachment_ids
            )

            return request.redirect(f'/my/employee/{employee_id}?token={token}&message_posted=1')

        except Exception as e:
            _logger.error(f"Error posting message: {str(e)}")
            return request.redirect(f'/my/employee/{employee_id}?token={token}&error={str(e)}')

    @http.route('/my/employee/<int:employee_id>/upload_attachment',
                type='jsonrpc', auth='public')
    def employee_portal_upload_attachment(self, employee_id, token=None, filename=None, file_content=None):
        """Subir adjunto al chatter via AJAX"""

        # Validar acceso
        employee = request.env['hr.employee'].sudo().browse(employee_id)
        if not employee.exists() or employee.portal_access_token != token:
            return {'error': 'Acceso denegado'}

        try:
            result = employee.portal_upload_attachment(
                filename=filename,
                file_content=file_content
            )
            return result

        except Exception as e:
            _logger.error(f"Error uploading attachment: {str(e)}")
            return {'error': str(e)}

    @http.route('/my/employee/<int:employee_id>/download_attachment/<int:attachment_id>',
                type='http', auth='public')
    def employee_portal_download_attachment(self, employee_id, attachment_id, token=None, **kwargs):
        """Descargar adjunto del chatter"""

        # Validar acceso
        employee = self._validate_employee_access(employee_id, token)
        if not employee:
            return request.render('lavish_hr_employee_portal.portal_access_denied')

        try:
            # Verificar que el adjunto pertenece al empleado
            attachment = request.env['ir.attachment'].sudo().browse(attachment_id)

            if not attachment.exists() or attachment.res_model != 'hr.employee' or attachment.res_id != employee_id:
                raise AccessError(_('No tiene acceso a este adjunto'))

            # Descargar adjunto
            import base64
            file_content = base64.b64decode(attachment.datas)

            headers = [
                ('Content-Type', attachment.mimetype or 'application/octet-stream'),
                ('Content-Length', len(file_content)),
                ('Content-Disposition', f'attachment; filename="{attachment.name}"')
            ]

            return request.make_response(file_content, headers=headers)

        except Exception as e:
            _logger.error(f"Error downloading attachment: {str(e)}")
            error_html = f"""
            <html>
                <head><title>Error</title></head>
                <body style="font-family: Arial; padding: 20px;">
                    <h2>Error al descargar el archivo</h2>
                    <p>{str(e)}</p>
                    <a href="/my/employee/{employee_id}?token={token}">Volver al portal</a>
                </body>
            </html>
            """
            return request.make_response(error_html, headers=[('Content-Type', 'text/html')])


    # =====================================================
    # RUTAS DE DETALLE CON IFRAME
    # =====================================================

    @http.route('/my/employee/<int:employee_id>/leave/<int:leave_id>',
                type='http', auth='public', website=True)
    def employee_portal_leave_detail(self, employee_id, leave_id, token=None,
                                       report_type=None, **kw):
        """Vista detallada de una licencia/ausencia con iframe"""

        employee = self._validate_employee_access(employee_id, token)
        if not employee:
            return request.render('lavish_hr_employee_portal.portal_access_denied')

        try:
            leave = request.env['hr.leave'].sudo().browse(leave_id)

            if not leave.exists() or leave.employee_id.id != employee_id:
                raise AccessError(_('No tiene acceso a esta ausencia'))

            if report_type == 'html':
                try:
                    values = {'leave': leave, 'employee': employee}
                    return request.render('lavish_hr_employee_portal.leave_html_view', values)
                except Exception as e:
                    _logger.error(f"Error generando HTML para ausencia {leave_id}: {str(e)}", exc_info=True)
                    return request.make_response(f"<html><body><h2>Error</h2><p>{str(e)}</p></body></html>",
                                                headers=[('Content-Type', 'text/html')])

            values = {'employee': employee, 'leave': leave, 'token': token, 'page_name': 'leave_detail'}
            return request.render("lavish_hr_employee_portal.employee_portal_leave_detail", values)

        except Exception as e:
            _logger.error(f"Error in leave detail: {str(e)}", exc_info=True)
            return request.redirect(f'/my/employee/{employee_id}?token={token}')

    @http.route('/my/employee/<int:employee_id>/epp/<int:request_id>',
                type='http', auth='public', website=True)
    def employee_portal_epp_detail(self, employee_id, request_id, token=None,
                                     report_type=None, **kw):
        """Vista detallada de una solicitud EPP/Dotación con iframe"""

        employee = self._validate_employee_access(employee_id, token)
        if not employee:
            return request.render('lavish_hr_employee_portal.portal_access_denied')

        try:
            epp_request = request.env['hr.epp.request'].sudo().browse(request_id)

            if not epp_request.exists() or epp_request.employee_id.id != employee_id:
                raise AccessError(_('No tiene acceso a esta solicitud'))

            if report_type == 'html':
                try:
                    lines = request.env['hr.epp.request.line'].sudo().search([('request_id', '=', request_id)])
                    values = {'epp_request': epp_request, 'lines': lines, 'employee': employee}
                    return request.render('lavish_hr_employee_portal.epp_html_view', values)
                except Exception as e:
                    _logger.error(f"Error generando HTML: {str(e)}", exc_info=True)
                    return request.make_response(f"<html><body><h2>Error</h2><p>{str(e)}</p></body></html>",
                                                headers=[('Content-Type', 'text/html')])

            values = {'employee': employee, 'epp_request': epp_request, 'token': token, 'page_name': 'epp_detail'}
            return request.render("lavish_hr_employee_portal.employee_portal_epp_detail", values)

        except Exception as e:
            _logger.error(f"Error in EPP detail: {str(e)}", exc_info=True)
            return request.redirect(f'/my/employee/{employee_id}?token={token}')

    @http.route('/my/employee/<int:employee_id>/medical/<int:certificate_id>',
                type='http', auth='public', website=True)
    def employee_portal_medical_detail(self, employee_id, certificate_id, token=None,
                                         report_type=None, **kw):
        """Vista detallada de un certificado médico con iframe"""

        employee = self._validate_employee_access(employee_id, token)
        if not employee:
            return request.render('lavish_hr_employee_portal.portal_access_denied')

        try:
            certificate = request.env['hr.medical.certificate'].sudo().browse(certificate_id)

            if not certificate.exists() or certificate.employee_id.id != employee_id:
                raise AccessError(_('No tiene acceso a este certificado'))

            if report_type == 'html':
                try:
                    values = {'certificate': certificate, 'employee': employee}
                    return request.render('lavish_hr_employee_portal.medical_html_view', values)
                except Exception as e:
                    _logger.error(f"Error generando HTML: {str(e)}", exc_info=True)
                    return request.make_response(f"<html><body><h2>Error</h2><p>{str(e)}</p></body></html>",
                                                headers=[('Content-Type', 'text/html')])

            values = {'employee': employee, 'certificate': certificate, 'token': token, 'page_name': 'medical_detail'}
            return request.render("lavish_hr_employee_portal.employee_portal_medical_detail", values)

        except Exception as e:
            _logger.error(f"Error in medical detail: {str(e)}", exc_info=True)
            return request.redirect(f'/my/employee/{employee_id}?token={token}')

    @http.route('/my/employee/<int:employee_id>/loan/<int:loan_id>',
                type='http', auth='public', website=True)
    def employee_portal_loan_detail(self, employee_id, loan_id, token=None,
                                      report_type=None, **kw):
        """Vista detallada de un préstamo con iframe"""

        employee = self._validate_employee_access(employee_id, token)
        if not employee:
            return request.render('lavish_hr_employee_portal.portal_access_denied')

        try:
            loan = request.env['hr.loan.request'].sudo().browse(loan_id)

            if not loan.exists() or loan.employee_id.id != employee_id:
                raise AccessError(_('No tiene acceso a este préstamo'))

            if report_type == 'html':
                try:
                    installments = request.env['hr.loan.installment'].sudo().search([
                        ('loan_id', '=', loan_id)
                    ], order='installment_number')
                    values = {'loan': loan, 'installments': installments, 'employee': employee}
                    return request.render('lavish_hr_employee_portal.loan_html_view', values)
                except Exception as e:
                    _logger.error(f"Error generando HTML: {str(e)}", exc_info=True)
                    return request.make_response(f"<html><body><h2>Error</h2><p>{str(e)}</p></body></html>",
                                                headers=[('Content-Type', 'text/html')])

            values = {'employee': employee, 'loan': loan, 'token': token, 'page_name': 'loan_detail'}
            return request.render("lavish_hr_employee_portal.employee_portal_loan_detail", values)

        except Exception as e:
            _logger.error(f"Error in loan detail: {str(e)}", exc_info=True)
            return request.redirect(f'/my/employee/{employee_id}?token={token}')
