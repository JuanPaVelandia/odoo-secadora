/** @odoo-module **/

/**
 * Procesador de Información Contextual
 * 
 * Genera información contextual para líneas de nómina relacionadas con:
 * - Préstamos (loan_id)
 * - Novedades de contrato (concept_id)
 * - Ausencias (leave_id)
 * - Vacaciones (vacation_leave_id)
 * 
 * Parámetros por categoría:
 * - badges: Configuración de badges por tipo de indicador
 * - kpis: Configuración de KPIs por tipo de relación
 * - labels: Etiquetas traducidas por tipo
 */

/**
 * Configuración de badges por tipo de indicador
 */
export const BADGE_CONFIG = {
    liquidar_con_base: {
        label: 'IBC',
        tooltip: 'Liquidar con IBC mes anterior',
        color: 'success',
        icon: 'fa-calculator'
    },
    base_seguridad_social: {
        label: 'SS',
        tooltip: 'Base Seguridad Social',
        color: 'info',
        icon: 'fa-shield'
    },
    base_prima: {
        label: 'PRI',
        tooltip: 'Base Prima',
        color: 'warning',
        icon: 'fa-gift'
    },
    base_cesantias: {
        label: 'CES',
        tooltip: 'Base Cesantias',
        color: 'primary',
        icon: 'fa-bank'
    },
    base_vacaciones: {
        label: 'VAC',
        tooltip: 'Base Vacaciones',
        color: 'info',
        icon: 'fa-sun-o'
    }
};

/**
 * Configuración de etiquetas por tipo de novedad
 */
export const CONCEPT_LABELS = {
    type_deduction: {
        'P': 'Prestamo Empresa',
        'A': 'Ahorro',
        'S': 'Seguro',
        'L': 'Libranza',
        'E': 'Embargo',
        'R': 'Retencion',
        'O': 'Otros'
    },
    aplicar: {
        '15': '1ra Quincena',
        '30': '2da Quincena',
        '0': 'Ambas Quincenas'
    },
    modality_value: {
        'fijo': 'Valor Fijo',
        'diario': 'Valor Diario',
        'diario_efectivo': 'Diario Efectivo'
    }
};

/**
 * Configuración de etiquetas por tipo de préstamo
 */
export const LOAN_TYPE_LABELS = {
    'advance': 'Anticipo',
    'loan': 'Prestamo',
    'advance_prima': 'Anticipo Prima',
    'advance_cesantias': 'Anticipo Cesantias'
};

/**
 * Genera información contextual para una línea de nómina
 * @param {Object} line - Línea de nómina
 * @param {Object} computation - Datos de computation
 * @param {Function} formatCurrency - Función para formatear moneda
 * @param {Function} formatDate - Función para formatear fechas
 * @returns {Object} Información contextual estructurada
 */
export function processContextualInfo(line, computation = {}, formatCurrency, formatDate) {
    const comp = computation || {};

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

    // Generar badges según indicadores
    if (result.liquidar_con_base) {
        result.badges.push(BADGE_CONFIG.liquidar_con_base);
    }
    if (result.base_seguridad_social) {
        result.badges.push(BADGE_CONFIG.base_seguridad_social);
    }
    if (result.base_prima) {
        result.badges.push(BADGE_CONFIG.base_prima);
    }
    if (result.base_cesantias) {
        result.badges.push(BADGE_CONFIG.base_cesantias);
    }
    if (result.base_vacaciones) {
        result.badges.push(BADGE_CONFIG.base_vacaciones);
    }

    // === PRESTAMOS ===
    if (line.loan_id) {
        result.has_relation = true;
        result.relation_type = 'loan';

        const loanData = comp.loan_data || comp.prestamo || {};
        const loanName = Array.isArray(line.loan_id) ? line.loan_id[1] : (line.loan_id?.display_name || 'Prestamo');

        result.relation_data = {
            name: loanName,
            loan_type: loanData.loan_type || '',
            loan_type_label: loanData.loan_type_label || (LOAN_TYPE_LABELS[loanData.loan_type] || loanData.loan_type || 'Prestamo'),
            original_amount: loanData.original_amount || 0,
            total_paid: loanData.total_paid || 0,
            remaining_amount: loanData.remaining_amount || 0,
            pending_installments: loanData.pending_installments || 0,
            total_installments: loanData.total_installments || 0,
            cuota_actual: loanData.cuota_actual || 0,
            payment_end_date: loanData.payment_end_date || null,
            porcentaje_pagado: loanData.porcentaje_pagado || 0,
        };

        // KPIs para préstamo
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
                value: formatCurrency ? formatCurrency(loanData.total_paid) : loanData.total_paid,
                format: 'currency',
                icon: 'fa-check',
                color: 'success'
            });
        }
        if (loanData.remaining_amount > 0) {
            result.kpis.push({
                label: 'Pendiente',
                value: formatCurrency ? formatCurrency(loanData.remaining_amount) : loanData.remaining_amount,
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

        result.relation_data = {
            name: conceptName,
            type_deduction: conceptData.type_deduction || '',
            type_deduction_label: CONCEPT_LABELS.type_deduction[conceptData.type_deduction] || conceptData.type_deduction_label || 'Concepto',
            type_emb: conceptData.type_emb || '',
            aplicar: conceptData.aplicar || '',
            aplicar_label: CONCEPT_LABELS.aplicar[conceptData.aplicar] || conceptData.aplicar_label || '',
            modality_value: conceptData.modality_value || 'fijo',
            modality_label: CONCEPT_LABELS.modality_value[conceptData.modality_value] || conceptData.modality_label || '',
            monthly_behavior: conceptData.monthly_behavior || '',
            period: conceptData.period || 'indefinite',
            balance: conceptData.balance || 0,
            total_paid: conceptData.total_paid || 0,
            remaining_installments: conceptData.remaining_installments || 0,
            proyectar_seguridad_social: conceptData.proyectar_seguridad_social || false,
            proyectar_nomina: conceptData.proyectar_nomina || false,
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

        if (result.relation_data.aplicar_label) {
            result.kpis.push({
                label: 'Aplica',
                value: result.relation_data.aplicar_label,
                icon: 'fa-calendar',
                color: 'info'
            });
        }

        if (result.relation_data.period === 'limited' && result.relation_data.balance > 0) {
            result.kpis.push({
                label: 'Saldo',
                value: formatCurrency ? formatCurrency(result.relation_data.balance) : result.relation_data.balance,
                format: 'currency',
                icon: 'fa-balance-scale',
                color: 'warning'
            });
        }

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
        if (result.relation_data.date_to && formatDate) {
            result.notas.push({
                texto: `Hasta: ${formatDate(result.relation_data.date_to)}`,
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
        if (result.relation_data.vacation_departure_date && formatDate) {
            result.notas.push({
                texto: `Salida: ${formatDate(result.relation_data.vacation_departure_date)}`,
                icon: 'fa-sign-out',
                color: 'info'
            });
        }
        if (result.relation_data.vacation_return_date && formatDate) {
            result.notas.push({
                texto: `Regreso: ${formatDate(result.relation_data.vacation_return_date)}`,
                icon: 'fa-sign-in',
                color: 'success'
            });
        }

    // === LINEAS SIN RELACION ===
    } else {
        result.has_relation = false;

        // KPIs básicos según categoría
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

/**
 * Formatea una fecha a formato colombiano
 * @param {string} dateStr - Fecha en formato string
 * @returns {string} Fecha formateada
 */
export function formatDate(dateStr) {
    if (!dateStr) return '';
    try {
        const date = new Date(dateStr);
        return date.toLocaleDateString('es-CO', { day: '2-digit', month: '2-digit', year: 'numeric' });
    } catch (e) {
        return dateStr;
    }
}
