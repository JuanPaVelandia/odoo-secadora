# -*- coding: utf-8 -*-
from odoo import api, fields, models
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import math


class TreasuryDashboard(models.AbstractModel):
    _name = 'treasury.dashboard'
    _description = 'Dashboard de Tesorería'

    @api.model
    def get_dashboard_data(self, date_from=None, date_to=None, projection_period='weekly', projection_count=5):
        """Obtiene todos los datos necesarios para el dashboard

        Args:
            date_from: Fecha inicial del periodo (string YYYY-MM-DD)
            date_to: Fecha final del periodo (string YYYY-MM-DD)
            projection_period: Tipo de periodo para proyección ('weekly', 'biweekly', 'monthly', etc.)
            projection_count: Número de periodos a proyectar
        """
        import logging
        _logger = logging.getLogger(__name__)

        # Convertir fechas si vienen como string
        today = fields.Date.today()
        if date_from:
            if isinstance(date_from, str):
                date_from = fields.Date.from_string(date_from)
        else:
            date_from = today.replace(day=1)  # Primer día del mes actual

        if date_to:
            if isinstance(date_to, str):
                date_to = fields.Date.from_string(date_to)
        else:
            date_to = today

        # Guardar en contexto para usar en submétodos
        self = self.with_context(date_from=date_from, date_to=date_to)

        user_info = self._get_user_info()

        data = {
            'liquidity': {},
            'daily_flow': {},
            'pending_payments': {},
            'advances': {},
            'advance_requests': {},
            'payments_by_state': [],
            'monthly_trend': [],
            'top_customers': [],
            'top_suppliers': [],
            'bank_list': [],
            'cash_list': [],
            'recent_payments': [],
            'recent_receipts': [],
            'user_info': user_info,
            # Proyecciones
            'cash_flow_projection': [],
            'payment_aging': {'receivable': [], 'payable': []},
            'orders_forecast': {'sales': {}, 'purchases': {}},
            'payment_trends': {'customer_avg_days': 0, 'supplier_avg_days': 0},
            # Flujo de caja anual
            'yearly_cash_flow': [],
            # Vencimientos próximos (próxima semana)
            'upcoming_due': {
                'payable_count': 0, 'payable_amount': 0,
                'receivable_count': 0, 'receivable_amount': 0
            },
            # Info del periodo seleccionado
            'period_info': {
                'date_from': str(date_from),
                'date_to': str(date_to),
            },
            # KPIs de gastos bancarios
            'bank_expenses_kpi': {}
        }

        # Cargar cada sección con manejo de errores
        try:
            data['liquidity'] = self._get_liquidity_data()
        except Exception as e:
            _logger.error(f"Error loading liquidity: {e}")

        try:
            data['daily_flow'] = self._get_daily_flow()
        except Exception as e:
            _logger.error(f"Error loading daily_flow: {e}")

        try:
            data['pending_payments'] = self._get_pending_payments()
        except Exception as e:
            _logger.error(f"Error loading pending_payments: {e}")

        try:
            data['advances'] = self._get_advances_data()
        except Exception as e:
            _logger.error(f"Error loading advances: {e}")

        try:
            data['advance_requests'] = self._get_advance_requests_data()
        except Exception as e:
            _logger.error(f"Error loading advance_requests: {e}")

        try:
            data['payments_by_state'] = self._get_payments_by_state()
        except Exception as e:
            _logger.error(f"Error loading payments_by_state: {e}")

        try:
            data['monthly_trend'] = self._get_monthly_trend()
        except Exception as e:
            _logger.error(f"Error loading monthly_trend: {e}")

        try:
            data['top_customers'] = self._get_top_customers()
        except Exception as e:
            _logger.error(f"Error loading top_customers: {e}")

        try:
            data['top_suppliers'] = self._get_top_suppliers()
        except Exception as e:
            _logger.error(f"Error loading top_suppliers: {e}")

        try:
            data['bank_list'] = self._get_bank_list()
        except Exception as e:
            _logger.error(f"Error loading bank_list: {e}")

        try:
            data['cash_list'] = self._get_cash_list()
        except Exception as e:
            _logger.error(f"Error loading cash_list: {e}")

        try:
            data['recent_payments'] = self._get_recent_payments()
        except Exception as e:
            _logger.error(f"Error loading recent_payments: {e}")

        try:
            data['recent_receipts'] = self._get_recent_receipts()
        except Exception as e:
            _logger.error(f"Error loading recent_receipts: {e}")

        # Datos de proyección
        try:
            data['cash_flow_projection'] = self._get_cash_flow_projection()
        except Exception as e:
            _logger.error(f"Error loading cash_flow_projection: {e}")

        try:
            data['payment_aging'] = self._get_payment_aging()
        except Exception as e:
            _logger.error(f"Error loading payment_aging: {e}")

        try:
            data['orders_forecast'] = self._get_orders_forecast()
        except Exception as e:
            _logger.error(f"Error loading orders_forecast: {e}")

        try:
            data['payment_trends'] = self._get_partner_payment_trends()
        except Exception as e:
            _logger.error(f"Error loading payment_trends: {e}")

        try:
            data['upcoming_due'] = self._get_upcoming_due()
        except Exception as e:
            _logger.error(f"Error loading upcoming_due: {e}")

        try:
            data['yearly_cash_flow'] = self._get_yearly_cash_flow()
        except Exception as e:
            _logger.error(f"Error loading yearly_cash_flow: {e}")

        try:
            data['cash_flow_forecast'] = self._get_cash_flow_forecast()
        except Exception as e:
            _logger.error(f"Error loading cash_flow_forecast: {e}")

        try:
            data['bank_expenses_kpi'] = self._get_bank_expenses_kpi()
        except Exception as e:
            _logger.error(f"Error loading bank_expenses_kpi: {e}")

        return data

    def _get_user_info(self):
        """Obtiene información del usuario actual"""
        user = self.env.user
        partner = user.partner_id
        company = user.company_id

        avatar_url = '/web/image?model=res.partner&id=%s&field=avatar_128' % partner.id if partner.avatar_128 else '/web/static/img/placeholder.png'
        company_logo = '/web/image?model=res.company&id=%s&field=logo' % company.id if company and company.logo else None

        return {
            'name': user.name or 'Usuario',
            'email': user.email or '',
            'avatar_url': avatar_url,
            'job_title': partner.function or 'Usuario',
            'company': company.name if company else '',
            'company_logo': company_logo,
            'currency_symbol': company.currency_id.symbol if company and company.currency_id else '$',
        }

    def _get_liquidity_data(self):
        """Calcula saldos de bancos y cajas usando SQL agregado (optimizado)"""
        company = self.env.company

        # Una sola query para obtener todos los saldos agrupados por tipo de diario
        query = """
            SELECT
                j.type,
                COUNT(DISTINCT j.id) as journal_count,
                COALESCE(SUM(aml.balance), 0) as total_balance
            FROM account_journal j
            LEFT JOIN account_account aa ON j.default_account_id = aa.id
            LEFT JOIN account_move_line aml ON aml.account_id = aa.id
                AND aml.parent_state = 'posted'
                AND aml.company_id = %s
            WHERE j.type IN ('bank', 'cash')
                AND j.company_id = %s
                AND j.active = TRUE
            GROUP BY j.type
        """
        self.env.cr.execute(query, (company.id, company.id))
        results = self.env.cr.dictfetchall()

        bank_balance = 0
        bank_count = 0
        cash_balance = 0
        cash_count = 0

        for row in results:
            if row['type'] == 'bank':
                bank_balance = row['total_balance'] or 0
                bank_count = row['journal_count'] or 0
            elif row['type'] == 'cash':
                cash_balance = row['total_balance'] or 0
                cash_count = row['journal_count'] or 0

        return {
            'bank_count': bank_count,
            'cash_count': cash_count,
            'bank_balance': bank_balance,
            'cash_balance': cash_balance,
            'total_liquidity': bank_balance + cash_balance
        }

    def _get_daily_flow(self):
        """Calcula ingresos y egresos del día"""
        company = self.env.company
        today = fields.Date.today()

        query = """
            SELECT
                COUNT(CASE WHEN payment_type = 'inbound' THEN 1 END) as income_count,
                COUNT(CASE WHEN payment_type = 'outbound' THEN 1 END) as expenses_count,
                COALESCE(SUM(CASE WHEN payment_type = 'inbound' THEN amount ELSE 0 END), 0) as today_income,
                COALESCE(SUM(CASE WHEN payment_type = 'outbound' THEN amount ELSE 0 END), 0) as today_expenses
            FROM account_payment
            WHERE date = %s
                AND state IN ('posted', 'paid')
                AND company_id = %s
        """
        self.env.cr.execute(query, (today, company.id))
        result = self.env.cr.dictfetchone()
        result['today_net_flow'] = result['today_income'] - result['today_expenses']
        return result

    def _get_pending_payments(self):
        """Calcula pagos y cobros pendientes (incluye notas de crédito)"""
        company = self.env.company

        query = """
            SELECT
                COUNT(CASE WHEN move_type IN ('out_invoice', 'out_refund') THEN 1 END) as customer_count,
                COUNT(CASE WHEN move_type IN ('in_invoice', 'in_refund') THEN 1 END) as supplier_count,
                COALESCE(SUM(CASE WHEN move_type IN ('out_invoice', 'out_refund') THEN amount_residual ELSE 0 END), 0) as pending_customer_payments,
                COALESCE(SUM(CASE WHEN move_type IN ('in_invoice', 'in_refund') THEN amount_residual ELSE 0 END), 0) as pending_supplier_payments
            FROM account_move
            WHERE state = 'posted'
                AND payment_state IN ('not_paid', 'partial')
                AND move_type IN ('out_invoice', 'out_refund', 'in_invoice', 'in_refund')
                AND company_id = %s
        """
        self.env.cr.execute(query, (company.id,))
        result = self.env.cr.dictfetchone()
        result['pending_payments_count'] = result['customer_count'] + result['supplier_count']
        return result

    def _get_advances_data(self):
        """Calcula anticipos sin aplicar por tipo"""
        company = self.env.company

        # Usar ORM en lugar de SQL para campos compute
        Payment = self.env['account.payment']

        # Anticipos de clientes (inbound)
        customer_advances = Payment.search([
            ('company_id', '=', company.id),
            ('is_advance', '=', True),
            ('state', 'in', ['posted', 'paid']),
            ('payment_type', '=', 'inbound'),
        ])

        # Anticipos a proveedores (outbound)
        supplier_advances = Payment.search([
            ('company_id', '=', company.id),
            ('is_advance', '=', True),
            ('state', 'in', ['posted', 'paid']),
            ('payment_type', '=', 'outbound'),
        ])

        return {
            'customer_count': len(customer_advances),
            'supplier_count': len(supplier_advances),
            'employee_count': 0,  # Por ahora no hay anticipos de empleados
            'unreconciled_advances_customer': sum(customer_advances.mapped('amount')),
            'unreconciled_advances_supplier': sum(supplier_advances.mapped('amount')),
            'unreconciled_advances_employee': 0,
        }

    def _get_advance_requests_data(self):
        """Calcula solicitudes de anticipo pendientes"""
        company = self.env.company

        query = """
            SELECT
                COUNT(ar.id) as pending_count,
                COALESCE(SUM(ar.amount_requested), 0) as pending_amount
            FROM advance_request ar
            INNER JOIN advance_request_stage ars ON ar.stage_id = ars.id
            WHERE ars.is_done = false
                AND ar.company_id = %s
        """
        self.env.cr.execute(query, (company.id,))
        return self.env.cr.dictfetchone()

    def _get_payments_by_state(self):
        """Pagos agrupados por estado (últimos 30 días)"""
        company = self.env.company
        date_from = fields.Date.today() - timedelta(days=30)

        query = """
            SELECT
                state,
                COUNT(*) as count,
                SUM(amount) as total
            FROM account_payment
            WHERE date >= %s
                AND company_id = %s
            GROUP BY state
            ORDER BY count DESC
        """
        self.env.cr.execute(query, (date_from, company.id))
        results = self.env.cr.dictfetchall()

        state_labels = {
            'draft': 'Borrador',
            'posted': 'Publicado',
            'sent': 'Enviado',
            'reconciled': 'Conciliado',
            'cancel': 'Cancelado'
        }

        for result in results:
            result['label'] = state_labels.get(result['state'], result['state'])

        return results

    def _get_monthly_trend(self):
        """Tendencia mensual de ingresos y egresos (últimos 6 meses)"""
        company = self.env.company
        data = []

        for i in range(5, -1, -1):
            month_date = datetime.now() - relativedelta(months=i)
            first_day = month_date.replace(day=1).date()
            last_day = (month_date.replace(day=1) + relativedelta(months=1) - timedelta(days=1)).date()

            query = """
                SELECT
                    COALESCE(SUM(CASE WHEN payment_type = 'inbound' THEN amount ELSE 0 END), 0) as income,
                    COALESCE(SUM(CASE WHEN payment_type = 'outbound' THEN amount ELSE 0 END), 0) as expenses
                FROM account_payment
                WHERE date >= %s
                    AND date <= %s
                    AND state IN ('posted', 'paid')
                    AND company_id = %s
            """
            self.env.cr.execute(query, (first_day, last_day, company.id))
            result = self.env.cr.dictfetchone()

            data.append({
                'month': month_date.strftime('%b %Y'),
                'income': result['income'],
                'expenses': result['expenses'],
                'balance': result['income'] - result['expenses']
            })

        return data

    def _get_top_customers(self):
        """Top 10 clientes que más pagan (últimos 90 días)"""
        company = self.env.company
        date_from = fields.Date.today() - timedelta(days=90)

        query = """
            SELECT
                rp.id as partner_id,
                rp.name as partner_name,
                COUNT(*) as payment_count,
                SUM(ap.amount) as total_amount
            FROM account_payment ap
            INNER JOIN res_partner rp ON ap.partner_id = rp.id
            WHERE ap.payment_type = 'inbound'
                AND ap.partner_type = 'customer'
                AND ap.state IN ('posted', 'paid')
                AND ap.date >= %s
                AND ap.company_id = %s
            GROUP BY rp.id, rp.name
            ORDER BY total_amount DESC
            LIMIT 10
        """
        self.env.cr.execute(query, (date_from, company.id))
        return self.env.cr.dictfetchall()

    def _get_top_suppliers(self):
        """Top 10 proveedores a los que más se paga (últimos 90 días)"""
        company = self.env.company
        date_from = fields.Date.today() - timedelta(days=90)

        query = """
            SELECT
                rp.id as partner_id,
                rp.name as partner_name,
                COUNT(*) as payment_count,
                SUM(ap.amount) as total_amount
            FROM account_payment ap
            INNER JOIN res_partner rp ON ap.partner_id = rp.id
            WHERE ap.payment_type = 'outbound'
                AND ap.partner_type = 'supplier'
                AND ap.state IN ('posted', 'paid')
                AND ap.date >= %s
                AND ap.company_id = %s
            GROUP BY rp.id, rp.name
            ORDER BY total_amount DESC
            LIMIT 10
        """
        self.env.cr.execute(query, (date_from, company.id))
        return self.env.cr.dictfetchall()

    def _get_bank_list(self):
        """Lista de bancos con saldo y movimientos del periodo (optimizado)"""
        company = self.env.company
        date_from = self.env.context.get('date_from', fields.Date.today().replace(day=1))
        date_to = self.env.context.get('date_to', fields.Date.today())

        # Una sola query para obtener saldos y movimientos de todos los bancos
        query = """
            WITH journal_balances AS (
                SELECT
                    j.id as journal_id,
                    COALESCE(j.name->>'es_CO', j.name->>'en_US', j.name::text) as journal_name,
                    COALESCE(SUM(aml.balance), 0) as balance
                FROM account_journal j
                LEFT JOIN account_account aa ON j.default_account_id = aa.id
                LEFT JOIN account_move_line aml ON aml.account_id = aa.id
                    AND aml.parent_state = 'posted'
                    AND aml.company_id = %(company_id)s
                WHERE j.type = 'bank'
                    AND j.company_id = %(company_id)s
                    AND j.active = TRUE
                GROUP BY j.id, j.name
            ),
            journal_movements AS (
                SELECT
                    ap.journal_id,
                    COALESCE(SUM(CASE WHEN ap.payment_type = 'inbound' THEN ap.amount ELSE 0 END), 0) as inbound,
                    COALESCE(SUM(CASE WHEN ap.payment_type = 'outbound' THEN ap.amount ELSE 0 END), 0) as outbound
                FROM account_payment ap
                WHERE ap.state IN ('posted', 'paid')
                    AND ap.date >= %(date_from)s
                    AND ap.date <= %(date_to)s
                    AND ap.company_id = %(company_id)s
                GROUP BY ap.journal_id
            )
            SELECT
                jb.journal_id,
                jb.journal_name as name,
                jb.balance,
                COALESCE(jm.inbound, 0) as inbound,
                COALESCE(jm.outbound, 0) as outbound
            FROM journal_balances jb
            LEFT JOIN journal_movements jm ON jb.journal_id = jm.journal_id
            ORDER BY jb.journal_name
        """
        self.env.cr.execute(query, {
            'company_id': company.id,
            'date_from': date_from,
            'date_to': date_to
        })
        return self.env.cr.dictfetchall()

    def _get_cash_list(self):
        """Lista de cajas con saldo y movimientos del periodo (optimizado)"""
        company = self.env.company
        date_from = self.env.context.get('date_from', fields.Date.today().replace(day=1))
        date_to = self.env.context.get('date_to', fields.Date.today())

        # Una sola query para obtener saldos y movimientos de todas las cajas
        query = """
            WITH journal_balances AS (
                SELECT
                    j.id as journal_id,
                    COALESCE(j.name->>'es_CO', j.name->>'en_US', j.name::text) as journal_name,
                    COALESCE(SUM(aml.balance), 0) as balance
                FROM account_journal j
                LEFT JOIN account_account aa ON j.default_account_id = aa.id
                LEFT JOIN account_move_line aml ON aml.account_id = aa.id
                    AND aml.parent_state = 'posted'
                    AND aml.company_id = %(company_id)s
                WHERE j.type = 'cash'
                    AND j.company_id = %(company_id)s
                    AND j.active = TRUE
                GROUP BY j.id, j.name
            ),
            journal_movements AS (
                SELECT
                    ap.journal_id,
                    COALESCE(SUM(CASE WHEN ap.payment_type = 'inbound' THEN ap.amount ELSE 0 END), 0) as inbound,
                    COALESCE(SUM(CASE WHEN ap.payment_type = 'outbound' THEN ap.amount ELSE 0 END), 0) as outbound
                FROM account_payment ap
                WHERE ap.state IN ('posted', 'paid')
                    AND ap.date >= %(date_from)s
                    AND ap.date <= %(date_to)s
                    AND ap.company_id = %(company_id)s
                GROUP BY ap.journal_id
            )
            SELECT
                jb.journal_id,
                jb.journal_name as name,
                jb.balance,
                COALESCE(jm.inbound, 0) as inbound,
                COALESCE(jm.outbound, 0) as outbound
            FROM journal_balances jb
            LEFT JOIN journal_movements jm ON jb.journal_id = jm.journal_id
            ORDER BY jb.journal_name
        """
        self.env.cr.execute(query, {
            'company_id': company.id,
            'date_from': date_from,
            'date_to': date_to
        })
        return self.env.cr.dictfetchall()

    def _get_recent_payments(self):
        """Pagos realizados del periodo seleccionado"""
        company = self.env.company
        date_from = self.env.context.get('date_from', fields.Date.today() - timedelta(days=30))
        date_to = self.env.context.get('date_to', fields.Date.today())

        query = """
            SELECT
                p.id,
                p.name,
                p.date,
                p.amount,
                p.payment_type,
                p.state,
                rp.name as partner_name,
                COALESCE(j.name->>'es_CO', j.name->>'en_US', j.name::text) as journal_name
            FROM account_payment p
            LEFT JOIN res_partner rp ON p.partner_id = rp.id
            LEFT JOIN account_journal j ON p.journal_id = j.id
            WHERE p.payment_type = 'outbound'
                AND p.state IN ('posted', 'paid')
                AND p.date >= %s
                AND p.date <= %s
                AND p.company_id = %s
            ORDER BY p.date DESC, p.id DESC
            LIMIT 20
        """
        self.env.cr.execute(query, (date_from, date_to, company.id))
        return self.env.cr.dictfetchall()

    def _get_recent_receipts(self):
        """Cobros realizados del periodo seleccionado"""
        company = self.env.company
        date_from = self.env.context.get('date_from', fields.Date.today() - timedelta(days=30))
        date_to = self.env.context.get('date_to', fields.Date.today())

        query = """
            SELECT
                p.id,
                p.name,
                p.date,
                p.amount,
                p.payment_type,
                p.state,
                rp.name as partner_name,
                COALESCE(j.name->>'es_CO', j.name->>'en_US', j.name::text) as journal_name
            FROM account_payment p
            LEFT JOIN res_partner rp ON p.partner_id = rp.id
            LEFT JOIN account_journal j ON p.journal_id = j.id
            WHERE p.payment_type = 'inbound'
                AND p.state IN ('posted', 'paid')
                AND p.date >= %s
                AND p.date <= %s
                AND p.company_id = %s
            ORDER BY p.date DESC, p.id DESC
            LIMIT 20
        """
        self.env.cr.execute(query, (date_from, date_to, company.id))
        return self.env.cr.dictfetchall()

    @api.model
    def get_cash_flow_projection_filtered(self, date_from=None, date_to=None, journal_id=None):
        """Proyección de flujo filtrada por diario específico"""
        return self._get_cash_flow_projection(
            period_type='weekly',
            num_periods=5,
            journal_id=journal_id
        )

    def _get_journal_balance(self, journal_id):
        """Obtiene el saldo actual de un diario específico"""
        company = self.env.company
        query = """
            SELECT COALESCE(SUM(aml.balance), 0) as balance
            FROM account_journal j
            LEFT JOIN account_account aa ON j.default_account_id = aa.id
            LEFT JOIN account_move_line aml ON aml.account_id = aa.id
                AND aml.parent_state = 'posted'
                AND aml.company_id = %s
            WHERE j.id = %s
        """
        self.env.cr.execute(query, (company.id, journal_id))
        result = self.env.cr.dictfetchone()
        return result['balance'] if result else 0

    def _get_yearly_cash_flow(self):
        """Obtiene el flujo de caja mensual del año actual"""
        company = self.env.company
        today = fields.Date.today()
        year_start = today.replace(month=1, day=1)

        months_data = []
        month_names = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
                       'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']

        for month in range(1, 13):
            month_start = year_start.replace(month=month)
            if month == 12:
                month_end = year_start.replace(year=year_start.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                month_end = year_start.replace(month=month + 1, day=1) - timedelta(days=1)

            # Ingresos del mes (pagos recibidos)
            query_inbound = """
                SELECT COALESCE(SUM(p.amount), 0) as total
                FROM account_payment p
                JOIN account_move m ON p.move_id = m.id
                WHERE p.payment_type = 'inbound'
                AND m.state = 'posted'
                AND p.date >= %s AND p.date <= %s
                AND p.company_id = %s
            """
            self.env.cr.execute(query_inbound, (month_start, month_end, company.id))
            inbound = self.env.cr.dictfetchone()['total'] or 0

            # Egresos del mes (pagos realizados)
            query_outbound = """
                SELECT COALESCE(SUM(p.amount), 0) as total
                FROM account_payment p
                JOIN account_move m ON p.move_id = m.id
                WHERE p.payment_type = 'outbound'
                AND m.state = 'posted'
                AND p.date >= %s AND p.date <= %s
                AND p.company_id = %s
            """
            self.env.cr.execute(query_outbound, (month_start, month_end, company.id))
            outbound = self.env.cr.dictfetchone()['total'] or 0

            net_flow = inbound - outbound
            is_future = month > today.month

            months_data.append({
                'month': month,
                'month_name': month_names[month - 1],
                'inbound': inbound,
                'outbound': outbound,
                'net_flow': net_flow,
                'is_current': month == today.month,
                'is_future': is_future
            })

        # Calcular totales
        total_inbound = sum(m['inbound'] for m in months_data if not m['is_future'])
        total_outbound = sum(m['outbound'] for m in months_data if not m['is_future'])
        total_net = total_inbound - total_outbound

        return {
            'months': months_data,
            'year': today.year,
            'total_inbound': total_inbound,
            'total_outbound': total_outbound,
            'total_net': total_net
        }

    def _get_cash_flow_projection(self, period_type='weekly', num_periods=5, journal_id=None):
        """Proyección de flujo de efectivo con periodos configurables y gastos bancarios

        Args:
            period_type: 'weekly', 'biweekly', 'monthly', 'quarterly', 'semester', 'yearly'
            num_periods: Número de periodos a proyectar
        """
        company = self.env.company
        today = fields.Date.today()

        # Obtener liquidez actual (filtrada por diario si aplica)
        if journal_id:
            journal = self.env['account.journal'].browse(journal_id)
            current_balance = self._get_journal_balance(journal_id)
            journal_name = journal.name if journal else 'Diario'
        else:
            liquidity = self._get_liquidity_data()
            current_balance = liquidity.get('total_liquidity', 0)
            journal_name = 'Todos'

        # Obtener tendencias de pago para ajustar proyecciones
        trends = self._get_partner_payment_trends()
        customer_delay = int(trends.get('customer_avg_days', 0))

        projection_data = []

        # Configuración de periodos
        period_config = {
            'weekly': {'days': 7, 'label': 'Sem'},
            'biweekly': {'days': 14, 'label': 'Qna'},
            'monthly': {'days': 30, 'label': 'Mes'},
            'quarterly': {'days': 90, 'label': 'Trim'},
            'semester': {'days': 180, 'label': 'Sem'},
            'yearly': {'days': 365, 'label': 'Año'}
        }
        config = period_config.get(period_type, period_config['weekly'])

        for period in range(num_periods):
            period_start = today + timedelta(days=period * config['days'])
            period_end = period_start + timedelta(days=config['days'] - 1)

            # Cobros esperados ajustados por tendencia de pago
            adjusted_start = period_start - timedelta(days=customer_delay)
            adjusted_end = period_end - timedelta(days=customer_delay)

            query_inbound = """
                SELECT COALESCE(SUM(amount_residual), 0) as expected_inbound
                FROM account_move
                WHERE move_type = 'out_invoice'
                    AND state = 'posted'
                    AND payment_state IN ('not_paid', 'partial')
                    AND invoice_date_due >= %s
                    AND invoice_date_due <= %s
                    AND company_id = %s
            """
            self.env.cr.execute(query_inbound, (adjusted_start, adjusted_end, company.id))
            inbound_result = self.env.cr.dictfetchone()

            # Pagos esperados
            query_outbound = """
                SELECT COALESCE(SUM(amount_residual), 0) as expected_outbound
                FROM account_move
                WHERE move_type = 'in_invoice'
                    AND state = 'posted'
                    AND payment_state IN ('not_paid', 'partial')
                    AND invoice_date_due >= %s
                    AND invoice_date_due <= %s
                    AND company_id = %s
            """
            self.env.cr.execute(query_outbound, (period_start, period_end, company.id))
            outbound_result = self.env.cr.dictfetchone()

            expected_inbound = inbound_result['expected_inbound'] or 0
            expected_outbound = outbound_result['expected_outbound'] or 0

            # Calcular gastos bancarios proyectados
            bank_expenses = self._calculate_projected_bank_expenses(
                period_start, period_end, expected_outbound, journal_id
            )

            net_flow = expected_inbound - expected_outbound - bank_expenses['total']
            current_balance += net_flow

            projection_data.append({
                'period': f'{config["label"]} {period + 1}',
                'period_start': period_start.strftime('%d/%m'),
                'period_end': period_end.strftime('%d/%m'),
                'expected_inbound': expected_inbound,
                'expected_outbound': expected_outbound,
                'bank_expenses': bank_expenses['total'],
                'bank_expenses_detail': bank_expenses['detail'],
                'net_flow': net_flow,
                'projected_balance': current_balance
            })

        return projection_data

    def _calculate_projected_bank_expenses(self, date_from, date_to, payment_amount, journal_id=None):
        """Calcula gastos bancarios proyectados basado en configuración de comisiones"""
        company = self.env.company
        Commission = self.env['treasury.bank.commission']
        Schedule = self.env['treasury.payment.schedule']

        total_expenses = 0.0
        detail = []

        # Obtener calendarios de pago activos
        domain = [
            ('company_id', '=', company.id),
            ('active', '=', True)
        ]
        if journal_id:
            domain.append(('journal_id', '=', journal_id))
        schedules = Schedule.search(domain)

        for schedule in schedules:
            # Obtener días de pago en el rango
            payment_days = schedule.get_payment_days_in_range(date_from, date_to)
            num_payment_days = len(payment_days)

            if num_payment_days == 0:
                continue

            # Buscar comisión asociada al banco/método del calendario
            if schedule.journal_id and schedule.payment_method_id:
                commission = Commission.search([
                    ('journal_id', '=', schedule.journal_id.id),
                    ('payment_method_id', '=', schedule.payment_method_id.id),
                    ('payment_type', '=', 'outbound'),
                    ('company_id', '=', company.id),
                    ('active', '=', True)
                ], limit=1)

                if commission:
                    # Estimar monto por día de pago
                    estimated_amount_per_day = payment_amount / max(num_payment_days, 1)

                    # Calcular comisión por cada día de pago
                    for _ in range(num_payment_days):
                        calc = commission.calculate_commission(estimated_amount_per_day)
                        total_expenses += calc['total']

                    detail.append({
                        'schedule': schedule.name,
                        'payment_days': num_payment_days,
                        'commission_name': commission.name,
                        'amount': total_expenses
                    })

        return {
            'total': total_expenses,
            'detail': detail
        }

    def _get_payment_aging(self):
        """Análisis de antigüedad de cuentas por cobrar y pagar"""
        company = self.env.company
        today = fields.Date.today()

        # Rangos de antigüedad
        ranges = [
            ('current', 'Al día', 0, 0),
            ('1_30', '1-30 días', 1, 30),
            ('31_60', '31-60 días', 31, 60),
            ('61_90', '61-90 días', 61, 90),
            ('over_90', '+90 días', 91, 9999),
        ]

        aging_receivable = []
        aging_payable = []

        for range_code, range_label, min_days, max_days in ranges:
            if range_code == 'current':
                # Facturas no vencidas
                query_recv = """
                    SELECT COUNT(*) as count, COALESCE(SUM(amount_residual), 0) as amount
                    FROM account_move
                    WHERE move_type = 'out_invoice'
                        AND state = 'posted'
                        AND payment_state IN ('not_paid', 'partial')
                        AND invoice_date_due >= %s
                        AND company_id = %s
                """
                self.env.cr.execute(query_recv, (today, company.id))
                recv = self.env.cr.dictfetchone()

                query_pay = """
                    SELECT COUNT(*) as count, COALESCE(SUM(amount_residual), 0) as amount
                    FROM account_move
                    WHERE move_type = 'in_invoice'
                        AND state = 'posted'
                        AND payment_state IN ('not_paid', 'partial')
                        AND invoice_date_due >= %s
                        AND company_id = %s
                """
                self.env.cr.execute(query_pay, (today, company.id))
                pay = self.env.cr.dictfetchone()
            else:
                date_from = today - timedelta(days=max_days)
                date_to = today - timedelta(days=min_days)

                query_recv = """
                    SELECT COUNT(*) as count, COALESCE(SUM(amount_residual), 0) as amount
                    FROM account_move
                    WHERE move_type = 'out_invoice'
                        AND state = 'posted'
                        AND payment_state IN ('not_paid', 'partial')
                        AND invoice_date_due >= %s
                        AND invoice_date_due < %s
                        AND company_id = %s
                """
                self.env.cr.execute(query_recv, (date_from, date_to, company.id))
                recv = self.env.cr.dictfetchone()

                query_pay = """
                    SELECT COUNT(*) as count, COALESCE(SUM(amount_residual), 0) as amount
                    FROM account_move
                    WHERE move_type = 'in_invoice'
                        AND state = 'posted'
                        AND payment_state IN ('not_paid', 'partial')
                        AND invoice_date_due >= %s
                        AND invoice_date_due < %s
                        AND company_id = %s
                """
                self.env.cr.execute(query_pay, (date_from, date_to, company.id))
                pay = self.env.cr.dictfetchone()

            aging_receivable.append({
                'range': range_label,
                'count': recv['count'] or 0,
                'amount': recv['amount'] or 0
            })

            aging_payable.append({
                'range': range_label,
                'count': pay['count'] or 0,
                'amount': pay['amount'] or 0
            })

        return {
            'receivable': aging_receivable,
            'payable': aging_payable
        }

    def _get_orders_forecast(self):
        """Pronóstico basado en órdenes de compra y venta pendientes"""
        company = self.env.company

        # Órdenes de venta confirmadas sin facturar
        SaleOrder = self.env['sale.order']
        sale_orders = SaleOrder.search([
            ('state', 'in', ['sale', 'done']),
            ('invoice_status', '!=', 'invoiced'),
            ('company_id', '=', company.id)
        ])
        sale_total = sum(sale_orders.mapped('amount_total'))
        # sale.order SÍ tiene amount_invoiced
        sale_pending = sum(so.amount_total - so.amount_invoiced for so in sale_orders)

        # Órdenes de compra confirmadas sin facturar
        PurchaseOrder = self.env['purchase.order']
        purchase_orders = PurchaseOrder.search([
            ('state', 'in', ['purchase', 'done']),
            ('invoice_status', '!=', 'invoiced'),
            ('company_id', '=', company.id)
        ])
        purchase_total = sum(purchase_orders.mapped('amount_total'))
        # purchase.order NO tiene amount_invoiced, calcular desde facturas
        purchase_invoiced = 0
        for po in purchase_orders:
            if po.invoice_ids:
                purchase_invoiced += sum(po.invoice_ids.filtered(
                    lambda inv: inv.state == 'posted'
                ).mapped('amount_total'))
        purchase_pending = purchase_total - purchase_invoiced

        return {
            'sales': {
                'count': len(sale_orders),
                'total': sale_total,
                'pending_to_invoice': sale_pending
            },
            'purchases': {
                'count': len(purchase_orders),
                'total': purchase_total,
                'pending_to_invoice': purchase_pending
            }
        }

    def _get_partner_payment_trends(self):
        """Tendencias de pago de clientes y proveedores - días promedio (optimizado con SQL)"""
        company = self.env.company
        date_from = fields.Date.today() - timedelta(days=180)

        # Query optimizada para calcular días promedio de cobro a clientes
        customer_query = """
            SELECT AVG(ap.date - am.invoice_date) as avg_days
            FROM account_payment ap
            JOIN account_move_line aml_pay ON aml_pay.payment_id = ap.id
            JOIN account_partial_reconcile apr ON apr.credit_move_id = aml_pay.id OR apr.debit_move_id = aml_pay.id
            JOIN account_move_line aml_inv ON (apr.credit_move_id = aml_inv.id OR apr.debit_move_id = aml_inv.id) AND aml_inv.id != aml_pay.id
            JOIN account_move am ON aml_inv.move_id = am.id
            WHERE ap.payment_type = 'inbound'
                AND ap.state IN ('posted', 'paid')
                AND ap.date >= %s
                AND ap.company_id = %s
                AND am.invoice_date IS NOT NULL
                AND am.move_type IN ('out_invoice', 'out_receipt')
                AND (ap.date - am.invoice_date) >= 0
        """
        self.env.cr.execute(customer_query, (date_from, company.id))
        customer_result = self.env.cr.fetchone()
        customer_avg = float(customer_result[0]) if customer_result and customer_result[0] else 0

        # Query optimizada para calcular días promedio de pago a proveedores
        supplier_query = """
            SELECT AVG(ap.date - am.invoice_date) as avg_days
            FROM account_payment ap
            JOIN account_move_line aml_pay ON aml_pay.payment_id = ap.id
            JOIN account_partial_reconcile apr ON apr.credit_move_id = aml_pay.id OR apr.debit_move_id = aml_pay.id
            JOIN account_move_line aml_inv ON (apr.credit_move_id = aml_inv.id OR apr.debit_move_id = aml_inv.id) AND aml_inv.id != aml_pay.id
            JOIN account_move am ON aml_inv.move_id = am.id
            WHERE ap.payment_type = 'outbound'
                AND ap.state IN ('posted', 'paid')
                AND ap.date >= %s
                AND ap.company_id = %s
                AND am.invoice_date IS NOT NULL
                AND am.move_type IN ('in_invoice', 'in_receipt')
                AND (ap.date - am.invoice_date) >= 0
        """
        self.env.cr.execute(supplier_query, (date_from, company.id))
        supplier_result = self.env.cr.fetchone()
        supplier_avg = float(supplier_result[0]) if supplier_result and supplier_result[0] else 0

        return {
            'customer_avg_days': round(customer_avg, 1),
            'supplier_avg_days': round(supplier_avg, 1)
        }

    def _get_upcoming_due(self):
        """Obtiene facturas por pagar y por cobrar en diferentes rangos de vencimiento"""
        company = self.env.company
        today = fields.Date.today()

        # Rangos de fecha
        ranges = {
            'overdue': {'start': None, 'end': today - timedelta(days=1)},  # Vencidas
            'today': {'start': today, 'end': today},  # Vencen hoy
            'week': {'start': today + timedelta(days=1), 'end': today + timedelta(days=7)},  # Próximos 7 días
            'month': {'start': today + timedelta(days=8), 'end': today + timedelta(days=30)},  # 8-30 días
            'quarter': {'start': today + timedelta(days=31), 'end': today + timedelta(days=90)},  # 31-90 días
        }

        result = {
            'receivable': {},
            'payable': {}
        }

        for range_key, dates in ranges.items():
            # Por Cobrar
            if dates['start'] is None:
                # Vencidas (fecha < hoy)
                query_recv = """
                    SELECT COUNT(*) as count, COALESCE(SUM(amount_residual), 0) as amount
                    FROM account_move
                    WHERE move_type IN ('out_invoice', 'out_refund')
                        AND state = 'posted'
                        AND payment_state IN ('not_paid', 'partial')
                        AND invoice_date_due < %s
                        AND company_id = %s
                """
                self.env.cr.execute(query_recv, (today, company.id))
            else:
                query_recv = """
                    SELECT COUNT(*) as count, COALESCE(SUM(amount_residual), 0) as amount
                    FROM account_move
                    WHERE move_type IN ('out_invoice', 'out_refund')
                        AND state = 'posted'
                        AND payment_state IN ('not_paid', 'partial')
                        AND invoice_date_due >= %s
                        AND invoice_date_due <= %s
                        AND company_id = %s
                """
                self.env.cr.execute(query_recv, (dates['start'], dates['end'], company.id))
            recv = self.env.cr.dictfetchone()
            result['receivable'][range_key] = {
                'count': recv['count'] or 0,
                'amount': recv['amount'] or 0
            }

            # Por Pagar
            if dates['start'] is None:
                query_pay = """
                    SELECT COUNT(*) as count, COALESCE(SUM(amount_residual), 0) as amount
                    FROM account_move
                    WHERE move_type IN ('in_invoice', 'in_refund')
                        AND state = 'posted'
                        AND payment_state IN ('not_paid', 'partial')
                        AND invoice_date_due < %s
                        AND company_id = %s
                """
                self.env.cr.execute(query_pay, (today, company.id))
            else:
                query_pay = """
                    SELECT COUNT(*) as count, COALESCE(SUM(amount_residual), 0) as amount
                    FROM account_move
                    WHERE move_type IN ('in_invoice', 'in_refund')
                        AND state = 'posted'
                        AND payment_state IN ('not_paid', 'partial')
                        AND invoice_date_due >= %s
                        AND invoice_date_due <= %s
                        AND company_id = %s
                """
                self.env.cr.execute(query_pay, (dates['start'], dates['end'], company.id))
            pay = self.env.cr.dictfetchone()
            result['payable'][range_key] = {
                'count': pay['count'] or 0,
                'amount': pay['amount'] or 0
            }

        # Totales
        result['receivable']['total'] = {
            'count': sum(v['count'] for v in result['receivable'].values()),
            'amount': sum(v['amount'] for v in result['receivable'].values())
        }
        result['payable']['total'] = {
            'count': sum(v['count'] for v in result['payable'].values()),
            'amount': sum(v['amount'] for v in result['payable'].values())
        }

        return result

    def _get_cash_flow_forecast(self):
        """Proyeccion de flujo de caja basada en tendencias historicas de pago"""
        company = self.env.company
        today = fields.Date.today()

        # Obtener datos historicos de los ultimos 6 meses para calcular tendencias
        six_months_ago = today - timedelta(days=180)

        # Promedio mensual de ingresos (pagos recibidos)
        query_avg_inbound = """
            SELECT
                AVG(monthly_total) as avg_monthly,
                STDDEV(monthly_total) as stddev_monthly,
                MIN(monthly_total) as min_monthly,
                MAX(monthly_total) as max_monthly
            FROM (
                SELECT
                    DATE_TRUNC('month', p.date) as mes,
                    SUM(p.amount) as monthly_total
                FROM account_payment p
                JOIN account_move m ON p.move_id = m.id
                WHERE p.payment_type = 'inbound'
                AND m.state = 'posted'
                AND p.date >= %s AND p.date <= %s
                AND p.company_id = %s
                GROUP BY DATE_TRUNC('month', p.date)
            ) as monthly_data
        """
        self.env.cr.execute(query_avg_inbound, (six_months_ago, today, company.id))
        inbound_stats = self.env.cr.dictfetchone()

        # Promedio mensual de egresos (pagos realizados)
        query_avg_outbound = """
            SELECT
                AVG(monthly_total) as avg_monthly,
                STDDEV(monthly_total) as stddev_monthly,
                MIN(monthly_total) as min_monthly,
                MAX(monthly_total) as max_monthly
            FROM (
                SELECT
                    DATE_TRUNC('month', p.date) as mes,
                    SUM(p.amount) as monthly_total
                FROM account_payment p
                JOIN account_move m ON p.move_id = m.id
                WHERE p.payment_type = 'outbound'
                AND m.state = 'posted'
                AND p.date >= %s AND p.date <= %s
                AND p.company_id = %s
                GROUP BY DATE_TRUNC('month', p.date)
            ) as monthly_data
        """
        self.env.cr.execute(query_avg_outbound, (six_months_ago, today, company.id))
        outbound_stats = self.env.cr.dictfetchone()

        # Tendencia de crecimiento (comparar ultimos 3 meses vs 3 meses anteriores)
        three_months_ago = today - timedelta(days=90)

        query_trend_inbound = """
            SELECT
                COALESCE(SUM(CASE WHEN p.date >= %s THEN p.amount ELSE 0 END), 0) as recent,
                COALESCE(SUM(CASE WHEN p.date < %s AND p.date >= %s THEN p.amount ELSE 0 END), 0) as previous
            FROM account_payment p
            JOIN account_move m ON p.move_id = m.id
            WHERE p.payment_type = 'inbound'
            AND m.state = 'posted'
            AND p.date >= %s
            AND p.company_id = %s
        """
        self.env.cr.execute(query_trend_inbound, (three_months_ago, three_months_ago, six_months_ago, six_months_ago, company.id))
        inbound_trend = self.env.cr.dictfetchone()

        query_trend_outbound = """
            SELECT
                COALESCE(SUM(CASE WHEN p.date >= %s THEN p.amount ELSE 0 END), 0) as recent,
                COALESCE(SUM(CASE WHEN p.date < %s AND p.date >= %s THEN p.amount ELSE 0 END), 0) as previous
            FROM account_payment p
            JOIN account_move m ON p.move_id = m.id
            WHERE p.payment_type = 'outbound'
            AND m.state = 'posted'
            AND p.date >= %s
            AND p.company_id = %s
        """
        self.env.cr.execute(query_trend_outbound, (three_months_ago, three_months_ago, six_months_ago, six_months_ago, company.id))
        outbound_trend = self.env.cr.dictfetchone()

        # Calcular tasa de crecimiento (con validacion)
        inbound_growth = 0.0
        if inbound_trend and inbound_trend.get('previous') and float(inbound_trend['previous']) > 0:
            recent = float(inbound_trend['recent'] or 0)
            previous = float(inbound_trend['previous'])
            inbound_growth = ((recent - previous) / previous) * 100
            # Limitar crecimiento a rango razonable (-50% a +100%)
            inbound_growth = max(-50, min(100, inbound_growth))

        outbound_growth = 0.0
        if outbound_trend and outbound_trend.get('previous') and float(outbound_trend['previous']) > 0:
            recent = float(outbound_trend['recent'] or 0)
            previous = float(outbound_trend['previous'])
            outbound_growth = ((recent - previous) / previous) * 100
            # Limitar crecimiento a rango razonable (-50% a +100%)
            outbound_growth = max(-50, min(100, outbound_growth))

        # Proyectar proximos 6 meses
        avg_inbound = float(inbound_stats.get('avg_monthly') or 0) if inbound_stats else 0
        avg_outbound = float(outbound_stats.get('avg_monthly') or 0) if outbound_stats else 0

        # Aplicar factor de crecimiento mensual (asegurar valor positivo)
        growth_factor_in = 1 + (inbound_growth / 100)
        growth_factor_out = 1 + (outbound_growth / 100)
        monthly_inbound_growth = abs(growth_factor_in) ** (1/3) if growth_factor_in > 0 else 1.0
        monthly_outbound_growth = abs(growth_factor_out) ** (1/3) if growth_factor_out > 0 else 1.0

        forecast_months = []
        month_names = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
                       'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']

        # Obtener liquidez actual
        liquidity = self._get_liquidity_data()
        running_balance = liquidity.get('total_liquidity', 0)

        for i in range(1, 7):
            future_date = today + relativedelta(months=i)
            month_idx = future_date.month - 1

            # Proyeccion con tendencia (validar valores)
            try:
                projected_inbound = avg_inbound * (monthly_inbound_growth ** i)
                projected_outbound = avg_outbound * (monthly_outbound_growth ** i)

                # Validar que no sean NaN o infinitos
                if math.isnan(projected_inbound) or math.isinf(projected_inbound):
                    projected_inbound = avg_inbound
                if math.isnan(projected_outbound) or math.isinf(projected_outbound):
                    projected_outbound = avg_outbound

                projected_net = projected_inbound - projected_outbound
                running_balance += projected_net

                if math.isnan(running_balance) or math.isinf(running_balance):
                    running_balance = liquidity.get('total_liquidity', 0)
            except (ValueError, OverflowError):
                projected_inbound = avg_inbound
                projected_outbound = avg_outbound
                projected_net = projected_inbound - projected_outbound
                running_balance = liquidity.get('total_liquidity', 0)

            forecast_months.append({
                'month': future_date.month,
                'year': future_date.year,
                'month_name': month_names[month_idx],
                'label': f"{month_names[month_idx]} {future_date.year}",
                'projected_inbound': round(projected_inbound, 2),
                'projected_outbound': round(projected_outbound, 2),
                'projected_net': round(projected_net, 2),
                'projected_balance': round(running_balance, 2),
                'confidence': 'high' if i <= 2 else ('medium' if i <= 4 else 'low')
            })

        return {
            'forecast_months': forecast_months,
            'stats': {
                'avg_monthly_inbound': avg_inbound,
                'avg_monthly_outbound': avg_outbound,
                'inbound_growth_pct': round(inbound_growth, 1),
                'outbound_growth_pct': round(outbound_growth, 1),
                'inbound_volatility': inbound_stats['stddev_monthly'] or 0,
                'outbound_volatility': outbound_stats['stddev_monthly'] or 0,
            },
            'current_balance': liquidity.get('total_liquidity', 0),
            'analysis_period': {
                'from': str(six_months_ago),
                'to': str(today)
            }
        }

    def _get_bank_expenses_kpi(self):
        """Obtiene KPIs de gastos bancarios basado en comisiones configuradas y movimientos"""
        company = self.env.company
        today = fields.Date.today()
        date_from = self.env.context.get('date_from', today.replace(day=1))
        date_to = self.env.context.get('date_to', today)

        # Mes anterior para comparacion
        first_day_prev_month = (date_from - relativedelta(months=1)).replace(day=1)
        last_day_prev_month = date_from - timedelta(days=1)

        # Comisiones configuradas
        Commission = self.env['treasury.bank.commission']
        commissions = Commission.search([
            ('company_id', '=', company.id),
            ('active', '=', True)
        ])

        # Estadisticas de comisiones configuradas
        total_commissions = len(commissions)
        exempt_commissions = len(commissions.filtered(lambda c: c.is_exempt))
        by_category = {}
        for comm in commissions:
            cat = comm.service_category
            if cat not in by_category:
                by_category[cat] = {'count': 0, 'avg_fixed': 0, 'total_fixed': 0}
            by_category[cat]['count'] += 1
            by_category[cat]['total_fixed'] += comm.commission_fixed or 0
        for cat in by_category:
            if by_category[cat]['count'] > 0:
                by_category[cat]['avg_fixed'] = by_category[cat]['total_fixed'] / by_category[cat]['count']

        # Usar cuenta de gastos bancarios configurada en la compañía
        # Si no está configurada, buscar por código 5305%
        expense_account = company.bank_expense_account_id
        if not expense_account:
            expense_account = self.env['account.account'].search([
                ('code', 'like', '5305%'),
                ('company_ids', 'in', company.id)
            ], limit=1)

        current_expenses = 0
        prev_expenses = 0
        expense_count = 0
        by_journal = []

        if expense_account:
            # Gastos del periodo actual
            query_current = """
                SELECT
                    COALESCE(SUM(aml.debit), 0) as total_debit,
                    COUNT(DISTINCT aml.id) as move_count
                FROM account_move_line aml
                JOIN account_move am ON aml.move_id = am.id
                WHERE aml.account_id = %s
                AND am.state = 'posted'
                AND aml.date >= %s AND aml.date <= %s
                AND aml.company_id = %s
            """
            self.env.cr.execute(query_current, (expense_account.id, date_from, date_to, company.id))
            result = self.env.cr.dictfetchone()
            current_expenses = result['total_debit'] or 0
            expense_count = result['move_count'] or 0

            # Gastos del mes anterior
            self.env.cr.execute(query_current, (expense_account.id, first_day_prev_month, last_day_prev_month, company.id))
            result_prev = self.env.cr.dictfetchone()
            prev_expenses = result_prev['total_debit'] or 0

            # Desglose por diario
            query_by_journal = """
                SELECT
                    COALESCE(j.name->>'es_CO', j.name->>'en_US', j.name::text) as journal_name,
                    j.id as journal_id,
                    COALESCE(SUM(aml.debit), 0) as total
                FROM account_move_line aml
                JOIN account_move am ON aml.move_id = am.id
                JOIN account_journal j ON am.journal_id = j.id
                WHERE aml.account_id = %s
                AND am.state = 'posted'
                AND aml.date >= %s AND aml.date <= %s
                AND aml.company_id = %s
                GROUP BY j.id, j.name
                ORDER BY total DESC
                LIMIT 5
            """
            self.env.cr.execute(query_by_journal, (expense_account.id, date_from, date_to, company.id))
            by_journal = self.env.cr.dictfetchall()

        # Calcular variacion
        variation_pct = 0
        if prev_expenses > 0:
            variation_pct = ((current_expenses - prev_expenses) / prev_expenses) * 100

        # Estimacion de gastos proyectados basado en pagos pendientes
        pending_payments = self._get_pending_payments()
        pending_amount = pending_payments.get('pending_supplier_payments', 0)

        # Estimar comision promedio
        avg_commission = 0
        if commissions:
            fixed_comms = commissions.filtered(lambda c: c.commission_type == 'fixed' and not c.is_exempt)
            if fixed_comms:
                avg_commission = sum(fixed_comms.mapped('commission_fixed')) / len(fixed_comms)

        # Proyectar gastos bancarios para pagos pendientes (asumiendo 1 transaccion por factura)
        supplier_count = pending_payments.get('supplier_count', 0)
        projected_expenses = supplier_count * avg_commission

        # Categorias de servicio con labels
        category_labels = dict(Commission._fields['service_category'].selection)
        category_summary = []
        for cat, data in by_category.items():
            category_summary.append({
                'category': cat,
                'label': category_labels.get(cat, cat),
                'count': data['count'],
                'avg_fixed': data['avg_fixed']
            })
        category_summary.sort(key=lambda x: x['count'], reverse=True)

        return {
            'current_expenses': current_expenses,
            'prev_expenses': prev_expenses,
            'variation_pct': round(variation_pct, 1),
            'expense_count': expense_count,
            'total_commissions_config': total_commissions,
            'exempt_commissions': exempt_commissions,
            'by_journal': by_journal,
            'by_category': category_summary[:5],
            'projected_expenses': projected_expenses,
            'avg_commission': avg_commission,
            'expense_account_code': expense_account.code if expense_account else 'N/A',
            'period': {
                'from': str(date_from),
                'to': str(date_to)
            }
        }
