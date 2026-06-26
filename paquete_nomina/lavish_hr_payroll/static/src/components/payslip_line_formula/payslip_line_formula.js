/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { LottieIcon } from "@lavish_hr_payroll/lib/lottie/lottie_icon";
import { RuleTemplateRegistry, RuleDataProcessors } from "./rule_templates/rule_template_registry";
import {
    SMMLV_2025,
    UVT_2025,
    AUXILIO_TRANSPORTE_2025,
    TOPE_25_SMMLV,
    TOPE_4_FSP,
    TOPE_2_SMMLV,
    TIPOS_ENTIDAD,
    RANGOS_FSP,
    TABLA_RETENCION_383,
    PORCENTAJES_SS,
    COLORES_APORTES,
    REGLAS_IBD,
    REGLAS_RETENCION,
    REGLAS_PRESTACIONES,
    REGLAS_HORAS_EXTRAS,
    REGLAS_AUXILIOS,
    getRangoFSP,
    getRangoRetencion,
    getTipoEntidad,
    getColoresAporte,
    getRegla,
    getReglasByTipo,
    getFactorHoraExtra,
    toUVT,
    fromUVT,
    toSMMLV,
} from "./pila_catalog";

export class PayslipLineFormula extends Component {
    static template = "lavish_hr_payroll.PayslipLineFormula";
    static components = { LottieIcon };

    static props = {
        record: Object,
        readonly: { type: Boolean, optional: true },
        id: { type: String, optional: true },
        name: { type: String, optional: true },
        value: { optional: true },
        "*": true,
    };

    // Diccionario de traducciones inglés -> español
    static translations = {
        // Campos comunes
        'has_changes': 'Tiene Cambios',
        'wage': 'Salario',
        'days': 'Días',
        'rate': 'Tasa',
        'total': 'Total',
        'amount': 'Monto',
        'quantity': 'Cantidad',
        'salary': 'Salario',
        'salary_type': 'Tipo Salario',
        'basic': 'Básico',
        'base': 'Base',
        'base_mensual': 'Base Mensual',
        'base_diaria': 'Base Diaria',
        'effective_days': 'Días Efectivos',
        'days_worked': 'Días Trabajados',
        'worked_days': 'Días Trabajados',
        'period_days': 'Días del Período',
        // IBD / IBC
        'ibc': 'IBC',
        'ibd': 'IBD',
        'ibc_final': 'IBC Final',
        'ibd_final': 'IBD Final',
        'o_earnings': 'Otros Devengos',
        'other_earnings': 'Otros Devengos',
        'absences': 'Ausencias',
        'absences_amount': 'Monto Ausencias',
        'top40': 'Tope 40 SMMLV',
        'smmlv': 'SMMLV',
        // Provisiones
        'prima': 'Prima',
        'cesantias': 'Cesantías',
        'int_cesantias': 'Int. Cesantías',
        'vacaciones': 'Vacaciones',
        'dias_computables': 'Días Computables',
        'factor': 'Factor',
        'provision': 'Provisión',
        // Seguridad Social
        'eps': 'EPS',
        'pension': 'Pensión',
        'arl': 'ARL',
        'salud': 'Salud',
        'fsp': 'Fondo Solidaridad',
        // Retención
        'uvt': 'Valor UVT',
        'valor_uvt': 'Valor UVT',
        'base_gravable': 'Base Gravable',
        'base_uvt': 'Base en UVT',
        'rango': 'Rango',
        'tarifa': 'Tarifa',
        'tarifa_porcentaje': 'Tarifa %',
        'retencion': 'Retención',
        'impuesto': 'Impuesto',
        'calculada': 'Calculada',
        'anterior': 'Anterior',
        'definitiva': 'Definitiva',
        'proyectada': 'Proyectada',
        'ing_base': 'Ing Base',
        'ibr1_antes_deducciones': 'IBR1 Antes Deducciones',
        'ibr2_antes_renta_exenta': 'IBR2 Antes Renta Exenta',
        'ibr3_final': 'IBR3 Final',
        'ibr_uvts': 'IBR UVTs',
        'deducciones': 'Deducciones',
        'rentas_exentas': 'Rentas Exentas',
        'renta_exenta_25': 'Renta Exenta 25%',
        'total_beneficios': 'Total Beneficios',
        'limite_40': 'Límite 40%',
        'limite_uvt': 'Límite UVT',
        'beneficios_limitados': 'Beneficios Limitados',
        'ded_dependientes': 'Ded. Dependientes',
        'ded_prepagada': 'Ded. Prepagada',
        'ded_vivienda': 'Ded. Vivienda',
        // Secciones
        'periodo': 'Período',
        'ingresos': 'Ingresos',
        'aportes': 'Aportes',
        'base_gravable_section': 'Base Gravable',
        'beneficios': 'Beneficios',
        'retencion_section': 'Retención',
        'parametros': 'Parámetros',
        'lineas_detalle': 'Líneas Detalle',
        'pasos_normativos': 'Pasos Normativos',
        // Aportes
        'solidaridad': 'Solidaridad',
        'subsistencia': 'Subsistencia',
        'total_pension': 'Total Pensión',
        'devengados': 'Devengados',
        // Otros
        'dias_trabajados': 'Días Trabajados',
        'debe_proyectar': 'Debe Proyectar',
        'base_legal': 'Base Legal',
        'elemento_ley': 'Elemento Ley',
        'detalle_componentes': 'Detalle Componentes',
        'year': 'Año',
        'month': 'Mes',
        'desde': 'Desde',
        'hasta': 'Hasta',
        // Préstamos
        'loan': 'Préstamo',
        'cuota': 'Cuota',
        'saldo': 'Saldo',
        'balance': 'Saldo',
        'installment': 'Cuota',
        'paid': 'Pagado',
        'pending': 'Pendiente',
        // Otros
        'entity': 'Entidad',
        'code': 'Código',
        'name': 'Nombre',
        'date': 'Fecha',
        'date_from': 'Desde',
        'date_to': 'Hasta',
        'state': 'Estado',
        'percentage': 'Porcentaje',
        'value': 'Valor',
        'result': 'Resultado',
        'description': 'Descripción',
        'concept': 'Concepto',
        'category': 'Categoría',
        'sequence': 'Secuencia',
        'number': 'Número',
        'reference': 'Referencia',
        // Días
        'holidays': 'Festivos',
        'weekends': 'Fines de Semana',
        'saturdays': 'Sábados',
        'sundays': 'Domingos',
        'leave_days': 'Días Ausencia',
        'work_days': 'Días Laborables',
        // Boolean
        'true': 'Sí',
        'false': 'No',
        'yes': 'Sí',
        'no': 'No',
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            loading: true,
            showDetails: true,
            showDetailLines: false,
            computation: null,
            formulaData: null,
            // Datos del empleado
            employee: null,
            // Datos de la nómina
            payslip: null,
            // Totales
            totalDevengos: 0,
            totalDeducciones: 0,
            neto: 0,
            // Días trabajados con detalles
            workedDays: [],
            periodDays: {
                total: 30,
                worked: 0,
                holidays: 0,
                saturdays: 0,
                sundays: 0,
                absences: 0,
            },
            // Calendario visual de días
            calendarDays: [],
            // Ausencias detalladas
            absenceList: [],
            // Novedades y conceptos (con detalles completos)
            novelties: [],
            contractConcepts: [],
            // Préstamos
            loans: [],
            loanDetails: null,
            // Otras líneas
            allLines: [],
            devengosLines: [],
            deduccionesLines: [],
            // Línea IBD
            ibdLine: null,
            // Línea Retención
            retentionLine: null,
            // Líneas de provisiones
            provisionLines: [],
            // Líneas de detalle del cómputo (otras nóminas, períodos anteriores)
            detailLines: [],
            // Agrupaciones
            groupedByCategory: {},
            groupedByRule: {},
            // Secciones expandidas del computation
            expandedComputationSections: {},
            // Secciones expandidas para templates
            expandedSections: {},
        });

        onWillStart(async () => {
            await this.loadAllData();
            await this.loadLoanDetails();
            this.state.loading = false;
        });
    }

    async loadAllData() {
        await this.loadComputationData();
        await this.loadPayslipData();
        await this.loadWorkedDays();
        await this.loadAllLines();
        await this.loadDetailLines();
        await this.loadEntityPILACode();
        this.calculateFormula();
        this.calculatePeriodDays();
        this.groupLines();
    }

    async loadComputationData() {
        const computation = this.props.record.data.computation;
        if (computation) {
            try {
                this.state.computation = JSON.parse(computation);
            } catch (e) {
                console.error("Error parsing computation JSON:", e);
                this.state.computation = {};
            }
        } else {
            this.state.computation = {};
        }
    }

    async loadPayslipData() {
        const line = this.line;
        if (!line.slip_id) return;

        try {
            const slipId = line.slip_id[0];
            const payslips = await this.orm.searchRead(
                'hr.payslip',
                [['id', '=', slipId]],
                ['name', 'number', 'state', 'date_from', 'date_to', 'employee_id', 'contract_id',
                 'struct_id', 'period_id', 'company_id']
            );

            if (payslips.length > 0) {
                this.state.payslip = payslips[0];

                // Cargar datos del empleado
                if (payslips[0].employee_id) {
                    const employees = await this.orm.searchRead(
                        'hr.employee',
                        [['id', '=', payslips[0].employee_id[0]]],
                        ['name', 'identification_id', 'job_id', 'department_id', 'work_email',
                         'mobile_phone', 'company_id', 'image_128', 'sabado']
                    );
                    if (employees.length > 0) {
                        this.state.employee = employees[0];
                    }
                }
            }
        } catch (error) {
            console.error("Error loading payslip data:", error);
        }
    }

    async loadWorkedDays() {
        const line = this.line;
        if (!line.slip_id) return;

        try {
            const slipId = line.slip_id[0];
            const workedDays = await this.orm.searchRead(
                'hr.payslip.worked_days',
                [['payslip_id', '=', slipId]],
                ['name', 'code', 'number_of_days', 'number_of_hours', 'amount', 'work_entry_type_id']
            );
            this.state.workedDays = workedDays;
        } catch (error) {
            console.error("Error loading worked days:", error);
        }
    }

    calculatePeriodDays() {
        // Calcular días del período basado en fechas de la nómina
        if (!this.state.payslip) return;

        // Parsear fechas correctamente (evitar problemas de zona horaria)
        const parseLocalDate = (dateStr) => {
            if (!dateStr) return null;
            const parts = dateStr.split('-');
            return new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
        };

        const dateFrom = parseLocalDate(this.state.payslip.date_from);
        const dateTo = parseLocalDate(this.state.payslip.date_to);
        const dayNames = ['D', 'L', 'M', 'M', 'J', 'V', 'S'];

        if (!dateFrom || !dateTo) return;

        // Obtener festivos colombianos del año
        const year = dateFrom.getFullYear();
        const holidays = this.getColombianHolidays(year);
        // Formatear fechas sin problemas de zona horaria
        const formatLocalDate = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
        const holidaySet = new Set(holidays.map(d => formatLocalDate(d)));

        let saturdays = 0;
        let sundays = 0;
        let holidayCount = 0;
        let realDays = 0;
        let workDays = 0;
        const calendarDays = [];

        // Crear calendario visual con días reales
        let current = new Date(dateFrom);
        while (current <= dateTo) {
            realDays++;
            const dayOfWeek = current.getDay();
            const dayNum = current.getDate();
            const dateStr = `${current.getFullYear()}-${String(current.getMonth() + 1).padStart(2, '0')}-${String(current.getDate()).padStart(2, '0')}`;

            let type = 'work'; // Verde - día laboral
            let color = '#22C55E'; // Verde del nuevo esquema

            // Verificar si es festivo
            const employeeWorksSaturday = this.state.employee?.sabado || false;

            if (holidaySet.has(dateStr)) {
                holidayCount++;
                type = 'holiday';
                color = '#EF4444'; // Rojo para festivos
            } else if (dayOfWeek === 0) {
                sundays++;
                type = 'sunday';
                color = '#F97316'; // Naranja
            } else if (dayOfWeek === 6) {
                saturdays++;
                if (employeeWorksSaturday) {
                    // Empleado trabaja sábados - contar como día laboral
                    type = 'saturday_work';
                    color = '#22C55E'; // Verde (día laboral)
                    workDays++;
                } else {
                    type = 'saturday';
                    color = '#2563EB'; // Azul (fin de semana)
                }
            } else {
                workDays++; // Solo contar días laborales reales (L-V no festivos)
            }

            calendarDays.push({
                date: dateStr,
                day: dayNum,
                dayName: dayNames[dayOfWeek],
                type: type,
                color: color,
                isVirtual: false,
            });

            current.setDate(current.getDate() + 1);
        }

        // Agregar días virtuales si el mes tiene menos de 30 días (Colombia usa 30 días/mes)
        let virtualDays = 0;
        if (realDays < 30) {
            virtualDays = 30 - realDays;
            for (let i = 1; i <= virtualDays; i++) {
                const virtualDayNum = realDays + i;
                calendarDays.push({
                    date: `virtual-${virtualDayNum}`,
                    day: virtualDayNum,
                    dayName: 'V', // V de Virtual
                    type: 'virtual',
                    color: '#9CA3AF', // Gris
                    isVirtual: true,
                });
            }
        }

        // Buscar días trabajados desde worked_days
        const workedEntry = this.state.workedDays.find(w =>
            w.code === 'WORK100' || w.code === 'DIAS_TRAB' || w.code === 'WORKED'
        );
        const worked = workedEntry ? workedEntry.number_of_days : 30;

        // Obtener lista de ausencias desde worked_days
        const absenceList = this.state.workedDays
            .filter(w => !['WORK100', 'DIAS_TRAB', 'WORKED', 'FESTIVOS', 'HOLIDAYS', 'HOLIDAY'].includes(w.code) && w.number_of_days > 0)
            .map(w => ({
                code: w.code,
                name: w.name,
                days: w.number_of_days,
                hours: w.number_of_hours,
            }));

        const absenceDays = absenceList.reduce((sum, a) => sum + (a.days || 0), 0);

        this.state.calendarDays = calendarDays;
        this.state.absenceList = absenceList;
        this.state.periodDays = {
            total: 30, // Siempre 30 para Colombia
            realDays: realDays,
            virtualDays: virtualDays,
            worked: worked,
            workDays: workDays, // Días laborales reales del calendario (L-V no festivos)
            holidays: holidayCount,
            saturdays: saturdays,
            sundays: sundays,
            absences: absenceDays,
        };
    }

    // Obtener festivos colombianos para un año dado
    getColombianHolidays(year) {
        const holidays = [];

        // Festivos fijos
        holidays.push(new Date(year, 0, 1));   // Año Nuevo
        holidays.push(new Date(year, 4, 1));   // Día del Trabajo
        holidays.push(new Date(year, 6, 20));  // Independencia
        holidays.push(new Date(year, 7, 7));   // Batalla de Boyacá
        holidays.push(new Date(year, 11, 8));  // Inmaculada Concepción
        holidays.push(new Date(year, 11, 25)); // Navidad

        // Festivos trasladables (Ley Emiliani) - se mueven al lunes siguiente
        const emilianiDates = [
            { month: 0, day: 6 },   // Reyes Magos
            { month: 2, day: 19 },  // San José
            { month: 5, day: 29 },  // San Pedro y San Pablo
            { month: 7, day: 15 },  // Asunción de la Virgen
            { month: 9, day: 12 },  // Día de la Raza
            { month: 10, day: 1 },  // Todos los Santos
            { month: 10, day: 11 }, // Independencia de Cartagena
        ];

        emilianiDates.forEach(({ month, day }) => {
            let date = new Date(year, month, day);
            const dayOfWeek = date.getDay();
            if (dayOfWeek !== 1) { // Si no es lunes, mover al próximo lunes
                const daysToAdd = dayOfWeek === 0 ? 1 : (8 - dayOfWeek);
                date.setDate(date.getDate() + daysToAdd);
            }
            holidays.push(date);
        });

        // Semana Santa (basada en Pascua)
        const easter = this.getEasterDate(year);

        // Jueves Santo (3 días antes de Pascua)
        const holyThursday = new Date(easter);
        holyThursday.setDate(holyThursday.getDate() - 3);
        holidays.push(holyThursday);

        // Viernes Santo (2 días antes de Pascua)
        const goodFriday = new Date(easter);
        goodFriday.setDate(goodFriday.getDate() - 2);
        holidays.push(goodFriday);

        // Ascensión (39 días después de Pascua, trasladado a lunes)
        const ascension = new Date(easter);
        ascension.setDate(ascension.getDate() + 39);
        if (ascension.getDay() !== 1) {
            const daysToAdd = ascension.getDay() === 0 ? 1 : (8 - ascension.getDay());
            ascension.setDate(ascension.getDate() + daysToAdd);
        }
        holidays.push(ascension);

        // Corpus Christi (60 días después de Pascua, trasladado a lunes)
        const corpusChristi = new Date(easter);
        corpusChristi.setDate(corpusChristi.getDate() + 60);
        if (corpusChristi.getDay() !== 1) {
            const daysToAdd = corpusChristi.getDay() === 0 ? 1 : (8 - corpusChristi.getDay());
            corpusChristi.setDate(corpusChristi.getDate() + daysToAdd);
        }
        holidays.push(corpusChristi);

        // Sagrado Corazón (68 días después de Pascua, trasladado a lunes)
        const sacredHeart = new Date(easter);
        sacredHeart.setDate(sacredHeart.getDate() + 68);
        if (sacredHeart.getDay() !== 1) {
            const daysToAdd = sacredHeart.getDay() === 0 ? 1 : (8 - sacredHeart.getDay());
            sacredHeart.setDate(sacredHeart.getDate() + daysToAdd);
        }
        holidays.push(sacredHeart);

        return holidays;
    }

    // Calcular fecha de Pascua usando algoritmo de Gauss
    getEasterDate(year) {
        const a = year % 19;
        const b = Math.floor(year / 100);
        const c = year % 100;
        const d = Math.floor(b / 4);
        const e = b % 4;
        const f = Math.floor((b + 8) / 25);
        const g = Math.floor((b - f + 1) / 3);
        const h = (19 * a + b - d - g + 15) % 30;
        const i = Math.floor(c / 4);
        const k = c % 4;
        const l = (32 + 2 * e + 2 * i - h - k) % 7;
        const m = Math.floor((a + 11 * h + 22 * l) / 451);
        const month = Math.floor((h + l - 7 * m + 114) / 31) - 1;
        const day = ((h + l - 7 * m + 114) % 31) + 1;
        return new Date(year, month, day);
    }

    async loadAllLines() {
        const line = this.line;
        if (!line.slip_id) return;

        try {
            const slipId = line.slip_id[0];
            const allLines = await this.orm.searchRead(
                'hr.payslip.line',
                [['slip_id', '=', slipId]],
                ['name', 'code', 'category_id', 'category_code', 'total', 'amount', 'quantity',
                 'rate', 'dev_or_ded', 'object_type', 'entity_id', 'loan_id', 'leave_id',
                 'concept_id', 'salary_rule_id', 'computation', 'appears_on_payslip'],
                { order: 'sequence' }
            );

            this.state.allLines = allLines;

            // Separar devengos y deducciones (solo los que aparecen en nómina)
            const visibleLines = allLines.filter(l => l.appears_on_payslip);
            this.state.devengosLines = visibleLines.filter(l => l.dev_or_ded === 'devengo');
            this.state.deduccionesLines = visibleLines.filter(l => l.dev_or_ded === 'deduccion');

            // Buscar totales específicos (por código o categoría)
            const totalDevLine = allLines.find(l => l.code === 'TOTALDEV' || l.code === 'TOTAL_DEV' || l.category_code === 'TOTALDEV');
            const totalDedLine = allLines.find(l => l.code === 'TOTALDED' || l.code === 'TOTAL_DED' || l.category_code === 'TOTALDED');
            const netoLine = allLines.find(l => l.code === 'NET' || l.code === 'NETO' || l.category_code === 'NET' || l.category_code === 'NETO');

            this.state.totalDevengos = totalDevLine ? totalDevLine.total :
                this.state.devengosLines.reduce((sum, l) => sum + (l.total || 0), 0);
            this.state.totalDeducciones = totalDedLine ? totalDedLine.total :
                this.state.deduccionesLines.reduce((sum, l) => sum + (l.total || 0), 0);
            this.state.neto = netoLine ? netoLine.total :
                (this.state.totalDevengos + this.state.totalDeducciones);

            // Buscar línea IBD
            this.state.ibdLine = allLines.find(l => l.code === 'IBD' || l.code === 'IBC' || l.code === 'IBC_R');

            // Buscar línea de retención
            this.state.retentionLine = allLines.find(l =>
                l.code === 'RT_MET_01' || l.code === 'RETEFUENTE' || l.code === 'RTEFTE'
            );

            // Buscar líneas de provisiones
            this.state.provisionLines = allLines.filter(l => l.category_code === 'PROV');

            // Buscar línea de cesantías (para calcular intereses)
            this.state.cesantiasLine = allLines.find(l =>
                (l.code && (l.code.includes('CESANTIAS') || l.code.includes('PRV_CES')) && !l.code.includes('ICES'))
            );

            // IMPORTANTE: Las novedades/ausencias solo se muestran en su propia línea,
            // no como lista global en todas las líneas.
            // Para la línea actual, verificar si ES una novedad/ausencia
            this.state.isNovelty = this.line.object_type === 'novelty' ||
                                   this.line.object_type === 'absence' ||
                                   !!this.line.leave_id;
            this.state.isContractConcept = !!this.line.concept_id;
            this.state.isLoan = !!this.line.loan_id;

            // NO mostrar lista global de novedades - cada línea muestra su propia info
            this.state.novelties = [];
            this.state.contractConcepts = [];
            this.state.loans = [];

        } catch (error) {
            console.error("Error loading lines:", error);
        }
    }

    async loadDetailLines() {
        // Buscar IDs de líneas en el computation (line_ids, acum_line_ids, lineas_detalle)
        const comp = this.state.computation || {};
        let lineIds = [];

        // Buscar en diferentes campos posibles
        if (comp.line_ids && Array.isArray(comp.line_ids)) {
            lineIds = lineIds.concat(comp.line_ids);
        }
        if (comp.acum_line_ids && Array.isArray(comp.acum_line_ids)) {
            lineIds = lineIds.concat(comp.acum_line_ids);
        }
        if (comp.lineas_detalle && Array.isArray(comp.lineas_detalle)) {
            lineIds = lineIds.concat(comp.lineas_detalle);
        }

        // Quitar duplicados
        lineIds = [...new Set(lineIds)];

        if (lineIds.length === 0) return;

        try {
            // Cargar las líneas con todos sus datos
            const detailLines = await this.orm.searchRead(
                'hr.payslip.line',
                [['id', 'in', lineIds]],
                ['id', 'name', 'code', 'total', 'amount', 'quantity', 'rate',
                 'salary_rule_id', 'category_id', 'category_code', 'slip_id',
                 'employee_id', 'contract_id', 'dev_or_ded', 'entity_id',
                 'loan_id', 'leave_id', 'concept_id', 'object_type'],
                { order: 'sequence' }
            );

            // Para cada línea, cargar datos adicionales de la nómina (período, fechas)
            for (const line of detailLines) {
                if (line.slip_id) {
                    const payslips = await this.orm.searchRead(
                        'hr.payslip',
                        [['id', '=', line.slip_id[0]]],
                        ['name', 'number', 'date_from', 'date_to', 'period_id', 'struct_id']
                    );
                    if (payslips.length > 0) {
                        line.payslip_info = payslips[0];
                        // Verificar si es de otro período
                        const currentPeriod = this.state.payslip?.period_id?.[0];
                        const linePeriod = payslips[0].period_id?.[0];
                        line.is_other_period = currentPeriod && linePeriod && currentPeriod !== linePeriod;
                    }
                }
            }

            this.state.detailLines = detailLines;
        } catch (error) {
            console.error("Error loading detail lines:", error);
        }
    }

    groupLines() {
        // Agrupar líneas de detalle por categoría
        const byCategory = {};
        const byRule = {};

        for (const line of this.state.detailLines) {
            const catKey = line.category_id ? line.category_id[0] : 'sin_categoria';
            const catName = line.category_id ? line.category_id[1] : 'Sin Categoría';

            if (!byCategory[catKey]) {
                byCategory[catKey] = { name: catName, lines: [] };
            }
            byCategory[catKey].lines.push(line);

            const ruleKey = line.salary_rule_id ? line.salary_rule_id[0] : 'sin_regla';
            const ruleName = line.salary_rule_id ? line.salary_rule_id[1] : 'Sin Regla';

            if (!byRule[ruleKey]) {
                byRule[ruleKey] = { name: ruleName, lines: [] };
            }
            byRule[ruleKey].lines.push(line);
        }

        this.state.groupedByCategory = byCategory;
        this.state.groupedByRule = byRule;
    }

    async loadLoanDetails() {
        const line = this.line;
        if (!line.loan_id) return;

        try {
            const loans = await this.orm.searchRead(
                'hr.employee.deduction.loan',
                [['id', '=', line.loan_id[0]]],
                ['name', 'amount', 'balance_amount', 'paid_amount', 'state', 'category_id',
                 'entity_id', 'installment_ids', 'date_start', 'date_end']
            );

            if (loans.length > 0) {
                const loan = loans[0];
                const installments = await this.orm.searchRead(
                    'hr.employee.deduction.loan.installment',
                    [['loan_id', '=', loan.id]],
                    ['sequence', 'amount', 'date', 'state'],
                    { order: 'sequence' }
                );

                this.state.loanDetails = {
                    ...loan,
                    installments: installments,
                    totalInstallments: installments.length,
                    paidInstallments: installments.filter(i => i.state === 'paid').length,
                    currentInstallment: installments.find(i => i.state === 'pending'),
                    isCompleted: loan.state === 'paid' || loan.balance_amount <= 0,
                    progress: loan.amount > 0 ? ((loan.paid_amount / loan.amount) * 100).toFixed(1) : 0,
                };
            }
        } catch (error) {
            console.error("Error loading loan details:", error);
        }
    }

    /**
     * Carga el codigo PILA de la entidad para lineas de seguridad social.
     * Consulta hr.employee.entities para obtener code_pila_eps, code_pila_ccf, etc.
     */
    async loadEntityPILACode() {
        const line = this.line;
        if (!line.entity_id) {
            this.state.entityPILA = null;
            return;
        }

        try {
            const entities = await this.orm.searchRead(
                'hr.employee.entities',
                [['id', '=', line.entity_id[0]]],
                ['name', 'business_name', 'code_pila_eps', 'code_pila_ccf',
                 'code_pila_regimen', 'code_pila_exterior', 'types_entities', 'partner_id']
            );

            if (entities.length > 0) {
                const entity = entities[0];

                // Determinar el codigo PILA segun el tipo de aporte
                let codigoPILA = null;
                const code = this.line.code || '';

                // Para EPS (salud)
                if (code.includes('SSOCIAL001') || code.toLowerCase().includes('salud')) {
                    codigoPILA = entity.code_pila_eps;
                }
                // Para CCF
                else if (code.toLowerCase().includes('ccf') || code.toLowerCase().includes('caja')) {
                    codigoPILA = entity.code_pila_ccf;
                }
                // Para otros, usar el primero disponible
                else {
                    codigoPILA = entity.code_pila_eps || entity.code_pila_ccf || entity.code_pila_regimen;
                }

                this.state.entityPILA = {
                    id: entity.id,
                    name: entity.business_name || entity.name,
                    codigoPILA: codigoPILA,
                    partner_id: entity.partner_id,
                    allCodes: {
                        eps: entity.code_pila_eps,
                        ccf: entity.code_pila_ccf,
                        regimen: entity.code_pila_regimen,
                        exterior: entity.code_pila_exterior,
                    }
                };
            }
        } catch (error) {
            console.error("Error loading entity PILA code:", error);
            this.state.entityPILA = null;
        }
    }

    get line() {
        return this.props.record.data;
    }

    get currentLine() {
        const lineId = this.line?.id;
        if (!lineId) return this.line;
        const allLines = this.state.allLines || [];
        return allLines.find(l => l.id === lineId) || this.line;
    }

    // Getter para los datos procesados de reglas con templates especificos
    get ruleData() {
        return this.state.ruleData || {};
    }

    // Getter para verificar si hay un template especifico registrado
    get hasSpecificTemplate() {
        const hasTemplate = !!this.state.registeredTemplateName;
        console.log('[TEMPLATE DEBUG] hasSpecificTemplate:', hasTemplate, 'registeredTemplateName:', this.state.registeredTemplateName);
        return hasTemplate;
    }

    // Getter para el nombre del template especifico
    get registeredTemplateName() {
        return this.state.registeredTemplateName || '';
    }

    // Determina si es template IBD
    get isIBDTemplate() {
        return this.state.registeredTemplateName === 'lavish_hr_payroll.RuleTemplate.IBD';
    }

    // Determina si es template de Retencion Proc1
    get isRetencionProc1Template() {
        return this.state.registeredTemplateName === 'lavish_hr_payroll.RuleTemplate.RetencionProc1';
    }

    // Determina si es template de Liquidacion
    get isLiquidacionTemplate() {
        return this.state.registeredTemplateName === 'lavish_hr_payroll.RuleTemplate.Liquidacion';
    }

    // Determina si es template de Provision
    get isProvisionTemplate() {
        return this.state.registeredTemplateName === 'lavish_hr_payroll.RuleTemplate.Provision';
    }

    // Determina si es template de Auxilio de Transporte
    get isAuxilioTransporteTemplate() {
        return this.state.registeredTemplateName === 'lavish_hr_payroll.RuleTemplate.AuxilioTransporte';
    }

    // Determina si es template de Prima
    get isPrimaTemplate() {
        return this.state.registeredTemplateName === 'lavish_hr_payroll.RuleTemplate.Prima';
    }

    // Determina si es template de Cesantias
    get isCesantiasTemplate() {
        return this.state.registeredTemplateName === 'lavish_hr_payroll.RuleTemplate.Cesantias';
    }

    // Determina si es template de Int. Cesantias
    get isIntCesantiasTemplate() {
        return this.state.registeredTemplateName === 'lavish_hr_payroll.RuleTemplate.IntCesantias';
    }

    get isDevengo() {
        return this.line.dev_or_ded === 'devengo';
    }

    get isDeduccion() {
        return this.line.dev_or_ded === 'deduccion';
    }

    get isBasicSalaryLine() {
        const code = (this.line.code || '').toUpperCase();
        const categoryCode = (this.line.category_code || '').toUpperCase();
        const lineType = (this.line.line_type || '').toUpperCase();
        return lineType === 'BASIC' || categoryCode === 'BASIC' ||
            code.includes('BASIC') || code.includes('BASICO');
    }

    get salaryRule() {
        const line = this.currentLine;
        return line.salary_rule_id ? line.salary_rule_id[1] : (line.name || line.code || '');
    }

    get category() {
        const line = this.currentLine;
        return line.category_id ? line.category_id[1] : (line.category_code || '');
    }

    get isRetention() {
        const code = this.line.code || '';
        return code.includes('RT_MET') || code.includes('RTEFTE') || code.includes('RETEFUENTE');
    }

    get isProvision() {
        return (this.line.category_code || '') === 'PROV';
    }

    get isIBD() {
        const code = this.line.code || '';
        return code === 'IBD' || code === 'IBC' || code === 'IBC_R';
    }

    get isSocialSecurity() {
        const code = this.line.code || '';
        return code.includes('SSOCIAL');
    }

    isVacationText(value) {
        const text = (value || '').toString().toUpperCase();
        return text.includes('VAC') || text.includes('VACACION');
    }

    get monthHours() {
        const workedDays = this.state.workedDays || [];
        if (!workedDays.length) return 0;

        const workedEntry = workedDays.find(w =>
            w.code === 'WORK100' || w.code === 'DIAS_TRAB' || w.code === 'WORKED'
        );
        let hours = workedEntry ? workedEntry.number_of_hours : 0;

        if (!hours) {
            hours = workedDays.reduce((sum, w) => sum + (w.number_of_hours || 0), 0);
        }

        if (!hours && this.state.periodDays?.total) {
            hours = this.state.periodDays.total * 8;
        }

        return hours;
    }

    get noveltyKpi() {
        if (!this.state.isNovelty) return null;

        const name = (this.line.leave_id && this.line.leave_id[1]) ? this.line.leave_id[1] : (this.line.name || '');
        const isVacation = this.isVacationText(this.line.code) || this.isVacationText(name);
        const isAbsence = !!this.line.leave_id;

        return {
            label: isVacation ? 'Vacaciones' : isAbsence ? 'Ausencia' : 'Novedad',
            name: name || this.line.code || '',
            quantity: this.line.quantity || 0,
            total: Math.abs(this.line.total || 0),
            icon: isVacation ? 'fa-sun-o' : isAbsence ? 'fa-calendar-times-o' : 'fa-flag',
            color: isVacation ? '#F59E0B' : isAbsence ? '#EF4444' : '#F97316',
            bg: isVacation ? '#FEF3C7' : isAbsence ? '#FEE2E2' : '#FFEDD5',
        };
    }

    /**
     * Obtiene el icono animado Lottie según el tipo de línea
     */
    getAnimatedIcon() {
        const code = (this.line.code || '').toUpperCase();
        const categoryCode = (this.line.category_code || '').toUpperCase();
        const devOrDed = this.line.dev_or_ded || '';

        // Devengos
        if (devOrDed === 'devengo') {
            if (categoryCode === 'BASIC' || code.includes('BASIC')) {
                return { name: 'money', color: '#22C55E' };
            }
            if (categoryCode === 'AUX' || code.includes('AUX')) {
                return { name: 'money', color: '#3B82F6' };
            }
            if (categoryCode === 'HEYREC' || code.includes('HORA') || code.includes('EXTRA')) {
                return { name: 'clock', color: '#F59E0B' };
            }
            if (this.isVacationText(code) || this.isVacationText(this.line.name)) {
                return { name: 'calendar', color: '#F59E0B' };
            }
            return { name: 'money', color: '#22C55E' };
        }

        // Deducciones
        if (devOrDed === 'deduccion') {
            if (this.isSocialSecurity) {
                return { name: 'alert', color: '#EF4444' };
            }
            if (this.isRetention) {
                return { name: 'percent', color: '#8B5CF6' };
            }
            if (code.includes('PRESTAMO') || code.includes('LOAN')) {
                return { name: 'money', color: '#F97316' };
            }
            return { name: 'alert', color: '#EF4444' };
        }

        // Provisiones
        if (this.isProvision) {
            return { name: 'chart', color: '#6366F1' };
        }

        // IBD/IBC
        if (this.isIBD) {
            return { name: 'analytics', color: '#06B6D4' };
        }

        // Por defecto
        return { name: 'info', color: '#6B7280' };
    }

    /**
     * Obtiene los datos de Seguridad Social para KPIs con entidad PILA.
     * Incluye validacion de entidad y codigo PILA.
     */
    get socialSecurityKPI() {
        if (!this.isSocialSecurity) return null;

        const code = this.line.code || '';
        const comp = this.state.computation || {};
        const entity = this.line.entity_id;

        // Configuracion por tipo de aporte
        const SSOCIAL_CONFIG = {
            'SSOCIAL001': {
                tipo: 'salud',
                nombre: 'Aporte Salud',
                icono: 'fa-heartbeat',
                colorGradient: 'from-rose-500 to-pink-600',
                colorBg: '#F43F5E',
                porcentajeEmpleado: 4.0,
                porcentajeEmpleador: 8.5,
                baseLegal: 'Ley 1122/2007',
                animacion: 'animate-heartbeat',
            },
            'SSOCIAL002': {
                tipo: 'pension',
                nombre: 'Aporte Pension',
                icono: 'fa-piggy-bank',
                colorGradient: 'from-blue-500 to-indigo-600',
                colorBg: '#3B82F6',
                porcentajeEmpleado: 4.0,
                porcentajeEmpleador: 12.0,
                baseLegal: 'Ley 797/2003',
                animacion: 'animate-bounce-slow',
            },
            'SSOCIAL003': {
                tipo: 'fsp_solidaridad',
                nombre: 'FSP Solidaridad',
                icono: 'fa-hands-helping',
                colorGradient: 'from-purple-500 to-violet-600',
                colorBg: '#8B5CF6',
                porcentajeEmpleado: 0.5,
                porcentajeEmpleador: 0,
                baseLegal: 'Ley 100/1993 Art. 27',
                animacion: 'animate-float',
                aplicaDesde: 4, // SMMLV
            },
            'SSOCIAL004': {
                tipo: 'fsp_subsistencia',
                nombre: 'FSP Subsistencia',
                icono: 'fa-hand-holding-usd',
                colorGradient: 'from-amber-500 to-orange-600',
                colorBg: '#F59E0B',
                baseLegal: 'Ley 797/2003 Art. 7',
                animacion: 'animate-wave',
                aplicaDesde: 4, // SMMLV
                rangoVariable: true,
            },
            'SSOCIAL_ARL': {
                tipo: 'arl',
                nombre: 'Riesgos Laborales',
                icono: 'fa-hard-hat',
                colorGradient: 'from-emerald-500 to-teal-600',
                colorBg: '#10B981',
                porcentajeEmpleado: 0,
                baseLegal: 'Decreto 1295/1994',
                animacion: 'animate-shake',
            },
        };

        // Buscar configuracion por codigo
        let config = SSOCIAL_CONFIG[code];
        if (!config) {
            // Intentar detectar por prefijo
            if (code.includes('ARL')) {
                config = SSOCIAL_CONFIG['SSOCIAL_ARL'];
            } else {
                config = {
                    tipo: 'otro',
                    nombre: 'Seguridad Social',
                    icono: 'fa-shield',
                    colorGradient: 'from-gray-500 to-gray-600',
                    colorBg: '#6B7280',
                    animacion: '',
                };
            }
        }

        // Datos de entidad PILA - usar datos cargados de BD si disponibles
        const entityPILA = this.state.entityPILA;
        const entidadInfo = {
            tieneEntidad: !!entity,
            nombre: entityPILA?.name || (entity ? entity[1] : null),
            id: entity ? entity[0] : null,
            codigoPILA: entityPILA?.codigoPILA || comp.codigo_pila || comp.entity_code || null,
            tipoEntidad: config.tipo === 'salud' ? 'EPS' :
                         config.tipo === 'pension' ? 'AFP' :
                         config.tipo === 'arl' ? 'ARL' :
                         config.tipo === 'fsp_solidaridad' || config.tipo === 'fsp_subsistencia' ? 'FSP' : 'ENTIDAD',
            allCodes: entityPILA?.allCodes || null,
        };

        // Advertencia si no tiene entidad
        const advertencias = [];
        if (!entidadInfo.tieneEntidad && ['salud', 'pension', 'arl'].includes(config.tipo)) {
            advertencias.push({
                tipo: 'warning',
                mensaje: `Sin ${entidadInfo.tipoEntidad} asignada`,
                icono: 'fa-exclamation-triangle',
            });
        }
        if (!entidadInfo.codigoPILA && entidadInfo.tieneEntidad) {
            advertencias.push({
                tipo: 'info',
                mensaje: 'Sin codigo PILA',
                icono: 'fa-info-circle',
            });
        }

        // Valores calculados - asegurar que no haya NaN
        const ibc = comp.ibc || comp.base || this.line.amount || 0;
        const porcentaje = this.line.rate || config.porcentajeEmpleado || 0;
        const lineTotal = this.line.total || 0;
        const valorAnterior = comp.valor_anterior || null;
        const variacion = valorAnterior && Math.abs(valorAnterior) > 0
            ? ((Math.abs(lineTotal) - Math.abs(valorAnterior)) / Math.abs(valorAnterior) * 100).toFixed(1)
            : null;

        return {
            codigo: code,
            config: config,
            entidad: entidadInfo,
            advertencias: advertencias,
            ibc: ibc,
            porcentaje: porcentaje,
            valor: Math.abs(lineTotal) || 0,
            valorAnterior: valorAnterior,
            variacion: variacion,
            datos: comp,
            // Agregar rangos FSP si aplica
            rangosFSP: RANGOS_FSP,
            rangoActual: getRangoFSP(ibc),
        };
    }

    // ========================================================================
    // GETTERS PARA CATALOGO PILA Y REFERENCIAS LEGALES
    // ========================================================================

    /**
     * Constantes de nomina 2025
     */
    get constantesNomina() {
        return {
            smmlv: SMMLV_2025,
            uvt: UVT_2025,
            auxilioTransporte: AUXILIO_TRANSPORTE_2025,
            tope25Smmlv: TOPE_25_SMMLV,
            tope4Fsp: TOPE_4_FSP,
        };
    }

    /**
     * Obtiene la entidad PILA enriquecida con metadata de tipo
     * Los datos de entidad vienen del sistema (RPC), no de catalogo fijo
     */
    get entidadPILAEnriquecida() {
        const entityPILA = this.state.entityPILA;
        if (!entityPILA) return null;

        // Determinar tipo de entidad basado en el codigo o tipo
        let tipoEntidad = null;
        const codigo = entityPILA.codigoPILA || entityPILA.codigo || '';
        const tipo = entityPILA.tipo || '';

        // Detectar tipo por prefijo del codigo o campo tipo
        if (codigo.startsWith('EPS') || tipo.includes('EPS') || tipo.includes('SALUD')) {
            tipoEntidad = getTipoEntidad('EPS');
        } else if (codigo.startsWith('AFP') || tipo.includes('AFP') || tipo.includes('PENSION')) {
            tipoEntidad = getTipoEntidad('AFP');
        } else if (codigo.startsWith('CCF') || tipo.includes('CCF') || tipo.includes('CAJA')) {
            tipoEntidad = getTipoEntidad('CCF');
        } else if (codigo.startsWith('ARL') || tipo.includes('ARL') || tipo.includes('RIESGO')) {
            tipoEntidad = getTipoEntidad('ARL');
        } else if (tipo) {
            tipoEntidad = getTipoEntidad(tipo);
        }

        return {
            ...entityPILA,
            tipoEntidad: tipoEntidad,
        };
    }

    /**
     * Obtiene la tabla de rangos FSP para mostrar en el template
     */
    get tablaRangosFSP() {
        return RANGOS_FSP;
    }

    /**
     * Obtiene el rango FSP actual basado en el IBC
     */
    get rangoFSPActual() {
        const ibc = this.state.computation?.ibc || this.line.amount || 0;
        const ibcEnSmmlv = toSMMLV(ibc);
        return getRangoFSP(ibcEnSmmlv);
    }

    /**
     * Obtiene la tabla de retencion Art. 383
     */
    get tablaRetencion383() {
        return TABLA_RETENCION_383;
    }

    /**
     * Obtiene el rango de retencion actual
     */
    get rangoRetencionActual() {
        const comp = this.state.computation || {};
        const baseUvt = comp.base_uvt || comp.ibr_uvts || 0;
        return getRangoRetencion(baseUvt);
    }

    /**
     * Obtiene los porcentajes de seguridad social
     */
    get porcentajesSegSocial() {
        return PORCENTAJES_SS;
    }

    /**
     * Obtiene la regla legal aplicable segun el tipo de linea
     */
    get reglaLegalAplicable() {
        const code = this.line.code || '';

        // IBD
        if (this.isIBD) {
            return {
                tipo: 'ibd',
                reglas: REGLAS_IBD,
                principal: REGLAS_IBD.ibd_final,
            };
        }

        // Retencion
        if (this.isRetention) {
            return {
                tipo: 'retencion',
                reglas: REGLAS_RETENCION,
                principal: REGLAS_RETENCION.retencion_final,
            };
        }

        // Provisiones
        if (this.isProvision) {
            if (code.includes('PRIM')) {
                return {
                    tipo: 'prestaciones',
                    reglas: REGLAS_PRESTACIONES,
                    principal: REGLAS_PRESTACIONES.prima_calculo,
                };
            }
            if (code.includes('CES') && !code.includes('ICES')) {
                return {
                    tipo: 'prestaciones',
                    reglas: REGLAS_PRESTACIONES,
                    principal: REGLAS_PRESTACIONES.cesantias_calculo,
                };
            }
            if (code.includes('ICES')) {
                return {
                    tipo: 'prestaciones',
                    reglas: REGLAS_PRESTACIONES,
                    principal: REGLAS_PRESTACIONES.int_cesantias_calculo,
                };
            }
            if (code.includes('VAC')) {
                return {
                    tipo: 'prestaciones',
                    reglas: REGLAS_PRESTACIONES,
                    principal: REGLAS_PRESTACIONES.vacaciones_calculo,
                };
            }
        }

        // Horas extras
        if (code.includes('HE') || code.includes('REC')) {
            const tipoHE = code.includes('HED') ? 'he_diurna' :
                          code.includes('HEN') ? 'he_nocturna' :
                          code.includes('HEDD') ? 'he_diurna_festivo' :
                          code.includes('HEND') ? 'he_nocturna_festivo' :
                          code.includes('RN') ? 'recargo_nocturno' :
                          code.includes('RD') ? 'recargo_dominical' : 'hora_ordinaria';
            return {
                tipo: 'horas_extras',
                reglas: REGLAS_HORAS_EXTRAS,
                principal: REGLAS_HORAS_EXTRAS[tipoHE] || REGLAS_HORAS_EXTRAS.hora_ordinaria,
            };
        }

        // Auxilios
        if (code.includes('AUX')) {
            return {
                tipo: 'auxilios',
                reglas: REGLAS_AUXILIOS,
                principal: REGLAS_AUXILIOS.auxilio_transporte,
            };
        }

        // Seguridad Social
        if (this.isSocialSecurity) {
            return {
                tipo: 'seguridad_social',
                porcentajes: PORCENTAJES_SS,
                principal: code.includes('001') ? { baseLegal: 'Ley 1122/2007 Art. 10' } :
                          code.includes('002') ? { baseLegal: 'Ley 797/2003 Art. 7' } :
                          code.includes('003') ? { baseLegal: 'Ley 100/1993 Art. 27' } :
                          code.includes('004') ? { baseLegal: 'Ley 797/2003 Art. 7' } :
                          { baseLegal: 'Decreto 1295/1994' },
            };
        }

        return null;
    }

    /**
     * Obtiene los colores para el tipo de aporte actual
     */
    get coloresAporte() {
        const code = this.line.code || '';
        return getColoresAporte(code);
    }

    /**
     * Verifica si el IBC excede el tope de 4 SMMLV para FSP
     */
    get aplicaFSP() {
        const ibc = this.state.computation?.ibc || this.line.amount || 0;
        return ibc > TOPE_4_FSP;
    }

    /**
     * Calcula los multiplos de SMMLV del IBC
     */
    get ibcEnSMMLV() {
        const ibc = this.state.computation?.ibc || this.line.amount || 0;
        return (ibc / SMMLV_2025).toFixed(2);
    }

    /**
     * Verifica si el computation tiene la estructura estandarizada del backend.
     * Si tiene tipo_visualizacion, significa que el backend ya preparo todos los datos.
     */
    hasStandardizedComputation() {
        const comp = this.state.computation || {};
        return comp.tipo_visualizacion && comp.pasos && Array.isArray(comp.pasos);
    }

    /**
     * Usa la estructura estandarizada del backend para renderizar.
     * NO recalcula nada - solo formatea y muestra los datos que vienen del backend.
     */
    useStandardizedComputation() {
        const comp = this.state.computation || {};
        const total = this.line.total || 0;

        // Mapear indicadores del backend al formato del widget
        const indicators = (comp.indicadores || []).map(ind => ({
            label: ind.label,
            value: this.formatIndicatorValue(ind.value, ind.formato),
            color: ind.color || 'secondary'
        }));

        // Mapear pasos del backend al formato del widget
        const steps = (comp.pasos || []).map(paso => ({
            label: paso.label,
            value: paso.value,
            format: paso.format || 'currency',
            highlight: paso.highlight || false,
            baseLegal: paso.base_legal || null
        }));

        // Construir explicacion
        let explanation = comp.explicacion || '';
        if (comp.base_legal) {
            explanation += (explanation ? ' - ' : '') + comp.base_legal;
        }

        this.state.formulaData = {
            type: comp.tipo_visualizacion,
            formula: comp.formula || 'Monto x Cantidad x Tasa%',
            explanation: explanation,
            steps: steps,
            indicators: indicators,
            baseLegal: comp.base_legal || '',
            elementoLey: comp.elemento_ley || '',
            articulos: comp.articulos || [],
            valorAnterior: comp.valor_anterior,
            variacion: comp.variacion,
            mostrarPasos: comp.mostrar_pasos || false,
            mostrarBaseLegal: comp.mostrar_base_legal || false,
            datos: comp.datos || {}
        };

        return true;
    }

    /**
     * Formatea el valor de un indicador segun su formato.
     */
    formatIndicatorValue(value, formato) {
        if (formato === 'currency') {
            return this.formatValue(value);
        } else if (formato === 'number') {
            return typeof value === 'number' ? value.toLocaleString('es-CO') : value;
        } else if (formato === 'percentage') {
            return `${value}%`;
        }
        return value;
    }

    /**
     * Verifica si hay un template registrado para el codigo de regla.
     * Usa el RuleTemplateRegistry para obtener la configuracion.
     */
    hasRegisteredTemplate() {
        const code = this.line.code || '';
        const hasTemplate = RuleTemplateRegistry.has(code);
        console.log('[TEMPLATE DEBUG] hasRegisteredTemplate for code:', code, '=', hasTemplate);
        console.log('[TEMPLATE DEBUG] line data keys:', Object.keys(this.line));
        console.log('[TEMPLATE DEBUG] line.salary_rule_id:', this.line.salary_rule_id);
        return hasTemplate;
    }

    /**
     * Usa el template registrado en RuleTemplateRegistry.
     * Permite extension sin modificar el codigo base.
     */
    useRegisteredTemplate() {
        const code = this.line.code || '';
        const templateConfig = RuleTemplateRegistry.get(code);

        if (!templateConfig) return false;

        const comp = this.state.computation || {};
        const { templateName, processor, config } = templateConfig;

        // Si hay un procesador, usarlo para transformar los datos
        let processedData = null;
        if (processor && typeof processor === 'function') {
            try {
                processedData = processor(this.line, comp, this.state);
            } catch (e) {
                console.warn(`Error procesando regla ${code}:`, e);
            }
        }

        // Usar datos procesados o los de computation
        const data = processedData || comp;

        // Guardar el nombre del template para renderizarlo dinamicamente
        this.state.registeredTemplateName = templateName || null;
        this.state.ruleData = processedData;
        console.log('[TEMPLATE DEBUG] Code:', code, 'Template:', templateName, 'ProcessedData:', processedData);

        // Construir formulaData desde la configuracion del template
        this.state.formulaData = {
            type: config.type || data.tipo_visualizacion || 'generic',
            formula: data.formula || config.formula || '',
            explanation: data.explicacion || config.baseLegal || '',
            steps: data.pasos || [],
            indicators: data.indicadores || [],
            baseLegal: config.baseLegal || data.base_legal || '',
            templateConfig: config,
            processedData: processedData,
        };

        return true;
    }

    calculateFormula() {
        const code = this.line.code || '';
        const amount = this.line.amount || 0;
        const quantity = this.line.quantity || 1;
        const total = this.line.total || 0;
        const comp = this.state.computation || {};

        // PRIORIDAD 1: Si hay un template registrado en RuleTemplateRegistry, usarlo
        if (this.hasRegisteredTemplate()) {
            if (this.useRegisteredTemplate()) {
                return;
            }
        }

        // PRIORIDAD 2: Si el backend envio estructura estandarizada, usarla directamente
        if (this.hasStandardizedComputation()) {
            this.useStandardizedComputation();
            return;
        }

        // PRIORIDAD 3 (FALLBACK): Logica legacy para reglas que aun no usan estructura estandarizada
        const daysWorked = comp.days_worked || comp.effective_days || comp.days || quantity;

        this.state.formulaData = {
            type: 'generic',
            formula: 'Monto x Cantidad x Tasa%',
            explanation: '',
            steps: [],
            indicators: []
        };

        if (code.includes('BASIC')) {
            this.state.formulaData = {
                type: 'basico',
                formula: 'Salario / 30 x Dias',
                explanation: 'Salario basico proporcional al periodo trabajado',
                steps: [
                    { label: 'Salario Mensual', value: comp.salary || comp.wage || amount * 30, format: 'currency' },
                    { label: 'Dias Trabajados', value: daysWorked, format: 'number' },
                    { label: 'Valor Dia', value: comp.rate || (comp.salary || comp.wage || amount * 30) / 30, format: 'currency' },
                    { label: 'Total', value: total, format: 'currency', highlight: true }
                ]
            };
        } else if (code.includes('AUX')) {
            this.state.formulaData = {
                type: 'auxilio',
                formula: 'Auxilio ÷ 30 × Días',
                explanation: 'Auxilio de transporte proporcional (Art. 4 Ley 15/1959)',
                steps: [
                    { label: 'Auxilio Mensual', value: comp.auxilio_transporte || 200000, format: 'currency' },
                    { label: 'Días', value: daysWorked, format: 'number' },
                    { label: 'Total', value: total, format: 'currency', highlight: true }
                ]
            };
        } else if (this.isIBD) {
            const ibdData = comp;
            const ibc_pre = ibdData.ibc_pre || total;
            const ibc_final = ibdData.ibc_final || total;
            const smmlv = ibdData.smmlv || 1423500;

            const steps = [];

            // Salario básico
            steps.push({
                label: 'Salario Básico',
                value: ibdData.salary || 0,
                format: 'currency'
            });

            // Otros devengos no salariales (si existen)
            if (ibdData.o_earnings && ibdData.o_earnings > 0) {
                steps.push({
                    label: 'Otros Devengos No Salariales',
                    value: ibdData.o_earnings,
                    format: 'currency'
                });

                const tope40 = ibdData.top40 || 0;
                if (tope40 > 0) {
                    steps.push({
                        label: 'Tope 40%',
                        value: tope40,
                        format: 'currency'
                    });

                    const excedente = Math.max(0, ibdData.o_earnings - tope40);
                    if (excedente > 0) {
                        steps.push({
                            label: 'Excedente Excluido',
                            value: -excedente,
                            format: 'currency'
                        });
                    }
                }
            }

            // Ausencias
            if (ibdData.absences_amount && ibdData.absences_amount !== 0 && !ibdData.include_absences_1393) {
                steps.push({
                    label: 'Ausencias',
                    value: ibdData.absences_amount,
                    format: 'currency'
                });
            }

            // IBC Pre-topes
            steps.push({
                label: 'IBC Antes de Topes',
                value: ibc_pre,
                format: 'currency'
            });

            // Factor integral (si aplica)
            if (ibc_pre > 0 && Math.abs(ibc_pre - ibc_final) / ibc_pre > 0.25) {
                steps.push({
                    label: 'Factor Integral (70%)',
                    value: ibc_final,
                    format: 'currency'
                });
            }

            // IBC Final
            steps.push({
                label: 'IBC Final',
                value: ibc_final,
                format: 'currency',
                highlight: true
            });

            // Valor diario
            steps.push({
                label: 'Valor Diario (IBC / 30)',
                value: ibdData.day_value || (ibc_final / 30),
                format: 'currency'
            });

            // Fórmula
            let formula = 'Salario Básico';
            if (ibdData.o_earnings > 0) {
                formula = ibdData.o_earnings > (ibdData.top40 || 0) ?
                    'Salario + (O.Dev - Exc40%)' : 'Salario + O.Dev';
            }

            // Indicadores
            const indicators = [
                { label: 'Días', value: ibdData.effective_days || 30, color: 'info' },
                { label: 'SMMLV', value: this.formatValue(smmlv, 'currency'), color: 'secondary' }
            ];

            if (ibdData.o_earnings > 0 && ibdData.o_earnings > (ibdData.top40 || 0)) {
                indicators.push({ label: 'Regla 40%', value: 'Aplicada', color: 'warning' });
            }

            this.state.formulaData = {
                type: 'ibd',
                formula: formula,
                explanation: 'Ingreso Base de Cotización',
                steps: steps,
                indicators: indicators,
                legalRef: 'Ley 100/1993 Art.18 | Ley 1393/2010 Art.27-30'
            };
        } else if (this.isSocialSecurity) {
            const ssData = comp;
            const tipoSS = code.includes('001') ? 'Salud' :
                          code.includes('002') ? 'Pensión' :
                          code.includes('003') ? 'Fondo Solidaridad' :
                          code.includes('004') ? 'Fondo Subsistencia' : 'Seguridad Social';
            const tasa = this.line.rate || (code.includes('001') || code.includes('002') ? 4 : 0);

            const steps = [];

            // IBC Base
            steps.push({
                label: 'IBC Base',
                value: ssData.ibc || amount || 0,
                format: 'currency'
            });

            // Base de cálculo (puede ser proyectada)
            const ibcBase = ssData.ibc || amount || 0;
            const baseCalculo = ssData.base_calculo || 0;
            const baseLabel = ssData.base_proyectada ? 'Base Cálculo (proyectada)' : 'Base Cálculo';
            if (ssData.base_proyectada || (baseCalculo && Math.abs(baseCalculo - ibcBase) > 100)) {
                steps.push({
                    label: baseLabel,
                    value: baseCalculo,
                    format: 'currency'
                });
            }

            // Porcentaje
            steps.push({
                label: 'Porcentaje',
                value: `${tasa}%`,
                format: 'text'
            });

            // Aporte
            steps.push({
                label: 'Aporte Empleado',
                value: Math.abs(total),
                format: 'currency',
                highlight: true
            });

            // Indicadores
            const indicators = [
                { label: 'Tipo', value: tipoSS, color: 'primary' }
            ];

            // Período anterior (si existe)
            if (ssData.valor_anterior && ssData.valor_anterior !== 0) {
                const diff = Math.abs(total) - Math.abs(ssData.valor_anterior);
                indicators.push({
                    label: 'vs Anterior',
                    value: `${diff >= 0 ? '+' : ''}${this.formatValue(diff, 'currency')}`,
                    color: diff > 0 ? 'warning' : diff < 0 ? 'success' : 'secondary'
                });
            }

            this.state.formulaData = {
                type: 'seguridad_social',
                formula: `IBC x ${tasa}%`,
                explanation: `Aporte empleado a ${tipoSS}`,
                steps: steps,
                indicators: indicators,
                legalRef: code.includes('001') || code.includes('002') ?
                    'Art. 204 Ley 100/1993' :
                    'Art. 27 Ley 100/1993 | Art. 7 Ley 797/2003'
            };
        } else if (this.isProvision) {
            const provData = comp;
            const isPrima = code.includes('PRIM');
            const isCesantias = code.includes('CES') && !code.includes('ICES');
            const isIntereses = code.includes('ICES');
            const isVacaciones = code.includes('VAC');

            const tipoProv = isPrima ? 'Prima' : isCesantias ? 'Cesantías' :
                            isIntereses ? 'Intereses Cesantías' : isVacaciones ? 'Vacaciones' : 'Provisión';

            const steps = [];
            let formula;

            if (isIntereses) {
                // Intereses: Cesantías × 12%
                const cesBase = provData.valor_cesantias || provData.cesantias_proporcionales || 0;
                steps.push({ label: 'Cesantías Causadas', value: cesBase, format: 'currency' });
                steps.push({ label: 'Tasa', value: '12%', format: 'text' });
                steps.push({ label: 'Intereses', value: Math.abs(total), format: 'currency', highlight: true });
                formula = 'Cesantías x 12%';
            } else if (isVacaciones) {
                // Vacaciones: Base × Días / 720
                const baseSal = provData.base_total || provData.base_mensual || 0;
                const dias = provData.dias_computables || 30;
                steps.push({ label: 'Base Salarial', value: baseSal, format: 'currency' });
                steps.push({ label: 'Días', value: dias, format: 'number' });
                steps.push({ label: 'Factor', value: 'Días / 720', format: 'text' });
                steps.push({ label: 'Provisión', value: Math.abs(total), format: 'currency', highlight: true });
                formula = 'Base x (Días/720)';
            } else {
                // Prima y Cesantías: Base × Días / 360
                const baseSal = provData.base_total || provData.base_mensual || provData.base_diaria * 30 || 0;
                const dias = provData.dias_computables || 30;

                steps.push({ label: 'Base Salarial', value: baseSal, format: 'currency' });
                steps.push({ label: 'Días Causados', value: dias, format: 'number' });
                steps.push({ label: 'Factor', value: 'Días / 360', format: 'text' });

                // Mostrar acumulado si existe
                if (provData.total_causado && Math.abs(provData.total_causado - Math.abs(total)) > 100) {
                    steps.push({ label: 'Total Causado', value: Math.abs(provData.total_causado), format: 'currency' });
                    if (provData.provision_acumulada) {
                        steps.push({ label: 'Ya Provisionado', value: -Math.abs(provData.provision_acumulada), format: 'currency' });
                    }
                }

                steps.push({ label: 'Provisión Mes', value: Math.abs(total), format: 'currency', highlight: true });
                formula = 'Base x (Días/360)';
            }

            const indicators = [
                { label: 'Tipo', value: tipoProv, color: 'warning' }
            ];

            // Indicador de fecha
            if (provData.fecha_inicio && provData.fecha_corte) {
                const fechaInicio = new Date(provData.fecha_inicio).toLocaleDateString('es-CO', { month: 'short', day: 'numeric' });
                const fechaCorte = new Date(provData.fecha_corte).toLocaleDateString('es-CO', { month: 'short', day: 'numeric' });
                indicators.push({
                    label: 'Período',
                    value: `${fechaInicio} - ${fechaCorte}`,
                    color: 'info'
                });
            }

            const legalRef = isPrima ? 'Art. 306 CST' : isCesantias ? 'Art. 249 CST' :
                            isIntereses ? 'Ley 52/1975' : 'Art. 186 CST';

            this.state.formulaData = {
                type: 'provision',
                formula: formula,
                explanation: `Provisión mensual de ${tipoProv}`,
                steps: steps,
                indicators: indicators,
                legalRef: legalRef
            };
        } else if (this.isRetention) {
            const retData = comp;
            const baseGrav = retData.base_gravable || {};
            const baseGravableValue = baseGrav.ibr3_final || retData.ibr3_final || amount || 0;
            const baseUvt = baseGrav.ibr_uvts || retData.base_uvt || 0;
            const uvt = retData.valor_uvt || 49799;
            const tarifa = retData.tarifa_porcentaje || retData.tarifa || 0;

            // Determinar rango
            let rango = '';
            if (baseUvt > 0) {
                if (baseUvt <= 95) rango = '0 - 95 UVT (0%)';
                else if (baseUvt <= 150) rango = '95 - 150 UVT (19%)';
                else if (baseUvt <= 360) rango = '150 - 360 UVT (28%)';
                else if (baseUvt <= 640) rango = '360 - 640 UVT (33%)';
                else if (baseUvt <= 945) rango = '640 - 945 UVT (35%)';
                else if (baseUvt <= 2300) rango = '945 - 2300 UVT (37%)';
                else rango = '> 2300 UVT (39%)';
            }

            const steps = [];

            // Base gravable
            steps.push({
                label: 'Base Gravable',
                value: baseGravableValue,
                format: 'currency'
            });

            // Base en UVT
            steps.push({
                label: 'Base en UVT',
                value: baseUvt.toFixed(2),
                format: 'text'
            });

            // Rango
            if (rango) {
                steps.push({
                    label: 'Rango Tabla',
                    value: rango,
                    format: 'text'
                });
            }

            // Tarifa
            if (tarifa > 0) {
                steps.push({
                    label: 'Tarifa Marginal',
                    value: `${tarifa}%`,
                    format: 'text'
                });
            }

            // Retención
            steps.push({
                label: 'Retención',
                value: Math.abs(total),
                format: 'currency',
                highlight: true
            });

            const indicators = [
                { label: 'UVT', value: this.formatValue(uvt, 'currency'), color: 'info' }
            ];

            // Proyección
            if (retData.es_proyectado) {
                indicators.push({ label: 'Proyectado', value: 'Quincenal', color: 'warning' });
            }

            this.state.formulaData = {
                type: 'retencion',
                formula: 'Tabla Art. 383',
                explanation: 'Retención en la Fuente',
                steps: steps,
                indicators: indicators,
                legalRef: 'Art. 383 ET | Ley 2010/2019 Art. 42'
            };
        } else {
            this.state.formulaData = {
                type: 'generic',
                formula: 'Monto × Cantidad × Tasa%',
                explanation: '',
                steps: [
                    { label: 'Monto Base', value: amount, format: 'currency' },
                    { label: 'Cantidad', value: quantity, format: 'number' },
                    { label: 'Tasa', value: `${this.line.rate || 100}%`, format: 'text' },
                    { label: 'Total', value: total, format: 'currency', highlight: true }
                ]
            };
        }
    }

    formatValue(value, format) {
        if (value === null || value === undefined) return '-';
        if (format === 'currency') {
            return new Intl.NumberFormat('es-CO', {
                style: 'currency',
                currency: 'COP',
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            }).format(value);
        }
        if (format === 'number') {
            return new Intl.NumberFormat('es-CO', {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            }).format(value);
        }
        return value;
    }

    parseFloat(value) {
        if (value === null || value === undefined || value === '') return 0;
        const parsed = Number.parseFloat(value);
        return Number.isFinite(parsed) ? parsed : 0;
    }

    formatDate(dateStr) {
        if (!dateStr) return '-';
        // Parsear fecha sin problemas de zona horaria
        const parts = dateStr.split('-');
        if (parts.length !== 3) return dateStr;
        const year = parts[0];
        const month = parts[1];
        const day = parts[2];
        return `${day}/${month}/${year}`;
    }

    translateKey(key) {
        if (!key) return '';
        const lowerKey = key.toLowerCase().replace(/_/g, ' ');

        // Buscar traducción directa
        const translation = PayslipLineFormula.translations[key.toLowerCase()];
        if (translation) return translation;

        // Convertir snake_case a Title Case en español
        return key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    }

    formatDisplayValue(value, depth = 0, key = '') {
        if (value === null || value === undefined) return '-';
        if (typeof value === 'number') {
            // Detectar si es un campo de días por el nombre de la clave
            const keyLower = (key || '').toLowerCase();
            const isDaysField = keyLower.includes('days') || keyLower.includes('dias') ||
                               keyLower.includes('worked') || keyLower.includes('trabajados') ||
                               keyLower.includes('period') || keyLower.includes('cantidad') ||
                               keyLower.includes('quantity') || keyLower.includes('count') ||
                               keyLower.includes('number_of') || keyLower.includes('dias_') ||
                               keyLower.includes('_days');
            if (isDaysField) {
                return this.formatValue(value, 'number');
            }
            return this.formatValue(value, 'currency');
        }
        if (typeof value === 'boolean') return value ? 'Sí' : 'No';
        if (value === 'true' || value === 'True') return 'Sí';
        if (value === 'false' || value === 'False') return 'No';
        if (Array.isArray(value)) {
            if (value.length === 0) return '-';
            // Si son objetos simples, mostrar resumen
            if (typeof value[0] === 'object') {
                return `${value.length} elementos`;
            }
            return value.slice(0, 3).join(', ') + (value.length > 3 ? '...' : '');
        }
        if (typeof value === 'object') {
            const keys = Object.keys(value);
            if (keys.length === 0) return '-';
            // Limitar profundidad para evitar recursión infinita
            if (depth > 1) return `{${keys.length} campos}`;
            // Formatear objeto de manera inteligente
            const formattedParts = [];
            for (const k of keys.slice(0, 3)) {
                const subVal = value[k];
                let displayVal;
                if (subVal === null || subVal === undefined) {
                    displayVal = '-';
                } else if (typeof subVal === 'number') {
                    displayVal = this.formatValue(subVal, 'currency');
                } else if (typeof subVal === 'boolean') {
                    displayVal = subVal ? 'Sí' : 'No';
                } else if (typeof subVal === 'object') {
                    // Para objetos anidados, mostrar resumen
                    if (Array.isArray(subVal)) {
                        displayVal = `[${subVal.length}]`;
                    } else {
                        const subKeys = Object.keys(subVal);
                        if (subKeys.length === 0) {
                            displayVal = '-';
                        } else {
                            // Intentar extraer valores numéricos principales
                            const numericVals = subKeys
                                .filter(sk => typeof subVal[sk] === 'number')
                                .slice(0, 2)
                                .map(sk => `${this.translateKey(sk)}: ${this.formatValue(subVal[sk], 'currency')}`);
                            displayVal = numericVals.length > 0 ? numericVals.join(', ') : `{${subKeys.length}}`;
                        }
                    }
                } else {
                    displayVal = String(subVal);
                }
                formattedParts.push(`${this.translateKey(k)}: ${displayVal}`);
            }
            return formattedParts.join(' | ') + (keys.length > 3 ? ' ...' : '');
        }
        // Traducir valores de texto conocidos
        const translated = PayslipLineFormula.translations[String(value).toLowerCase()];
        if (translated) return translated;
        return String(value);
    }

    get computationEntries() {
        if (!this.state.computation || typeof this.state.computation !== 'object') return [];

        const entries = [];
        const skipKeys = new Set(['meta_info', 'acum_line_ids', 'steps', 'formula', 'indicators', 'lineas_detalle', 'line_ids']);
        if (this.isSocialSecurity) {
            const comp = this.state.computation || {};
            const code = this.line.code || '';
            const isFsp = code === 'SSOCIAL003' || code === 'SSOCIAL004';
            if (isFsp && !comp.base_proyectada && !comp.debe_proyectar) {
                ['ibc_periodo', 'base_calculo', 'base_proyectada', 'debe_proyectar'].forEach((key) => {
                    skipKeys.add(key);
                });
            }
        }
        let currentSection = null;

        Object.entries(this.state.computation).forEach(([key, value]) => {
            if (value === null || value === undefined || skipKeys.has(key)) return;

            if (typeof value === 'object' && !Array.isArray(value)) {
                // Agregar encabezado del grupo
                const sectionName = this.translateKey(key);
                currentSection = sectionName;
                entries.push({
                    key: `header_${key}`,
                    keyFormatted: sectionName,
                    displayValue: '',
                    isNumber: false,
                    isNested: false,
                    isHeader: true,
                    parentSection: null,
                });

                Object.entries(value).forEach(([subKey, subValue]) => {
                    if (subValue !== null && subValue !== undefined) {
                        entries.push({
                            key: `${key}_${subKey}`,
                            keyFormatted: this.translateKey(subKey),
                            displayValue: this.formatDisplayValue(subValue, 0, subKey),
                            isNumber: typeof subValue === 'number',
                            isNested: true,
                            isHeader: false,
                            parentKey: sectionName,
                            parentSection: sectionName,
                        });
                    }
                });
            } else {
                // Campos sueltos van a una sección "General" si no hay sección actual
                if (!currentSection) {
                    currentSection = 'General';
                    entries.push({
                        key: 'header_general',
                        keyFormatted: 'General',
                        displayValue: '',
                        isNumber: false,
                        isNested: false,
                        isHeader: true,
                        parentSection: null,
                    });
                }
                entries.push({
                    key: key,
                    keyFormatted: this.translateKey(key),
                    displayValue: this.formatDisplayValue(value, 0, key),
                    isNumber: typeof value === 'number',
                    isNested: false,
                    isHeader: false,
                    parentSection: currentSection,
                });
            }
        });

        return entries;
    }

    get stateLabel() {
        const states = {
            'draft': 'Borrador',
            'verify': 'Por Verificar',
            'done': 'Confirmado',
            'paid': 'Pagado',
            'cancel': 'Cancelado',
        };
        return states[this.state.payslip?.state] || this.state.payslip?.state || '-';
    }

    toggleDetails() {
        this.state.showDetails = !this.state.showDetails;
    }

    toggleDetailLines() {
        this.state.showDetailLines = !this.state.showDetailLines;
    }

    // Toggles para secciones del computation
    toggleComputationSection(sectionName, ev) {
        if (ev) ev.stopPropagation();
        if (!this.state.expandedComputationSections) {
            this.state.expandedComputationSections = {};
        }
        this.state.expandedComputationSections[sectionName] = !this.state.expandedComputationSections[sectionName];
    }

    isSectionExpanded(sectionName) {
        if (!this.state.expandedComputationSections) return false;
        return this.state.expandedComputationSections[sectionName] || false;
    }

    // Toggle para secciones de templates (IBD, Retención, etc.)
    toggleSection(sectionName) {
        if (!this.state.expandedSections) {
            this.state.expandedSections = {};
        }
        this.state.expandedSections[sectionName] = !this.state.expandedSections[sectionName];
    }

    // Métodos para navegar a registros relacionados
    async openRecord(model, resId) {
        if (!resId) return;
        await this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: model,
            res_id: resId,
            views: [[false, 'form']],
            target: 'current',
        });
    }

    openPayslip(slipId) {
        this.openRecord('hr.payslip', slipId);
    }

    openSalaryRule(ruleId) {
        this.openRecord('hr.salary.rule', ruleId);
    }

    openCategory(catId) {
        this.openRecord('hr.salary.rule.category', catId);
    }

    openContract(contractId) {
        this.openRecord('hr.contract', contractId);
    }

    openEmployee(employeeId) {
        this.openRecord('hr.employee', employeeId);
    }

    openPayslipLine(lineId) {
        this.openRecord('hr.payslip.line', lineId);
    }

    // Getters para agrupaciones
    get categoryGroups() {
        return Object.values(this.state.groupedByCategory);
    }

    get ruleGroups() {
        return Object.values(this.state.groupedByRule);
    }

    get usedRules() {
        const rules = [];
        const seen = new Set();
        const detailed = this.usedRulesDetailed;

        for (const rule of detailed) {
            const key = rule.code || rule.name;
            if (!key || seen.has(key)) continue;
            seen.add(key);
            rules.push({ id: rule.id || null, code: rule.code, name: rule.name });
        }

        return rules;
    }

    get usedRulesDetailed() {
        const entries = [];
        const seen = new Set();
        const detailLines = this.state.detailLines || [];

        for (const line of detailLines) {
            const code = line.code || '';
            const name = line.salary_rule_id ? line.salary_rule_id[1] : (line.name || code || '');
            const category = line.category_id ? line.category_id[1] : (line.category_code || '');
            const amount = line.amount || 0;
            const quantity = line.quantity || 0;
            const rate = line.rate || 0;
            const total = line.total || 0;
            const fingerprint = `${code}:${amount}:${quantity}:${rate}:${total}`;
            if (seen.has(fingerprint)) continue;
            seen.add(fingerprint);
            entries.push({
                id: line.salary_rule_id ? line.salary_rule_id[0] : null,
                code,
                name,
                category,
                amount,
                quantity,
                rate,
                total,
            });
        }

        const compRules = this.state.computation?.datos?.reglas_usadas ||
            this.state.computation?.reglas_usadas || [];
        for (const rule of compRules) {
            const code = rule.codigo || rule.code || '';
            const name = rule.nombre || rule.name || code || '';
            const category = rule.categoria || rule.category_name || rule.category_code || '';
            const amount = rule.amount || 0;
            const quantity = rule.quantity || 0;
            const rate = rule.rate || 0;
            const total = rule.total || 0;
            const fingerprint = `${code}:${amount}:${quantity}:${rate}:${total}`;
            if (seen.has(fingerprint)) continue;
            seen.add(fingerprint);
            entries.push({
                id: rule.rule_id || null,
                code,
                name,
                category,
                amount,
                quantity,
                rate,
                total,
            });
        }

        return entries;
    }

    formatRuleQuantity(rule) {
        const code = (rule.code || '').toUpperCase();
        const name = (rule.name || '').toUpperCase();
        const isHours = code.includes('HE') || name.includes('HORA') || name.includes('HORAS');
        const qty = this.formatValue(rule.quantity || 0, 'number');
        return isHours ? `${qty} H` : qty;
    }

    formatRuleRate(rule) {
        const rate = Number(rule.rate || 0);
        if (Number.isNaN(rate)) return '-';
        return `${rate.toFixed(2)}%`;
    }

    get hasDetailLines() {
        return this.state.detailLines && this.state.detailLines.length > 0;
    }

    // Obtener info de novedad/ausencia para una línea
    getNoveltyInfo(line) {
        if (line.leave_id) {
            return { type: 'ausencia', name: line.leave_id[1] || 'Ausencia' };
        }
        if (line.object_type === 'novelty') {
            return { type: 'novedad', name: line.entity_id ? line.entity_id[1] : 'Novedad' };
        }
        return null;
    }

    // Obtener info del contrato
    getContractInfo(line) {
        if (line.contract_id) {
            return { id: line.contract_id[0], name: line.contract_id[1] };
        }
        return null;
    }

    // Obtener info del empleado
    getEmployeeInfo(line) {
        if (line.employee_id) {
            return { id: line.employee_id[0], name: line.employee_id[1] };
        }
        return null;
    }
}

registry.category("fields").add("payslip_line_formula", {
    component: PayslipLineFormula,
});
