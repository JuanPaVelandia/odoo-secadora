/** @odoo-module **/

import { Component, useRef, onMounted, onPatched } from "@odoo/owl";
import { loadJS } from "@web/core/assets";

export class SummaryHeroCard extends Component {
    static template = "lavish_hr_payroll.SummaryHeroCard";
    static props = {
        company: Object,
        period: Object,
        kpis: Object,
        trendData: Object,
    };

    setup() {
        this.chartRef = useRef("chartCanvas");
        this.chart = null;

        onMounted(() => this.renderChart());
        onPatched(() => this.updateChart());
    }

    get company() {
        return this.props.company || {};
    }

    get hasLogo() {
        return !!this.company.logo_url;
    }

    get periodName() {
        return this.props.period?.name || "Periodo actual";
    }

    get trendLabels() {
        return this.props.trendData?.labels || [];
    }

    get trendValues() {
        return this.props.trendData?.datasets?.[0]?.data || [];
    }

    get hasTrend() {
        return this.trendValues.some((value) => (Number(value) || 0) > 0);
    }

    get trendTotal() {
        return this.props.trendData?.formatted_current || "$0";
    }

    get trendPrev() {
        return this.props.trendData?.formatted_prev || "$0";
    }

    get trendChangeValue() {
        if (this.props.trendData?.change === undefined || this.props.trendData?.change === null) {
            return null;
        }
        return Number(this.props.trendData.change) || 0;
    }

    get trendChange() {
        const change = this.trendChangeValue;
        if (change === null) {
            return "0.0";
        }
        return change.toFixed(1);
    }

    get trendChangeClass() {
        const change = this.trendChangeValue;
        if (change === null) {
            return "text-muted";
        }
        return change >= 0 ? "text-success" : "text-danger";
    }

    get trendChangeIcon() {
        const change = this.trendChangeValue;
        if (change === null) {
            return "fa-minus";
        }
        return change >= 0 ? "fa-arrow-up" : "fa-arrow-down";
    }

    get totalEmployees() {
        return this.props.kpis?.total_employees?.value || 0;
    }

    get totalPayslips() {
        return this.props.kpis?.payslips_month?.count || 0;
    }

    get totalDevengado() {
        return this.props.kpis?.total_devengado?.formatted || "$0";
    }

    get totalNeto() {
        return this.props.kpis?.payslips_month?.formatted || "$0";
    }

    async renderChart() {
        await loadJS("/web/static/lib/Chart/Chart.js");

        const canvas = this.chartRef.el;
        if (!canvas) return;

        const ctx = canvas.getContext("2d");
        const gradient = ctx.createLinearGradient(0, 0, 0, 180);
        gradient.addColorStop(0, "rgba(37, 99, 235, 0.35)");
        gradient.addColorStop(1, "rgba(37, 99, 235, 0.02)");

        this.chart = new Chart(ctx, {
            type: "line",
            data: {
                labels: this.trendLabels,
                datasets: [
                    {
                        label: "Nomina neta",
                        data: this.trendValues,
                        borderColor: "#2563eb",
                        backgroundColor: gradient,
                        fill: true,
                        tension: 0.35,
                        pointRadius: 3,
                        pointBackgroundColor: "#2563eb",
                        pointBorderColor: "#ffffff",
                        pointBorderWidth: 1.5,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false,
                    },
                    tooltip: {
                        callbacks: {
                            label: (context) => {
                                const value = context.parsed?.y || 0;
                                return `${context.label}: ${value.toLocaleString("es-CO", { maximumFractionDigits: 0 })}`;
                            },
                        },
                    },
                },
                scales: {
                    x: {
                        grid: {
                            display: false,
                        },
                        ticks: {
                            font: {
                                size: 10,
                            },
                        },
                    },
                    y: {
                        grid: {
                            color: "rgba(15, 23, 42, 0.08)",
                        },
                        ticks: {
                            callback: (value) => value.toLocaleString("es-CO"),
                            font: {
                                size: 10,
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

        this.chart.data.labels = this.trendLabels;
        this.chart.data.datasets[0].data = this.trendValues;
        this.chart.update();
    }
}
