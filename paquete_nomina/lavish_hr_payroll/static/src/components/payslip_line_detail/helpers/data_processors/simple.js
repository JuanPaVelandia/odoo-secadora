/** @odoo-module **/

/**
 * Procesador de Datos para Vista Simple
 * 
 * Genera KPIs y fórmulas simples para reglas básicas.
 * 
 * Parámetros por categoría:
 * - kpi_config: Configuración de KPIs por tipo de campo
 * - formula_parts: Partes de fórmula por tipo de cálculo
 */

/**
 * Configuración de KPIs por tipo de campo
 */
export const KPI_CONFIG = {
    base: {
        etiqueta: 'Base',
        formato: 'currency',
        subtitulo: ''
    },
    cantidad: {
        etiqueta: 'Cantidad',
        formato: 'decimal',
        subtitulo: 'dias/unidades'
    },
    tasa: {
        etiqueta: 'Tasa',
        formato: 'percent',
        subtitulo: 'aplicada'
    },
    valor: {
        etiqueta: 'Valor',
        formato: 'currency',
        subtitulo: 'total'
    }
};

/**
 * Genera KPIs simples para una línea de nómina
 * @param {Object} line - Línea de nómina
 * @param {Object} computation - Datos de computation
 * @returns {Array} Array de KPIs
 */
export function processSimpleKpis(line, computation = {}) {
    const kpis = [];
    const comp = computation || {};

    // KPI 1: Base (salario/monto)
    if (line.amount && line.amount !== line.total) {
        kpis.push({
            etiqueta: comp.kpis?.[0]?.etiqueta || KPI_CONFIG.base.etiqueta,
            valor: line.amount,
            formato: comp.kpis?.[0]?.formato || KPI_CONFIG.base.formato,
            subtitulo: comp.kpis?.[0]?.subtitulo || KPI_CONFIG.base.subtitulo
        });
    }

    // KPI 2: Cantidad/Dias
    if (line.quantity && line.quantity !== 1) {
        kpis.push({
            etiqueta: comp.kpis?.[1]?.etiqueta || KPI_CONFIG.cantidad.etiqueta,
            valor: line.quantity,
            formato: comp.kpis?.[1]?.formato || KPI_CONFIG.cantidad.formato,
            subtitulo: comp.kpis?.[1]?.subtitulo || KPI_CONFIG.cantidad.subtitulo
        });
    }

    // KPI 3: Tasa
    if (line.rate && line.rate !== 100) {
        kpis.push({
            etiqueta: comp.kpis?.[2]?.etiqueta || KPI_CONFIG.tasa.etiqueta,
            valor: line.rate,
            formato: comp.kpis?.[2]?.formato || KPI_CONFIG.tasa.formato,
            subtitulo: comp.kpis?.[2]?.subtitulo || KPI_CONFIG.tasa.subtitulo
        });
    }

    // Si no hay KPIs, crear uno con el total
    if (kpis.length === 0) {
        kpis.push({
            etiqueta: KPI_CONFIG.valor.etiqueta,
            valor: line.total,
            formato: KPI_CONFIG.valor.formato,
            subtitulo: KPI_CONFIG.valor.subtitulo
        });
    }

    return kpis;
}

/**
 * Genera fórmula simple para una línea de nómina
 * @param {Object} line - Línea de nómina
 * @param {Object} computation - Datos de computation
 * @param {Function} formatCurrency - Función para formatear moneda
 * @returns {string|null} Fórmula generada o null
 */
export function processSimpleFormula(line, computation = {}, formatCurrency) {
    if (computation && computation.formula) {
        return computation.formula;
    }
    
    // Generar fórmula básica
    const parts = [];
    if (line.amount) parts.push(formatCurrency ? formatCurrency(line.amount) : line.amount);
    if (line.quantity && line.quantity !== 1) parts.push(`x ${line.quantity}`);
    if (line.rate && line.rate !== 100) parts.push(`x ${line.rate}%`);
    if (parts.length > 0) {
        parts.push(`= ${formatCurrency ? formatCurrency(line.total) : line.total}`);
        return parts.join(' ');
    }
    return null;
}
