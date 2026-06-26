/** @odoo-module **/
/**
 * Constantes para categorias de nomina y sus estilos.
 * Codigos sincronizados con hr_payslip_run.py y res_config_settings.py
 */

/**
 * Categorias de lineas de nomina con estilos.
 * Codigos usados: BASIC, AUX, HEYREC, SSOCIAL, PROV, etc.
 */
export const PAYSLIP_CATEGORIES = {
    // === DEVENGOS ===
    BASIC: {
        code: 'BASIC',
        name: 'Salario Basico',
        type: 'earning',
        icon: 'fa-briefcase',
        color: '#43A047',
        bgColor: '#E8F5E9',
        textColor: '#2E7D32',
        cssClass: 'category--basic',
    },
    AUX: {
        code: 'AUX',
        name: 'Auxilio Transporte/Conectividad',
        type: 'earning',
        icon: 'fa-bus',
        color: '#66BB6A',
        bgColor: '#E8F5E9',
        textColor: '#388E3C',
        cssClass: 'category--transport',
    },
    HEYREC: {
        code: 'HEYREC',
        name: 'Horas Extra y Recargos',
        type: 'earning',
        icon: 'fa-clock-o',
        color: '#26A69A',
        bgColor: '#E0F2F1',
        textColor: '#00796B',
        cssClass: 'category--overtime',
    },
    HE: {
        code: 'HE',
        name: 'Horas Extra',
        type: 'earning',
        icon: 'fa-clock-o',
        color: '#26A69A',
        bgColor: '#E0F2F1',
        textColor: '#00796B',
        cssClass: 'category--overtime',
    },
    VACACIONES: {
        code: 'VACACIONES',
        name: 'Vacaciones',
        type: 'earning',
        icon: 'fa-calendar-check-o',
        color: '#42A5F5',
        bgColor: '#E3F2FD',
        textColor: '#1565C0',
        cssClass: 'category--vacation',
    },
    AUS: {
        code: 'AUS',
        name: 'Ausencias',
        type: 'earning',
        icon: 'fa-calendar-minus-o',
        color: '#42A5F5',
        bgColor: '#E3F2FD',
        textColor: '#1565C0',
        cssClass: 'category--absence',
    },
    AUSENCIA: {
        code: 'AUSENCIA',
        name: 'Ausencias',
        type: 'earning',
        icon: 'fa-calendar-minus-o',
        color: '#42A5F5',
        bgColor: '#E3F2FD',
        textColor: '#1565C0',
        cssClass: 'category--absence',
    },
    INCAPACIDAD: {
        code: 'INCAPACIDAD',
        name: 'Incapacidades',
        type: 'earning',
        icon: 'fa-ambulance',
        color: '#FF7043',
        bgColor: '#FBE9E7',
        textColor: '#E64A19',
        cssClass: 'category--disability',
    },
    ACCIDENTE_TRABAJO: {
        code: 'ACCIDENTE_TRABAJO',
        name: 'Accidente de Trabajo',
        type: 'earning',
        icon: 'fa-ambulance',
        color: '#E53935',
        bgColor: '#FFEBEE',
        textColor: '#C62828',
        cssClass: 'category--accident',
    },
    LICENCIA_MATERNIDAD: {
        code: 'LICENCIA_MATERNIDAD',
        name: 'Licencia Maternidad/Paternidad',
        type: 'earning',
        icon: 'fa-child',
        color: '#AB47BC',
        bgColor: '#F3E5F5',
        textColor: '#7B1FA2',
        cssClass: 'category--maternity',
    },
    LICENCIA_REMUNERADA: {
        code: 'LICENCIA_REMUNERADA',
        name: 'Licencia Remunerada',
        type: 'earning',
        icon: 'fa-calendar',
        color: '#5C6BC0',
        bgColor: '#E8EAF6',
        textColor: '#3949AB',
        cssClass: 'category--license',
    },
    AUSENCIA_NO_PAGO: {
        code: 'AUSENCIA_NO_PAGO',
        name: 'Ausencia Sin Pago',
        type: 'absence',
        icon: 'fa-calendar-times-o',
        color: '#8D6E63',
        bgColor: '#EFEBE9',
        textColor: '#5D4037',
        cssClass: 'category--no-pay',
    },
    SANCIONES: {
        code: 'SANCIONES',
        name: 'Sanciones',
        type: 'deduction',
        icon: 'fa-ban',
        color: '#D32F2F',
        bgColor: '#FFCDD2',
        textColor: '#B71C1C',
        cssClass: 'category--sanction',
    },
    INDEM: {
        code: 'INDEM',
        name: 'Indemnizaciones',
        type: 'earning',
        icon: 'fa-legal',
        color: '#F57C00',
        bgColor: '#FFE0B2',
        textColor: '#E65100',
        cssClass: 'category--indemnization',
    },
    INTVIV: {
        code: 'INTVIV',
        name: 'Intereses de Vivienda',
        type: 'deduction',
        icon: 'fa-home',
        color: '#00897B',
        bgColor: '#B2DFDB',
        textColor: '#004D40',
        cssClass: 'category--housing',
    },
    DEV_SALARIAL: {
        code: 'DEV_SALARIAL',
        name: 'Devengos Salariales',
        type: 'earning',
        icon: 'fa-money',
        color: '#66BB6A',
        bgColor: '#E8F5E9',
        textColor: '#388E3C',
        cssClass: 'category--salary-earning',
    },
    DEV_NO_SALARIAL: {
        code: 'DEV_NO_SALARIAL',
        name: 'Devengos No Salariales',
        type: 'earning',
        icon: 'fa-gift',
        color: '#7E57C2',
        bgColor: '#EDE7F6',
        textColor: '#5E35B1',
        cssClass: 'category--non-salary',
    },

    // === BASE IBC/IBD ===
    BASE_SEC: {
        code: 'BASE_SEC',
        name: 'Base Seguridad Social',
        type: 'info',
        icon: 'fa-database',
        color: '#0097A7',
        bgColor: '#E0F7FA',
        textColor: '#00838F',
        cssClass: 'category--base',
    },

    // === DEDUCCIONES ===
    SSOCIAL: {
        code: 'SSOCIAL',
        name: 'Seguridad Social',
        type: 'deduction',
        icon: 'fa-shield',
        color: '#EF5350',
        bgColor: '#FFEBEE',
        textColor: '#C62828',
        cssClass: 'category--social-security',
    },
    SS: {
        code: 'SS',
        name: 'Seguridad Social',
        type: 'deduction',
        icon: 'fa-shield',
        color: '#EF5350',
        bgColor: '#FFEBEE',
        textColor: '#C62828',
        cssClass: 'category--social-security',
    },
    SS_EMP: {
        code: 'SS_EMP',
        name: 'Seguridad Social Empresa',
        type: 'company',
        icon: 'fa-building',
        color: '#78909C',
        bgColor: '#ECEFF1',
        textColor: '#455A64',
        cssClass: 'category--company-ss',
    },
    DEDUCCIONES: {
        code: 'DEDUCCIONES',
        name: 'Deducciones',
        type: 'deduction',
        icon: 'fa-minus-circle',
        color: '#E57373',
        bgColor: '#FFEBEE',
        textColor: '#C62828',
        cssClass: 'category--deductions',
    },
    RET: {
        code: 'RET',
        name: 'Retencion en la Fuente',
        type: 'deduction',
        icon: 'fa-percent',
        color: '#FF7043',
        bgColor: '#FBE9E7',
        textColor: '#E64A19',
        cssClass: 'category--retention',
    },
    RETEFUENTE: {
        code: 'RETEFUENTE',
        name: 'Retencion en la Fuente',
        type: 'deduction',
        icon: 'fa-percent',
        color: '#FF7043',
        bgColor: '#FBE9E7',
        textColor: '#E64A19',
        cssClass: 'category--retention',
    },
    EM: {
        code: 'EM',
        name: 'Embargos',
        type: 'deduction',
        icon: 'fa-gavel',
        color: '#8D6E63',
        bgColor: '#EFEBE9',
        textColor: '#5D4037',
        cssClass: 'category--embargo',
    },
    PARF: {
        code: 'PARF',
        name: 'Parafiscales',
        type: 'company',
        icon: 'fa-university',
        color: '#78909C',
        bgColor: '#ECEFF1',
        textColor: '#455A64',
        cssClass: 'category--parafiscales',
    },
    PARAFISCALES: {
        code: 'PARAFISCALES',
        name: 'Parafiscales',
        type: 'company',
        icon: 'fa-university',
        color: '#78909C',
        bgColor: '#ECEFF1',
        textColor: '#455A64',
        cssClass: 'category--parafiscales',
    },
    COMP: {
        code: 'COMP',
        name: 'Contribuciones Empresa',
        type: 'company',
        icon: 'fa-building',
        color: '#607D8B',
        bgColor: '#ECEFF1',
        textColor: '#455A64',
        cssClass: 'category--company',
    },
    CONTRIBUCION: {
        code: 'CONTRIBUCION',
        name: 'Contribuciones',
        type: 'company',
        icon: 'fa-building',
        color: '#607D8B',
        bgColor: '#ECEFF1',
        textColor: '#455A64',
        cssClass: 'category--contribution',
    },

    // === PROVISIONES ===
    PROV: {
        code: 'PROV',
        name: 'Provisiones',
        type: 'provision',
        icon: 'fa-bank',
        color: '#9C27B0',
        bgColor: '#F3E5F5',
        textColor: '#7B1FA2',
        cssClass: 'category--provisions',
    },
    PRESTACIONES_SOCIALES: {
        code: 'PRESTACIONES_SOCIALES',
        name: 'Prestaciones Sociales',
        type: 'benefit',
        icon: 'fa-trophy',
        color: '#FF9800',
        bgColor: '#FFF3E0',
        textColor: '#E65100',
        cssClass: 'category--benefits',
    },
    PRIMA: {
        code: 'PRIMA',
        name: 'Prima',
        type: 'benefit',
        icon: 'fa-star',
        color: '#FFC107',
        bgColor: '#FFF8E1',
        textColor: '#F57C00',
        cssClass: 'category--prima',
    },

    // === TOTALIZADORES ===
    TOTALDEV: {
        code: 'TOTALDEV',
        name: 'Total Devengos',
        type: 'total',
        icon: 'fa-plus-circle',
        color: '#4CAF50',
        bgColor: '#E8F5E9',
        textColor: '#2E7D32',
        cssClass: 'category--total-dev',
    },
    TOTALDED: {
        code: 'TOTALDED',
        name: 'Total Deducciones',
        type: 'total',
        icon: 'fa-minus-circle',
        color: '#F44336',
        bgColor: '#FFEBEE',
        textColor: '#C62828',
        cssClass: 'category--total-ded',
    },
    NET: {
        code: 'NET',
        name: 'Neto a Pagar',
        type: 'total',
        icon: 'fa-money',
        color: '#3949AB',
        bgColor: '#E8EAF6',
        textColor: '#1A237E',
        cssClass: 'category--net',
    },
    NETO: {
        code: 'NETO',
        name: 'Neto a Pagar',
        type: 'total',
        icon: 'fa-money',
        color: '#3949AB',
        bgColor: '#E8EAF6',
        textColor: '#1A237E',
        cssClass: 'category--net',
    },
    GROSS: {
        code: 'GROSS',
        name: 'Bruto',
        type: 'total',
        icon: 'fa-calculator',
        color: '#607D8B',
        bgColor: '#ECEFF1',
        textColor: '#455A64',
        cssClass: 'category--gross',
    },

    // === OTROS ===
    OTROS: {
        code: 'OTROS',
        name: 'Otros',
        type: 'other',
        icon: 'fa-ellipsis-h',
        color: '#9E9E9E',
        bgColor: '#F5F5F5',
        textColor: '#616161',
        cssClass: 'category--other',
    },
};

/**
 * Colores por tipo de categoria
 */
export const CATEGORY_TYPE_COLORS = {
    earning: {
        primary: '#4CAF50',
        light: '#E8F5E9',
        dark: '#2E7D32',
        text: '#1B5E20',
        border: '#81C784',
    },
    deduction: {
        primary: '#EF5350',
        light: '#FFEBEE',
        dark: '#C62828',
        text: '#B71C1C',
        border: '#E57373',
    },
    provision: {
        primary: '#9C27B0',
        light: '#F3E5F5',
        dark: '#7B1FA2',
        text: '#6A1B9A',
        border: '#BA68C8',
    },
    benefit: {
        primary: '#FF9800',
        light: '#FFF3E0',
        dark: '#E65100',
        text: '#E65100',
        border: '#FFB74D',
    },
    company: {
        primary: '#78909C',
        light: '#ECEFF1',
        dark: '#455A64',
        text: '#37474F',
        border: '#90A4AE',
    },
    absence: {
        primary: '#42A5F5',
        light: '#E3F2FD',
        dark: '#1565C0',
        text: '#0D47A1',
        border: '#64B5F6',
    },
    total: {
        primary: '#3949AB',
        light: '#E8EAF6',
        dark: '#1A237E',
        text: '#1A237E',
        border: '#7986CB',
    },
    info: {
        primary: '#607D8B',
        light: '#ECEFF1',
        dark: '#455A64',
        text: '#37474F',
        border: '#90A4AE',
    },
    other: {
        primary: '#9E9E9E',
        light: '#F5F5F5',
        dark: '#616161',
        text: '#424242',
        border: '#BDBDBD',
    },
};

/**
 * Obtiene configuracion de categoria por codigo.
 * @param {string} code - Codigo de categoria
 * @returns {Object} Configuracion de categoria (default: OTROS)
 */
export function getCategory(code) {
    return PAYSLIP_CATEGORIES[code] || PAYSLIP_CATEGORIES.OTROS;
}

/**
 * Obtiene colores para tipo de categoria.
 * @param {string} type - Tipo: earning, deduction, provision, benefit, total
 * @returns {Object} Colores del tipo
 */
export function getCategoryTypeColors(type) {
    return CATEGORY_TYPE_COLORS[type] || CATEGORY_TYPE_COLORS.other;
}

/**
 * Obtiene color principal de categoria.
 * @param {string} code - Codigo de categoria
 * @returns {string} Color hexadecimal
 */
export function getCategoryColor(code) {
    return getCategory(code).color;
}

/**
 * Obtiene color de fondo de categoria.
 * @param {string} code - Codigo de categoria
 * @returns {string} Color hexadecimal
 */
export function getCategoryBgColor(code) {
    return getCategory(code).bgColor;
}

/**
 * Obtiene icono FontAwesome de categoria.
 * @param {string} code - Codigo de categoria
 * @returns {string} Clase de icono
 */
export function getCategoryIcon(code) {
    return getCategory(code).icon;
}
