/** @odoo-module **/

/**
 * Configuraciones estáticas para PayslipLineDetail
 * 
 * Este módulo contiene todas las configuraciones estáticas que determinan
 * el comportamiento visual y de procesamiento del widget de detalle de línea.
 */

/**
 * Mapeo de tipos de visualización por código de regla
 */
export const VISUALIZATION_TYPE_MAP = {
    // Tipo Simple (KPI)
    'BASIC': 'simple',
    'BASIC001': 'simple',
    'BASIC002': 'simple',
    'BASIC003': 'simple',
    'SSOCIAL001': 'simple',
    'SSOCIAL002': 'simple',
    'LOAN': 'simple',
    'NOV': 'simple',

    // Provisiones
    'PROV_PRIMA': 'provision',
    'PROV_CESANTIAS': 'provision',
    'PROV_INTCES': 'provision',
    'PROV_VAC': 'provision',
    'PROV_': 'provision',
    'PRV_PRIMA': 'provision',
    'PRV_CES': 'provision',
    'PRV_ICES': 'provision',
    'PRV_VAC': 'provision',
    'PRV_': 'provision',

    // Tipo Formula - Auxilios, Seguridad Social, HE
    'AUX000': 'formula',
    'AUX00C': 'formula',
    'DEV_AUX': 'formula',
    'SSOCIAL003': 'formula',
    'SSOCIAL004': 'formula',
    'HEYREC': 'formula',
    'INC_': 'formula',

    // Tipo Prestacion - Prestaciones Sociales (con pasos detallados del backend)
    'PRIMA': 'prestacion',
    'CESANTIAS': 'prestacion',
    'CES_YEAR': 'prestacion',
    'INTCESANTIAS': 'prestacion',
    'INTCES_YEAR': 'prestacion',
    'VACCONTRATO': 'prestacion',
    'VACDISFRUTADAS': 'prestacion',
    'VACANOVE': 'prestacion',
    'VACATIONS_MONEY': 'prestacion',
    'VAC_': 'prestacion',

    // Tipo Multi-paso (IBD, Retenciones, Indemnizaciones)
    'IBD': 'multi_paso',
    'IBC': 'multi_paso',
    // Retenciones - todos los codigos
    'RTEFTE': 'multi_paso',
    'RTF': 'multi_paso',
    'RT_MET_01': 'multi_paso',
    'RT_MET_02': 'multi_paso',
    'RET_PRIMA': 'multi_paso',
    'RTF_INDEM': 'multi_paso',
    'RETENCION': 'multi_paso',
    // Indemnizaciones
    'INDEM': 'multi_paso',
    'PREAVISO': 'multi_paso',
};

/**
 * Configuración de estilos por tipo de regla
 */
export const RULE_CONFIG = {
    'IBD': {
        icon: 'fa-building',
        color: '#0EA5E9',
        gradient: 'linear-gradient(135deg, #E0F2FE 0%, #BAE6FD 100%)',
        borderColor: '#7DD3FC',
        name: 'Ingreso Base de Cotizacion',
        baseLegal: 'Ley 1393/2010'
    },
    'IBC': {
        icon: 'fa-building',
        color: '#0EA5E9',
        gradient: 'linear-gradient(135deg, #E0F2FE 0%, #BAE6FD 100%)',
        borderColor: '#7DD3FC',
        name: 'Ingreso Base de Cotizacion',
        baseLegal: 'Ley 1393/2010'
    },
    // Seguridad Social especifica
    'SSOCIAL001': {
        icon: 'fa-heartbeat',
        color: '#DC2626',
        gradient: 'linear-gradient(135deg, #FEE2E2 0%, #FECACA 100%)',
        borderColor: '#FCA5A5',
        name: 'Aporte Salud Empleado',
        baseLegal: 'Ley 100/1993 Art. 204',
        porcentaje: 4.0,
        descripcion: 'Salud: 12.5% total (8.5% empresa + 4% empleado)'
    },
    'SSOCIAL002': {
        icon: 'fa-shield',
        color: '#2563EB',
        gradient: 'linear-gradient(135deg, #DBEAFE 0%, #BFDBFE 100%)',
        borderColor: '#93C5FD',
        name: 'Aporte Pension Empleado',
        baseLegal: 'Ley 100/1993 Art. 20',
        porcentaje: 4.0,
        descripcion: 'Pension: 16% total (12% empresa + 4% empleado)'
    },
    'SSOCIAL003': {
        icon: 'fa-university',
        color: '#7C3AED',
        gradient: 'linear-gradient(135deg, #EDE9FE 0%, #DDD6FE 100%)',
        borderColor: '#C4B5FD',
        name: 'Fondo Solidaridad Pensional',
        baseLegal: 'Ley 797/2003 Art. 7',
        porcentaje: 0.5,
        descripcion: 'FSP: 0.5% adicional si IBC > 4 SMMLV',
        tabla_rangos: true
    },
    'SSOCIAL004': {
        icon: 'fa-users',
        color: '#0D9488',
        gradient: 'linear-gradient(135deg, #CCFBF1 0%, #99F6E4 100%)',
        borderColor: '#5EEAD4',
        name: 'Fondo Subsistencia',
        baseLegal: 'Ley 797/2003 Art. 8',
        porcentaje_variable: true,
        descripcion: 'Subsistencia: 0.5%-1.5% adicional si IBC > 16 SMMLV',
        tabla_rangos: true
    },
    'BASIC': {
        icon: 'fa-money',
        color: '#2563EB',
        gradient: 'linear-gradient(135deg, #DBEAFE 0%, #BFDBFE 100%)',
        borderColor: '#93C5FD',
        name: 'Salario Basico',
        baseLegal: 'Art. 127 C.S.T.'
    },
    'PRIMA': {
        icon: 'fa-gift',
        color: '#15803D',
        gradient: 'linear-gradient(135deg, #DCFCE7 0%, #BBF7D0 100%)',
        borderColor: '#86EFAC',
        name: 'Prima de Servicios',
        baseLegal: 'Art. 306 C.S.T.'
    },
    'CES': {
        icon: 'fa-university',
        color: '#D97706',
        gradient: 'linear-gradient(135deg, #FEF3C7 0%, #FDE68A 100%)',
        borderColor: '#FCD34D',
        name: 'Cesantias',
        baseLegal: 'Art. 249 C.S.T.'
    },
    'ICES': {
        icon: 'fa-line-chart',
        color: '#EA580C',
        gradient: 'linear-gradient(135deg, #FFEDD5 0%, #FED7AA 100%)',
        borderColor: '#FDBA74',
        name: 'Intereses Cesantias',
        baseLegal: 'Ley 52/1975'
    },
    'VAC': {
        icon: 'fa-sun-o',
        color: '#CA8A04',
        gradient: 'linear-gradient(135deg, #FEF9C3 0%, #FEF08A 100%)',
        borderColor: '#FDE047',
        name: 'Vacaciones',
        baseLegal: 'Art. 186-192 C.S.T.'
    },
    'AUX': {
        icon: 'fa-bus',
        color: '#0D9488',
        gradient: 'linear-gradient(135deg, #CCFBF1 0%, #99F6E4 100%)',
        borderColor: '#5EEAD4',
        name: 'Auxilio de Transporte',
        baseLegal: 'Ley 15/1959'
    },
    'EPS': {
        icon: 'fa-heartbeat',
        color: '#DC2626',
        gradient: 'linear-gradient(135deg, #FEE2E2 0%, #FECACA 100%)',
        borderColor: '#FCA5A5',
        name: 'Aporte Salud',
        baseLegal: 'Ley 100/1993'
    },
    'SSOCIAL': {
        icon: 'fa-shield',
        color: '#7C3AED',
        gradient: 'linear-gradient(135deg, #EDE9FE 0%, #DDD6FE 100%)',
        borderColor: '#C4B5FD',
        name: 'Seguridad Social',
        baseLegal: 'Ley 100/1993'
    },
    'AFP': {
        icon: 'fa-shield',
        color: '#2563EB',
        gradient: 'linear-gradient(135deg, #DBEAFE 0%, #BFDBFE 100%)',
        borderColor: '#93C5FD',
        name: 'Aporte Pension',
        baseLegal: 'Ley 100/1993'
    },
    'RTEFTE': {
        icon: 'fa-percent',
        color: '#DC2626',
        gradient: 'linear-gradient(135deg, #FEE2E2 0%, #FECACA 100%)',
        borderColor: '#FCA5A5',
        name: 'Retencion en la Fuente',
        baseLegal: 'Art. 383-387 E.T.'
    },
    'RTF': {
        icon: 'fa-percent',
        color: '#DC2626',
        gradient: 'linear-gradient(135deg, #FEE2E2 0%, #FECACA 100%)',
        borderColor: '#FCA5A5',
        name: 'Retencion en la Fuente',
        baseLegal: 'Art. 383-387 E.T.'
    },
    'RT_MET_01': {
        icon: 'fa-percent',
        color: '#DC2626',
        gradient: 'linear-gradient(135deg, #FEE2E2 0%, #FECACA 100%)',
        borderColor: '#FCA5A5',
        name: 'Retención en la Fuente (Procedimiento 1)',
        baseLegal: 'Art. 383-387 E.T.',
        descripcion: 'Procedimiento 1: Cálculo mensual sobre ingresos gravables',
        procedimiento: 1
    },
    'RT_MET_02': {
        icon: 'fa-percent',
        color: '#DC2626',
        gradient: 'linear-gradient(135deg, #FEE2E2 0%, #FECACA 100%)',
        borderColor: '#FCA5A5',
        name: 'Retención en la Fuente (Procedimiento 2)',
        baseLegal: 'Art. 386 E.T.',
        descripcion: 'Procedimiento 2: Promedio de 12 meses anteriores',
        procedimiento: 2
    },
    'PROV': {
        icon: 'fa-database',
        color: '#7C3AED',
        gradient: 'linear-gradient(135deg, #EDE9FE 0%, #DDD6FE 100%)',
        borderColor: '#C4B5FD',
        name: 'Provision',
        baseLegal: 'Art. 249, 306 C.S.T.'
    },
    'HE_': {
        icon: 'fa-clock-o',
        color: '#7C3AED',
        gradient: 'linear-gradient(135deg, #EDE9FE 0%, #DDD6FE 100%)',
        borderColor: '#C4B5FD',
        name: 'Horas Extras',
        baseLegal: 'Art. 159-168 C.S.T.'
    },
    'HEYREC': {
        icon: 'fa-clock-o',
        color: '#7C3AED',
        gradient: 'linear-gradient(135deg, #EDE9FE 0%, #DDD6FE 100%)',
        borderColor: '#C4B5FD',
        name: 'Horas Extras',
        baseLegal: 'Art. 159-168 C.S.T.'
    },
    'LOAN': {
        icon: 'fa-credit-card',
        color: '#7C3AED',
        gradient: 'linear-gradient(135deg, #EDE9FE 0%, #DDD6FE 100%)',
        borderColor: '#C4B5FD',
        name: 'Prestamo',
        baseLegal: ''
    },
    'INCAP': {
        icon: 'fa-medkit',
        color: '#DC2626',
        gradient: 'linear-gradient(135deg, #FEE2E2 0%, #FECACA 100%)',
        borderColor: '#FCA5A5',
        name: 'Incapacidad',
        baseLegal: 'Art. 227 C.S.T.'
    },
    'INC_': {
        icon: 'fa-medkit',
        color: '#DC2626',
        gradient: 'linear-gradient(135deg, #FEE2E2 0%, #FECACA 100%)',
        borderColor: '#FCA5A5',
        name: 'Incapacidad',
        baseLegal: 'Decreto 2943/2013'
    },
    'INDEM': {
        icon: 'fa-gavel',
        color: '#B91C1C',
        gradient: 'linear-gradient(135deg, #FEE2E2 0%, #FECACA 100%)',
        borderColor: '#FCA5A5',
        name: 'Indemnizacion',
        baseLegal: 'Art. 64 C.S.T.'
    },
    // Cesantias
    'CESANTIAS': {
        icon: 'fa-university',
        color: '#D97706',
        gradient: 'linear-gradient(135deg, #FEF3C7 0%, #FDE68A 100%)',
        borderColor: '#FCD34D',
        name: 'Cesantías',
        baseLegal: 'Art. 249 C.S.T.',
        descripcion: 'Un mes de salario por cada año de servicios'
    },
    'CES_YEAR': {
        icon: 'fa-university',
        color: '#D97706',
        gradient: 'linear-gradient(135deg, #FEF3C7 0%, #FDE68A 100%)',
        borderColor: '#FCD34D',
        name: 'Cesantías Anuales',
        baseLegal: 'Art. 249 C.S.T.',
        descripcion: 'Liquidación anual de cesantías'
    },
    // Intereses Cesantias
    'INTCESANTIAS': {
        icon: 'fa-line-chart',
        color: '#EA580C',
        gradient: 'linear-gradient(135deg, #FFEDD5 0%, #FED7AA 100%)',
        borderColor: '#FDBA74',
        name: 'Intereses sobre Cesantías',
        baseLegal: 'Ley 52/1975',
        descripcion: '12% anual sobre saldo de cesantías'
    },
    'INTCES_YEAR': {
        icon: 'fa-line-chart',
        color: '#EA580C',
        gradient: 'linear-gradient(135deg, #FFEDD5 0%, #FED7AA 100%)',
        borderColor: '#FDBA74',
        name: 'Intereses Cesantías Anuales',
        baseLegal: 'Ley 52/1975',
        descripcion: '12% anual, pago antes del 31 de enero'
    },
    // Vacaciones
    'VACCONTRATO': {
        icon: 'fa-sun-o',
        color: '#CA8A04',
        gradient: 'linear-gradient(135deg, #FEF9C3 0%, #FEF08A 100%)',
        borderColor: '#FDE047',
        name: 'Vacaciones por Contrato',
        baseLegal: 'Art. 186-192 C.S.T.',
        descripcion: '15 días hábiles por año de servicio'
    },
    'VACDISFRUTADAS': {
        icon: 'fa-sun-o',
        color: '#CA8A04',
        gradient: 'linear-gradient(135deg, #FEF9C3 0%, #FEF08A 100%)',
        borderColor: '#FDE047',
        name: 'Vacaciones Disfrutadas',
        baseLegal: 'Art. 186 C.S.T.',
        descripcion: 'Días de vacaciones tomados en el período'
    },
    'VACANOVE': {
        icon: 'fa-sun-o',
        color: '#CA8A04',
        gradient: 'linear-gradient(135deg, #FEF9C3 0%, #FEF08A 100%)',
        borderColor: '#FDE047',
        name: 'Vacaciones Novedad',
        baseLegal: 'Art. 186 C.S.T.',
        descripcion: 'Novedad de vacaciones en el período'
    },
    'VACATIONS_MONEY': {
        icon: 'fa-sun-o',
        color: '#CA8A04',
        gradient: 'linear-gradient(135deg, #FEF9C3 0%, #FEF08A 100%)',
        borderColor: '#FDE047',
        name: 'Vacaciones en Dinero',
        baseLegal: 'Art. 189 C.S.T.',
        descripcion: 'Compensación monetaria de vacaciones'
    },
    // Retenciones especiales
    'RET_PRIMA': {
        icon: 'fa-percent',
        color: '#DC2626',
        gradient: 'linear-gradient(135deg, #FEE2E2 0%, #FECACA 100%)',
        borderColor: '#FCA5A5',
        name: 'Retencion sobre Prima',
        baseLegal: 'Art. 385 E.T.',
        descripcion: 'Retencion aplicada a la prima de servicios'
    },
    'RTF_INDEM': {
        icon: 'fa-percent',
        color: '#DC2626',
        gradient: 'linear-gradient(135deg, #FEE2E2 0%, #FECACA 100%)',
        borderColor: '#FCA5A5',
        name: 'Retencion sobre Indemnizacion',
        baseLegal: 'Art. 401-3 E.T.',
        descripcion: 'Retencion aplicada a indemnizaciones'
    },
    // Preaviso
    'PREAVISO': {
        icon: 'fa-calendar-times-o',
        color: '#B91C1C',
        gradient: 'linear-gradient(135deg, #FEE2E2 0%, #FECACA 100%)',
        borderColor: '#FCA5A5',
        name: 'Preaviso',
        baseLegal: 'Art. 64 C.S.T.',
        descripcion: 'Indemnizacion por falta de preaviso'
    },
    // Provisiones especificas
    'PRV_PRIMA': {
        icon: 'fa-database',
        color: '#15803D',
        gradient: 'linear-gradient(135deg, #DCFCE7 0%, #BBF7D0 100%)',
        borderColor: '#86EFAC',
        name: 'Provision Prima',
        baseLegal: 'Art. 306 C.S.T.',
        tasa: 8.33
    },
    'PRV_CES': {
        icon: 'fa-database',
        color: '#D97706',
        gradient: 'linear-gradient(135deg, #FEF3C7 0%, #FDE68A 100%)',
        borderColor: '#FCD34D',
        name: 'Provision Cesantias',
        baseLegal: 'Art. 249 C.S.T.',
        tasa: 8.33
    },
    'PRV_ICES': {
        icon: 'fa-database',
        color: '#EA580C',
        gradient: 'linear-gradient(135deg, #FFEDD5 0%, #FED7AA 100%)',
        borderColor: '#FDBA74',
        name: 'Provision Int. Cesantias',
        baseLegal: 'Ley 52/1975',
        tasa: 1.0
    },
    'PRV_VAC': {
        icon: 'fa-database',
        color: '#CA8A04',
        gradient: 'linear-gradient(135deg, #FEF9C3 0%, #FEF08A 100%)',
        borderColor: '#FDE047',
        name: 'Provision Vacaciones',
        baseLegal: 'Art. 186-192 C.S.T.',
        tasa: 4.17
    },
};

/**
 * Colores para pasos del timeline
 */
export const STEP_COLORS = ['#3B82F6', '#8B5CF6', '#F97316', '#22C55E', '#EC4899', '#14B8A6', '#EF4444'];

/**
 * Obtiene la configuración de regla por código
 * @param {string} code - Código de la regla
 * @returns {Object} Configuración de la regla o configuración por defecto
 */
export function getRuleConfig(code) {
    const codeUpper = (code || '').toUpperCase();
    
    // Buscar coincidencia exacta
    if (RULE_CONFIG[codeUpper]) {
        return RULE_CONFIG[codeUpper];
    }
    
    // Buscar coincidencia parcial
    for (const [key, config] of Object.entries(RULE_CONFIG)) {
        if (codeUpper.includes(key) || codeUpper.startsWith(key)) {
            return config;
        }
    }
    
    // Retornar configuración por defecto según tipo
    return null; // El componente principal determinará el default según dev_or_ded
}
