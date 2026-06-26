/** @odoo-module **/

/**
 * Parser de Computation para Provisiones
 * 
 * Parsea datos de computation para provisiones (Prima, Cesantías, Intereses, Vacaciones).
 * 
 * Parámetros:
 * - computation: Objeto computation completo
 * - line: Línea de nómina
 * 
 * Retorna objeto estructurado con:
 * - tipoProvision, baseLegal, explicacion
 * - baseTotal, salarioBase, variableTotal, auxilioTransporte
 * - diasPagados, diasComputables, diasPeriodo
 * - provisionCalculada, provisionAcumulada
 * - formulaPasos, conceptosIncluidos
 */

/**
 * Mapeo de códigos a tipos de provisión
 */
export const PROVISION_TYPES = {
    PRIMA: {
        tipo: 'PRIMA DE SERVICIOS',
        baseLegal: 'Art. 306 C.S.T.',
        explicacion: '30 días de salario por año trabajado, pagaderos en 2 cuotas semestrales',
        divisor: 360,
        tasa: 1.0
    },
    CESANTIAS: {
        tipo: 'CESANTÍAS',
        baseLegal: 'Art. 249 C.S.T.',
        explicacion: '30 días de salario por año de servicio, consignación antes del 15 de febrero',
        divisor: 360,
        tasa: 1.0
    },
    INTCES: {
        tipo: 'INTERESES CESANTÍAS',
        baseLegal: 'Ley 52/1975',
        explicacion: '12% anual sobre cesantías acumuladas, pagaderos en enero o al retiro',
        divisor: 360,
        tasa: 12.0
    },
    VACACIONES: {
        tipo: 'VACACIONES',
        baseLegal: 'Art. 186-192 C.S.T.',
        explicacion: '15 días hábiles remunerados por año de servicio',
        divisor: 720,
        tasa: 1.0
    }
};

/**
 * Detecta tipo de provisión por código
 * @param {string} code - Código de la línea
 * @returns {Object} Configuración del tipo de provisión
 */
export function detectProvisionType(code) {
    const codeUpper = (code || '').toUpperCase();
    
    if (codeUpper.includes('PRIMA')) {
        return PROVISION_TYPES.PRIMA;
    } else if (codeUpper.includes('INTCES') || codeUpper.includes('INT_CES')) {
        return PROVISION_TYPES.INTCES;
    } else if (codeUpper.includes('CES')) {
        return PROVISION_TYPES.CESANTIAS;
    } else if (codeUpper.includes('VAC')) {
        return PROVISION_TYPES.VACACIONES;
    }
    
    return PROVISION_TYPES.PRIMA; // Default
}

/**
 * Normaliza pasos de fórmula del backend
 * @param {Array} rawPasos - Pasos sin normalizar
 * @returns {Array} Pasos normalizados
 */
export function normalizeFormulaPasos(rawPasos = []) {
    return rawPasos.map((fp, idx) => {
        const desc = (fp.concepto || fp.formula_texto || '').toLowerCase()
            .normalize('NFD').replace(/[\u0300-\u036f]/g, '');
        let formato = fp.formato || 'currency';
        let valor = fp.resultado !== undefined ? fp.resultado : fp.valor;

        // Detectar formato por contenido
        if (fp.tipo === 'periodo' || (typeof valor === 'string' && valor.includes(' a '))) {
            formato = 'text';
        } else if (desc.includes('dias') || desc.includes('cantidad') ||
            desc.includes('meses') || desc.includes('semanas') || desc.includes('horas') ||
            desc.includes('factor') || desc.includes('numero') || desc.includes('proporcion')) {
            formato = 'integer';
        } else if (desc.includes('tasa') || desc.includes('porcentaje') || desc.includes('%')) {
            formato = 'percent';
        } else if (desc.includes('base') || desc.includes('salario') || desc.includes('valor') ||
                   desc.includes('total') || desc.includes('cesantias') || desc.includes('prima')) {
            formato = 'currency';
        }

        // Normalizar valor
        if (typeof valor === 'number' && isNaN(valor)) {
            valor = 0;
        } else if (valor === undefined || valor === null) {
            valor = formato === 'text' ? '-' : 0;
        }

        return {
            paso: fp.paso || idx + 1,
            concepto: fp.concepto || '',
            formulaTexto: fp.formula_texto || '',
            resultado: valor,
            formato: formato,
            tipo: fp.tipo || 'paso'
        };
    });
}

/**
 * Parsea computation para provisión
 * @param {Object} computation - Objeto computation completo
 * @param {Object} line - Línea de nómina
 * @returns {Object} Datos estructurados de provisión
 */
export function parseProvisionComputation(computation = {}, line = {}) {
    const comp = computation || {};
    const datos = comp.datos || comp;
    const dataKpi = datos.data_kpi || comp.data_kpi || {};
    const resumen = datos.resumen || {};
    const configGlobal = datos.config_global || {};
    const configAuxilio = datos.config_auxilio || {};
    const code = (line.code || '').toUpperCase();
    
    // Detectar tipo
    const provType = detectProvisionType(code);
    
    // Datos principales
    // Priorizar claves actuales del backend y mantener compatibilidad con legado.
    const salarioBase = datos.salario_periodo || resumen.salario_periodo || resumen.salary_basic || dataKpi.salary_base || 0;
    const variableTotal = datos.variable_total || resumen.variable_total || resumen.salary_variable || dataKpi.salary_variable || 0;
    const auxilioTransporte = datos.auxilio_transporte_periodo || resumen.auxilio_transporte_periodo || resumen.salary_auxilio || dataKpi.subsidy || 0;
    const baseTotal = datos.base_total || resumen.base_total || dataKpi.base_mensual || line.amount || 0;
    
    // Días
    const diasPeriodo = datos.dias_periodo || dataKpi.dias_periodo || resumen.dias_periodo || 30;
    const diasPagados = datos.dias_pagados || dataKpi.dias_pagados || resumen.dias_pagados || diasPeriodo;
    const diasAusenciasPagadas = datos.dias_ausencias_pagadas || dataKpi.dias_ausencias_pagadas || 0;
    const diasAusenciasNoPagadas = datos.dias_ausencias_no_pagadas || dataKpi.dias_ausencias_no_pagadas || 0;
    const diasComputables = datos.dias_computables || dataKpi.dias_computables || resumen.dias_computables || diasPagados;
    
    // Provisión
    const provisionCalculada = resumen.provision_calculada || dataKpi.provision_calculada || line.total || 0;
    const provisionAcumulada = (
        datos.provision_acumulada ??
        resumen.provision_acumulada ??
        dataKpi.provision_acumulada ??
        0
    );
    const saldoAnterior = (
        datos.saldo_contable ??
        resumen.saldo_contable ??
        resumen.saldo_anterior ??
        dataKpi.saldo_anterior ??
        0
    );
    const ajuste = (
        datos.ajuste ??
        resumen.ajuste ??
        dataKpi.ajuste ??
        0
    );
    const valorAnterior = dataKpi.valor_anterior || 0;
    const diferenciaPeriodoAnterior = dataKpi.diferencia_periodo_anterior || 0;
    
    // Configuración auxilio
    const aplicaAuxilio = (
        datos.aplica_auxilio_transporte ??
        configAuxilio.aplica ??
        dataKpi.aplica_auxilio ??
        false
    );
    
    // Conceptos incluidos
    const rawConceptos = datos.conceptos_incluidos || dataKpi.lineas_base_variable || [];
    const conceptosIncluidos = rawConceptos.map(l => ({
        codigo: l.codigo || '',
        nombre: typeof l.nombre === 'string' ? l.nombre :
               Array.isArray(l.nombre) ? (l.nombre[1] || l.nombre[0] || '') :
               (l.nombre?.name || l.nombre?.display_name || ''),
        valor: l.total || l.valor || l.valor_usado || 0,
        categoria: l.categoria || 'VAR',
        dias_formula: l.dias_formula || '-',
        tipo: l.tipo || 'variable',
        es_ausencia: !!l.es_ausencia
    }));
    
    // Fórmula pasos
    const rawFormulaPasos = datos.formula_pasos || [];
    const formulaPasos = normalizeFormulaPasos(rawFormulaPasos);
    
    // Indicadores y warnings
    const indicadores = datos.indicadores || [];
    const warnings = datos.warnings || [];
    
    // Método de cálculo
    const metodo = datos.metodo || configGlobal.metodo || 'simple';
    const metodoLabel = metodo === 'simple' ? 'Método Simple' : 
                       metodo === 'complejo' ? 'Método Complejo' : 
                       'Método Estándar';
    
    // Es liquidación
    const esLiquidacion = datos.es_liquidacion || dataKpi.es_liquidacion || false;
    
    // Fechas
    const fechaInicio = dataKpi.fecha_inicio || datos.fecha_inicio || '';
    const fechaCorte = dataKpi.fecha_corte || datos.fecha_corte || '';
    
    return {
        // Identificación
        codigo: code,
        nombre: line.name || '',
        tipoProvision: provType.tipo,
        baseLegal: provType.baseLegal,
        explicacion: provType.explicacion,
        metodo: metodo,
        metodoLabel: metodoLabel,
        esLiquidacion: esLiquidacion,
        
        // Base
        baseTotal: baseTotal,
        salarioBase: salarioBase,
        variableTotal: variableTotal,
        auxilioTransporte: auxilioTransporte,
        aplicaAuxilio: aplicaAuxilio,
        configAuxilio: configAuxilio,
        
        // Días
        diasPeriodo: diasPeriodo,
        diasPagados: diasPagados,
        diasAusenciasPagadas: diasAusenciasPagadas,
        diasAusenciasNoPagadas: diasAusenciasNoPagadas,
        diasComputables: diasComputables,
        
        // Cálculo
        periodoBase: provType.divisor,
        tasa: provType.tasa,
        provisionCalculada: provisionCalculada,
        provisionAcumulada: provisionAcumulada,
        saldoAnterior: saldoAnterior,
        ajuste: ajuste,
        totalReconocidoVigencia: provisionCalculada + provisionAcumulada,
        
        // Comparativa
        valorAnterior: valorAnterior,
        diferenciaPeriodoAnterior: diferenciaPeriodoAnterior,
        
        // Detalle
        conceptosIncluidos: conceptosIncluidos,
        formulaPasos: formulaPasos,
        indicadores: indicadores,
        warnings: warnings,
        
        // Fechas
        fechaInicio: fechaInicio,
        fechaCorte: fechaCorte
    };
}
