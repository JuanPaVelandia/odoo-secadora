# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class WithholdingConcept(models.Model):
    """
    Conceptos de Retención en la Fuente Colombia

    Ejemplos:
    - Compras (declarantes/no declarantes)
    - Servicios generales
    - Servicios profesionales / Honorarios
    - Arrendamientos
    - Salarios (tabla progresiva)
    - ReteIVA
    - ReteICA
    """
    _name = 'withholding.concept'
    _description = 'Withholding Concept'
    _order = 'sequence, code'
    _rec_name = 'display_name'

    # Identificación
    code = fields.Char(
        string='Code',
        required=True,
        help='Unique code for the concept (e.g., COMPRAS, SERVICIOS, HONORARIOS)'
    )
    name = fields.Char(
        string='Name',
        required=True,
        translate=True
    )
    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=True
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10
    )
    active = fields.Boolean(
        string='Active',
        default=True
    )

    # Clasificación
    concept_type = fields.Selection([
        ('retefuente', 'Retención en la Fuente'),
        ('reteiva', 'Retención de IVA'),
        ('reteica', 'Retención de ICA'),
        ('inc', 'Impuesto Nacional al Consumo'),
        ('iva', 'IVA'),
        ('other', 'Otro'),
    ], string='Concept Type', required=True, default='retefuente')

    # Tipo de cálculo
    calculation_type = fields.Selection([
        ('fixed_rate', 'Tarifa Fija'),
        ('progressive', 'Tabla Progresiva (UVT)'),
        ('by_contributor', 'Por Tipo de Contribuyente'),
    ], string='Calculation Type', required=True, default='fixed_rate',
        help='''
        - Tarifa Fija: Una sola tarifa (ej: IVA 19%)
        - Tabla Progresiva: Rangos en UVT (ej: Retención salarios)
        - Por Tipo Contribuyente: Diferente tarifa para declarantes/no declarantes
        '''
    )

    # ========== CONFIGURACIÓN DE BASE ==========
    requires_minimum_base = fields.Boolean(
        string='Requires Minimum Base',
        default=True,
        help='If checked, tax only applies when base exceeds minimum threshold'
    )
    base_type = fields.Selection([
        ('fixed', 'Fixed Amount (COP)'),
        ('uvt', 'UVT Units'),
    ], string='Base Type', default='uvt')

    # NUEVO: Configuración de cómo se evalúa la base
    base_evaluation = fields.Selection([
        ('line', 'Per Line (Por Línea)'),
        ('document', 'Document Total (Total Documento)'),
        ('document_by_tax', 'Document Total by Tax (Total por Impuesto)'),
    ], string='Base Evaluation', default='line', required=True,
        help='''
        - Per Line: Evalúa la base mínima en cada línea individualmente
        - Document Total: Evalúa la base mínima sobre el total del documento
        - Document Total by Tax: Suma todas las líneas con este impuesto y evalúa
        '''
    )

    # NUEVO: Activar/Desactivar validación
    validate_base_enabled = fields.Boolean(
        string='Validate Base Enabled',
        default=False,  # Desactivado por defecto
        help='Enable/disable base validation. If disabled, tax always applies regardless of base amount.'
    )

    # NUEVO: Aplicar en documentos
    apply_on_sale = fields.Boolean(
        string='Apply on Sales',
        default=True,
        help='Apply this concept on sale orders and invoices'
    )
    apply_on_purchase = fields.Boolean(
        string='Apply on Purchases',
        default=True,
        help='Apply this concept on purchase orders and bills'
    )

    # NUEVO: Modo de aplicación del impuesto
    tax_application_mode = fields.Selection([
        ('per_line', 'Por Línea (Individual)'),
        ('all_lines', 'Todas las Líneas (General)'),
    ], string='Tax Application Mode', default='per_line', required=True,
        help='''
        - Por Línea: El impuesto se aplica individualmente a cada línea que lo tenga configurado
        - Todas las Líneas: Si el documento tiene este impuesto, se aplica a todas las líneas del documento
        '''
    )

    # NUEVO: Período de cálculo (mensual, por operación)
    calculation_period = fields.Selection([
        ('operation', 'Por Operación'),
        ('monthly', 'Acumulado Mensual'),
        ('yearly', 'Acumulado Anual'),
    ], string='Calculation Period', default='operation', required=True,
        help='''
        - Por Operación: Evalúa la base mínima en cada transacción
        - Acumulado Mensual: Suma las operaciones del mes para evaluar la base (Art. 401 E.T.)
        - Acumulado Anual: Suma las operaciones del año para evaluar la base
        '''
    )

    # Relaciones
    rate_ids = fields.One2many(
        'withholding.rate',
        'concept_id',
        string='Rates by Year'
    )
    bracket_ids = fields.One2many(
        'withholding.bracket',
        'concept_id',
        string='Progressive Brackets'
    )
    tax_ids = fields.One2many(
        'account.tax',
        'withholding_concept_id',
        string='Related Taxes'
    )

    # Campos informativos
    description = fields.Text(
        string='Description',
        translate=True
    )
    legal_reference = fields.Char(
        string='Legal Reference',
        help='E.g., Art. 383 E.T., Decreto 0572/2025'
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company
    )

    # NUEVO: Información de UVT actual
    current_uvt_value = fields.Float(
        string='Current UVT Value',
        compute='_compute_current_uvt_value',
        digits='Product Price'
    )
    current_min_base = fields.Float(
        string='Current Min Base (COP)',
        compute='_compute_current_min_base',
        digits='Product Price'
    )

    _sql_constraints = [
        ('code_company_uniq', 'unique(code, company_id)',
         'The concept code must be unique per company!')
    ]

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for record in self:
            record.display_name = f"[{record.code}] {record.name}" if record.code else record.name

    @api.depends('company_id')
    def _compute_current_uvt_value(self):
        today = fields.Date.context_today(self)
        for record in self:
            record.current_uvt_value = self.env['tax.general.parameter'].get_uvt_value(
                date_eval=today,
                company_id=record.company_id.id if record.company_id else self.env.company.id
            )

    @api.depends('rate_ids', 'current_uvt_value', 'base_type')
    def _compute_current_min_base(self):
        today = fields.Date.context_today(self)
        for record in self:
            rate_info = record.get_current_rate(date_eval=today)
            record.current_min_base = rate_info.get('min_base_amount', 0)

    def get_current_rate(self, date_eval=None, contributor_type='declarant'):
        """
        Get the applicable rate for a given date and contributor type

        Args:
            date_eval: Date to evaluate (default: today)
            contributor_type: 'declarant' or 'non_declarant'

        Returns:
            dict with rate_percent, min_base_uvt, min_base_amount
        """
        self.ensure_one()
        if not date_eval:
            date_eval = fields.Date.context_today(self)

        # Get UVT value for the date
        uvt_value = self.env['tax.general.parameter'].get_uvt_value(
            date_eval=date_eval,
            company_id=self.company_id.id if self.company_id else self.env.company.id
        )

        # Find applicable rate
        rate = self.rate_ids.filtered(
            lambda r: r.active and
                      r.date_from <= date_eval and
                      (not r.date_to or r.date_to >= date_eval)
        )

        if not rate:
            _logger.warning(f'No rate found for concept {self.code} on {date_eval}')
            return {
                'rate_percent': 0,
                'min_base_uvt': 0,
                'min_base_amount': 0,
                'uvt_value': uvt_value,
            }

        rate = rate[0]  # Get first matching rate

        # Determine rate based on contributor type
        if self.calculation_type == 'by_contributor':
            rate_percent = rate.rate_declarant if contributor_type == 'declarant' else rate.rate_non_declarant
        else:
            rate_percent = rate.rate_percent

        # Calculate minimum base in COP
        if self.base_type == 'uvt':
            min_base_amount = rate.min_base_uvt * uvt_value
        else:
            min_base_amount = rate.min_base_fixed

        return {
            'rate_percent': rate_percent,
            'min_base_uvt': rate.min_base_uvt,
            'min_base_amount': min_base_amount,
            'min_base_fixed': rate.min_base_fixed,
            'uvt_value': uvt_value,
            'rate_id': rate.id,
        }

    def get_accumulated_base(self, partner_id, date_eval=None, tax_id=None):
        """
        Get accumulated base for monthly/yearly calculation

        Args:
            partner_id: Partner ID to calculate for
            date_eval: Date to evaluate (determines month/year)
            tax_id: Specific tax to filter by

        Returns:
            float: Accumulated base amount
        """
        self.ensure_one()
        if not date_eval:
            date_eval = fields.Date.context_today(self)

        # Determine date range based on calculation period
        if self.calculation_period == 'monthly':
            # First day of the month
            date_from = date_eval.replace(day=1)
            # Last day of the month
            if date_eval.month == 12:
                date_to = date_eval.replace(day=31)
            else:
                next_month = date_eval.replace(month=date_eval.month + 1, day=1)
                from datetime import timedelta
                date_to = next_month - timedelta(days=1)
        elif self.calculation_period == 'yearly':
            date_from = date_eval.replace(month=1, day=1)
            date_to = date_eval.replace(month=12, day=31)
        else:
            return 0.0  # No accumulation for per-operation

        # Search for invoices with this concept/tax
        domain = [
            ('partner_id', '=', partner_id),
            ('invoice_date', '>=', date_from),
            ('invoice_date', '<=', date_to),
            ('state', '=', 'posted'),
            ('move_type', 'in', ['in_invoice', 'in_refund', 'out_invoice', 'out_refund']),
        ]

        moves = self.env['account.move'].search(domain)
        accumulated_base = 0.0

        for move in moves:
            for line in move.invoice_line_ids:
                # Check if line has the tax with this concept
                for tax in line.tax_ids:
                    if tax.withholding_concept_id.id == self.id:
                        accumulated_base += abs(line.price_subtotal)

        return accumulated_base

    def should_apply_tax(self, base_amount, date_eval=None, contributor_type='declarant',
                         document_type='sale', total_document_base=None, partner_id=None):
        """
        Determine if the tax should be applied based on configuration

        Args:
            base_amount: Base amount to evaluate (line or document total)
            date_eval: Date for evaluation
            contributor_type: 'declarant' or 'non_declarant'
            document_type: 'sale' or 'purchase'
            total_document_base: Total document base (for document-level evaluation)
            partner_id: Partner ID for accumulated calculation

        Returns:
            dict with 'applies' (bool), 'reason' (str), 'rate_percent' (float)
        """
        self.ensure_one()

        result = {
            'applies': False,
            'reason': '',
            'rate_percent': 0,
            'min_base_amount': 0,
            'base_evaluated': 0,
            'accumulated_base': 0,
        }

        # Check if concept is active
        if not self.active:
            result['reason'] = _('Concept is inactive')
            return result

        # Check document type
        if document_type == 'sale' and not self.apply_on_sale:
            result['reason'] = _('Concept not applicable on sales')
            return result
        if document_type == 'purchase' and not self.apply_on_purchase:
            result['reason'] = _('Concept not applicable on purchases')
            return result

        # If validation is disabled, always apply
        if not self.validate_base_enabled:
            rate_info = self.get_current_rate(date_eval, contributor_type)
            result['applies'] = True
            result['rate_percent'] = rate_info['rate_percent']
            result['reason'] = _('Base validation disabled')
            return result

        # Determine which base to evaluate
        if self.base_evaluation == 'document' and total_document_base is not None:
            base_to_evaluate = total_document_base
        elif self.base_evaluation == 'document_by_tax' and total_document_base is not None:
            base_to_evaluate = total_document_base
        else:
            base_to_evaluate = base_amount

        # For monthly/yearly calculation, add accumulated base
        if self.calculation_period in ('monthly', 'yearly') and partner_id:
            accumulated = self.get_accumulated_base(partner_id, date_eval)
            result['accumulated_base'] = accumulated
            base_to_evaluate += accumulated

        result['base_evaluated'] = base_to_evaluate

        # Get current rate and minimum base
        rate_info = self.get_current_rate(date_eval, contributor_type)
        result['min_base_amount'] = rate_info['min_base_amount']
        result['rate_percent'] = rate_info['rate_percent']

        # Check minimum base requirement
        if self.requires_minimum_base:
            if abs(base_to_evaluate) < rate_info['min_base_amount']:
                result['reason'] = _(
                    'Base $%(base)s < Min $%(min)s (%(uvt)s UVT)',
                    base=f"{abs(base_to_evaluate):,.0f}",
                    min=f"{rate_info['min_base_amount']:,.0f}",
                    uvt=f"{rate_info['min_base_uvt']:.2f}"
                )
                return result

        result['applies'] = True
        result['reason'] = _('Tax applies')
        return result

    def calculate_withholding(self, base_amount, date_eval=None, contributor_type='declarant',
                              document_type='sale', total_document_base=None):
        """
        Calculate withholding amount for a given base

        Args:
            base_amount: Base amount in COP
            date_eval: Date for evaluation
            contributor_type: 'declarant' or 'non_declarant'
            document_type: 'sale' or 'purchase'
            total_document_base: Total document base for evaluation

        Returns:
            dict with calculation details
        """
        self.ensure_one()
        if not date_eval:
            date_eval = fields.Date.context_today(self)

        result = {
            'concept_id': self.id,
            'concept_code': self.code,
            'base_amount': base_amount,
            'withholding_amount': 0,
            'rate_applied': 0,
            'applies': False,
            'reason': '',
            'base_evaluation': self.base_evaluation,
        }

        # For progressive calculation
        if self.calculation_type == 'progressive':
            return self._calculate_progressive(base_amount, date_eval)

        # Check if tax should apply
        should_apply = self.should_apply_tax(
            base_amount=base_amount,
            date_eval=date_eval,
            contributor_type=contributor_type,
            document_type=document_type,
            total_document_base=total_document_base
        )

        if not should_apply['applies']:
            result['reason'] = should_apply['reason']
            result['min_base_amount'] = should_apply['min_base_amount']
            return result

        # Get current rate
        rate_info = self.get_current_rate(date_eval, contributor_type)

        # Calculate withholding on the actual line base (not document total)
        result['applies'] = True
        result['rate_applied'] = rate_info['rate_percent']
        result['withholding_amount'] = abs(base_amount) * rate_info['rate_percent'] / 100
        result['uvt_value'] = rate_info['uvt_value']
        result['min_base_uvt'] = rate_info['min_base_uvt']
        result['min_base_amount'] = rate_info['min_base_amount']

        return result

    def _calculate_progressive(self, base_amount, date_eval):
        """
        Calculate withholding using progressive brackets (for salary withholding)

        Uses the formula: (Base_UVT - resta_uvt) * tarifa% + mas_uvt

        Returns:
            dict with calculation details including bracket info
        """
        self.ensure_one()

        result = {
            'concept_id': self.id,
            'concept_code': self.code,
            'base_amount': base_amount,
            'withholding_amount': 0,
            'rate_applied': 0,
            'applies': False,
            'bracket_number': 0,
            'reason': '',
        }

        # Get UVT value
        uvt_value = self.env['tax.general.parameter'].get_uvt_value(
            date_eval=date_eval,
            company_id=self.company_id.id if self.company_id else self.env.company.id
        )

        if not uvt_value:
            result['reason'] = _('UVT value not configured for this date')
            return result

        # Convert base to UVT
        base_uvt = abs(base_amount) / uvt_value
        result['base_uvt'] = base_uvt
        result['uvt_value'] = uvt_value

        # Find applicable bracket
        brackets = self.bracket_ids.filtered(
            lambda b: b.active and
                      b.date_from <= date_eval and
                      (not b.date_to or b.date_to >= date_eval)
        ).sorted('from_uvt')

        if not brackets:
            result['reason'] = _('No brackets configured for this date')
            return result

        # Find the bracket that applies
        applicable_bracket = None
        for bracket in brackets:
            if bracket.from_uvt < base_uvt <= bracket.to_uvt:
                applicable_bracket = bracket
                break
            elif bracket.to_uvt == 0 and base_uvt > bracket.from_uvt:
                # Last bracket (infinite)
                applicable_bracket = bracket
                break

        if not applicable_bracket:
            # Base is in first bracket (0% rate)
            result['reason'] = _('Base %(uvt).2f UVT is below minimum threshold', uvt=base_uvt)
            return result

        # Calculate using bracket formula
        # Formula: (Base_UVT - resta_uvt) * tarifa% + mas_uvt
        base_restante = base_uvt - applicable_bracket.subtract_uvt
        withholding_uvt = (base_restante * applicable_bracket.rate_percent / 100) + applicable_bracket.plus_uvt

        result['applies'] = True
        result['bracket_number'] = applicable_bracket.bracket_number
        result['rate_applied'] = applicable_bracket.rate_percent
        result['subtract_uvt'] = applicable_bracket.subtract_uvt
        result['plus_uvt'] = applicable_bracket.plus_uvt
        result['withholding_uvt'] = withholding_uvt
        result['withholding_amount'] = withholding_uvt * uvt_value
        result['formula'] = f"({base_uvt:.2f} - {applicable_bracket.subtract_uvt}) × {applicable_bracket.rate_percent}% + {applicable_bracket.plus_uvt} UVT"

        return result
