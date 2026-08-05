# -*- coding: utf-8 -*-
import json
import logging
import base64
from io import BytesIO

from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

CERTIFICATE_TYPES = [
    ('ica', 'Retención de ICA'),
    ('iva', 'Retención de IVA'),
    ('timbre', 'Retención de Timbre'),
    ('fuente', 'Retención en la Fuente'),
]


class L10nCoExogenousCertificateSendWizard(models.TransientModel):
    _name = 'l10n_co.exogenous_certificate_send_wizard'
    _description = 'Wizard de generación y envío masivo de certificados'

    config_id = fields.Many2one(
        comodel_name='l10n_co.exogenous_certificate_config',
        string='Configuración',
        required=True)

    certificate_type = fields.Selection(
        selection=CERTIFICATE_TYPES,
        string='Tipo certificado',
        related='config_id.certificate_type',
        readonly=True)

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        related='config_id.company_id',
        readonly=True)

    period_type = fields.Selection([
        ('annual', 'Anual'),
        ('bimonthly', 'Bimestral'),
        ('quarterly', 'Trimestral'),
        ('quadrimester', 'Cuatrimestral'),
        ('monthly', 'Mensual'),
    ], string='Tipo de período',
        default='annual',
        required=True,
        help='Define cómo se agrupan los datos en el auxiliar y el certificado')

    year = fields.Integer(
        string='Año gravable',
        default=lambda self: fields.Date.today().year,
        required=True)

    period_number = fields.Selection([
        ('1', '1'), ('2', '2'), ('3', '3'), ('4', '4'),
        ('5', '5'), ('6', '6'), ('7', '7'), ('8', '8'),
        ('9', '9'), ('10', '10'), ('11', '11'), ('12', '12'),
    ], string='Período',
        default='1',
        help='Número del período según el tipo seleccionado')

    date_from = fields.Date(
        string='Fecha inicial',
        compute='_compute_dates',
        store=True,
        readonly=False)

    date_to = fields.Date(
        string='Fecha final',
        compute='_compute_dates',
        store=True,
        readonly=False)

    expedition_date = fields.Date(
        string='Fecha de expedición',
        required=True,
        default=fields.Date.context_today)

    @api.depends('period_type', 'year', 'period_number')
    def _compute_dates(self):
        """Calcula fecha inicial y final según el tipo de período"""
        from calendar import monthrange
        for rec in self:
            if not rec.year:
                continue
            y = rec.year
            p = int(rec.period_number or '1')

            if rec.period_type == 'annual':
                rec.date_from = fields.Date.to_date(f'{y}-01-01')
                rec.date_to = fields.Date.to_date(f'{y}-12-31')
            elif rec.period_type == 'monthly':
                m = min(p, 12)
                _, last_day = monthrange(y, m)
                rec.date_from = fields.Date.to_date(f'{y}-{m:02d}-01')
                rec.date_to = fields.Date.to_date(f'{y}-{m:02d}-{last_day}')
            elif rec.period_type == 'bimonthly':
                # Bimestre: 1=Ene-Feb, 2=Mar-Abr, ... 6=Nov-Dic
                bim = min(p, 6)
                m_start = (bim - 1) * 2 + 1
                m_end = m_start + 1
                _, last_day = monthrange(y, m_end)
                rec.date_from = fields.Date.to_date(f'{y}-{m_start:02d}-01')
                rec.date_to = fields.Date.to_date(f'{y}-{m_end:02d}-{last_day}')
            elif rec.period_type == 'quarterly':
                # Trimestre: 1=Ene-Mar, 2=Abr-Jun, 3=Jul-Sep, 4=Oct-Dic
                q = min(p, 4)
                m_start = (q - 1) * 3 + 1
                m_end = m_start + 2
                _, last_day = monthrange(y, m_end)
                rec.date_from = fields.Date.to_date(f'{y}-{m_start:02d}-01')
                rec.date_to = fields.Date.to_date(f'{y}-{m_end:02d}-{last_day}')
            elif rec.period_type == 'quadrimester':
                # Cuatrimestre: 1=Ene-Abr, 2=May-Ago, 3=Sep-Dic
                quad = min(p, 3)
                m_start = (quad - 1) * 4 + 1
                m_end = m_start + 3
                _, last_day = monthrange(y, m_end)
                rec.date_from = fields.Date.to_date(f'{y}-{m_start:02d}-01')
                rec.date_to = fields.Date.to_date(f'{y}-{m_end:02d}-{last_day}')

    def _get_period_label(self):
        """Retorna etiqueta legible del período seleccionado"""
        self.ensure_one()
        labels = {
            'annual': 'Año %s' % self.year,
            'monthly': {
                '1': 'Enero', '2': 'Febrero', '3': 'Marzo', '4': 'Abril',
                '5': 'Mayo', '6': 'Junio', '7': 'Julio', '8': 'Agosto',
                '9': 'Septiembre', '10': 'Octubre', '11': 'Noviembre', '12': 'Diciembre',
            },
            'bimonthly': {
                '1': 'Enero - Febrero', '2': 'Marzo - Abril',
                '3': 'Mayo - Junio', '4': 'Julio - Agosto',
                '5': 'Septiembre - Octubre', '6': 'Noviembre - Diciembre',
            },
            'quarterly': {
                '1': '1er Trimestre', '2': '2do Trimestre',
                '3': '3er Trimestre', '4': '4to Trimestre',
            },
            'quadrimester': {
                '1': '1er Cuatrimestre', '2': '2do Cuatrimestre',
                '3': '3er Cuatrimestre',
            },
        }
        if self.period_type == 'annual':
            return labels['annual']
        period_labels = labels.get(self.period_type, {})
        return '%s %s' % (period_labels.get(self.period_number, ''), self.year)

    city_id = fields.Many2one(
        comodel_name='res.city',
        string='Ciudad',
        help='Filtrar por ciudad. Aplica para ICA')

    partner_ids = fields.Many2many(
        comodel_name='res.partner',
        relation='l10n_co_cert_wizard_partner_rel',
        string='Terceros',
        help='Si se seleccionan, genera solo para estos terceros')

    # Exclusiones (heredadas del formato de exógena)
    journal_ids = fields.Many2many(
        comodel_name='account.journal',
        relation='l10n_co_cert_wizard_journal_rel',
        string='Diarios a excluir')

    send_email = fields.Boolean(
        string='Enviar por correo',
        default=False,
        help='Enviar automáticamente los certificados generados por correo electrónico')

    # Resultado de consulta
    preview_line_ids = fields.One2many(
        comodel_name='l10n_co.exogenous_certificate_send_wizard_line',
        inverse_name='wizard_id',
        string='Vista previa')

    state = fields.Selection([
        ('config', 'Configuración'),
        ('preview', 'Vista previa'),
        ('done', 'Completado'),
    ], default='config', string='Estado')

    generated_count = fields.Integer(
        string='Certificados generados',
        readonly=True)

    sent_count = fields.Integer(
        string='Certificados enviados',
        readonly=True)

    error_count = fields.Integer(
        string='Certificados con error',
        readonly=True)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_from > rec.date_to:
                raise ValidationError(_('La fecha inicial debe ser anterior a la fecha final'))

    def action_consult(self):
        """Consulta los datos y muestra vista previa agrupada por tercero y cuenta"""
        self.ensure_one()
        self.preview_line_ids.unlink()

        config = self.config_id
        if not config.line_ids:
            raise UserError(_('No hay cuentas contables configuradas para este tipo de certificado'))

        # Obtener cuentas configuradas, filtradas por ciudad si aplica
        config_lines = config.line_ids
        if self.city_id and config.certificate_type == 'ica':
            config_lines = config_lines.filtered(
                lambda l: l.city_id == self.city_id or not l.city_id)

        # Resolver cuentas de todas las líneas
        all_accounts = self.env['account.account']
        for cl in config_lines:
            all_accounts |= cl.get_resolved_accounts()
        account_ids = all_accounts.ids
        if not account_ids:
            raise UserError(_('No hay cuentas contables que coincidan con los filtros'))

        # Construir dominio base reutilizando la lógica de exógena
        results = self._get_certificate_data(account_ids, config_lines)

        if not results:
            raise UserError(_('No se encontraron movimientos contables para el período y cuentas configuradas'))

        # Crear líneas de vista previa con detalle de documentos
        WizardLine = self.env['l10n_co.exogenous_certificate_send_wizard_line']
        WizardDetail = self.env['l10n_co.exogenous_certificate_send_wizard_detail']

        for key, data in results.items():
            partner_id, group_id, city_id = key
            line = WizardLine.create({
                'wizard_id': self.id,
                'partner_id': partner_id,
                'account_id': data.get('account_id', False),
                'concept_name': data.get('concept_name', ''),
                'city_id': city_id or False,
                'base_amount': data['base_amount'],
                'retained_amount': data['retained_amount'],
                'partner_email': data.get('email', ''),
            })

            # Crear detalle de movimientos
            detail_vals = []
            for dl in data.get('detail_lines', []):
                detail_vals.append({
                    'line_id': line.id,
                    'move_line_id': dl['move_line_id'],
                    'move_id': dl['move_id'],
                    'move_name': dl['move_name'],
                    'date': dl['date'],
                    'account_id': dl['account_id'],
                    'partner_id': dl['partner_id'],
                    'debit': dl['debit'],
                    'credit': dl['credit'],
                    'tax_base_amount': dl['tax_base_amount'],
                    'ref': dl['ref'],
                })
            if detail_vals:
                WizardDetail.create(detail_vals)

        self.state = 'preview'
        return self._reopen_wizard_full()

    def _get_certificate_data(self, account_ids, config_lines):
        """Consulta account.move.line agrupado por tercero, cuenta y ciudad.

        Reutiliza la misma lógica de dominio que format_setting._get_information_by_account_move_line
        """
        AML = self.env['account.move.line']
        domain = [
            *AML._check_company_domain(self.company_id),
            ('parent_state', '=', 'posted'),
            ('account_id', 'in', account_ids),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('partner_id', '!=', False),
        ]

        if self.journal_ids:
            domain.append(('journal_id', 'not in', self.journal_ids.ids))

        if self.partner_ids:
            domain.append(('partner_id', 'in', self.partner_ids.ids))

        move_lines = self.env['account.move.line'].search_read(
            domain=domain,
            fields=['id', 'partner_id', 'account_id', 'debit', 'credit',
                    'tax_base_amount', 'move_id', 'date', 'ref', 'name'],
            order='partner_id, account_id, date')

        if not move_lines:
            return {}

        # Mapeo cuenta -> (config_line_id, ciudad, naturaleza, nombre_concepto)
        account_config_map = {}  # account_id -> config_line
        for cl in config_lines:
            resolved = cl.get_resolved_accounts()
            for acc in resolved:
                account_config_map[acc.id] = cl

        # Agrupar por (partner_id, config_line_id, city_id) para respetar los conceptos
        # Si la línea tiene concept_name, varias cuentas se agrupan bajo un solo concepto
        results = {}
        partner_ids_set = set()
        for ml in move_lines:
            partner_id = ml['partner_id'][0]
            account_id = ml['account_id'][0]

            cl = account_config_map.get(account_id)
            if not cl:
                continue

            city_id = cl.city_id.id if cl.city_id else False
            nature = cl.nature_account or 'cr_db'

            debit = ml['debit'] or 0
            credit = ml['credit'] or 0
            tax_base = ml['tax_base_amount'] or 0

            if nature == 'debit' and debit == 0:
                continue
            if nature == 'credit' and credit == 0:
                continue
            if nature == 'base_calc_db' and debit <= 0:
                continue
            if nature == 'base_calc_cr' and credit <= 0:
                continue
            if nature == 'base_calc_db_cr' and (debit - credit) == 0:
                continue
            if nature == 'base_calc_cr_db' and (credit - debit) == 0:
                continue

            if nature == 'debit':
                retained_delta = debit
            elif nature == 'credit':
                retained_delta = credit
            elif nature == 'cr_db':
                retained_delta = credit - debit
            elif nature == 'db_cr':
                retained_delta = debit - credit
            elif nature == 'base_calc_db':
                retained_delta = tax_base if debit > 0 else 0
            elif nature == 'base_calc_cr':
                retained_delta = tax_base if credit > 0 else 0
            elif nature == 'base_calc_db_cr':
                retained_delta = tax_base if (debit - credit) != 0 else 0
            elif nature == 'base_calc_cr_db':
                retained_delta = tax_base if (credit - debit) != 0 else 0
            elif nature == 'tax_base_amount':
                retained_delta = tax_base
            else:
                retained_delta = credit - debit

            if cl.concept_name:
                group_id = ('cl', cl.id)
                concept_label = cl.concept_name
            else:
                group_id = ('acc', account_id)
                concept_label = ml['account_id'][1] if ml['account_id'] else ''

            key = (partner_id, group_id, city_id)
            if key not in results:
                results[key] = {
                    'base_amount': 0.0,
                    'retained_amount': 0.0,
                    'concept_name': concept_label,
                    'account_id': account_id,
                    'detail_lines': [],
                }
            partner_ids_set.add(partner_id)

            results[key]['detail_lines'].append({
                'move_line_id': ml['id'],
                'move_id': ml['move_id'][0] if ml['move_id'] else False,
                'move_name': ml['move_id'][1] if ml['move_id'] else '',
                'date': ml['date'],
                'account_id': account_id,
                'partner_id': partner_id,
                'debit': debit,
                'credit': credit,
                'tax_base_amount': tax_base,
                'ref': ml['ref'] or '',
            })

            results[key]['retained_amount'] += retained_delta

            if nature.startswith('base_calc') or nature == 'tax_base_amount':
                results[key]['base_amount'] += tax_base
            elif credit > 0:
                results[key]['base_amount'] += tax_base
            elif debit > 0:
                results[key]['base_amount'] -= tax_base

        results = {k: v for k, v in results.items() if v['retained_amount'] != 0 or v['detail_lines']}

        # Obtener correos de los partners
        partners = self.env['res.partner'].browse(list(partner_ids_set)).read(['email'])
        email_map = {p['id']: p['email'] or '' for p in partners}
        for key in results:
            results[key]['email'] = email_map.get(key[0], '')

        return results

    def action_generate(self):
        """Genera los certificados PDF y crea registros históricos"""
        self.ensure_one()

        if not self.preview_line_ids:
            raise UserError(_('Primero debe consultar los datos'))

        # Agrupar líneas por tercero (y ciudad si ICA)
        partner_groups = {}
        for line in self.preview_line_ids:
            if self.config_id.certificate_type == 'ica':
                group_key = (line.partner_id.id, line.city_id.id if line.city_id else False)
            else:
                group_key = (line.partner_id.id, False)

            if group_key not in partner_groups:
                partner_groups[group_key] = {
                    'partner': line.partner_id,
                    'city': line.city_id,
                    'lines': [],
                    'total_base': 0.0,
                    'total_retained': 0.0,
                    'email': line.partner_email,
                }
            partner_groups[group_key]['lines'].append(line)
            partner_groups[group_key]['total_base'] += line.base_amount
            partner_groups[group_key]['total_retained'] += line.retained_amount

        generated = 0
        sent = 0
        errors = 0
        history_ids = []

        for group_key, group_data in partner_groups.items():
            try:
                # Generar consecutivo
                consecutive = False
                if self.config_id.consecutive_sequence_id:
                    consecutive = self.config_id.consecutive_sequence_id.next_by_id()

                # Preparar datos del certificado para el PDF
                cert_data = self._prepare_certificate_data(group_data)
                cert_data['consecutive'] = consecutive or ''

                # Generar PDF
                pdf_content = self._generate_certificate_pdf(cert_data)

                partner = group_data['partner']
                city = group_data['city']

                filename = 'Certificado_%s_%s_%s.pdf' % (
                    dict(CERTIFICATE_TYPES).get(self.config_id.certificate_type, ''),
                    partner.vat or partner.name,
                    self.date_from.year if self.date_from else '',
                )

                # Crear registro histórico
                history_vals = {
                    'config_id': self.config_id.id,
                    'partner_id': partner.id,
                    'city_id': city.id if city else False,
                    'date_from': self.date_from,
                    'date_to': self.date_to,
                    'generation_date': fields.Datetime.now(),
                    'email': group_data['email'] or partner.email,
                    'user_id': self.env.user.id,
                    'state': 'pending',
                    'consecutive': consecutive,
                    'pdf_file': base64.b64encode(pdf_content) if pdf_content else False,
                    'pdf_filename': filename,
                    'certificate_data': json.dumps(cert_data, default=str),
                    'total_base': group_data['total_base'],
                    'total_retained': group_data['total_retained'],
                }
                history = self.env['l10n_co.exogenous_certificate_history'].create(history_vals)
                history_ids.append(history.id)
                generated += 1

                # Enviar por correo si está configurado
                if self.send_email and (group_data['email'] or partner.email):
                    try:
                        history.write({
                            'notification_date': fields.Datetime.now(),
                            'state': 'in_progress',
                        })
                        history._send_certificate_email()
                        history.write({
                            'state': 'sent',
                            'send_date': fields.Datetime.now(),
                        })
                        sent += 1
                    except Exception as e:
                        history.write({
                            'state': 'error',
                            'error_message': str(e),
                        })
                        errors += 1
                        _logger.warning("Error enviando certificado a %s: %s", partner.name, str(e))

            except Exception as e:
                errors += 1
                _logger.exception("Error generando certificado para %s", group_data['partner'].name)

        self.write({
            'state': 'done',
            'generated_count': generated,
            'sent_count': sent,
            'error_count': errors,
        })

        # Si hay registros, abrir la vista de historial
        if history_ids:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Certificados generados'),
                'res_model': 'l10n_co.exogenous_certificate_history',
                'view_mode': 'list,form',
                'domain': [('id', 'in', history_ids)],
                'context': {'create': False},
            }

        return self._reopen_wizard()

    def _prepare_certificate_data(self, group_data):
        """Prepara los datos estructurados para renderizar el certificado PDF"""
        partner = group_data['partner']
        company = self.company_id
        config = self.config_id
        type_labels = dict(CERTIFICATE_TYPES)
        now = fields.Datetime.now()

        cert_data = {
            'certificate_type': config.certificate_type,
            'certificate_title': config.report_title or type_labels.get(config.certificate_type, ''),
            'article': config.article or '',
            'report_style': config.report_style or 'classic',
            'signer_name': config.signer_name or '',
            'signer_position': config.signer_position or '',
            'signer_signature': config.signer_signature.decode() if config.signer_signature else '',
            'expedition_date': str(self.expedition_date),
            # Generación = momento del PDF. Notificación = lo mismo si el wizard
            # va a enviar el email (es la "hora prevista" que aparece en el PDF
            # antes de despachar). Si no se envía, queda vacía.
            'generation_date': fields.Datetime.to_string(now),
            'notification_date': fields.Datetime.to_string(now) if self.send_email else '',
            'year': self.year or (self.date_from.year if self.date_from else ''),
            'period_type': self.period_type,
            'period_label': self._get_period_label(),
            'date_from': str(self.date_from),
            'date_to': str(self.date_to),
            # Datos empresa
            'company_name': company.name or '',
            'company_vat': company.vat or '',
            'company_city': company.city or '',
            'company_street': company.street or '',
            # Datos tercero
            'partner_name': partner.name or '',
            'partner_commercial_name': partner.commercial_company_name or '',
            'partner_vat': partner.vat or '',
            'partner_city': partner.city or '',
            'partner_street': partner.street or '',
            'partner_phone': partner.phone or '',
            'partner_email': group_data.get('email', ''),
            # Ciudad (para ICA)
            'city_name': group_data['city'].name if group_data.get('city') else '',
            # Usuario
            'user_name': self.env.user.name or '',
            # Totales
            'total_base': group_data['total_base'],
            'total_retained': group_data['total_retained'],
            # Líneas detalle
            'lines': [],
        }

        # Strip the leading account code from the concept label so the PDF
        # shows "SERVICIOS GENERALES DECLARANTES 4%" instead of
        # "23652502 SERVICIOS GENERALES DECLARANTES 4%". The DIAN certificate
        # is for the partner — the account code is internal accounting noise.
        import re as _re
        for line in group_data['lines']:
            raw_name = line.concept_name or (line.account_id.name if line.account_id else '')
            clean_name = _re.sub(r'^\s*\d+\s+', '', raw_name) if raw_name else ''
            cert_data['lines'].append({
                'account_code': line.account_id.code if line.account_id else '',
                'account_name': clean_name,
                'base_amount': line.base_amount,
                'retained_amount': line.retained_amount,
                'city_name': line.city_id.name if line.city_id else '',
            })

        return cert_data

    def _generate_certificate_pdf(self, cert_data):
        """Genera el PDF del certificado usando el template QWeb.

        TODO: Esta función contiene la lógica de renderizado del PDF.
        El usuario debe definir la fórmula de cálculo para retenciones
        especiales (IVA con bimestres, etc.)
        """
        # Renderizar con QWeb
        report_action = self.env.ref(
            'l10n_co_exogenous_information_reporting.action_report_certificate_retention',
            raise_if_not_found=False)

        if report_action:
            # v14 signature: _render_qweb_pdf(self, res_ids=None, data=None)
            # (v15+ added an extra report_ref positional arg in front, which is
            # why the v18-style call with report_action.report_name as a
            # positional collided with res_ids in v14 — "got multiple values
            # for argument 'res_ids'"). Pass res_ids as the wizard id so the
            # report engine has a document to render against.
            pdf_content, _ = report_action._render_qweb_pdf(
                res_ids=[self.id],
                data={'cert_data': cert_data})
            return pdf_content

        _logger.warning("Template de reporte no encontrado, generando PDF básico")
        return False

    def action_back_to_config(self):
        """Vuelve al paso de configuración"""
        self.ensure_one()
        self.preview_line_ids.unlink()
        self.state = 'config'
        return self._reopen_wizard()

    def _reopen_wizard(self):
        """Reabre el wizard en popup"""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Envío masivo de certificados'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _reopen_wizard_full(self):
        """Reabre el wizard en pantalla completa para ver el auxiliar"""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Auxiliar de certificados - Vista previa'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }


class L10nCoExogenousCertificateSendWizardLine(models.TransientModel):
    _name = 'l10n_co.exogenous_certificate_send_wizard_line'
    _description = 'Línea de vista previa del wizard de certificados'
    _order = 'partner_id, account_id'

    wizard_id = fields.Many2one(
        comodel_name='l10n_co.exogenous_certificate_send_wizard',
        string='Wizard',
        required=True,
        ondelete='cascade')

    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Tercero',
        readonly=True)

    partner_vat = fields.Char(
        related='partner_id.vat',
        string='NIT')

    account_id = fields.Many2one(
        comodel_name='account.account',
        string='Cuenta contable',
        readonly=True)

    concept_name = fields.Char(
        string='Concepto',
        readonly=True,
        help='Nombre del concepto en el certificado')

    city_id = fields.Many2one(
        comodel_name='res.city',
        string='Ciudad',
        readonly=True)

    base_amount = fields.Float(
        string='Base retención',
        digits=(16, 2),
        readonly=True)

    retained_amount = fields.Float(
        string='Retenido',
        digits=(16, 2),
        readonly=True)

    partner_email = fields.Char(
        string='Correo',
        readonly=True)

    detail_ids = fields.One2many(
        comodel_name='l10n_co.exogenous_certificate_send_wizard_detail',
        inverse_name='line_id',
        string='Detalle movimientos')

    detail_count = fields.Integer(
        string='Docs',
        compute='_compute_detail_count')

    @api.depends('detail_ids')
    def _compute_detail_count(self):
        for rec in self:
            rec.detail_count = len(rec.detail_ids)

    def action_view_detail(self):
        """Abre el detalle de movimientos de esta línea"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Detalle movimientos - %s') % self.partner_id.name,
            'res_model': 'l10n_co.exogenous_certificate_send_wizard_detail',
            'view_mode': 'list',
            'domain': [('line_id', '=', self.id)],
            'target': 'new',
            'context': {'create': False, 'edit': False},
        }


class L10nCoExogenousCertificateSendWizardDetail(models.TransientModel):
    _name = 'l10n_co.exogenous_certificate_send_wizard_detail'
    _description = 'Detalle de movimiento contable del certificado'
    _order = 'date, move_name'

    line_id = fields.Many2one(
        comodel_name='l10n_co.exogenous_certificate_send_wizard_line',
        string='Línea',
        required=True,
        ondelete='cascade')

    move_line_id = fields.Many2one(
        comodel_name='account.move.line',
        string='Apunte contable',
        readonly=True)

    move_id = fields.Many2one(
        comodel_name='account.move',
        string='Asiento',
        readonly=True)

    move_name = fields.Char(
        string='Documento',
        readonly=True)

    date = fields.Date(
        string='Fecha',
        readonly=True)

    account_id = fields.Many2one(
        comodel_name='account.account',
        string='Cuenta',
        readonly=True)

    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Tercero',
        readonly=True)

    debit = fields.Float(
        string='Débito',
        digits=(16, 2),
        readonly=True)

    credit = fields.Float(
        string='Crédito',
        digits=(16, 2),
        readonly=True)

    tax_base_amount = fields.Float(
        string='Base imponible',
        digits=(16, 2),
        readonly=True)

    ref = fields.Char(
        string='Referencia',
        readonly=True)
