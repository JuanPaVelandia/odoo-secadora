/** @odoo-module **/

/**
 * Configuraciones Predefinidas para Componentes Genéricos
 * =======================================================
 *
 * Este archivo contiene configuraciones reutilizables para diferentes
 * casos de uso de los componentes genéricos.
 */

/**
 * Configuración para tabla de reglas de nómina con IBD
 */
export const RULES_WITH_IBD_CONFIG = {
    levels: [
        {
            name: 'category',
            labelField: 'name',
            colorField: 'color',
            bgColorField: 'bgColor',
            textColorField: 'textColor',
            iconField: 'icon',
            showTotal: true,
            expandable: true,
        },
        {
            name: 'rule',
            labelField: 'name',
            showBadge: true,
            badgeField: 'type_concepts',
            expandable: false,
        },
    ],
    columns: [
        {
            key: 'name',
            label: 'Nombre',
            width: '30%',
            type: 'text'
        },
        {
            key: 'code',
            label: 'Código',
            width: '10%',
            type: 'text'
        },
        {
            key: 'ibd_percentage',
            label: '% IBD',
            width: '10%',
            type: 'badge',
            formatter: (value) => value === 0 ? '0%' : '40%',
            colorFormatter: (value, row) => row.ibd_color || '#FFFFFF',
            textColorFormatter: (value) => value === 0 ? '#424242' : '#1B5E20'
        },
        {
            key: 'percentage_used',
            label: '% Usado',
            width: '10%',
            type: 'percentage',
            formatter: 'percentage',
            helpText: 'Porcentaje efectivamente aplicado en el cálculo'
        },
        {
            key: 'amount_used',
            label: 'Valor Usado',
            width: '15%',
            type: 'currency',
            formatter: 'currency',
            helpText: 'Valor calculado en la nómina actual'
        },
        {
            key: 'law_reference',
            label: 'Referencia Legal',
            width: '25%',
            type: 'link',
            linkField: 'law_url'
        },
    ],
    expandedByDefault: false,
};

/**
 * Configuración para tabla de nóminas con líneas detalladas
 */
export const PAYSLIP_LINES_CONFIG = {
    levels: [
        {
            name: 'category',
            labelField: 'title',
            colorField: 'color',
            textColorField: 'textColor',
            showTotal: true,
            expandable: true,
        },
        {
            name: 'line',
            labelField: 'name',
            showQuantity: true,
            showAmount: true,
        },
    ],
    columns: [
        {
            key: 'name',
            label: 'Concepto',
            width: '40%',
            type: 'text'
        },
        {
            key: 'code',
            label: 'Código',
            width: '15%',
            type: 'text'
        },
        {
            key: 'quantity',
            label: 'Días',
            width: '10%',
            type: 'number',
            formatter: 'number'
        },
        {
            key: 'rate',
            label: 'Tasa %',
            width: '10%',
            type: 'percentage'
        },
        {
            key: 'amount',
            label: 'Valor',
            width: '25%',
            type: 'currency',
            formatter: 'currency'
        },
    ],
    expandedByDefault: true,
};

/**
 * Configuración para novedades diferentes (hr.novelties.different.concepts)
 */
export const NOVELTIES_CONFIG = {
    levels: [
        {
            name: 'type',
            labelField: 'name',
            colorField: 'color',
            expandable: true,
        },
        {
            name: 'novelty',
            labelField: 'name',
            showBadge: true,
            badgeField: 'state',
        },
    ],
    columns: [
        {
            key: 'name',
            label: 'Concepto',
            width: '30%',
            type: 'text'
        },
        {
            key: 'input_id',
            label: 'Entrada',
            width: '20%',
            type: 'text'
        },
        {
            key: 'amount',
            label: 'Valor',
            width: '15%',
            type: 'currency',
            formatter: 'currency'
        },
        {
            key: 'aplicar',
            label: 'Quincena',
            width: '10%',
            type: 'badge',
            formatter: (value) => value === '15' ? '1Q' : value === '30' ? '2Q' : 'Todas',
        },
        {
            key: 'state',
            label: 'Estado',
            width: '15%',
            type: 'badge'
        },
        {
            key: 'payslip_id',
            label: 'Nómina',
            width: '10%',
            type: 'link'
        },
    ],
    expandedByDefault: false,
};

/**
 * Configuración de campos para visualización de nómina
 */
export const PAYSLIP_FIELDS_CONFIG = [
    { key: 'id', label: 'ID', type: 'text', highlight: true },
    { key: 'number', label: 'Número', type: 'text' },
    { key: 'employee_id', label: 'Empleado', type: 'many2one' },
    { key: 'contract_id', label: 'Contrato', type: 'many2one' },
    { key: 'date_from', label: 'Fecha Desde', type: 'date' },
    { key: 'date_to', label: 'Fecha Hasta', type: 'date' },
    { key: 'struct_id', label: 'Estructura', type: 'many2one' },
    { key: 'state', label: 'Estado', type: 'badge', colorMap: {
        'draft': { bg: '#EEEEEE', text: '#757575', label: 'Borrador' },
        'verify': { bg: '#E8EAF6', text: '#3949AB', label: 'Verificar' },
        'done': { bg: '#E8F5E9', text: '#2E7D32', label: 'Hecho' },
        'paid': { bg: '#E1F5FE', text: '#0277BD', label: 'Pagado' },
        'cancel': { bg: '#FFEBEE', text: '#C62828', label: 'Cancelado' },
    }},
];

/**
 * Configuración de campos para visualización de ausencias
 */
export const ABSENCE_FIELDS_CONFIG = [
    { key: 'id', label: 'ID Ausencia', type: 'text', highlight: true },
    { key: 'employee_id', label: 'Empleado', type: 'many2one' },
    { key: 'holiday_status_id', label: 'Tipo de Ausencia', type: 'badge', colorMap: {
        'vac': { bg: '#E8F5E9', text: '#2E7D32', label: 'Vacaciones' },
        'ige': { bg: '#FFF3E0', text: '#E65100', label: 'Incapacidad EPS' },
        'irl': { bg: '#FFEBEE', text: '#C62828', label: 'Incapacidad ARL' },
        'lnr': { bg: '#F3E5F5', text: '#7B1FA2', label: 'Licencia No Remunerada' },
        'lma': { bg: '#E1F5FE', text: '#0277BD', label: 'Licencia Maternidad' },
        'lpa': { bg: '#E3F2FD', text: '#1565C0', label: 'Licencia Paternidad' },
    }},
    { key: 'request_date_from', label: 'Desde', type: 'date' },
    { key: 'request_date_to', label: 'Hasta', type: 'date' },
    { key: 'number_of_days', label: 'Días', type: 'number' },
    { key: 'state', label: 'Estado', type: 'badge' },
];

/**
 * Configuración de campos para visualización de préstamos
 */
export const LOAN_FIELDS_CONFIG = [
    { key: 'id', label: 'ID Préstamo', type: 'text', highlight: true },
    { key: 'name', label: 'Nombre', type: 'text' },
    { key: 'employee_id', label: 'Empleado', type: 'many2one' },
    { key: 'date', label: 'Fecha', type: 'date' },
    { key: 'loan_amount', label: 'Monto Total', type: 'currency' },
    { key: 'balance_amount', label: 'Saldo Pendiente', type: 'currency' },
    { key: 'installment', label: 'Valor Cuota', type: 'currency' },
    { key: 'payment_date', label: 'Fecha Pago', type: 'date' },
    { key: 'state', label: 'Estado', type: 'badge', colorMap: {
        'draft': { bg: '#EEEEEE', text: '#757575', label: 'Borrador' },
        'approve': { bg: '#E8F5E9', text: '#2E7D32', label: 'Aprobado' },
        'refuse': { bg: '#FFEBEE', text: '#C62828', label: 'Rechazado' },
        'cancel': { bg: '#F5F5F5', text: '#9E9E9E', label: 'Cancelado' },
    }},
];

/**
 * Tipos de badges con colores predefinidos
 */
export const BADGE_TYPES = {
    // Estados de nómina
    payslip_state: {
        draft: { bg: '#EEEEEE', text: '#757575', icon: 'fa-file-alt' },
        verify: { bg: '#E8EAF6', text: '#3949AB', icon: 'fa-check-circle' },
        done: { bg: '#E8F5E9', text: '#2E7D32', icon: 'fa-check-double' },
        paid: { bg: '#E1F5FE', text: '#0277BD', icon: 'fa-money-bill-wave' },
        cancel: { bg: '#FFEBEE', text: '#C62828', icon: 'fa-times-circle' },
    },

    // Tipos de concepto
    type_concepts: {
        sueldo: { bg: '#E8F5E9', text: '#2E7D32', label: 'Sueldo' },
        contrato: { bg: '#E3F2FD', text: '#1565C0', label: 'Fijo Contrato' },
        ley: { bg: '#FFF3E0', text: '#E65100', label: 'Por Ley' },
        novedad: { bg: '#E0F7FA', text: '#00838F', label: 'Novedad' },
        prestacion: { bg: '#F3E5F5', text: '#7B1FA2', label: 'Prestación' },
        provision: { bg: '#FFF9C4', text: '#F57F17', label: 'Provisión' },
        consolidacion: { bg: '#FFEBEE', text: '#C62828', label: 'Total' },
        tributaria: { bg: '#FCE4EC', text: '#C2185B', label: 'Tributaria' },
        seguridad_social: { bg: '#E1F5FE', text: '#0277BD', label: 'SS' },
        parafiscal: { bg: '#E8EAF6', text: '#3949AB', label: 'Parafiscal' },
    },

    // Quincenas
    fortnight: {
        '15': { bg: '#E3F2FD', text: '#1565C0', label: '1ra Quincena' },
        '30': { bg: '#E8F5E9', text: '#2E7D32', label: '2da Quincena' },
        '0': { bg: '#F5F5F5', text: '#616161', label: 'Siempre' },
    },
};

/**
 * Opciones de formateo para valores
 */
export const FORMATTERS = {
    currency: (value) => {
        if (value === null || value === undefined) return '';
        return new Intl.NumberFormat('es-CO', {
            style: 'currency',
            currency: 'COP',
            minimumFractionDigits: 0,
            maximumFractionDigits: 0
        }).format(value);
    },

    number: (value) => {
        if (value === null || value === undefined) return '';
        return new Intl.NumberFormat('es-CO', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        }).format(value);
    },

    percentage: (value) => {
        if (value === null || value === undefined) return '';
        return `${value}%`;
    },

    date: (value) => {
        if (!value) return '';
        return new Date(value).toLocaleDateString('es-CO', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric'
        });
    },

    boolean: (value) => {
        return value ? 'Sí' : 'No';
    },
};

/**
 * Paleta de colores estándar para interfaces financieras
 */
export const COLOR_PALETTE = {
    // Inputs editables
    input_editable: '#0070C0',

    // Fórmulas y cálculos
    formula_calculated: '#000000',

    // Links externos
    link_external: '#FF0000',

    // IBD
    ibd_applies: '#92D050',      // Verde - Aplica 40%
    ibd_excluded: '#C0C0C0',     // Gris - Excluido

    // Headers
    header_category: '#FFC000',  // Naranja - Categoría nivel 1
    header_rule: '#4472C4',      // Azul - Regla nivel 2
    header_line: '#FFFFFF',      // Blanco - Línea nivel 3

    // Estados
    alert: '#FFFF00',            // Amarillo - Alerta

    // Devengos y Deducciones
    earnings: {
        bg: '#E8F5E9',
        text: '#2E7D32',
        icon: '#4CAF50',
    },
    deductions: {
        bg: '#FFEBEE',
        text: '#C62828',
        icon: '#EF5350',
    },
    net: {
        bg: '#E8EAF6',
        text: '#3949AB',
        icon: '#5C6BC0',
    },
};

/**
 * Configuración de espaciado para el calendario de días
 */
export const DAYS_CALENDAR_SPACING = {
    wide: {
        maxDays: 15,
        cellWidth: '50px',
        fontSize: '14px',
    },
    normal: {
        maxDays: 31,
        cellWidth: '30px',
        fontSize: '12px',
    },
    compact: {
        maxDays: Infinity,
        cellWidth: '20px',
        fontSize: '10px',
    },
};

/**
 * Configuración de iconos para diferentes tipos de datos
 */
export const ICON_MAPPING = {
    // Tipos de registro
    payslip: 'fa-file-invoice-dollar',
    absence: 'fa-user-clock',
    loan: 'fa-hand-holding-usd',
    contract: 'fa-file-signature',

    // Acciones
    view: 'fa-eye',
    edit: 'fa-edit',
    delete: 'fa-trash',
    download: 'fa-download',
    print: 'fa-print',

    // Estados
    success: 'fa-check-circle',
    warning: 'fa-exclamation-triangle',
    error: 'fa-times-circle',
    info: 'fa-info-circle',
};
