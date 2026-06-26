/** @odoo-module **/
/**
 * Componente Grid de Lineas de Nomina - Vista Horizontal Pivot
 * Filas = Empleados, Columnas = Conceptos de Nomina
 */

import { Component, useState, onWillStart, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export class PayslipLineGrid extends Component {
    static template = "lavish_hr_payroll.PayslipLineGrid";
    static props = {
        "*": true,
    };

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");

        // Estados disponibles para filtrar
        this.payslipStates = [
            { value: 'draft', label: 'Borrador', color: 'secondary', icon: 'fa-pencil' },
            { value: 'verify', label: 'En Espera', color: 'warning', icon: 'fa-clock-o' },
            { value: 'done', label: 'Hecho', color: 'success', icon: 'fa-check' },
            { value: 'paid', label: 'Pagado', color: 'info', icon: 'fa-money' },
            { value: 'cancel', label: 'Cancelado', color: 'danger', icon: 'fa-times' },
        ];

        this.state = useState({
            loading: true,
            // Datos del grid horizontal
            employees: [],      // Lista de empleados (filas)
            concepts: [],       // Lista de conceptos/reglas (columnas)
            gridData: {},       // Datos: {employeeId: {conceptCode: value}}
            totals: {
                byEmployee: {},  // Totales por empleado
                byConcept: {},   // Totales por concepto
                general: 0,
            },
            // Filtros
            filters: {
                payslipRunId: null,
                departmentId: null,
                selectedStates: ['verify', 'done', 'paid'],
                searchText: "",
            },
            // Selectores
            payslipRuns: [],
            departments: [],
            // Opciones
            showZeroColumns: true,
            fixedColumns: true,
            showRuleName: false, // false = codigo, true = nombre
        });

        onWillStart(async () => {
            await this.loadInitialData();
        });

        onMounted(() => {
            this.state.loading = false;
        });
    }

    async loadInitialData() {
        try {
            const [payslipRuns, departments] = await Promise.all([
                this.orm.searchRead(
                    "hr.payslip.run",
                    [["state", "!=", "draft"]],
                    ["id", "name", "date_start", "date_end", "state"],
                    { order: "date_start desc", limit: 50 }
                ),
                this.orm.searchRead(
                    "hr.department",
                    [],
                    ["id", "name"],
                    { order: "name" }
                ),
            ]);

            this.state.payslipRuns = payslipRuns;
            this.state.departments = departments;

            if (payslipRuns.length > 0) {
                this.state.filters.payslipRunId = payslipRuns[0].id;
                await this.loadGridData();
            }
        } catch (error) {
            console.error("Error loading initial data:", error);
            this.notification.add(_t("Error al cargar datos"), { type: "danger" });
        }
    }

    async loadGridData() {
        if (!this.state.filters.payslipRunId) return;

        this.state.loading = true;
        try {
            // Construir dominio
            const domain = this.buildDomain();

            // Obtener payslips
            const payslips = await this.orm.searchRead(
                "hr.payslip",
                domain,
                ["id", "employee_id", "state"],
                { order: "employee_id", limit: 500 }
            );

            if (payslips.length === 0) {
                this.state.employees = [];
                this.state.concepts = [];
                this.state.gridData = {};
                this.state.loading = false;
                return;
            }

            const payslipIds = payslips.map(p => p.id);
            const employeeIds = [...new Set(payslips.map(p => p.employee_id[0]))];

            // Obtener empleados
            const employeesData = await this.orm.searchRead(
                "hr.employee",
                [["id", "in", employeeIds]],
                ["id", "name", "identification_id", "department_id", "job_id"],
                { order: "name" }
            );

            // Obtener lineas de nomina
            const lines = await this.orm.searchRead(
                "hr.payslip.line",
                [["slip_id", "in", payslipIds]],
                ["slip_id", "code", "name", "category_id", "total", "sequence"],
                { order: "sequence" }
            );

            // Mapear payslip -> employee
            const payslipToEmployee = {};
            payslips.forEach(p => {
                payslipToEmployee[p.id] = p.employee_id[0];
            });

            // Construir lista de conceptos unicos (columnas)
            const conceptsMap = {};
            lines.forEach(line => {
                if (!conceptsMap[line.code]) {
                    conceptsMap[line.code] = {
                        code: line.code,
                        name: line.name,
                        category: line.category_id ? line.category_id[1] : '',
                        sequence: line.sequence,
                    };
                }
            });

            // Ordenar conceptos por secuencia
            const concepts = Object.values(conceptsMap).sort((a, b) => a.sequence - b.sequence);

            // Construir grid de datos
            const gridData = {};
            const totalsByEmployee = {};
            const totalsByConcept = {};

            employeesData.forEach(emp => {
                gridData[emp.id] = {};
                totalsByEmployee[emp.id] = 0;
            });

            concepts.forEach(c => {
                totalsByConcept[c.code] = 0;
            });

            lines.forEach(line => {
                const empId = payslipToEmployee[line.slip_id[0]];
                if (empId && gridData[empId]) {
                    gridData[empId][line.code] = (gridData[empId][line.code] || 0) + line.total;
                    totalsByEmployee[empId] = (totalsByEmployee[empId] || 0) + line.total;
                    totalsByConcept[line.code] = (totalsByConcept[line.code] || 0) + line.total;
                }
            });

            // Filtrar empleados por busqueda
            let filteredEmployees = employeesData;
            if (this.state.filters.searchText) {
                const search = this.state.filters.searchText.toLowerCase();
                filteredEmployees = employeesData.filter(emp =>
                    emp.name.toLowerCase().includes(search) ||
                    (emp.identification_id || '').toLowerCase().includes(search)
                );
            }

            this.state.employees = filteredEmployees;
            this.state.concepts = concepts;
            this.state.gridData = gridData;
            this.state.totals = {
                byEmployee: totalsByEmployee,
                byConcept: totalsByConcept,
                general: Object.values(totalsByEmployee).reduce((a, b) => a + b, 0),
            };

        } catch (error) {
            console.error("Error loading grid data:", error);
            this.notification.add(_t("Error al cargar grid"), { type: "danger" });
        }
        this.state.loading = false;
    }

    buildDomain() {
        const domain = [];

        const selectedStates = this.state.filters.selectedStates;
        if (selectedStates && selectedStates.length > 0) {
            domain.push(["state", "in", selectedStates]);
        } else {
            domain.push(["state", "=", false]);
        }

        if (this.state.filters.payslipRunId) {
            domain.push(["payslip_run_id", "=", this.state.filters.payslipRunId]);
        }
        if (this.state.filters.departmentId) {
            domain.push(["employee_id.department_id", "=", this.state.filters.departmentId]);
        }

        return domain;
    }

    // Event handlers
    onPayslipRunChange(ev) {
        this.state.filters.payslipRunId = parseInt(ev.target.value) || null;
        this.loadGridData();
    }

    onDepartmentChange(ev) {
        this.state.filters.departmentId = parseInt(ev.target.value) || null;
        this.loadGridData();
    }

    onSearchChange(ev) {
        this.state.filters.searchText = ev.target.value;
        clearTimeout(this._searchTimeout);
        this._searchTimeout = setTimeout(() => {
            this.loadGridData();
        }, 400);
    }

    onShowZeroChange(ev) {
        // Siempre mostrar todas las columnas/conceptos, incluso en cero.
        this.state.showZeroColumns = true;
        this.loadGridData();
    }

    toggleRuleDisplay() {
        this.state.showRuleName = !this.state.showRuleName;
    }

    toggleState(stateValue) {
        const idx = this.state.filters.selectedStates.indexOf(stateValue);
        if (idx > -1) {
            this.state.filters.selectedStates.splice(idx, 1);
        } else {
            this.state.filters.selectedStates.push(stateValue);
        }
        this.loadGridData();
    }

    selectAllStates() {
        this.state.filters.selectedStates = this.payslipStates.map(s => s.value);
        this.loadGridData();
    }

    clearAllStates() {
        this.state.filters.selectedStates = [];
        this.loadGridData();
    }

    isStateSelected(stateValue) {
        return this.state.filters.selectedStates.includes(stateValue);
    }

    // Navegacion
    openEmployee(employeeId) {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            name: _t("Empleado"),
            res_model: "hr.employee",
            res_id: employeeId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    // Formateo
    formatCurrency(value) {
        if (value === undefined || value === null) return '-';
        return new Intl.NumberFormat("es-CO", {
            style: "currency",
            currency: "COP",
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        }).format(value);
    }

    formatNumber(value) {
        if (value === undefined || value === null) return '-';
        return new Intl.NumberFormat("es-CO", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        }).format(value);
    }

    getCellValue(employeeId, conceptCode) {
        const val = this.state.gridData[employeeId]?.[conceptCode];
        return val !== undefined ? val : null;
    }

    getCellClass(value) {
        if (value === null || value === undefined) return 'text-muted';
        if (value > 0) return 'value-positive';
        if (value < 0) return 'value-negative';
        return '';
    }

    // Exportar
    async exportExcel() {
        if (this.state.employees.length === 0) {
            this.notification.add(_t("No hay datos para exportar"), { type: "warning" });
            return;
        }
        // Construir URL con parametros
        const params = new URLSearchParams({
            payslip_run_id: this.state.filters.payslipRunId || '',
            department_ids: JSON.stringify(this.state.filters.departmentId ? [this.state.filters.departmentId] : []),
            selected_states: JSON.stringify(this.state.filters.selectedStates || []),
            group_by: 'employee',
            show_zero: 'true',
        });
        window.open(`/payroll/grid/excel?${params.toString()}`, '_blank');
    }

    async exportPDF() {
        if (this.state.employees.length === 0) {
            this.notification.add(_t("No hay datos para exportar"), { type: "warning" });
            return;
        }
        // Construir URL con parametros
        const params = new URLSearchParams({
            payslip_run_id: this.state.filters.payslipRunId || '',
            department_ids: JSON.stringify(this.state.filters.departmentId ? [this.state.filters.departmentId] : []),
            selected_states: JSON.stringify(this.state.filters.selectedStates || []),
            group_by: 'employee',
            show_zero: 'true',
        });
        window.open(`/payroll/grid/pdf?${params.toString()}`, '_blank');
    }

    async exportExcelCompiled() {
        if (this.state.employees.length === 0) {
            this.notification.add(_t("No hay datos para exportar"), { type: "warning" });
            return;
        }
        const params = new URLSearchParams({
            payslip_run_id: this.state.filters.payslipRunId || '',
            department_ids: JSON.stringify(this.state.filters.departmentId ? [this.state.filters.departmentId] : []),
            selected_states: JSON.stringify(this.state.filters.selectedStates || []),
        });
        window.open(`/payroll/grid/excel_compiled?${params.toString()}`, '_blank');
    }
}

registry.category("actions").add("payslip_line_grid", PayslipLineGrid);
