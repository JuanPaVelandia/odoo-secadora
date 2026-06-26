/** @odoo-module **/
/**
 * Componente generico para cards del dashboard.
 * Usa slots de OWL para contenido flexible.
 * Elimina duplicacion de header/body/footer en multiples componentes.
 */

import { Component, useState } from "@odoo/owl";
import { getLottieIcon, getFaIcon } from "../../../constants/payroll_icons";

export class DashboardCard extends Component {
    static template = "lavish_hr_payroll.SharedDashboardCard";
    static props = {
        title: String,
        icon: { type: String, optional: true },  // FontAwesome icon class
        lottieIcon: { type: String, optional: true },  // Lottie icon key
        color: { type: String, optional: true },  // Header color theme
        fullscreenEnabled: { type: Boolean, optional: true },
        loading: { type: Boolean, optional: true },
        empty: { type: Boolean, optional: true },
        emptyMessage: { type: String, optional: true },
        onAction: { type: Function, optional: true },
        slots: { type: Object, optional: true },
    };
    static defaultProps = {
        color: 'primary',
        fullscreenEnabled: false,
        loading: false,
        empty: false,
        emptyMessage: 'No hay datos disponibles',
    };

    setup() {
        this.state = useState({
            isFullscreen: false,
        });
    }

    get iconClass() {
        if (this.props.icon) {
            return `fa ${this.props.icon}`;
        }
        return `fa ${getFaIcon('default')}`;
    }

    get lottieIconPath() {
        if (this.props.lottieIcon) {
            return getLottieIcon(this.props.lottieIcon);
        }
        return null;
    }

    get headerClass() {
        const base = 'card-header d-flex justify-content-between align-items-center';
        if (this.state.isFullscreen) {
            return `modal-header bg-${this.props.color} text-white`;
        }
        return base;
    }

    get bodyClass() {
        if (this.state.isFullscreen) {
            return 'modal-body';
        }
        return 'card-body';
    }

    get cardClass() {
        let cls = 'dashboard-card card h-100';
        if (this.props.loading) {
            cls += ' dashboard-card--loading';
        }
        if (this.props.empty) {
            cls += ' dashboard-card--empty';
        }
        return cls;
    }

    get hasHeader() {
        return !!this.props.title;
    }

    get hasFooter() {
        return !!this.props.slots?.footer;
    }

    get showContent() {
        return !this.props.loading && !this.props.empty;
    }

    toggleFullscreen() {
        this.state.isFullscreen = !this.state.isFullscreen;
    }

    async onActionClick(actionName, params = {}) {
        if (this.props.onAction) {
            await this.props.onAction(actionName, params);
        }
    }
}
