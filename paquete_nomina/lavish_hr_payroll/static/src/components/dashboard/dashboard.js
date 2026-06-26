/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { KPICard } from "./kpi_card/kpi_card";
import { SocialSecurityChart } from "./social_security_chart/social_security_chart";
import { BatchList } from "./batch_list/batch_list";
import { PayslipList } from "./payslip_list/payslip_list";
import { GenerateBatchModal } from "./generate_batch_modal/generate_batch_modal";
import { IncomeDeductionsChart } from "./income_deductions_chart/income_deductions_chart";
import { DisabilityChart } from "./disability_chart/disability_chart";
import { OvertimeDepartmentChart } from "./overtime_department_chart/overtime_department_chart";
import { AbsencesByTypeChart } from "./absences_by_type_chart/absences_by_type_chart";
import { AccidentsTrendChart } from "./accidents_trend_chart/accidents_trend_chart";
import { CityMapCard } from "./city_map_card/city_map_card";
import { SummaryHeroCard } from "./summary_hero/summary_hero";
import { AlertsBreakdownChart } from "./alerts_breakdown_chart/alerts_breakdown_chart";
import { AlertsDetailCard } from "./alerts_detail_card/alerts_detail_card";
import { ExpiringContractsCard } from "./expiring_contracts_card/expiring_contracts_card";
import { PaymentScheduleCard } from "./payment_schedule_card/payment_schedule_card";
import { NewEmployeesCard } from "./new_employees_card/new_employees_card";
import { PendingLeavesCard } from "./pending_leaves_card/pending_leaves_card";
import { PayrollSummaryCard } from "./payroll_summary_card/payroll_summary_card";

export class LavishHRPayrollDashboard extends Component {
    static template = "lavish_hr_payroll.Dashboard";
    static components = {
        KPICard,
        SocialSecurityChart,
        BatchList,
        PayslipList,
        GenerateBatchModal,
        IncomeDeductionsChart,
        DisabilityChart,
        OvertimeDepartmentChart,
        AbsencesByTypeChart,
        AccidentsTrendChart,
        CityMapCard,
        SummaryHeroCard,
        AlertsBreakdownChart,
        AlertsDetailCard,
        ExpiringContractsCard,
        PaymentScheduleCard,
        NewEmployeesCard,
        PendingLeavesCard,
        PayrollSummaryCard,
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        // Cargar estado guardado
        const savedState = this._loadState();

        this.state = useState({
            loading: true,
            dashboardData: null,
            selectedPeriodId: savedState.selectedPeriodId || null,
            selectedDepartmentId: savedState.selectedDepartmentId || null,
            showGenerateBatchModal: false,
            periodType: savedState.periodType || 'payroll_period', // 'payroll_period', 'today', 'week', 'month', 'quarter', 'year', etc.
            customDateFrom: savedState.customDateFrom || this._formatDate(new Date()),
            customDateTo: savedState.customDateTo || this._formatDate(new Date()),
            activeTab: savedState.activeTab || 'resumen',
        });

        this.tabs = [
            {
                id: 'resumen',
                name: 'Resumen',
                icon: 'fa-chart-pie',
            },
            {
                id: 'nomina',
                name: 'Nómina',
                icon: 'fa-file-invoice-dollar',
                badge: () => this.payslips.length || null,
            },
            {
                id: 'talento',
                name: 'Talento',
                icon: 'fa-users',
                badge: () => this.newEmployees.total || null,
            },
            {
                id: 'analitica',
                name: 'Analítica',
                icon: 'fa-chart-line',
            },
            {
                id: 'alertas',
                name: 'Alertas',
                icon: 'fa-exclamation-triangle',
                badge: () => this.alertsCount || null,
            },
        ];

        if (!this.tabs.some((tab) => tab.id === this.state.activeTab)) {
            this.state.activeTab = 'resumen';
        }

        onWillStart(async () => {
            await this.loadDashboardData();
        });
    }

    _loadState() {
        try {
            const saved = localStorage.getItem('payroll_dashboard_state');
            return saved ? JSON.parse(saved) : {};
        } catch (e) {
            console.error('Error loading dashboard state:', e);
            return {};
        }
    }

    _saveState() {
        try {
            const stateToSave = {
                selectedPeriodId: this.state.selectedPeriodId,
                selectedDepartmentId: this.state.selectedDepartmentId,
                periodType: this.state.periodType,
                customDateFrom: this.state.customDateFrom,
                customDateTo: this.state.customDateTo,
                activeTab: this.state.activeTab,
            };
            localStorage.setItem('payroll_dashboard_state', JSON.stringify(stateToSave));
        } catch (e) {
            console.error('Error saving dashboard state:', e);
        }
    }

    _formatDate(date) {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    }

    _getDateRangeForPeriodType(periodType) {
        const today = new Date();
        let dateFrom, dateTo;

        switch(periodType) {
            case 'today':
                dateFrom = dateTo = today;
                break;

            case 'week':
                // Esta semana (lunes a domingo)
                const dayOfWeek = today.getDay();
                const diff = today.getDate() - dayOfWeek + (dayOfWeek === 0 ? -6 : 1); // adjust when day is sunday
                dateFrom = new Date(today.setDate(diff));
                dateTo = new Date(dateFrom);
                dateTo.setDate(dateFrom.getDate() + 6);
                break;

            case 'month':
                // Este mes
                dateFrom = new Date(today.getFullYear(), today.getMonth(), 1);
                dateTo = new Date(today.getFullYear(), today.getMonth() + 1, 0);
                break;

            case 'quarter':
                // Este trimestre
                const quarter = Math.floor(today.getMonth() / 3);
                dateFrom = new Date(today.getFullYear(), quarter * 3, 1);
                dateTo = new Date(today.getFullYear(), quarter * 3 + 3, 0);
                break;

            case 'year':
                // Este año
                dateFrom = new Date(today.getFullYear(), 0, 1);
                dateTo = new Date(today.getFullYear(), 11, 31);
                break;

            case 'prev_month':
                // Mes anterior
                dateFrom = new Date(today.getFullYear(), today.getMonth() - 1, 1);
                dateTo = new Date(today.getFullYear(), today.getMonth(), 0);
                break;

            case 'prev_quarter':
                // Trimestre anterior
                const prevQuarter = Math.floor(today.getMonth() / 3) - 1;
                const prevQuarterYear = prevQuarter < 0 ? today.getFullYear() - 1 : today.getFullYear();
                const adjustedQuarter = prevQuarter < 0 ? 3 : prevQuarter;
                dateFrom = new Date(prevQuarterYear, adjustedQuarter * 3, 1);
                dateTo = new Date(prevQuarterYear, adjustedQuarter * 3 + 3, 0);
                break;

            case 'prev_year':
                // Año anterior
                dateFrom = new Date(today.getFullYear() - 1, 0, 1);
                dateTo = new Date(today.getFullYear() - 1, 11, 31);
                break;

            default:
                return null;
        }

        return {
            date_from: this._formatDate(dateFrom),
            date_to: this._formatDate(dateTo)
        };
    }

    async loadDashboardData(periodId = null, departmentId = null) {
        this.state.loading = true;
        try {
            const params = {
                department_id: departmentId !== null ? departmentId : this.state.selectedDepartmentId,
            };

            // Si es periodo de nómina, enviar period_id
            if (this.state.periodType === 'payroll_period') {
                params.period_id = periodId !== null ? periodId : this.state.selectedPeriodId;
            }
            // Si es custom, usar las fechas del state
            else if (this.state.periodType === 'custom') {
                params.date_from = this.state.customDateFrom;
                params.date_to = this.state.customDateTo;
            }
            // Si es un tipo predefinido, calcular las fechas
            else {
                const dateRange = this._getDateRangeForPeriodType(this.state.periodType);
                if (dateRange) {
                    params.date_from = dateRange.date_from;
                    params.date_to = dateRange.date_to;
                }
            }

            const data = await this.orm.call(
                "hr.payslip",
                "get_hr_dashboard_data",
                [],
                params
            );
            this.state.dashboardData = data;
            if (periodId !== null) this.state.selectedPeriodId = periodId;
            if (departmentId !== null) this.state.selectedDepartmentId = departmentId;
            this.state.loading = false;
        } catch (error) {
            console.error("Error loading dashboard data:", error);
            this.notification.add("Error al cargar datos del dashboard", {
                type: "danger",
            });
            this.state.loading = false;
        }
    }

    async onPeriodTypeChange(ev) {
        const periodType = ev.target.value;
        this.state.periodType = periodType;
        this._saveState();

        // Si cambia a periodo de nómina, recargar con el periodo actual
        if (periodType === 'payroll_period') {
            await this.loadDashboardData(this.state.selectedPeriodId, this.state.selectedDepartmentId);
        }
        // Si cambia a custom, no recargar hasta que el usuario seleccione fechas
        else if (periodType === 'custom') {
            // No hacer nada, esperar a que el usuario seleccione fechas
        }
        // Para otros tipos, calcular y recargar
        else {
            await this.loadDashboardData(null, this.state.selectedDepartmentId);
        }
    }

    async onPeriodChange(ev) {
        const periodId = parseInt(ev.target.value) || null;
        this.state.selectedPeriodId = periodId;
        this._saveState();
        await this.loadDashboardData(periodId, this.state.selectedDepartmentId);
    }

    async onCustomDateChange(ev, field) {
        this.state[field] = ev.target.value;
        this._saveState();
        // Solo recargar si ambas fechas están definidas
        if (this.state.customDateFrom && this.state.customDateTo) {
            await this.loadDashboardData(null, this.state.selectedDepartmentId);
        }
    }

    async onDepartmentChange(ev) {
        const departmentId = parseInt(ev.target.value) || null;
        this.state.selectedDepartmentId = departmentId;
        this._saveState();
        await this.loadDashboardData(this.state.selectedPeriodId, departmentId);
    }

    async onRefresh() {
        await this.loadDashboardData(this.state.selectedPeriodId);
        this.notification.add("Dashboard actualizado", {
            type: "success",
        });
    }

    onTabChange(tabId) {
        this.state.activeTab = tabId;
        this._saveState();
    }

    getTabBadge(tab) {
        if (typeof tab.badge === 'function') {
            return tab.badge();
        }
        return tab.badge;
    }

    get alertsCount() {
        const withoutSS = this.kpis.employees_without_ss?.value || 0;
        const withoutPayslip = this.kpis.employees_without_payslip?.value || 0;
        const withoutSettlement = this.kpis.employees_without_settlement?.value || 0;
        return withoutSS + withoutPayslip + withoutSettlement;
    }

    onGenerateBatch() {
        this.state.showGenerateBatchModal = true;
    }

    async onBatchGenerated() {
        this.state.showGenerateBatchModal = false;
        await this.loadDashboardData(this.state.selectedPeriodId);
        this.notification.add("Lote generado exitosamente", {
            type: "success",
        });
    }

    onCloseModal() {
        this.state.showGenerateBatchModal = false;
    }

    get period() {
        return this.state.dashboardData?.period || {};
    }

    get kpis() {
        return this.state.dashboardData?.kpis || {};
    }

    get socialSecurity() {
        return this.state.dashboardData?.social_security || {};
    }

    get batches() {
        return this.state.dashboardData?.batches || [];
    }

    get payslips() {
        return this.state.dashboardData?.payslips || [];
    }

    get charts() {
        return this.state.dashboardData?.charts || {};
    }

    get departments() {
        return this.state.dashboardData?.departments || [];
    }

    get periods() {
        return this.state.dashboardData?.periods || [];
    }

    get expiringContracts() {
        return this.state.dashboardData?.expiring_contracts || {};
    }

    get paymentSchedule() {
        return this.state.dashboardData?.payment_schedule || {};
    }

    get newEmployees() {
        return this.state.dashboardData?.new_employees || {};
    }

    get pendingLeaves() {
        return this.state.dashboardData?.pending_leaves || {};
    }

    get payrollSummary() {
        return this.state.dashboardData?.payroll_summary || {};
    }

    get company() {
        return this.state.dashboardData?.company || {};
    }

    get payrollTrend() {
        return this.charts.payroll_trend || {};
    }

    get employeesByCity() {
        return this.charts.employees_by_city || {};
    }

    get alertsBreakdown() {
        return {
            without_ss: this.kpis.employees_without_ss?.value || 0,
            without_payslip: this.kpis.employees_without_payslip?.value || 0,
            without_settlement: this.kpis.employees_without_settlement?.value || 0,
        };
    }

    get overtimeByDepartment() {
        return this.charts.overtime_by_department || {};
    }

    get absencesByType() {
        return this.charts.absences_by_type || {};
    }

    get accidentsTrend() {
        return this.charts.accidents_chart || {};
    }

    get overtimeTotalHours() {
        return this._sumDataset(this.overtimeByDepartment, 0);
    }

    get absencesTotalDays() {
        return this._sumDataset(this.absencesByType, 0);
    }

    get accidentsTotal() {
        return this._sumDataset(this.accidentsTrend, 0);
    }

    get incidentsTotal() {
        return this._sumDataset(this.accidentsTrend, 1);
    }

    get overtimeTotalLabel() {
        return `${this._formatNumber(this.overtimeTotalHours, 1)} h`;
    }

    get absencesTotalLabel() {
        return `${this._formatNumber(this.absencesTotalDays, 1)} días`;
    }

    get accidentsTotalLabel() {
        return this._formatNumber(this.accidentsTotal, 0);
    }

    get incidentsTotalLabel() {
        return this._formatNumber(this.incidentsTotal, 0);
    }

    _sumDataset(chartData, index) {
        const values = chartData?.datasets?.[index]?.data || [];
        return values.reduce((sum, value) => sum + (Number(value) || 0), 0);
    }

    _formatNumber(value, maxFractionDigits = 1) {
        return (Number(value) || 0).toLocaleString("es-CO", {
            maximumFractionDigits: maxFractionDigits,
        });
    }

    async handleAction(actionName, kwargs = {}) {
        try {
            // Agregar el departamento seleccionado si existe y no está ya en kwargs
            const params = { ...kwargs };
            if (this.state.selectedDepartmentId && !params.department_id) {
                params.department_id = this.state.selectedDepartmentId;
            }

            const actionData = await this.orm.call(
                "hr.payslip",
                "get_dashboard_action",
                [],
                {
                    action_name: actionName,
                    ...params
                }
            );
            if (actionData) {
                await this.action.doAction(actionData);
            }
        } catch (error) {
            console.error("Error executing dashboard action:", error);
            this.notification.add("Error al ejecutar la acción", {
                type: "danger",
            });
        }
    }
}

registry.category("actions").add("lavish_hr_payroll_dashboard", LavishHRPayrollDashboard);
