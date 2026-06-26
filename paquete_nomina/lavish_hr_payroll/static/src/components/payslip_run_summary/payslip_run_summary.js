/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class PayslipRunSummary extends Component {
    static template = "lavish_hr_payroll.PayslipRunSummary";
    static props = {
        ...standardFieldProps,
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            expanded: {},
            payslips: [],
            departments: [],
            totals: {
                basic: 0,
                earnings: 0,
                deductions: 0,
                net: 0,
            },
            searchTerm: "",
            selectedDepartment: "all",
            currentPage: 1,
            pageSize: 10,
        });

        onWillStart(async () => {
            await this.loadData();
        });
    }

    async loadData() {
        const resId = this.props.record.resId;
        if (!resId) {
            this.state.loading = false;
            return;
        }

        try {
            const result = await this.orm.call(
                "hr.payslip.run",
                "get_payslips_detail",
                [resId]
            );

            this.state.payslips = result.payslips || [];
            this.state.totals = result.totals || this.state.totals;

            // Extraer departamentos únicos
            const depts = new Set();
            this.state.payslips.forEach(p => {
                if (p.department) depts.add(p.department);
            });
            this.state.departments = Array.from(depts).sort();

            this.state.loading = false;
        } catch (error) {
            console.error("Error loading payslips data:", error);
            this.state.loading = false;
        }
    }

    togglePayslip(payslipId) {
        this.state.expanded[payslipId] = !this.state.expanded[payslipId];
    }

    isPayslipExpanded(payslipId) {
        return this.state.expanded[payslipId] || false;
    }

    formatCurrency(value) {
        return new Intl.NumberFormat('es-CO', {
            style: 'currency',
            currency: 'COP',
            minimumFractionDigits: 0,
            maximumFractionDigits: 0
        }).format(value || 0);
    }

    formatNumber(value) {
        return new Intl.NumberFormat('es-CO', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        }).format(value || 0);
    }

    getStateColor(state) {
        const colors = {
            'draft': '#9E9E9E',
            'verify': '#5C6BC0',     // Indigo
            'done': '#4CAF50',
            'paid': '#0288D1',       // Light Blue
            'cancel': '#E53935',
        };
        return colors[state] || '#9E9E9E';
    }

    getStateBadge(state) {
        const badges = {
            'draft': { bg: '#EEEEEE', color: '#757575', text: 'Borrador' },
            'verify': { bg: '#E8EAF6', color: '#3949AB', text: 'Verificar' },
            'done': { bg: '#E8F5E9', color: '#2E7D32', text: 'Hecho' },
            'paid': { bg: '#E1F5FE', color: '#0277BD', text: 'Pagado' },
            'cancel': { bg: '#FFEBEE', color: '#C62828', text: 'Cancelado' },
        };
        return badges[state] || { bg: '#EEEEEE', color: '#757575', text: state };
    }

    // Filtrado y paginación
    get filteredPayslips() {
        let filtered = this.state.payslips;

        // Filtrar por departamento
        if (this.state.selectedDepartment !== "all") {
            filtered = filtered.filter(p => p.department === this.state.selectedDepartment);
        }

        // Filtrar por búsqueda
        if (this.state.searchTerm) {
            const term = this.state.searchTerm.toLowerCase();
            filtered = filtered.filter(p =>
                p.employee_name.toLowerCase().includes(term) ||
                (p.identification && p.identification.includes(term))
            );
        }

        return filtered;
    }

    get paginatedPayslips() {
        const start = (this.state.currentPage - 1) * this.state.pageSize;
        const end = start + this.state.pageSize;
        return this.filteredPayslips.slice(start, end);
    }

    get totalPages() {
        return Math.ceil(this.filteredPayslips.length / this.state.pageSize);
    }

    get filteredTotals() {
        const filtered = this.filteredPayslips;
        const earnings = filtered.reduce((sum, p) => sum + (p.gross || 0), 0);
        const deductions = filtered.reduce((sum, p) => sum + Math.abs(p.deductions || 0), 0);
        // Neto = Devengos - Deducciones (si net no viene calculado correctamente)
        const netCalc = filtered.reduce((sum, p) => {
            if (p.net && p.net !== 0) {
                return sum + p.net;
            }
            // Si net es 0 o undefined, calcularlo
            return sum + ((p.gross || 0) - Math.abs(p.deductions || 0));
        }, 0);
        return {
            earnings: earnings,
            deductions: deductions,
            net: netCalc,
        };
    }

    onSearchInput(ev) {
        this.state.searchTerm = ev.target.value;
        this.state.currentPage = 1;
    }

    onDepartmentChange(ev) {
        this.state.selectedDepartment = ev.target.value;
        this.state.currentPage = 1;
    }

    onPageSizeChange(ev) {
        this.state.pageSize = parseInt(ev.target.value);
        this.state.currentPage = 1;
    }

    goToPage(page) {
        if (page >= 1 && page <= this.totalPages) {
            this.state.currentPage = page;
        }
    }

    prevPage() {
        this.goToPage(this.state.currentPage - 1);
    }

    nextPage() {
        this.goToPage(this.state.currentPage + 1);
    }

    expandAll() {
        this.paginatedPayslips.forEach(p => {
            this.state.expanded[p.id] = true;
        });
    }

    collapseAll() {
        this.paginatedPayslips.forEach(p => {
            this.state.expanded[p.id] = false;
        });
    }

    async refreshData() {
        this.state.loading = true;
        await this.loadData();
    }

    get hasData() {
        return this.state.payslips.length > 0;
    }

    // Acciones
    async openPayslipForm(payslipId) {
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "hr.payslip",
            res_id: payslipId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async openPayslipModal(payslipId, employeeName) {
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: `Nómina - ${employeeName}`,
            res_model: "hr.payslip",
            res_id: payslipId,
            views: [[false, "form"]],
            target: "new",
        });
    }

    async computePayslip(payslipId) {
        try {
            this.notification.add("Computando nómina...", { type: "info" });

            // Colapsar la nómina antes de computar para evitar referencias a líneas eliminadas
            const wasExpanded = this.state.expanded[payslipId];
            this.state.expanded[payslipId] = false;

            // Computar la nómina
            await this.orm.call("hr.payslip", "compute_sheet", [[payslipId]]);

            // Recargar datos
            await this.loadData();

            // Volver a expandir la nómina con los nuevos datos si estaba expandida
            if (wasExpanded) {
                this.state.expanded[payslipId] = true;
            }

            this.notification.add("Nómina computada exitosamente", { type: "success" });
        } catch (error) {
            console.error("Error computing payslip:", error);
            this.notification.add("Error al computar: " + (error.message || "Error desconocido"), { type: "danger" });
        }
    }

    async viewPayslipLines(payslipId, employeeName) {
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: `Líneas - ${employeeName}`,
            res_model: "hr.payslip.line",
            views: [[false, "list"], [false, "form"]],
            domain: [['slip_id', '=', payslipId]],
            target: "new",
        });
    }

    async addNoveltyToEmployee(employeeId, employeeName) {
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: `Nueva Novedad - ${employeeName}`,
            res_model: "hr.novelties.different.concepts",
            views: [[false, "form"]],
            target: "new",
            context: {
                default_employee_id: employeeId,
            }
        });
    }

    async viewEmployeeNovelties(employeeId, employeeName) {
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: `Novedades - ${employeeName}`,
            res_model: "hr.novelties.different.concepts",
            views: [[false, "list"], [false, "form"]],
            domain: [['employee_id', '=', employeeId]],
            target: "new",
        });
    }

    // Agregar hora extra
    async addOvertimeToEmployee(employeeId, employeeName) {
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: `Nueva Hora Extra - ${employeeName}`,
            res_model: "hr.overtime",
            views: [[false, "form"]],
            target: "new",
            context: {
                default_employee_id: employeeId,
            }
        });
    }

    // Agregar ausencia
    async addLeaveToEmployee(employeeId, employeeName) {
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: `Nueva Ausencia - ${employeeName}`,
            res_model: "hr.leave",
            views: [[false, "form"]],
            target: "new",
            context: {
                default_employee_id: employeeId,
            }
        });
    }

    // Agregar préstamo
    async addLoanToEmployee(employeeId, employeeName) {
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: `Nuevo Préstamo - ${employeeName}`,
            res_model: "hr.loan",
            views: [[false, "form"]],
            target: "new",
            context: {
                default_employee_id: employeeId,
            }
        });
    }

    // Ver formulario de regla salarial
    async viewSalaryRule(ruleId, ruleName) {
        if (!ruleId) return;
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: `Regla: ${ruleName}`,
            res_model: "hr.salary.rule",
            res_id: ruleId,
            views: [[false, "form"]],
            target: "new",
        });
    }

    // Ver detalle de línea de nómina (abre formulario con widget payslip_line_formula)
    async viewPayslipLineDetail(lineId, lineName) {
        if (!lineId) return;
        try {
            // Verificar que el registro existe antes de abrir
            const exists = await this.orm.searchCount("hr.payslip.line", [["id", "=", lineId]]);
            if (!exists) {
                this.notification.add("La línea ya no existe. Recargando datos...", { type: "warning" });
                await this.loadData();
                return;
            }
            await this.action.doAction({
                type: "ir.actions.act_window",
                name: `Detalle: ${lineName}`,
                res_model: "hr.payslip.line",
                res_id: lineId,
                views: [[false, "form"]],
                target: "new",
            });
        } catch (error) {
            console.error("Error opening payslip line detail:", error);
            this.notification.add("Error al abrir detalle. Recargando...", { type: "warning" });
            await this.loadData();
        }
    }

    // Ver hora extra
    async viewOvertime(overtimeId) {
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "Hora Extra",
            res_model: "hr.overtime",
            res_id: overtimeId,
            views: [[false, "form"]],
            target: "new",
        });
    }

    // Ver ausencia
    async viewLeave(leaveId) {
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "Ausencia",
            res_model: "hr.leave",
            res_id: leaveId,
            views: [[false, "form"]],
            target: "new",
        });
    }
}

export const payslipRunSummaryField = {
    component: PayslipRunSummary,
    supportedTypes: ["char", "text", "binary"],
};

registry.category("fields").add("payslip_run_summary", payslipRunSummaryField);
