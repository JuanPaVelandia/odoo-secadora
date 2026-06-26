/** @odoo-module **/

import { Component, useRef, onMounted, onPatched, useState } from "@odoo/owl";
import { loadJS } from "@web/core/assets";

export class SocialSecurityChart extends Component {
    static template = "lavish_hr_payroll.SocialSecurityChart";
    static props = {
        socialSecurity: Object,
        period: Object,
    };

    setup() {
        this.chartRef = useRef("chartCanvas");
        this.chart = null;

        // Cargar estado guardado
        const savedState = this._loadState();

        this.state = useState({
            collapsed: savedState.collapsed || false
        });

        onMounted(() => this.renderChart());
        onPatched(() => this.updateChart());
    }

    _loadState() {
        try {
            const saved = localStorage.getItem('social_security_chart_state');
            return saved ? JSON.parse(saved) : {};
        } catch (e) {
            console.error('Error loading social security chart state:', e);
            return {};
        }
    }

    _saveState() {
        try {
            const stateToSave = {
                collapsed: this.state.collapsed,
            };
            localStorage.setItem('social_security_chart_state', JSON.stringify(stateToSave));
        } catch (e) {
            console.error('Error saving social security chart state:', e);
        }
    }

    toggleCollapse() {
        this.state.collapsed = !this.state.collapsed;
        this._saveState();
    }

    async renderChart() {
        await loadJS("/web/static/lib/Chart/Chart.js");

        const canvas = this.chartRef.el;
        if (!canvas) return;

        const ctx = canvas.getContext("2d");
        const chartData = this.props.socialSecurity.chart_data || {};

        this.chart = new Chart(ctx, {
            type: "doughnut",
            data: {
                labels: chartData.labels || [],
                datasets: [{
                    data: chartData.values || [],
                    backgroundColor: [
                        '#0dcaf0', // EPS - cyan
                        '#198754', // AFP - green
                        '#ffc107', // ARL - yellow
                        '#dc3545', // CCF - red
                    ],
                    borderWidth: 2,
                    borderColor: '#fff',
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            padding: 15,
                            font: {
                                size: 12,
                            },
                        },
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const label = context.label || '';
                                const value = context.parsed || 0;
                                const pct = chartData.percentages?.[context.dataIndex] || 0;
                                return `${label}: $${value.toLocaleString('es-CO', {maximumFractionDigits: 0})} (${pct}%)`;
                            }
                        }
                    }
                },
            },
        });
    }

    updateChart() {
        if (!this.chart) {
            this.renderChart();
            return;
        }

        const chartData = this.props.socialSecurity.chart_data || {};
        this.chart.data.labels = chartData.labels || [];
        this.chart.data.datasets[0].data = chartData.values || [];
        this.chart.update();
    }

    get hasData() {
        return this.props.socialSecurity.exists &&
               this.props.socialSecurity.chart_data?.values?.some(v => v > 0);
    }

    get detailByEntity() {
        return this.props.socialSecurity.detail_by_entity || [];
    }
}
