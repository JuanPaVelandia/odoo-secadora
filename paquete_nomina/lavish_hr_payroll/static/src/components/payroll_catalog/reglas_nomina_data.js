/** @odoo-module **/

/**
 * ============================================================================
 * DATOS DE REGLAS DE NOMINA COLOMBIANA
 * ============================================================================
 *
 * Contiene todas las reglas, normas legales y tablas de calculo
 * para el sistema de nomina colombiano.
 *
 * Parametros 2025:
 * - SMMLV: $1,423,500
 * - UVT: $49,799
 * - Auxilio Transporte: $200,000
 */

export const UVT_2025 = 49799;
export const SMMLV_2025 = 1423500;
export const AUX_TRANSPORTE_2025 = 200000;

export const REGLAS_NOMINA = {

    // ========================================================================
    // IBC - INGRESO BASE DE COTIZACION
    // ========================================================================
    ibc: {
        titulo: "INGRESO BASE DE COTIZACION (IBC)",
        fundamentoLegal: {
            normas: [
                {
                    id: "LEY-1393-2010",
                    nombre: "Ley 1393 de 2010",
                    articulo: "Art. 30",
                    descripcion: "Regla del 40% para devengos no constitutivos de salario"
                },
                {
                    id: "DEC-1406-1999",
                    nombre: "Decreto 1406 de 1999",
                    articulo: "Art. 18-19",
                    descripcion: "Reglamentacion del IBC para el Sistema de Seguridad Social Integral"
                },
                {
                    id: "CST-127",
                    nombre: "Codigo Sustantivo del Trabajo",
                    articulo: "Art. 127-128",
                    descripcion: "Definicion de salario y factores constitutivos"
                },
                {
                    id: "DEC-780-2016",
                    nombre: "Decreto 780 de 2016",
                    articulo: "Art. 3.2.2.1",
                    descripcion: "Unificacion normativa del Sistema de Seguridad Social"
                }
            ],
            explicacion: `El Ingreso Base de Cotizacion (IBC) constituye la base gravable sobre la cual se calculan
los aportes al Sistema de Seguridad Social Integral. Segun el articulo 18 del Decreto 1406 de 1999,
el IBC comprende todos los pagos que constituyen salario conforme al articulo 127 del CST.

La Ley 1393 de 2010 establece que los pagos no constitutivos de salario no podran exceder el 40%
del total de la remuneracion. El exceso sobre este limite debera incluirse en la base de cotizacion.`
        },
        reglas: [
            { id: "IBC-001", codigo: "IBD", nombre: "IBC Diario", secuencia: 100, fechaCreacion: "2024-01-15", estado: "Activa", formula: "Suma(Devengos Salariales) / 30" },
            { id: "IBC-002", codigo: "IBC", nombre: "IBC Mensual", secuencia: 101, fechaCreacion: "2024-01-15", estado: "Activa", formula: "IBD x Dias Cotizados" },
            { id: "IBC-003", codigo: "ACTUALIBC_R", nombre: "Actualizacion IBC Retroactivo", secuencia: 102, fechaCreacion: "2024-02-01", estado: "Activa", formula: "IBC Anterior + Ajustes" }
        ],
        calculo: {
            formula: `
R = Salario + Devengos No Salariales
T = 40% x R
E = max(0, Devengos No Salariales - T)
IBC = Salario + E

TOPES (Art. 5 Ley 797 de 2003):
- Minimo: 1 SMMLV ($1,423,500 para 2025)
- Maximo: 25 SMMLV ($35,587,500 para 2025)`,
            ejemplo: {
                salarioBasico: 3500000,
                devengosNoSalariales: 2000000,
                remuneracionTotal: 5500000,
                limite40: 2200000,
                exceso: 0,
                ibcFinal: 3500000
            }
        }
    },

    // ========================================================================
    // SEGURIDAD SOCIAL
    // ========================================================================
    seguridadSocial: {
        titulo: "SEGURIDAD SOCIAL",
        fundamentoLegal: {
            normas: [
                { id: "LEY-100-1993", nombre: "Ley 100 de 1993", articulo: "Art. 15-22", descripcion: "Sistema General de Seguridad Social Integral" },
                { id: "LEY-797-2003", nombre: "Ley 797 de 2003", articulo: "Art. 5", descripcion: "Reforma pensional - topes y cotizaciones" },
                { id: "LEY-1122-2007", nombre: "Ley 1122 de 2007", articulo: "Art. 10", descripcion: "Cotizacion al Sistema General de Salud" },
                { id: "DEC-1295-1994", nombre: "Decreto 1295 de 1994", articulo: "Completo", descripcion: "Sistema General de Riesgos Laborales" }
            ],
            explicacion: `El Sistema de Seguridad Social Integral comprende Salud (EPS), Pension (AFP),
y Riesgos Laborales (ARL). Las cotizaciones se calculan sobre el IBC con las siguientes tarifas:

- SALUD: 12.5% (8.5% empleador + 4% trabajador) - Ley 1122/2007
- PENSION: 16% (12% empleador + 4% trabajador) - Ley 797/2003
- ARL: Variable segun nivel de riesgo (0.522% - 6.96%) - Dec. 1295/1994`
        },
        reglas: [
            { id: "SS-001", codigo: "SALUD_EMP", nombre: "Aporte Salud Empleador", secuencia: 200, estado: "Activa", porcentaje: 8.5, formula: "IBC x 8.5%" },
            { id: "SS-002", codigo: "SALUD_TRAB", nombre: "Aporte Salud Trabajador", secuencia: 201, estado: "Activa", porcentaje: 4.0, formula: "IBC x 4%" },
            { id: "SS-003", codigo: "PENSION_EMP", nombre: "Aporte Pension Empleador", secuencia: 210, estado: "Activa", porcentaje: 12.0, formula: "IBC x 12%" },
            { id: "SS-004", codigo: "PENSION_TRAB", nombre: "Aporte Pension Trabajador", secuencia: 211, estado: "Activa", porcentaje: 4.0, formula: "IBC x 4%" },
            { id: "SS-005", codigo: "FSP", nombre: "Fondo de Solidaridad Pensional", secuencia: 220, estado: "Activa", porcentaje: 1.0, formula: "IBC x 1% (si IBC > 4 SMMLV)" },
            { id: "SS-006", codigo: "FSP_SUB", nombre: "Fondo de Subsistencia", secuencia: 221, estado: "Activa", porcentaje: "Variable", formula: "0.2% - 1% adicional segun tabla" },
            { id: "SS-007", codigo: "ARL", nombre: "Aporte ARL", secuencia: 230, estado: "Activa", porcentaje: "Variable", formula: "IBC x Tarifa segun nivel riesgo" }
        ],
        tablaFSP: [
            { rango: "4 - 16 SMMLV", adicional: "0%", total: "1.0%" },
            { rango: "16 - 17 SMMLV", adicional: "0.2%", total: "1.2%" },
            { rango: "17 - 18 SMMLV", adicional: "0.4%", total: "1.4%" },
            { rango: "18 - 19 SMMLV", adicional: "0.6%", total: "1.6%" },
            { rango: "19 - 20 SMMLV", adicional: "0.8%", total: "1.8%" },
            { rango: "> 20 SMMLV", adicional: "1.0%", total: "2.0%" }
        ],
        tablaARL: [
            { nivel: "I", tarifa: "0.522%", descripcion: "Riesgo minimo (oficinas, administracion)" },
            { nivel: "II", tarifa: "1.044%", descripcion: "Riesgo bajo (comercio, servicios)" },
            { nivel: "III", tarifa: "2.436%", descripcion: "Riesgo medio (manufactura ligera)" },
            { nivel: "IV", tarifa: "4.350%", descripcion: "Riesgo alto (construccion, mineria)" },
            { nivel: "V", tarifa: "6.960%", descripcion: "Riesgo maximo (extraccion petrolera)" }
        ]
    },

    // ========================================================================
    // RETENCIONES
    // ========================================================================
    retenciones: {
        titulo: "RETENCION EN LA FUENTE",
        fundamentoLegal: {
            normas: [
                { id: "ET-383", nombre: "Estatuto Tributario", articulo: "Art. 383", descripcion: "Tabla de retencion en la fuente para ingresos laborales" },
                { id: "ET-387", nombre: "Estatuto Tributario", articulo: "Art. 387", descripcion: "Deducciones y rentas exentas" },
                { id: "ET-388", nombre: "Estatuto Tributario", articulo: "Art. 388", descripcion: "Depuracion de la base de retencion" },
                { id: "LEY-1819-2016", nombre: "Ley 1819 de 2016", articulo: "Art. 1-17", descripcion: "Reforma tributaria estructural" },
                { id: "DEC-2250-2017", nombre: "Decreto 2250 de 2017", articulo: "Completo", descripcion: "Reglamentacion retencion sobre rentas de trabajo" }
            ],
            explicacion: `La retencion en la fuente sobre ingresos laborales se calcula mediante el procedimiento
de depuracion establecido en el Art. 388 del E.T., restando del ingreso bruto las deducciones
permitidas (aportes obligatorios, dependientes, medicina prepagada, intereses de vivienda)
y la renta exenta del 25% (limitada a 240 UVT mensuales).

El valor de la UVT para 2025 es de $49,799, lo que establece limites y rangos actualizados
para el calculo de la retencion.`
        },
        reglas: [
            { id: "RET-001", codigo: "RET_FTE", nombre: "Retencion en la Fuente", secuencia: 300, estado: "Activa", linea: "Ingreso gravable despues de depuracion", formula: "Segun tabla Art. 383 E.T." },
            { id: "RET-002", codigo: "RET_PRIMA", nombre: "Retencion sobre Prima", secuencia: 301, estado: "Activa", linea: "Prima de servicios", formula: "0% hasta 95 UVT, luego tabla normal" },
            { id: "RET-003", codigo: "RET_CESANTIAS", nombre: "Retencion sobre Cesantias", secuencia: 302, estado: "Activa", linea: "Cesantias e intereses", formula: "Exentas (Art. 206 Num. 4 E.T.)" },
            { id: "RET-004", codigo: "RET_VACACIONES", nombre: "Retencion sobre Vacaciones", secuencia: 303, estado: "Activa", linea: "Vacaciones compensadas", formula: "0% hasta 95 UVT, luego tabla normal" },
            { id: "RET-005", codigo: "RET_INDEM", nombre: "Retencion sobre Indemnizacion", secuencia: 304, estado: "Activa", linea: "Indemnizacion por despido", formula: "Exenta hasta limites Art. 206 E.T." }
        ],
        tablaRetencion: [
            { rangoDesde: 0, rangoHasta: 95, tarifa: "0%", formula: "$0" },
            { rangoDesde: 95, rangoHasta: 150, tarifa: "19%", formula: "(Ingreso UVT - 95) x 19%" },
            { rangoDesde: 150, rangoHasta: 360, tarifa: "28%", formula: "(Ingreso UVT - 150) x 28% + 10.45 UVT" },
            { rangoDesde: 360, rangoHasta: 640, tarifa: "33%", formula: "(Ingreso UVT - 360) x 33% + 69.05 UVT" },
            { rangoDesde: 640, rangoHasta: 945, tarifa: "35%", formula: "(Ingreso UVT - 640) x 35% + 161.45 UVT" },
            { rangoDesde: 945, rangoHasta: 2300, tarifa: "37%", formula: "(Ingreso UVT - 945) x 37% + 268.20 UVT" },
            { rangoDesde: 2300, rangoHasta: 99999, tarifa: "39%", formula: "(Ingreso UVT - 2300) x 39% + 769.55 UVT" }
        ],
        depuracion: [
            { concepto: "Ingreso Bruto Laboral", tipo: "+" },
            { concepto: "(-) Aportes obligatorios salud (4%)", tipo: "-" },
            { concepto: "(-) Aportes obligatorios pension (4%)", tipo: "-" },
            { concepto: "(-) Aportes voluntarios pension (hasta 25% ingreso)", tipo: "-" },
            { concepto: "(-) Cuenta AFC (hasta 25% ingreso)", tipo: "-" },
            { concepto: "(-) Intereses vivienda (hasta 100 UVT/mes)", tipo: "-" },
            { concepto: "(-) Medicina prepagada (hasta 16 UVT/mes)", tipo: "-" },
            { concepto: "(-) Dependientes (10% ingreso, max 32 UVT)", tipo: "-" },
            { concepto: "(=) Subtotal", tipo: "=" },
            { concepto: "(-) Renta exenta 25% (max 240 UVT)", tipo: "-" },
            { concepto: "(=) Base Gravable", tipo: "=" }
        ]
    },

    // ========================================================================
    // PRESTACIONES SOCIALES
    // ========================================================================
    prestaciones: {
        titulo: "PRESTACIONES SOCIALES",
        fundamentoLegal: {
            normas: [
                { id: "CST-306", nombre: "Codigo Sustantivo del Trabajo", articulo: "Art. 306-308", descripcion: "Prima de servicios - derecho y cuantia" },
                { id: "CST-249", nombre: "Codigo Sustantivo del Trabajo", articulo: "Art. 249-258", descripcion: "Cesantias - regimen y liquidacion" },
                { id: "LEY-52-1975", nombre: "Ley 52 de 1975", articulo: "Art. 1", descripcion: "Intereses sobre cesantias (12% anual)" },
                { id: "CST-186", nombre: "Codigo Sustantivo del Trabajo", articulo: "Art. 186-192", descripcion: "Vacaciones anuales remuneradas" },
                { id: "CST-253", nombre: "Codigo Sustantivo del Trabajo", articulo: "Art. 253", descripcion: "Promedio salarial para liquidaciones" }
            ],
            explicacion: `Las prestaciones sociales constituyen derechos irrenunciables del trabajador colombiano.
Se calculan sobre el salario promedio que incluye todos los factores constitutivos de salario
mas el auxilio de transporte (para prima y cesantias, no para vacaciones).

Cuando el salario es variable o ha variado en los ultimos 3 meses, se aplica el Art. 253 CST
para calcular el promedio sobre los ultimos 12 meses o la fraccion trabajada.`
        },
        reglas: {
            prima: [
                { id: "PRIM-001", codigo: "PRIMA_SEM1", nombre: "Prima Semestre 1", secuencia: 400, estado: "Activa", formula: "(Salario + Aux.Transp) x Dias / 360", baseLegal: "Art. 306 CST" },
                { id: "PRIM-002", codigo: "PRIMA_SEM2", nombre: "Prima Semestre 2", secuencia: 401, estado: "Activa", formula: "(Salario + Aux.Transp) x Dias / 360", baseLegal: "Art. 306 CST" },
                { id: "PRIM-003", codigo: "PRIMA_PROP", nombre: "Prima Proporcional (Liquidacion)", secuencia: 402, estado: "Activa", formula: "Promedio x Dias Semestre / 180", baseLegal: "Art. 306-308 CST" }
            ],
            cesantias: [
                { id: "CES-001", codigo: "CESANTIAS", nombre: "Cesantias Anuales", secuencia: 410, estado: "Activa", formula: "(Salario + Aux.Transp) x Dias / 360", baseLegal: "Art. 249 CST" },
                { id: "CES-002", codigo: "INT_CESANTIAS", nombre: "Intereses sobre Cesantias", secuencia: 411, estado: "Activa", formula: "Cesantias x Dias x 12% / 360", baseLegal: "Ley 52 de 1975" },
                { id: "CES-003", codigo: "CES_PARCIAL", nombre: "Cesantias Parciales", secuencia: 412, estado: "Activa", formula: "Cesantias acumuladas (retiro parcial)", baseLegal: "Art. 254 CST" }
            ],
            vacaciones: [
                { id: "VAC-001", codigo: "VAC_DISFRUTE", nombre: "Vacaciones Disfrutadas", secuencia: 420, estado: "Activa", formula: "Salario Base x Dias / 30", baseLegal: "Art. 186 CST" },
                { id: "VAC-002", codigo: "VAC_DINERO", nombre: "Vacaciones en Dinero", secuencia: 421, estado: "Activa", formula: "Salario x 15 / 360 x Anos", baseLegal: "Art. 189 CST" },
                { id: "VAC-003", codigo: "VAC_PROP", nombre: "Vacaciones Proporcionales", secuencia: 422, estado: "Activa", formula: "Salario x Dias / 720", baseLegal: "Art. 186-189 CST" }
            ]
        },
        calculoDetallado: {
            prima: {
                titulo: "PRIMA DE SERVICIOS",
                formula: "Base = Salario Promedio + Auxilio de Transporte\nPrima = Base x Dias Trabajados / 360",
                incluyeAuxTransporte: true,
                diasAnuales: 30,
                fechasPago: {
                    semestre1: "Junio 30",
                    semestre2: "Diciembre 20"
                }
            },
            cesantias: {
                titulo: "CESANTIAS",
                formula: "Base = Ultimo Salario + Auxilio de Transporte\nCesantias = Base x Dias Trabajados / 360",
                incluyeAuxTransporte: true,
                interesesAnuales: 12,
                fechasLimite: {
                    deposito: "Febrero 14",
                    pagoIntereses: "Enero 31"
                }
            },
            vacaciones: {
                titulo: "VACACIONES",
                formula: "Dias de derecho = 15 dias habiles por ano trabajado\nVacaciones = Salario x 15 x Anos / 360",
                incluyeAuxTransporte: false,
                diasAnuales: 15
            }
        }
    },

    // ========================================================================
    // PARAFISCALES
    // ========================================================================
    parafiscales: {
        titulo: "APORTES PARAFISCALES",
        fundamentoLegal: {
            normas: [
                { id: "LEY-21-1982", nombre: "Ley 21 de 1982", articulo: "Art. 7", descripcion: "Aportes a Cajas de Compensacion Familiar" },
                { id: "LEY-89-1988", nombre: "Ley 89 de 1988", articulo: "Art. 2", descripcion: "Aportes al SENA" },
                { id: "LEY-27-1974", nombre: "Ley 27 de 1974", articulo: "Art. 1", descripcion: "Aportes al ICBF" },
                { id: "LEY-1607-2012", nombre: "Ley 1607 de 2012", articulo: "Art. 25", descripcion: "Exoneracion de aportes (CREE)" }
            ],
            explicacion: `Los aportes parafiscales se calculan sobre la nomina y tienen destinos especificos:

- SENA (2%): Formacion profesional
- ICBF (3%): Proteccion de la ninez
- Cajas de Compensacion (4%): Subsidio familiar

EXONERACION (Ley 1607/2012): Empresas que tributan renta y contribuyentes de
regimen especial estan exoneradas de SENA e ICBF para trabajadores con salario < 10 SMMLV.`
        },
        reglas: [
            { id: "PARF-001", codigo: "SENA", nombre: "Aporte SENA", secuencia: 500, estado: "Activa", porcentaje: 2.0, formula: "Nomina x 2%", exonerable: true },
            { id: "PARF-002", codigo: "ICBF", nombre: "Aporte ICBF", secuencia: 501, estado: "Activa", porcentaje: 3.0, formula: "Nomina x 3%", exonerable: true },
            { id: "PARF-003", codigo: "CCF", nombre: "Caja de Compensacion", secuencia: 502, estado: "Activa", porcentaje: 4.0, formula: "Nomina x 4%", exonerable: false }
        ]
    }
};

/**
 * Funciones de utilidad para calculos
 */
export const PayrollCalculations = {

    /**
     * Calcula el IBC aplicando regla del 40%
     */
    calcularIBC(salarioBasico, devengosNoSalariales) {
        const remuneracionTotal = salarioBasico + devengosNoSalariales;
        const limite40 = remuneracionTotal * 0.4;
        const exceso = Math.max(0, devengosNoSalariales - limite40);
        return salarioBasico + exceso;
    },

    /**
     * Calcula la prima de servicios
     */
    calcularPrima(salarioBasico, auxTransporte, diasTrabajados) {
        return (salarioBasico + auxTransporte) * diasTrabajados / 360;
    },

    /**
     * Calcula cesantias
     */
    calcularCesantias(salarioBasico, auxTransporte, diasTrabajados) {
        return (salarioBasico + auxTransporte) * diasTrabajados / 360;
    },

    /**
     * Calcula intereses sobre cesantias
     */
    calcularInteresesCesantias(cesantias, diasTrabajados) {
        return cesantias * diasTrabajados * 0.12 / 360;
    },

    /**
     * Calcula vacaciones
     */
    calcularVacaciones(salarioBasico, diasTrabajados) {
        return salarioBasico * 15 * (diasTrabajados / 360) / 360;
    },

    /**
     * Calcula FSP segun rango salarial
     */
    calcularFSP(ibc, smmlv) {
        const rangoSMMLV = ibc / smmlv;

        if (rangoSMMLV <= 4) return 0;
        if (rangoSMMLV <= 16) return ibc * 0.01;
        if (rangoSMMLV <= 17) return ibc * 0.012;
        if (rangoSMMLV <= 18) return ibc * 0.014;
        if (rangoSMMLV <= 19) return ibc * 0.016;
        if (rangoSMMLV <= 20) return ibc * 0.018;
        return ibc * 0.02;
    },

    /**
     * Formatea valor como moneda colombiana
     */
    formatCurrency(value) {
        return new Intl.NumberFormat('es-CO', {
            style: 'currency',
            currency: 'COP',
            minimumFractionDigits: 0,
            maximumFractionDigits: 0
        }).format(value);
    }
};
