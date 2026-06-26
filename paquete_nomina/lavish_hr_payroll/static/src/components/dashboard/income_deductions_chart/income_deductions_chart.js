/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class IncomeDeductionsChart extends Component {
    static template = "lavish_hr_payroll.IncomeDeductionsChart";

    setup() {
        this.action = useService("action");

        // Load saved state from localStorage
        const savedState = this._loadState();

        this.state = useState({
            collapsed: savedState.collapsed || false,
            searchText: '',
            expandedCategories: savedState.expandedCategories || {}, // {categoryCode: true/false}
            expandedRules: savedState.expandedRules || {}, // {categoryCode: true/false} - NEW
            expandedEmployees: savedState.expandedEmployees || {},  // {employeeId: true/false}
            employeesPage: {}, // {categoryCode: pageNumber} - Paginación por categoría
            employeesPerPage: 5, // Empleados por página
        });
    }

    _loadState() {
        try {
            const saved = localStorage.getItem('income_deductions_chart_state');
            return saved ? JSON.parse(saved) : {};
        } catch (e) {
            console.error('Error loading dashboard state:', e);
            return {};
        }
    }

    _saveState() {
        try {
            const stateToSave = {
                collapsed: this.state.collapsed,
                expandedCategories: this.state.expandedCategories,
                expandedRules: this.state.expandedRules,
                expandedEmployees: this.state.expandedEmployees,
            };
            localStorage.setItem('income_deductions_chart_state', JSON.stringify(stateToSave));
        } catch (e) {
            console.error('Error saving dashboard state:', e);
        }
    }

    toggleCategoryExpand(categoryCode) {
        this.state.expandedCategories[categoryCode] = !this.state.expandedCategories[categoryCode];
        this._saveState();
    }

    isCategoryExpanded(categoryCode) {
        return !!this.state.expandedCategories[categoryCode];
    }

    toggleRulesExpand(categoryCode) {
        this.state.expandedRules[categoryCode] = !this.state.expandedRules[categoryCode];
        this._saveState();
    }

    isRulesExpanded(categoryCode) {
        return !!this.state.expandedRules[categoryCode];
    }

    toggleEmployeeExpand(employeeId) {
        this.state.expandedEmployees[employeeId] = !this.state.expandedEmployees[employeeId];
        this._saveState();
    }

    isEmployeeExpanded(employeeId) {
        return !!this.state.expandedEmployees[employeeId];
    }

    toggleCollapse() {
        this.state.collapsed = !this.state.collapsed;
        this._saveState();
    }

    onSearchChange(ev) {
        this.state.searchText = ev.target.value.toLowerCase();
    }

    _filterItems(items) {
        if (!this.state.searchText) return items;

        return items.filter(item => {
            const name = (item.name || item.label || '').toLowerCase();
            const code = (item.code || '').toLowerCase();
            return name.includes(this.state.searchText) || code.includes(this.state.searchText);
        });
    }

    get hasData() {
        return this.props.chartData &&
               (this.props.chartData.income?.categories?.length > 0 ||
                this.props.chartData.deductions?.categories?.length > 0);
    }

    get netAmount() {
        if (!this.props.chartData?.net) return { value: 0, formatted: '$0' };
        return this.props.chartData.net;
    }

    get totalIncome() {
        if (!this.props.chartData?.income) return { total: 0, formatted_total: '$0' };
        return {
            total: this.props.chartData.income.total || 0,
            formatted: this.props.chartData.income.formatted_total || '$0'
        };
    }

    get totalDeductions() {
        if (!this.props.chartData?.deductions) return { total: 0, formatted_total: '$0' };
        return {
            total: this.props.chartData.deductions.total || 0,
            formatted: this.props.chartData.deductions.formatted_total || '$0'
        };
    }

    get incomeItemsRaw() {
        // Usar 'categories' que incluye código de categoría y reglas
        if (this.props.chartData?.income?.categories) {
            return this.props.chartData.income.categories;
        }
        return [];
    }

    get deductionItemsRaw() {
        // Usar 'categories' que incluye código de categoría y reglas
        if (this.props.chartData?.deductions?.categories) {
            return this.props.chartData.deductions.categories;
        }
        return [];
    }

    get incomeItems() {
        return this._filterItems(this.incomeItemsRaw);
    }

    get deductionItems() {
        return this._filterItems(this.deductionItemsRaw);
    }

    getPercentage(value, total) {
        if (!total || total === 0) return 0;
        return ((value / total) * 100).toFixed(1);
    }

    // Paginación de empleados
    getEmployeesPage(categoryCode) {
        return this.state.employeesPage[categoryCode] || 1;
    }

    getPaginatedEmployees(employees, categoryCode) {
        if (!employees || employees.length === 0) return [];
        const page = this.getEmployeesPage(categoryCode);
        const perPage = this.state.employeesPerPage;
        const start = (page - 1) * perPage;
        const end = start + perPage;
        return employees.slice(start, end);
    }

    getTotalEmployeesPages(employees) {
        if (!employees || employees.length === 0) return 1;
        return Math.ceil(employees.length / this.state.employeesPerPage);
    }

    nextEmployeesPage(categoryCode, totalPages) {
        const currentPage = this.getEmployeesPage(categoryCode);
        if (currentPage < totalPages) {
            this.state.employeesPage[categoryCode] = currentPage + 1;
        }
    }

    prevEmployeesPage(categoryCode) {
        const currentPage = this.getEmployeesPage(categoryCode);
        if (currentPage > 1) {
            this.state.employeesPage[categoryCode] = currentPage - 1;
        }
    }

    goToEmployeesPage(categoryCode, page) {
        this.state.employeesPage[categoryCode] = page;
    }

    getCategoryIcon(categoryCode, categoryName) {
        const code = (categoryCode || '').toUpperCase();
        const name = (categoryName || '').toUpperCase();

        // Iconos para categorías de ingresos (devengos)
        if (code.includes('BASIC') || name.includes('BÁSICO') || name.includes('BASICO')) {
            return 'fa-money';
        }
        if (code.includes('DEV_SALARIAL') || name.includes('SALARIAL')) {
            return 'fa-usd';
        }
        if (code.includes('AUXILIO') || code.includes('AUX') || name.includes('AUXILIO')) {
            return 'fa-life-ring';
        }
        if (code.includes('HORAS_EXTRA') || name.includes('EXTRA')) {
            return 'fa-clock';
        }
        if (code.includes('INCAPACIDAD') || name.includes('INCAPACIDAD')) {
            return 'fa-medkit';
        }
        if (code.includes('VACACIONES') || name.includes('VACACIONES')) {
            return 'fa-plane';
        }
        if (code.includes('BONIFICACION') || name.includes('BONIFICACIÓN')) {
            return 'fa-gift';
        }
        if (code.includes('COMISION') || name.includes('COMISIÓN')) {
            return 'fa-chart-line';
        }

        // Iconos para categorías de deducciones
        if (code.includes('SALUD') || name.includes('SALUD')) {
            return 'fa-heartbeat';
        }
        if (code.includes('PENSION') || name.includes('PENSIÓN')) {
            return 'fa-institution';
        }
        if (code.includes('RETENCION') || code.includes('RTEFTE') || name.includes('RETENCIÓN')) {
            return 'fa-percent';
        }
        if (code.includes('PRESTAMO') || name.includes('PRÉSTAMO')) {
            return 'fa-credit-card';
        }
        if (code.includes('EMBARGO') || name.includes('EMBARGO')) {
            return 'fa-gavel';
        }
        if (code.includes('FONDO') || name.includes('FONDO')) {
            return 'fa-archive';
        }
        if (code.includes('ALIMENTACION') || name.includes('ALIMENTACIÓN')) {
            return 'fa-cutlery';
        }

        // Iconos por defecto
        if (code.includes('DEV') || code.includes('BASIC')) {
            return 'fa-plus-circle';
        }
        if (code.includes('DED')) {
            return 'fa-minus-circle';
        }

        return 'fa-circle';
    }

    async onViewCategoryLines(categoryCode, categoryName) {
        if (this.props.onAction) {
            const params = {
                category_code: categoryCode,
                category_name: categoryName
            };

            // Agregar period_id o fechas según lo disponible
            if (this.props.period?.id) {
                params.period_id = this.props.period.id;
            }

            // Agregar fechas si están disponibles en el período
            if (this.props.period?.date_from) {
                params.date_from = this.props.period.date_from;
            }
            if (this.props.period?.date_to) {
                params.date_to = this.props.period.date_to;
            }

            await this.props.onAction('view_payslip_lines_by_category', params);
        }
    }

    async onViewDetails() {
        if (this.props.onAction) {
            const params = {};

            // Agregar period_id o fechas según lo disponible
            if (this.props.period?.id) {
                params.period_id = this.props.period.id;
            }

            // Agregar fechas si están disponibles
            if (this.props.period?.date_from) {
                params.date_from = this.props.period.date_from;
            }
            if (this.props.period?.date_to) {
                params.date_to = this.props.period.date_to;
            }

            await this.props.onAction('view_payslips', params);
        }
    }
}
