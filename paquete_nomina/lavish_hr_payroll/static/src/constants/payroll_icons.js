/** @odoo-module **/
/**
 * Constantes centralizadas para iconos de nomina.
 * Incluye FontAwesome y rutas a iconos Lottie locales.
 */

const LOTTIE_BASE_PATH = '/lavish_hr_payroll/static/src/lib/lottie/icons/';

/**
 * Iconos Lottie por categoria/concepto
 */
export const LOTTIE_ICONS = {
    // Generales
    default: `${LOTTIE_BASE_PATH}wloilxuq.json`,
    loading: `${LOTTIE_BASE_PATH}loading.json`,
    empty: `${LOTTIE_BASE_PATH}empty.json`,

    // Devengos
    sueldo: `${LOTTIE_BASE_PATH}qhviklyi.json`,
    auxilio: `${LOTTIE_BASE_PATH}uiiwvjrg.json`,
    horas_extras: `${LOTTIE_BASE_PATH}kbtmbyzy.json`,
    comisiones: `${LOTTIE_BASE_PATH}wyqtxzeh.json`,
    vacaciones: `${LOTTIE_BASE_PATH}iprinfmf.json`,
    incapacidades: `${LOTTIE_BASE_PATH}yrxnwkni.json`,
    licencias: `${LOTTIE_BASE_PATH}hrqwmutt.json`,
    devengos_salariales: `${LOTTIE_BASE_PATH}qhviklyi.json`,
    devengos_no_salariales: `${LOTTIE_BASE_PATH}mwikjdwh.json`,

    // Deducciones
    seguridad_social: `${LOTTIE_BASE_PATH}mqqsmoak.json`,
    retencion: `${LOTTIE_BASE_PATH}nizfqlnq.json`,
    deducciones: `${LOTTIE_BASE_PATH}vduvxizq.json`,
    prestamos: `${LOTTIE_BASE_PATH}prestamos.json`,

    // Prestaciones
    prestaciones: `${LOTTIE_BASE_PATH}fqbvgezn.json`,
    prima: `${LOTTIE_BASE_PATH}prima.json`,
    cesantias: `${LOTTIE_BASE_PATH}cesantias.json`,

    // Dashboard
    employees: `${LOTTIE_BASE_PATH}employees.json`,
    money: `${LOTTIE_BASE_PATH}yeallgsa.json`,
    calendar: `${LOTTIE_BASE_PATH}calendar.json`,
    chart: `${LOTTIE_BASE_PATH}chart.json`,
    alert: `${LOTTIE_BASE_PATH}alert.json`,
};

/**
 * Iconos FontAwesome por categoria
 */
export const FA_ICONS = {
    // Generales
    default: 'fa-file-o',
    loading: 'fa-spinner fa-spin',
    empty: 'fa-inbox',
    search: 'fa-search',
    filter: 'fa-filter',
    refresh: 'fa-refresh',
    expand: 'fa-expand',
    compress: 'fa-compress',
    external: 'fa-external-link',
    info: 'fa-info-circle',
    warning: 'fa-exclamation-triangle',
    error: 'fa-times-circle',
    success: 'fa-check-circle',

    // Devengos
    basic: 'fa-briefcase',
    transport: 'fa-bus',
    overtime: 'fa-clock-o',
    vacation: 'fa-calendar-check-o',
    absence: 'fa-calendar-minus-o',
    commission: 'fa-percent',
    bonus: 'fa-gift',
    ibd: 'fa-database',
    history: 'fa-history',

    // Deducciones
    health: 'fa-medkit',
    pension: 'fa-shield',
    solidarity: 'fa-handshake-o',
    retention: 'fa-percent',
    loans: 'fa-credit-card',

    // Prestaciones y provisiones
    benefits: 'fa-trophy',
    provisions: 'fa-bank',
    prima: 'fa-star',
    cesantias: 'fa-archive',
    interests: 'fa-line-chart',

    // Empleados y contratos
    employee: 'fa-user',
    employees: 'fa-users',
    contract: 'fa-file-text-o',
    department: 'fa-building-o',
    identification: 'fa-id-card-o',

    // Acciones
    view: 'fa-eye',
    edit: 'fa-pencil',
    delete: 'fa-trash',
    download: 'fa-download',
    print: 'fa-print',
    compute: 'fa-calculator',
    add: 'fa-plus',
    remove: 'fa-minus',

    // Estados
    draft: 'fa-file-o',
    verify: 'fa-check-circle-o',
    done: 'fa-check',
    paid: 'fa-money',
    cancel: 'fa-times',

    // Totales
    earnings: 'fa-plus-circle',
    deductions: 'fa-minus-circle',
    net: 'fa-money',
};

/**
 * Obtiene icono Lottie por clave.
 * @param {string} key - Clave del icono
 * @returns {string} Ruta al archivo JSON
 */
export function getLottieIcon(key) {
    return LOTTIE_ICONS[key] || LOTTIE_ICONS.default;
}

/**
 * Obtiene clase FontAwesome por clave.
 * @param {string} key - Clave del icono
 * @returns {string} Clase CSS de FontAwesome
 */
export function getFaIcon(key) {
    return FA_ICONS[key] || FA_ICONS.default;
}

/**
 * Obtiene icono FontAwesome para categoria de nomina.
 * @param {string} categoryCode - Codigo de categoria (BASIC, SALUD, etc.)
 * @returns {string} Clase CSS de FontAwesome
 */
export function getCategoryIcon(categoryCode) {
    const categoryIcons = {
        'BASIC': FA_ICONS.basic,
        'AUXTRANSPORTE': FA_ICONS.transport,
        'HEYREC': FA_ICONS.overtime,
        'VACACIONES': FA_ICONS.vacation,
        'AUSENCIAS': FA_ICONS.absence,
        'COMISIONES': FA_ICONS.commission,
        'BONIFICACIONES': FA_ICONS.bonus,
        'DEV_SALARIAL': FA_ICONS.basic,
        'DEV_NO_SALARIAL': FA_ICONS.bonus,
        'IBD': FA_ICONS.ibd,
        'IBC': FA_ICONS.ibd,
        'SALUD': FA_ICONS.health,
        'PENSION': FA_ICONS.pension,
        'FONDO_SOLIDARIDAD': FA_ICONS.solidarity,
        'FSP': FA_ICONS.solidarity,
        'RETENCION': FA_ICONS.retention,
        'RTF': FA_ICONS.retention,
        'PRESTAMOS': FA_ICONS.loans,
        'DESCUENTOS': FA_ICONS.deductions,
        'PROVISIONES': FA_ICONS.provisions,
        'PRESTACIONES': FA_ICONS.benefits,
        'PRIMA': FA_ICONS.prima,
        'CESANTIAS': FA_ICONS.cesantias,
        'INT_CESANTIAS': FA_ICONS.interests,
    };
    return categoryIcons[categoryCode] || FA_ICONS.default;
}
