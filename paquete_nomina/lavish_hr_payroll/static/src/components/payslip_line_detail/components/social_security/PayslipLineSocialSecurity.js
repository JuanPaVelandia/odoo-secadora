/** @odoo-module **/

import { Component } from "@odoo/owl";

/**
 * PayslipLineSocialSecurity - Vista de seguridad social
 * Muestra distribución de aportes (empleado/empresa) y cálculo
 * 
 * Props:
 * - ssData: Object - Datos de seguridad social (tipo, porcentajes, valores, IBC)
 * - ruleConfig: Object - Configuración visual de la regla
 * - formatCurrency: Function - Función para formatear moneda
 * - getLeyUrl: Function - Función para obtener URL de ley
 */
export class PayslipLineSocialSecurity extends Component {
    static template = "lavish_hr_payroll.PayslipLineSocialSecurity";
    static props = {
        ssData: { type: Object },
        ruleConfig: { type: Object },
        formatCurrency: { type: Function },
        getLeyUrl: { type: Function },
    };

    get data() {
        return this.props.ssData || {};
    }

    get hasCondiciones() {
        return this.data.condiciones && this.data.condiciones.length > 0;
    }

    get empleadoBarWidth() {
        if (!this.data.porcentaje_total) return 0;
        return (this.data.porcentaje_empleado / this.data.porcentaje_total) * 100;
    }
}
