/** @odoo-module **/

import { Component, useState, onWillStart, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

/**
 * PayslipLiquidationSummary - Widget para resumen estructurado de liquidacion
 *
 * Muestra las lineas de nomina organizadas por categorias:
 * - Devengos (salariales, no salariales, auxilios, comisiones)
 * - Seguridad Social
 * - Deducciones
 * - Prestaciones Sociales (prima, cesantias, vacaciones)
 * - Neto a Pagar
 */
export class PayslipLiquidationSummary extends Component {
    static template = "lavish_hr_payroll.PayslipLiquidationSummary";
    static props = { ...standardFieldProps };

    // Configuracion de categorias
    static CATEGORY_ORDER = {
        'BASIC': 1,
        'DEV_SALARIAL': 2,
        'HEYREC': 3,
        'COMISIONES': 4,
        'AUX': 5,
        'DEV_NO_SALARIAL': 6,
        'TOTALDEV': 7,
        'SSOCIAL': 10,
        'DED': 20,
        'DEDUCCIONES': 21,
        'TOTALDED': 22,
        'NET': 30,
        'PROVISIONES': 40,
        'PRESTACIONES_SOCIALES': 41,
    };

    static CATEGORY_GROUPS = {
        'devengos': {
            name: 'Devengos',
            icon: 'fa-plus-circle',
            color: '#28a745',
            gradient: 'linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%)',
            borderColor: '#28a745',
            codes: ['BASIC', 'DEV_SALARIAL', 'HEYREC', 'COMISIONES', 'AUX', 'DEV_NO_SALARIAL'],
        },
        'subtotal_devengos': {
            name: 'Total Devengos',
            icon: 'fa-check-circle',
            color: '#155724',
            gradient: 'linear-gradient(135deg, #c3e6cb 0%, #a3d3ad 100%)',
            borderColor: '#155724',
            codes: ['TOTALDEV'],
            isTotal: true,
        },
        'seguridad_social': {
            name: 'Seguridad Social',
            icon: 'fa-shield',
            color: '#6f42c1',
            gradient: 'linear-gradient(135deg, #e2d9f3 0%, #d4c5ec 100%)',
            borderColor: '#6f42c1',
            codes: ['SSOCIAL'],
        },
        'deducciones': {
            name: 'Deducciones',
            icon: 'fa-minus-circle',
            color: '#dc3545',
            gradient: 'linear-gradient(135deg, #f8d7da 0%, #f5c6cb 100%)',
            borderColor: '#dc3545',
            codes: ['DED', 'DEDUCCIONES'],
        },
        'subtotal_deducciones': {
            name: 'Total Deducciones',
            icon: 'fa-exclamation-circle',
            color: '#721c24',
            gradient: 'linear-gradient(135deg, #f5c6cb 0%, #e9a4ad 100%)',
            borderColor: '#721c24',
            codes: ['TOTALDED'],
            isTotal: true,
        },
        'neto': {
            name: 'Neto a Pagar',
            icon: 'fa-money',
            color: '#007bff',
            gradient: 'linear-gradient(135deg, #cce5ff 0%, #b3d7ff 100%)',
            borderColor: '#007bff',
            codes: ['NET'],
            isTotal: true,
        },
        'provisiones': {
            name: 'Provisiones y Prestaciones',
            icon: 'fa-university',
            color: '#fd7e14',
            gradient: 'linear-gradient(135deg, #ffe5d0 0%, #ffd9b8 100%)',
            borderColor: '#fd7e14',
            codes: ['PROVISIONES', 'PRESTACIONES_SOCIALES'],
        },
    };

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            isLoading: true,
            lines: [],
            groupedLines: {},
            totals: {
                devengos: 0,
                deducciones: 0,
                seguridad_social: 0,
                neto: 0,
                provisiones: 0,
            },
            expandedGroups: {
                devengos: true,
                seguridad_social: true,
                deducciones: true,
                neto: true,
                provisiones: true,
            },
            viewMode: 'cards', // 'cards' o 'table'
            showZeroLines: false,
        });

        onWillStart(async () => {
            await this.loadData();
        });
    }

    get payslipId() {
        // Obtener el ID del payslip del record actual
        return this.props.record?.data?.id || this.props.record?.resId;
    }

    async loadData() {
        this.state.isLoading = true;
        try {
            const payslipId = this.payslipId;
            if (!payslipId) {
                this.state.isLoading = false;
                return;
            }

            // Obtener las lineas de nomina
            const lines = await this.orm.searchRead(
                'hr.payslip.line',
                [['slip_id', '=', payslipId]],
                ['id', 'name', 'code', 'category_id', 'quantity', 'rate', 'amount', 'total', 'sequence'],
                { order: 'sequence, id' }
            );

            this.state.lines = lines;
            this._groupLines(lines);
            this._calculateTotals(lines);
        } catch (error) {
            console.error('Error cargando datos de liquidacion:', error);
        }
        this.state.isLoading = false;
    }

    _groupLines(lines) {
        const grouped = {};

        // Inicializar grupos
        for (const [key, config] of Object.entries(PayslipLiquidationSummary.CATEGORY_GROUPS)) {
            grouped[key] = {
                ...config,
                lines: [],
                subtotal: 0,
            };
        }

        for (const line of lines) {
            const catCode = line.category_id ? line.category_id[1]?.split(' ')[0] : '';
            const groupKey = this._getCategoryGroup(catCode);

            if (!this.state.showZeroLines && !line.total) {
                continue;
            }

            if (grouped[groupKey]) {
                grouped[groupKey].lines.push({
                    ...line,
                    categoryCode: catCode,
                    order: PayslipLiquidationSummary.CATEGORY_ORDER[catCode] || 99,
                });
                grouped[groupKey].subtotal += line.total || 0;
            }
        }

        // Ordenar lineas dentro de cada grupo
        for (const group of Object.values(grouped)) {
            group.lines.sort((a, b) => a.order - b.order || a.sequence - b.sequence);
        }

        this.state.groupedLines = grouped;
    }

    _getCategoryGroup(catCode) {
        for (const [groupKey, config] of Object.entries(PayslipLiquidationSummary.CATEGORY_GROUPS)) {
            if (config.codes.some(code => catCode.startsWith(code) || catCode === code)) {
                return groupKey;
            }
        }
        return 'devengos'; // Default
    }

    _calculateTotals(lines) {
        const totals = {
            devengos: 0,
            deducciones: 0,
            seguridad_social: 0,
            neto: 0,
            provisiones: 0,
        };

        for (const line of lines) {
            const catCode = line.category_id ? line.category_id[1]?.split(' ')[0] : '';

            if (catCode === 'TOTALDEV') {
                totals.devengos = line.total || 0;
            } else if (catCode === 'TOTALDED') {
                totals.deducciones = Math.abs(line.total || 0);
            } else if (catCode === 'NET') {
                totals.neto = line.total || 0;
            } else if (catCode.startsWith('SSOCIAL') || catCode === 'SSOCIAL') {
                totals.seguridad_social += Math.abs(line.total || 0);
            } else if (catCode.startsWith('PROV') || catCode.startsWith('PRV') ||
                       catCode.startsWith('PRIMA') || catCode.startsWith('CES') ||
                       catCode.startsWith('VAC') || catCode.startsWith('INTCES')) {
                totals.provisiones += line.total || 0;
            }
        }

        this.state.totals = totals;
    }

    formatCurrency(value) {
        if (value === null || value === undefined) return '$0';
        const absValue = Math.abs(value);
        return new Intl.NumberFormat('es-CO', {
            style: 'currency',
            currency: 'COP',
            minimumFractionDigits: 0,
            maximumFractionDigits: 0,
        }).format(absValue);
    }

    formatNumber(value, decimals = 2) {
        if (value === null || value === undefined) return '';
        if (value === 1) return ''; // No mostrar cantidad si es 1
        return new Intl.NumberFormat('es-CO', {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals,
        }).format(value);
    }

    toggleGroup(groupKey) {
        this.state.expandedGroups[groupKey] = !this.state.expandedGroups[groupKey];
    }

    toggleViewMode() {
        this.state.viewMode = this.state.viewMode === 'cards' ? 'table' : 'cards';
    }

    toggleShowZero() {
        this.state.showZeroLines = !this.state.showZeroLines;
        this._groupLines(this.state.lines);
    }

    get hasLines() {
        return this.state.lines.length > 0;
    }

    get groupEntries() {
        return Object.entries(this.state.groupedLines).filter(([key, group]) => group.lines.length > 0);
    }

    // Calcular indicadores KPI
    get kpiData() {
        return [
            {
                label: 'Total Devengos',
                value: this.state.totals.devengos,
                icon: 'fa-plus-circle',
                color: '#28a745',
                bgColor: '#d4edda',
            },
            {
                label: 'Seguridad Social',
                value: this.state.totals.seguridad_social,
                icon: 'fa-shield',
                color: '#6f42c1',
                bgColor: '#e2d9f3',
            },
            {
                label: 'Total Deducciones',
                value: this.state.totals.deducciones,
                icon: 'fa-minus-circle',
                color: '#dc3545',
                bgColor: '#f8d7da',
            },
            {
                label: 'Neto a Pagar',
                value: this.state.totals.neto,
                icon: 'fa-money',
                color: '#007bff',
                bgColor: '#cce5ff',
                isMain: true,
            },
        ];
    }

    // Para exportar como PDF (usa el controlador existente)
    async exportPdf() {
        const payslipId = this.payslipId;
        if (!payslipId) return;

        window.open(`/payroll/grid/pdf?payslip_id=${payslipId}`, '_blank');
    }
}

// Registrar como widget de campo
registry.category("fields").add("payslip_liquidation_summary", {
    component: PayslipLiquidationSummary,
    supportedTypes: ["one2many", "many2many"],
    extractProps: (fieldInfo) => ({
        fieldName: fieldInfo.name,
    }),
});
