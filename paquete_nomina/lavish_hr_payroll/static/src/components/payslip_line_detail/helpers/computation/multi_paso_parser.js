/** @odoo-module **/

/**
 * Parser de Computation para Multi-Paso
 * 
 * Parsea datos de computation para visualizaciones multi-paso (IBD, Retenciones complejas).
 * 
 * Parámetros:
 * - computation: Objeto computation completo
 * - line: Línea de nómina
 * 
 * Retorna objeto estructurado con:
 * - pasos: Array de pasos expandibles
 * - timeline: Datos para timeline visual
 * - explicacionLegal: Explicación legal asociada
 */

/**
 * Normaliza un paso individual
 * @param {Object} rawPaso - Paso sin normalizar
 * @param {number} index - Índice del paso
 * @returns {Object} Paso normalizado
 */
export function normalizeStep(rawPaso, index) {
    const paso = rawPaso || {};
    const desc = (paso.concepto || paso.descripcion || paso.texto || '').toLowerCase()
        .normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    
    let formato = paso.formato || 'currency';
    let valor = paso.resultado !== undefined ? paso.resultado : paso.valor;

    // Detectar formato
    if (paso.tipo === 'periodo' || (typeof valor === 'string' && valor.includes(' a '))) {
        formato = 'text';
    } else if (desc.includes('dias') || desc.includes('cantidad') ||
        desc.includes('meses') || desc.includes('semanas') || desc.includes('horas') ||
        desc.includes('factor') || desc.includes('numero') || desc.includes('proporcion')) {
        formato = 'integer';
    } else if (desc.includes('tasa') || desc.includes('porcentaje') || desc.includes('%')) {
        formato = 'percent';
    } else if (desc.includes('base') || desc.includes('salario') || desc.includes('valor') ||
               desc.includes('total') || desc.includes('ibc') || desc.includes('ibd')) {
        formato = 'currency';
    }

    // Normalizar valor
    if (typeof valor === 'number' && isNaN(valor)) {
        valor = 0;
    } else if (valor === undefined || valor === null) {
        valor = formato === 'text' ? '-' : 0;
    }

    return {
        numero: paso.numero || paso.paso || index + 1,
        titulo: paso.titulo || paso.concepto || paso.descripcion || `Paso ${index + 1}`,
        descripcion: paso.descripcion || paso.concepto || '',
        valor: valor,
        formato: formato,
        tipo: paso.tipo || 'paso',
        color: paso.color || null,
        icono: paso.icono || null,
        legal: paso.legal || paso.base_legal || '',
        explicacion: paso.explicacion || '',
        subpasos: paso.subpasos || [],
        tabla: paso.tabla || null
    };
}

/**
 * Genera timeline visual desde pasos
 * @param {Array} pasos - Array de pasos normalizados
 * @returns {Array} Array de elementos de timeline
 */
export function generateTimeline(pasos) {
    const colors = ['#3B82F6', '#8B5CF6', '#F97316', '#22C55E', '#EC4899', '#14B8A6', '#EF4444'];
    
    return pasos.map((paso, idx) => ({
        numero: paso.numero,
        label: paso.titulo.substring(0, 20), // Truncar para UI
        color: paso.color || colors[idx % colors.length],
        icono: paso.icono || null,
        isFinal: idx === pasos.length - 1
    }));
}

/**
 * Parsea computation para multi-paso
 * @param {Object} computation - Objeto computation completo
 * @param {Object} line - Línea de nómina
 * @returns {Object} Datos estructurados multi-paso
 */
export function parseMultiPasoComputation(computation = {}, line = {}) {
    const comp = computation || {};
    const datos = comp.datos || comp;
    
    // Obtener pasos desde diferentes ubicaciones posibles
    let rawPasos = comp.pasos || [];
    
    // Si no hay pasos directos, buscar en explicacion_legal
    if (rawPasos.length === 0 && datos.explicacion_legal) {
        const expLegal = datos.explicacion_legal;
        rawPasos = expLegal.explicaciones_legales || expLegal.pasos || [];
    }
    
    // Si aún no hay pasos, buscar en timeline
    if (rawPasos.length === 0 && comp.timeline) {
        rawPasos = comp.timeline.pasos || [];
    }
    
    // Normalizar pasos
    const pasos = rawPasos.map((p, idx) => normalizeStep(p, idx));
    
    // Generar timeline
    const timeline = comp.timeline || generateTimeline(pasos);
    
    // Explicación legal
    const explicacionLegal = datos.explicacion_legal || comp.explicacion_legal || {};
    
    // Título y descripción general
    const titulo = comp.titulo || datos.titulo || line.name || '';
    const descripcion = comp.descripcion || datos.descripcion || '';
    const baseLegal = explicacionLegal.base_legal || comp.base_legal || '';
    
    // Resumen
    const resumen = datos.resumen || comp.resumen || {};
    const valorTotal = resumen.valor_total || line.total || 0;
    const valorInicial = resumen.valor_inicial || pasos[0]?.valor || 0;
    
    return {
        // Identificación
        codigo: (line.code || '').toUpperCase(),
        nombre: line.name || '',
        titulo: titulo,
        descripcion: descripcion,
        baseLegal: baseLegal,
        
        // Pasos
        pasos: pasos,
        totalPasos: pasos.length,
        
        // Timeline
        timeline: timeline,
        
        // Explicación legal
        explicacionLegal: explicacionLegal,
        
        // Resumen
        valorTotal: valorTotal,
        valorInicial: valorInicial,
        
        // Configuración
        mostrarTimeline: comp.mostrar_timeline !== false,
        expandirPrimerPaso: comp.expandir_primer_paso !== false,
        expandirUltimoPaso: comp.expandir_ultimo_paso !== false
    };
}
