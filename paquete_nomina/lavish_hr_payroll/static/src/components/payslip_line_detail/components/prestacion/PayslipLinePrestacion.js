/** @odoo-module **/

import { Component, useState } from "@odoo/owl";

/**
 * PayslipLinePrestacion - Vista de prestaciones sociales
 * Prima, Cesantías, Intereses Cesantías, Vacaciones
 * 
 * Props:
 * - prestacionData: Object - Datos de la prestación procesados
 * - ruleConfig: Object - Configuración visual de la regla
 * - formatCurrency: Function - Función para formatear moneda
 * - formatValue: Function - Función para formatear valores
 * - getLeyUrl: Function - Función para obtener URL de ley
 * - getStepColor: Function - Función para obtener color del paso
 */
export class PayslipLinePrestacion extends Component {
    static template = "lavish_hr_payroll.PayslipLinePrestacion";
    static props = {
        prestacionData: { type: Object },
        ruleConfig: { type: Object },
        formatCurrency: { type: Function },
        formatValue: { type: Function },
        getLeyUrl: { type: Function },
        getStepColor: { type: Function },
    };

    // Colores para pasos
    static STEP_COLORS = ['#3B82F6', '#8B5CF6', '#F97316', '#22C55E', '#EC4899', '#14B8A6', '#EF4444'];

    setup() {
        this.state = useState({
            showVariableDetail: false,
        });
    }

    toggleVariableDetail() {
        this.state.showVariableDetail = !this.state.showVariableDetail;
    }

    get data() {
        return this.props.prestacionData || {};
    }

    get hasIndicadores() {
        return this.data.indicadores && this.data.indicadores.length > 0;
    }

    get hasLineasVariable() {
        return this.data.lineasVariable && this.data.lineasVariable.length > 0;
    }

    get hasFormulaPasos() {
        return this.data.formulaPasos && this.data.formulaPasos.length > 0;
    }

    get totalLineasVariable() {
        if (!this.hasLineasVariable) return 0;
        return this.data.lineasVariable.reduce((sum, l) => sum + l.total, 0);
    }

    getStepColor(index) {
        return PayslipLinePrestacion.STEP_COLORS[index % PayslipLinePrestacion.STEP_COLORS.length];
    }
}
