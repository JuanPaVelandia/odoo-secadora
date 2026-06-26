/** @odoo-module **/

import { Component, useState, onWillRender } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";

// Sub-componentes importados desde index centralizado
import {
    PayslipLineHeader,
    PayslipLineContextual,
    PayslipLineSimple,
    PayslipLineProvision,
    PayslipLineSocialSecurity,
    PayslipLinePrestacion,
    PayslipLineMultiPaso,
    PayslipLineFormula,
} from "./components";

// Helpers importados desde index centralizado
import {
    VISUALIZATION_TYPE_MAP,
    RULE_CONFIG,
    STEP_COLORS,
    getRuleConfig,
    getLeyUrl,
    formatValue,
    formatCurrency,
    translateKey,
    getStepColor,
} from "./helpers";

/**
 * PayslipLineDetail - Widget visual para detalle de linea de nomina
 * Adaptado segun GUIA_POSICIONAMIENTO_WIDGET_FORMULA.txt
 *
 * Soporta 3 tipos de visualizacion:
 * - simple: KPIs en fila + formula corta
 * - formula: 2 columnas (inputs + pasos) + tabla rangos opcional
 * - multi_paso: Timeline + pasos expandibles
 * - provision: Vista detallada de provisiones (4 pasos)
 * - prestacion: Vista de prestaciones sociales
 * 
 * ARQUITECTURA DE SUB-COMPONENTES:
 * ├── PayslipLineHeader       - Cabecera con código, nombre, badge devengo/deducción
 * ├── PayslipLineContextual   - Info contextual (préstamos, novedades, ausencias)
 * ├── PayslipLineSimple       - Vista simple con KPIs en fila
 * ├── PayslipLineProvision    - Vista detallada de provisiones
 * ├── PayslipLineSocialSecurity - Vista seguridad social
 * ├── PayslipLinePrestacion   - Vista de prestaciones sociales
 * ├── PayslipLineMultiPaso    - Vista multi-paso con timeline
 * └── PayslipLineFormula      - Vista de fórmula con 2 columnas
 */
export class PayslipLineDetail extends Component {
    static template = "lavish_hr_payroll.PayslipLineDetail";
    static props = { ...standardFieldProps };
    
    // Registro de sub-componentes para uso en template
    static components = {
        PayslipLineHeader,
        PayslipLineContextual,
        PayslipLineSimple,
        PayslipLineProvision,
        PayslipLineSocialSecurity,
        PayslipLinePrestacion,
        PayslipLineMultiPaso,
        PayslipLineFormula,
    };

    // Configuracion de tipos de visualizacion por codigo de regla (importado de helpers)
    static VISUALIZATION_TYPE_MAP = VISUALIZATION_TYPE_MAP;

    // Configuracion de estilos por tipo de regla (importado de helpers)
    static RULE_CONFIG = RULE_CONFIG;

    // Colores para pasos del timeline (importado de helpers)
    static STEP_COLORS = STEP_COLORS;

    setup() {
        this.action = useService("action");

        this.state = useState({
            sections: {
                pasos: true,
                reglas: true,
                detalle: false,
                info: false,
                ibc_componentes: true,
                ibc_validaciones: true,
                // Provisiones
                prov_base: true,
                prov_conceptos: false,
                prov_dias: true,
                prov_formula: true,
                prov_resultado: true,
                prov_acumulado: true,
                prov_comparativa: true,
                // Prestaciones
                prest_variable: false,
            },
            expandedSteps: {}, // Para multi_paso: {1: true, 7: true}
            expandedProvSteps: {1: true, 2: true, 3: true, 4: true}, // Para provisiones
            expandedFlujoItems: {}, // Para retencion: {ingresos: true, incr: false, ...}
            activeTimelineStep: null,
        });

        this.computation = null;
        this._stepsInitialized = false;
        onWillRender(() => this.parseComputation());
    }

    parseComputation() {
        const raw = this.props.record.data[this.props.name];
        if (!raw) {
            this.computation = null;
            return;
        }
        try {
            this.computation = typeof raw === 'string' ? JSON.parse(raw) : raw;
            // Inicializar pasos expandidos para multi_paso
            if (this.visualizationType === 'multi_paso') {
                this._initExpandedSteps();
            }
        } catch (e) {
            console.error('[parseComputation] Parse error:', e);
            this.computation = null;
        }
    }

    _initExpandedSteps() {
        // Solo inicializar una vez para evitar loop infinito
        if (this._stepsInitialized || !this.computation) return;
        this._stepsInitialized = true;

        // Obtener pasos directamente del computation sin usar el getter
        const rawPasos = this.computation.pasos ||
            (this.computation.datos?.explicacion_legal?.explicaciones_legales) || [];

        if (rawPasos.length > 0) {
            const newExpanded = {};
            // Expandir primer y ultimo paso por defecto
            newExpanded[1] = true;
            newExpanded[rawPasos.length] = true;
            this.state.expandedSteps = newExpanded;
        }
    }

    get line() {
        return this.props.record.data;
    }

    get hasComputation() {
        return this.computation && Object.keys(this.computation).length > 0;
    }

    get isDevengo() {
        return this.line.dev_or_ded === 'devengo';
    }

    // ==================== INFORMACION CONTEXTUAL ====================
    // Muestra informacion segun el tipo de linea: prestamo, novedad, ausencia, etc.

    get hasContextualInfo() {
        const line = this.line;
        // Tiene relacion si tiene loan_id, concept_id, leave_id, vacation_leave_id
        return !!(line.loan_id || line.concept_id || line.leave_id || line.vacation_leave_id);
    }

    get contextualInfo() {
        const line = this.line;
        const comp = this.computation || {};

        // Estructura base con indicadores de base
        const result = {
            tipo: line.object_type || 'regular',
            has_relation: false,
            relation_type: null,
            kpis: [],
            notas: [],
            acciones: [],
            relation_data: {},
            // Indicadores de base - estos se muestran como badges
            liquidar_con_base: line.liquidar_con_base || false,
            base_seguridad_social: line.base_seguridad_social || false,
            base_prima: line.base_prima || false,
            base_cesantias: line.base_cesantias || false,
            base_vacaciones: line.base_vacaciones || false,
            badges: [],  // Badges a mostrar en header
        };

        // Generar badges segun indicadores
        if (result.liquidar_con_base) {
            result.badges.push({
                label: 'IBC',
                tooltip: 'Liquidar con IBC mes anterior',
                color: 'success',
                icon: 'fa-calculator'
            });
        }
        if (result.base_seguridad_social) {
            result.badges.push({
                label: 'SS',
                tooltip: 'Base Seguridad Social',
                color: 'info',
                icon: 'fa-shield'
            });
        }
        if (result.base_prima) {
            result.badges.push({
                label: 'PRI',
                tooltip: 'Base Prima',
                color: 'warning',
                icon: 'fa-gift'
            });
        }
        if (result.base_cesantias) {
            result.badges.push({
                label: 'CES',
                tooltip: 'Base Cesantias',
                color: 'primary',
                icon: 'fa-bank'
            });
        }

        // === PRESTAMOS ===
        if (line.loan_id) {
            result.has_relation = true;
            result.relation_type = 'loan';

            // Extraer datos del computation si disponibles
            const loanData = comp.loan_data || comp.prestamo || {};

            // Datos basicos de la linea
            const loanName = Array.isArray(line.loan_id) ? line.loan_id[1] : (line.loan_id?.display_name || 'Prestamo');

            result.relation_data = {
                name: loanName,
                loan_type: loanData.loan_type || '',
                loan_type_label: loanData.loan_type_label || this._getLoanTypeLabel(loanData.loan_type),
                original_amount: loanData.original_amount || 0,
                total_paid: loanData.total_paid || 0,
                remaining_amount: loanData.remaining_amount || 0,
                pending_installments: loanData.pending_installments || 0,
                total_installments: loanData.total_installments || 0,
                cuota_actual: loanData.cuota_actual || 0,
                payment_end_date: loanData.payment_end_date || null,
                porcentaje_pagado: loanData.porcentaje_pagado || 0,
            };

            // KPIs para prestamo
            if (loanData.cuota_actual && loanData.total_installments) {
                result.kpis.push({
                    label: 'Cuota',
                    value: `${loanData.cuota_actual}/${loanData.total_installments}`,
                    icon: 'fa-hashtag',
                    color: 'info'
                });
            }
            if (loanData.total_paid > 0) {
                result.kpis.push({
                    label: 'Pagado',
                    value: loanData.total_paid,
                    format: 'currency',
                    icon: 'fa-check',
                    color: 'success'
                });
            }
            if (loanData.remaining_amount > 0) {
                result.kpis.push({
                    label: 'Pendiente',
                    value: loanData.remaining_amount,
                    format: 'currency',
                    icon: 'fa-clock-o',
                    color: 'warning'
                });
            }

            // Barra de progreso
            if (loanData.porcentaje_pagado > 0) {
                result.progress = {
                    value: loanData.porcentaje_pagado,
                    label: `${loanData.porcentaje_pagado}% pagado`
                };
            }

        // === NOVEDADES DE CONTRATO ===
        } else if (line.concept_id) {
            result.has_relation = true;
            result.relation_type = 'concept';

            const conceptData = comp.concept_data || comp.novedad || {};
            const conceptName = Array.isArray(line.concept_id) ? line.concept_id[1] : (line.concept_id?.display_name || 'Novedad');

            const typeLabels = {
                'P': 'Prestamo Empresa',
                'A': 'Ahorro',
                'S': 'Seguro',
                'L': 'Libranza',
                'E': 'Embargo',
                'R': 'Retencion',
                'O': 'Otros'
            };

            const aplicarLabels = {
                '15': '1ra Quincena',
                '30': '2da Quincena',
                '0': 'Ambas Quincenas'
            };

            const modalityLabels = {
                'fijo': 'Valor Fijo',
                'diario': 'Valor Diario',
                'diario_efectivo': 'Diario Efectivo'
            };

            result.relation_data = {
                name: conceptName,
                type_deduction: conceptData.type_deduction || '',
                type_deduction_label: typeLabels[conceptData.type_deduction] || conceptData.type_deduction_label || 'Concepto',
                type_emb: conceptData.type_emb || '',
                aplicar: conceptData.aplicar || '',
                aplicar_label: aplicarLabels[conceptData.aplicar] || conceptData.aplicar_label || '',
                modality_value: conceptData.modality_value || 'fijo',
                modality_label: modalityLabels[conceptData.modality_value] || conceptData.modality_label || '',
                monthly_behavior: conceptData.monthly_behavior || '',
                period: conceptData.period || 'indefinite',
                // Saldos y estadisticas
                balance: conceptData.balance || 0,
                total_paid: conceptData.total_paid || 0,
                remaining_installments: conceptData.remaining_installments || 0,
                // Proyecciones
                proyectar_seguridad_social: conceptData.proyectar_seguridad_social || false,
                proyectar_nomina: conceptData.proyectar_nomina || false,
                // Control
                double_payment: line.double_payment || conceptData.double_payment || false,
                is_previous_period: line.is_previous_period || conceptData.is_previous_period || false,
            };

            // KPIs
            result.kpis.push({
                label: 'Tipo',
                value: result.relation_data.type_deduction_label,
                icon: 'fa-tag',
                color: 'primary'
            });

            // Aplicacion
            if (result.relation_data.aplicar_label) {
                result.kpis.push({
                    label: 'Aplica',
                    value: result.relation_data.aplicar_label,
                    icon: 'fa-calendar',
                    color: 'info'
                });
            }

            // Saldo si tiene periodo limitado
            if (result.relation_data.period === 'limited' && result.relation_data.balance > 0) {
                result.kpis.push({
                    label: 'Saldo',
                    value: result.relation_data.balance,
                    format: 'currency',
                    icon: 'fa-balance-scale',
                    color: 'warning'
                });
            }

            // Cuotas restantes
            if (result.relation_data.remaining_installments > 0) {
                result.kpis.push({
                    label: 'Restantes',
                    value: `${result.relation_data.remaining_installments} cuotas`,
                    icon: 'fa-list-ol',
                    color: 'info'
                });
            }

            // Acciones especiales
            if (line.double_payment) {
                result.acciones.push({
                    accion: 'PAGO_DOBLE',
                    label: 'Pago Doble',
                    icon: 'fa-clone',
                    color: 'warning',
                    descripcion: 'Recuperando cuota saltada'
                });
            }

            if (line.is_previous_period) {
                result.notas.push({
                    texto: 'Novedad de periodo anterior',
                    icon: 'fa-history',
                    color: 'info'
                });
            }

            // Notas de modalidad
            if (result.relation_data.modality_value && result.relation_data.modality_value !== 'fijo') {
                result.notas.push({
                    texto: `Modalidad: ${result.relation_data.modality_label}`,
                    icon: 'fa-calculator',
                    color: 'info'
                });
            }

            // Proyecciones
            if (result.relation_data.proyectar_seguridad_social) {
                result.notas.push({
                    texto: 'Proyecta en Seguridad Social',
                    icon: 'fa-shield',
                    color: 'success'
                });
            }

        // === AUSENCIAS ===
        } else if (line.leave_id && !line.vacation_leave_id) {
            result.has_relation = true;
            result.relation_type = 'leave';

            const leaveData = comp.leave_data || comp.ausencia || {};
            const leaveName = Array.isArray(line.leave_id) ? line.leave_id[1] : (line.leave_id?.display_name || 'Ausencia');

            result.relation_data = {
                name: leaveName,
                leave_type: leaveData.leave_type || '',
                number_of_days: line.leave_number_of_days || leaveData.number_of_days || line.quantity || 0,
                date_from: line.leave_date_from || leaveData.date_from || null,
                date_to: line.leave_date_to || leaveData.date_to || null,
                fecha_regreso: leaveData.fecha_regreso || null,
                entity: leaveData.entity || null,
            };

            // KPIs
            result.kpis.push({
                label: 'Dias',
                value: result.relation_data.number_of_days,
                icon: 'fa-calendar-times-o',
                color: 'warning'
            });

            if (result.relation_data.leave_type) {
                result.kpis.push({
                    label: 'Tipo',
                    value: result.relation_data.leave_type,
                    icon: 'fa-medkit',
                    color: 'danger'
                });
            }

            // Fecha de regreso
            if (result.relation_data.date_to) {
                result.notas.push({
                    texto: `Hasta: ${this._formatDate(result.relation_data.date_to)}`,
                    icon: 'fa-calendar-check-o',
                    color: 'success'
                });
            }

        // === VACACIONES ===
        } else if (line.vacation_leave_id || line.object_type === 'vacation') {
            result.has_relation = true;
            result.relation_type = 'vacation';

            const vacData = comp.vacation_data || comp.vacaciones || {};
            const vacName = line.vacation_leave_id ?
                (Array.isArray(line.vacation_leave_id) ? line.vacation_leave_id[1] : line.vacation_leave_id?.display_name) :
                'Vacaciones';

            result.relation_data = {
                name: vacName || 'Vacaciones',
                number_of_days: line.quantity || vacData.number_of_days || 0,
                vacation_departure_date: line.vacation_departure_date || vacData.departure_date || null,
                vacation_return_date: line.vacation_return_date || vacData.return_date || null,
            };

            // KPIs
            result.kpis.push({
                label: 'Dias',
                value: result.relation_data.number_of_days,
                icon: 'fa-sun-o',
                color: 'info'
            });

            // Fechas
            if (result.relation_data.vacation_departure_date) {
                result.notas.push({
                    texto: `Salida: ${this._formatDate(result.relation_data.vacation_departure_date)}`,
                    icon: 'fa-sign-out',
                    color: 'info'
                });
            }
            if (result.relation_data.vacation_return_date) {
                result.notas.push({
                    texto: `Regreso: ${this._formatDate(result.relation_data.vacation_return_date)}`,
                    icon: 'fa-sign-in',
                    color: 'success'
                });
            }

        // === LINEAS SIN RELACION ===
        } else {
            result.has_relation = false;

            // KPIs basicos segun categoria
            const catCode = line.category_code || '';
            const code = (line.code || '').toUpperCase();

            if (catCode === 'BASIC' || code.startsWith('BASIC')) {
                result.kpis = [
                    { label: 'Salario', value: line.total, format: 'currency', icon: 'fa-money', color: 'success' },
                    { label: 'Dias', value: line.quantity, icon: 'fa-calendar', color: 'info' },
                ];
            } else if (catCode === 'HEYREC' || code.startsWith('HE_')) {
                result.kpis = [
                    { label: 'Valor', value: line.total, format: 'currency', icon: 'fa-clock-o', color: 'primary' },
                    { label: 'Horas', value: line.quantity, icon: 'fa-hourglass', color: 'info' },
                ];
            } else if (code.includes('PROV') || code.includes('PRV')) {
                result.kpis = [
                    { label: 'Provision', value: line.total, format: 'currency', icon: 'fa-database', color: 'purple' },
                ];
            } else if (line.dev_or_ded === 'deduccion') {
                result.kpis = [
                    { label: 'Deduccion', value: Math.abs(line.total), format: 'currency', icon: 'fa-minus-circle', color: 'danger' },
                ];
            } else {
                result.kpis = [
                    { label: 'Total', value: line.total, format: 'currency', icon: 'fa-dollar', color: 'primary' },
                ];
            }
        }

        return result;
    }

    _getLoanTypeLabel(type) {
        const labels = {
            'advance': 'Anticipo',
            'loan': 'Prestamo',
            'advance_prima': 'Anticipo Prima',
            'advance_cesantias': 'Anticipo Cesantias'
        };
        return labels[type] || type || 'Prestamo';
    }

    _formatDate(dateStr) {
        if (!dateStr) return '';
        try {
            const date = new Date(dateStr);
            return date.toLocaleDateString('es-CO', { day: '2-digit', month: '2-digit', year: 'numeric' });
        } catch (e) {
            return dateStr;
        }
    }

    // ==================== TIPO DE VISUALIZACION ====================

    get visualizationType() {
        const code = (this.line.code || '').toUpperCase();

        // 1. Provisiones: siempre usar vista provision (prioridad maxima)
        // Detecta: PROV_, PRV_, _PROV, _PRV, PROVISION
        if (code.startsWith('PROV_') || code.startsWith('PRV_') ||
            code.includes('_PROV') || code.includes('_PRV') ||
            code.includes('PROVISION')) {
            return 'provision';
        }

        // 2. Si el computation especifica tipo, usarlo
        // Soportar tanto 'tipo' como 'tipo_visualizacion' (IBD usa tipo_visualizacion)
        if (this.computation) {
            const tipo = this.computation.tipo || this.computation.tipo_visualizacion;
            if (tipo) {
                // Mapear 'ibd' a 'multi_paso' ya que 'ibd' es el tipo de visualizacion interno
                if (tipo === 'ibd') return 'multi_paso';
                return tipo;
            }
        }

        // 3. Detectar por estructura del computation
        if (this.computation) {
            // Cotizante 51 -> formula con tabla
            if (this.computation.cotizante_51 || this.computation.variante === 'ibd_cotizante_51') {
                return 'formula';
            }
            // Tiene timeline o mas de 5 pasos -> multi_paso
            if (this.computation.timeline || (this.computation.pasos && this.computation.pasos.length > 5)) {
                return 'multi_paso';
            }
            // Tiene explicacion_legal con 7 pasos (IBD) -> multi_paso
            if (this.computation.datos && this.computation.datos.explicacion_legal) {
                const expLegal = this.computation.datos.explicacion_legal;
                if (expLegal.explicaciones_legales && expLegal.explicaciones_legales.length >= 5) {
                    return 'multi_paso';
                }
            }
            // Tiene tabla_rangos -> formula
            if (this.computation.tabla_rangos) {
                return 'formula';
            }
            // Tiene columna_izquierda/derecha -> formula
            if (this.computation.columna_izquierda || this.computation.columna_derecha) {
                return 'formula';
            }
        }

        // 4. Detectar por codigo de regla en mapa
        for (const [key, type] of Object.entries(PayslipLineDetail.VISUALIZATION_TYPE_MAP)) {
            if (code === key || code.startsWith(key)) {
                return type;
            }
        }

        // 5. Default: simple para la mayoria
        return 'simple';
    }

    get isSimple() {
        return this.visualizationType === 'simple';
    }

    get isFormula() {
        return this.visualizationType === 'formula';
    }

    get isMultiPaso() {
        return this.visualizationType === 'multi_paso';
    }

    get isProvision() {
        return this.visualizationType === 'provision';
    }

    get isPrestacion() {
        return this.visualizationType === 'prestacion';
    }

    // ==================== PRESTACION: Datos para Prima, Cesantias, Vacaciones ====================

    get prestacionData() {
        const comp = this.computation || {};
        const datos = comp.datos || comp;
        const dataKpi = datos.data_kpi || comp.data_kpi || {};
        const resumen = datos.resumen || {};
        const configGlobal = datos.config_global || {};
        const configAuxilio = datos.config_auxilio || {};
        const line = this.line;
        const code = (line.code || '').toUpperCase();

        // Detectar tipo de prestacion
        let tipoPrestacion = 'PRESTACION';
        let baseLegal = 'C.S.T.';
        let explicacion = '';
        let divisor = 360;

        if (code.includes('PRIMA')) {
            baseLegal = 'Art. 306 C.S.T.';
            tipoPrestacion = 'PRIMA DE SERVICIOS';
            explicacion = '30 días de salario por año trabajado, pagaderos en 2 cuotas semestrales';
            divisor = 360;
        } else if (code.includes('INTCES') || code.includes('INT_CES')) {
            baseLegal = 'Ley 52/1975';
            tipoPrestacion = 'INTERESES CESANTÍAS';
            explicacion = '12% anual sobre cesantías acumuladas, pagaderos en enero o al retiro';
            divisor = 360;
        } else if (code.includes('CES')) {
            baseLegal = 'Art. 249 C.S.T.';
            tipoPrestacion = 'CESANTÍAS';
            explicacion = '30 días de salario por año de servicio, consignación antes del 15 de febrero';
            divisor = 360;
        } else if (code.includes('VAC')) {
            baseLegal = 'Art. 186-192 C.S.T.';
            tipoPrestacion = 'VACACIONES';
            explicacion = '15 días hábiles remunerados por año de servicio';
            divisor = 720;
        }

        // Datos principales del resumen
        const salarioBase = resumen.salary_basic || dataKpi.salary_base || 0;
        const variableTotal = resumen.salary_variable || dataKpi.salary_variable || 0;
        const variableAcumulado = resumen.salary_variable_acumulado || dataKpi.salary_variable_acumulado || 0;
        const variableActual = resumen.salary_variable_actual || dataKpi.salary_variable_actual || 0;
        const auxilioTransporte = resumen.salary_auxilio || dataKpi.subsidy || 0;
        const baseTotal = resumen.base_total || dataKpi.base_mensual || line.amount || 0;

        // Dias
        const diasTrabajados = dataKpi.days_worked || line.quantity || 0;
        const diasNoPagados = dataKpi.days_no_pay || 0;
        const mesesPeriodo = dataKpi.meses_periodo || resumen.meses_periodo || 6;

        // Conceptos adicionales
        const conceptosSumar = resumen.conceptos_sumar || dataKpi.conceptos_sumar || 0;
        const conceptosRestar = resumen.conceptos_restar || dataKpi.conceptos_restar || 0;
        const conceptosNeto = resumen.conceptos_neto || dataKpi.conceptos_neto || 0;

        // Formula pasos del backend - normalizar con formato
        const rawFormulaPasos = datos.formula_pasos || [];
        const formulaPasos = rawFormulaPasos.map((fp, idx) => {
            const desc = (fp.concepto || fp.formula_texto || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
            let formato = fp.formato || 'currency';
            let valor = fp.resultado !== undefined ? fp.resultado : fp.valor;

            // Si el tipo es 'periodo' o el valor es string (fechas), usar formato text
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

            // Solo convertir a 0 si es número NaN, no si es string válido
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

        // Indicadores del backend
        const indicadores = datos.indicadores || [];

        // Lineas variables detalladas
        const lineasVariable = dataKpi.lineas_base_variable || [];
        const lineasNormalizadas = lineasVariable.map(l => ({
            codigo: l.codigo || '',
            nombre: typeof l.nombre === 'string' ? l.nombre :
                   Array.isArray(l.nombre) ? (l.nombre[1] || l.nombre[0] || '') :
                   (l.nombre?.name || l.nombre?.display_name || ''),
            total: l.total || 0,
            valorUsado: l.valor_usado || 0,
            tipo: l.tipo || 'variable',
            fecha: l.fecha || '',
            slipNumber: l.slip_number || '',
            payslipId: l.payslip_id || null,
            categoria: l.categoria || ''
        }));

        // Reglas usadas
        const reglasUsadas = dataKpi.reglas_usadas || datos.trazabilidad?.reglas_usadas || [];

        // Comparativa periodo anterior
        const valoresAnteriores = dataKpi.valores_anteriores || datos.trazabilidad?.valores_anteriores || {};
        const diferencia = dataKpi.diferencia_periodo_anterior || datos.trazabilidad?.diferencia || 0;
        const porcentajeCambio = dataKpi.porcentaje_cambio || datos.trazabilidad?.porcentaje_cambio || 0;

        // Config auxilio
        const aplicaAuxilio = configAuxilio.aplica || dataKpi.aplica_auxilio || false;

        // Dias adicionales
        const diasAdicionales = dataKpi.dias_adicionales_info || {};

        return {
            // Identificacion
            codigo: code,
            nombre: line.name || '',
            tipoPrestacion: tipoPrestacion,
            baseLegal: baseLegal,
            explicacion: explicacion,
            esLiquidacion: resumen.es_liquidacion || false,

            // Componentes del salario
            salarioBase: salarioBase,
            variableTotal: variableTotal,
            variableAcumulado: variableAcumulado,
            variableActual: variableActual,
            auxilioTransporte: auxilioTransporte,
            baseTotal: baseTotal,
            mesesPeriodo: mesesPeriodo,

            // Conceptos adicionales
            conceptosSumar: conceptosSumar,
            conceptosRestar: conceptosRestar,
            conceptosNeto: conceptosNeto,

            // Dias
            diasTrabajados: diasTrabajados,
            diasNoPagados: diasNoPagados,
            diasAdicionales: diasAdicionales,
            divisor: divisor,

            // Pasos de formula
            formulaPasos: formulaPasos,

            // Indicadores
            indicadores: indicadores,

            // Lineas variables
            lineasVariable: lineasNormalizadas,

            // Reglas usadas
            reglasUsadas: reglasUsadas,

            // Comparativa
            valorAnterior: valoresAnteriores.valor_anterior || 0,
            diferencia: diferencia,
            porcentajeCambio: porcentajeCambio,

            // Config
            aplicaAuxilio: aplicaAuxilio,
            configAuxilio: configAuxilio,
            configGlobal: configGlobal,

            // Total
            total: line.total || resumen.valor_prestacion || 0
        };
    }

    // ==================== PROVISION: Datos para vista contable ====================

    get provisionData() {
        const comp = this.computation || {};
        const datos = comp.datos || comp.data_kpi || comp;
        const dataKpi = comp.data_kpi || datos.data_kpi || {};
        const resumen = datos.resumen || {};
        const configGlobal = datos.config_global || {};
        const configAuxilio = datos.config_auxilio || {};
        const line = this.line;
        const code = (line.code || '').toUpperCase();

        // Detectar tipo de provision y configurar tasa/base legal
        let tipoProvision = resumen.tipo_provision || 'Provision';
        let baseLegal = 'Art. 249, 306 C.S.T.';
        let explicacion = '';
        let tasaDefault = 8.33;
        let periodoBase = 360;

        if (code.includes('PRIMA') || code.includes('PRIM')) {
            baseLegal = 'Art. 306 C.S.T.';
            tipoProvision = 'Provisión Prima';
            tasaDefault = configGlobal.tasa_prima || 8.33;
            explicacion = 'Prima de servicios: 30 días de salario por año trabajado. Se provisiona mensualmente al ' + tasaDefault + '% del salario base.';
        } else if (code.includes('ICES') || code.includes('INTCES') || code.includes('INT_CES')) {
            baseLegal = 'Ley 52/1975';
            tipoProvision = 'Provisión Int. Cesantías';
            tasaDefault = configGlobal.tasa_intereses || 12;
            explicacion = 'Intereses sobre cesantías: 12% anual sobre cesantías acumuladas. Se pagan en enero o al retiro.';
        } else if (code.includes('CES') && !code.includes('ICES')) {
            baseLegal = 'Art. 249 C.S.T. / Ley 50/1990';
            tipoProvision = 'Provisión Cesantías';
            tasaDefault = configGlobal.tasa_cesantias || 8.33;
            explicacion = 'Cesantías: 30 días de salario por año de servicio. Se consignan al fondo antes del 15 de febrero.';
        } else if (code.includes('VAC')) {
            baseLegal = 'Art. 186-192 C.S.T.';
            tipoProvision = 'Provisión Vacaciones';
            tasaDefault = configGlobal.tasa_vacaciones || 4.17;
            explicacion = 'Vacaciones: 15 días hábiles por año. Se provisionan al ' + tasaDefault + '% mensual.';
        }

        // Valores principales del calculo
        const salarioPeriodo = datos.salario_periodo || dataKpi.base_mensual || datos.salario_base_mensual || dataKpi.salary_base || 0;
        const salarioBase = datos.salario_base_mensual || salarioPeriodo || dataKpi.salary_base || 0;
        const variableTotal = datos.variable_total || dataKpi.salary_variable || 0;
        const variableMensual = datos.variable_mensual || dataKpi.salary_variable_acumulado || 0;
        const auxilioTransporte = datos.auxilio_transporte_periodo || dataKpi.subsidy || 0;
        const auxilioMensual = datos.auxilio_transporte_mensual || dataKpi.subsidy_mensual || 0;
        const baseTotal = datos.base_total || dataKpi.base_mensual || resumen.base_total || line.amount || 0;
        const salarioMensualReferencia = datos.salario_base_mensual_real || dataKpi.salary_base || salarioBase || 0;
        const salarioAjuste = Math.max(0, salarioMensualReferencia - salarioBase);

        // Dias
        const diasPeriodo = datos.dias_periodo || 360;
        const diasPagados = datos.dias_pagados || dataKpi.days_worked || line.quantity || 30;
        const diasAusenciasPagadas = datos.dias_ausencias_pagadas || 0;
        const diasAusenciasNoPagadas = datos.dias_ausencias_no_pagadas || dataKpi.days_no_pay || 0;
        const diasComputables = datos.dias_computables || diasPagados;
        const salarioDias = datos.salario_dias_display || diasPagados;
        const auxilioDias = datos.auxilio_dias_display || datos.auxilio_dias_usados || diasPagados;

        // Tasa aplicada
        const tasa = resumen.tasa_aplicada || datos.tasa || tasaDefault;

        // Calculo de provision
        const provisionCalculada = line.total || resumen.valor_provision || datos.total_causado_con_tasa || 0;
        const saldoAnterior = (
            datos.saldo_contable ??
            resumen.saldo_contable ??
            resumen.saldo_anterior ??
            0
        );
        const provisionAcumulada = (
            datos.provision_acumulada ??
            resumen.provision_acumulada ??
            dataKpi.provision_acumulada ??
            0
        );
        const ajuste = (
            datos.ajuste ??
            resumen.ajuste ??
            dataKpi.ajuste ??
            0
        );
        const totalReconocidoVigencia = provisionCalculada + provisionAcumulada;

        // Método de cálculo
        const metodo = datos.metodo || (configGlobal.metodo_simple_activo ? 'simple' : 'complejo');
        const metodoLabel = resumen.metodo_calculo || (metodo === 'simple' ? 'Método Simple (Rápido)' : 'Método Complejo (Acumulación)');

        // Conceptos incluidos en la base - normalizar estructura
        const rawConceptos = datos.conceptos_incluidos || dataKpi.lineas_base_variable || [];
        const conceptosIncluidos = rawConceptos.map(c => {
            // Normalizar nombre: puede ser string, array [id, name], u objeto {name: ...}
            let nombreStr = '';
            if (typeof c.nombre === 'string') {
                nombreStr = c.nombre;
            } else if (Array.isArray(c.nombre)) {
                nombreStr = c.nombre[1] || c.nombre[0] || '';
            } else if (c.nombre && typeof c.nombre === 'object') {
                nombreStr = c.nombre.name || c.nombre.display_name || JSON.stringify(c.nombre);
            } else if (c.name) {
                // Fallback a 'name' si existe
                nombreStr = typeof c.name === 'string' ? c.name :
                           Array.isArray(c.name) ? (c.name[1] || c.name[0] || '') :
                           (c.name.name || c.name.display_name || '');
            }
            return {
                codigo: c.codigo || c.code || '',
                nombre: nombreStr,
                valor: c.valor || c.total || c.valor_usado || 0,
                categoria: c.categoria || c.category || ''
            };
        });

        // Formula pasos del backend - normalizar con formato correcto
        const rawFormulaPasos = datos.formula_pasos || [];
        const formulaPasos = rawFormulaPasos.map((fp, idx) => {
            // Detectar formato segun descripcion del paso
            const desc = (fp.concepto || fp.label || fp.formula_texto || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
            let formato = fp.formato || 'currency';

            // Si es periodo, dias, cantidad, etc. - no es moneda
            if (desc.includes('periodo') || desc.includes('dias') ||
                desc.includes('cantidad') || desc.includes('meses') ||
                desc.includes('semanas') || desc.includes('horas') ||
                desc.includes('factor') || desc.includes('numero') ||
                desc.includes('proporcion') || desc.includes('tiempo')) {
                formato = 'integer';
            } else if (desc.includes('tasa') || desc.includes('porcentaje') || desc.includes('%')) {
                formato = 'percent';
            }

            // Validar que el valor es numerico
            let valor = fp.resultado !== undefined ? fp.resultado : fp.valor;
            if (valor === undefined || valor === null || (typeof valor === 'number' && isNaN(valor))) {
                valor = 0;
            }

            return {
                paso: fp.paso || idx + 1,
                concepto: fp.concepto || fp.label || '',
                formula_texto: fp.formula_texto || '',
                resultado: valor,
                formato: formato
            };
        });

        // Indicadores visuales
        const indicadores = datos.indicadores || [];

        // Auxilio transporte info
        const aplicaAuxilio = datos.aplica_auxilio_transporte || configAuxilio.aplica || false;
        const auxilioModalidad = datos.auxilio_modality || configAuxilio.modality_aux || 'no';

        // Franjas de salario (si hubo cambio)
        const huboCambioSalario = datos.hubo_cambio_salario || false;
        const franjasSalario = datos.franjas_salario || [];

        // Valores anteriores para comparativa
        const valoresAnteriores = datos.valores_anteriores || dataKpi.valores_anteriores || {};
        const valorAnterior = valoresAnteriores.valor_anterior || 0;
        const diferenciaPeriodoAnterior = datos.diferencia_periodo_anterior || comp.trazabilidad?.diferencia_periodo_anterior || 0;

        // Fechas
        const fechaInicio = resumen.periodo ? resumen.periodo.split(' al ')[0] : null;
        const fechaCorte = resumen.periodo ? resumen.periodo.split(' al ')[1] : null;

        // Warnings del backend
        const warnings = datos.warnings || [];

        // Desglose ausencias
        const desgloseAusencias = datos.desglose_ausencias || {
            dias_ausencias_pagadas: diasAusenciasPagadas,
            dias_ausencias_no_pagadas: diasAusenciasNoPagadas,
            total_ausencias: diasAusenciasPagadas + diasAusenciasNoPagadas
        };

        return {
            // Identificacion
            codigo: code,
            nombre: line.name || resumen.tipo_provision || '',
            tipoProvision: tipoProvision,
            baseLegal: baseLegal,
            explicacion: explicacion,

            // Metodo
            metodo: metodo,
            metodoLabel: metodoLabel,

            // Componentes del salario
            salarioBase: salarioBase,
            salarioPeriodo: salarioPeriodo,
            salarioMensualReferencia: salarioMensualReferencia,
            salarioAjuste: salarioAjuste,
            variableTotal: variableTotal,
            variableMensual: variableMensual,
            auxilioTransporte: auxilioTransporte,
            auxilioMensual: auxilioMensual,
            baseTotal: baseTotal,

            // Dias
            diasPeriodo: diasPeriodo,
            diasPagados: diasPagados,
            diasAusenciasPagadas: diasAusenciasPagadas,
            diasAusenciasNoPagadas: diasAusenciasNoPagadas,
            diasComputables: diasComputables,
            salarioDias: salarioDias,
            auxilioDias: auxilioDias,

            // Tasa y calculo
            tasa: tasa,
            periodoBase: periodoBase,
            provisionCalculada: provisionCalculada,
            saldoAnterior: saldoAnterior,
            provisionAcumulada: provisionAcumulada,
            ajuste: ajuste,
            totalReconocidoVigencia: totalReconocidoVigencia,

            // Auxilio transporte
            aplicaAuxilio: aplicaAuxilio,
            auxilioModalidad: auxilioModalidad,
            configAuxilio: configAuxilio,

            // Cambios de salario
            huboCambioSalario: huboCambioSalario,
            franjasSalario: franjasSalario,

            // Conceptos incluidos
            conceptosIncluidos: conceptosIncluidos,

            // Pasos de formula
            formulaPasos: formulaPasos,

            // Indicadores
            indicadores: indicadores,

            // Comparativa
            valorAnterior: valorAnterior,
            diferenciaPeriodoAnterior: diferenciaPeriodoAnterior,

            // Ausencias
            desgloseAusencias: desgloseAusencias,

            // Fechas
            fechaInicio: fechaInicio,
            fechaCorte: fechaCorte,

            // Config global
            configGlobal: configGlobal,

            // Warnings
            warnings: warnings,

            // Flags
            esLiquidacion: datos.es_liquidacion || false,
            esConsolidacion: datos.es_consolidacion || false
        };
    }

    // ==================== CONFIGURACION DE REGLA ====================

    get ruleConfig() {
        const code = (this.line.code || '').toUpperCase();
        const config = getRuleConfig(code);
        
        // Si se encontró configuración, retornarla
        if (config) {
            return config;
        }

        // Default segun tipo
        if (this.isDevengo) {
            return {
                icon: 'fa-plus-circle',
                color: '#22C55E',
                gradient: 'linear-gradient(135deg, #DCFCE7 0%, #BBF7D0 100%)',
                borderColor: '#86EFAC',
                name: 'Devengo',
                baseLegal: ''
            };
        }
        return {
            icon: 'fa-minus-circle',
            color: '#EF4444',
            gradient: 'linear-gradient(135deg, #FEE2E2 0%, #FECACA 100%)',
            borderColor: '#FCA5A5',
            name: 'Deduccion',
            baseLegal: ''
        };
    }

    // ==================== TIPO SIMPLE: KPIs ====================

    get simpleKpis() {
        const kpis = [];
        const line = this.line;
        const comp = this.computation || {};

        // KPI 1: Base (salario/monto)
        if (line.amount && line.amount !== line.total) {
            kpis.push({
                etiqueta: comp.kpis?.[0]?.etiqueta || 'Base',
                valor: line.amount,
                formato: 'currency',
                subtitulo: comp.kpis?.[0]?.subtitulo || ''
            });
        }

        // KPI 2: Cantidad/Dias
        if (line.quantity && line.quantity !== 1) {
            kpis.push({
                etiqueta: comp.kpis?.[1]?.etiqueta || 'Cantidad',
                valor: line.quantity,
                formato: 'decimal',
                subtitulo: comp.kpis?.[1]?.subtitulo || 'dias/unidades'
            });
        }

        // KPI 3: Tasa
        if (line.rate && line.rate !== 100) {
            kpis.push({
                etiqueta: comp.kpis?.[2]?.etiqueta || 'Tasa',
                valor: line.rate,
                formato: 'percent',
                subtitulo: comp.kpis?.[2]?.subtitulo || 'aplicada'
            });
        }

        // Si no hay KPIs, crear uno con el total
        if (kpis.length === 0) {
            kpis.push({
                etiqueta: 'Valor',
                valor: line.total,
                formato: 'currency',
                subtitulo: 'total'
            });
        }

        return kpis;
    }

    get simpleFormula() {
        if (this.computation && this.computation.formula) {
            return this.computation.formula;
        }
        // Generar formula basica
        const parts = [];
        if (this.line.amount) parts.push(this.formatCurrency(this.line.amount));
        if (this.line.quantity && this.line.quantity !== 1) parts.push(`x ${this.line.quantity}`);
        if (this.line.rate && this.line.rate !== 100) parts.push(`x ${this.line.rate}%`);
        if (parts.length > 0) {
            parts.push(`= ${this.formatCurrency(this.line.total)}`);
            return parts.join(' ');
        }
        return null;
    }

    // ==================== TIPO MULTI_PASO: Datos para componente ====================

    /**
     * multipasoData - Datos unificados para PayslipLineMultiPaso
     * Estructura: { pasos: [], indicadores: [], warnings: [], total: {} }
     */
    get multipasoData() {
        const comp = this.computation || {};
        const datos = comp.datos || comp;

        // Obtener pasos del computation
        let pasos = [];
        if (comp.pasos && comp.pasos.length > 0) {
            // Soportar ambos formatos:
            // - IBD: {label, value, format, base_legal, highlight}
            // - Otros: {titulo, valor, formato, descripcion, formula}
            // El template espera: paso, concepto, formulaTexto, resultado, items, esFinal
            pasos = comp.pasos.map((paso, idx) => ({
                // numero y paso (ambos para compatibilidad)
                numero: paso.numero || idx + 1,
                paso: paso.numero || idx + 1,
                // titulo y concepto (ambos para compatibilidad)
                titulo: paso.titulo || paso.label || paso.descripcion || paso.concepto || `Paso ${idx + 1}`,
                concepto: paso.titulo || paso.label || paso.descripcion || paso.concepto || `Paso ${idx + 1}`,
                // etiqueta corta para timeline
                etiquetaCorta: paso.etiquetaCorta || (paso.label || paso.titulo || '').substring(0, 15),
                // descripcion
                descripcion: paso.descripcion || paso.titulo || paso.label || '',
                // formula y formulaTexto (ambos para compatibilidad)
                formula: paso.formula || paso.formula_texto || '',
                formulaTexto: paso.formula || paso.formula_texto || '',
                // Soportar value (IBD) o resultado/valor
                resultado: paso.resultado !== undefined ? paso.resultado : (paso.value !== undefined ? paso.value : paso.valor),
                // Soportar format (IBD) o formato
                formato: paso.formato || paso.format || 'currency',
                // detalle y items (ambos para compatibilidad)
                detalle: paso.detalle || paso.items || [],
                items: paso.detalle || paso.items || [],
                // es_subtotal, esFinal, highlight
                es_subtotal: paso.es_subtotal || paso.tipo === 'resultado' || paso.highlight || false,
                esFinal: paso.es_subtotal || paso.tipo === 'resultado' || paso.highlight || false,
                base_legal: paso.base_legal || ''
            }));
        } else if (comp.explicacion_legal && comp.explicacion_legal.pasos) {
            pasos = comp.explicacion_legal.pasos.map((paso, idx) => ({
                numero: idx + 1,
                paso: idx + 1,
                titulo: paso.titulo || paso.descripcion || `Paso ${idx + 1}`,
                concepto: paso.titulo || paso.descripcion || `Paso ${idx + 1}`,
                etiquetaCorta: (paso.titulo || paso.descripcion || '').substring(0, 15),
                descripcion: paso.descripcion || '',
                formula: paso.formula || '',
                formulaTexto: paso.formula || '',
                resultado: paso.resultado || paso.valor || 0,
                formato: paso.formato || 'currency',
                detalle: paso.detalle || [],
                items: paso.detalle || [],
                es_subtotal: paso.es_resultado || false,
                esFinal: paso.es_resultado || false,
                base_legal: paso.base_legal || ''
            }));
        } else if (comp.formula_pasos && comp.formula_pasos.length > 0) {
            pasos = comp.formula_pasos.map((fp, idx) => ({
                numero: fp.paso || idx + 1,
                paso: fp.paso || idx + 1,
                titulo: fp.concepto || fp.label || `Paso ${idx + 1}`,
                concepto: fp.concepto || fp.label || `Paso ${idx + 1}`,
                etiquetaCorta: (fp.concepto || fp.label || '').substring(0, 15),
                descripcion: fp.formula_texto || '',
                formula: fp.formula_texto || '',
                formulaTexto: fp.formula_texto || '',
                resultado: fp.resultado !== undefined ? fp.resultado : fp.valor,
                formato: fp.formato || 'currency',
                detalle: [],
                items: [],
                es_subtotal: fp.tipo === 'resultado',
                esFinal: fp.tipo === 'resultado',
                base_legal: fp.base_legal || ''
            }));
        }

        // Indicadores - transformar a formato esperado por template
        // Template espera: {texto, icono, color}
        // IBD tiene: {label, value, color, formato}
        const indicadoresRaw = comp.indicadores || datos.indicadores || [];
        const indicadores = indicadoresRaw.map(ind => ({
            texto: ind.texto || (ind.label && ind.value !== undefined ? `${ind.label}: ${ind.value}` : ind.label) || '',
            icono: ind.icono || 'fa-info-circle',
            color: ind.color || 'primary'
        }));

        // Warnings
        const warnings = comp.warnings || datos.warnings || comp.alertas || [];

        // Total
        const total = {
            etiqueta: 'TOTAL',
            valor: this.line.total
        };

        return {
            titulo: comp.titulo || datos.titulo || 'CÁLCULO DETALLADO',
            pasos,
            indicadores,
            warnings,
            total,
            baseLegal: comp.base_legal || datos.base_legal || '',
            explicacion: comp.explicacion || datos.explicacion || ''
        };
    }

    // ==================== TIPO FORMULA: Datos para componente ====================

    /**
     * formulaData - Datos unificados para PayslipLineFormula
     * Estructura: { kpis: [], pasos: [], tablas: [], indicadores: [] }
     */
    get formulaData() {
        const comp = this.computation || {};
        const datos = comp.datos || comp;

        // KPIs de la columna izquierda
        let kpis = [];
        if (comp.columna_izquierda && comp.columna_izquierda.items) {
            kpis = comp.columna_izquierda.items;
        } else {
            // Construir desde datos básicos
            const line = this.line;
            if (line.amount && line.amount !== line.total) {
                kpis.push({ etiqueta: 'Base', valor: line.amount, formato: 'currency' });
            }
            if (line.quantity && line.quantity !== 1) {
                kpis.push({ etiqueta: 'Cantidad', valor: line.quantity, formato: 'decimal' });
            }
            if (line.rate && line.rate !== 100) {
                kpis.push({ etiqueta: 'Tasa', valor: line.rate, formato: 'percent' });
            }
        }

        // Pasos de la columna derecha
        let pasos = [];
        if (comp.columna_derecha && comp.columna_derecha.pasos) {
            pasos = comp.columna_derecha.pasos;
        } else if (comp.pasos && comp.pasos.length > 0) {
            pasos = comp.pasos.map((paso, idx) => ({
                numero: paso.numero || idx + 1,
                descripcion: paso.descripcion || paso.concepto || '',
                resultado: paso.resultado !== undefined ? paso.resultado : paso.valor,
                formato: paso.formato || 'currency',
                es_subtotal: paso.es_subtotal || paso.tipo === 'resultado'
            }));
        } else if (comp.formula_pasos && comp.formula_pasos.length > 0) {
            pasos = comp.formula_pasos.map((fp, idx) => ({
                numero: fp.paso || idx + 1,
                descripcion: fp.concepto || fp.label || '',
                resultado: fp.resultado !== undefined ? fp.resultado : fp.valor,
                formato: fp.formato || 'currency',
                es_subtotal: fp.tipo === 'resultado'
            }));
        }

        // Tablas (rangos, etc.)
        let tablas = [];
        if (comp.tabla_rangos) {
            tablas.push(comp.tabla_rangos);
        }
        if (comp.tablas && Array.isArray(comp.tablas)) {
            tablas = tablas.concat(comp.tablas);
        }

        // Indicadores
        const indicadores = comp.indicadores || datos.indicadores || [];

        // Total
        const total = {
            etiqueta: 'TOTAL',
            valor: this.line.total
        };

        return {
            kpis,
            pasos,
            tablas,
            indicadores,
            total,
            validaciones: comp.columna_izquierda?.validaciones || [],
            baseLegal: comp.base_legal || datos.base_legal || ''
        };
    }

    // ==================== TIPO FORMULA: Columnas ====================

    get formulaInputs() {
        if (!this.computation) return [];

        // Buscar en columna_izquierda
        if (this.computation.columna_izquierda && this.computation.columna_izquierda.items) {
            return this.computation.columna_izquierda.items;
        }

        // Construir desde computation
        const inputs = [];
        const datos = this.computation.datos || this.computation;

        // Campos comunes a mostrar
        const fieldsToShow = ['salary', 'wage', 'smmlv', 'ibc', 'base', 'dias_trabajados', 'effective_days'];
        for (const field of fieldsToShow) {
            if (datos[field] !== undefined && datos[field] !== null) {
                inputs.push({
                    etiqueta: this.translateKey(field),
                    valor: datos[field],
                    formato: typeof datos[field] === 'number' && datos[field] > 1000 ? 'currency' : 'decimal'
                });
            }
        }

        return inputs;
    }

    get formulaValidaciones() {
        if (!this.computation) return [];

        if (this.computation.columna_izquierda && this.computation.columna_izquierda.validaciones) {
            return this.computation.columna_izquierda.validaciones;
        }

        // Extraer indicadores como validaciones
        if (this.computation.indicadores) {
            return this.computation.indicadores.map(ind => ({
                etiqueta: ind.label || ind.etiqueta,
                estado: ind.color === 'success' || ind.color === 'info' ? 'ok' :
                       ind.color === 'warning' ? 'warning' : 'error',
                mensaje: ind.value || ind.valor
            }));
        }

        return [];
    }

    get formulaPasos() {
        if (!this.computation) return this._generarPasosBasicos();

        // Buscar en columna_derecha
        if (this.computation.columna_derecha && this.computation.columna_derecha.pasos) {
            return this.computation.columna_derecha.pasos;
        }

        // Buscar pasos directos
        if (this.computation.pasos && this.computation.pasos.length > 0) {
            return this.computation.pasos;
        }

        // Buscar en formula_pasos
        if (this.computation.formula_pasos) {
            return this.computation.formula_pasos.map((fp, idx) => {
                // Detectar formato segun descripcion del paso (case insensitive)
                const desc = (fp.concepto || fp.label || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
                let formato = fp.formato || 'currency';

                // Si es periodo, dias, cantidad, etc. - no es moneda
                if (desc.includes('periodo') || desc.includes('dias') ||
                    desc.includes('cantidad') || desc.includes('meses') ||
                    desc.includes('semanas') || desc.includes('horas') ||
                    desc.includes('factor') || desc.includes('numero')) {
                    formato = 'integer';
                } else if (desc.includes('tasa') || desc.includes('porcentaje') || desc.includes('%')) {
                    formato = 'percent';
                }

                // Validar que el valor es numerico
                let valor = fp.resultado !== undefined ? fp.resultado : fp.valor;
                if (valor === undefined || valor === null || (typeof valor === 'number' && isNaN(valor))) {
                    valor = 0;
                }

                return {
                    numero: idx + 1,
                    descripcion: fp.concepto || fp.label || '',
                    valor: valor,
                    formato: formato,
                    es_subtotal: fp.tipo === 'resultado'
                };
            });
        }

        return this._generarPasosBasicos();
    }

    get formulaTotal() {
        if (this.computation && this.computation.columna_derecha && this.computation.columna_derecha.total) {
            return this.computation.columna_derecha.total;
        }
        return {
            etiqueta: 'TOTAL',
            valor: this.line.total
        };
    }

    get tablaRangos() {
        if (!this.computation) return null;

        if (this.computation.tabla_rangos) {
            return this.computation.tabla_rangos;
        }

        // Para cotizante 51, construir tabla
        if (this.computation.cotizante_51 || this.computation.variante === 'ibd_cotizante_51') {
            const smmlv = this.computation.smmlv || this.computation.datos?.smmlv || 1423500;
            const diasActuales = this.computation.dias_mes_completo || this.computation.number_of_days || 0;

            return {
                titulo: 'TABLA COTIZANTE 51 (Res. 2388/2016)',
                columnas: ['Rango Dias', 'Semanas', 'Factor', 'IBC'],
                filas: [
                    { rango: '0 dias', valores: ['1', '25%', this.formatCurrency(smmlv * 0.25)], activo: diasActuales === 0 },
                    { rango: '1-7 dias', valores: ['1', '25%', this.formatCurrency(smmlv * 0.25)], activo: diasActuales >= 1 && diasActuales <= 7 },
                    { rango: '8-14 dias', valores: ['2', '50%', this.formatCurrency(smmlv * 0.50)], activo: diasActuales >= 8 && diasActuales <= 14 },
                    { rango: '15-21 dias', valores: ['3', '75%', this.formatCurrency(smmlv * 0.75)], activo: diasActuales >= 15 && diasActuales <= 21 },
                    { rango: '22-30 dias', valores: ['4', '100%', this.formatCurrency(smmlv)], activo: diasActuales >= 22 },
                ]
            };
        }

        // Tablas para reglas de Seguridad Social
        const code = (this.line.code || '').toUpperCase();

        // SSOCIAL003 - FSP (Fondo Solidaridad Pensional)
        if (code === 'SSOCIAL003' || code.startsWith('FSP')) {
            const smmlv = this.computation?.smmlv || this.computation?.datos?.smmlv || 1423500;
            const ibc = this.computation?.ibc || this.line.amount || 0;
            const ibcEnSmmlv = ibc / smmlv;

            return {
                titulo: 'FSP - Ley 797/2003 Art. 7',
                nota: 'Aplica si IBC > 4 SMMLV',
                columnas: ['Rango IBC', 'Aplica FSP', '%'],
                filas: [
                    { rango: '< 4 SMMLV', valores: ['No aplica', '0%'], activo: ibcEnSmmlv < 4 },
                    { rango: '>= 4 SMMLV', valores: ['Si aplica', '0.5%'], activo: ibcEnSmmlv >= 4 },
                ],
                condicion: {
                    titulo: 'Validacion IBC',
                    valor: ibcEnSmmlv >= 4,
                    mensaje: ibcEnSmmlv >= 4
                        ? `IBC (${ibcEnSmmlv.toFixed(2)} SMMLV) >= 4 SMMLV -> Aplica FSP`
                        : `IBC (${ibcEnSmmlv.toFixed(2)} SMMLV) < 4 SMMLV -> No aplica`
                }
            };
        }

        // SSOCIAL004 - Fondo de Subsistencia
        if (code === 'SSOCIAL004' || code.startsWith('SUBS')) {
            const smmlv = this.computation?.smmlv || this.computation?.datos?.smmlv || 1423500;
            const ibc = this.computation?.ibc || this.line.amount || 0;
            const ibcEnSmmlv = ibc / smmlv;

            // Determinar rango activo
            let rangoActivo = 0;
            if (ibcEnSmmlv >= 20) rangoActivo = 4;
            else if (ibcEnSmmlv >= 19) rangoActivo = 3;
            else if (ibcEnSmmlv >= 17) rangoActivo = 2;
            else if (ibcEnSmmlv >= 16) rangoActivo = 1;

            return {
                titulo: 'SUBSISTENCIA - Ley 797/2003 Art. 8',
                nota: 'Adicional al FSP si IBC > 16 SMMLV',
                columnas: ['Rango IBC', 'Adicional', 'Total FSP+Subs'],
                filas: [
                    { rango: '< 16 SMMLV', valores: ['0%', '0.5%'], activo: rangoActivo === 0 },
                    { rango: '16 - 17 SMMLV', valores: ['0.2%', '0.7%'], activo: rangoActivo === 1 },
                    { rango: '17 - 18 SMMLV', valores: ['0.4%', '0.9%'], activo: rangoActivo === 2 },
                    { rango: '18 - 19 SMMLV', valores: ['0.6%', '1.1%'], activo: rangoActivo === 2 },
                    { rango: '19 - 20 SMMLV', valores: ['0.8%', '1.3%'], activo: rangoActivo === 3 },
                    { rango: '>= 20 SMMLV', valores: ['1.0%', '1.5%'], activo: rangoActivo === 4 },
                ],
                condicion: {
                    titulo: 'Validacion IBC',
                    valor: ibcEnSmmlv >= 16,
                    mensaje: ibcEnSmmlv >= 16
                        ? `IBC (${ibcEnSmmlv.toFixed(2)} SMMLV) >= 16 SMMLV -> Aplica Subsistencia`
                        : `IBC (${ibcEnSmmlv.toFixed(2)} SMMLV) < 16 SMMLV -> No aplica`
                }
            };
        }

        return null;
    }

    // Getter especifico para identificar si es regla de Seguridad Social
    get isSeguridadSocial() {
        const code = (this.line.code || '').toUpperCase();
        return code.startsWith('SSOCIAL') || code.startsWith('EPS') || code.startsWith('AFP') || code.startsWith('FSP');
    }

    // Getter para obtener resumen de seguridad social
    get seguridadSocialResumen() {
        if (!this.isSeguridadSocial) return null;

        const code = (this.line.code || '').toUpperCase();
        const comp = this.computation || {};
        const datos = comp.datos || comp;

        const resumen = {
            tipo: '',
            porcentaje_empleado: 0,
            porcentaje_empresa: 0,
            porcentaje_total: 0,
            base_legal: '',
            entidad: '',
            ibc: datos.ibc || this.line.amount || 0,
            valor_empleado: this.line.total || 0,
            valor_empresa: 0,
            condiciones: []
        };

        if (code === 'SSOCIAL001' || code.includes('SALUD')) {
            resumen.tipo = 'SALUD';
            resumen.porcentaje_empleado = 4.0;
            resumen.porcentaje_empresa = 8.5;
            resumen.porcentaje_total = 12.5;
            resumen.base_legal = 'Ley 100/1993 Art. 204';
            resumen.entidad = datos.eps_name || 'EPS';
            resumen.valor_empresa = resumen.ibc * 0.085;
            resumen.condiciones = [
                'Aplica sobre IBC mensual',
                'No aplica si pensionado cotizante'
            ];
        } else if (code === 'SSOCIAL002' || code.includes('PENSION')) {
            resumen.tipo = 'PENSION';
            resumen.porcentaje_empleado = 4.0;
            resumen.porcentaje_empresa = 12.0;
            resumen.porcentaje_total = 16.0;
            resumen.base_legal = 'Ley 100/1993 Art. 20';
            resumen.entidad = datos.afp_name || 'AFP';
            resumen.valor_empresa = resumen.ibc * 0.12;
            resumen.condiciones = [
                'Aplica sobre IBC mensual',
                'No aplica si pensionado o > 3 SMMLV integral'
            ];
        } else if (code === 'SSOCIAL003' || code.includes('FSP')) {
            resumen.tipo = 'FSP';
            resumen.porcentaje_empleado = 0.5;
            resumen.porcentaje_empresa = 0;
            resumen.porcentaje_total = 0.5;
            resumen.base_legal = 'Ley 797/2003 Art. 7';
            resumen.entidad = 'Fondo Solidaridad';
            resumen.condiciones = [
                'Aplica si IBC > 4 SMMLV',
                'Deduccion adicional a pension'
            ];
        } else if (code === 'SSOCIAL004' || code.includes('SUBS')) {
            const smmlv = datos.smmlv || 1423500;
            const ibcEnSmmlv = resumen.ibc / smmlv;
            let pct = 0;
            if (ibcEnSmmlv >= 20) pct = 1.0;
            else if (ibcEnSmmlv >= 19) pct = 0.8;
            else if (ibcEnSmmlv >= 18) pct = 0.6;
            else if (ibcEnSmmlv >= 17) pct = 0.4;
            else if (ibcEnSmmlv >= 16) pct = 0.2;

            resumen.tipo = 'SUBSISTENCIA';
            resumen.porcentaje_empleado = pct;
            resumen.porcentaje_empresa = 0;
            resumen.porcentaje_total = pct;
            resumen.base_legal = 'Ley 797/2003 Art. 8';
            resumen.entidad = 'Fondo Subsistencia';
            resumen.condiciones = [
                'Aplica si IBC > 16 SMMLV',
                'Escala progresiva 0.2% a 1.0%',
                'Adicional al FSP'
            ];
        }

        return resumen;
    }

    // ==================== IBC/IBD (Ingreso Base de Cotizacion) ====================

    get isIBC() {
        const code = (this.line.code || '').toUpperCase();
        return code === 'IBC' || code.startsWith('IBC_') || code === 'IBD' || code.startsWith('IBD_');
    }

    get ibcResumen() {
        if (!this.isIBC) return null;

        const comp = this.computation || {};
        const datos = comp.datos || comp;
        const smmlv = datos.smmlv || 1423500;

        // Verificar si es cotizante 51 (tiempo parcial)
        const esCotizante51 = datos.cotizante_51 || false;

        // Componentes del IBC desde las reglas usadas
        const componentes = [];

        // Si hay reglas_usadas del backend, usarlas
        const reglasUsadas = datos.reglas_usadas || [];
        if (reglasUsadas.length > 0) {
            for (const regla of reglasUsadas) {
                const esSalarial = regla.category_code === 'DEV_SALARIAL' ||
                                   (regla.category_code || '').includes('SALARIAL');
                componentes.push({
                    concepto: regla.name || regla.code,
                    valor: regla.total || 0,
                    icono: this._getIconForRule(regla.code),
                    color: esSalarial ? '#2563EB' : '#7C3AED',
                    incluido: true,
                    categoria: regla.category_name || regla.category_code
                });
            }
        } else {
            // Fallback: construir desde datos agregados
            if (datos.salary > 0) {
                componentes.push({
                    concepto: 'Ingresos Salariales',
                    valor: datos.salary,
                    icono: 'fa-money',
                    color: '#2563EB',
                    incluido: true,
                    nota: 'Art. 27 Ley 1393/2010'
                });
            }

            if (datos.o_earnings > 0) {
                const top40 = datos.top40 || 0;
                const exceso40 = datos.o_earnings > top40 ? datos.o_earnings - top40 : 0;
                componentes.push({
                    concepto: 'Otros Devengos No Salariales',
                    valor: datos.o_earnings,
                    icono: 'fa-plus-circle',
                    color: '#7C3AED',
                    incluido: exceso40 === 0,
                    nota: exceso40 > 0 ? `Exceso 40%: ${this.formatCurrency(exceso40)} excluido` : 'Dentro del 40%'
                });
            }

            if (datos.paid_absences_ibc_amount > 0) {
                componentes.push({
                    concepto: 'Ausencias Pagadas (IBC)',
                    valor: datos.paid_absences_ibc_amount,
                    icono: 'fa-calendar-minus-o',
                    color: '#0D9488',
                    incluido: true,
                    nota: datos.include_absences_1393 ? 'Incluidas en regla 40%' : 'Fuera de regla 40%'
                });
            }

            if (datos.unpaid_absences_amount > 0) {
                componentes.push({
                    concepto: 'Ausencias No Pagadas',
                    valor: datos.unpaid_absences_amount,
                    icono: 'fa-times-circle',
                    color: '#DC2626',
                    incluido: false,
                    nota: 'LNR, SLN, Permisos'
                });
            }
        }

        // IBC final
        const ibcFinal = datos.ibc_final || this.line.total || 0;
        const ibcPre = datos.ibc_pre || ibcFinal;
        const ibcEnSmmlv = smmlv > 0 ? ibcFinal / smmlv : 0;

        // Validaciones
        const validaciones = [];

        // IBC minimo (1 SMMLV)
        validaciones.push({
            regla: 'IBC Minimo',
            descripcion: 'Minimo 1 SMMLV',
            base_legal: 'Art. 18 Ley 100/1993',
            valor_referencia: smmlv,
            cumple: ibcFinal >= smmlv * 0.99, // 99% para tolerancia redondeo
            mensaje: ibcFinal >= smmlv * 0.99
                ? `IBC (${this.formatCurrency(ibcFinal)}) >= SMMLV`
                : `IBC ajustado al minimo legal`
        });

        // IBC maximo (25 SMMLV)
        const ibcMaximo = smmlv * 25;
        const aplicoLimite25 = ibcPre > ibcMaximo;
        validaciones.push({
            regla: 'IBC Maximo',
            descripcion: 'Maximo 25 SMMLV',
            base_legal: 'Art. 30 Ley 1393/2010',
            valor_referencia: ibcMaximo,
            cumple: !aplicoLimite25,
            mensaje: aplicoLimite25
                ? `IBC topado a 25 SMMLV (${this.formatCurrency(ibcMaximo)})`
                : `IBC dentro del limite (${ibcEnSmmlv.toFixed(2)} SMMLV)`
        });

        // Regla del 40%
        const top40 = datos.top40 || 0;
        const oEarnings = datos.o_earnings || 0;
        if (oEarnings > 0) {
            const aplicoRegla40 = oEarnings > top40;
            validaciones.push({
                regla: 'Regla del 40%',
                descripcion: 'Limite ingresos no salariales',
                base_legal: 'Art. 27 Ley 1393/2010',
                valor_referencia: top40,
                cumple: !aplicoRegla40,
                mensaje: aplicoRegla40
                    ? `Exceso excluido: ${this.formatCurrency(oEarnings - top40)}`
                    : `No salariales (${this.formatCurrency(oEarnings)}) <= 40% (${this.formatCurrency(top40)})`
            });
        }

        // Pasos del calculo desde explicacion_legal
        const pasosCalculo = [];
        const explicacionLegal = datos.explicacion_legal || {};
        const explicaciones = explicacionLegal.explicaciones_legales || [];
        for (const exp of explicaciones) {
            pasosCalculo.push({
                paso: exp.paso,
                titulo: exp.titulo,
                valor: exp.valor,
                base_legal: exp.base_legal,
                formula: exp.formula || null,
                destacado: exp.paso === 7 // Resultado final
            });
        }

        // Notas
        const notas = [];
        if (esCotizante51) {
            notas.push(`Cotizante 51: ${datos.rango_tabla_51 || 'Tabla especial'}`);
            notas.push(datos.nota_legal || 'Res. 2388/2016');
        } else {
            notas.push('IBC = Base para aportes a Seguridad Social');
            if (datos.include_absences_1393) {
                notas.push('Ausencias incluidas en calculo del 40%');
            }
        }

        // Variacion respecto al mes anterior
        const variacion = {
            valor_anterior: datos.valores_anteriores?.valor_anterior_promedio || 0,
            diferencia: datos.diferencia_periodo_anterior || 0,
            porcentaje: datos.porcentaje_cambio || 0
        };

        return {
            tipo: esCotizante51 ? 'IBC COTIZANTE 51' : 'IBC',
            base_legal: 'Ley 1393/2010',
            componentes: componentes,
            // Totales
            salary: datos.salary || 0,
            o_earnings: oEarnings,
            absences_amount: datos.absences_amount || 0,
            top40: top40,
            // IBC
            ibc_pre: ibcPre,
            ibc_calculado: ibcFinal,
            ibc_en_smmlv: ibcEnSmmlv,
            smmlv: smmlv,
            // Cotizante 51
            cotizante_51: esCotizante51,
            tabla_51: esCotizante51 ? {
                dias: datos.dias_mes_completo || datos.number_of_days || 0,
                semanas: datos.semanas_51 || 0,
                factor: datos.factor_51 || 0,
                rango: datos.rango_tabla_51 || '',
                ibc_tabla: datos.ibc_tabla_mensual || 0
            } : null,
            // Calculo
            pasos_calculo: pasosCalculo,
            validaciones: validaciones,
            variacion: variacion,
            notas: notas,
            // Dias
            effective_days: datos.effective_days || 30,
            day_value: datos.day_value || (ibcFinal / 30)
        };
    }

    _getIconForRule(code) {
        const icons = {
            'BASIC': 'fa-money',
            'SALARIO': 'fa-money',
            'HED': 'fa-clock-o',
            'HEN': 'fa-moon-o',
            'HEDF': 'fa-calendar',
            'HENF': 'fa-calendar-o',
            'HRND': 'fa-clock-o',
            'HRNN': 'fa-moon-o',
            'COMISION': 'fa-handshake-o',
            'BONIF': 'fa-gift',
            'AUX': 'fa-bus',
            'INCAP': 'fa-medkit',
            'VAC': 'fa-plane',
            'LIC': 'fa-calendar-check-o'
        };
        const upperCode = (code || '').toUpperCase();
        for (const [key, icon] of Object.entries(icons)) {
            if (upperCode.includes(key)) return icon;
        }
        return 'fa-circle-o';
    }

    // ==================== RETENCION EN LA FUENTE ====================

    get isRetencion() {
        const code = (this.line.code || '').toUpperCase();
        // Detectar todos los codigos de retencion
        return code.startsWith('RTEFTE') ||
               code.startsWith('RTF') ||
               code.startsWith('RT_MET') ||
               code.startsWith('RET_') ||
               code === 'RET_PRIMA' ||
               code === 'RTF_INDEM' ||
               code.includes('RETENCION');
    }

    get retencionResumen() {
        if (!this.isRetencion) {
            return null;
        }

        const comp = this.computation || {};

        // El backend genera data_kpi con esta estructura:
        // - parametros.valor_uvt
        // - ingresos.total, ingresos.salario, ingresos.devengados
        // - base_gravable.ibr3_final, ibr_uvts, ibr1_antes_deducciones, etc.
        // - beneficios.deducciones, ded_dependientes, ded_prepagada, ded_vivienda, rentas_exentas, renta_exenta_25
        // - retencion.calculada, anterior, definitiva, tarifa_porcentaje, proyectada
        // - aportes.salud, pension, solidaridad, subsistencia, total
        // - pasos_normativos (array de pasos con detalle)

        const parametros = comp.parametros || {};
        const ingresos = comp.ingresos || {};
        const baseGravableData = comp.base_gravable || {};
        const beneficios = comp.beneficios || {};
        const retencionData = comp.retencion || {};
        const aportes = comp.aportes || {};
        const periodo = comp.periodo || {};

        // UVT del backend o default 2024
        const uvt = parametros.valor_uvt || comp.uvt || 47065;

        // Procedimiento usado
        const procedimiento = retencionData.procedimiento || 1;

        // Componentes del calculo - mapeados desde estructura backend
        const ingresoLaboral = ingresos.total || ingresos.salario || this.line.amount || 0;
        const incr = aportes.total || 0; // Ingresos No Constitutivos de Renta
        const subtotal1 = baseGravableData.ibr1_antes_deducciones || baseGravableData.ing_base || (ingresoLaboral - incr);
        const deducciones = beneficios.deducciones || 0;
        const rentasExentas = beneficios.rentas_exentas || 0;
        const rentaExenta25 = beneficios.renta_exenta_25 || 0;
        const beneficiosLimitados = beneficios.beneficios_limitados || baseGravableData.beneficios_limitados || 0;
        const baseGravable = baseGravableData.ibr3_final || comp.base_gravable || (subtotal1 - beneficiosLimitados);
        const baseEnUvt = baseGravableData.ibr_uvts || (baseGravable / uvt);

        // Tabla de rangos segun Art. 383 E.T.
        const rangos = [
            { desde: 0, hasta: 95, tarifa: 0, formula: '0' },
            { desde: 95, hasta: 150, tarifa: 19, formula: '(Base - 95 UVT) x 19%' },
            { desde: 150, hasta: 360, tarifa: 28, formula: '(Base - 150 UVT) x 28% + 10 UVT' },
            { desde: 360, hasta: 640, tarifa: 33, formula: '(Base - 360 UVT) x 33% + 69 UVT' },
            { desde: 640, hasta: 945, tarifa: 35, formula: '(Base - 640 UVT) x 35% + 162 UVT' },
            { desde: 945, hasta: 2300, tarifa: 37, formula: '(Base - 945 UVT) x 37% + 268 UVT' },
            { desde: 2300, hasta: Infinity, tarifa: 39, formula: '(Base - 2300 UVT) x 39% + 770 UVT' },
        ];

        // Determinar rango activo
        let rangoActivo = 0;
        for (let i = 0; i < rangos.length; i++) {
            if (baseEnUvt >= rangos[i].desde && baseEnUvt < rangos[i].hasta) {
                rangoActivo = i;
                break;
            }
        }

        // Retencion calculada
        const retencionCalculada = Math.abs(this.line.total) || retencionData.definitiva || retencionData.calculada || 0;
        const retencionAnterior = retencionData.anterior || 0;
        const esProyectada = retencionData.proyectada || parametros.debe_proyectar || false;
        const tarifaPorcentaje = retencionData.tarifa_porcentaje || rangos[rangoActivo].tarifa;
        const tarifaEfectiva = ingresoLaboral > 0 ? (retencionCalculada / ingresoLaboral * 100) : 0;

        // ═══════════════════════════════════════════════════════════════════
        // LINEAS USADAS DEL BACKEND (detalle completo con codigo/nombre/id)
        // ═══════════════════════════════════════════════════════════════════
        const lineasUsadas = comp.lineas_usadas || {};
        const lineasIngresos = lineasUsadas.ingresos || [];
        const lineasAportes = lineasUsadas.aportes || [];
        const lineasDeducciones = lineasUsadas.deducciones || [];
        const lineasRentasExentas = lineasUsadas.rentas_exentas || [];

        // Parametros de proyeccion
        const diasTrabajados = parametros.dias_trabajados || 30;
        const factorProyeccion = diasTrabajados > 0 && diasTrabajados < 30 ? (30 / diasTrabajados) : 1;

        // ═══════════════════════════════════════════════════════════════════
        // DETALLE DE INGRESOS - Conceptos y reglas usados
        // ═══════════════════════════════════════════════════════════════════
        const detalleIngresos = [];

        // Desde lineas_usadas del backend (detalle completo)
        if (lineasIngresos.length > 0) {
            lineasIngresos.forEach(linea => {
                const esProyectado = linea.category_code === 'PROYECTADO' || linea.code?.startsWith('PROY_');
                detalleIngresos.push({
                    id: linea.id,
                    code: linea.code,
                    concepto: linea.name || linea.code,
                    valor: linea.total || linea.amount || 0,
                    categoria: linea.category_name || linea.category_code || '',
                    icono: this._getIconoCategoria(linea.category_code),
                    esProyectado: esProyectado,
                    factor: esProyectado ? linea.factor : null,
                });
            });
        } else {
            // Fallback: Construir desde totales
            if (ingresos.salario) {
                detalleIngresos.push({ concepto: 'Salario Basico', valor: ingresos.salario, categoria: 'BASIC', icono: 'fa-money' });
            }
            if (ingresos.devengados) {
                detalleIngresos.push({ concepto: 'Devengos Salariales', valor: ingresos.devengados, categoria: 'DEV_SALARIAL', icono: 'fa-plus-circle' });
            }
            if (ingresos.dev_no_salarial) {
                detalleIngresos.push({ concepto: 'Devengos No Salariales', valor: ingresos.dev_no_salarial, categoria: 'DEV_NO_SALARIAL', icono: 'fa-gift' });
            }
            if (ingresos.proyectados) {
                detalleIngresos.push({ concepto: 'Conceptos Proyectados', valor: ingresos.proyectados, categoria: 'PROYECTADO', icono: 'fa-calendar', esProyectado: true });
            }
        }

        // ═══════════════════════════════════════════════════════════════════
        // DETALLE INCR - Aportes obligatorios (desde lineas o totales)
        // ═══════════════════════════════════════════════════════════════════
        const detalleIncr = [];

        if (lineasAportes.length > 0) {
            lineasAportes.forEach(linea => {
                detalleIncr.push({
                    id: linea.id,
                    code: linea.code,
                    concepto: linea.concepto || linea.name || linea.code,
                    valor: Math.abs(linea.total || 0),
                    limite: linea.base_legal || '',
                    icono: this._getIconoAporte(linea.code),
                });
            });
        } else {
            // Fallback desde totales
            if (aportes.salud) {
                detalleIncr.push({ code: 'SSOCIAL001', concepto: 'Aporte Salud Empleado', valor: aportes.salud, limite: 'Art. 56 ET', icono: 'fa-heartbeat' });
            }
            if (aportes.pension) {
                detalleIncr.push({ code: 'SSOCIAL002', concepto: 'Aporte Pension Obligatoria', valor: aportes.pension, limite: 'Art. 55 ET', icono: 'fa-shield' });
            }
            if (aportes.solidaridad) {
                detalleIncr.push({ code: 'SSOCIAL003', concepto: 'Fondo Solidaridad Pensional', valor: aportes.solidaridad, limite: 'Art. 55 ET, Ley 797/2003', icono: 'fa-users' });
            }
            if (aportes.subsistencia) {
                detalleIncr.push({ code: 'SSOCIAL004', concepto: 'Fondo Subsistencia', valor: aportes.subsistencia, limite: 'Art. 55 ET, Ley 797/2003', icono: 'fa-heart' });
            }
        }

        // ═══════════════════════════════════════════════════════════════════
        // DETALLE DEDUCCIONES - Art. 387 (desde lineas o totales)
        // ═══════════════════════════════════════════════════════════════════
        const detalleDeducciones = [];

        if (lineasDeducciones.length > 0) {
            lineasDeducciones.forEach(linea => {
                detalleDeducciones.push({
                    id: linea.id,
                    code: linea.code,
                    concepto: linea.nombre || linea.name || linea.code,
                    valor: linea.valor || linea.total || 0,
                    limite: linea.tope_descripcion || linea.base_legal || '',
                    icono: this._getIconoDeduccion(linea.code),
                    tope_uvt: linea.tope_uvt,
                    tope_pesos: linea.tope_pesos,
                });
            });
        } else {
            // Fallback desde totales
            if (beneficios.ded_dependientes) {
                detalleDeducciones.push({ code: 'DED_DEP', concepto: 'Deduccion por Dependientes', valor: beneficios.ded_dependientes, limite: 'Max 32 UVT (10% ingresos)', icono: 'fa-child' });
            }
            if (beneficios.ded_prepagada) {
                detalleDeducciones.push({ code: 'DED_PREP', concepto: 'Medicina Prepagada', valor: beneficios.ded_prepagada, limite: 'Max 16 UVT mensual', icono: 'fa-medkit' });
            }
            if (beneficios.ded_vivienda) {
                detalleDeducciones.push({ code: 'DED_VIV', concepto: 'Intereses de Vivienda', valor: beneficios.ded_vivienda, limite: 'Max 100 UVT mensual', icono: 'fa-home' });
            }
        }

        // ═══════════════════════════════════════════════════════════════════
        // DETALLE RENTAS EXENTAS - AFC/AVC (desde lineas o totales)
        // ═══════════════════════════════════════════════════════════════════
        const detalleRentas = [];

        if (lineasRentasExentas.length > 0) {
            lineasRentasExentas.forEach(linea => {
                detalleRentas.push({
                    id: linea.id,
                    code: linea.code,
                    concepto: linea.name || linea.tipo || linea.code,
                    valor: linea.total || 0,
                    limite: linea.base_legal || '',
                    icono: linea.tipo === 'AFC' ? 'fa-home' : 'fa-university',
                    fuente: linea.fuente, // 'nomina' o 'contrato'
                });
            });
        } else {
            // Fallback desde totales
            if (rentasExentas > 0) {
                detalleRentas.push({ code: 'AFC_AVC', concepto: 'Aportes AFC/AVC', valor: rentasExentas, limite: 'Max 30% o 3800 UVT anual', icono: 'fa-university' });
            }
        }
        if (rentaExenta25 > 0) {
            detalleRentas.push({ concepto: '25% Renta Exenta', valor: rentaExenta25, limite: 'Max 790 UVT/anual', icono: 'fa-percent' });
        }

        // ═══════════════════════════════════════════════════════════════════
        // INFORMACION DE PROYECCION
        // ═══════════════════════════════════════════════════════════════════
        const infoProyeccion = esProyectada ? {
            activa: true,
            dias_trabajados: diasTrabajados,
            factor: factorProyeccion,
            mensaje: `Proyectado de ${diasTrabajados} dias a 30 dias (factor: ${factorProyeccion.toFixed(4)})`,
        } : null;

        // Flujo de calculo - UNICO (sin duplicacion)
        // Incluye detalle expandible en cada linea con base legal
        const flujo = [
            {
                id: 'ingresos',
                etiqueta: 'Ingresos Laborales Brutos',
                valor: ingresoLaboral,
                icono: 'fa-money',
                uvt: (ingresoLaboral / uvt).toFixed(2),
                tipo: 'ingreso',
                base_legal: 'Art. 103 ET',
                descripcion: 'Rentas de trabajo: salarios, comisiones, prestaciones sociales, viaticos, bonificaciones y compensaciones por servicios personales',
                elemento_ley: 'Se consideran rentas de trabajo las obtenidas por personas naturales por concepto de salarios, comisiones, prestaciones sociales, viaticos, gastos de representacion, honorarios, emolumentos eclesiasticos, compensaciones recibidas por el trabajo asociado cooperativo y, en general, las compensaciones por servicios personales.',
                detalle: detalleIngresos,
                expandible: detalleIngresos.length > 0 || true,
                categorias_incluir: ['BASIC', 'DEV_SALARIAL', 'DEV_NO_SALARIAL', 'COMISIONES', 'HEYREC'],
                categorias_excluir: ['CESANTIAS', 'INT_CESANTIAS'],
            },
            {
                id: 'incr',
                etiqueta: 'INCR - Aportes Obligatorios',
                valor: -incr,
                icono: 'fa-minus-circle',
                resta: true,
                uvt: (incr / uvt).toFixed(2),
                detalle: detalleIncr,
                tipo: 'incr',
                base_legal: 'Art. 55 y 56 ET',
                descripcion: 'Aportes obligatorios a fondos de pensiones y seguridad social en salud',
                elemento_ley: 'Los aportes obligatorios que efectuen los trabajadores a los fondos de pensiones y los aportes al sistema de seguridad social en salud no hacen parte de la base para aplicar la retencion en la fuente.',
                expandible: detalleIncr.length > 0
            },
            {
                id: 'subtotal1',
                etiqueta: 'Subtotal 1 (IBR1)',
                valor: subtotal1,
                icono: 'fa-calculator',
                subtotal: true,
                uvt: (subtotal1 / uvt).toFixed(2),
                tipo: 'subtotal',
                base_legal: '',
                descripcion: 'Ingreso Base de Retencion antes de deducciones = Ingresos - INCR',
                expandible: false
            },
            {
                id: 'deducciones',
                etiqueta: 'Deducciones Tributarias',
                valor: -deducciones,
                icono: 'fa-minus-circle',
                resta: true,
                uvt: (deducciones / uvt).toFixed(2),
                detalle: detalleDeducciones,
                tipo: 'deduccion',
                base_legal: 'Art. 387 ET',
                descripcion: 'Deducciones por dependientes economicos, medicina prepagada e intereses de vivienda',
                elemento_ley: 'Los pagos efectuados por los siguientes conceptos son deducibles de la base de retencion: intereses en prestamos para adquisicion de vivienda, pagos de salud prepagada y dependientes economicos.',
                expandible: detalleDeducciones.length > 0
            },
            {
                id: 'rentas',
                etiqueta: 'Rentas Exentas AFC/AVC',
                valor: -(rentasExentas + rentaExenta25),
                icono: 'fa-minus-circle',
                resta: true,
                uvt: ((rentasExentas + rentaExenta25) / uvt).toFixed(2),
                detalle: detalleRentas,
                tipo: 'renta',
                base_legal: 'Art. 126-1, 126-4 y 206 ET',
                descripcion: 'Aportes voluntarios AFC/AVC (max 30% o 3800 UVT) + 25% renta exenta laboral (max 790 UVT)',
                elemento_ley: 'Los aportes voluntarios a fondos de pensiones y cuentas AFC que realice el trabajador no haran parte de la base para aplicar retencion en la fuente, siempre que sumados no excedan el 30% del ingreso laboral o tributario del ano y hasta 3.800 UVT anuales. El 25% del valor total de los pagos laborales es renta exenta, limitado a 790 UVT anuales.',
                expandible: detalleRentas.length > 0
            },
            {
                id: 'base',
                etiqueta: 'Base Gravable (IBR3)',
                valor: baseGravable,
                icono: 'fa-calculator',
                destacado: true,
                uvt: baseEnUvt.toFixed(2),
                tipo: 'base',
                base_legal: 'Art. 383 ET',
                descripcion: `Ingreso Base de Retencion Final: ${baseEnUvt.toFixed(2)} UVT`,
                expandible: false
            },
        ];

        // Condiciones
        const condiciones = [
            `Procedimiento ${procedimiento} (Art. 38${procedimiento === 1 ? '5' : '6'} ET)`,
            baseEnUvt < 95 ? 'Base gravable < 95 UVT: No aplica retencion' : `Tarifa marginal: ${rangos[rangoActivo].tarifa}%`,
            `Tarifa efectiva: ${tarifaEfectiva.toFixed(2)}%`,
            `UVT ${periodo.year || new Date().getFullYear()}: $${uvt.toLocaleString('es-CO')}`
        ];

        if (esProyectada) {
            condiciones.push('Retencion proyectada (quincenal)');
        }
        if (retencionAnterior > 0) {
            condiciones.push(`Retencion anterior: $${retencionAnterior.toLocaleString('es-CO')}`);
        }

        return {
            tipo: 'RETENCION',
            base_legal: 'Art. 383-387 E.T.',
            procedimiento: procedimiento,
            uvt: uvt,
            // Flujo de calculo
            flujo: flujo,
            base_gravable: baseGravable,
            base_en_uvt: baseEnUvt,
            // Subtotales
            ingresoLaboral: ingresoLaboral,
            incr: incr,
            subtotal1: subtotal1,
            deducciones: deducciones,
            rentasExentas: rentasExentas,
            rentaExenta25: rentaExenta25,
            beneficiosLimitados: beneficiosLimitados,
            // Tabla de rangos
            rangos: rangos.map((r, idx) => ({
                ...r,
                activo: idx === rangoActivo,
                desde_cop: r.desde * uvt,
                hasta_cop: r.hasta === Infinity ? 'En adelante' : r.hasta * uvt
            })),
            rango_aplicado: rangos[rangoActivo],
            // Resultado
            retencion: retencionCalculada,
            retencion_anterior: retencionAnterior,
            tarifa_efectiva: tarifaEfectiva,
            tarifa_porcentaje: tarifaPorcentaje,
            es_proyectada: esProyectada,
            // Proyeccion
            proyeccion: infoProyeccion,
            dias_trabajados: diasTrabajados,
            // Condiciones
            condiciones: condiciones,
            // Pasos normativos del backend
            pasos_normativos: comp.pasos_normativos || []
        };
    }

    // ==================== HELPERS ICONOS RETENCION ====================

    _getIconoCategoria(categoryCode) {
        const iconos = {
            'BASIC': 'fa-money',
            'DEV_SALARIAL': 'fa-plus-circle',
            'DEV_NO_SALARIAL': 'fa-gift',
            'COMISIONES': 'fa-percent',
            'HEYREC': 'fa-clock-o',
            'PROYECTADO': 'fa-calendar',
            'COMPLEMENTARIOS': 'fa-star',
        };
        return iconos[categoryCode] || 'fa-circle-o';
    }

    _getIconoAporte(code) {
        const iconos = {
            'SSOCIAL001': 'fa-heartbeat',
            'SSOCIAL002': 'fa-shield',
            'SSOCIAL003': 'fa-users',
            'SSOCIAL004': 'fa-heart',
        };
        return iconos[code] || 'fa-minus-circle';
    }

    _getIconoDeduccion(code) {
        const iconos = {
            'DED_DEP': 'fa-child',
            'DED_DEPENDIENTES': 'fa-child',
            'DED_PREP': 'fa-medkit',
            'DED_PREPAGADA': 'fa-medkit',
            'DED_VIV': 'fa-home',
            'DED_VIVIENDA': 'fa-home',
        };
        return iconos[code] || 'fa-minus-square';
    }

    // ==================== TIPO MULTI_PASO: Timeline ====================

    get multiPasoTimeline() {
        if (this.computation && this.computation.timeline) {
            return this.computation.timeline;
        }

        // Construir timeline desde pasos
        const pasos = this.multiPasoPasos;
        return {
            pasos_total: pasos.length,
            paso_actual: pasos.length > 0 ? pasos[pasos.length - 1].numero : 0,
            pasos_completados: pasos.map(p => p.numero),
            pasos_destacados: pasos
                .filter(p => p.destacado || p.es_paso_clave || p.es_paso_final)
                .map(p => p.numero),
            clickeable: true
        };
    }

    get multiPasoPasos() {
        if (!this.computation) return [];

        const datos = this.computation.datos || {};
        const uvt = this.computation.parametros?.valor_uvt || 47065;

        // RETENCIONES: Buscar pasos_normativos del backend (estructura completa de retenciones.py)
        if (this.computation.pasos_normativos && Array.isArray(this.computation.pasos_normativos)) {
            return this.computation.pasos_normativos.map((p, idx) => {
                const pasoNumero = p.paso || idx + 1;
                const esUltimo = idx === this.computation.pasos_normativos.length - 1;
                const detalle = p.detalle || {};

                // Construir items detallados segun el paso
                const items = this._getItemsParaPasoRetencion(pasoNumero, p, detalle, uvt);

                // Determinar si tiene alerta (exceso en limite global)
                const tieneAlerta = pasoNumero === 6 && detalle.exceso > 0;

                return {
                    numero: pasoNumero,
                    titulo: p.nombre || `Paso ${pasoNumero}`,
                    base_legal: p.base_legal || detalle.base_legal || '',
                    explicacion: this._getExplicacionPasoRetencion(pasoNumero),
                    formula: this._getFormulaPasoRetencion(pasoNumero, p, detalle, uvt),
                    destacado: pasoNumero === 7 || pasoNumero === 8, // Tabla y resultado final
                    es_paso_clave: pasoNumero === 6, // Limite global es clave
                    es_paso_final: esUltimo,
                    alerta: tieneAlerta,
                    items: items,
                    subtotal: {
                        etiqueta: p.nombre,
                        valor: p.valor || 0,
                        uvt: uvt > 0 ? ((p.valor || 0) / uvt).toFixed(2) : '0'
                    },
                    notas: this._getNotasPasoRetencion(pasoNumero, p, detalle),
                };
            });
        }

        // Buscar pasos estructurados genericos
        if (this.computation.pasos && Array.isArray(this.computation.pasos)) {
            return this.computation.pasos.map((p, idx) => {
                const pasoNumero = idx + 1;
                const esUltimo = idx === this.computation.pasos.length - 1;
                const tituloLower = (p.label || '').toLowerCase();

                // Construir items detallados basados en el tipo de paso
                const items = this._getItemsParaPaso(tituloLower, p, datos);

                // Obtener formula para el paso
                const formula = this._getFormulaParaPaso(tituloLower, p, datos);

                return {
                    numero: pasoNumero,
                    titulo: p.label || p.titulo || `Paso ${pasoNumero}`,
                    base_legal: p.base_legal || '',
                    explicacion: p.explicacion || p.description || this._getExplicacionPaso(p.label || p.titulo, pasoNumero),
                    formula: formula,
                    destacado: p.destacado || p.highlight || false,
                    es_paso_clave: p.es_paso_clave || false,
                    es_paso_final: esUltimo,
                    alerta: p.alerta || false,
                    items: items,
                    subtotal: { etiqueta: p.label || p.titulo, valor: p.value || p.valor || 0 },
                    notas: p.notas || [],
                };
            });
        }

        // Construir desde explicacion_legal (IBD)
        if (this.computation.datos && this.computation.datos.explicacion_legal) {
            const expLegal = this.computation.datos.explicacion_legal;
            if (expLegal.explicaciones_legales) {
                return expLegal.explicaciones_legales.map((exp, idx) => {
                    const pasoNumero = exp.paso || idx + 1;
                    return {
                        numero: pasoNumero,
                        titulo: exp.titulo || `Paso ${idx + 1}`,
                        base_legal: exp.base_legal || '',
                        destacado: pasoNumero === 7,
                        es_paso_final: pasoNumero === 7,
                        items: [{
                            etiqueta: exp.termino_legal || exp.explicacion || '',
                            valor: exp.valor,
                            formato: 'currency'
                        }],
                        subtotal: { etiqueta: exp.titulo, valor: exp.valor },
                        notas: exp.formula ? [exp.formula] : [],
                    };
                });
            }
        }

        return [];
    }

    // Helpers para pasos de retencion
    _getItemsParaPasoRetencion(pasoNumero, paso, detalle, uvt) {
        const items = [];
        const formatCurrency = (v) => `$${(v || 0).toLocaleString('es-CO', {minimumFractionDigits: 0, maximumFractionDigits: 0})}`;

        switch (pasoNumero) {
            case 1: // Ingresos Brutos
                if (detalle.salario) items.push({ etiqueta: 'Salario Base', valor: detalle.salario, uvt: (detalle.salario / uvt).toFixed(2), icono: 'fa-money' });
                if (detalle.devengados) items.push({ etiqueta: 'Otros Devengados', valor: detalle.devengados, uvt: (detalle.devengados / uvt).toFixed(2), icono: 'fa-plus' });
                if (detalle.total) items.push({ etiqueta: 'Total Ingresos', valor: detalle.total, uvt: (detalle.total / uvt).toFixed(2), icono: 'fa-calculator', destacado: true });
                // Lineas detalle
                if (detalle.lineas_detalle && detalle.lineas_detalle.length > 0) {
                    detalle.lineas_detalle.forEach(linea => {
                        items.push({
                            etiqueta: linea.name || linea.code,
                            valor: linea.total,
                            uvt: (linea.total / uvt).toFixed(2),
                            icono: 'fa-file-text-o',
                            esDetalle: true
                        });
                    });
                }
                break;

            case 2: // INCR
                if (detalle.salud) items.push({ etiqueta: 'Aporte Salud', valor: detalle.salud, uvt: (detalle.salud / uvt).toFixed(2), icono: 'fa-heartbeat' });
                if (detalle.pension) items.push({ etiqueta: 'Aporte Pension', valor: detalle.pension, uvt: (detalle.pension / uvt).toFixed(2), icono: 'fa-shield' });
                if (detalle.solidaridad) items.push({ etiqueta: 'Fondo Solidaridad', valor: detalle.solidaridad, uvt: (detalle.solidaridad / uvt).toFixed(2), icono: 'fa-users' });
                if (detalle.subsistencia) items.push({ etiqueta: 'Fondo Subsistencia', valor: detalle.subsistencia, uvt: (detalle.subsistencia / uvt).toFixed(2), icono: 'fa-hand-o-up' });
                if (detalle.total) items.push({ etiqueta: 'Total INCR', valor: detalle.total, uvt: (detalle.total / uvt).toFixed(2), icono: 'fa-minus-circle', destacado: true, resta: true });
                if (paso.subtotal_1) items.push({ etiqueta: 'Subtotal 1', valor: paso.subtotal_1, uvt: (paso.subtotal_1 / uvt).toFixed(2), icono: 'fa-calculator', esSubtotal: true });
                break;

            case 3: // Deducciones
                if (detalle.dependientes) items.push({ etiqueta: 'Dependientes (10%)', valor: detalle.dependientes, uvt: (detalle.dependientes / uvt).toFixed(2), icono: 'fa-child', limite: 'Max 32 UVT' });
                if (detalle.prepagada) items.push({ etiqueta: 'Medicina Prepagada', valor: detalle.prepagada, uvt: (detalle.prepagada / uvt).toFixed(2), icono: 'fa-medkit', limite: 'Max 16 UVT' });
                if (detalle.vivienda) items.push({ etiqueta: 'Intereses Vivienda', valor: detalle.vivienda, uvt: (detalle.vivienda / uvt).toFixed(2), icono: 'fa-home', limite: 'Max 100 UVT' });
                if (detalle.total) items.push({ etiqueta: 'Total Deducciones', valor: detalle.total, uvt: (detalle.total / uvt).toFixed(2), icono: 'fa-minus-circle', destacado: true, resta: true });
                break;

            case 4: // Rentas Exentas AFC/AVC
                if (detalle.afc_reportado) items.push({ etiqueta: 'AFC', valor: detalle.afc_reportado, uvt: (detalle.afc_reportado / uvt).toFixed(2), icono: 'fa-home' });
                if (detalle.avc_reportado) items.push({ etiqueta: 'AVC', valor: detalle.avc_reportado, uvt: (detalle.avc_reportado / uvt).toFixed(2), icono: 'fa-university' });
                if (detalle.limite_30_pct) items.push({ etiqueta: 'Limite 30%', valor: detalle.limite_30_pct, uvt: (detalle.limite_30_pct / uvt).toFixed(2), icono: 'fa-percent', esLimite: true });
                if (detalle.total_aceptado) items.push({ etiqueta: 'Total Aceptado', valor: detalle.total_aceptado, uvt: (detalle.total_aceptado / uvt).toFixed(2), icono: 'fa-check-circle', destacado: true });
                break;

            case 5: // Renta Exenta 25%
                if (detalle.base_calculo) items.push({ etiqueta: 'Base Calculo (Subtotal 2)', valor: detalle.base_calculo, uvt: (detalle.base_calculo / uvt).toFixed(2), icono: 'fa-calculator' });
                if (detalle.valor_calculado) items.push({ etiqueta: 'Calculo 25%', valor: detalle.valor_calculado, uvt: (detalle.valor_calculado / uvt).toFixed(2), icono: 'fa-percent' });
                if (detalle.tope_pesos) items.push({ etiqueta: `Tope ${detalle.tope_uvt || 65.83} UVT`, valor: detalle.tope_pesos, uvt: detalle.tope_uvt || 65.83, icono: 'fa-ban', esLimite: true });
                if (detalle.valor_aplicado) items.push({ etiqueta: 'Valor Aplicado', valor: detalle.valor_aplicado, uvt: (detalle.valor_aplicado / uvt).toFixed(2), icono: 'fa-check-circle', destacado: true });
                break;

            case 6: // Limite Global 40%
                if (detalle.total_beneficios_solicitados) items.push({ etiqueta: 'Total Beneficios', valor: detalle.total_beneficios_solicitados, uvt: (detalle.total_beneficios_solicitados / uvt).toFixed(2), icono: 'fa-list' });
                if (detalle.limite_40_pct) items.push({ etiqueta: 'Limite 40%', valor: detalle.limite_40_pct, uvt: (detalle.limite_40_pct / uvt).toFixed(2), icono: 'fa-percent', esLimite: true });
                if (detalle.limite_uvt_mensual_pesos) items.push({ etiqueta: 'Limite UVT (1340/12)', valor: detalle.limite_uvt_mensual_pesos, uvt: '111.67', icono: 'fa-calculator', esLimite: true });
                if (detalle.beneficios_aceptados) items.push({ etiqueta: 'Beneficios Aceptados', valor: detalle.beneficios_aceptados, uvt: (detalle.beneficios_aceptados / uvt).toFixed(2), icono: 'fa-check-circle', destacado: true });
                if (detalle.exceso > 0) items.push({ etiqueta: 'Exceso (No deducible)', valor: detalle.exceso, uvt: (detalle.exceso / uvt).toFixed(2), icono: 'fa-exclamation-triangle', alerta: true });
                break;

            case 7: // Tabla Retencion
                const rangoAplicado = detalle.rango_aplicado;
                if (rangoAplicado) {
                    items.push({ etiqueta: 'Rango Desde', valor: rangoAplicado.desde, formato: 'uvt', icono: 'fa-arrow-down' });
                    items.push({ etiqueta: 'Rango Hasta', valor: rangoAplicado.hasta === Infinity ? 'En adelante' : rangoAplicado.hasta, formato: 'uvt', icono: 'fa-arrow-up' });
                    items.push({ etiqueta: 'Tarifa', valor: rangoAplicado.tarifa, formato: 'percent', icono: 'fa-percent', destacado: true });
                }
                if (detalle.base_uvt) items.push({ etiqueta: 'Base en UVT', valor: detalle.base_uvt, formato: 'uvt', icono: 'fa-calculator' });
                break;

            case 8: // Retencion Definitiva
                if (paso.retencion_calculada) items.push({ etiqueta: 'Retencion Calculada', valor: paso.retencion_calculada, uvt: (paso.retencion_calculada / uvt).toFixed(2), icono: 'fa-calculator' });
                if (paso.retencion_anterior) items.push({ etiqueta: 'Retencion Anterior', valor: paso.retencion_anterior, uvt: (paso.retencion_anterior / uvt).toFixed(2), icono: 'fa-history', resta: true });
                if (paso.diferencia) items.push({ etiqueta: 'Diferencia', valor: paso.diferencia, uvt: (paso.diferencia / uvt).toFixed(2), icono: 'fa-arrows-v' });
                items.push({ etiqueta: 'Retencion Definitiva', valor: paso.valor || 0, uvt: ((paso.valor || 0) / uvt).toFixed(2), icono: 'fa-check-circle', destacado: true, esFinal: true });
                if (paso.proyectada) items.push({ etiqueta: 'Proyeccion Quincenal', valor: 'Si', formato: 'text', icono: 'fa-calendar', esNota: true });
                break;
        }

        return items;
    }

    _getExplicacionPasoRetencion(pasoNumero) {
        const explicaciones = {
            1: 'Suma de todos los ingresos laborales del periodo (salario, comisiones, horas extras, bonificaciones). Excluye cesantias, intereses de cesantias y prima.',
            2: 'Aportes obligatorios a seguridad social que no constituyen renta: salud (4%), pension (4%), solidaridad y subsistencia.',
            3: 'Deducciones tributarias permitidas: dependientes (10% hasta 32 UVT), medicina prepagada (hasta 16 UVT), intereses vivienda (hasta 100 UVT).',
            4: 'Aportes voluntarios a AFC (Ahorro Fomento Construccion) y AVC (Aportes Voluntarios Pension). Limite conjunto: 30% o 3800 UVT/anual.',
            5: 'Renta exenta del 25% sobre el subtotal despues de deducciones. Tope: 790 UVT anuales (65.83 UVT/mes).',
            6: 'Limite global: La suma de deducciones y rentas exentas no puede superar el 40% del subtotal 1, ni 1340 UVT anuales.',
            7: 'Aplicacion de la tabla de retencion Art. 383 ET segun rangos de UVT. Formula: (Base - Resta) x Tarifa% + Suma.',
            8: 'Retencion final: Se resta la retencion de la quincena anterior (si aplica) para evitar doble retencion.'
        };
        return explicaciones[pasoNumero] || '';
    }

    _getFormulaPasoRetencion(pasoNumero, paso, detalle, uvt) {
        const formatNum = (n) => (n || 0).toLocaleString('es-CO', {maximumFractionDigits: 0});

        switch (pasoNumero) {
            case 1:
                return `Salario + Devengados = ${formatNum(detalle.total || paso.valor)}`;
            case 2:
                return `Ingresos - INCR = Subtotal 1 = ${formatNum(paso.subtotal_1 || 0)}`;
            case 3:
                return `Dependientes + Prepagada + Vivienda = ${formatNum(detalle.total || paso.valor)}`;
            case 4:
                return `min(AFC + AVC, 30%, 3800 UVT) = ${formatNum(detalle.total_aceptado || paso.valor)}`;
            case 5:
                return `min(Subtotal2 x 25%, 790 UVT) = ${formatNum(detalle.valor_aplicado || paso.valor)}`;
            case 6:
                return `min(Beneficios, 40%, 1340 UVT) = ${formatNum(detalle.beneficios_aceptados || paso.valor)}`;
            case 7:
                const rango = detalle.rango_aplicado || {};
                if (rango.tarifa > 0) {
                    return `((${formatNum(detalle.base_uvt)} - ${rango.resta_uvt}) x ${rango.tarifa}% + ${rango.suma_uvt}) x UVT`;
                }
                return 'Base < 95 UVT: No aplica retencion';
            case 8:
                if (paso.retencion_anterior > 0) {
                    return `${formatNum(paso.retencion_calculada)} - ${formatNum(paso.retencion_anterior)} = ${formatNum(paso.valor)}`;
                }
                return `Retencion: ${formatNum(paso.valor)}`;
            default:
                return '';
        }
    }

    _getNotasPasoRetencion(pasoNumero, paso, detalle) {
        const notas = [];

        switch (pasoNumero) {
            case 1:
                notas.push('Art. 103 ET - Definicion rentas de trabajo');
                if (detalle.lineas_proyectadas?.length > 0) {
                    notas.push(`Incluye ${detalle.lineas_proyectadas.length} conceptos proyectados`);
                }
                break;
            case 2:
                notas.push('Art. 55 y 56 ET - INCR');
                break;
            case 3:
                notas.push('Art. 387 ET - Deducciones');
                if (detalle.detalle?.length > 0) {
                    detalle.detalle.forEach(d => {
                        if (d.valor_aplicado !== d.valor_calculado) {
                            notas.push(`${d.concepto}: Limitado por tope UVT`);
                        }
                    });
                }
                break;
            case 4:
                notas.push('Art. 126-1 y 126-4 ET - AFC/AVC');
                break;
            case 5:
                notas.push('Art. 206 Num. 10 ET - Renta Exenta 25%');
                break;
            case 6:
                notas.push('Art. 336 ET (Ley 2277/2022) - Limite Global');
                if (detalle.exceso > 0) {
                    notas.push(`Exceso de ${(detalle.exceso / (detalle.beneficios_aceptados + detalle.exceso) * 100).toFixed(1)}% no deducible`);
                }
                break;
            case 7:
                notas.push('Art. 383 ET - Tabla de Retencion');
                notas.push(detalle.formula || '');
                break;
            case 8:
                notas.push('Art. 385 ET - Procedimiento 1');
                if (paso.proyectada) {
                    notas.push('Retencion proyectada a 30 dias y dividida en 2 quincenas');
                }
                if (paso.payslip_line_anterior) {
                    notas.push(`Nomina anterior: ${paso.payslip_line_anterior.numero || 'N/A'}`);
                }
                break;
        }

        return notas;
    }

    get comparativaAnterior() {
        if (!this.computation) return null;

        if (this.computation.comparativa_anterior) {
            return this.computation.comparativa_anterior;
        }

        // Construir desde datos
        const datos = this.computation.datos || this.computation;
        if (datos.valores_anteriores && datos.diferencia_periodo_anterior !== undefined) {
            return {
                mostrar: true,
                valor_anterior: datos.valores_anteriores.valor_anterior_promedio || datos.valores_anteriores.valor_anterior || 0,
                valor_actual: datos.ibc_final || this.line.total,
                diferencia: datos.diferencia_periodo_anterior || 0,
                porcentaje: datos.porcentaje_cambio || 0,
                tendencia: (datos.diferencia_periodo_anterior || 0) >= 0 ? 'up' : 'down'
            };
        }

        return null;
    }

    isStepExpanded(stepNumber) {
        return this.state.expandedSteps[stepNumber] === true;
    }

    toggleStep(stepNumber) {
        // Crear nuevo objeto para triggear reactividad OWL
        const newExpanded = Object.assign({}, this.state.expandedSteps);
        newExpanded[stepNumber] = !newExpanded[stepNumber];
        this.state.expandedSteps = newExpanded;
    }

    scrollToStep(stepNumber) {
        this.state.activeTimelineStep = stepNumber;
        // Expandir el paso
        const newExpanded = Object.assign({}, this.state.expandedSteps);
        newExpanded[stepNumber] = true;
        this.state.expandedSteps = newExpanded;
    }

    // ==================== FLUJO RETENCION EXPANDIBLE ====================

    isFlujoItemExpanded(itemId) {
        return this.state.expandedFlujoItems[itemId] === true;
    }

    toggleFlujoItem(itemId) {
        const newExpanded = Object.assign({}, this.state.expandedFlujoItems);
        newExpanded[itemId] = !newExpanded[itemId];
        this.state.expandedFlujoItems = newExpanded;
    }

    // ==================== PROVISION STEPS ====================

    isProvStepExpanded(stepNumber) {
        return this.state.expandedProvSteps[stepNumber] === true;
    }

    toggleProvStep(stepNumber) {
        const newExpanded = Object.assign({}, this.state.expandedProvSteps);
        newExpanded[stepNumber] = !newExpanded[stepNumber];
        this.state.expandedProvSteps = newExpanded;
    }

    scrollToProvStep(stepNumber) {
        this.state.activeTimelineStep = stepNumber;
        const newExpanded = Object.assign({}, this.state.expandedProvSteps);
        newExpanded[stepNumber] = true;
        this.state.expandedProvSteps = newExpanded;
    }

    // ==================== PASOS BASICOS (fallback) ====================

    _generarPasosBasicos() {
        const pasos = [];
        if (this.line.amount) {
            pasos.push({ numero: 1, descripcion: 'Monto Base', valor: this.line.amount, formato: 'currency' });
        }
        if (this.line.quantity && this.line.quantity !== 1) {
            pasos.push({ numero: 2, descripcion: 'Cantidad / Dias', valor: this.line.quantity, formato: 'decimal' });
        }
        if (this.line.rate && this.line.rate !== 100) {
            pasos.push({ numero: 3, descripcion: 'Tasa', valor: this.line.rate, formato: 'percent' });
        }
        pasos.push({ numero: pasos.length + 1, descripcion: 'TOTAL', valor: this.line.total, formato: 'currency', es_subtotal: true });
        return pasos;
    }

    _getItemsParaPaso(tituloLower, paso, datos) {
        const reglas = datos.reglas_usadas || [];

        // Segun el tipo de paso, filtrar las reglas correspondientes
        if (tituloLower.includes('ingresos salariales') || tituloLower.includes('salario')) {
            // Filtrar reglas salariales (BASIC, DEV_SALARIAL)
            const salariales = reglas.filter(r =>
                r.category_code === 'BASIC' ||
                r.category_code === 'DEV_SALARIAL' ||
                r.category_code === 'BASICO'
            );
            return {
                tipo: 'tabla',
                columnas: ['Tipo', 'Codigo', 'Nombre', 'Valor', 'Base 40%'],
                filas: salariales.map(r => ({
                    tipo: r.category_code === 'BASIC' || r.category_code === 'BASICO' ? 'BAS' : 'SAL',
                    codigo: r.code,
                    nombre: r.name,
                    valor: r.total,
                    base40: 'Si'
                })),
                total: datos.salary || paso.value || 0
            };
        }
        else if (tituloLower.includes('ausencia')) {
            // Usar ausencias_detalle del backend que tiene IBC individual por ausencia
            const ausenciasDetalle = datos.ausencias_detalle || [];

            // Si hay detalle de ausencias del backend, usarlo
            if (ausenciasDetalle.length > 0) {
                return {
                    tipo: 'tabla_ausencias',
                    columnas: ['Tipo', 'Codigo', 'Nombre', 'Pago', 'IBC Usado', 'Base 40%'],
                    filas: ausenciasDetalle.map(a => ({
                        tipo: a.type || 'AUS',
                        codigo: a.code,
                        nombre: a.name,
                        valor: a.payment || 0,
                        ibc_usado: a.ibc_amount || a.payment || 0,
                        base40: datos.include_absences_1393 ? 'Si' : 'No',
                        ibc_source: a.ibc_source || '',
                        days: a.days_payslip || 0,
                    })),
                    total: datos.paid_absences_amount || paso.value || 0,
                    ibc_total: datos.paid_absences_ibc_amount || 0,
                    diferencia: (datos.paid_absences_ibc_amount || 0) - (datos.paid_absences_amount || 0),
                    nota: datos.paid_absences_ibc_amount && datos.paid_absences_ibc_amount !== datos.paid_absences_amount ?
                        `IBC calculado con base del mes anterior (diferente al pago)` : null
                };
            }

            // Fallback: usar reglas_usadas si no hay ausencias_detalle
            const ausencias = reglas.filter(r =>
                r.category_code === 'INCAPACIDAD' ||
                r.category_code === 'AUSENCIAS' ||
                r.category_code?.includes('AUS')
            );
            return {
                tipo: 'tabla_ausencias',
                columnas: ['Tipo', 'Codigo', 'Nombre', 'Pago', 'IBC Usado', 'Base 40%'],
                filas: ausencias.map(r => ({
                    tipo: 'AUS',
                    codigo: r.code,
                    nombre: r.name,
                    valor: r.total,
                    ibc_usado: datos.paid_absences_ibc_amount || r.total,
                    base40: datos.include_absences_1393 ? 'Si' : 'No'
                })),
                total: datos.paid_absences_amount || paso.value || 0,
                ibc_total: datos.paid_absences_ibc_amount || 0,
                nota: datos.paid_absences_ibc_amount ?
                    `IBC Ausencia: ${this.formatCurrency(datos.paid_absences_ibc_amount)} (calculado con IBC mes anterior)` : null
            };
        }
        else if (tituloLower.includes('no salarial')) {
            // Filtrar no salariales
            const noSalariales = reglas.filter(r =>
                r.category_code === 'DEV_NO_SALARIAL' ||
                r.category_code?.includes('NO_SAL')
            );
            return {
                tipo: 'tabla',
                columnas: ['Tipo', 'Codigo', 'Nombre', 'Valor', 'Base 40%'],
                filas: noSalariales.map(r => ({
                    tipo: 'N/S',
                    codigo: r.code,
                    nombre: r.name,
                    valor: r.total,
                    base40: 'Exceso'
                })),
                total: datos.o_earnings || paso.value || 0
            };
        }
        else if (tituloLower.includes('regla') && tituloLower.includes('40')) {
            return {
                tipo: 'calculo',
                lineas: [
                    { etiqueta: 'Base Salarial', valor: datos.salary_for_40 || 0 },
                    { etiqueta: '+ Ingresos No Salariales', valor: datos.o_earnings || 0 },
                    { etiqueta: '= Total Ingresos', valor: (datos.salary_for_40 || 0) + (datos.o_earnings || 0), destacado: true },
                    { etiqueta: 'Tope 40%', valor: datos.top40 || 0 },
                    { etiqueta: 'Exceso No Salarial', valor: Math.max(0, (datos.o_earnings || 0) - (datos.top40 || 0)), alerta: true },
                ],
                total: paso.value || 0
            };
        }
        else if (tituloLower.includes('factor') && tituloLower.includes('salarial')) {
            // Paso de Factor Salarial (70% para salario integral)
            const esSalarioIntegral = datos.es_salario_integral || false;
            const ibcAntesFactor = datos.ibc_antes_factor || 0;
            const ibcDespuesFactor = datos.ibc_antes_limite || (ibcAntesFactor * 0.7);
            const desglose = datos.desglose_factor || {};

            if (!esSalarioIntegral) {
                return {
                    tipo: 'simple',
                    valor: paso.value || ibcAntesFactor,
                    nota: 'No aplica factor 70% (no es salario integral)'
                };
            }

            // Construir lista de reglas desde aplica_70 y aplica_100
            const reglas70 = (desglose.aplica_70 || []).map(r => ({
                codigo: r.code,
                nombre: r.name,
                categoria: r.category_code || 'BASIC',
                montoOriginal: r.monto_original || 0,
                factor: 0.7,
                montoAjustado: r.monto_ajustado || 0,
                esBasic: r.es_basic || false,
            }));

            const reglas100 = (desglose.aplica_100 || []).map(r => ({
                codigo: r.code,
                nombre: r.name,
                categoria: r.category_code || '',
                montoOriginal: r.monto_original || 0,
                factor: 1.0,
                montoAjustado: r.monto_ajustado || 0,
                esBasic: false,
            }));

            // IBC de ausencias (siempre al 100%)
            const ibcAusencias = datos.paid_absences_ibc_amount || 0;

            return {
                tipo: 'tabla_factor',
                reglas70: reglas70,
                reglas100: reglas100,
                ibcAusencias: ibcAusencias,
                resumen: {
                    totalBase70: desglose.total_base_70 || 0,
                    totalBase100: desglose.total_base_100 || 0,
                    totalAjustado70: desglose.total_ajustado_70 || 0,
                    totalAjustado100: desglose.total_ajustado_100 || 0,
                    totalFinal: desglose.total_final || ibcDespuesFactor,
                },
                total: ibcDespuesFactor,
                esSalarioIntegral: true,
                explicacion: 'Categoría BASIC aplica 70%. Comisiones y otros devengos aplican 100%. IBC Ausencias aplica 100%.'
            };
        }
        else if (tituloLower.includes('limite') || tituloLower.includes('verificacion')) {
            const limite25 = datos.limite_25_smmlv || (datos.smmlv || 0) * 25;
            const salario = datos.salary || 0;
            const ibcAusencias = datos.paid_absences_ibc_amount || 0;
            const excesoNoSalarial = Math.max(0, (datos.o_earnings || 0) - (datos.top40 || 0));
            const ibcFinal = datos.ibc_final || 0;
            const desglose = datos.desglose_factor || {};

            // Datos de salario integral
            const esSalarioIntegral = datos.es_salario_integral || false;
            const ibcAntesFactor = datos.ibc_antes_factor || (salario + ibcAusencias + excesoNoSalarial);
            const ibcAntesLimite = datos.ibc_antes_limite || ibcFinal;
            const aplicoLimite = datos.aplico_limite_25 || false;

            const lineas = [];

            // Si es salario integral, mostrar el resumen del desglose
            if (esSalarioIntegral && desglose.total_base_70 > 0) {
                // Mostrar resumen del factor salarial
                lineas.push({
                    etiqueta: 'Conceptos al 70%',
                    valor: desglose.total_ajustado_70 || 0,
                    info: `(Base: ${this.formatCurrency(desglose.total_base_70 || 0)} × 70%)`
                });

                if (desglose.total_base_100 > 0) {
                    lineas.push({
                        etiqueta: '+ Conceptos al 100%',
                        valor: desglose.total_ajustado_100 || 0,
                        info: '(Comisiones, bonificaciones, etc.)'
                    });
                }

                lineas.push({ etiqueta: '', valor: null, separador: true });
                lineas.push({
                    etiqueta: '= Subtotal Devengos Ajustados',
                    valor: desglose.total_final || 0,
                    destacado: true
                });
            } else {
                // Contrato ordinario - mostrar desglose simple
                lineas.push({ etiqueta: 'Ingresos Salariales', valor: salario });
            }

            if (ibcAusencias > 0) {
                lineas.push({ etiqueta: '+ IBC Ausencias', valor: ibcAusencias, info: '(Del mes anterior)' });
            }

            if (excesoNoSalarial > 0) {
                lineas.push({ etiqueta: '+ Exceso No Salarial', valor: excesoNoSalarial, info: '(Regla 40%)' });
            }

            // Subtotal antes del límite
            lineas.push({ etiqueta: '', valor: null, separador: true });
            lineas.push({ etiqueta: '= IBC antes de límite', valor: ibcAntesLimite, destacado: true });

            // Verificación del límite
            lineas.push({ etiqueta: '', valor: null, separador: true });
            lineas.push({
                etiqueta: 'Límite 25 SMMLV',
                valor: limite25,
                info: `(${this.formatCurrency(datos.smmlv || 0)} × 25)`,
                tipo_linea: 'limite'
            });

            if (aplicoLimite) {
                lineas.push({
                    etiqueta: 'Se aplicó límite máximo',
                    valor: null,
                    alerta: true,
                    info: `IBC excedía en ${this.formatCurrency(ibcAntesLimite - limite25)}`
                });
            } else {
                lineas.push({
                    etiqueta: 'Dentro del límite',
                    valor: null,
                    ok: true,
                    info: `Margen: ${this.formatCurrency(limite25 - ibcAntesLimite)}`
                });
            }

            lineas.push({ etiqueta: '', valor: null, separador: true });
            lineas.push({ etiqueta: '= IBC FINAL', valor: ibcFinal, destacado: true, es_final: true });

            return {
                tipo: 'calculo',
                lineas: lineas,
                total: ibcFinal,
                cumple: !aplicoLimite,
                esSalarioIntegral: esSalarioIntegral,
                aplicoLimite: aplicoLimite,
                explicacion: esSalarioIntegral ?
                    'El IBC se calcula aplicando el factor 70% solo a la categoría BASIC. Otros devengos (comisiones, etc.) van al 100%. El límite máximo es 25 SMMLV (Art. 30 Ley 1393/2010).' :
                    'El límite máximo de IBC es 25 SMMLV según Art. 30 Ley 1393/2010.'
            };
        }

        // Fallback: mostrar valor simple
        return {
            tipo: 'simple',
            valor: paso.value || paso.valor || 0
        };
    }

    _getFormulaParaPaso(tituloLower, paso, datos) {
        if (tituloLower.includes('ingresos salariales')) {
            const salary = datos.salary || 0;
            const oEarn = datos.o_earnings || 0;
            if (oEarn > 0) {
                return `Salario (${this.formatCurrency(salary)}) + Otros Devengos (${this.formatCurrency(oEarn)}) = ${this.formatCurrency(salary + oEarn)}`;
            }
            return null;
        }
        if (tituloLower.includes('regla') && tituloLower.includes('40')) {
            const base = datos.salary_for_40 || 0;
            const top40 = datos.top40 || 0;
            return `Tope 40% = ${this.formatCurrency(base)} x 40% = ${this.formatCurrency(top40)}`;
        }
        if (tituloLower.includes('limite')) {
            const smmlv = datos.smmlv || 0;
            return `Limite = SMMLV (${this.formatCurrency(smmlv)}) x 25 = ${this.formatCurrency(smmlv * 25)}`;
        }
        return paso.formula || null;
    }

    _getExplicacionPaso(titulo, numero) {
        // Generar explicaciones automaticas basadas en el titulo del paso
        const tituloLower = (titulo || '').toLowerCase();

        const explicaciones = {
            'ingresos salariales': 'Se suman todos los ingresos que constituyen salario segun el Art. 127 del C.S.T.',
            'regla del 40%': 'Los pagos no salariales no pueden superar el 40% del total devengado (Art. 27 Ley 1393/2010).',
            'limite': 'Se verifica que el IBC no supere los limites legales establecidos (25 SMMLV).',
            'verificacion': 'Se valida el cumplimiento de las condiciones normativas.',
            'ibc': 'Ingreso Base de Cotizacion para aportes a seguridad social.',
            'ausencia': 'Para ausencias remuneradas se usa el IBC del mes anterior o promedio.',
            'no salarial': 'Ingresos que no constituyen salario pero pueden afectar el IBC.',
            'salario': 'Base salarial del empleado para el periodo.',
            'resultado': 'Valor final calculado despues de aplicar todas las reglas.',
        };

        for (const [key, exp] of Object.entries(explicaciones)) {
            if (tituloLower.includes(key)) {
                return exp;
            }
        }

        return null;
    }

    // ==================== REGLAS USADAS ====================

    get reglasUsadas() {
        if (!this.computation) return [];

        let rawReglas = this.computation.reglas_usadas;

        if (!rawReglas && this.computation.datos) {
            rawReglas = this.computation.datos.reglas_usadas;
        }

        if (!rawReglas && this.computation.tabla_conceptos_base) {
            rawReglas = this.computation.tabla_conceptos_base;
        }

        if (!rawReglas || !Array.isArray(rawReglas)) {
            return [];
        }

        // Filtrar reglas con valor cero
        rawReglas = rawReglas.filter(r => (r.total || r.valor || 0) !== 0);

        // Obtener ausencias_detalle para cruzar con IBC
        const datos = this.computation.datos || {};
        const ausenciasDetalle = datos.ausencias_detalle || [];
        const ibcTotal = datos.paid_absences_ibc_amount || 0;

        // Crear mapa de IBC por codigo de ausencia
        const ibcPorCodigo = {};
        for (const aus of ausenciasDetalle) {
            if (aus.code) {
                ibcPorCodigo[aus.code] = aus.ibc_amount || aus.payment || 0;
            }
        }

        return rawReglas.map(r => {
            const code = r.code || r.codigo || '';
            const esAusencia = r.es_ausencia || r.category_code === 'INCAPACIDAD' || r.category_code === 'AUSENCIAS';
            let ibcUsado = null;

            // Si es ausencia, buscar IBC en ausencias_detalle
            if (esAusencia) {
                // Buscar por codigo exacto o parcial
                ibcUsado = ibcPorCodigo[code];
                if (!ibcUsado && ausenciasDetalle.length === 1) {
                    // Si solo hay una ausencia, usar su IBC
                    ibcUsado = ausenciasDetalle[0].ibc_amount || null;
                }
            }

            return {
                rule_id: r.rule_id,
                code: code,
                name: r.name || r.nombre || '',
                category_code: r.category_code || r.categoria || '',
                category_name: r.category_name || '',
                amount: r.amount || 0,
                quantity: r.quantity || 0,
                rate: r.rate || 0,
                total: r.total || r.valor || 0,
                origen: r.origen || r.tipo || '',
                es_ausencia: esAusencia,
                ibc_usado: ibcUsado,
            };
        });
    }

    get hasReglasUsadas() {
        return this.reglasUsadas.length > 0;
    }

    get totalReglasUsadas() {
        return this.reglasUsadas.reduce((sum, r) => sum + (r.total || 0), 0);
    }

    get subtotalDevSalarial() {
        return this.reglasUsadas
            .filter(r => r.category_code === 'DEV_SALARIAL' || r.category_code === 'DEVENGOS' || r.category_code === 'BASIC')
            .reduce((sum, r) => sum + (r.total || 0), 0);
    }

    get subtotalAusencias() {
        return this.reglasUsadas
            .filter(r => r.es_ausencia)
            .reduce((sum, r) => sum + (r.total || 0), 0);
    }

    get subtotalNoSalarial() {
        return this.reglasUsadas
            .filter(r => r.category_code === 'DEV_NO_SALARIAL' || r.category_code?.includes('NO_SAL'))
            .reduce((sum, r) => sum + (r.total || 0), 0);
    }

    get hasAusenciasConIbc() {
        // Hay ausencias con IBC diferente al pago?
        const datos = this.computation?.datos || {};
        const ibcAmount = datos.paid_absences_ibc_amount || 0;
        const pagoAmount = datos.paid_absences_amount || 0;
        return ibcAmount > 0 && ibcAmount !== pagoAmount;
    }

    get totalIbcAusencias() {
        const datos = this.computation?.datos || {};
        return datos.paid_absences_ibc_amount || 0;
    }

    get ibcDiffMessage() {
        const datos = this.computation?.datos || {};
        const ibcAmount = datos.paid_absences_ibc_amount || 0;
        const pagoAmount = datos.paid_absences_amount || 0;
        if (ibcAmount > 0 && ibcAmount !== pagoAmount) {
            const diff = ibcAmount - pagoAmount;
            return `IBC calculado con base del mes anterior. Diferencia: ${this.formatCurrency(diff)} (IBC: ${this.formatCurrency(ibcAmount)} vs Pago: ${this.formatCurrency(pagoAmount)})`;
        }
        return null;
    }

    get ibdComponentes() {
        const datos = this.computation?.datos || {};
        const salario = datos.salary || 0;
        const ibcAusencias = datos.paid_absences_ibc_amount || 0;
        const oEarnings = datos.o_earnings || 0;
        const top40 = datos.top40 || 0;
        const excesoNoSalarial = Math.max(0, oEarnings - top40);

        // Calcular subtotal antes de ajustes
        const subtotalBase = salario + ibcAusencias + excesoNoSalarial;

        // Datos de salario integral y límite
        const esSalarioIntegral = datos.es_salario_integral || false;
        const ibcAntesFactor = datos.ibc_antes_factor || subtotalBase;
        const ibcAntesLimite = datos.ibc_antes_limite || (esSalarioIntegral ? subtotalBase * 0.7 : subtotalBase);
        const limite25Smmlv = datos.limite_25_smmlv || 0;
        const aplicoLimite25 = datos.aplico_limite_25 || false;
        const smmlv = datos.smmlv || 0;

        return {
            salariales: salario,
            ibcAusencias: ibcAusencias,
            excesoNoSalarial: excesoNoSalarial,
            subtotalBase: subtotalBase,
            // Salario integral
            esSalarioIntegral: esSalarioIntegral,
            ibcAntesFactor: ibcAntesFactor,
            factorIntegral: 0.7,
            ibcDespuesFactor: esSalarioIntegral ? ibcAntesFactor * 0.7 : ibcAntesFactor,
            // Límite 25 SMMLV
            ibcAntesLimite: ibcAntesLimite,
            limite25Smmlv: limite25Smmlv,
            aplicoLimite25: aplicoLimite25,
            smmlv: smmlv,
            // Total final
            total: datos.ibc_final || 0
        };
    }

    // URLs de leyes colombianas (importado de helpers)
    getLeyUrl(baseLegal) {
        return getLeyUrl(baseLegal);
    }

    // ==================== FORMATEO (importado de helpers) ====================

    formatValue(value, formato = 'currency') {
        return formatValue(value, formato);
    }

    formatCurrency(value) {
        return formatCurrency(value);
    }

    translateKey(key) {
        return translateKey(key);
    }

    getStepColor(index) {
        return getStepColor(index);
    }

    // ==================== UI ACTIONS ====================

    toggleSection(section) {
        // Crear nuevo objeto para triggear reactividad OWL
        const newSections = Object.assign({}, this.state.sections);
        newSections[section] = !newSections[section];
        this.state.sections = newSections;
    }

    openSalaryRule() {
        const ruleId = this.line.salary_rule_id;
        if (ruleId && ruleId[0]) {
            this.action.doAction({
                type: 'ir.actions.act_window',
                res_model: 'hr.salary.rule',
                res_id: ruleId[0],
                views: [[false, 'form']],
                target: 'current',
            });
        }
    }

    openRule(ruleId) {
        if (ruleId) {
            this.action.doAction({
                type: 'ir.actions.act_window',
                res_model: 'hr.salary.rule',
                res_id: ruleId,
                views: [[false, 'form']],
                target: 'new',
            });
        }
    }
}

registry.category("fields").add("payslip_line_detail", {
    component: PayslipLineDetail,
    supportedTypes: ["text", "char"],
});
