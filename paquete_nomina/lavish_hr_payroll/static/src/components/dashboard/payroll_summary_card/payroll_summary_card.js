/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class PayrollSummaryCard extends Component {
    static template = "lavish_hr_payroll.PayrollSummaryCard";

    setup() {
        this.action = useService("action");
        this.state = useState({
            isFullscreen: false,
            activeTab: 'devengos',
        });
    }

    get hasData() {
        return this.props.summaryData && (
               (this.props.summaryData.items && this.props.summaryData.items.length > 0) ||
               (this.props.summaryData.payslips_count && this.props.summaryData.payslips_count > 0)
        );
    }

    get totalDevengos() {
        return this.props.summaryData?.formatted_devengos || '$0';
    }

    get totalDeducciones() {
        return this.props.summaryData?.formatted_deducciones || '$0';
    }

    get totalNeto() {
        return this.props.summaryData?.formatted_neto || '$0';
    }

    get payslipsCount() {
        return this.props.summaryData?.payslips_count || 0;
    }

    get employeesCount() {
        return this.props.summaryData?.employees_count || 0;
    }

    get devengosItems() {
        if (!this.props.summaryData?.items) return [];
        return this.props.summaryData.items.filter(item => item.type === 'earning');
    }

    get deduccionesItems() {
        if (!this.props.summaryData?.items) return [];
        return this.props.summaryData.items.filter(item => item.type === 'deduction');
    }

    get allItems() {
        return this.props.summaryData?.items || [];
    }

    getColorClass(color) {
        const colors = {
            'danger': 'text-danger',
            'success': 'text-success',
            'warning': 'text-warning',
            'info': 'text-info',
            'primary': 'text-primary',
            'secondary': 'text-secondary',
            'purple': 'text-purple',
            'pink': 'text-pink'
        };
        return colors[color] || 'text-secondary';
    }

    getBgColorClass(color) {
        const colors = {
            'danger': 'bg-danger',
            'success': 'bg-success',
            'warning': 'bg-warning',
            'info': 'bg-info',
            'primary': 'bg-primary',
            'secondary': 'bg-secondary',
            'purple': 'bg-purple',
            'pink': 'bg-pink'
        };
        return colors[color] || 'bg-secondary';
    }

    getLordicon(key) {
        // Ruta base para iconos locales (sin CDN)
        const basePath = '/lavish_hr_payroll/static/src/lib/lottie/icons/';
        const icons = {
            'sueldo': basePath + 'qhviklyi.json',
            'auxilio': basePath + 'uiiwvjrg.json',
            'horas_extras': basePath + 'kbtmbyzy.json',
            'comisiones': basePath + 'wyqtxzeh.json',
            'vacaciones': basePath + 'iprinfmf.json',
            'incapacidades': basePath + 'yrxnwkni.json',
            'licencias': basePath + 'hrqwmutt.json',
            'prestaciones': basePath + 'fqbvgezn.json',
            'devengos_salariales': basePath + 'qhviklyi.json',
            'devengos_no_salariales': basePath + 'mwikjdwh.json',
            'seguridad_social': basePath + 'mqqsmoak.json',
            'retencion': basePath + 'nizfqlnq.json',
            'deducciones': basePath + 'vduvxizq.json'
        };
        return icons[key] || basePath + 'wloilxuq.json';
    }

    toggleFullscreen() {
        this.state.isFullscreen = !this.state.isFullscreen;
    }

    setActiveTab(tab) {
        this.state.activeTab = tab;
    }

    async onViewPayslips() {
        if (this.props.onAction) {
            const params = {};
            if (this.props.period?.id) {
                params.period_id = this.props.period.id;
            }
            await this.props.onAction('view_payslips', params);
        }
    }

    async onViewDetail(key) {
        if (this.props.onAction) {
            const params = { category_code: key };
            if (this.props.period?.id) {
                params.period_id = this.props.period.id;
            }
            await this.props.onAction('view_payslip_lines_by_category', params);
        }
    }
}
