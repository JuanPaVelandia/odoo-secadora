/** @odoo-module **/

import { Component } from "@odoo/owl";

/**
 * PayslipLineHeader - Cabecera del detalle de línea de nómina
 * Muestra: código, nombre, icono, badge devengo/deducción
 * 
 * Props:
 * - line: Object - Datos de la línea (code, name, dev_or_ded)
 * - ruleConfig: Object - Configuración visual de la regla (icon, color, gradient, borderColor)
 */
export class PayslipLineHeader extends Component {
    static template = "lavish_hr_payroll.PayslipLineHeader";
    static props = {
        line: { type: Object },
        ruleConfig: { type: Object },
    };

    get isDevengo() {
        return this.props.line.dev_or_ded === 'devengo';
    }
}
