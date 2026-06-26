/** @odoo-module **/

import { Component, useRef, onMounted, onPatched } from "@odoo/owl";
import { loadJS } from "@web/core/assets";

export class OvertimeDepartmentChart extends Component {
    static template = "lavish_hr_payroll.OvertimeDepartmentChart";
    static props = {
        chartData: Object,
        period: Object,
    };

    setup() {
        this.chartRef = useRef("chartCanvas");
        this.chart = null;

        onMounted(() => this.renderChart());
        onPatched(() => this.updateChart());
    }

    get labels() {
        return this.props.chartData?.labels || [];
    }

    get values() {
        return this.props.chartData?.datasets?.[0]?.data || [];
    }

    get hasData() {
        return this.values.some((value) => (Number(value) || 0) > 0);
    }

    get totalHours() {
        return this.values.reduce((sum, value) => sum + (Number(value) || 0), 0);
    }

    get totalHoursLabel() {
        return `${this._formatNumber(this.totalHours, 1)} h`;
    }

    _formatNumber(value, maxFractionDigits = 1) {
        return (Number(value) || 0).toLocaleString("es-CO", {
            maximumFractionDigits: maxFractionDigits,
        });
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
                        label: "Horas extras",
                        data: this.values,
                        backgroundColor: "rgba(244, 162, 97, 0.75)",
                        borderColor: "#f4a261",
                        borderWidth: 1,
                        borderRadius: 8,
                        maxBarThickness: 28,
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
                                return `${context.label}: ${this._formatNumber(value, 1)} h`;
                            },
                        },
                    },
                },
                scales: {
                    x: {
                        ticks: {
                            font: {
                                size: 11,
                            },
                        },
                        grid: {
                            color: "rgba(15, 23, 42, 0.08)",
                        },
                    },
                    y: {
                        beginAtZero: true,
                        ticks: {
                            font: {
                                size: 11,
                            },
                            callback: (value) => value,
                        },
                        grid: {
                            display: false,
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
