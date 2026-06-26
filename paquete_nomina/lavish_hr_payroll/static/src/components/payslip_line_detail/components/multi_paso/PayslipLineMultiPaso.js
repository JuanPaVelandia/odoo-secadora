/** @odoo-module **/

import { Component, useState } from "@odoo/owl";

/**
 * PayslipLineMultiPaso - Vista multi-paso con timeline expandible
 * Usado para IBD, retenciones, y otros cálculos complejos
 * 
 * Props:
 * - multipasoData: Object - Datos del cálculo multi-paso
 * - ruleConfig: Object - Configuración visual de la regla
 * - formatCurrency: Function - Función para formatear moneda
 * - formatValue: Function - Función para formatear valores
 * - getLeyUrl: Function - Función para obtener URL de ley
 */
export class PayslipLineMultiPaso extends Component {
    static template = "lavish_hr_payroll.PayslipLineMultiPaso";
    static props = {
        multipasoData: { type: Object },
        ruleConfig: { type: Object },
        formatCurrency: { type: Function },
        formatValue: { type: Function },
        getLeyUrl: { type: Function },
    };

    // Colores para pasos
    static STEP_COLORS = ['#3B82F6', '#8B5CF6', '#F97316', '#22C55E', '#EC4899', '#14B8A6', '#EF4444'];

    setup() {
        this.state = useState({
            expandedSteps: {1: true, 2: true, 3: true, 4: true, 5: true},
        });
    }

    get data() {
        return this.props.multipasoData || {};
    }

    get pasos() {
        return this.data.pasos || [];
    }

    get totalPasos() {
        return this.pasos.length;
    }

    get hasIndicadores() {
        return this.data.indicadores && this.data.indicadores.length > 0;
    }

    get hasWarnings() {
        return this.data.warnings && this.data.warnings.length > 0;
    }

    toggleStep(stepIndex) {
        this.state.expandedSteps[stepIndex] = !this.state.expandedSteps[stepIndex];
    }

    isStepExpanded(stepIndex) {
        return this.state.expandedSteps[stepIndex] !== false;
    }

    scrollToStep(stepIndex) {
        this.toggleStep(stepIndex);
    }

    getStepColor(index) {
        return PayslipLineMultiPaso.STEP_COLORS[index % PayslipLineMultiPaso.STEP_COLORS.length];
    }

    formatPasoValue(paso) {
        if (paso.formato === 'currency') {
            return this.props.formatCurrency(paso.resultado);
        } else if (paso.formato === 'porcentaje') {
            return `${paso.resultado}%`;
        } else if (paso.formato === 'dias') {
            return `${paso.resultado} días`;
        } else if (paso.formato === 'uvt') {
            return `${paso.resultado} UVT`;
        }
        return this.props.formatValue(paso.resultado, paso.formato);
    }
}
