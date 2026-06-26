/** @odoo-module **/

import { Component, useRef, onMounted, onPatched } from "@odoo/owl";
import { loadJS } from "@web/core/assets";

export class AccidentsTrendChart extends Component {
    static template = "lavish_hr_payroll.AccidentsTrendChart";
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

    get datasets() {
        return this.props.chartData?.datasets || [];
    }

    get accidentsValues() {
        return this.datasets?.[0]?.data || [];
    }

    get incidentsValues() {
        return this.datasets?.[1]?.data || [];
    }

    get hasData() {
        return [...this.accidentsValues, ...this.incidentsValues].some(
            (value) => (Number(value) || 0) > 0
        );
    }

    get accidentsTotal() {
        return this.accidentsValues.reduce((sum, value) => sum + (Number(value) || 0), 0);
    }

    get incidentsTotal() {
        return this.incidentsValues.reduce((sum, value) => sum + (Number(value) || 0), 0);
    }

    formatNumber(value) {
        return (Number(value) || 0).toLocaleString("es-CO", {
            maximumFractionDigits: 0,
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
                        label: this.datasets?.[0]?.label || "Accidentes",
                        data: this.accidentsValues,
                        type: "bar",
                        backgroundColor: "rgba(244, 162, 97, 0.7)",
                        borderColor: "#f4a261",
                        borderWidth: 1,
                        borderRadius: 6,
                        maxBarThickness: 24,
                    },
                    {
                        label: this.datasets?.[1]?.label || "Incidentes",
                        data: this.incidentsValues,
                        type: "line",
                        borderColor: "#2a9d8f",
                        backgroundColor: "rgba(42, 157, 143, 0.15)",
                        tension: 0.3,
                        fill: true,
                        pointRadius: 3,
                        pointBackgroundColor: "#2a9d8f",
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: "bottom",
                    },
                },
                interaction: {
                    mode: "index",
                    intersect: false,
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            precision: 0,
                            font: {
                                size: 11,
                            },
                        },
                        grid: {
                            color: "rgba(15, 23, 42, 0.08)",
                        },
                    },
                    x: {
                        ticks: {
                            font: {
                                size: 11,
                            },
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
        this.chart.data.datasets[0].data = this.accidentsValues;
        this.chart.data.datasets[1].data = this.incidentsValues;
        this.chart.update();
    }
}
