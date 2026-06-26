/** @odoo-module **/

/**
 * ═══════════════════════════════════════════════════════════════════════════
 * REGISTRO DE TEMPLATES PARA REGLAS SALARIALES
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * Este módulo proporciona un sistema extensible de hooks/templates para
 * personalizar la visualización de cada regla salarial en el widget
 * PayslipLineFormula.
 *
 * ARQUITECTURA:
 * - Cada regla puede tener su propio template y procesador de datos
 * - Los templates se registran por código de regla o patrón
 * - Soporta herencia y extensión de templates base
 *
 * USO:
 * ```javascript
 * import { RuleTemplateRegistry } from './rule_template_registry';
 *
 * RuleTemplateRegistry.register('RT_MET_01', {
 *     templateName: 'lavish_hr_payroll.RuleTemplate.Retencion',
 *     processor: (line, computation, state) => processedData,
 *     config: { ... }
 * });
 * ```
 */

export const RuleTemplateRegistry = {
    _templates: {},
    _patterns: [],
    _processors: {},
    _configs: {},

    /**
     * Registra un template para una regla específica o patrón
     * @param {string} codeOrPattern - Código de regla o patrón regex
     * @param {Object} options - Configuración del template
     */
    register(codeOrPattern, options = {}) {
        const {
            templateName = null,
            processor = null,
            config = {},
            priority = 10,
            isPattern = false,
        } = options;

        if (isPattern) {
            this._patterns.push({
                pattern: new RegExp(codeOrPattern),
                templateName,
                processor,
                config,
                priority,
            });
            // Ordenar patrones por prioridad (mayor primero)
            this._patterns.sort((a, b) => b.priority - a.priority);
        } else {
            this._templates[codeOrPattern] = templateName;
            if (processor) this._processors[codeOrPattern] = processor;
            if (config) this._configs[codeOrPattern] = config;
        }
    },

    /**
     * Obtiene el template para un código de regla
     * @param {string} code - Código de la regla
     * @returns {Object|null} - { templateName, processor, config } o null
     */
    get(code) {
        // Primero buscar por código exacto
        if (this._templates[code]) {
            return {
                templateName: this._templates[code],
                processor: this._processors[code] || null,
                config: this._configs[code] || {},
            };
        }

        // Luego buscar por patrones
        for (const patternConfig of this._patterns) {
            if (patternConfig.pattern.test(code)) {
                return {
                    templateName: patternConfig.templateName,
                    processor: patternConfig.processor,
                    config: patternConfig.config,
                };
            }
        }

        return null;
    },

    /**
     * Verifica si existe un template para un código
     * @param {string} code - Código de la regla
     * @returns {boolean}
     */
    has(code) {
        return this.get(code) !== null;
    },

    /**
     * Lista todos los templates registrados
     * @returns {Array}
     */
    list() {
        const list = [];

        // Templates exactos
        for (const [code, templateName] of Object.entries(this._templates)) {
            list.push({
                type: 'exact',
                code,
                templateName,
                hasProcessor: !!this._processors[code],
            });
        }

        // Patrones
        for (const patternConfig of this._patterns) {
            list.push({
                type: 'pattern',
                pattern: patternConfig.pattern.toString(),
                templateName: patternConfig.templateName,
                priority: patternConfig.priority,
                hasProcessor: !!patternConfig.processor,
            });
        }

        return list;
    },
};

/**
 * ═══════════════════════════════════════════════════════════════════════════
 * CONFIGURACIONES DE TEMPLATES POR TIPO DE REGLA
 * ═══════════════════════════════════════════════════════════════════════════
 */

export const RULE_TEMPLATE_CONFIGS = {
    // ─────────────────────────────────────────────────────────────────────────
    // RETENCIÓN EN LA FUENTE - PROCEDIMIENTO 1 (Art. 385 ET)
    // ─────────────────────────────────────────────────────────────────────────
    RETENCION_PROC1: {
        code: 'RT_MET_01',
        name: 'Retención en la Fuente - Procedimiento 1',
        baseLegal: 'Art. 385, 387 y 383 E.T.',
        color: '#DC2626', // Rojo
        icon: 'fa-percent',
        sections: [
            {
                id: 'ingresos',
                title: '1. Ingresos Laborales del Mes',
                baseLegal: 'Art. 103 E.T.',
                color: '#22C55E',
                fields: ['salario', 'devengados', 'dev_no_salarial', 'total_ingresos'],
                showLines: true,
            },
            {
                id: 'incr',
                title: '2. Ingresos No Constitutivos de Renta',
                baseLegal: 'Art. 55 y 56 E.T.',
                color: '#3B82F6',
                fields: ['salud', 'pension', 'solidaridad', 'subsistencia', 'total_incr'],
                showLines: true,
            },
            {
                id: 'subtotal1',
                title: 'Subtotal 1',
                isSubtotal: true,
                formula: 'Ingresos - INCR',
            },
            {
                id: 'deducciones',
                title: '3. Deducciones',
                baseLegal: 'Art. 387 E.T.',
                color: '#F97316',
                subsections: [
                    { id: 'dependientes', name: 'Dependientes', baseLegal: 'Art. 387 Num. 1', tope: '32 UVT/mes' },
                    { id: 'prepagada', name: 'Medicina Prepagada', baseLegal: 'Art. 387 Num. 2', tope: '16 UVT/mes' },
                    { id: 'vivienda', name: 'Intereses Vivienda', baseLegal: 'Art. 119/387 Num. 3', tope: '100 UVT/mes' },
                ],
                showLines: true,
            },
            {
                id: 'rentas_exentas',
                title: '4. Rentas Exentas (AFC/AVC)',
                baseLegal: 'Art. 126-1 y 126-4 E.T.',
                color: '#8B5CF6',
                tope: '30% + 3800 UVT/año',
                showLines: true,
            },
            {
                id: 'renta_25',
                title: '5. Renta Exenta 25%',
                baseLegal: 'Art. 206 Num. 10 E.T. (Ley 2277/2022)',
                color: '#06B6D4',
                tope: '790 UVT/año (65.83 UVT/mes)',
            },
            {
                id: 'limite_global',
                title: '6. Límite Global 40%',
                baseLegal: 'Art. 336 E.T. (Ley 2277/2022)',
                color: '#EF4444',
                tope: 'min(40%, 1340 UVT/año)',
            },
            {
                id: 'base_gravable',
                title: '7. Base Gravable',
                isSubtotal: true,
                formula: 'Subtotal 1 - Deducciones - Rentas Exentas (limitadas)',
            },
            {
                id: 'tabla_retencion',
                title: '8. Tabla de Retención',
                baseLegal: 'Art. 383 E.T.',
                showTable: true,
                table: [
                    { desde: 0, hasta: 95, tarifa: 0 },
                    { desde: 95, hasta: 150, tarifa: 19 },
                    { desde: 150, hasta: 360, tarifa: 28 },
                    { desde: 360, hasta: 640, tarifa: 33 },
                    { desde: 640, hasta: 945, tarifa: 35 },
                    { desde: 945, hasta: 2300, tarifa: 37 },
                    { desde: 2300, hasta: null, tarifa: 39 },
                ],
            },
        ],
    },

    // ─────────────────────────────────────────────────────────────────────────
    // RETENCIÓN EN LA FUENTE - PROCEDIMIENTO 2 (Art. 386 ET)
    // ─────────────────────────────────────────────────────────────────────────
    RETENCION_PROC2: {
        code: 'RT_MET_02',
        name: 'Retención en la Fuente - Procedimiento 2',
        baseLegal: 'Art. 386 E.T.',
        color: '#9333EA', // Púrpura
        icon: 'fa-calculator',
        sections: [
            {
                id: 'promedio_ingresos',
                title: '1. Promedio Ingresos (12 meses)',
                baseLegal: 'Art. 386 E.T.',
                color: '#22C55E',
            },
            {
                id: 'promedio_incr',
                title: '2. Promedio INCR',
                baseLegal: 'Art. 55 y 56 E.T.',
                color: '#3B82F6',
            },
            {
                id: 'porcentaje_fijo',
                title: '3. Porcentaje Fijo Calculado',
                baseLegal: 'Art. 386 E.T.',
                color: '#F97316',
            },
            {
                id: 'aplicacion',
                title: '4. Aplicación del Porcentaje',
                isResult: true,
            },
        ],
    },

    // ─────────────────────────────────────────────────────────────────────────
    // IBD - INGRESO BASE DE COTIZACIÓN
    // ─────────────────────────────────────────────────────────────────────────
    IBD: {
        code: 'IBD',
        name: 'Ingreso Base de Cotización (IBC)',
        baseLegal: 'Art. 18 Ley 100/1993',
        color: '#0EA5E9', // Azul cielo
        icon: 'fa-building',
        sections: [
            {
                id: 'devengos',
                title: '1. Total Devengos',
                color: '#22C55E',
                showLines: true,
            },
            {
                id: 'exclusiones',
                title: '2. Exclusiones',
                baseLegal: 'Art. 128 C.S.T.',
                color: '#F97316',
                showLines: true,
            },
            {
                id: 'ausencias',
                title: '3. Descuento Ausencias',
                color: '#EF4444',
                showLines: true,
            },
            {
                id: 'ibc_calculado',
                title: '4. IBC Calculado',
                isSubtotal: true,
            },
            {
                id: 'topes',
                title: '5. Validación de Topes',
                baseLegal: 'Art. 18 Ley 100/1993',
                topes: [
                    { nombre: 'Mínimo', valor: '1 SMMLV' },
                    { nombre: 'Máximo', valor: '25 SMMLV' },
                ],
            },
        ],
    },

    // ─────────────────────────────────────────────────────────────────────────
    // PRIMA DE SERVICIOS
    // ─────────────────────────────────────────────────────────────────────────
    PRIMA: {
        code: 'PRIMA',
        name: 'Prima de Servicios',
        baseLegal: 'Art. 306 C.S.T.',
        color: '#10B981', // Verde esmeralda
        icon: 'fa-gift',
        sections: [
            {
                id: 'base_prima',
                title: '1. Base de Liquidación',
                baseLegal: 'Art. 306 C.S.T.',
                color: '#22C55E',
                formula: 'Salario + Aux. Transporte + Promedio Variable',
            },
            {
                id: 'dias_causados',
                title: '2. Días Causados',
                color: '#3B82F6',
            },
            {
                id: 'calculo',
                title: '3. Cálculo',
                formula: 'Base × Días / 360',
                isResult: true,
            },
        ],
    },

    // ─────────────────────────────────────────────────────────────────────────
    // CESANTÍAS
    // ─────────────────────────────────────────────────────────────────────────
    CESANTIAS: {
        code: 'CESANTIAS',
        name: 'Cesantías',
        baseLegal: 'Art. 249 C.S.T.',
        color: '#F59E0B', // Ámbar
        icon: 'fa-university',
        sections: [
            {
                id: 'base_cesantias',
                title: '1. Base de Liquidación',
                baseLegal: 'Art. 253 C.S.T.',
                color: '#22C55E',
            },
            {
                id: 'dias_causados',
                title: '2. Días Causados',
                color: '#3B82F6',
            },
            {
                id: 'calculo',
                title: '3. Cálculo',
                formula: 'Base × Días / 360',
                isResult: true,
            },
        ],
    },

    // ─────────────────────────────────────────────────────────────────────────
    // INTERESES DE CESANTÍAS
    // ─────────────────────────────────────────────────────────────────────────
    INT_CESANTIAS: {
        code: 'INT_CESANTIAS',
        name: 'Intereses sobre Cesantías',
        baseLegal: 'Ley 52/1975',
        color: '#F97316', // Naranja
        icon: 'fa-line-chart',
        sections: [
            {
                id: 'cesantias_acumuladas',
                title: '1. Cesantías Acumuladas',
                color: '#22C55E',
            },
            {
                id: 'dias_causados',
                title: '2. Días Causados',
                color: '#3B82F6',
            },
            {
                id: 'calculo',
                title: '3. Cálculo',
                formula: 'Cesantías × 12% × Días / 360',
                baseLegal: 'Art. 1 Ley 52/1975',
                isResult: true,
            },
        ],
    },

    // ─────────────────────────────────────────────────────────────────────────
    // LIQUIDACIÓN DEFINITIVA
    // ─────────────────────────────────────────────────────────────────────────
    LIQUIDACION: {
        code: 'LIQUIDACION',
        name: 'Liquidación Definitiva',
        baseLegal: 'Art. 64, 65, 249, 306 C.S.T.',
        color: '#7C3AED', // Púrpura
        icon: 'fa-file-text',
        sections: [
            {
                id: 'datos_base',
                title: '1. Datos Base',
                color: '#22C55E',
            },
            {
                id: 'periodos',
                title: '2. Períodos de Cálculo',
                color: '#3B82F6',
            },
            {
                id: 'conceptos',
                title: '3. Conceptos de Liquidación',
                color: '#7C3AED',
            },
            {
                id: 'indemnizacion',
                title: '4. Indemnización',
                baseLegal: 'Art. 64 C.S.T.',
                color: '#DC2626',
            },
        ],
    },

    // ─────────────────────────────────────────────────────────────────────────
    // PROVISIÓN MENSUAL
    // ─────────────────────────────────────────────────────────────────────────
    PROVISION: {
        code: 'PROVISION',
        name: 'Provisión Mensual de Prestaciones',
        baseLegal: 'Art. 249, 306 C.S.T., Ley 52/1975',
        color: '#6366F1', // Indigo
        icon: 'fa-database',
        porcentajes: {
            cesantias: 8.33,
            int_cesantias: 1.00,
            prima: 8.33,
            vacaciones: 4.17,
            total: 21.83,
        },
    },

    // ─────────────────────────────────────────────────────────────────────────
    // AUXILIO DE TRANSPORTE
    // ─────────────────────────────────────────────────────────────────────────
    AUXILIO_TRANSPORTE: {
        code: 'AUX_TRANS',
        name: 'Auxilio de Transporte',
        baseLegal: 'Ley 15/1959, Decreto Anual',
        color: '#3B82F6', // Azul
        icon: 'fa-bus',
        condicion: 'Salario <= 2 SMMLV',
    },
};

/**
 * ═══════════════════════════════════════════════════════════════════════════
 * PROCESADORES DE DATOS POR TIPO DE REGLA
 * ═══════════════════════════════════════════════════════════════════════════
 */

export const RuleDataProcessors = {
    /**
     * Procesa datos de Retención Procedimiento 1
     * Mapea campos desde Python (computed_values) a la estructura esperada por el template
     */
    processRetencionProc1(line, computation, allLines) {
        const comp = computation || {};

        // Extraer ingresos desde la sección anidada si existe
        const ingresos = comp.ingresos || {};
        const aportes = comp.aportes || {};
        const baseGravable = comp.base_gravable || {};
        const beneficios = comp.beneficios || {};
        const retencion = comp.retencion || {};

        // Calcular base gravable y UVT desde diferentes posibles fuentes
        const baseGravableValue = baseGravable.ibr3_final || baseGravable.ibr_final ||
                                  comp.ibr3_final || comp.ibr_final || comp.base_gravable || 0;
        const baseUvtValue = baseGravable.ibr_uvts || comp.ibr_uvts || comp.base_uvt || 0;
        const tarifaValue = retencion.tarifa_porcentaje || comp.tarifa_porcentaje || comp.tarifa || 0;
        const uvtValue = comp.valor_uvt || comp.uvt || aportes.uvt || 49799;

        // Determinar rango aplicado basado en base UVT
        let rangoAplicado = '';
        if (baseUvtValue > 0 && baseUvtValue <= 95) rangoAplicado = '0 - 95';
        else if (baseUvtValue > 95 && baseUvtValue <= 150) rangoAplicado = '95 - 150';
        else if (baseUvtValue > 150 && baseUvtValue <= 360) rangoAplicado = '150 - 360';
        else if (baseUvtValue > 360 && baseUvtValue <= 640) rangoAplicado = '360 - 640';
        else if (baseUvtValue > 640 && baseUvtValue <= 945) rangoAplicado = '640 - 945';
        else if (baseUvtValue > 945 && baseUvtValue <= 2300) rangoAplicado = '945 - 2300';
        else if (baseUvtValue > 2300) rangoAplicado = '> 2300';

        return {
            // Paso 1: Ingresos
            // IMPORTANTE: Usar ?? en lugar de || para que 0 no se trate como falsy
            ingresos: {
                salario: ingresos.salario ?? comp.salario ?? comp.salary ?? 0,
                devengados: ingresos.devengados ?? comp.devengados ?? 0,  // NO usar comp.dev_salarial que incluye básico
                dev_no_salarial: ingresos.dev_no_salarial ?? comp.dev_no_salarial ?? 0,
                total: ingresos.total ?? comp.total_ingresos ?? comp.ingresos_total ??
                       ((ingresos.salario ?? 0) + (ingresos.devengados ?? 0) + (ingresos.dev_no_salarial ?? 0)),
                lineas: comp.lineas_ingresos || [],
            },
            // Paso 2: INCR (Ingresos No Constitutivos de Renta)
            incr: {
                salud: aportes.salud || comp.salud || comp.incr_salud || 0,
                pension: aportes.pension || comp.pension || comp.incr_pension || 0,
                solidaridad: aportes.solidaridad || comp.solidaridad || comp.incr_solidaridad || 0,
                subsistencia: aportes.subsistencia || comp.subsistencia || comp.incr_subsistencia || 0,
                total: aportes.total || comp.total_incr ||
                       ((aportes.salud || 0) + (aportes.pension || 0) +
                        (aportes.solidaridad || 0) + (aportes.subsistencia || 0)),
                lineas: comp.lineas_incr || aportes.lineas_detalle || [],
            },
            // Subtotal 1
            subtotal_1: baseGravable.ibr1_antes_deducciones || comp.subtotal_1 || comp.ing_base || 0,
            // Paso 3: Deducciones
            deducciones: {
                dependientes: beneficios.ded_dependientes || comp.ded_dependientes || comp.dependientes || 0,
                prepagada: beneficios.ded_prepagada || comp.ded_prepagada || comp.prepagada || 0,
                vivienda: beneficios.ded_vivienda || comp.ded_vivienda || comp.vivienda || 0,
                total: beneficios.deducciones || baseGravable.deducciones || comp.total_deducciones || 0,
                lineas: comp.lineas_deducciones || [],
            },
            // Paso 4: Rentas Exentas AFC/AVC
            rentas_exentas: {
                afc: beneficios.afc || comp.afc || 0,
                avc: beneficios.avc || comp.avc || 0,
                total: beneficios.rentas_exentas || baseGravable.rentas_exentas || comp.total_rentas_exentas || 0,
                limite_30_pct: comp.limite_30_pct || 0,
                limite_uvt: baseGravable.limite_uvt || comp.limite_uvt_afc || 0,
                lineas: comp.lineas_afc_avc || [],
            },
            // Paso 5: Renta Exenta 25%
            renta_25: {
                base: baseGravable.ibr2_antes_renta_exenta || comp.base_25 || 0,
                calculado: beneficios.renta_exenta_25 || comp.renta_25_calculado || 0,
                tope: comp.tope_25 || 0,
                aplicado: beneficios.renta_exenta_25 || baseGravable.renta_exenta_25 || comp.renta_25 || 0,
            },
            // Paso 6: Límite Global
            limite_global: {
                total_beneficios: beneficios.total_beneficios || baseGravable.total_beneficios || comp.total_beneficios || 0,
                limite_40_pct: baseGravable.limite_40 || comp.limite_40_pct || 0,
                limite_uvt: baseGravable.limite_uvt || comp.limite_uvt_global || 0,
                aplicado: beneficios.beneficios_limitados || baseGravable.beneficios_limitados || comp.beneficios_limitados || 0,
            },
            // Paso 7: Base Gravable Final
            base_gravable: baseGravableValue,
            base_uvt: baseUvtValue,
            // Paso 8: Retención
            rango: comp.rango || rangoAplicado,
            tarifa: tarifaValue,
            retencion: retencion.definitiva || retencion.calculada || comp.retencion || Math.abs(line.total || 0),
            // UVT vigente
            uvt: uvtValue,
        };
    },

    /**
     * Procesa datos de IBD/IBC
     * Mapea campos desde Python (_ibd en ibd_sss.py) a la estructura del template
     *
     * Campos de Python:
     * - salary: Total devengos salariales
     * - o_earnings: Pagos no constitutivos de salario (Art. 128 CST)
     * - top40: Límite 40% calculado (salary_for_40 + o_earnings) * 0.4
     * - salary_for_40: Salario base para calcular 40%
     * - absences_amount: Valor monetario de ausencias
     * - ibc_pre: IBC antes de aplicar topes
     * - ibc_final: IBC final después de topes
     * - smmlv: Salario mínimo vigente
     * - effective_days: Días efectivos (30)
     * - include_absences_1393: Si incluye ausencias en cálculo Ley 1393
     * - acum_line_ids: Líneas detalle del cómputo
     * - absences_by_category: Ausencias desglosadas por categoría
     */
    processIBD(line, computation, allLines) {
        const raw = computation || {};
        const comp = raw.datos || raw;

        // Obtener valores de Python (soporta estructura estandarizada en comp.datos)
        const salary = comp.salary || comp.salario || 0;
        const oEarnings = comp.o_earnings || comp.pagos_no_salariales || 0;
        const top40 = comp.top40 || 0;
        const salaryFor40 = comp.salary_for_40 || salary;
        const absencesAmount = comp.absences_amount || comp.ausencias || 0;
        const ibcPre = comp.ibc_pre || 0;
        const ibcFinal = comp.ibc_final || line.total || 0;
        const smmlv = comp.smmlv || 1423500; // 2025
        const effectiveDays = comp.effective_days || 30;
        const includeAbsences1393 = comp.include_absences_1393 || false;
        const dayValue = comp.day_value || (ibcFinal / 30);

        // Líneas detalle del cómputo
        const detailLines = allLines?.detailLines || [];
        const absencesByCategory = comp.absences_by_category || {};
        const lineasDetalle = Array.isArray(detailLines) && detailLines.length ? detailLines : [];
        const devengosDetalle = lineasDetalle.filter(l => l.category_code !== 'DEV_NO_SALARIAL');
        const noSalarialDetalle = lineasDetalle.filter(l => l.category_code === 'DEV_NO_SALARIAL');

        // Calcular exceso de pagos no salariales sobre 40%
        const excesoNoSalarial = oEarnings > top40 ? oEarnings - top40 : 0;

        // Determinar si se aplicó tope máximo (25 SMMLV)
        let topeAplicado = null;
        if (ibcFinal >= 25 * smmlv) topeAplicado = 'maximo';

        // Cotizante tipo 51 (especial) - Res. 2388/2016
        const esCotizante51 = comp.cotizante_51 || false;
        const tablaAplicada = comp.tabla_aplicada || '';

        // Campos detallados para cotizante 51
        const tipoPeriodo51 = comp.tipo_periodo || 'MENSUAL';
        const esQuincenal51 = comp.es_quincenal || false;
        const quincenaActual = comp.quincena_actual || 'N/A';
        const diasPeriodoActual = comp.dias_periodo_actual || 30;
        const diasOtraQuincena = comp.dias_otra_quincena || 0;
        const diasMesCompleto = comp.dias_mes_completo || 30;
        const ibcTablaMensual = comp.ibc_tabla_mensual || 0;
        const rangoTabla51 = comp.rango_tabla_51 || '';
        const descripcionRango51 = comp.descripcion_rango || '';
        const explicacionCalculo51 = comp.explicacion_calculo || [];

        return {
            // Información general
            es_cotizante_51: esCotizante51,
            tabla_aplicada: tablaAplicada,

            // Campos detallados cotizante 51
            cotizante_51: {
                tipo_periodo: tipoPeriodo51,
                es_quincenal: esQuincenal51,
                quincena_actual: quincenaActual,
                dias_periodo_actual: diasPeriodoActual,
                dias_otra_quincena: diasOtraQuincena,
                dias_mes_completo: diasMesCompleto,
                ibc_tabla_mensual: ibcTablaMensual,
                ibc_periodo: ibcFinal,
                rango_tabla: rangoTabla51,
                descripcion_rango: descripcionRango51,
                explicacion: explicacionCalculo51,
                factor: esQuincenal51 ? 0.5 : 1.0,
            },

            // PASO 1: Total Devengos Salariales
            devengos: {
                salario: salary,
                total: salary,
                lineas: devengosDetalle,
            },

            // PASO 2: Pagos No Constitutivos de Salario (Art. 128 CST)
            pagos_no_salariales: {
                total: oEarnings,
                lineas: noSalarialDetalle,
            },

            // PASO 3: Cálculo Ley 1393 (Límite 40%)
            ley_1393: {
                incluye_ausencias: includeAbsences1393,
                salario_base: salaryFor40,
                pagos_no_salariales: oEarnings,
                suma_para_40: salaryFor40 + oEarnings,
                limite_40_pct: top40,
                exceso: excesoNoSalarial,
                base_legal: 'Art. 30 Ley 1393/2010',
            },

            // PASO 4: Descuento Ausencias
            ausencias: {
                valor: absencesAmount,
                por_categoria: absencesByCategory,
                incluidas_en_1393: includeAbsences1393,
            },

            // PASO 5: IBC Preliminar (antes de topes)
            ibc_preliminar: ibcPre,

            // PASO 6: Validación de Topes (solo máximo 25 SMMLV)
            topes: {
                smmlv: smmlv,
                maximo: 25 * smmlv,
                aplicado: topeAplicado,
            },

            // PASO 7: IBC Final
            ibc_final: ibcFinal,
            dias_efectivos: effectiveDays,
            valor_dia: dayValue,

            // Líneas detalle completas del cómputo
            lineas_detalle: lineasDetalle,
        };
    },

    /**
     * Procesa datos de Prima de Servicios
     */
    processPrima(line, computation, allLines) {
        const comp = computation || {};
        return {
            base: {
                salario: comp.salary || comp.salario || 0,
                auxilio: comp.auxilio_transporte || 0,
                variable: comp.promedio_variable || 0,
                total: comp.base_prima || comp.base || 0,
            },
            dias_causados: comp.dias_computables || comp.days || 180,
            factor: 360,
            prima: comp.prima || line.total || 0,
        };
    },

    /**
     * Procesa datos de Cesantías
     */
    processCesantias(line, computation, allLines) {
        const comp = computation || {};
        return {
            base: {
                salario: comp.salary || comp.salario || 0,
                auxilio: comp.auxilio_transporte || 0,
                total: comp.base_cesantias || comp.base || 0,
            },
            dias_causados: comp.dias_computables || comp.days || 360,
            factor: 360,
            cesantias: comp.cesantias || line.total || 0,
        };
    },

    /**
     * Procesa datos de Intereses de Cesantías
     */
    processIntCesantias(line, computation, allLines) {
        const comp = computation || {};
        return {
            cesantias_acumuladas: comp.cesantias_acumuladas || comp.base || 0,
            dias_causados: comp.dias_computables || comp.days || 360,
            tasa: 12,
            factor: 360,
            intereses: comp.intereses || line.total || 0,
        };
    },

    /**
     * Procesa datos de Liquidación Definitiva
     */
    processLiquidacion(line, computation, allLines) {
        const comp = computation || {};
        const SMMLV = 1423500; // 2025

        return {
            // Información del empleado
            fecha_ingreso: comp.fecha_ingreso || '',
            fecha_retiro: comp.fecha_retiro || '',
            tiempo_laborado: comp.tiempo_laborado || '',
            causa_retiro: comp.causa_retiro || 'Renuncia voluntaria',

            // Datos base
            salario_basico: comp.salario_basico || comp.salary || 0,
            promedio_variables: comp.promedio_variables || 0,
            salario_total: comp.salario_total || (comp.salario_basico || 0) + (comp.promedio_variables || 0),
            auxilio_transporte: comp.auxilio_transporte || 0,
            aplica_auxilio: comp.aplica_auxilio !== false,
            base_prestaciones: comp.base_prestaciones || 0,
            base_vacaciones: comp.base_vacaciones || comp.salario_basico || 0,

            // Periodos
            dias_mes: comp.dias_mes || 0,
            dias_semestre: comp.dias_semestre || 0,
            dias_anio: comp.dias_anio || comp.dias_año || 0,
            dias_totales: comp.dias_totales || 0,

            // Conceptos de liquidación
            salario_proporcional: comp.salario_proporcional || 0,
            prima_proporcional: comp.prima_proporcional || 0,
            cesantias_proporcional: comp.cesantias_proporcional || 0,
            int_cesantias: comp.int_cesantias || 0,
            vacaciones_compensadas: comp.vacaciones_compensadas || 0,
            dias_vacaciones_causadas: comp.dias_vacaciones_causadas || 0,
            dias_vacaciones_disfrutadas: comp.dias_vacaciones_disfrutadas || 0,
            dias_vacaciones_pendientes: comp.dias_vacaciones_pendientes || 0,

            // Totales
            total_devengos: comp.total_devengos || line.total || 0,
            total_deducciones: comp.total_deducciones || 0,
            neto_pagar: comp.neto_pagar || 0,

            // Indemnización (si aplica)
            aplica_indemnizacion: comp.aplica_indemnizacion || false,
            indemnizacion_regla: comp.indemnizacion_regla || '',
            indemnizacion_dias: comp.indemnizacion_dias || 0,
            indemnizacion_estructura: comp.indemnizacion_estructura || [],
            indemnizacion_valor: comp.indemnizacion_valor || 0,
            salario_dia: comp.salario_dia || (comp.salario_total || 0) / 30,

            total_liquidacion: comp.total_liquidacion || line.total || 0,
        };
    },

    /**
     * Procesa datos de Provisión Mensual
     * Soporta dos estructuras:
     * - Metodo simple: base_total, salario_minimo_mensual, auxilio_transporte_mensual
     * - Metodo complejo: data_kpi.base_mensual, data_kpi.salary_base, data_kpi.subsidy
     *
     * Extrae KPIs detallados para visualizacion rica como el widget de dias del periodo
     */
    processProvision(line, computation, allLines) {
        const comp = computation || {};
        const dataKpi = comp.data_kpi || {};

        // Detectar metodo usado
        const metodo = comp.metodo || 'complejo';
        const provisionType = comp.provision_type || line.code || '';

        // Extraer valores segun estructura disponible
        let salarioBasico, promedioVariables, auxTransporte, diasTrabajados;
        let baseDiaria, baseMensual, baseFieldUsed;

        if (metodo === 'simple_rapido') {
            // Metodo simple
            salarioBasico = comp.salario_minimo_mensual || comp.base_salario_minimo || 0;
            promedioVariables = 0;
            auxTransporte = comp.auxilio_transporte_mensual || comp.auxilio_transporte_periodo || 0;
            diasTrabajados = comp.dias_trabajados || comp.dias_computables || 30;
            baseDiaria = salarioBasico / 30;
            baseMensual = salarioBasico;
            baseFieldUsed = 'salario_minimo';
        } else {
            // Metodo complejo con data_kpi
            salarioBasico = dataKpi.salary_base || dataKpi.base_mensual || comp.base_total || 0;
            promedioVariables = dataKpi.salary_variable || 0;
            auxTransporte = dataKpi.subsidy || 0;
            diasTrabajados = Math.abs(dataKpi.days_worked || 30);
            baseDiaria = dataKpi.base_diaria || (salarioBasico / 30);
            baseMensual = dataKpi.base_mensual || salarioBasico;
            baseFieldUsed = dataKpi.base_field_used || 'base_prestaciones';
        }

        const salarioTotal = salarioBasico + promedioVariables;
        const basePrestaciones = salarioTotal + auxTransporte;
        const baseVacaciones = salarioBasico;

        // Calcular provisiones (usar valores del backend si existen, sino calcular)
        const tasa = comp.tasa || 0;
        const montoTotal = Math.abs(comp.monto_total || line.total || 0);
        const totalCausado = comp.total_causado || montoTotal;
        const incrementoMes = comp.incremento_mes || montoTotal;

        // Determinar tipo de provision para mostrar info correcta
        const tipoProvision = provisionType.toLowerCase();
        let nombreProvision = 'Provision';
        let porcentaje = 0;
        let baseLegal = '';
        let formulaCalculo = '';
        let iconClass = 'fa-database';
        let colorTheme = '#6366F1'; // Indigo por defecto

        if (tipoProvision.includes('vac') || tipoProvision === 'vacaciones') {
            nombreProvision = 'Vacaciones';
            porcentaje = tasa || 4.17;
            baseLegal = 'Art. 186-192 C.S.T.';
            formulaCalculo = 'Salario Base x 4.17% (15 dias / 360)';
            iconClass = 'fa-sun-o';
            colorTheme = '#F59E0B'; // Amber
        } else if (tipoProvision.includes('prim') || tipoProvision === 'prima') {
            nombreProvision = 'Prima';
            porcentaje = tasa || 8.33;
            baseLegal = 'Art. 306 C.S.T.';
            formulaCalculo = 'Base Prestaciones x 8.33% (30 dias / 360)';
            iconClass = 'fa-gift';
            colorTheme = '#10B981'; // Emerald
        } else if (tipoProvision.includes('ices') || tipoProvision === 'intereses') {
            nombreProvision = 'Int. Cesantias';
            porcentaje = tasa || 1.0;
            baseLegal = 'Ley 52/1975';
            formulaCalculo = 'Cesantias Acum. x 12% x Dias / 360';
            iconClass = 'fa-line-chart';
            colorTheme = '#F97316'; // Orange
        } else if (tipoProvision.includes('ces') || tipoProvision === 'cesantias') {
            nombreProvision = 'Cesantias';
            porcentaje = tasa || 8.33;
            baseLegal = 'Art. 249 C.S.T., Ley 50/1990';
            formulaCalculo = 'Base Prestaciones x 8.33% (30 dias / 360)';
            iconClass = 'fa-university';
            colorTheme = '#3B82F6'; // Blue
        }

        // Periodo
        const fechaInicio = comp.fecha_inicio || '';
        const fechaFin = comp.fecha_fin || comp.fecha_corte || '';
        const periodo = fechaInicio && fechaFin ? `${fechaInicio} - ${fechaFin}` : '';

        // Construir lista de KPIs para mostrar en grid (similar a dias del periodo)
        const kpis = [
            {
                id: 'base_mensual',
                label: 'Base Mensual',
                value: baseMensual,
                format: 'currency',
                icon: 'fa-money',
                color: '#22C55E',
                description: 'Salario base para el calculo',
            },
            {
                id: 'base_diaria',
                label: 'Base Diaria',
                value: baseDiaria,
                format: 'currency',
                icon: 'fa-calendar',
                color: '#3B82F6',
                description: 'Base mensual / 30 dias',
            },
            {
                id: 'dias_trabajados',
                label: 'Dias Trabajados',
                value: diasTrabajados,
                format: 'number',
                icon: 'fa-clock-o',
                color: '#8B5CF6',
                description: 'Dias del periodo',
            },
            {
                id: 'tasa',
                label: 'Tasa',
                value: porcentaje,
                format: 'percent',
                icon: 'fa-percent',
                color: colorTheme,
                description: 'Porcentaje de provision',
            },
        ];

        // Agregar KPIs adicionales segun tipo
        if (promedioVariables > 0) {
            kpis.push({
                id: 'promedio_variables',
                label: 'Promedio Variables',
                value: promedioVariables,
                format: 'currency',
                icon: 'fa-bar-chart',
                color: '#EC4899',
                description: 'Promedio de pagos variables',
            });
        }

        if (auxTransporte > 0) {
            kpis.push({
                id: 'auxilio_transporte',
                label: 'Auxilio Transporte',
                value: auxTransporte,
                format: 'currency',
                icon: 'fa-bus',
                color: '#06B6D4',
                description: 'Incluido en base prestaciones',
            });
        }

        // Detalle del calculo paso a paso
        const pasosCalculo = [];

        // Paso 1: Base de calculo
        if (nombreProvision === 'Vacaciones') {
            pasosCalculo.push({
                numero: 1,
                titulo: 'Base de Calculo',
                descripcion: 'Solo salario basico (sin variables ni auxilio)',
                valor: salarioBasico,
                formato: 'currency',
            });
        } else {
            pasosCalculo.push({
                numero: 1,
                titulo: 'Base de Calculo',
                descripcion: 'Salario + Variables + Auxilio',
                valor: basePrestaciones,
                formato: 'currency',
                desglose: [
                    { label: 'Salario Base', valor: salarioBasico },
                    { label: 'Variables', valor: promedioVariables },
                    { label: 'Auxilio', valor: auxTransporte },
                ],
            });
        }

        // Paso 2: Dias trabajados
        pasosCalculo.push({
            numero: 2,
            titulo: 'Dias del Periodo',
            descripcion: 'Dias efectivos trabajados',
            valor: diasTrabajados,
            formato: 'number',
        });

        // Paso 3: Aplicar tasa
        pasosCalculo.push({
            numero: 3,
            titulo: 'Aplicar Tasa',
            descripcion: `Tasa de provision: ${porcentaje}%`,
            valor: porcentaje,
            formato: 'percent',
            formula: formulaCalculo,
        });

        // Paso 4: Resultado
        pasosCalculo.push({
            numero: 4,
            titulo: 'Provision del Periodo',
            descripcion: 'Monto a provisionar',
            valor: montoTotal,
            formato: 'currency',
            esResultado: true,
        });

        // Informacion de trazabilidad (reglas relacionadas)
        // Usar reglas del backend si estan disponibles, sino buscar en allLines
        let reglasRelacionadas = [];

        if (comp.reglas_relacionadas && comp.reglas_relacionadas.length > 0) {
            // Usar reglas del backend
            reglasRelacionadas = comp.reglas_relacionadas.map(r => ({
                id: r.line_ids ? r.line_ids[0] : 0,
                code: r.codigo,
                name: r.nombre,
                total: r.total || 0,
                tipo: r.tipo || 'base',
            }));
        } else if (allLines && allLines.length > 0) {
            // Fallback: Buscar reglas en allLines
            const codigosRelacionados = {
                'vacaciones': ['BASICO', 'SALARY', 'WAGE'],
                'prima': ['BASICO', 'SALARY', 'AUX000', 'AUX00C'],
                'cesantias': ['BASICO', 'SALARY', 'AUX000', 'AUX00C'],
                'intereses': ['CESANTIAS', 'CES_'],
            };

            const patronesBuscar = codigosRelacionados[tipoProvision] || [];
            for (const linea of allLines) {
                if (!linea.code) continue;
                for (const patron of patronesBuscar) {
                    if (linea.code.toUpperCase().includes(patron.toUpperCase())) {
                        reglasRelacionadas.push({
                            id: linea.id,
                            code: linea.code,
                            name: linea.name,
                            total: linea.total || 0,
                        });
                        break;
                    }
                }
            }
        }

        return {
            periodo: periodo,
            fecha_inicio: fechaInicio,
            fecha_fin: fechaFin,
            metodo: metodo,
            tipo_provision: nombreProvision,
            provision_type: provisionType,
            base_legal: baseLegal,
            formula_calculo: formulaCalculo,
            icon_class: iconClass,
            color_theme: colorTheme,

            // Bases de calculo
            salario_basico: salarioBasico,
            promedio_variables: promedioVariables,
            salario_total: salarioTotal,
            auxilio_transporte: auxTransporte,
            aplica_auxilio: auxTransporte > 0,
            base_prestaciones: basePrestaciones,
            base_vacaciones: baseVacaciones,

            // KPIs detallados
            base_diaria: baseDiaria,
            base_mensual: baseMensual,
            base_field_used: baseFieldUsed,
            base_field_label: baseFieldUsed === 'base_vacaciones' ? 'Base Vacaciones' :
                              baseFieldUsed === 'base_prestaciones' ? 'Base Prestaciones' :
                              baseFieldUsed === 'salario_minimo' ? 'Salario Minimo' : 'Base General',

            dias_trabajados: diasTrabajados,
            tasa: porcentaje,
            formula: comp.formula || dataKpi.formula || formulaCalculo,

            // Valores calculados
            monto_total: montoTotal,
            total_causado: totalCausado,
            incremento_mes: incrementoMes,
            saldo_contable: comp.saldo_contable || 0,
            provision_acumulada: comp.provision_acumulada || 0,

            // Para template consolidado (si se usa)
            provision_cesantias: comp.provision_cesantias || 0,
            provision_int_cesantias: comp.provision_int_cesantias || 0,
            provision_prima: comp.provision_prima || 0,
            provision_vacaciones: comp.provision_vacaciones || 0,
            total_provision: montoTotal,

            // KPIs para grid visual
            kpis: kpis,

            // Pasos del calculo detallados
            pasos_calculo: pasosCalculo,

            // Reglas relacionadas (trazabilidad)
            reglas_relacionadas: reglasRelacionadas,

            // Trazabilidad completa
            trazabilidad: comp.trazabilidad || {},
            valores_anteriores: dataKpi.valores_anteriores || {},

            // Data KPI original para debug/detalles adicionales
            data_kpi_raw: dataKpi,
        };
    },

    /**
     * Procesa datos de Auxilio de Transporte
     */
    processAuxilioTransporte(line, computation, allLines) {
        const comp = computation || {};
        const datos = comp.datos || {};
        const SMMLV = 1423500; // 2025
        const TOPE_2_SMMLV = 2 * SMMLV;
        const VALOR_MENSUAL = datos.monthly_value || comp.monthly_value || 200000;

        // Obtener salario base - buscar en datos (donde Python lo envia) y en comp
        const salarioBase = datos.salary_base || comp.salary_base || datos.salario_base || 0;
        const salaryLimit = datos.salary_limit || comp.salary_limit || TOPE_2_SMMLV;
        const dentroTope = datos.dentro_tope !== undefined ? datos.dentro_tope :
                          (comp.dentro_tope !== undefined ? comp.dentro_tope : (salarioBase <= salaryLimit));
        const aplica = dentroTope;

        // Datos del calculo - buscar en datos y comp
        const valorDiario = datos.daily_value || comp.daily_value || (VALOR_MENSUAL / 30);
        const diasTrabajados = datos.days || comp.days || datos.dias_trabajados || line.quantity || 0;
        const valorTotal = datos.total || comp.total || line.total || 0;

        // Validaciones aplicadas
        const validaciones = datos.validaciones || comp.validaciones || [];
        const sinValidacionTope = validaciones.includes('sin_validacion_tope');

        return {
            salario_base: salarioBase,
            tope_2_smmlv: salaryLimit,
            aplica: aplica,
            motivo_no_aplica: !aplica ? 'Salario supera 2 SMMLV' : null,
            sin_validacion_tope: sinValidacionTope,

            valor_mensual: VALOR_MENSUAL,
            valor_diario: valorDiario,
            dias_trabajados: diasTrabajados,
            dias_con_derecho: datos.dias_con_derecho || comp.dias_con_derecho || diasTrabajados,
            dias_primera_quincena: datos.dias_primera_quincena || comp.dias_primera_quincena || 0,
            dias_segunda_quincena: datos.dias_segunda_quincena || comp.dias_segunda_quincena || 0,
            variaciones: datos.variaciones || comp.variaciones || [],
            valor_calculado: valorTotal,
            validaciones: validaciones,
        };
    },
};

/**
 * ═══════════════════════════════════════════════════════════════════════════
 * REGISTRO INICIAL DE TEMPLATES
 * ═══════════════════════════════════════════════════════════════════════════
 */

// Registrar templates por código exacto
RuleTemplateRegistry.register('RT_MET_01', {
    templateName: 'lavish_hr_payroll.RuleTemplate.RetencionProc1',
    processor: RuleDataProcessors.processRetencionProc1,
    config: RULE_TEMPLATE_CONFIGS.RETENCION_PROC1,
});

RuleTemplateRegistry.register('RT_MET_02', {
    templateName: 'lavish_hr_payroll.RuleTemplate.RetencionProc2',
    processor: RuleDataProcessors.processRetencionProc1, // Usa el mismo procesador base
    config: RULE_TEMPLATE_CONFIGS.RETENCION_PROC2,
});

RuleTemplateRegistry.register('IBD', {
    templateName: 'lavish_hr_payroll.RuleTemplate.IBD',
    processor: RuleDataProcessors.processIBD,
    config: RULE_TEMPLATE_CONFIGS.IBD,
});

RuleTemplateRegistry.register('IBC', {
    templateName: 'lavish_hr_payroll.RuleTemplate.IBD',
    processor: RuleDataProcessors.processIBD,
    config: RULE_TEMPLATE_CONFIGS.IBD,
});

// Registrar templates por patrón
RuleTemplateRegistry.register('PRIMA.*', {
    templateName: 'lavish_hr_payroll.RuleTemplate.Prima',
    processor: RuleDataProcessors.processPrima,
    config: RULE_TEMPLATE_CONFIGS.PRIMA,
    isPattern: true,
    priority: 10,
});

RuleTemplateRegistry.register('CESANTIAS.*|CES_.*', {
    templateName: 'lavish_hr_payroll.RuleTemplate.Cesantias',
    processor: RuleDataProcessors.processCesantias,
    config: RULE_TEMPLATE_CONFIGS.CESANTIAS,
    isPattern: true,
    priority: 10,
});

RuleTemplateRegistry.register('INT_CES.*|ICES.*|INTCES.*|INTCES_.*', {
    templateName: 'lavish_hr_payroll.RuleTemplate.IntCesantias',
    processor: RuleDataProcessors.processIntCesantias,
    config: RULE_TEMPLATE_CONFIGS.INT_CESANTIAS,
    isPattern: true,
    priority: 10,
});

RuleTemplateRegistry.register('RTEFTE.*|RETEFUENTE.*', {
    templateName: 'lavish_hr_payroll.RuleTemplate.RetencionProc1',
    processor: RuleDataProcessors.processRetencionProc1,
    config: RULE_TEMPLATE_CONFIGS.RETENCION_PROC1,
    isPattern: true,
    priority: 5,
});

// Registrar templates de Liquidación
RuleTemplateRegistry.register('LIQ.*|LIQUIDACION.*', {
    templateName: 'lavish_hr_payroll.RuleTemplate.Liquidacion',
    processor: RuleDataProcessors.processLiquidacion,
    config: RULE_TEMPLATE_CONFIGS.LIQUIDACION,
    isPattern: true,
    priority: 10,
});

// Registrar templates de Provisión
// PRV_CES, PRV_ICES, PRV_PRIM, PRV_VAC son los codigos reales de provision
RuleTemplateRegistry.register('PROV.*|PROVISION.*|PRV_.*', {
    templateName: 'lavish_hr_payroll.RuleTemplate.Provision',
    processor: RuleDataProcessors.processProvision,
    config: RULE_TEMPLATE_CONFIGS.PROVISION,
    isPattern: true,
    priority: 10,
});

// Registrar templates de Auxilio de Transporte
// AUX000 = Auxilio de Transporte, AUX00C = Auxilio de Conectividad
RuleTemplateRegistry.register('AUX_TRANS.*|AUXILIO_TRANS.*|AUX000|AUX00C', {
    templateName: 'lavish_hr_payroll.RuleTemplate.AuxilioTransporte',
    processor: RuleDataProcessors.processAuxilioTransporte,
    config: RULE_TEMPLATE_CONFIGS.AUXILIO_TRANSPORTE,
    isPattern: true,
    priority: 10,
});

export default RuleTemplateRegistry;
