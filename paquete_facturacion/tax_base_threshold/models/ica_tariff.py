# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class IcaTariff(models.Model):
    """
    Tarifas de ICA (Industria y Comercio) por Municipio y Actividad CIIU

    El ICA es un impuesto municipal que varía según:
    - Municipio donde se realiza la actividad
    - Actividad económica (código CIIU)
    - Tipo de actividad (Industrial, Comercial, Servicios, Financiera)

    La tarifa se expresa en "por mil" (‰)
    Ejemplo: 9.66 ‰ significa 0.966%
    """
    _name = 'ica.tariff'
    _description = 'ICA Tariff by Municipality and CIIU'
    _order = 'municipality_id, ciiu_id'
    _rec_name = 'display_name'

    # Identificación
    municipality_id = fields.Many2one(
        'res.city',
        string='Municipality',
        required=True,
        ondelete='restrict',
        help='Municipality where the ICA rate applies'
    )
    state_id = fields.Many2one(
        'res.country.state',
        string='Department',
        related='municipality_id.state_id',
        store=True,
        readonly=True
    )
    # CIIU - campo opcional, solo si el módulo lavish_erp está instalado
    ciiu_id = fields.Many2one(
        'lavish.ciiu',
        string='CIIU Activity',
        required=False,
        ondelete='restrict',
        help='Economic activity code (CIIU) - requires lavish_erp module'
    )
    ciiu_code = fields.Char(
        string='CIIU Code',
        help='Manual CIIU code if lavish.ciiu is not available'
    )
    ciiu_name = fields.Char(
        string='CIIU Description',
        help='Manual CIIU description if lavish.ciiu is not available'
    )

    # Clasificación de actividad
    activity_type = fields.Selection([
        ('industrial', 'Industrial'),
        ('commercial', 'Commercial'),
        ('services', 'Services'),
        ('financial', 'Financial'),
    ], string='Activity Type', required=True, default='commercial')

    # Tarifa
    rate = fields.Float(
        string='Rate (‰)',
        digits=(10, 4),
        required=True,
        help='Rate in per thousand (‰). Example: 9.66 means 0.966%'
    )
    rate_percent = fields.Float(
        string='Rate (%)',
        compute='_compute_rate_percent',
        digits=(10, 6),
        store=True,
        help='Rate converted to percentage'
    )

    # Vigencia
    date_from = fields.Date(
        string='Valid From',
        required=True,
        default=fields.Date.context_today
    )
    date_to = fields.Date(
        string='Valid To'
    )
    fiscal_year = fields.Char(
        string='Fiscal Year',
        compute='_compute_fiscal_year',
        store=True
    )

    # Campos adicionales
    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=True
    )
    active = fields.Boolean(
        string='Active',
        default=True
    )
    notes = fields.Text(
        string='Notes'
    )
    legal_reference = fields.Char(
        string='Legal Reference',
        help='Municipal agreement or decree reference'
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='company_id.currency_id',
        readonly=True,
        store=True
    )

    # Base mínima para aplicar ICA
    min_base_type = fields.Selection([
        ('none', 'No Minimum'),
        ('uvt', 'UVT'),
        ('fixed', 'Fixed Amount'),
    ], string='Minimum Base Type', default='none',
        help='Type of minimum base threshold for ICA application')
    min_base_uvt = fields.Float(
        string='Minimum Base (UVT)',
        digits=(10, 2),
        default=0,
        help='Minimum base in UVT units. ICA will not apply if base is below this threshold.'
    )
    min_base_fixed = fields.Float(
        string='Minimum Base (Fixed)',
        digits='Product Price',
        default=0,
        help='Minimum base in fixed amount. ICA will not apply if base is below this threshold.'
    )
    min_base_computed = fields.Float(
        string='Computed Min Base',
        compute='_compute_min_base',
        digits='Product Price',
        help='Computed minimum base in currency for current date'
    )

    _sql_constraints = [
        ('municipality_ciiu_date_uniq',
         'unique(municipality_id, ciiu_id, date_from, company_id)',
         'A tariff for this municipality, CIIU and date already exists!')
    ]

    @api.depends('rate')
    def _compute_rate_percent(self):
        for record in self:
            record.rate_percent = record.rate / 10.0  # ‰ to %

    @api.depends('min_base_type', 'min_base_uvt', 'min_base_fixed')
    def _compute_min_base(self):
        """Compute the minimum base in currency based on type"""
        TaxParam = self.env['tax.general.parameter']
        today = fields.Date.context_today(self)

        for record in self:
            if record.min_base_type == 'uvt' and record.min_base_uvt:
                uvt_value = TaxParam.get_uvt_value(today, record.company_id.id)
                record.min_base_computed = record.min_base_uvt * uvt_value
            elif record.min_base_type == 'fixed' and record.min_base_fixed:
                record.min_base_computed = record.min_base_fixed
            else:
                record.min_base_computed = 0.0

    @api.depends('date_from')
    def _compute_fiscal_year(self):
        for record in self:
            record.fiscal_year = str(record.date_from.year) if record.date_from else ''

    @api.depends('municipality_id', 'ciiu_id', 'ciiu_code', 'rate')
    def _compute_display_name(self):
        for record in self:
            parts = []
            if record.municipality_id:
                parts.append(record.municipality_id.name)
            if record.ciiu_id:
                parts.append(f"[{record.ciiu_id.code}]")
            elif record.ciiu_code:
                parts.append(f"[{record.ciiu_code}]")
            if record.rate:
                parts.append(f"{record.rate}‰")
            record.display_name = ' - '.join(parts) if parts else _('New Tariff')

    @api.constrains('rate')
    def _check_rate(self):
        for record in self:
            if record.rate < 0:
                raise ValidationError(_('Rate cannot be negative.'))
            if record.rate > 100:
                raise ValidationError(_('Rate seems too high. Please verify (max 100‰ = 10%).'))

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for record in self:
            if record.date_to and record.date_from > record.date_to:
                raise ValidationError(_('End date must be after start date.'))

    @api.model
    def get_tariff(self, municipality_id, ciiu_id=None, date_eval=None, company_id=None):
        """
        Get the applicable ICA tariff for a municipality and CIIU activity

        Args:
            municipality_id: ID of res.city (municipality)
            ciiu_id: ID of lavish.ciiu (economic activity) - optional
            date_eval: Date for evaluation (default: today)
            company_id: Company ID (default: current company)

        Returns:
            ica.tariff record or False if not found
        """
        if not municipality_id:
            return False

        if not date_eval:
            date_eval = fields.Date.context_today(self)
        if not company_id:
            company_id = self.env.company.id

        # Construir dominio base
        domain = [
            ('municipality_id', '=', municipality_id),
            ('date_from', '<=', date_eval),
            '|',
            ('date_to', '>=', date_eval),
            ('date_to', '=', False),
            ('active', '=', True),
            '|',
            ('company_id', '=', company_id),
            ('company_id', '=', False),
        ]

        # Si se especifica CIIU, buscar primero con CIIU específico
        if ciiu_id:
            domain_ciiu = domain + [('ciiu_id', '=', ciiu_id)]
            tariff = self.search(domain_ciiu, limit=1, order='company_id desc, date_from desc')
            if tariff:
                return tariff

        # Buscar tarifa general del municipio (sin CIIU específico)
        domain_general = domain + [('ciiu_id', '=', False)]
        tariff = self.search(domain_general, limit=1, order='company_id desc, date_from desc')

        return tariff

    @api.model
    def get_rate_for_municipality(self, municipality_id, ciiu_id=None, date_eval=None, company_id=None):
        """
        Get the ICA rate for a specific municipality

        Args:
            municipality_id: ID of res.city (municipality)
            ciiu_id: ID of lavish.ciiu (economic activity) - optional
            date_eval: Date for evaluation
            company_id: Company ID

        Returns:
            dict with rate_per_mil, rate_percent, tariff_id, or empty values if not found
        """
        result = {
            'rate_per_mil': 0.0,
            'rate_percent': 0.0,
            'tariff_id': False,
            'municipality': '',
            'ciiu': '',
            'found': False,
        }

        if not municipality_id:
            return result

        # Find tariff
        tariff = self.get_tariff(
            municipality_id=municipality_id,
            ciiu_id=ciiu_id,
            date_eval=date_eval,
            company_id=company_id
        )

        if tariff:
            municipality = self.env['res.city'].browse(municipality_id)
            ciiu_display = ''
            if tariff.ciiu_id:
                ciiu_display = f"[{tariff.ciiu_id.code}] {tariff.ciiu_id.name}"
            elif tariff.ciiu_code:
                ciiu_display = f"[{tariff.ciiu_code}] {tariff.ciiu_name or ''}"

            result.update({
                'rate_per_mil': tariff.rate,
                'rate_percent': tariff.rate_percent,
                'tariff_id': tariff.id,
                'municipality': municipality.name if municipality else '',
                'ciiu': ciiu_display,
                'found': True,
            })
        else:
            municipality = self.env['res.city'].browse(municipality_id)
            _logger.info(
                f'No ICA tariff found for municipality {municipality.name if municipality else municipality_id}'
            )

        return result

    @api.model
    def get_rate_for_partner(self, partner, date_eval=None, municipality_id=None):
        """
        Get the ICA rate for a partner based on their municipality and CIIU

        Args:
            partner: res.partner record
            date_eval: Date for evaluation
            municipality_id: Override municipality ID (from invoice city_id)

        Returns:
            dict with rate_per_mil, rate_percent, tariff_id, or empty values if not found
        """
        result = {
            'rate_per_mil': 0.0,
            'rate_percent': 0.0,
            'tariff_id': False,
            'municipality': '',
            'ciiu': '',
            'found': False,
        }

        # Si se proporciona municipality_id desde el contexto (ej: del move.city_id), usarlo
        if municipality_id:
            # Get CIIU from partner if available
            ciiu_id = None
            if partner:
                if hasattr(partner, 'ciiu_id') and partner.ciiu_id:
                    ciiu_id = partner.ciiu_id.id
                elif hasattr(partner, 'ciiu_activity') and partner.ciiu_activity:
                    ciiu_id = partner.ciiu_activity.id

            return self.get_rate_for_municipality(
                municipality_id=municipality_id,
                ciiu_id=ciiu_id,
                date_eval=date_eval
            )

        if not partner:
            return result

        # Get municipality - try city_id first, then postal city
        municipality = None
        if hasattr(partner, 'city_id') and partner.city_id:
            municipality = partner.city_id
        elif hasattr(partner, 'postal_city_id') and partner.postal_city_id:
            municipality = partner.postal_city_id

        # Get CIIU
        ciiu = None
        ciiu_id = None
        if hasattr(partner, 'ciiu_id') and partner.ciiu_id:
            ciiu = partner.ciiu_id
            ciiu_id = ciiu.id
        elif hasattr(partner, 'ciiu_activity') and partner.ciiu_activity:
            ciiu = partner.ciiu_activity
            ciiu_id = ciiu.id

        if not municipality:
            _logger.debug(
                f'ICA tariff not found for partner {partner.id}: '
                f'municipality={municipality}'
            )
            return result

        # Find tariff
        tariff = self.get_tariff(
            municipality_id=municipality.id,
            ciiu_id=ciiu_id,
            date_eval=date_eval
        )

        if tariff:
            ciiu_display = ''
            if ciiu:
                ciiu_display = f"[{ciiu.code}] {ciiu.name}"
            elif tariff.ciiu_code:
                ciiu_display = f"[{tariff.ciiu_code}] {tariff.ciiu_name or ''}"

            result.update({
                'rate_per_mil': tariff.rate,
                'rate_percent': tariff.rate_percent,
                'tariff_id': tariff.id,
                'municipality': municipality.name,
                'ciiu': ciiu_display,
                'found': True,
            })
        else:
            _logger.info(
                f'No ICA tariff found for municipality {municipality.name}'
                + (f' and CIIU {ciiu.code}' if ciiu else '')
            )

        return result

    def get_min_base_amount(self, date_eval=None, company_id=None):
        """
        Get the minimum base amount for this tariff at a specific date.

        Args:
            date_eval: Date for UVT value lookup
            company_id: Company ID for UVT value lookup

        Returns:
            float: Minimum base amount in currency
        """
        self.ensure_one()

        if self.min_base_type == 'none':
            return 0.0

        if not date_eval:
            date_eval = fields.Date.context_today(self)
        if not company_id:
            company_id = self.company_id.id or self.env.company.id

        if self.min_base_type == 'uvt' and self.min_base_uvt:
            TaxParam = self.env['tax.general.parameter']
            uvt_value = TaxParam.get_uvt_value(date_eval, company_id)
            return self.min_base_uvt * uvt_value
        elif self.min_base_type == 'fixed' and self.min_base_fixed:
            return self.min_base_fixed

        return 0.0

    def calculate_ica(self, base_amount, partner=None, municipality_id=None,
                      ciiu_id=None, date_eval=None):
        """
        Calculate ICA amount for a given base

        Args:
            base_amount: Base amount to apply ICA
            partner: res.partner record (optional, to get CIIU)
            municipality_id: Explicit municipality ID (from invoice city_id)
            ciiu_id: Explicit CIIU ID
            date_eval: Date for evaluation

        Returns:
            dict with calculation details including:
            - applies: True if ICA applies (tariff found and base >= minimum)
            - below_threshold: True if base is below minimum threshold
            - min_base: Minimum base threshold amount
        """
        result = {
            'base_amount': base_amount,
            'ica_amount': 0.0,
            'rate_per_mil': 0.0,
            'rate_percent': 0.0,
            'municipality': '',
            'ciiu': '',
            'applies': False,
            'below_threshold': False,
            'min_base': 0.0,
            'tariff_id': False,
        }

        # Intentar obtener municipality_id del contexto si no se proporciona
        if not municipality_id:
            municipality_id = self._context.get('municipality_id') or self._context.get('city_id')

        if not date_eval:
            date_eval = self._context.get('invoice_date') or fields.Date.context_today(self)

        tariff = False

        # Si tenemos municipality_id explícito, usarlo directamente
        if municipality_id:
            # Obtener CIIU del partner si está disponible
            partner_ciiu_id = ciiu_id
            if not partner_ciiu_id and partner:
                if hasattr(partner, 'ciiu_id') and partner.ciiu_id:
                    partner_ciiu_id = partner.ciiu_id.id
                elif hasattr(partner, 'ciiu_activity') and partner.ciiu_activity:
                    partner_ciiu_id = partner.ciiu_activity.id

            tariff = self.get_tariff(
                municipality_id=municipality_id,
                ciiu_id=partner_ciiu_id,
                date_eval=date_eval
            )

            if tariff:
                municipality = self.env['res.city'].browse(municipality_id)
                ciiu_display = ''
                if tariff.ciiu_id:
                    ciiu_display = f"[{tariff.ciiu_id.code}] {tariff.ciiu_id.name}"
                elif tariff.ciiu_code:
                    ciiu_display = f"[{tariff.ciiu_code}] {tariff.ciiu_name or ''}"

                result.update({
                    'rate_per_mil': tariff.rate,
                    'rate_percent': tariff.rate_percent,
                    'municipality': municipality.name if municipality else '',
                    'ciiu': ciiu_display,
                    'tariff_id': tariff.id,
                })

        elif partner:
            # Fallback: usar partner para obtener municipio
            rate_info = self.get_rate_for_partner(partner, date_eval)
            if rate_info['found']:
                result.update({
                    'rate_per_mil': rate_info['rate_per_mil'],
                    'rate_percent': rate_info['rate_percent'],
                    'municipality': rate_info['municipality'],
                    'ciiu': rate_info['ciiu'],
                    'tariff_id': rate_info['tariff_id'],
                })
                if rate_info['tariff_id']:
                    tariff = self.browse(rate_info['tariff_id'])

        # Validate minimum base threshold
        if tariff:
            min_base = tariff.get_min_base_amount(date_eval)
            result['min_base'] = min_base

            if min_base > 0 and abs(base_amount) < min_base:
                # Base is below threshold - ICA does not apply
                result['below_threshold'] = True
                result['applies'] = False
                _logger.debug(
                    f'ICA not applied: base {base_amount} < min_base {min_base} '
                    f'for municipality {result["municipality"]}'
                )
            else:
                # Base meets threshold - ICA applies
                result['applies'] = True
                # ICA = Base × (Rate ‰ / 1000)
                result['ica_amount'] = abs(base_amount) * (result['rate_per_mil'] / 1000.0)

        return result


class AccountTaxIca(models.Model):
    """
    Extension of account.tax for ICA dynamic calculation
    """
    _inherit = 'account.tax'

    is_ica_dynamic = fields.Boolean(
        string='Dynamic ICA Rate',
        default=False,
        help='If checked, ICA rate will be calculated dynamically based on municipality and CIIU'
    )
    ica_default_rate = fields.Float(
        string='Default ICA Rate (‰)',
        digits=(10, 4),
        help='Default rate in per thousand if no specific tariff is found'
    )

    @api.model
    def _add_tax_details_in_base_line(self, base_line, company, rounding_method=None):
        """
        Override to propagate municipality context to tax computation.

        This ensures that dynamic ICA taxes receive the municipality_id
        from the base_line's record (account.move.line) when computing.
        """
        # Get municipality context from the base_line record if available
        record = base_line.get('record')
        municipality_id = False
        invoice_date = False

        if record and hasattr(record, 'move_id') and record.move_id:
            move = record.move_id
            if hasattr(move, 'city_id') and move.city_id:
                municipality_id = move.city_id.id
            invoice_date = move.invoice_date or move.date

        # If we have municipality context, add it to tax_ids
        if municipality_id and base_line.get('tax_ids'):
            base_line['tax_ids'] = base_line['tax_ids'].with_context(
                municipality_id=municipality_id,
                city_id=municipality_id,
                invoice_date=invoice_date,
            )

        return super()._add_tax_details_in_base_line(base_line, company, rounding_method)

    def _eval_tax_amount_price_excluded(self, batch, raw_base, evaluation_context):
        """
        Override Odoo 18 tax calculation for dynamic ICA

        La ciudad para el cálculo de ICA se obtiene del contexto (city_id/municipality_id)
        que viene del campo city_id del account.move:
        - Para facturas de venta: ciudad de la compañía
        - Para facturas de compra: ciudad del proveedor
        """
        self.ensure_one()

        if self.is_ica_dynamic:
            # Obtener municipality_id del contexto
            municipality_id = self._context.get('municipality_id') or self._context.get('city_id')
            date_eval = self._context.get('invoice_date') or fields.Date.context_today(self)

            # Get ICA rate from tariffs using municipality from context
            ica_result = self.env['ica.tariff'].with_context(
                municipality_id=municipality_id
            ).calculate_ica(
                base_amount=raw_base,
                municipality_id=municipality_id,
                date_eval=date_eval
            )

            if ica_result['applies']:
                # ICA amount (negativo porque es retención)
                ica_amount = ica_result['ica_amount'] * -1
                _logger.info(
                    f'ICA Dynamic: municipality={municipality_id}, '
                    f'rate={ica_result["rate_per_mil"]}‰, '
                    f'base={raw_base}, amount={ica_amount}'
                )
                return ica_amount
            elif self.ica_default_rate:
                # Use default rate
                ica_amount = abs(raw_base) * (self.ica_default_rate / 1000.0) * -1
                _logger.info(
                    f'ICA Default Rate: {self.ica_default_rate}‰, base={raw_base}, amount={ica_amount}'
                )
                return ica_amount
            else:
                _logger.debug(f'ICA: No tariff found for municipality={municipality_id}')
                return 0.0

        return super()._eval_tax_amount_price_excluded(batch, raw_base, evaluation_context)

    def _compute_amount(self, base_amount, price_unit, quantity, product, partner, fixed_multiplicator=1):
        """
        Override for compatibility with older code paths
        """
        self.ensure_one()

        if self.is_ica_dynamic:
            municipality_id = self._context.get('municipality_id') or self._context.get('city_id')
            date_eval = self._context.get('invoice_date') or fields.Date.context_today(self)

            if partner and hasattr(partner, 'is_ica') and not partner.is_ica:
                return 0.0

            ica_result = self.env['ica.tariff'].calculate_ica(
                base_amount=base_amount,
                partner=partner,
                municipality_id=municipality_id,
                date_eval=date_eval
            )

            if ica_result['applies']:
                return ica_result['ica_amount'] * -1
            elif self.ica_default_rate:
                return abs(base_amount) * (self.ica_default_rate / 1000.0) * -1
            return 0.0

        return super()._compute_amount(
            base_amount=base_amount,
            price_unit=price_unit,
            quantity=quantity,
            product=product,
            partner=partner,
            fixed_multiplicator=fixed_multiplicator
        )
