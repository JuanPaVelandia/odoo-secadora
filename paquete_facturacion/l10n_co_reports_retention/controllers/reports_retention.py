# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from datetime import datetime
import logging

from odoo import http, _
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.http import request
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)


class PortalReportRetention(CustomerPortal):


    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'rention_count' in counters:
            values['rention_count'] = 'Ver Certificados'
        if 'rentionica_download' in counters:
            values['rentionica_download'] = 'Descargar'
        if 'rentioniva_download' in counters:
            values['rentioniva_download'] = 'Descargar'
        if 'rentionfu_download' in counters:
            values['rentionfu_download'] = 'Descargar'
        return values

    def _check_user_has_retentions(self, partner_id, company_id):
        AccountMoveLine = request.env['account.move.line'].sudo()

        retention_lines = AccountMoveLine.search([
            ('partner_id', '=', partner_id),
            ('company_id', '=', company_id),
            ('tax_ids', '!=', False),
            ('move_id.state', '=', 'posted'),
        ], limit=1)

        return bool(retention_lines)

    @http.route(['/my/retention'], type='http', auth="user", website=True)
    def reports_retention(self, **kw):
        partner_id = request.env.user.partner_id.id
        company_id = request.env.company.id

        has_retentions = self._check_user_has_retentions(partner_id, company_id)

        values = {
            'page_name': 'certificate',
            'has_retentions': has_retentions,
            'partner_name': request.env.user.partner_id.name,
        }
        return request.render("l10n_co_reports_retention.portal_my_retention", values)
    
    def _get_user_companies(self):
        """Get companies accessible by the current user"""
        return request.env.user.company_ids

    @http.route(['/my/retentionica'], type='http', auth="user", website=True)
    def reports_retention_ica(self, **kw):
        """ICA retention certificate form"""
        user_companies = self._get_user_companies()

        values = {
            'page_name': 'certificateica',
            'certificate': True,
            'user_companies': user_companies,
            'has_multiple_companies': len(user_companies) > 1,
            'default_company': request.env.company,
        }

        if 'msg' in kw:
            values['msg'] = kw.get("msg")

        return request.render("l10n_co_reports_retention.portal_my_retentionica", values)
    
    @http.route(['/my/retentioniva'], type='http', auth="user", website=True)
    def reports_retention_iva(self, **kw):
        """IVA retention certificate form"""
        user_companies = self._get_user_companies()

        values = {
            'page_name': 'certificateiva',
            'certificate': True,
            'user_companies': user_companies,
            'has_multiple_companies': len(user_companies) > 1,
            'default_company': request.env.company,
        }

        if 'msg' in kw:
            values['msg'] = kw.get("msg")

        return request.render("l10n_co_reports_retention.portal_my_retentioniva", values)
    
    @http.route(['/my/retentionretefu'], type='http', auth="user", website=True)
    def reports_retention_retefu(self, **kw):
        """Fuente retention certificate form"""
        user_companies = self._get_user_companies()

        values = {
            'page_name': 'certificateretefu',
            'certificate': True,
            'user_companies': user_companies,
            'has_multiple_companies': len(user_companies) > 1,
            'default_company': request.env.company,
        }

        if 'msg' in kw:
            values['msg'] = kw.get("msg")

        return request.render("l10n_co_reports_retention.portal_my_retentionfu", values)
    
    def _validate_dates(self, date_from, date_to, redirect_url):
        if not date_from or not date_to:
            return request.redirect(redirect_url + '?msg=Las fechas son requeridas')

        try:
            date_from_obj = datetime.strptime(date_from, "%Y-%m-%d")
            date_to_obj = datetime.strptime(date_to, "%Y-%m-%d")

            if date_from_obj.year != date_to_obj.year:
                return request.redirect(redirect_url + '?msg=Las fechas no deben ser de diferentes años')

            if date_from_obj > date_to_obj:
                return request.redirect(redirect_url + '?msg=La fecha inicial no puede ser mayor a la fecha final')

        except ValueError as e:
            _logger.error(f"Error al validar fechas: {e}")
            return request.redirect(redirect_url + '?msg=Formato de fecha inválido')

        return None

    def _get_company_id(self, company_id_param):
        """Get and validate company ID"""
        if isinstance(company_id_param, str):
            try:
                company_id = int(company_id_param)
            except ValueError:
                company_id = request.env.company.id
        else:
            company_id = company_id_param or request.env.company.id

        # Verificar que el usuario tenga acceso a la compañía
        if company_id not in request.env.user.company_ids.ids:
            company_id = request.env.company.id

        return company_id

    def _generate_retention_pdf(self, report_ref, company_id, date_from, date_to, redirect_url):
        """Generate retention certificate PDF"""
        try:
            report = request.env.ref(report_ref).sudo()
            options = report.get_options({})
            options["date"]["period_type"] = 'fiscalyear'
            options["date"]["filter"] = 'custom'
            options["date"]["date_from"] = date_from
            options["date"]["date_to"] = date_to
            options["unfold_all"] = True
            options["multi_company"] = [{'id': company_id}]
            options["partner_ids"] = [str(request.env.user.partner_id.id)]

            data = {'wizard_values': {
                'expedition_date': date_to,
                'declaration_date': date_to,
                'article': 'ART. 10 DECRETO 836/91',
            }}

            report_service = request.env['ir.actions.report'].sudo()
            pdf_content, _ = report_service.with_context(
                allowed_company_ids=[company_id],
                options=options,
                from_retention=True
            )._render_qweb_pdf(
                'l10n_co_reports.action_report_certification',
                res_ids=None,
                data=data
            )

            return pdf_content

        except Exception as e:
            _logger.error(f"Error al generar PDF de retención: {e}")
            return None

    @http.route(['/my/retentionica/report'], type='http', auth="user", methods=['POST'], csrf=True)
    def reports_retention_reteicare(self, **kw):
        """Generate ICA retention certificate PDF"""
        date_from = kw.get("date_from")
        date_to = kw.get("date_to")
        redirect_url = '/my/retentionica'

        # Validar fechas
        validation_error = self._validate_dates(date_from, date_to, redirect_url)
        if validation_error:
            return validation_error

        # Obtener y validar compañía
        company_id = self._get_company_id(kw.get("company_id"))

        # Generar PDF
        pdf_content = self._generate_retention_pdf(
            'l10n_co_reports.l10n_co_reports_ica',
            company_id,
            date_from,
            date_to,
            redirect_url
        )

        if not pdf_content:
            return request.redirect(redirect_url + '?msg=No se pudo generar el certificado para este periodo')

        pdf_filename = f'Certificado_Retencion_ICA_{date_from}_{date_to}.pdf'

        return request.make_response(pdf_content, [
            ('Content-Type', 'application/pdf'),
            ('Content-Disposition', f'attachment; filename="{pdf_filename}"')
        ])
    
    @http.route(['/my/retentioniva/report'], type='http', auth="user", methods=['POST'], csrf=True)
    def reports_retention_reteivare(self, **kw):
        """Generate IVA retention certificate PDF"""
        date_from = kw.get("date_from")
        date_to = kw.get("date_to")
        redirect_url = '/my/retentioniva'

        # Validar fechas
        validation_error = self._validate_dates(date_from, date_to, redirect_url)
        if validation_error:
            return validation_error

        # Obtener y validar compañía
        company_id = self._get_company_id(kw.get("company_id"))

        # Generar PDF
        pdf_content = self._generate_retention_pdf(
            'l10n_co_reports.l10n_co_reports_iva',
            company_id,
            date_from,
            date_to,
            redirect_url
        )

        if not pdf_content:
            return request.redirect(redirect_url + '?msg=No se pudo generar el certificado para este periodo')

        pdf_filename = f'Certificado_Retencion_IVA_{date_from}_{date_to}.pdf'

        return request.make_response(pdf_content, [
            ('Content-Type', 'application/pdf'),
            ('Content-Disposition', f'attachment; filename="{pdf_filename}"')
        ])
    
    @http.route(['/my/retentionfu/report'], type='http', auth="user", methods=['POST'], csrf=True)
    def reports_retention_retefure(self, **kw):
        """Generate Fuente retention certificate PDF"""
        date_from = kw.get("date_from")
        date_to = kw.get("date_to")
        redirect_url = '/my/retentionretefu'

        # Validar fechas
        validation_error = self._validate_dates(date_from, date_to, redirect_url)
        if validation_error:
            return validation_error

        # Obtener y validar compañía
        company_id = self._get_company_id(kw.get("company_id"))

        # Generar PDF
        pdf_content = self._generate_retention_pdf(
            'l10n_co_reports.l10n_co_reports_fuente',
            company_id,
            date_from,
            date_to,
            redirect_url
        )

        if not pdf_content:
            return request.redirect(redirect_url + '?msg=No se pudo generar el certificado para este periodo')

        pdf_filename = f'Certificado_Retencion_Fuente_{date_from}_{date_to}.pdf'

        return request.make_response(pdf_content, [
            ('Content-Type', 'application/pdf'),
            ('Content-Disposition', f'attachment; filename="{pdf_filename}"')
        ])