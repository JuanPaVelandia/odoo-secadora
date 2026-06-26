/** @odoo-module **/

import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class NewEmployeesCard extends Component {
    static template = "lavish_hr_payroll.NewEmployeesCard";

    setup() {
        this.action = useService("action");
    }

    get hasData() {
        return this.props.employeesData &&
               this.props.employeesData.employees &&
               this.props.employeesData.employees.length > 0;
    }

    get totalEmployees() {
        return this.props.employeesData?.total || 0;
    }

    get employees() {
        if (!this.props.employeesData?.employees) return [];
        // Return only first 5 employees for display
        return this.props.employeesData.employees.slice(0, 5);
    }

    getDaysSinceHiring(dateStr) {
        if (!dateStr) return null;
        const hireDate = new Date(dateStr);
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        hireDate.setHours(0, 0, 0, 0);
        const diffTime = today - hireDate;
        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
        return diffDays;
    }

    getHiringText(dateStr) {
        const days = this.getDaysSinceHiring(dateStr);
        if (days === null) return '';
        if (days === 0) return 'Hoy';
        if (days === 1) return 'Hace 1 día';
        if (days <= 7) return `Hace ${days} días`;
        if (days <= 30) return `Hace ${Math.floor(days / 7)} semana(s)`;
        return `Hace ${Math.floor(days / 30)} mes(es)`;
    }

    async onViewAllEmployees() {
        if (this.props.onAction) {
            const params = {};
            if (this.props.period?.id) {
                params.period_id = this.props.period.id;
            }
            if (this.props.period?.date_from) {
                params.date_from = this.props.period.date_from;
            }
            if (this.props.period?.date_to) {
                params.date_to = this.props.period.date_to;
            }
            await this.props.onAction('view_new_employees', params);
        }
    }

    async onViewEmployee(employeeId) {
        if (this.props.onAction) {
            await this.props.onAction('view_employees', {
                employee_id: employeeId
            });
        }
    }
}
