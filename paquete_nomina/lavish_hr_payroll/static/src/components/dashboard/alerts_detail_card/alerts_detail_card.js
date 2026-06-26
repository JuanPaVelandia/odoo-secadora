/** @odoo-module **/

import { Component } from "@odoo/owl";

export class AlertsDetailCard extends Component {
    static template = "lavish_hr_payroll.AlertsDetailCard";
    static props = {
        kpis: Object,
        period: Object,
        onAction: Function,
    };

    get sections() {
        return [
            {
                key: "without_ss",
                title: "Sin Seguridad Social",
                subtitle: "Empleados no incluidos en SS",
                icon: "fa-shield",
                color: "danger",
                employees: this.props.kpis?.employees_without_ss?.employees || [],
                employeeIds: this.props.kpis?.employees_without_ss?.employee_ids || [],
                action: "view_employees_without_ss",
            },
            {
                key: "without_payslip",
                title: "Sin Nomina en Periodo",
                subtitle: "Empleados activos sin nomina",
                icon: "fa-file-alt",
                color: "warning",
                employees: this.props.kpis?.employees_without_payslip?.employees || [],
                employeeIds: this.props.kpis?.employees_without_payslip?.employee_ids || [],
                action: "view_employees_without_payslip",
            },
            {
                key: "without_settlement",
                title: "Sin Liquidacion",
                subtitle: "Terminados sin liquidar",
                icon: "fa-exclamation-triangle",
                color: "success",
                employees: this.props.kpis?.employees_without_settlement?.employees || [],
                employeeIds: this.props.kpis?.employees_without_settlement?.employee_ids || [],
                action: "view_employees_without_settlement",
            },
        ];
    }

    getVisibleEmployees(employees) {
        return employees.slice(0, 8);
    }

    getTotalEmployees(employees) {
        return employees.length;
    }

    hasMore(employees) {
        return employees.length > 8;
    }

    async onViewSection(section) {
        if (this.props.onAction && section.employeeIds.length) {
            await this.props.onAction(section.action, { employee_ids: section.employeeIds });
        }
    }
}
