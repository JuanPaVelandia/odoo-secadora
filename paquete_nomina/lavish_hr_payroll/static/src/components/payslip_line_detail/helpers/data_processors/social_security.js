/** @odoo-module **/

/**
 * Procesador de Datos de Seguridad Social
 * 
 * Genera resumen de seguridad social con porcentajes y cálculos.
 * 
 * Parámetros por categoría:
 * - porcentajes: Porcentajes por tipo de seguridad social
 * - condiciones: Condiciones por tipo
 * - escalas: Escalas progresivas (ej: Subsistencia)
 */

/**
 * Configuración de porcentajes por tipo de seguridad social
 */
export const SS_PORCENTAJES = {
    SALUD: {
        empleado: 4.0,
        empresa: 8.5,
        total: 12.5,
        base_legal: 'Ley 100/1993 Art. 204'
    },
    PENSION: {
        empleado: 4.0,
        empresa: 12.0,
        total: 16.0,
        base_legal: 'Ley 100/1993 Art. 20'
    },
    FSP: {
        empleado: 0.5,
        empresa: 0,
        total: 0.5,
        base_legal: 'Ley 797/2003 Art. 7'
    }
};

/**
 * Configuración de condiciones por tipo
 */
export const SS_CONDICIONES = {
    SALUD: [
        'Aplica sobre IBC mensual',
        'No aplica si pensionado cotizante'
    ],
    PENSION: [
        'Aplica sobre IBC mensual',
        'No aplica si pensionado o > 3 SMMLV integral'
    ],
    FSP: [
        'Aplica si IBC > 4 SMMLV',
        'Deduccion adicional a pension'
    ],
    SUBSISTENCIA: [
        'Aplica si IBC > 16 SMMLV',
        'Escala progresiva 0.2% a 1.0%',
        'Adicional al FSP'
    ]
};

/**
 * Escala progresiva de Subsistencia según IBC en SMMLV
 */
export const SUBSISTENCIA_ESCALA = [
    { desde: 20, porcentaje: 1.0 },
    { desde: 19, porcentaje: 0.8 },
    { desde: 18, porcentaje: 0.6 },
    { desde: 17, porcentaje: 0.4 },
    { desde: 16, porcentaje: 0.2 }
];

/**
 * Calcula porcentaje de Subsistencia según IBC
 * @param {number} ibc - IBC del empleado
 * @param {number} smmlv - Valor del SMMLV
 * @returns {number} Porcentaje a aplicar (0.0 a 1.0)
 */
export function calcularPorcentajeSubsistencia(ibc, smmlv) {
    const ibcEnSmmlv = ibc / smmlv;
    for (const escala of SUBSISTENCIA_ESCALA) {
        if (ibcEnSmmlv >= escala.desde) {
            return escala.porcentaje;
        }
    }
    return 0;
}

/**
 * Genera resumen de seguridad social para una línea
 * @param {Object} line - Línea de nómina
 * @param {Object} computation - Datos de computation
 * @returns {Object|null} Resumen de seguridad social o null
 */
export function processSocialSecurityResumen(line, computation = {}) {
    const code = (line.code || '').toUpperCase();
    const datos = computation.datos || computation;

    const resumen = {
        tipo: '',
        porcentaje_empleado: 0,
        porcentaje_empresa: 0,
        porcentaje_total: 0,
        base_legal: '',
        entidad: '',
        ibc: datos.ibc || line.amount || 0,
        valor_empleado: line.total || 0,
        valor_empresa: 0,
        condiciones: []
    };

    if (code === 'SSOCIAL001' || code.includes('SALUD')) {
        const config = SS_PORCENTAJES.SALUD;
        resumen.tipo = 'SALUD';
        resumen.porcentaje_empleado = config.empleado;
        resumen.porcentaje_empresa = config.empresa;
        resumen.porcentaje_total = config.total;
        resumen.base_legal = config.base_legal;
        resumen.entidad = datos.eps_name || 'EPS';
        resumen.valor_empresa = resumen.ibc * (config.empresa / 100);
        resumen.condiciones = SS_CONDICIONES.SALUD;
        
    } else if (code === 'SSOCIAL002' || code.includes('PENSION')) {
        const config = SS_PORCENTAJES.PENSION;
        resumen.tipo = 'PENSION';
        resumen.porcentaje_empleado = config.empleado;
        resumen.porcentaje_empresa = config.empresa;
        resumen.porcentaje_total = config.total;
        resumen.base_legal = config.base_legal;
        resumen.entidad = datos.afp_name || 'AFP';
        resumen.valor_empresa = resumen.ibc * (config.empresa / 100);
        resumen.condiciones = SS_CONDICIONES.PENSION;
        
    } else if (code === 'SSOCIAL003' || code.includes('FSP')) {
        const config = SS_PORCENTAJES.FSP;
        resumen.tipo = 'FSP';
        resumen.porcentaje_empleado = config.empleado;
        resumen.porcentaje_empresa = config.empresa;
        resumen.porcentaje_total = config.total;
        resumen.base_legal = config.base_legal;
        resumen.entidad = 'Fondo Solidaridad';
        resumen.condiciones = SS_CONDICIONES.FSP;
        
    } else if (code === 'SSOCIAL004' || code.includes('SUBS')) {
        const smmlv = datos.smmlv || 1423500;
        const pct = calcularPorcentajeSubsistencia(resumen.ibc, smmlv);
        
        resumen.tipo = 'SUBSISTENCIA';
        resumen.porcentaje_empleado = pct;
        resumen.porcentaje_empresa = 0;
        resumen.porcentaje_total = pct;
        resumen.base_legal = 'Ley 797/2003 Art. 8';
        resumen.entidad = 'Fondo Subsistencia';
        resumen.condiciones = SS_CONDICIONES.SUBSISTENCIA;
    } else {
        // No es seguridad social reconocida
        return null;
    }

    return resumen;
}
