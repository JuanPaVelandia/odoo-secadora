/** @odoo-module **/

/**
 * Parser de Computation para Fórmula
 * 
 * Parsea datos de computation para visualizaciones de fórmula (tablas, rangos, columnas).
 * 
 * Parámetros:
 * - computation: Objeto computation completo
 * - line: Línea de nómina
 * 
 * Retorna objeto estructurado con:
 * - formula: Fórmula textual
 * - tablaRangos: Tabla de rangos si aplica
 * - columnaIzquierda/Derecha: Columnas si aplica
 * - explicacion: Explicación de la fórmula
 */

/**
 * Normaliza tabla de rangos
 * @param {Object} rawTabla - Tabla sin normalizar
 * @returns {Object} Tabla normalizada
 */
export function normalizeTablaRangos(rawTabla = {}) {
    const rangos = rawTabla.rangos || [];
    const columnas = rawTabla.columnas || ['Desde', 'Hasta', 'Tasa', 'Valor'];
    
    return {
        titulo: rawTabla.titulo || 'Tabla de Rangos',
        columnas: columnas,
        rangos: rangos.map((rango, idx) => ({
            desde: rango.desde || rango.min || 0,
            hasta: rango.hasta || rango.max || 0,
            tasa: rango.tasa || rango.porcentaje || 0,
            valor: rango.valor || rango.resultado || 0,
            aplicado: rango.aplicado || false,
            color: rango.color || null
        })),
        rangoAplicado: rangos.findIndex(r => r.aplicado) + 1 || null
    };
}

/**
 * Normaliza columnas izquierda/derecha
 * @param {Array} rawColumnas - Columnas sin normalizar
 * @param {string} lado - 'izquierda' o 'derecha'
 * @returns {Array} Columnas normalizadas
 */
export function normalizeColumnas(rawColumnas = [], lado = 'izquierda') {
    return rawColumnas.map((col, idx) => ({
        etiqueta: col.etiqueta || col.label || `Item ${idx + 1}`,
        valor: col.valor || col.value || 0,
        formato: col.formato || 'currency',
        color: col.color || null,
        icono: col.icono || null,
        explicacion: col.explicacion || ''
    }));
}

/**
 * Parsea computation para fórmula
 * @param {Object} computation - Objeto computation completo
 * @param {Object} line - Línea de nómina
 * @returns {Object} Datos estructurados de fórmula
 */
export function parseFormulaComputation(computation = {}, line = {}) {
    const comp = computation || {};
    const datos = comp.datos || comp;
    
    // Fórmula textual
    const formula = comp.formula || datos.formula || '';
    
    // Tabla de rangos
    const tablaRangos = comp.tabla_rangos || datos.tabla_rangos ? 
        normalizeTablaRangos(comp.tabla_rangos || datos.tabla_rangos) : null;
    
    // Columnas izquierda/derecha
    const columnaIzquierda = comp.columna_izquierda || datos.columna_izquierda ?
        normalizeColumnas(comp.columna_izquierda || datos.columna_izquierda, 'izquierda') : null;
    const columnaDerecha = comp.columna_derecha || datos.columna_derecha ?
        normalizeColumnas(comp.columna_derecha || datos.columna_derecha, 'derecha') : null;
    
    // Explicación
    const explicacion = comp.explicacion || datos.explicacion || '';
    const baseLegal = comp.base_legal || datos.base_legal || '';
    
    // Cotizante 51 (caso especial)
    const cotizante51 = comp.cotizante_51 || datos.cotizante_51 || null;
    
    // Tipo de visualización
    let tipoVisualizacion = 'formula_simple';
    if (tablaRangos) {
        tipoVisualizacion = 'formula_tabla';
    } else if (columnaIzquierda || columnaDerecha) {
        tipoVisualizacion = 'formula_columnas';
    } else if (cotizante51) {
        tipoVisualizacion = 'formula_cotizante51';
    }
    
    return {
        // Identificación
        codigo: (line.code || '').toUpperCase(),
        nombre: line.name || '',
        tipoVisualizacion: tipoVisualizacion,
        
        // Fórmula
        formula: formula,
        explicacion: explicacion,
        baseLegal: baseLegal,
        
        // Tabla de rangos
        tablaRangos: tablaRangos,
        
        // Columnas
        columnaIzquierda: columnaIzquierda,
        columnaDerecha: columnaDerecha,
        
        // Casos especiales
        cotizante51: cotizante51,
        
        // Valor total
        valorTotal: line.total || 0
    };
}
