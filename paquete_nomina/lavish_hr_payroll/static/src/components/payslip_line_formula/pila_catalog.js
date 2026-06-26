/** @odoo-module **/
/**
 * Catalogo de Constantes Legales y Tablas de Referencia
 * Para uso en el widget payslip_line_formula
 *
 * NOTA: Los datos de entidades (EPS, AFP, CCF, ARL) se obtienen
 * dinamicamente del sistema via RPC, no estan hardcodeados aqui.
 *
 * Fuentes:
 * - Resolucion 2388/2016 UGPP
 * - Resolucion 5858/2016 MinSalud
 * - Decreto 1833/2016
 * - Estatuto Tributario
 * - Codigo Sustantivo del Trabajo
 */

// ============================================================================
// CONSTANTES ANUALES 2025
// ============================================================================

export const SMMLV_2025 = 1423500;
export const UVT_2025 = 49799;
export const AUXILIO_TRANSPORTE_2025 = 200000;
export const TOPE_25_SMMLV = 25 * SMMLV_2025;
export const TOPE_4_FSP = 4 * SMMLV_2025;
export const TOPE_2_SMMLV = 2 * SMMLV_2025; // Limite auxilio transporte
export const TOPE_40_PERCENT = 0.4;

// ============================================================================
// TIPOS DE ENTIDAD (Metadata para UI)
// ============================================================================

export const TIPOS_ENTIDAD = {
    'EPS': { nombre: 'Entidad Promotora de Salud', abreviatura: 'EPS', icono: 'fa-hospital-alt' },
    'AFP': { nombre: 'Administradora Fondos Pensiones', abreviatura: 'AFP', icono: 'fa-university' },
    'RPM': { nombre: 'Regimen Prima Media', abreviatura: 'RPM', icono: 'fa-landmark' },
    'CCF': { nombre: 'Caja Compensacion Familiar', abreviatura: 'CCF', icono: 'fa-users' },
    'ARL': { nombre: 'Administradora Riesgos Laborales', abreviatura: 'ARL', icono: 'fa-hard-hat' },
    'FSP': { nombre: 'Fondo Solidaridad Pensional', abreviatura: 'FSP', icono: 'fa-hands-helping' },
    'SENA': { nombre: 'Servicio Nacional de Aprendizaje', abreviatura: 'SENA', icono: 'fa-graduation-cap' },
    'ICBF': { nombre: 'Instituto Colombiano Bienestar Familiar', abreviatura: 'ICBF', icono: 'fa-child' },
};

// ============================================================================
// TABLA FSP - Ley 797/2003 Art. 7
// ============================================================================

export const RANGOS_FSP = [
    { rango: '0 - 4', desde: 0, hasta: 4, solidaridad: 0, subsistencia: 0, total: 0 },
    { rango: '4 - 16', desde: 4, hasta: 16, solidaridad: 0.5, subsistencia: 0.5, total: 1.0 },
    { rango: '16 - 17', desde: 16, hasta: 17, solidaridad: 0.5, subsistencia: 0.7, total: 1.2 },
    { rango: '17 - 18', desde: 17, hasta: 18, solidaridad: 0.5, subsistencia: 0.9, total: 1.4 },
    { rango: '18 - 19', desde: 18, hasta: 19, solidaridad: 0.5, subsistencia: 1.1, total: 1.6 },
    { rango: '19 - 20', desde: 19, hasta: 20, solidaridad: 0.5, subsistencia: 1.3, total: 1.8 },
    { rango: '> 20', desde: 20, hasta: Infinity, solidaridad: 0.5, subsistencia: 1.5, total: 2.0 },
];

// ============================================================================
// TABLA RETENCION - Art. 383 ET
// ============================================================================

export const TABLA_RETENCION_383 = [
    { rango: '0 - 95', desde: 0, hasta: 95, tarifa: 0, adicional: 0 },
    { rango: '95 - 150', desde: 95, hasta: 150, tarifa: 19, adicional: 0 },
    { rango: '150 - 360', desde: 150, hasta: 360, tarifa: 28, adicional: 10.45 },
    { rango: '360 - 640', desde: 360, hasta: 640, tarifa: 33, adicional: 69.25 },
    { rango: '640 - 945', desde: 640, hasta: 945, tarifa: 35, adicional: 161.65 },
    { rango: '945 - 2300', desde: 945, hasta: 2300, tarifa: 37, adicional: 268.40 },
    { rango: '> 2300', desde: 2300, hasta: Infinity, tarifa: 39, adicional: 770.75 },
];

// ============================================================================
// PORCENTAJES SEGURIDAD SOCIAL 2025
// ============================================================================

export const PORCENTAJES_SS = {
    salud: {
        empleado: 4.0,
        empleador: 8.5,
        total: 12.5,
        baseLegal: 'Ley 1122/2007 Art. 10',
    },
    pension: {
        empleado: 4.0,
        empleador: 12.0,
        total: 16.0,
        baseLegal: 'Ley 797/2003 Art. 7',
    },
    arl: {
        empleado: 0,
        empleador: 'Variable', // 0.348% a 8.7% segun riesgo
        baseLegal: 'Decreto 1295/1994',
        clases: [
            { clase: 'I', riesgo: 'Minimo', tarifa: 0.522 },
            { clase: 'II', riesgo: 'Bajo', tarifa: 1.044 },
            { clase: 'III', riesgo: 'Medio', tarifa: 2.436 },
            { clase: 'IV', riesgo: 'Alto', tarifa: 4.350 },
            { clase: 'V', riesgo: 'Maximo', tarifa: 6.960 },
        ],
    },
    ccf: {
        empleado: 0,
        empleador: 4.0,
        baseLegal: 'Ley 21/1982',
    },
    sena: {
        empleado: 0,
        empleador: 2.0,
        baseLegal: 'Ley 21/1982',
    },
    icbf: {
        empleado: 0,
        empleador: 3.0,
        baseLegal: 'Ley 89/1988',
    },
};

// ============================================================================
// COLORES PARA UI POR TIPO DE APORTE
// ============================================================================

export const COLORES_APORTES = {
    'SALUD': { bg: '#F43F5E', bgLight: '#FFF1F2', text: '#BE123C', border: '#FDA4AF' },
    'PENSION': { bg: '#3B82F6', bgLight: '#EFF6FF', text: '#1D4ED8', border: '#93C5FD' },
    'FSP': { bg: '#8B5CF6', bgLight: '#F5F3FF', text: '#6D28D9', border: '#C4B5FD' },
    'ARL': { bg: '#10B981', bgLight: '#ECFDF5', text: '#047857', border: '#6EE7B7' },
    'CCF': { bg: '#F59E0B', bgLight: '#FFFBEB', text: '#B45309', border: '#FCD34D' },
    'SENA': { bg: '#06B6D4', bgLight: '#ECFEFF', text: '#0891B2', border: '#67E8F9' },
    'ICBF': { bg: '#EC4899', bgLight: '#FDF2F8', text: '#BE185D', border: '#F9A8D4' },
    'DEFAULT': { bg: '#6B7280', bgLight: '#F9FAFB', text: '#374151', border: '#D1D5DB' },
};

// ============================================================================
// REGLAS IBD CON REFERENCIAS LEGALES
// ============================================================================

export const REGLAS_IBD = {
    totalizar_salariales: {
        id: 'REGLA-SAL-001',
        nombre: 'Acumulacion Devengos Salariales',
        baseLegal: 'Art. 127 CST - Elementos constitutivos de salario',
        formula: 'salary = sum(Devengos donde base_seguridad_social = True)',
        icono: 'fa-coins',
        color: 'green',
    },
    totalizar_no_salariales: {
        id: 'REGLA-NOSAL-001',
        nombre: 'Acumulacion Devengos No Salariales',
        baseLegal: 'Art. 128 CST - Pagos no constitutivos de salario',
        formula: 'o_earnings = sum(Devengos donde category = DEV_NO_SALARIAL)',
        icono: 'fa-file-invoice-dollar',
        color: 'amber',
    },
    base_regla_40: {
        id: 'REGLA-40-001',
        nombre: 'Base Regla 40%',
        baseLegal: 'Art. 27 Ley 1393/2010',
        formula: 'salary_for_40 = salary + absences (si include_absences_1393)',
        icono: 'fa-balance-scale',
        color: 'purple',
    },
    tope_40: {
        id: 'REGLA-40-002',
        nombre: 'Tope 40% Remuneracion',
        baseLegal: 'Art. 27 Ley 1393/2010',
        formula: 'top40 = (salary_for_40 + o_earnings) * 0.40',
        icono: 'fa-percentage',
        color: 'orange',
    },
    evaluar_exceso: {
        id: 'REGLA-40-003',
        nombre: 'Evaluacion Exceso Ley 1393',
        baseLegal: 'Art. 27 Ley 1393/2010',
        formula: 'exceso = max(0, o_earnings - top40)',
        icono: 'fa-exclamation-triangle',
        color: 'red',
    },
    ibc_pre: {
        id: 'REGLA-IBC-001',
        nombre: 'IBC Preliminar',
        baseLegal: 'Art. 27 Ley 1393/2010',
        formula: 'ibc_pre = salary_for_40 + exceso + absences',
        icono: 'fa-calculator',
        color: 'indigo',
    },
    factor_integral: {
        id: 'REGLA-INT-001',
        nombre: 'Factor Salarial Integral',
        baseLegal: 'Art. 132 CST - Salario Integral',
        formula: 'ibc_pre = ibc_pre * 0.70',
        icono: 'fa-star',
        color: 'purple',
        condicion: 'Aplica si modality_salary == "integral"',
    },
    tope_25: {
        id: 'REGLA-TOPE-001',
        nombre: 'Tope Maximo IBC',
        baseLegal: 'Art. 30 Ley 1393/2010',
        formula: 'ibc_final = min(ibc_pre, 25 * SMMLV)',
        icono: 'fa-hand-paper',
        color: 'red',
    },
};

// ============================================================================
// REGLAS DE RETENCION EN LA FUENTE
// ============================================================================

export const REGLAS_RETENCION = {
    ingresos_laborales: {
        id: 'RT-ING-001',
        nombre: 'Ingresos Laborales Gravables',
        baseLegal: 'Art. 103 ET - Rentas de trabajo',
        formula: 'ing_base = salary + other_earnings',
        icono: 'fa-money-bill-wave',
        color: 'green',
    },
    deducciones_art_387: {
        id: 'RT-DED-001',
        nombre: 'Deducciones Art. 387 ET',
        baseLegal: 'Art. 387 ET - Deducciones',
        formula: 'deducciones = salud + pension + fsp + dependientes + prepagada + vivienda',
        icono: 'fa-minus-circle',
        color: 'amber',
        componentes: [
            { codigo: 'SALUD', nombre: 'Aporte Salud Empleado' },
            { codigo: 'PENSION', nombre: 'Aporte Pension Empleado' },
            { codigo: 'FSP', nombre: 'Fondo Solidaridad Pensional' },
            { codigo: 'DEPENDIENTES', nombre: 'Deduccion Dependientes', limite: '10% ing_bruto, max 32 UVT' },
            { codigo: 'PREPAGADA', nombre: 'Medicina Prepagada', limite: '16 UVT/mes' },
            { codigo: 'VIVIENDA', nombre: 'Intereses Vivienda/AFC', limite: '100 UVT/mes' },
        ],
    },
    rentas_exentas: {
        id: 'RT-REX-001',
        nombre: 'Rentas Exentas Art. 206',
        baseLegal: 'Art. 206 ET Numeral 10',
        formula: 'renta_exenta_25 = min(ibr1 * 0.25, 240 UVT)',
        icono: 'fa-gift',
        color: 'purple',
        limite: '240 UVT mensuales',
    },
    limite_40: {
        id: 'RT-LIM-001',
        nombre: 'Limite 40% Beneficios',
        baseLegal: 'Art. 388 ET - Limite de beneficios',
        formula: 'beneficios_limitados = min(total_beneficios, ing_base * 0.40)',
        icono: 'fa-percentage',
        color: 'orange',
    },
    tabla_383: {
        id: 'RT-TAB-001',
        nombre: 'Aplicar Tabla Art. 383',
        baseLegal: 'Art. 383 ET - Tabla de retencion',
        formula: 'retencion_uvt = (base_uvt - limite_inferior) * tarifa% + impuesto_adicional',
        icono: 'fa-table',
        color: 'indigo',
    },
};

// ============================================================================
// REGLAS DE PRESTACIONES SOCIALES
// ============================================================================

export const REGLAS_PRESTACIONES = {
    prima_calculo: {
        id: 'PREST-PRIM-001',
        nombre: 'Prima de Servicios',
        baseLegal: 'Art. 306 CST',
        formula: 'prima = (salario + aux_transporte) × dias / 360',
        icono: 'fa-gift',
        color: 'green',
        periodos: ['Junio (1er semestre)', 'Diciembre (2do semestre)'],
    },
    cesantias_calculo: {
        id: 'PREST-CES-001',
        nombre: 'Cesantias',
        baseLegal: 'Art. 249 CST',
        formula: 'cesantias = (salario + aux_transporte) × dias / 360',
        icono: 'fa-piggy-bank',
        color: 'blue',
        nota: 'Consignar antes del 14 de febrero',
    },
    int_cesantias_calculo: {
        id: 'PREST-ICES-001',
        nombre: 'Intereses Cesantias',
        baseLegal: 'Ley 52/1975',
        formula: 'intereses = cesantias × 12% × dias / 360',
        icono: 'fa-percentage',
        color: 'amber',
        nota: 'Tasa fija del 12% anual',
    },
    vacaciones_calculo: {
        id: 'PREST-VAC-001',
        nombre: 'Vacaciones',
        baseLegal: 'Art. 186 CST',
        formula: 'vacaciones = salario × dias / 720',
        icono: 'fa-umbrella-beach',
        color: 'cyan',
        nota: 'NO incluye auxilio de transporte',
    },
};

// ============================================================================
// REGLAS DE HORAS EXTRAS Y RECARGOS
// ============================================================================

export const REGLAS_HORAS_EXTRAS = {
    hora_ordinaria: {
        id: 'HE-ORD-001',
        nombre: 'Valor Hora Ordinaria',
        baseLegal: 'Art. 134 CST',
        formula: 'valor_hora = salario / 240',
        icono: 'fa-clock',
        color: 'gray',
        factor: 1.0,
    },
    he_diurna: {
        id: 'HE-DIA-001',
        nombre: 'Hora Extra Diurna',
        baseLegal: 'Art. 168 CST',
        formula: 'he_diurna = hora × 1.25',
        icono: 'fa-sun',
        color: 'amber',
        recargo: 25,
        horario: '6:00 - 21:00',
    },
    he_nocturna: {
        id: 'HE-NOC-001',
        nombre: 'Hora Extra Nocturna',
        baseLegal: 'Art. 168 CST',
        formula: 'he_nocturna = hora × 1.75',
        icono: 'fa-moon',
        color: 'indigo',
        recargo: 75,
        horario: '21:00 - 6:00',
    },
    he_diurna_festivo: {
        id: 'HE-DDF-001',
        nombre: 'HE Diurna Dom/Festivo',
        baseLegal: 'Art. 179 CST',
        formula: 'he_diurna_fest = hora × 2.00',
        icono: 'fa-calendar-day',
        color: 'orange',
        recargo: 100,
    },
    he_nocturna_festivo: {
        id: 'HE-NDF-001',
        nombre: 'HE Nocturna Dom/Festivo',
        baseLegal: 'Art. 179 CST',
        formula: 'he_nocturna_fest = hora × 2.50',
        icono: 'fa-star-and-crescent',
        color: 'purple',
        recargo: 150,
    },
    recargo_nocturno: {
        id: 'REC-NOC-001',
        nombre: 'Recargo Nocturno',
        baseLegal: 'Art. 168 CST',
        formula: 'recargo = hora × 0.35',
        icono: 'fa-moon',
        color: 'blue',
        recargo: 35,
    },
    recargo_dominical: {
        id: 'REC-DOM-001',
        nombre: 'Recargo Dominical/Festivo',
        baseLegal: 'Art. 179 CST',
        formula: 'recargo = hora × 0.75',
        icono: 'fa-calendar-check',
        color: 'green',
        recargo: 75,
    },
};

// ============================================================================
// REGLAS DE AUXILIOS
// ============================================================================

export const REGLAS_AUXILIOS = {
    auxilio_transporte: {
        id: 'AUX-TRA-001',
        nombre: 'Auxilio de Transporte',
        baseLegal: 'Ley 15/1959, Decreto anual',
        formula: 'auxilio = valor_mensual × dias / 30',
        icono: 'fa-bus',
        color: 'blue',
        valor_2025: AUXILIO_TRANSPORTE_2025,
        condicion: 'Aplica si salario <= 2 SMMLV',
    },
    auxilio_conectividad: {
        id: 'AUX-CON-001',
        nombre: 'Auxilio de Conectividad',
        baseLegal: 'Ley 2088/2021',
        formula: 'auxilio = valor_transporte',
        icono: 'fa-wifi',
        color: 'cyan',
        condicion: 'Aplica en teletrabajo si salario <= 2 SMMLV',
    },
};

// ============================================================================
// PORCENTAJES PROVISIONES PRESTACIONES SOCIALES
// ============================================================================

export const PORCENTAJES_PROVISION = {
    cesantias: {
        id: 'PROV-CES',
        nombre: 'Cesantias',
        porcentaje: 8.33,
        baseLegal: 'Art. 249 CST',
        formula: 'provision = (salario + aux_transporte) × 8.33%',
        incluyeAuxTransporte: true,
        cuentaGasto: '510530',
        cuentaPasivo: '261005',
    },
    int_cesantias: {
        id: 'PROV-ICES',
        nombre: 'Intereses Cesantias',
        porcentaje: 1.00,
        baseLegal: 'Ley 52/1975',
        formula: 'provision = cesantias_mes × 1%',
        incluyeAuxTransporte: true,
        cuentaGasto: '510533',
        cuentaPasivo: '261010',
    },
    prima: {
        id: 'PROV-PRIM',
        nombre: 'Prima de Servicios',
        porcentaje: 8.33,
        baseLegal: 'Art. 306 CST',
        formula: 'provision = (salario + aux_transporte) × 8.33%',
        incluyeAuxTransporte: true,
        cuentaGasto: '510536',
        cuentaPasivo: '261015',
    },
    vacaciones: {
        id: 'PROV-VAC',
        nombre: 'Vacaciones',
        porcentaje: 4.17,
        baseLegal: 'Art. 186 CST',
        formula: 'provision = salario_basico × 4.17%',
        incluyeAuxTransporte: false,
        cuentaGasto: '510539',
        cuentaPasivo: '261020',
        nota: 'Solo salario basico, SIN variables ni auxilio transporte',
    },
    total: {
        nombre: 'Total Provision Mensual',
        porcentaje: 21.83,
        desglose: 'Cesantias 8.33% + Int.Ces 1% + Prima 8.33% + Vacaciones 4.17%',
    },
};

// ============================================================================
// REGLAS LIQUIDACION DEFINITIVA
// ============================================================================

export const REGLAS_LIQUIDACION = {
    salario_proporcional: {
        id: 'LIQ-SAL-001',
        nombre: 'Salario Proporcional',
        baseLegal: 'Art. 65 CST',
        formula: 'salario × (dias_trabajados / 30)',
        icono: 'fa-money-bill',
        color: 'green',
    },
    prima_proporcional: {
        id: 'LIQ-PRIM-001',
        nombre: 'Prima Proporcional',
        baseLegal: 'Art. 306 CST',
        formula: '(salario + aux_transporte) × dias_semestre / 360',
        icono: 'fa-gift',
        color: 'green',
        nota: 'Dias desde 1-Ene o 1-Jul hasta fecha retiro',
    },
    cesantias_proporcional: {
        id: 'LIQ-CES-001',
        nombre: 'Cesantias Proporcionales',
        baseLegal: 'Art. 249 CST, Ley 50/1990',
        formula: '(salario + aux_transporte) × dias_año / 360',
        icono: 'fa-piggy-bank',
        color: 'blue',
        nota: 'Dias desde 1-Ene hasta fecha retiro',
    },
    int_cesantias_proporcional: {
        id: 'LIQ-ICES-001',
        nombre: 'Intereses Cesantias',
        baseLegal: 'Ley 52/1975',
        formula: 'cesantias × dias × 12% / 360',
        icono: 'fa-percentage',
        color: 'amber',
    },
    vacaciones_compensadas: {
        id: 'LIQ-VAC-001',
        nombre: 'Vacaciones Compensadas',
        baseLegal: 'Art. 186-192 CST',
        formula: 'salario_basico × dias_pendientes / 30',
        icono: 'fa-umbrella-beach',
        color: 'cyan',
        nota: 'Solo salario basico, SIN variables ni auxilio',
    },
    dias_vacaciones: {
        id: 'LIQ-DVA-001',
        nombre: 'Dias Vacaciones Causados',
        baseLegal: 'Art. 186 CST',
        formula: 'dias_totales × 15 / 360',
        icono: 'fa-calendar-alt',
        color: 'cyan',
        nota: '15 dias habiles por cada 360 dias trabajados',
    },
};

// ============================================================================
// REGLAS INDEMNIZACION - Art. 64 CST
// ============================================================================

export const REGLAS_INDEMNIZACION = {
    contrato_indefinido_bajo: {
        id: 'IND-INB-001',
        nombre: 'Indemnizacion Contrato Indefinido (<= 10 SMMLV)',
        baseLegal: 'Art. 64 CST, Literal A',
        formula: '30 dias + (20 dias × años_adicionales)',
        icono: 'fa-file-contract',
        color: 'red',
        condicion: 'Salario <= 10 SMMLV',
        estructura: [
            { concepto: 'Primer año', dias: 30, nota: '30 dias de salario' },
            { concepto: 'Años adicionales', dias: 20, nota: '20 dias por cada año adicional' },
        ],
    },
    contrato_indefinido_alto: {
        id: 'IND-INA-001',
        nombre: 'Indemnizacion Contrato Indefinido (> 10 SMMLV)',
        baseLegal: 'Art. 64 CST, Literal A',
        formula: '20 dias + (15 dias × años_adicionales)',
        icono: 'fa-file-contract',
        color: 'purple',
        condicion: 'Salario > 10 SMMLV',
        estructura: [
            { concepto: 'Primer año', dias: 20, nota: '20 dias de salario' },
            { concepto: 'Años adicionales', dias: 15, nota: '15 dias por cada año adicional' },
        ],
    },
    contrato_fijo: {
        id: 'IND-FIJ-001',
        nombre: 'Indemnizacion Contrato Fijo',
        baseLegal: 'Art. 64 CST, Literal B',
        formula: 'salario_dia × dias_faltantes_contrato',
        icono: 'fa-calendar-times',
        color: 'orange',
        nota: 'Tiempo faltante para vencer el contrato, nunca menor a 15 dias',
    },
    contrato_obra: {
        id: 'IND-OBR-001',
        nombre: 'Indemnizacion Contrato Obra',
        baseLegal: 'Art. 64 CST, Literal C',
        formula: 'salario_dia × dias_tiempo_faltante_obra',
        icono: 'fa-tools',
        color: 'amber',
        nota: 'Tiempo estimado faltante para culminar la obra, minimo 15 dias',
    },
    nota_fiscal: {
        id: 'IND-NF-001',
        nombre: 'Tratamiento Fiscal Indemnizacion',
        baseLegal: 'Art. 401-3 ET',
        nota: 'Indemnizacion NO hace base para aportes SS pero SI esta sujeta a retencion fuente',
    },
};

// ============================================================================
// REGLAS VARIACION AUXILIO TRANSPORTE
// ============================================================================

export const REGLAS_VARIACION_AUX_TRANSPORTE = {
    aplica_auxilio: {
        id: 'VAT-APL-001',
        nombre: 'Condicion de Aplicacion',
        baseLegal: 'Ley 15/1959',
        formula: 'aplica = salario_base <= (2 × SMMLV)',
        icono: 'fa-bus',
        color: 'blue',
        tope_2025: TOPE_2_SMMLV,
    },
    variacion_salario_mes: {
        id: 'VAT-VSM-001',
        nombre: 'Variacion por Cambio Salario',
        baseLegal: 'Ley 15/1959',
        casos: [
            {
                caso: 'Aumento por encima de 2 SMMLV',
                efecto: 'Pierde derecho desde fecha del aumento',
                formula: 'aux = valor × dias_antes_aumento / 30',
            },
            {
                caso: 'Reduccion por debajo de 2 SMMLV',
                efecto: 'Adquiere derecho desde fecha de reduccion',
                formula: 'aux = valor × dias_despues_reduccion / 30',
            },
        ],
    },
    variacion_incapacidad: {
        id: 'VAT-INC-001',
        nombre: 'Variacion por Incapacidad',
        baseLegal: 'CST Art. 227, Decreto 770/2022',
        casos: [
            {
                caso: 'Incapacidad total del periodo',
                efecto: 'NO aplica auxilio transporte',
                formula: 'aux = 0',
            },
            {
                caso: 'Incapacidad parcial',
                efecto: 'Proporcional a dias laborados',
                formula: 'aux = valor × dias_laborados / 30',
            },
        ],
    },
    variacion_licencia: {
        id: 'VAT-LIC-001',
        nombre: 'Variacion por Licencias',
        baseLegal: 'CST',
        casos: [
            {
                tipo: 'Licencia No Remunerada',
                efecto: 'NO aplica auxilio',
                formula: 'aux = valor × (30 - dias_licencia) / 30',
            },
            {
                tipo: 'Licencia Maternidad/Paternidad',
                efecto: 'SI aplica auxilio (paga EPS)',
                formula: 'aux = valor_completo',
            },
        ],
    },
    variacion_suspension: {
        id: 'VAT-SUS-001',
        nombre: 'Variacion por Suspension',
        baseLegal: 'CST Art. 51',
        efecto: 'NO aplica auxilio en dias de suspension',
        formula: 'aux = valor × (30 - dias_suspension) / 30',
    },
    para_prestaciones: {
        id: 'VAT-PRE-001',
        nombre: 'Auxilio en Prestaciones',
        baseLegal: 'Art. 7 Ley 1/1963',
        casos: [
            { prestacion: 'Cesantias', incluye: true },
            { prestacion: 'Int. Cesantias', incluye: true },
            { prestacion: 'Prima', incluye: true },
            { prestacion: 'Vacaciones', incluye: false, nota: 'No incluye aux.transporte' },
        ],
    },
};

// ============================================================================
// TABLAS RESUMEN DEVENGOS Y DEDUCCIONES
// ============================================================================

export const CATEGORIAS_NOMINA = {
    devengos_salariales: {
        id: 'CAT-DEV-SAL',
        nombre: 'Devengos Salariales',
        baseLegal: 'Art. 127 CST',
        color: 'green',
        incluyeEnIBD: true,
        conceptos: [
            { codigo: 'BASICO', nombre: 'Salario Basico', tipo: 'fijo' },
            { codigo: 'COMISION', nombre: 'Comisiones', tipo: 'variable' },
            { codigo: 'HE', nombre: 'Horas Extras', tipo: 'variable' },
            { codigo: 'RECARGO', nombre: 'Recargos', tipo: 'variable' },
            { codigo: 'BONIF_SAL', nombre: 'Bonificaciones Salariales', tipo: 'variable' },
            { codigo: 'INCEN_SAL', nombre: 'Incentivos Salariales', tipo: 'variable' },
        ],
    },
    devengos_no_salariales: {
        id: 'CAT-DEV-NOSAL',
        nombre: 'Devengos No Salariales',
        baseLegal: 'Art. 128 CST',
        color: 'amber',
        incluyeEnIBD: false,
        limite40: true,
        conceptos: [
            { codigo: 'AUX_ALIM', nombre: 'Auxilio Alimentacion', tipo: 'fijo' },
            { codigo: 'AUX_VEST', nombre: 'Auxilio Vestuario', tipo: 'fijo' },
            { codigo: 'BONIF_NOSAL', nombre: 'Bonificaciones No Salariales', tipo: 'variable' },
            { codigo: 'PRIMA_NOSAL', nombre: 'Primas Extralegales No Salariales', tipo: 'variable' },
        ],
    },
    auxilios: {
        id: 'CAT-AUX',
        nombre: 'Auxilios Legales',
        color: 'blue',
        conceptos: [
            { codigo: 'AUX_TRANS', nombre: 'Auxilio Transporte', condicion: '<= 2 SMMLV', enPrestaciones: 'Cesantias, Prima' },
            { codigo: 'AUX_CONEC', nombre: 'Auxilio Conectividad', condicion: 'Teletrabajo', enPrestaciones: 'Cesantias, Prima' },
        ],
    },
    prestaciones: {
        id: 'CAT-PREST',
        nombre: 'Prestaciones Sociales',
        color: 'purple',
        conceptos: [
            { codigo: 'PRIMA', nombre: 'Prima de Servicios', periodo: 'Semestral' },
            { codigo: 'CESANTIAS', nombre: 'Cesantias', periodo: 'Anual' },
            { codigo: 'INT_CES', nombre: 'Intereses Cesantias', periodo: 'Anual' },
            { codigo: 'VACACIONES', nombre: 'Vacaciones', periodo: '15 dias/año' },
        ],
    },
    deducciones_ley: {
        id: 'CAT-DED-LEY',
        nombre: 'Deducciones de Ley',
        color: 'red',
        conceptos: [
            { codigo: 'SALUD', nombre: 'Aporte Salud', porcentaje: 4.0 },
            { codigo: 'PENSION', nombre: 'Aporte Pension', porcentaje: 4.0 },
            { codigo: 'FSP', nombre: 'Fondo Solidaridad', condicion: '> 4 SMMLV' },
            { codigo: 'RETENCION', nombre: 'Retencion Fuente', condicion: 'Segun tabla 383' },
        ],
    },
    deducciones_voluntarias: {
        id: 'CAT-DED-VOL',
        nombre: 'Deducciones Voluntarias',
        color: 'orange',
        conceptos: [
            { codigo: 'COOP', nombre: 'Aportes Cooperativas' },
            { codigo: 'PREST_EMP', nombre: 'Prestamos Empresa' },
            { codigo: 'EMBARGO', nombre: 'Embargos Judiciales', limite: '50% neto' },
            { codigo: 'LIBRANZA', nombre: 'Libranzas', limite: '50% neto' },
        ],
    },
};

// ============================================================================
// REGLAS CONSOLIDACION
// ============================================================================

export const REGLAS_CONSOLIDACION = {
    consolidado_periodo: {
        id: 'CON-PER-001',
        nombre: 'Consolidacion por Periodo',
        baseLegal: 'Art. 127 CST',
        formula: 'consolidado = Σ(valores_mensuales)',
        icono: 'fa-layer-group',
        color: 'indigo',
    },
    promedio_variable: {
        id: 'CON-PVAR-001',
        nombre: 'Promedio Variable',
        baseLegal: 'CST Art. 127',
        formula: 'promedio = Σ(variables_periodo) / meses_periodo',
        icono: 'fa-chart-line',
        color: 'cyan',
        nota: 'Para prestaciones usar ultimos 3, 6 o 12 meses segun caso',
    },
    ibc_promedio: {
        id: 'CON-IBC-001',
        nombre: 'IBC Promedio',
        baseLegal: 'Ley 1393/2010',
        formula: 'ibc_prom = Σ(ibc_mensuales) / meses',
        icono: 'fa-calculator',
        color: 'blue',
    },
    base_prestaciones_promedio: {
        id: 'CON-BPP-001',
        nombre: 'Base Prestaciones Promedio',
        baseLegal: 'CST',
        formula: 'base_prest = salario_promedio + aux_transporte (si aplica)',
        icono: 'fa-balance-scale',
        color: 'green',
    },
};

// ============================================================================
// FUNCIONES HELPER
// ============================================================================

/**
 * Obtiene el rango FSP aplicable segun el IBC en SMMLV
 */
export function getRangoFSP(ibcEnSmmlv) {
    return RANGOS_FSP.find(r => ibcEnSmmlv > r.desde && ibcEnSmmlv <= r.hasta) || RANGOS_FSP[0];
}

/**
 * Calcula provision mensual de prestaciones
 * @param {number} salarioBase - Salario basico mensual
 * @param {number} variables - Promedio de variables (comisiones, HE, etc.)
 * @param {boolean} aplicaAuxTransporte - Si el empleado tiene derecho a auxilio
 * @returns {Object} - Desglose de provisiones
 */
export function calcularProvisionMensual(salarioBase, variables = 0, aplicaAuxTransporte = true) {
    const salarioTotal = salarioBase + variables;
    const auxTransporte = aplicaAuxTransporte ? AUXILIO_TRANSPORTE_2025 : 0;
    const basePrestaciones = salarioTotal + auxTransporte;

    const cesantias = basePrestaciones * 0.0833;
    const intCesantias = cesantias * 0.01;
    const prima = basePrestaciones * 0.0833;
    const vacaciones = salarioBase * 0.0417; // Solo salario basico

    return {
        salarioBase,
        variables,
        auxTransporte,
        basePrestaciones,
        baseVacaciones: salarioBase,
        provisiones: {
            cesantias: Math.round(cesantias),
            intCesantias: Math.round(intCesantias),
            prima: Math.round(prima),
            vacaciones: Math.round(vacaciones),
        },
        totalProvision: Math.round(cesantias + intCesantias + prima + vacaciones),
        porcentajeTotal: 21.83,
    };
}

/**
 * Calcula dias de indemnizacion segun Art. 64 CST
 * @param {number} salarioMensual - Salario mensual del trabajador
 * @param {number} diasTrabajados - Dias totales trabajados
 * @param {string} tipoContrato - 'indefinido' | 'fijo' | 'obra'
 * @param {number} diasRestantesContrato - Para contrato fijo, dias que faltan
 * @returns {Object} - Calculo de indemnizacion
 */
export function calcularIndemnizacion(salarioMensual, diasTrabajados, tipoContrato = 'indefinido', diasRestantesContrato = 0) {
    const salarioDia = salarioMensual / 30;
    const añosTrabajados = diasTrabajados / 360;
    const añosCompletos = Math.floor(añosTrabajados);
    const fraccionAño = añosTrabajados - añosCompletos;
    const tope10SMMLV = 10 * SMMLV_2025;

    let diasIndemnizacion = 0;
    let reglaAplicada = '';
    let estructura = [];

    if (tipoContrato === 'indefinido') {
        if (salarioMensual <= tope10SMMLV) {
            // Salario <= 10 SMMLV
            reglaAplicada = 'Art. 64 CST, Literal A (Salario <= 10 SMMLV)';
            const diasPrimerAño = 30;
            const diasAdicionales = Math.max(0, añosCompletos - 1) * 20;
            const diasFraccion = fraccionAño * 20;
            diasIndemnizacion = diasPrimerAño + diasAdicionales + diasFraccion;

            estructura = [
                { concepto: 'Primer año', dias: diasPrimerAño },
                { concepto: `Años adicionales (${Math.max(0, añosCompletos - 1)} × 20)`, dias: diasAdicionales },
                { concepto: `Fraccion año (${(fraccionAño * 12).toFixed(2)} meses)`, dias: Math.round(diasFraccion * 100) / 100 },
            ];
        } else {
            // Salario > 10 SMMLV
            reglaAplicada = 'Art. 64 CST, Literal A (Salario > 10 SMMLV)';
            const diasPrimerAño = 20;
            const diasAdicionales = Math.max(0, añosCompletos - 1) * 15;
            const diasFraccion = fraccionAño * 15;
            diasIndemnizacion = diasPrimerAño + diasAdicionales + diasFraccion;

            estructura = [
                { concepto: 'Primer año', dias: diasPrimerAño },
                { concepto: `Años adicionales (${Math.max(0, añosCompletos - 1)} × 15)`, dias: diasAdicionales },
                { concepto: `Fraccion año (${(fraccionAño * 12).toFixed(2)} meses)`, dias: Math.round(diasFraccion * 100) / 100 },
            ];
        }
    } else if (tipoContrato === 'fijo') {
        reglaAplicada = 'Art. 64 CST, Literal B (Contrato Fijo)';
        diasIndemnizacion = Math.max(15, diasRestantesContrato);
        estructura = [
            { concepto: 'Dias restantes contrato', dias: diasRestantesContrato },
            { concepto: 'Minimo legal', dias: 15 },
            { concepto: 'Dias a pagar', dias: diasIndemnizacion },
        ];
    } else if (tipoContrato === 'obra') {
        reglaAplicada = 'Art. 64 CST, Literal C (Contrato Obra)';
        diasIndemnizacion = Math.max(15, diasRestantesContrato);
        estructura = [
            { concepto: 'Tiempo estimado restante obra', dias: diasRestantesContrato },
            { concepto: 'Minimo legal', dias: 15 },
            { concepto: 'Dias a pagar', dias: diasIndemnizacion },
        ];
    }

    return {
        salarioMensual,
        salarioDia,
        diasTrabajados,
        añosTrabajados: Math.round(añosTrabajados * 100) / 100,
        tipoContrato,
        reglaAplicada,
        diasIndemnizacion: Math.round(diasIndemnizacion * 100) / 100,
        valorIndemnizacion: Math.round(diasIndemnizacion * salarioDia),
        estructura,
        notaFiscal: 'Indemnizacion NO hace base SS pero SI retencion fuente (Art. 401-3 ET)',
    };
}

/**
 * Evalua si aplica auxilio de transporte y calcula variaciones
 * @param {number} salarioBase - Salario basico mensual
 * @param {number} diasTrabajados - Dias efectivamente laborados
 * @param {Object} novedades - { incapacidad, licencia, suspension }
 * @returns {Object} - Calculo de auxilio con variaciones
 */
export function evaluarAuxilioTransporte(salarioBase, diasTrabajados = 30, novedades = {}) {
    const aplicaBase = salarioBase <= TOPE_2_SMMLV;
    const valorMensual = AUXILIO_TRANSPORTE_2025;

    let diasConDerecho = diasTrabajados;
    const variaciones = [];

    // Evaluar novedades
    if (novedades.incapacidad > 0) {
        diasConDerecho -= novedades.incapacidad;
        variaciones.push({
            tipo: 'Incapacidad',
            dias: novedades.incapacidad,
            efecto: 'Reduce dias con derecho',
            baseLegal: 'CST Art. 227',
        });
    }

    if (novedades.licenciaNoRemunerada > 0) {
        diasConDerecho -= novedades.licenciaNoRemunerada;
        variaciones.push({
            tipo: 'Licencia No Remunerada',
            dias: novedades.licenciaNoRemunerada,
            efecto: 'Reduce dias con derecho',
            baseLegal: 'CST',
        });
    }

    if (novedades.suspension > 0) {
        diasConDerecho -= novedades.suspension;
        variaciones.push({
            tipo: 'Suspension',
            dias: novedades.suspension,
            efecto: 'Reduce dias con derecho',
            baseLegal: 'CST Art. 51',
        });
    }

    // Licencia maternidad/paternidad SI paga auxilio (lo paga EPS)
    if (novedades.licenciaMaternidad > 0) {
        variaciones.push({
            tipo: 'Licencia Maternidad/Paternidad',
            dias: novedades.licenciaMaternidad,
            efecto: 'Conserva derecho (paga EPS)',
            baseLegal: 'Ley 1822/2017',
        });
    }

    diasConDerecho = Math.max(0, diasConDerecho);
    const valorCalculado = aplicaBase ? Math.round(valorMensual * diasConDerecho / 30) : 0;

    return {
        salarioBase,
        tope2SMMLV: TOPE_2_SMMLV,
        aplicaBase,
        motivoNoAplica: !aplicaBase ? 'Salario supera 2 SMMLV' : null,
        diasTrabajados,
        diasConDerecho,
        variaciones,
        valorMensual,
        valorCalculado,
        paraPrestaciones: {
            cesantias: true,
            intCesantias: true,
            prima: true,
            vacaciones: false,
        },
    };
}

/**
 * Calcula liquidacion proporcional de prestaciones
 * @param {Object} params - Parametros del calculo
 * @returns {Object} - Liquidacion detallada
 */
export function calcularLiquidacionProporcional(params) {
    const {
        salarioBase,
        promedioVariables = 0,
        auxTransporte = 0,
        fechaIngreso,
        fechaRetiro,
        diasVacacionesDisfrutadas = 0,
    } = params;

    const fechaIni = new Date(fechaIngreso);
    const fechaFin = new Date(fechaRetiro);

    // Calcular dias totales trabajados
    const diasTotales = Math.floor((fechaFin - fechaIni) / (1000 * 60 * 60 * 24)) + 1;

    // Dias del año actual (desde 1 de enero)
    const inicioAño = new Date(fechaFin.getFullYear(), 0, 1);
    const diasAño = Math.floor((fechaFin - inicioAño) / (1000 * 60 * 60 * 24)) + 1;

    // Dias del semestre actual
    const esPrimerSemestre = fechaFin.getMonth() < 6;
    const inicioSemestre = esPrimerSemestre
        ? new Date(fechaFin.getFullYear(), 0, 1)
        : new Date(fechaFin.getFullYear(), 6, 1);
    const diasSemestre = Math.floor((fechaFin - inicioSemestre) / (1000 * 60 * 60 * 24)) + 1;

    // Dias del mes
    const diasMes = fechaFin.getDate();

    const salarioTotal = salarioBase + promedioVariables;
    const basePrestaciones = salarioTotal + auxTransporte;

    // Calculos
    const salarioProporcional = Math.round(salarioTotal * diasMes / 30);
    const primaProporcional = Math.round(basePrestaciones * diasSemestre / 360);
    const cesantiasProporcional = Math.round(basePrestaciones * diasAño / 360);
    const intCesantias = Math.round(cesantiasProporcional * diasAño * 0.12 / 360);

    // Vacaciones
    const diasVacacionesCausadas = diasTotales * 15 / 360;
    const diasVacacionesPendientes = Math.max(0, diasVacacionesCausadas - diasVacacionesDisfrutadas);
    const vacacionesCompensadas = Math.round(salarioBase * diasVacacionesPendientes / 30);

    const totalDevengos = salarioProporcional + primaProporcional + cesantiasProporcional + intCesantias + vacacionesCompensadas;

    return {
        datosBase: {
            salarioBase,
            promedioVariables,
            salarioTotal,
            auxTransporte,
            basePrestaciones,
            baseVacaciones: salarioBase,
        },
        periodos: {
            diasTotales,
            diasAño,
            diasSemestre,
            diasMes,
        },
        conceptos: {
            salarioProporcional: {
                valor: salarioProporcional,
                dias: diasMes,
                formula: `${salarioTotal.toLocaleString()} × ${diasMes}/30`,
            },
            primaProporcional: {
                valor: primaProporcional,
                dias: diasSemestre,
                formula: `${basePrestaciones.toLocaleString()} × ${diasSemestre}/360`,
            },
            cesantiasProporcional: {
                valor: cesantiasProporcional,
                dias: diasAño,
                formula: `${basePrestaciones.toLocaleString()} × ${diasAño}/360`,
            },
            intCesantias: {
                valor: intCesantias,
                formula: `${cesantiasProporcional.toLocaleString()} × ${diasAño} × 12%/360`,
            },
            vacacionesCompensadas: {
                valor: vacacionesCompensadas,
                diasCausadas: Math.round(diasVacacionesCausadas * 100) / 100,
                diasDisfrutadas: diasVacacionesDisfrutadas,
                diasPendientes: Math.round(diasVacacionesPendientes * 100) / 100,
                formula: `${salarioBase.toLocaleString()} × ${diasVacacionesPendientes.toFixed(2)}/30`,
            },
        },
        totalDevengos,
    };
}

/**
 * Obtiene el rango de retencion segun UVTs
 */
export function getRangoRetencion(uvts) {
    return TABLA_RETENCION_383.find(r => uvts > r.desde && uvts <= r.hasta) || TABLA_RETENCION_383[0];
}

/**
 * Obtiene informacion del tipo de entidad
 */
export function getTipoEntidad(tipo) {
    return TIPOS_ENTIDAD[tipo] || { nombre: tipo, abreviatura: tipo, icono: 'fa-building' };
}

/**
 * Obtiene colores para un tipo de aporte
 */
export function getColoresAporte(tipo) {
    // Normalizar tipo
    const tipoNorm = (tipo || '').toUpperCase();
    if (tipoNorm.includes('SALUD')) return COLORES_APORTES['SALUD'];
    if (tipoNorm.includes('PENSION')) return COLORES_APORTES['PENSION'];
    if (tipoNorm.includes('FSP') || tipoNorm.includes('SOLIDARIDAD')) return COLORES_APORTES['FSP'];
    if (tipoNorm.includes('ARL') || tipoNorm.includes('RIESGO')) return COLORES_APORTES['ARL'];
    if (tipoNorm.includes('CCF') || tipoNorm.includes('CAJA')) return COLORES_APORTES['CCF'];
    if (tipoNorm.includes('SENA')) return COLORES_APORTES['SENA'];
    if (tipoNorm.includes('ICBF')) return COLORES_APORTES['ICBF'];
    return COLORES_APORTES['DEFAULT'];
}

/**
 * Obtiene regla por tipo y ID
 */
export function getRegla(tipo, reglaId) {
    const catalogos = {
        'ibd': REGLAS_IBD,
        'retencion': REGLAS_RETENCION,
        'prestaciones': REGLAS_PRESTACIONES,
        'horas_extras': REGLAS_HORAS_EXTRAS,
        'auxilios': REGLAS_AUXILIOS,
    };
    const catalogo = catalogos[tipo];
    return catalogo ? catalogo[reglaId] || null : null;
}

/**
 * Obtiene todas las reglas de un tipo
 */
export function getReglasByTipo(tipo) {
    const catalogos = {
        'ibd': REGLAS_IBD,
        'retencion': REGLAS_RETENCION,
        'prestaciones': REGLAS_PRESTACIONES,
        'horas_extras': REGLAS_HORAS_EXTRAS,
        'auxilios': REGLAS_AUXILIOS,
    };
    return catalogos[tipo] || {};
}

/**
 * Factor de hora extra segun codigo
 */
export function getFactorHoraExtra(codigo) {
    const factores = {
        'HED': 1.25,   // Diurna
        'HEN': 1.75,   // Nocturna
        'HEDD': 2.00,  // Diurna Dominical
        'HEND': 2.50,  // Nocturna Dominical
        'RN': 0.35,    // Recargo Nocturno
        'RD': 0.75,    // Recargo Dominical
        'RDN': 1.10,   // Recargo Dominical Nocturno
    };
    return factores[codigo] || 1.0;
}

/**
 * Convierte valor a UVT
 */
export function toUVT(valor) {
    return valor / UVT_2025;
}

/**
 * Convierte UVT a valor en pesos
 */
export function fromUVT(uvt) {
    return uvt * UVT_2025;
}

/**
 * Convierte valor a SMMLV
 */
export function toSMMLV(valor) {
    return valor / SMMLV_2025;
}

// ============================================================================
// EXPORT DEFAULT
// ============================================================================

export default {
    // Constantes
    SMMLV_2025,
    UVT_2025,
    AUXILIO_TRANSPORTE_2025,
    TOPE_25_SMMLV,
    TOPE_4_FSP,
    TOPE_2_SMMLV,
    // Metadata
    TIPOS_ENTIDAD,
    // Tablas
    RANGOS_FSP,
    TABLA_RETENCION_383,
    PORCENTAJES_SS,
    COLORES_APORTES,
    // Reglas
    REGLAS_IBD,
    REGLAS_RETENCION,
    REGLAS_PRESTACIONES,
    REGLAS_HORAS_EXTRAS,
    REGLAS_AUXILIOS,
    // Provisiones y Liquidacion
    PORCENTAJES_PROVISION,
    REGLAS_LIQUIDACION,
    REGLAS_INDEMNIZACION,
    REGLAS_VARIACION_AUX_TRANSPORTE,
    CATEGORIAS_NOMINA,
    REGLAS_CONSOLIDACION,
    // Funciones
    getRangoFSP,
    getRangoRetencion,
    getTipoEntidad,
    getColoresAporte,
    getRegla,
    getReglasByTipo,
    getFactorHoraExtra,
    toUVT,
    fromUVT,
    toSMMLV,
    // Funciones de calculo
    calcularProvisionMensual,
    calcularIndemnizacion,
    evaluarAuxilioTransporte,
    calcularLiquidacionProporcional,
};
