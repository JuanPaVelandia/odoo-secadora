/** @odoo-module **/

/**
 * URLs de leyes colombianas para PayslipLineDetail
 * 
 * Este módulo contiene la función que mapea referencias legales a URLs
 * verificadas en funcionpublica.gov.co
 */

/**
 * Obtiene la URL de una ley o norma legal colombiana
 * @param {string} baseLegal - Referencia legal (ej: "Ley 1393/2010", "Art. 306 C.S.T.")
 * @returns {string|null} URL de la norma o null si no se encuentra
 */
export function getLeyUrl(baseLegal) {
    if (!baseLegal) return null;
    const text = baseLegal.toLowerCase();

    // === SEGURIDAD SOCIAL ===
    // Ley 1393 de 2010 (Regla 40%, limite 25 SMMLV)
    if (text.includes('1393')) {
        return 'https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=39995';
    }
    // Ley 100 de 1993 (Sistema de Seguridad Social)
    if (text.includes('ley 100') || (text.includes('100') && text.includes('1993'))) {
        return 'https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=5248';
    }
    // Decreto 780 de 2016 (Decreto Unico Sector Salud)
    if (text.includes('780') && text.includes('2016')) {
        return 'https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=77813';
    }
    // Ley 797 de 2003 (Reforma pensional)
    if (text.includes('797')) {
        return 'https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=7223';
    }
    // Decreto 1833 de 2016 (Sistema General de Pensiones)
    if (text.includes('1833')) {
        return 'https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=85319';
    }

    // === RETENCION EN LA FUENTE ===
    // Estatuto Tributario - Decreto 624 de 1989 (Art. 383, 385, 386, 387, 388)
    if (text.includes('estatuto tributario') || text.includes('624') || text.includes('art. 383') || text.includes('art. 385') || text.includes('art. 386') || text.includes('art. 387') || text.includes('art. 388')) {
        return 'https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=6533';
    }
    // Ley 1607 de 2012 (Reforma tributaria - IMAN/IMAS)
    if (text.includes('1607')) {
        return 'https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=51040';
    }
    // Ley 2277 de 2022 (Reforma tributaria)
    if (text.includes('2277')) {
        return 'https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=199883';
    }

    // === PRESTACIONES SOCIALES / CODIGO SUSTANTIVO DEL TRABAJO ===
    // Codigo Sustantivo del Trabajo - Decreto 2663 de 1950
    // Detectar cualquier articulo del C.S.T.
    if (text.includes('c.s.t') || text.includes('cst') || text.includes('codigo sustantivo') || text.includes('2663')) {
        return 'https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=199983';
    }
    // Articulos especificos del C.S.T. que linkean al CST completo
    // Art. 64 (Indemnizacion), Art. 127 (Salario), Art. 154-156 (Embargos)
    // Art. 159-168 (Horas extras), Art. 186-192 (Vacaciones), Art. 227 (Incapacidad)
    // Art. 249 (Cesantias), Art. 306 (Prima)
    if (text.match(/art\.?\s*(64|127|154|155|156|159|160|161|162|163|164|165|166|167|168|186|187|188|189|190|191|192|227|249|306)/i)) {
        return 'https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=199983';
    }
    // Ley 52/1975 - Decreto 116/1976 (Intereses cesantias 12% anual)
    if (text.includes('ley 52') || (text.includes('52') && text.includes('1975')) || text.includes('intereses cesant')) {
        return 'https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=3285';
    }
    // Decreto 2943 de 2013 (Incapacidades - 2 primeros dias empleador)
    if (text.includes('2943') || text.includes('decreto 2943')) {
        return 'https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=55977';
    }
    // Ley 50 de 1990 (Cesantias anualizadas, reforma laboral)
    if (text.includes('ley 50') || (text.includes('50') && text.includes('1990'))) {
        return 'https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=281';
    }
    // Ley 1788 de 2016 (Prima de servicios trabajadores domesticos)
    if (text.includes('1788')) {
        return 'http://www.secretariasenado.gov.co/senado/basedoc/ley_1788_2016.html';
    }

    // === AUXILIO DE TRANSPORTE ===
    // Ley 15 de 1959 (Auxilio de transporte - norma base)
    if (text.includes('ley 15') || (text.includes('15') && text.includes('1959')) || text.includes('auxilio de transporte')) {
        return 'https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=172765';
    }

    // === TIEMPO PARCIAL / JORNADA LABORAL / COTIZANTE 51 ===
    // Decreto 2616 de 2013 (Cotizacion SS tiempo parcial, base cotizante 51)
    if (text.includes('2616') || text.includes('tiempo parcial') || text.includes('cotizante 51') || text.includes('tipo 51')) {
        return 'https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=65326';
    }
    // Decreto 1990 de 2016 (PILA - Planilla Integrada)
    if (text.includes('1990') && text.includes('2016') || text.includes('pila')) {
        return 'https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=78396';
    }
    // Ley 2101 de 2021 (Reduccion jornada laboral 42h)
    if (text.includes('2101') || text.includes('jornada laboral')) {
        return 'https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=166506';
    }
    // Decreto 1042 de 1978 (Jornada empleados publicos)
    if (text.includes('1042') && text.includes('1978')) {
        return 'https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=1254';
    }
    // Decreto 1273 de 2018 (Independientes - pago mes vencido)
    if (text.includes('1273') && text.includes('2018')) {
        return 'https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=87624';
    }

    // === EMBARGOS ===
    // Art. 154-156 CST ya cubiertos arriba con CST

    return null;
}
