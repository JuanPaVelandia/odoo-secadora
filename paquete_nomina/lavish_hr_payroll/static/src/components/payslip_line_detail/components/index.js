/** @odoo-module **/

/**
 * Index de Sub-componentes para PayslipLineDetail
 * 
 * Este archivo exporta todos los sub-componentes creados para facilitar
 * la auditoría y mantenimiento del widget de detalle de línea de nómina.
 * 
 * Estructura de componentes:
 * 
 * PayslipLineDetail (principal)
 * ├── PayslipLineHeader       - Cabecera con código, nombre, badge devengo/deducción
 * ├── PayslipLineContextual   - Info contextual (préstamos, novedades, ausencias, vacaciones)
 * ├── PayslipLineSimple       - Vista simple con KPIs en fila (reglas básicas)
 * ├── PayslipLineProvision    - Vista detallada de provisiones (4 pasos)
 * ├── PayslipLineSocialSecurity - Vista seguridad social y distribución de aportes
 * ├── PayslipLinePrestacion   - Vista de prestaciones (prima, cesantías, vacaciones)
 * ├── PayslipLineMultiPaso    - Vista multi-paso con timeline (IBD, retenciones)
 * └── PayslipLineFormula      - Vista de fórmula con 2 columnas + tablas
 */

// Header
export { PayslipLineHeader } from "./header/PayslipLineHeader";

// Contextual
export { PayslipLineContextual } from "./contextual/PayslipLineContextual";

// Simple View
export { PayslipLineSimple } from "./simple/PayslipLineSimple";

// Provision View
export { PayslipLineProvision } from "./provision/PayslipLineProvision";

// Social Security View
export { PayslipLineSocialSecurity } from "./social_security/PayslipLineSocialSecurity";

// Prestación View
export { PayslipLinePrestacion } from "./prestacion/PayslipLinePrestacion";

// Multi-Paso View
export { PayslipLineMultiPaso } from "./multi_paso/PayslipLineMultiPaso";

// Formula View
export { PayslipLineFormula } from "./formula/PayslipLineFormula";
