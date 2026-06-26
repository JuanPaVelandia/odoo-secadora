/** @odoo-module **/

import { Component, useRef, onMounted, onPatched } from "@odoo/owl";
import { loadJS } from "@web/core/assets";

export class AbsencesByTypeChart extends Component {
    static template = "lavish_hr_payroll.AbsencesByTypeChart";
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

    get totalDays() {
        return this.values.reduce((sum, value) => sum + (Number(value) || 0), 0);
    }

    get totalDaysLabel() {
        return `${this.formatNumber(this.totalDays, 1)} dias`;
    }

    get hasData() {
        return this.values.some((value) => (Number(value) || 0) > 0);
    }

    get summaryItems() {
        const items = this.labels.map((label, index) => ({
            label,
            value: Number(this.values[index]) || 0,
        }));
        return items.sort((a, b) => b.value - a.value).slice(0, 5);
    }

    getColorPalette() {
        return [
            "#f4a261",
            "#e76f51",
            "#2a9d8f",
            "#e9c46a",
            "#457b9d",
            "#a8dadc",
            "#f1faee",
            "#adb5bd",
        ];
    }

    getColors() {
        const palette = this.getColorPalette();
        return this.labels.map((_, index) => palette[index % palette.length]);
    }

    getPercentage(value) {
        if (!this.totalDays) return 0;
        return ((value / this.totalDays) * 100).toFixed(1);
    }

    formatNumber(value, maxFractionDigits = 1) {
        return (Number(value) || 0).toLocaleString("es-CO", {
            maximumFractionDigits: maxFractionDigits,
        });
    }

    async renderChart() {
        await loadJS("/web/static/lib/Chart/Chart.js");

        const canvas = this.chartRef.el;
        if (!canvas) return;

        const ctx = canvas.getContext("2d");
        const centerTextPlugin = {
            id: "centerText",
            afterDraw: (chart) => {
                const { ctx, chartArea } = chart;
                if (!chartArea) return;

                const { left, right, top, bottom } = chartArea;
                const centerX = (left + right) / 2;
                const centerY = (top + bottom) / 2;
                const mainText = chart.options.plugins?.centerText?.text || "";
                const subText = chart.options.plugins?.centerText?.subtext || "";

                ctx.save();
                ctx.textAlign = "center";
                ctx.textBaseline = "middle";
                ctx.fillStyle = "#1f2937";
                ctx.font = "600 16px sans-serif";
                ctx.fillText(mainText, centerX, centerY - 6);
                ctx.fillStyle = "#6b7280";
                ctx.font = "12px sans-serif";
                ctx.fillText(subText, centerX, centerY + 12);
                ctx.restore();
            },
        };

        this.chart = new Chart(ctx, {
            type: "doughnut",
            data: {
                labels: this.labels,
                datasets: [
                    {
                        data: this.values,
                        backgroundColor: this.getColors(),
                        borderColor: "#ffffff",
                        borderWidth: 2,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: "65%",
                plugins: {
                    legend: {
                        position: "bottom",
                        labels: {
                            padding: 12,
                            font: {
                                size: 11,
                            },
                        },
                    },
                    tooltip: {
                        callbacks: {
                            label: (context) => {
                                const value = context.parsed || 0;
                                const pct = this.getPercentage(value);
                                return `${context.label}: ${this.formatNumber(value, 1)} dias (${pct}%)`;
                            },
                        },
                    },
                    centerText: {
                        text: this.totalDaysLabel,
                        subtext: "Total dias",
                    },
                },
            },
            plugins: [centerTextPlugin],
        });
    }

    updateChart() {
        if (!this.chart) {
            this.renderChart();
            return;
        }

        this.chart.data.labels = this.labels;
        this.chart.data.datasets[0].data = this.values;
        this.chart.data.datasets[0].backgroundColor = this.getColors();
        if (this.chart.options?.plugins?.centerText) {
            this.chart.options.plugins.centerText.text = this.totalDaysLabel;
        }
        this.chart.update();
    }
}
