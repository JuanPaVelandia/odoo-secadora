/** @odoo-module **/
/**
 * Salary Increase Summary Widget
 * ==============================
 * Widget visual estilo resumen para mostrar estadisticas del proceso
 * de aumento salarial de forma grafica e interactiva.
 *
 * Caracteristicas:
 * - Tarjetas de estadisticas con iconos
 * - Barra de progreso visual
 * - Distribucion por departamento (grafico de barras)
 * - Resumen de incrementos por rango salarial
 */

import { Component, useState, onWillStart, onWillUpdateProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { formatMonetary } from "@web/views/fields/formatters";

export class SalaryIncreaseSummary extends Component {
    static template = "lavish_hr_payroll.SalaryIncreaseSummary";
    static props = {
        ...standardFieldProps,
    };

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            loading: true,
            stats: {},
            departmentBreakdown: [],
            salaryRanges: [],
            progressPercentage: 0,
        });

        onWillStart(async () => {
            await this.loadData();
        });

        onWillUpdateProps(async (nextProps) => {
            if (nextProps.record?.resId !== this.props.record?.resId) {
                await this.loadData();
            }
        });
    }

    get recordId() {
        return this.props.record?.resId;
    }

    get currency() {
        return this.props.record?.data?.currency_id?.[1] || "COP";
    }

    async loadData() {
        if (!this.recordId) {
            this.state.loading = false;
            return;
        }

        try {
            const result = await this.orm.call(
                "hr.salary.increase",
                "get_summary_data",
                [this.recordId]
            );

            this.state.stats = result.stats || {};
            this.state.departmentBreakdown = result.department_breakdown || [];
            this.state.salaryRanges = result.salary_ranges || [];
            this.state.progressPercentage = result.progress_percentage || 0;
            this.state.loading = false;
        } catch (error) {
            console.error("Error loading salary increase summary:", error);
            this.state.loading = false;
        }
    }

    formatCurrency(value) {
        if (!value) return "$ 0";
        return new Intl.NumberFormat('es-CO', {
            style: 'currency',
            currency: 'COP',
            minimumFractionDigits: 0,
            maximumFractionDigits: 0,
        }).format(value);
    }

    formatPercentage(value) {
        if (!value) return "0%";
        return `${value.toFixed(1)}%`;
    }

    getProgressClass() {
        const pct = this.state.progressPercentage;
        if (pct >= 100) return "bg-success";
        if (pct >= 50) return "bg-info";
        if (pct >= 25) return "bg-warning";
        return "bg-secondary";
    }

    getMaxDepartmentValue() {
        if (!this.state.departmentBreakdown.length) return 1;
        return Math.max(...this.state.departmentBreakdown.map(d => d.count));
    }

    getDepartmentBarWidth(count) {
        const max = this.getMaxDepartmentValue();
        return `${(count / max) * 100}%`;
    }

    getRangeColor(index) {
        const colors = ['bg-primary', 'bg-info', 'bg-success', 'bg-warning', 'bg-danger'];
        return colors[index % colors.length];
    }
}

// Registrar como widget de campo
registry.category("fields").add("salary_increase_summary", {
    component: SalaryIncreaseSummary,
});
