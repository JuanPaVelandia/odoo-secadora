/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class PayslipList extends Component {
    static template = "lavish_hr_payroll.PayslipList";
    static props = {
        payslips: Array,
        period: Object,
    };

    setup() {
        this.action = useService("action");
        this.state = useState({
            currentPage: 1,
            itemsPerPage: 10,
            expanded: {},
            searchTerm: "",
            selectedState: "all",
        });
    }

    // Filtros
    get states() {
        return [
            { key: 'all', label: 'Todos', color: 'secondary' },
            { key: 'draft', label: 'Borrador', color: 'secondary' },
            { key: 'verify', label: 'Verificar', color: 'info' },
            { key: 'done', label: 'Hecho', color: 'success' },
            { key: 'paid', label: 'Pagado', color: 'primary' },
        ];
    }

    get filteredPayslips() {
        let filtered = this.props.payslips;

        // Filtrar por estado
        if (this.state.selectedState !== "all") {
            filtered = filtered.filter(p => p.state === this.state.selectedState);
        }

        // Filtrar por búsqueda
        if (this.state.searchTerm) {
            const term = this.state.searchTerm.toLowerCase();
            filtered = filtered.filter(p =>
                p.employee_name.toLowerCase().includes(term) ||
                (p.number && p.number.toLowerCase().includes(term))
            );
        }

        return filtered;
    }

    get stateCount() {
        const counts = { all: this.props.payslips.length };
        for (const p of this.props.payslips) {
            counts[p.state] = (counts[p.state] || 0) + 1;
        }
        return counts;
    }

    get filteredTotals() {
        const filtered = this.filteredPayslips;
        return {
            devengado: filtered.reduce((sum, p) => sum + (p.devengado || 0), 0),
            deducciones: filtered.reduce((sum, p) => sum + (p.deducciones || 0), 0),
            neto: filtered.reduce((sum, p) => sum + (p.neto || 0), 0),
        };
    }

    get totalPages() {
        return Math.ceil(this.filteredPayslips.length / this.state.itemsPerPage);
    }

    get paginatedPayslips() {
        const start = (this.state.currentPage - 1) * this.state.itemsPerPage;
        const end = start + this.state.itemsPerPage;
        return this.filteredPayslips.slice(start, end);
    }

    get pageNumbers() {
        const pages = [];
        const maxPagesToShow = 5;
        const totalPages = this.totalPages;

        let startPage = Math.max(1, this.state.currentPage - Math.floor(maxPagesToShow / 2));
        let endPage = Math.min(totalPages, startPage + maxPagesToShow - 1);

        if (endPage - startPage + 1 < maxPagesToShow) {
            startPage = Math.max(1, endPage - maxPagesToShow + 1);
        }

        for (let i = startPage; i <= endPage; i++) {
            pages.push(i);
        }

        return pages;
    }

    // Métodos de formato
    formatCurrency(value) {
        return new Intl.NumberFormat('es-CO', {
            style: 'currency',
            currency: 'COP',
            minimumFractionDigits: 0,
            maximumFractionDigits: 0
        }).format(value || 0);
    }

    // Navegación
    goToPage(page) {
        if (page >= 1 && page <= this.totalPages) {
            this.state.currentPage = page;
        }
    }

    nextPage() {
        if (this.state.currentPage < this.totalPages) {
            this.state.currentPage++;
        }
    }

    prevPage() {
        if (this.state.currentPage > 1) {
            this.state.currentPage--;
        }
    }

    // Filtros
    setStateFilter(state) {
        this.state.selectedState = state;
        this.state.currentPage = 1;
    }

    onSearchInput(ev) {
        this.state.searchTerm = ev.target.value;
        this.state.currentPage = 1;
    }

    onPageSizeChange(ev) {
        this.state.itemsPerPage = parseInt(ev.target.value);
        this.state.currentPage = 1;
    }

    // Expandir/Colapsar
    togglePayslip(payslipId) {
        this.state.expanded[payslipId] = !this.state.expanded[payslipId];
    }

    isExpanded(payslipId) {
        return this.state.expanded[payslipId] || false;
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

    // Acciones
    async openPayslip(payslipId) {
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

    getStateClass(state) {
        const stateClasses = {
            'draft': 'secondary',
            'verify': 'info',
            'done': 'success',
            'paid': 'primary',
            'cancel': 'danger',
        };
        return stateClasses[state] || 'secondary';
    }

    getStateColor(state) {
        const colors = {
            'draft': '#9E9E9E',
            'verify': '#5C6BC0',
            'done': '#4CAF50',
            'paid': '#0288D1',
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
}
