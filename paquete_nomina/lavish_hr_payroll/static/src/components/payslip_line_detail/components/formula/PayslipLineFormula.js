/** @odoo-module **/

import { Component, useState } from "@odoo/owl";

/**
 * PayslipLineFormula - Vista de fórmula con 2 columnas y tablas
 * Usado para reglas con fórmula, pasos de cálculo y KPIs
 * 
 * Props:
 * - formulaData: Object - Datos de la fórmula y cálculo
 * - ruleConfig: Object - Configuración visual de la regla
 * - formatCurrency: Function - Función para formatear moneda
 * - formatValue: Function - Función para formatear valores
 * - getLeyUrl: Function - Función para obtener URL de ley
 */
export class PayslipLineFormula extends Component {
    static template = "lavish_hr_payroll.PayslipLineFormula";
    static props = {
        formulaData: { type: Object },
        ruleConfig: { type: Object },
        formatCurrency: { type: Function },
        formatValue: { type: Function },
        getLeyUrl: { type: Function },
    };

    // Colores para pasos
    static STEP_COLORS = ['#3B82F6', '#8B5CF6', '#F97316', '#22C55E', '#EC4899', '#14B8A6', '#EF4444'];

    setup() {
        this.state = useState({
            showStepsDetail: true,
            showTables: {},
        });
    }

    get data() {
        return this.props.formulaData || {};
    }

    get kpis() {
        return this.data.kpis || [];
    }

    get pasos() {
        return this.data.pasos || [];
    }

    get tablas() {
        return this.data.tablas || [];
    }

    get hasKpis() {
        return this.kpis.length > 0;
    }

    get hasPasos() {
        return this.pasos.length > 0;
    }

    get hasTablas() {
        return this.tablas.length > 0;
    }

    get hasIndicadores() {
        return this.data.indicadores && this.data.indicadores.length > 0;
    }

    toggleStepsDetail() {
        this.state.showStepsDetail = !this.state.showStepsDetail;
    }

    toggleTable(tableId) {
        this.state.showTables[tableId] = !this.state.showTables[tableId];
    }

    isTableExpanded(tableId) {
        return this.state.showTables[tableId] !== false;
    }

    getStepColor(index) {
        return PayslipLineFormula.STEP_COLORS[index % PayslipLineFormula.STEP_COLORS.length];
    }

    formatPasoValue(paso) {
        if (paso.formato === 'currency') {
            return this.props.formatCurrency(paso.resultado);
        } else if (paso.formato === 'porcentaje' || paso.formato === 'percentage') {
            return `${paso.resultado}%`;
        } else if (paso.formato === 'dias' || paso.formato === 'days') {
            return `${paso.resultado} días`;
        } else if (paso.formato === 'uvt') {
            return `${paso.resultado} UVT`;
        } else if (paso.formato === 'entero' || paso.formato === 'integer') {
            return parseInt(paso.resultado).toLocaleString('es-CO');
        }
        return this.props.formatValue(paso.resultado, paso.formato || 'currency');
    }
}
