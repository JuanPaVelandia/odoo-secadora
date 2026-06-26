/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class PayrollDashboardTabs extends Component {
    static template = "lavish_hr_payroll.DashboardTabs";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.state = useState({
            activeTab: 'resumen',
            loading: true,
            kpis: {},
            alerts: {
                count: 0,
                items: []
            }
        });

        this.tabs = [
            {
                id: 'resumen',
                name: 'Resumen Ejecutivo',
                icon: 'fa-dashboard',
                color: 'primary',
                badge: null
            },
            {
                id: 'nomina',
                name: 'Gestión de Nómina',
                icon: 'fa-money',
                color: 'success',
                badge: null
            },
            {
                id: 'personal',
                name: 'Gestión de Personal',
                icon: 'fa-users',
                color: 'info',
                badge: null
            },
            {
                id: 'indicadores',
                name: 'Indicadores',
                icon: 'fa-chart-line',
                color: 'warning',
                badge: null
            },
            {
                id: 'alertas',
                name: 'Alertas',
                icon: 'fa-exclamation-triangle',
                color: 'danger',
                badge: () => this.state.alerts.count || null
            }
        ];

        onWillStart(async () => {
            await this.loadDashboardData();
        });
    }

    async loadDashboardData() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                'hr.payslip',
                'get_dashboard_data',
                [],
                {
                    context: this.env.context
                }
            );

            this.state.kpis = data.kpis || {};
            this.state.alerts = data.alerts || { count: 0, items: [] };

            // Actualizar badges dinámicos
            this.updateTabBadges(data);

        } catch (error) {
            console.error('Error loading dashboard:', error);
        } finally {
            this.state.loading = false;
        }
    }

    updateTabBadges(data) {
        // Badge para nómina (lotes pendientes)
        const nominaTab = this.tabs.find(t => t.id === 'nomina');
        if (nominaTab && data.pending_batches) {
            nominaTab.badge = () => data.pending_batches;
        }

        // Badge para personal (nuevos empleados)
        const personalTab = this.tabs.find(t => t.id === 'personal');
        if (personalTab && data.new_employees_count) {
            personalTab.badge = () => data.new_employees_count;
        }
    }

    onTabChange(tabId) {
        this.state.activeTab = tabId;
    }

    getTabBadge(tab) {
        if (typeof tab.badge === 'function') {
            return tab.badge();
        }
        return tab.badge;
    }

    async handleAction(action, kwargs = {}) {
        if (action === 'view_alerts') {
            this.state.activeTab = 'alertas';
        } else {
            await this.action.doAction(action, kwargs);
        }
    }
}

registry.category("actions").add("payroll_dashboard_tabs", PayrollDashboardTabs);
