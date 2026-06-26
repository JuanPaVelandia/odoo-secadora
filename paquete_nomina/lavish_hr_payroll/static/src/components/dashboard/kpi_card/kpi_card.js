/** @odoo-module **/

import { Component } from "@odoo/owl";

export class KPICard extends Component {
    static template = "lavish_hr_payroll.KPICard";
    static props = {
        title: String,
        value: [String, Number],
        subtitle: { type: String, optional: true },
        icon: String,
        color: String,
        state: { type: String, optional: true },
        onClick: { type: Function, optional: true },
        animatedIcon: { type: String, optional: true },
    };

    get isClickable() {
        return this.props.onClick !== undefined;
    }

    get colorHex() {
        const colors = {
            'primary': '#0d6efd',
            'success': '#198754',
            'info': '#0dcaf0',
            'warning': '#ffc107',
            'danger': '#dc3545',
            'purple': '#6f42c1',
            'pink': '#d63384',
            'secondary': '#6c757d',
        };
        return colors[this.props.color] || colors.primary;
    }

    handleClick() {
        if (this.props.onClick) {
            this.props.onClick();
        }
    }
}
