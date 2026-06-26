/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class DisabilityChart extends Component {
    static template = "lavish_hr_payroll.DisabilityChart";

    setup() {
        this.action = useService("action");

        // Cargar estado guardado
        const savedState = this._loadState();

        this.state = useState({
            collapsed: savedState.collapsed || false
        });
    }

    _loadState() {
        try {
            const saved = localStorage.getItem('disability_chart_state');
            return saved ? JSON.parse(saved) : {};
        } catch (e) {
            console.error('Error loading disability chart state:', e);
            return {};
        }
    }

    _saveState() {
        try {
            const stateToSave = {
                collapsed: this.state.collapsed,
            };
            localStorage.setItem('disability_chart_state', JSON.stringify(stateToSave));
        } catch (e) {
            console.error('Error saving disability chart state:', e);
        }
    }

    toggleCollapse() {
        this.state.collapsed = !this.state.collapsed;
        this._saveState();
    }

    get hasData() {
        return this.props.chartData &&
               this.props.chartData.detail &&
               this.props.chartData.detail.length > 0;
    }

    get totalDays() {
        return this.props.chartData?.total_days || 0;
    }

    get totalCases() {
        return this.props.chartData?.total_cases || 0;
    }

    get disabilityItems() {
        if (!this.props.chartData?.detail) return [];
        return this.props.chartData.detail;
    }

    getPercentageDays(days) {
        if (!this.totalDays || this.totalDays === 0) return 0;
        return ((days / this.totalDays) * 100).toFixed(1);
    }

    getPercentageCases(cases) {
        if (!this.totalCases || this.totalCases === 0) return 0;
        return ((cases / this.totalCases) * 100).toFixed(1);
    }

    /**
     * Obtiene el icono de tendencia según la variación
     * @param {Object} item - Item de incapacidad con información de tendencia
     * @returns {Object} { icon: string, color: string, text: string }
     */
    getTrendIcon(item) {
        if (!item.trend || item.trend === 0) {
            return {
                icon: 'fa-minus',
                color: 'text-secondary',
                text: 'Sin variación'
            };
        } else if (item.trend > 0) {
            return {
                icon: 'fa-arrow-up',
                color: 'text-danger',
                text: `+${item.trend}%`
            };
        } else {
            return {
                icon: 'fa-arrow-down',
                color: 'text-success',
                text: `${item.trend}%`
            };
        }
    }

    /**
     * Verifica si hay reglas asociadas al item
     * @param {Object} item - Item de incapacidad
     * @returns {boolean}
     */
    hasRules(item) {
        return item.rules && item.rules.length > 0;
    }

    /**
     * Obtiene las reglas de un item
     * @param {Object} item - Item de incapacidad
     * @returns {Array}
     */
    getRules(item) {
        return item.rules || [];
    }

    async onViewDisability(disabilityType) {
        if (this.props.onAction) {
            const params = { disability_type: disabilityType };

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

            await this.props.onAction('view_disabilities', params);
        }
    }

    async onViewAllDisabilities() {
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

            await this.props.onAction('view_disabilities', params);
        }
    }
}
