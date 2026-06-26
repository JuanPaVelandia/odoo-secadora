/** @odoo-module **/

import { Component, useRef, onMounted, onPatched } from "@odoo/owl";
import { loadJS } from "@web/core/assets";

export class AlertsBreakdownChart extends Component {
    static template = "lavish_hr_payroll.AlertsBreakdownChart";
    static props = {
        counts: Object,
        period: Object,
    };

    setup() {
        this.chartRef = useRef("chartCanvas");
        this.chart = null;

        onMounted(() => this.renderChart());
        onPatched(() => this.updateChart());
    }

    get labels() {
        return ["Sin SS", "Sin nomina", "Sin liquidacion"];
    }

    get values() {
        return [
            this.props.counts?.without_ss || 0,
            this.props.counts?.without_payslip || 0,
            this.props.counts?.without_settlement || 0,
        ];
    }

    get hasData() {
        return this.values.some((value) => (Number(value) || 0) > 0);
    }

    get total() {
        return this.values.reduce((sum, value) => sum + (Number(value) || 0), 0);
    }

    async renderChart() {
        await loadJS("/web/static/lib/Chart/Chart.js");

        const canvas = this.chartRef.el;
        if (!canvas) return;

        const ctx = canvas.getContext("2d");
        this.chart = new Chart(ctx, {
            type: "bar",
            data: {
                labels: this.labels,
                datasets: [
                    {
                        label: "Alertas",
                        data: this.values,
                        backgroundColor: [
                            "rgba(220, 53, 69, 0.7)",
                            "rgba(255, 193, 7, 0.7)",
                            "rgba(25, 135, 84, 0.7)",
                        ],
                        borderColor: ["#dc3545", "#ffc107", "#198754"],
                        borderWidth: 1,
                        borderRadius: 8,
                        maxBarThickness: 32,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                indexAxis: "y",
                plugins: {
                    legend: {
                        display: false,
                    },
                    tooltip: {
                        callbacks: {
                            label: (context) => {
                                const value = context.parsed?.x || 0;
                                return `${context.label}: ${value}`;
                            },
                        },
                    },
                },
                scales: {
                    x: {
                        beginAtZero: true,
                        grid: {
                            color: "rgba(15, 23, 42, 0.08)",
                        },
                        ticks: {
                            precision: 0,
                        },
                    },
                    y: {
                        grid: {
                            display: false,
                        },
                        ticks: {
                            font: {
                                size: 11,
                            },
                        },
                    },
                },
            },
        });
    }

    updateChart() {
        if (!this.chart) {
            this.renderChart();
            return;
        }

        this.chart.data.labels = this.labels;
        this.chart.data.datasets[0].data = this.values;
        this.chart.update();
    }
}
