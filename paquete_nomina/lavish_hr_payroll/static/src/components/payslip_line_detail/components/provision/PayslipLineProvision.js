/** @odoo-module **/

import { Component, useState } from "@odoo/owl";

/**
 * PayslipLineProvision - Vista detallada de provisiones
 * Muestra 4 pasos: Base, Días, Fórmula, Resultado
 * 
 * Props:
 * - provisionData: Object - Datos de la provisión procesados
 * - ruleConfig: Object - Configuración visual de la regla
 * - formatCurrency: Function - Función para formatear moneda
 * - formatValue: Function - Función para formatear valores
 * - getLeyUrl: Function - Función para obtener URL de ley
 */
export class PayslipLineProvision extends Component {
    static template = "lavish_hr_payroll.PayslipLineProvision";
    static props = {
        provisionData: { type: Object },
        ruleConfig: { type: Object },
        formatCurrency: { type: Function },
        formatValue: { type: Function },
        getLeyUrl: { type: Function },
    };

    setup() {
        this.state = useState({
            expandedSteps: { 1: true, 2: true, 3: true, 4: true },
        });
    }

    toggleStep(stepNum) {
        this.state.expandedSteps[stepNum] = !this.state.expandedSteps[stepNum];
    }

    isStepExpanded(stepNum) {
        return this.state.expandedSteps[stepNum] || false;
    }

    scrollToStep(stepNum) {
        // Expandir el paso si está colapsado
        if (!this.state.expandedSteps[stepNum]) {
            this.state.expandedSteps[stepNum] = true;
        }
    }

    get data() {
        return this.props.provisionData || {};
    }

    get hasConceptos() {
        return this.data.conceptosIncluidos && this.data.conceptosIncluidos.length > 0;
    }

    get hasFormulaPasos() {
        return this.data.formulaPasos && this.data.formulaPasos.length > 0;
    }

    get hasIndicadores() {
        return this.data.indicadores && this.data.indicadores.length > 0;
    }

    get hasWarnings() {
        return this.data.warnings && this.data.warnings.length > 0;
    }

    get showComparativa() {
        return this.data.valorAnterior > 0;
    }

    get showFechas() {
        return this.data.fechaInicio || this.data.fechaCorte;
    }
}
