/** @odoo-module **/

import { Component, onWillStart, onMounted, useState, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export class TreasuryDashboard extends Component {
    static template = "custom_account_treasury.TreasuryDashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        // Calcular fechas por defecto (mes actual)
        const today = new Date();
        const firstDayOfMonth = new Date(today.getFullYear(), today.getMonth(), 1);
        const lastDayOfMonth = new Date(today.getFullYear(), today.getMonth() + 1, 0);

        this.state = useState({
            dashboardData: {
                liquidity: {},
                daily_flow: {},
                pending_payments: {},
                advances: {},
                advance_requests: {},
                payments_by_state: [],
                monthly_trend: [],
                top_customers: [],
                top_suppliers: [],
                user_info: {},
                bank_list: [],
                cash_list: [],
                recent_payments: [],
                recent_receipts: [],
                // Proyecciones
                cash_flow_projection: [],
                payment_aging: { receivable: [], payable: [] },
                orders_forecast: { sales: {}, purchases: {} },
                payment_trends: { customer_avg_days: 0, supplier_avg_days: 0 },
                // Vencimientos por rango
                upcoming_due: {
                    receivable: { overdue: {}, today: {}, week: {}, month: {}, quarter: {}, total: {} },
                    payable: { overdue: {}, today: {}, week: {}, month: {}, quarter: {}, total: {} }
                },
                // Flujo de caja anual
                yearly_cash_flow: { months: [], year: new Date().getFullYear(), total_inbound: 0, total_outbound: 0, total_net: 0 },
                // Prediccion de flujo de caja
                cash_flow_forecast: { forecast_months: [], stats: {}, current_balance: 0 },
                // KPIs de gastos bancarios
                bank_expenses_kpi: {
                    current_expenses: 0, prev_expenses: 0, variation_pct: 0, expense_count: 0,
                    total_commissions_config: 0, exempt_commissions: 0, by_journal: [], by_category: [],
                    projected_expenses: 0, avg_commission: 0, expense_account_code: 'N/A'
                }
            },
            loading: true,
            // Filtros de periodo
            selectedPeriod: 'month',
            dateFrom: this.formatDateForInput(firstDayOfMonth),
            dateTo: this.formatDateForInput(lastDayOfMonth),
            // Filtro de diario para proyección
            projectionJournalId: null,
        });

        this.chartRefs = {
            monthlyTrendChart: useRef("monthlyTrendChart"),
            paymentsStateChart: useRef("paymentsStateChart"),
            topCustomersChart: useRef("topCustomersChart"),
            topSuppliersChart: useRef("topSuppliersChart"),
            // Nuevos gráficos de proyección
            cashFlowProjectionChart: useRef("cashFlowProjectionChart"),
            agingReceivableChart: useRef("agingReceivableChart"),
            agingPayableChart: useRef("agingPayableChart"),
            // Gráfico de movimientos por diario
            journalMovementsChart: useRef("journalMovementsChart"),
            // Flujo de caja anual
            yearlyCashFlowChart: useRef("yearlyCashFlowChart"),
            // Prediccion de flujo de caja
            cashFlowForecastChart: useRef("cashFlowForecastChart"),
        };

        onWillStart(async () => {
            await this.loadDashboardData();
        });

        onMounted(() => {
            this.initializeCharts();
        });
    }

    formatDateForInput(date) {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    }

    calculateDateRange() {
        const today = new Date();
        let dateFrom, dateTo;

        switch (this.state.selectedPeriod) {
            case 'today':
                dateFrom = dateTo = this.formatDateForInput(today);
                break;
            case 'week':
                const startOfWeek = new Date(today);
                startOfWeek.setDate(today.getDate() - today.getDay());
                const endOfWeek = new Date(startOfWeek);
                endOfWeek.setDate(startOfWeek.getDate() + 6);
                dateFrom = this.formatDateForInput(startOfWeek);
                dateTo = this.formatDateForInput(endOfWeek);
                break;
            case 'month':
                dateFrom = this.formatDateForInput(new Date(today.getFullYear(), today.getMonth(), 1));
                dateTo = this.formatDateForInput(new Date(today.getFullYear(), today.getMonth() + 1, 0));
                break;
            case 'quarter':
                const quarter = Math.floor(today.getMonth() / 3);
                dateFrom = this.formatDateForInput(new Date(today.getFullYear(), quarter * 3, 1));
                dateTo = this.formatDateForInput(new Date(today.getFullYear(), quarter * 3 + 3, 0));
                break;
            case 'year':
                dateFrom = this.formatDateForInput(new Date(today.getFullYear(), 0, 1));
                dateTo = this.formatDateForInput(new Date(today.getFullYear(), 11, 31));
                break;
            case 'custom':
                dateFrom = this.state.dateFrom;
                dateTo = this.state.dateTo;
                break;
            default:
                dateFrom = this.formatDateForInput(new Date(today.getFullYear(), today.getMonth(), 1));
                dateTo = this.formatDateForInput(new Date(today.getFullYear(), today.getMonth() + 1, 0));
        }

        return { dateFrom, dateTo };
    }

    onPeriodChange(ev) {
        this.state.selectedPeriod = ev.target.value;
        if (this.state.selectedPeriod !== 'custom') {
            const { dateFrom, dateTo } = this.calculateDateRange();
            this.state.dateFrom = dateFrom;
            this.state.dateTo = dateTo;
            this.refreshDashboard();
        }
    }

    onDateFromChange(ev) {
        this.state.dateFrom = ev.target.value;
        this.refreshDashboard();
    }

    onDateToChange(ev) {
        this.state.dateTo = ev.target.value;
        this.refreshDashboard();
    }

    async loadDashboardData() {
        try {
            const { dateFrom, dateTo } = this.calculateDateRange();
            console.log('Loading dashboard data:', dateFrom, 'to', dateTo);

            const data = await this.orm.call(
                "treasury.dashboard",
                "get_dashboard_data",
                [dateFrom, dateTo]
            );
            console.log('Dashboard data received:', data);

            this.state.dashboardData = {
                liquidity: data.liquidity || {},
                daily_flow: data.daily_flow || {},
                pending_payments: data.pending_payments || {},
                advances: data.advances || {},
                advance_requests: data.advance_requests || {},
                payments_by_state: data.payments_by_state || [],
                monthly_trend: data.monthly_trend || [],
                top_customers: data.top_customers || [],
                top_suppliers: data.top_suppliers || [],
                user_info: data.user_info || {},
                bank_list: data.bank_list || [],
                cash_list: data.cash_list || [],
                recent_payments: data.recent_payments || [],
                recent_receipts: data.recent_receipts || [],
                // Proyecciones
                cash_flow_projection: data.cash_flow_projection || [],
                payment_aging: data.payment_aging || { receivable: [], payable: [] },
                orders_forecast: data.orders_forecast || { sales: {}, purchases: {} },
                payment_trends: data.payment_trends || { customer_avg_days: 0, supplier_avg_days: 0 },
                // Vencimientos por rango
                upcoming_due: data.upcoming_due || {
                    receivable: { overdue: {}, today: {}, week: {}, month: {}, quarter: {}, total: {} },
                    payable: { overdue: {}, today: {}, week: {}, month: {}, quarter: {}, total: {} }
                },
                // Flujo de caja anual
                yearly_cash_flow: data.yearly_cash_flow || { months: [], year: new Date().getFullYear(), total_inbound: 0, total_outbound: 0, total_net: 0 },
                // Prediccion de flujo de caja
                cash_flow_forecast: data.cash_flow_forecast || { forecast_months: [], stats: {}, current_balance: 0 },
                // KPIs de gastos bancarios
                bank_expenses_kpi: data.bank_expenses_kpi || {
                    current_expenses: 0, prev_expenses: 0, variation_pct: 0, expense_count: 0,
                    total_commissions_config: 0, exempt_commissions: 0, by_journal: [], by_category: [],
                    projected_expenses: 0, avg_commission: 0, expense_account_code: 'N/A'
                }
            };
            this.state.loading = false;
        } catch (error) {
            this.notification.add(_t("Error al cargar datos del dashboard"), {
                type: "danger"
            });
            console.error("Dashboard loading error:", error);
            this.state.loading = false;
        }
    }

    async refreshDashboard() {
        this.state.loading = true;
        await this.loadDashboardData();
        // Esperar al siguiente tick para que el DOM se actualice
        await new Promise(resolve => setTimeout(resolve, 100));
        this.initializeCharts();
    }

    initializeCharts() {
        if (this.state.loading) {
            console.warn('Charts init skipped - still loading');
            return;
        }
        console.log('Initializing charts with data:', this.state.dashboardData);

        // Destruir gráficos existentes si existen
        Object.keys(this.chartRefs).forEach(key => {
            const ref = this.chartRefs[key];
            if (ref.el && ref.el.chartInstance) {
                ref.el.chartInstance.destroy();
            }
        });

        // Inicializar nuevos gráficos
        this.renderJournalMovementsChart();
        this.renderMonthlyTrendChart();
        this.renderPaymentsStateChart();
        this.renderTopCustomersChart();
        this.renderTopSuppliersChart();
        // Gráficos de proyección
        this.renderCashFlowProjectionChart();
        this.renderAgingReceivableChart();
        this.renderAgingPayableChart();
        // Flujo de caja anual
        this.renderYearlyCashFlowChart();
        // Prediccion de flujo de caja
        this.renderCashFlowForecastChart();
    }

    renderJournalMovementsChart() {
        const container = this.chartRefs.journalMovementsChart.el;
        if (!container) return;

        // Combinar datos de bancos y cajas
        const banks = this.state.dashboardData.bank_list || [];
        const cashes = this.state.dashboardData.cash_list || [];
        const allJournals = [...banks, ...cashes];

        if (!allJournals.length) return;

        const ctx = container.getContext('2d');

        const chartInstance = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: allJournals.map(j => j.name),
                datasets: [
                    {
                        label: 'Saldo',
                        data: allJournals.map(j => j.balance),
                        backgroundColor: allJournals.map(j => j.balance >= 0 ? 'rgba(34, 197, 94, 0.8)' : 'rgba(239, 68, 68, 0.8)'),
                        borderColor: allJournals.map(j => j.balance >= 0 ? 'rgb(34, 197, 94)' : 'rgb(239, 68, 68)'),
                        borderWidth: 1,
                        borderRadius: 4,
                    },
                    {
                        label: 'Entradas',
                        data: allJournals.map(j => j.inbound),
                        backgroundColor: 'rgba(59, 130, 246, 0.7)',
                        borderColor: 'rgb(59, 130, 246)',
                        borderWidth: 1,
                        borderRadius: 4,
                    },
                    {
                        label: 'Salidas',
                        data: allJournals.map(j => -j.outbound),
                        backgroundColor: 'rgba(249, 115, 22, 0.7)',
                        borderColor: 'rgb(249, 115, 22)',
                        borderWidth: 1,
                        borderRadius: 4,
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: false
                    },
                    legend: {
                        position: 'top',
                    },
                    tooltip: {
                        callbacks: {
                            label: (context) => {
                                const value = Math.abs(context.raw);
                                return `${context.dataset.label}: ${this.formatCurrency(value)}`;
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: (value) => this.formatCurrency(Math.abs(value))
                        }
                    },
                    x: {
                        ticks: {
                            maxRotation: 45,
                            minRotation: 0
                        }
                    }
                }
            }
        });

        container.chartInstance = chartInstance;
    }

    renderMonthlyTrendChart() {
        const container = this.chartRefs.monthlyTrendChart.el;
        if (!container) {
            console.warn('Monthly trend chart container not found');
            return;
        }

        const data = this.state.dashboardData.monthly_trend || [];
        if (!data.length) {
            console.warn('No monthly trend data');
            return;
        }

        const ctx = container.getContext('2d');

        try {
            const chartInstance = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: data.map(d => d.month),
                    datasets: [
                        {
                            label: 'Ingresos',
                            data: data.map(d => d.income || 0),
                            backgroundColor: 'rgba(34, 197, 94, 0.7)',
                            borderColor: 'rgb(34, 197, 94)',
                            borderWidth: 1,
                            borderRadius: 4,
                        },
                        {
                            label: 'Egresos',
                            data: data.map(d => d.expenses || 0),
                            backgroundColor: 'rgba(239, 68, 68, 0.7)',
                            borderColor: 'rgb(239, 68, 68)',
                            borderWidth: 1,
                            borderRadius: 4,
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        title: {
                            display: false
                        },
                        legend: {
                            position: 'top'
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                callback: (value) => this.formatCurrency(value)
                            }
                        }
                    }
                }
            });
            container.chartInstance = chartInstance;
        } catch (e) {
            console.error('Error rendering monthly trend chart:', e);
        }
    }

    renderPaymentsStateChart() {
        const container = this.chartRefs.paymentsStateChart.el;
        if (!container || !this.state.dashboardData.payments_by_state.length) return;

        const data = this.state.dashboardData.payments_by_state;
        const ctx = container.getContext('2d');
        const self = this;

        const chartInstance = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: data.map(d => d.label),
                datasets: [{
                    data: data.map(d => d.count),
                    backgroundColor: [
                        'rgba(59, 130, 246, 0.7)',
                        'rgba(34, 197, 94, 0.7)',
                        'rgba(234, 179, 8, 0.7)',
                        'rgba(168, 85, 247, 0.7)',
                        'rgba(107, 114, 128, 0.7)'
                    ],
                    borderColor: [
                        'rgb(59, 130, 246)',
                        'rgb(34, 197, 94)',
                        'rgb(234, 179, 8)',
                        'rgb(168, 85, 247)',
                        'rgb(107, 114, 128)'
                    ],
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: true,
                        text: 'Pagos por Estado (Últimos 30 días) - Click para ver'
                    },
                    legend: {
                        position: 'right'
                    }
                },
                onClick: (event, elements) => {
                    if (elements.length > 0) {
                        const index = elements[0].index;
                        const state = data[index].state;
                        self.openPaymentsByState(state);
                    }
                }
            }
        });

        container.chartInstance = chartInstance;
    }

    renderTopCustomersChart() {
        const container = this.chartRefs.topCustomersChart.el;
        if (!container || !this.state.dashboardData.top_customers.length) return;

        const data = this.state.dashboardData.top_customers;
        const ctx = container.getContext('2d');
        const self = this;

        const chartInstance = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: data.map(d => d.partner_name),
                datasets: [{
                    label: 'Total Pagado',
                    data: data.map(d => d.total_amount),
                    backgroundColor: 'rgba(59, 130, 246, 0.7)',
                    borderColor: 'rgb(59, 130, 246)',
                    borderWidth: 1
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: true,
                        text: 'Top 10 Clientes - Click para ver pagos'
                    },
                    legend: {
                        display: false
                    }
                },
                scales: {
                    x: {
                        beginAtZero: true,
                        ticks: {
                            callback: function(value) {
                                return '$' + value.toLocaleString();
                            }
                        }
                    }
                },
                onClick: (event, elements) => {
                    if (elements.length > 0) {
                        const index = elements[0].index;
                        const partnerId = data[index].partner_id;
                        const partnerName = data[index].partner_name;
                        self.openPartnerPayments(partnerId, partnerName, 'inbound');
                    }
                }
            }
        });

        container.chartInstance = chartInstance;
    }

    formatCurrency(value) {
        const symbol = this.state.dashboardData.user_info.currency_symbol || '$';
        return symbol + ' ' + parseFloat(value || 0).toLocaleString('es-CO', {
            minimumFractionDigits: 0,
            maximumFractionDigits: 0
        });
    }

    formatNumber(value) {
        return parseFloat(value || 0).toLocaleString('es-CO');
    }

    // Acciones de navegación
    openBankJournals() {
        this.action.doAction({
            name: _t('Diarios Bancarios'),
            type: 'ir.actions.act_window',
            res_model: 'account.journal',
            views: [[false, 'list'], [false, 'form']],
            domain: [['type', '=', 'bank']],
            context: { default_type: 'bank' }
        });
    }

    openCashJournals() {
        this.action.doAction({
            name: _t('Diarios de Caja'),
            type: 'ir.actions.act_window',
            res_model: 'account.journal',
            views: [[false, 'list'], [false, 'form']],
            domain: [['type', '=', 'cash']],
            context: { default_type: 'cash' }
        });
    }

    openPendingCustomerInvoices() {
        this.action.doAction({
            name: _t('Por Cobrar (Facturas y Notas Crédito)'),
            type: 'ir.actions.act_window',
            res_model: 'account.move',
            views: [[false, 'list'], [false, 'form']],
            domain: [
                ['state', '=', 'posted'],
                ['payment_state', 'in', ['not_paid', 'partial']],
                ['move_type', 'in', ['out_invoice', 'out_refund']]
            ]
        });
    }

    openPendingSupplierInvoices() {
        this.action.doAction({
            name: _t('Por Pagar (Facturas y Notas Crédito)'),
            type: 'ir.actions.act_window',
            res_model: 'account.move',
            views: [[false, 'list'], [false, 'form']],
            domain: [
                ['state', '=', 'posted'],
                ['payment_state', 'in', ['not_paid', 'partial']],
                ['move_type', 'in', ['in_invoice', 'in_refund']]
            ]
        });
    }

    openAdvances() {
        this.action.doAction({
            name: _t('Anticipos Sin Aplicar'),
            type: 'ir.actions.act_window',
            res_model: 'account.payment',
            views: [[false, 'list'], [false, 'form']],
            domain: [
                ['is_advance', '=', true],
                ['state', '=', 'posted']
            ]
        });
    }

    openAdvanceRequests() {
        this.action.doAction({
            name: _t('Solicitudes de Anticipo'),
            type: 'ir.actions.act_window',
            res_model: 'advance.request',
            views: [[false, 'kanban'], [false, 'list'], [false, 'form']],
            domain: [
                ['stage_id.is_done', '=', false]
            ]
        });
    }

    openPayments() {
        this.action.doAction({
            name: _t('Todos los Pagos'),
            type: 'ir.actions.act_window',
            res_model: 'account.payment',
            views: [[false, 'list'], [false, 'form']],
            domain: [['payment_type', '=', 'outbound']]
        });
    }

    openReceipts() {
        this.action.doAction({
            name: _t('Todos los Cobros'),
            type: 'ir.actions.act_window',
            res_model: 'account.payment',
            views: [[false, 'list'], [false, 'form']],
            domain: [['payment_type', '=', 'inbound']]
        });
    }

    openPaymentForm(paymentId) {
        this.action.doAction({
            name: _t('Pago'),
            type: 'ir.actions.act_window',
            res_model: 'account.payment',
            res_id: paymentId,
            views: [[false, 'form']],
            target: 'current'
        });
    }

    openReceiptForm(receiptId) {
        this.action.doAction({
            name: _t('Cobro'),
            type: 'ir.actions.act_window',
            res_model: 'account.payment',
            res_id: receiptId,
            views: [[false, 'form']],
            target: 'current'
        });
    }

    openDueInvoices(invoiceType, rangeKey) {
        const today = new Date();
        const moveTypes = invoiceType === 'receivable'
            ? ['out_invoice', 'out_refund']
            : ['in_invoice', 'in_refund'];

        const rangeLabels = {
            'overdue': 'Vencidas',
            'today': 'Vencen Hoy',
            'week': 'Próximos 7 días',
            'month': '8-30 días',
            'quarter': '31-90 días'
        };

        const typeLabel = invoiceType === 'receivable' ? 'Por Cobrar' : 'Por Pagar';
        let domain = [
            ['state', '=', 'posted'],
            ['payment_state', 'in', ['not_paid', 'partial']],
            ['move_type', 'in', moveTypes]
        ];

        // Calcular fechas según el rango
        let dateStart, dateEnd;
        switch (rangeKey) {
            case 'overdue':
                dateEnd = new Date(today);
                dateEnd.setDate(today.getDate() - 1);
                domain.push(['invoice_date_due', '<', this.formatDateForInput(today)]);
                break;
            case 'today':
                domain.push(['invoice_date_due', '=', this.formatDateForInput(today)]);
                break;
            case 'week':
                dateStart = new Date(today);
                dateStart.setDate(today.getDate() + 1);
                dateEnd = new Date(today);
                dateEnd.setDate(today.getDate() + 7);
                domain.push(['invoice_date_due', '>=', this.formatDateForInput(dateStart)]);
                domain.push(['invoice_date_due', '<=', this.formatDateForInput(dateEnd)]);
                break;
            case 'month':
                dateStart = new Date(today);
                dateStart.setDate(today.getDate() + 8);
                dateEnd = new Date(today);
                dateEnd.setDate(today.getDate() + 30);
                domain.push(['invoice_date_due', '>=', this.formatDateForInput(dateStart)]);
                domain.push(['invoice_date_due', '<=', this.formatDateForInput(dateEnd)]);
                break;
            case 'quarter':
                dateStart = new Date(today);
                dateStart.setDate(today.getDate() + 31);
                dateEnd = new Date(today);
                dateEnd.setDate(today.getDate() + 90);
                domain.push(['invoice_date_due', '>=', this.formatDateForInput(dateStart)]);
                domain.push(['invoice_date_due', '<=', this.formatDateForInput(dateEnd)]);
                break;
        }

        this.action.doAction({
            name: _t(`${typeLabel} - ${rangeLabels[rangeKey]}`),
            type: 'ir.actions.act_window',
            res_model: 'account.move',
            views: [[false, 'list'], [false, 'form']],
            domain: domain,
            context: { search_default_group_by_partner: 1 }
        });
    }

    openPaymentsByState(state) {
        this.action.doAction({
            name: _t(`Pagos - ${state}`),
            type: 'ir.actions.act_window',
            res_model: 'account.payment',
            views: [[false, 'list'], [false, 'form']],
            domain: [['state', '=', state]]
        });
    }

    openPartnerPayments(partnerId, partnerName, paymentType) {
        this.action.doAction({
            name: _t(`Pagos - ${partnerName}`),
            type: 'ir.actions.act_window',
            res_model: 'account.payment',
            views: [[false, 'list'], [false, 'form']],
            domain: [
                ['partner_id', '=', partnerId],
                ['payment_type', '=', paymentType],
                ['state', 'in', ['posted', 'paid']]
            ]
        });
    }

    renderTopSuppliersChart() {
        const container = this.chartRefs.topSuppliersChart.el;
        if (!container || !this.state.dashboardData.top_suppliers.length) return;

        const data = this.state.dashboardData.top_suppliers;
        const ctx = container.getContext('2d');
        const self = this;

        const chartInstance = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: data.map(d => d.partner_name),
                datasets: [{
                    label: 'Total Pagado',
                    data: data.map(d => d.total_amount),
                    backgroundColor: 'rgba(239, 68, 68, 0.7)',
                    borderColor: 'rgb(239, 68, 68)',
                    borderWidth: 1
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: true,
                        text: 'Top 10 Proveedores - Click para ver pagos'
                    },
                    legend: {
                        display: false
                    }
                },
                scales: {
                    x: {
                        beginAtZero: true,
                        ticks: {
                            callback: function(value) {
                                return '$' + value.toLocaleString();
                            }
                        }
                    }
                },
                onClick: (event, elements) => {
                    if (elements.length > 0) {
                        const index = elements[0].index;
                        const partnerId = data[index].partner_id;
                        const partnerName = data[index].partner_name;
                        self.openPartnerPayments(partnerId, partnerName, 'outbound');
                    }
                }
            }
        });

        container.chartInstance = chartInstance;
    }

    // Gráfico de proyección de flujo de efectivo
    renderCashFlowProjectionChart() {
        const container = this.chartRefs.cashFlowProjectionChart.el;
        if (!container || !this.state.dashboardData.cash_flow_projection.length) return;

        const data = this.state.dashboardData.cash_flow_projection;
        const ctx = container.getContext('2d');

        const chartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.map(d => `${d.period || ''} (${d.period_start || ''}-${d.period_end || ''})`),
                datasets: [
                    {
                        label: 'Saldo Proyectado',
                        data: data.map(d => d.projected_balance),
                        borderColor: 'rgb(59, 130, 246)',
                        backgroundColor: 'rgba(59, 130, 246, 0.1)',
                        fill: true,
                        tension: 0.3,
                        borderWidth: 3,
                        pointRadius: 5,
                        pointBackgroundColor: 'rgb(59, 130, 246)'
                    },
                    {
                        label: 'Cobros Esperados',
                        data: data.map(d => d.expected_inbound),
                        borderColor: 'rgb(34, 197, 94)',
                        backgroundColor: 'transparent',
                        borderWidth: 2,
                        borderDash: [5, 5],
                        pointRadius: 4
                    },
                    {
                        label: 'Pagos Esperados',
                        data: data.map(d => d.expected_outbound),
                        borderColor: 'rgb(239, 68, 68)',
                        backgroundColor: 'transparent',
                        borderWidth: 2,
                        borderDash: [5, 5],
                        pointRadius: 4
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: true,
                        text: 'Proyección de Flujo de Efectivo (Próximas 5 Semanas)',
                        font: { size: 14, weight: 'bold' }
                    },
                    legend: {
                        position: 'top'
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return context.dataset.label + ': $' + context.raw.toLocaleString();
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: false,
                        ticks: {
                            callback: function(value) {
                                return '$' + value.toLocaleString();
                            }
                        },
                        grid: {
                            color: 'rgba(0, 0, 0, 0.05)'
                        }
                    },
                    x: {
                        grid: {
                            display: false
                        }
                    }
                }
            }
        });

        container.chartInstance = chartInstance;
    }

    // Gráfico de antigüedad de cuentas por cobrar
    renderAgingReceivableChart() {
        const container = this.chartRefs.agingReceivableChart.el;
        const agingData = this.state.dashboardData.payment_aging;
        if (!container || !agingData.receivable || !agingData.receivable.length) return;

        const data = agingData.receivable;
        const ctx = container.getContext('2d');

        const colors = [
            'rgba(34, 197, 94, 0.7)',   // Verde - Al día
            'rgba(59, 130, 246, 0.7)',  // Azul - 1-30
            'rgba(234, 179, 8, 0.7)',   // Amarillo - 31-60
            'rgba(249, 115, 22, 0.7)',  // Naranja - 61-90
            'rgba(239, 68, 68, 0.7)'    // Rojo - +90
        ];

        const chartInstance = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: data.map(d => d.range),
                datasets: [{
                    label: 'Monto Por Cobrar',
                    data: data.map(d => d.amount),
                    backgroundColor: colors,
                    borderColor: colors.map(c => c.replace('0.7', '1')),
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: true,
                        text: 'Antigüedad de Cuentas por Cobrar',
                        font: { size: 14, weight: 'bold' }
                    },
                    legend: {
                        display: false
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const idx = context.dataIndex;
                                const count = data[idx].count;
                                return [
                                    'Monto: $' + context.raw.toLocaleString(),
                                    'Facturas: ' + count
                                ];
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: function(value) {
                                return '$' + value.toLocaleString();
                            }
                        }
                    }
                }
            }
        });

        container.chartInstance = chartInstance;
    }

    // Gráfico de antigüedad de cuentas por pagar
    renderAgingPayableChart() {
        const container = this.chartRefs.agingPayableChart.el;
        const agingData = this.state.dashboardData.payment_aging;
        if (!container || !agingData.payable || !agingData.payable.length) return;

        const data = agingData.payable;
        const ctx = container.getContext('2d');

        const colors = [
            'rgba(34, 197, 94, 0.7)',   // Verde - Al día
            'rgba(59, 130, 246, 0.7)',  // Azul - 1-30
            'rgba(234, 179, 8, 0.7)',   // Amarillo - 31-60
            'rgba(249, 115, 22, 0.7)',  // Naranja - 61-90
            'rgba(239, 68, 68, 0.7)'    // Rojo - +90
        ];

        const chartInstance = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: data.map(d => d.range),
                datasets: [{
                    label: 'Monto Por Pagar',
                    data: data.map(d => d.amount),
                    backgroundColor: colors,
                    borderColor: colors.map(c => c.replace('0.7', '1')),
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: true,
                        text: 'Antigüedad de Cuentas por Pagar',
                        font: { size: 14, weight: 'bold' }
                    },
                    legend: {
                        display: false
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const idx = context.dataIndex;
                                const count = data[idx].count;
                                return [
                                    'Monto: $' + context.raw.toLocaleString(),
                                    'Facturas: ' + count
                                ];
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: function(value) {
                                return '$' + value.toLocaleString();
                            }
                        }
                    }
                }
            }
        });

        container.chartInstance = chartInstance;
    }

    renderYearlyCashFlowChart() {
        const container = this.chartRefs.yearlyCashFlowChart.el;
        const yearlyData = this.state.dashboardData.yearly_cash_flow;
        if (!container || !yearlyData || !yearlyData.months || !yearlyData.months.length) return;

        const data = yearlyData.months;
        const ctx = container.getContext('2d');

        const chartInstance = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: data.map(d => d.month_name),
                datasets: [
                    {
                        label: 'Ingresos',
                        data: data.map(d => d.inbound),
                        backgroundColor: data.map(d => d.is_future ? 'rgba(34, 197, 94, 0.3)' : 'rgba(34, 197, 94, 0.8)'),
                        borderColor: 'rgb(34, 197, 94)',
                        borderWidth: 1,
                        order: 2
                    },
                    {
                        label: 'Egresos',
                        data: data.map(d => d.outbound),
                        backgroundColor: data.map(d => d.is_future ? 'rgba(239, 68, 68, 0.3)' : 'rgba(239, 68, 68, 0.8)'),
                        borderColor: 'rgb(239, 68, 68)',
                        borderWidth: 1,
                        order: 2
                    },
                    {
                        label: 'Flujo Neto',
                        data: data.map(d => d.net_flow),
                        type: 'line',
                        borderColor: 'rgb(59, 130, 246)',
                        backgroundColor: 'rgba(59, 130, 246, 0.1)',
                        borderWidth: 3,
                        pointRadius: 4,
                        pointBackgroundColor: data.map(d => d.is_current ? 'rgb(234, 179, 8)' : 'rgb(59, 130, 246)'),
                        pointBorderColor: data.map(d => d.is_current ? 'rgb(234, 179, 8)' : 'rgb(59, 130, 246)'),
                        pointRadius: data.map(d => d.is_current ? 8 : 4),
                        tension: 0.3,
                        fill: false,
                        order: 1
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    intersect: false,
                    mode: 'index'
                },
                plugins: {
                    title: {
                        display: true,
                        text: `Flujo de Caja Mensual ${yearlyData.year}`,
                        font: { size: 16, weight: 'bold' }
                    },
                    legend: {
                        position: 'top',
                        labels: { usePointStyle: true }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const value = context.raw || 0;
                                const sign = value >= 0 ? '' : '-';
                                return `${context.dataset.label}: ${sign}$${Math.abs(value).toLocaleString()}`;
                            },
                            afterBody: function(context) {
                                const idx = context[0].dataIndex;
                                const monthData = data[idx];
                                if (monthData.is_current) {
                                    return ['', '★ Mes actual'];
                                }
                                if (monthData.is_future) {
                                    return ['', '(Sin datos aún)'];
                                }
                                return [];
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { display: false }
                    },
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: function(value) {
                                if (Math.abs(value) >= 1000000) {
                                    return '$' + (value / 1000000).toFixed(1) + 'M';
                                }
                                return '$' + value.toLocaleString();
                            }
                        }
                    }
                }
            }
        });

        container.chartInstance = chartInstance;
    }

    renderCashFlowForecastChart() {
        const container = this.chartRefs.cashFlowForecastChart.el;
        const forecastData = this.state.dashboardData.cash_flow_forecast;
        if (!container || !forecastData || !forecastData.forecast_months || !forecastData.forecast_months.length) return;

        const data = forecastData.forecast_months;
        const stats = forecastData.stats || {};
        const ctx = container.getContext('2d');

        // Colores segun nivel de confianza
        const getBarColor = (confidence, type) => {
            const colors = {
                inbound: {
                    high: 'rgba(34, 197, 94, 0.9)',
                    medium: 'rgba(34, 197, 94, 0.6)',
                    low: 'rgba(34, 197, 94, 0.3)'
                },
                outbound: {
                    high: 'rgba(239, 68, 68, 0.9)',
                    medium: 'rgba(239, 68, 68, 0.6)',
                    low: 'rgba(239, 68, 68, 0.3)'
                }
            };
            return colors[type][confidence] || colors[type].medium;
        };

        const chartInstance = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: data.map(d => d.label),
                datasets: [
                    {
                        label: 'Ingresos Proyectados',
                        data: data.map(d => d.projected_inbound),
                        backgroundColor: data.map(d => getBarColor(d.confidence, 'inbound')),
                        borderColor: 'rgb(34, 197, 94)',
                        borderWidth: 1,
                        borderDash: [5, 5],
                        order: 2
                    },
                    {
                        label: 'Egresos Proyectados',
                        data: data.map(d => d.projected_outbound),
                        backgroundColor: data.map(d => getBarColor(d.confidence, 'outbound')),
                        borderColor: 'rgb(239, 68, 68)',
                        borderWidth: 1,
                        borderDash: [5, 5],
                        order: 2
                    },
                    {
                        label: 'Saldo Proyectado',
                        data: data.map(d => d.projected_balance),
                        type: 'line',
                        borderColor: 'rgb(59, 130, 246)',
                        backgroundColor: 'rgba(59, 130, 246, 0.1)',
                        borderWidth: 3,
                        pointRadius: 6,
                        pointBackgroundColor: data.map(d => d.projected_balance >= 0 ? 'rgb(34, 197, 94)' : 'rgb(239, 68, 68)'),
                        pointBorderColor: 'rgb(59, 130, 246)',
                        tension: 0.3,
                        fill: true,
                        order: 1
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    intersect: false,
                    mode: 'index'
                },
                plugins: {
                    title: {
                        display: true,
                        text: 'Prediccion Flujo de Caja (Proximos 6 Meses)',
                        font: { size: 16, weight: 'bold' }
                    },
                    subtitle: {
                        display: true,
                        text: `Tendencia Ingresos: ${stats.inbound_growth_pct || 0}% | Tendencia Egresos: ${stats.outbound_growth_pct || 0}%`,
                        font: { size: 12 },
                        color: '#6b7280'
                    },
                    legend: {
                        position: 'top',
                        labels: { usePointStyle: true }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const value = context.raw || 0;
                                const sign = value >= 0 ? '' : '-';
                                return `${context.dataset.label}: ${sign}$${Math.abs(value).toLocaleString()}`;
                            },
                            afterBody: function(context) {
                                const idx = context[0].dataIndex;
                                const monthData = data[idx];
                                const confidence = {
                                    'high': 'Alta confianza',
                                    'medium': 'Confianza media',
                                    'low': 'Baja confianza'
                                };
                                return ['', `Confianza: ${confidence[monthData.confidence] || 'Media'}`];
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { display: false }
                    },
                    y: {
                        beginAtZero: false,
                        ticks: {
                            callback: function(value) {
                                if (Math.abs(value) >= 1000000) {
                                    return '$' + (value / 1000000).toFixed(1) + 'M';
                                }
                                return '$' + value.toLocaleString();
                            }
                        }
                    }
                }
            }
        });

        container.chartInstance = chartInstance;
    }

    // Acciones adicionales
    openSaleOrders() {
        this.action.doAction({
            name: _t('Órdenes de Venta Pendientes'),
            type: 'ir.actions.act_window',
            res_model: 'sale.order',
            views: [[false, 'list'], [false, 'form']],
            domain: [
                ['state', 'in', ['sale', 'done']],
                ['invoice_status', '!=', 'invoiced']
            ]
        });
    }

    openPurchaseOrders() {
        this.action.doAction({
            name: _t('Órdenes de Compra Pendientes'),
            type: 'ir.actions.act_window',
            res_model: 'purchase.order',
            views: [[false, 'list'], [false, 'form']],
            domain: [
                ['state', 'in', ['purchase', 'done']],
                ['invoice_status', '!=', 'invoiced']
            ]
        });
    }

    // Filtro por diario para proyección
    async onProjectionJournalChange(ev) {
        const journalId = ev.target.value ? parseInt(ev.target.value) : null;
        this.state.projectionJournalId = journalId;
        await this.refreshProjection();
    }

    async refreshProjection() {
        try {
            const { dateFrom, dateTo } = this.calculateDateRange();
            const journalId = this.state.projectionJournalId || false;
            console.log('Refreshing projection:', dateFrom, dateTo, journalId);

            const projection = await this.orm.call(
                "treasury.dashboard",
                "get_cash_flow_projection_filtered",
                [dateFrom, dateTo, journalId]
            );
            console.log('Projection result:', projection);

            this.state.dashboardData.cash_flow_projection = projection || [];

            // Destruir gráfico existente antes de renderizar
            const container = this.chartRefs.cashFlowProjectionChart.el;
            if (container && container.chartInstance) {
                container.chartInstance.destroy();
                container.chartInstance = null;
            }

            this.renderCashFlowProjectionChart();
        } catch (error) {
            console.error("Error refreshing projection:", error);
            this.notification.add(_t("Error al actualizar proyección"), { type: "danger" });
        }
    }

    // Exportar proyección a Excel
    exportProjectionToExcel() {
        const data = this.state.dashboardData.cash_flow_projection;
        if (!data || !data.length) {
            this.notification.add(_t("No hay datos para exportar"), { type: "warning" });
            return;
        }

        // Crear CSV con BOM para Excel
        let csv = '\uFEFF';
        csv += 'Periodo,Fecha Inicio,Fecha Fin,Cobros Esperados,Pagos Esperados,Gastos Bancarios,Flujo Neto,Saldo Proyectado\n';

        data.forEach(row => {
            csv += [
                row.period || '',
                row.period_start || '',
                row.period_end || '',
                row.expected_inbound || 0,
                row.expected_outbound || 0,
                row.bank_expenses || 0,
                row.net_flow || 0,
                row.projected_balance || 0
            ].join(',') + '\n';
        });

        // Descargar archivo
        const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        const url = URL.createObjectURL(blob);
        link.setAttribute('href', url);
        link.setAttribute('download', `proyeccion_flujo_${new Date().toISOString().split('T')[0]}.csv`);
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);

        this.notification.add(_t("Exportación completada"), { type: "success" });
    }
}

registry.category("actions").add("treasury_dashboard", TreasuryDashboard);
