"""
WorkedDaysService - Servicio para cálculo de días trabajados (WORK100)

Maneja la lógica de:
- Día 31 según configuración de ausencia (apply_day_31)
- Auxilio de transporte según tipo de ausencia (pay_transport_allowance)
- Días virtuales de febrero
- Días fuera de contrato

Autor: Lavish S.A.S
"""

import calendar
from datetime import date, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
import logging

_logger = logging.getLogger(__name__)

# Constantes
DAYS_MONTH = 30
DAYS_YEAR = 360
HOURS_PER_DAY = 8


@dataclass
class DayInfo:
    """Información de un día específico en el período."""
    date: date
    day_number: int
    is_day_31: bool = False
    is_february_last: bool = False
    is_virtual_day: bool = False
    virtual_day_number: int = 0
    is_sunday: bool = False
    is_holiday: bool = False
    is_rest_day: bool = False
    is_within_contract: bool = True
    is_absence_day: bool = False
    absence_type_id: int = 0
    absence_config: Dict = field(default_factory=dict)
    days_payslip: float = 0
    days_work: float = 0
    days_aux: float = 0
    hours: float = 0
    amount: float = 0


@dataclass
class WorkedDaysResult:
    """Resultado del cálculo de días trabajados."""
    worked_days: float = 0          # WORK100 - días trabajados
    worked_aux_days: float = 0      # Días para auxilio de transporte
    worked_30: float = 0            # Día 31 (para WORK131)
    out_of_contract_days: float = 0 # Días fuera de contrato
    aux_transport_days: float = 0   # Días de ausencia que pagan auxilio
    days_without_aux_transport: float = 0  # Días que NO pagan auxilio (vacaciones, etc.)
    adjustments: List[str] = field(default_factory=list)
    day_details: List[DayInfo] = field(default_factory=list)

    # Resumen por tipo de ausencia
    absence_summary: Dict = field(default_factory=dict)


class WorkedDaysService:
    """
    Servicio para calcular días trabajados (WORK100) considerando:
    - Configuración de tipos de ausencia
    - Día 31 según apply_day_31
    - Auxilio de transporte según pay_transport_allowance
    - Días virtuales de febrero
    """

    def __init__(self, payslip=None, contract=None, holidays=None):
        """
        Inicializa el servicio.

        Args:
            payslip: hr.payslip record
            contract: hr.contract record
            holidays: Lista de fechas festivas
        """
        self.payslip = payslip
        self.contract = contract
        self.holidays = holidays or []
        self._result = WorkedDaysResult()

    def calculate(self, date_from: date, date_to: date, leaves: list = None) -> WorkedDaysResult:
        """
        Calcula los días trabajados para el período.

        Args:
            date_from: Fecha inicial del período
            date_to: Fecha final del período
            leaves: Lista de ausencias (hr.leave records)

        Returns:
            WorkedDaysResult con todos los cálculos
        """
        leaves = leaves or []
        self._result = WorkedDaysResult()

        # Calcular días base del período
        lab_days = self._days360(date_from, date_to)
        self._result.worked_days = lab_days
        self._result.worked_aux_days = lab_days

        # Procesar cada día del período
        current = date_from
        while current <= date_to:
            day_info = self._process_day(current, leaves)
            self._result.day_details.append(day_info)
            current += timedelta(days=1)

        # Agregar días virtuales de febrero si aplica
        if date_to.month == 2:
            self._add_february_virtual_days(date_to.year, leaves)

        # Procesar ausencias que NO pagan auxilio pero NO restan días trabajados
        # (ej: vacaciones disfrutadas con sub_wd=False, pay_transport_allowance=False)
        self._process_leaves_without_aux_transport(date_from, date_to, leaves)

        return self._result

    def _process_day(self, current_date: date, leaves: list) -> DayInfo:
        """
        Procesa un día específico.

        Args:
            current_date: Fecha a procesar
            leaves: Lista de ausencias

        Returns:
            DayInfo con la información del día
        """
        day_info = DayInfo(
            date=current_date,
            day_number=current_date.day,
            is_day_31=(current_date.day == 31),
            is_sunday=(current_date.weekday() == 6),
            is_holiday=(current_date in self.holidays),
        )
        day_info.is_rest_day = day_info.is_sunday or day_info.is_holiday

        # Verificar si está dentro del contrato
        if self.contract:
            contract_end = self.contract.date_end or current_date
            day_info.is_within_contract = (
                self.contract.date_start <= current_date <= contract_end
            )

        if not day_info.is_within_contract:
            self._result.out_of_contract_days += 1
            return day_info

        # Buscar ausencia activa para este día
        active_leave = self._find_active_leave(current_date, leaves)

        if active_leave:
            day_info.is_absence_day = True
            day_info.absence_type_id = active_leave.holiday_status_id.id
            day_info.absence_config = self._get_absence_config(active_leave)
            self._process_absence_day(day_info, active_leave)
        else:
            self._process_work_day(day_info)

        return day_info

    def _find_active_leave(self, current_date: date, leaves: list):
        """
        Busca una ausencia activa para la fecha dada.
        Solo considera ausencias que restan días (sub_wd=True).
        """
        for leave in leaves:
            leave_start = leave.date_from.date() if hasattr(leave.date_from, 'date') else leave.date_from
            leave_end = leave.date_to.date() if hasattr(leave.date_to, 'date') else leave.date_to

            if leave_start <= current_date <= leave_end:
                status = leave.holiday_status_id
                # Solo ausencias que restan días y no son vacaciones compensadas
                if status.sub_wd and status.novelty not in ['vco', 'p']:
                    return leave
        return None

    def _process_leaves_without_aux_transport(self, date_from: date, date_to: date, leaves: list):
        """
        Procesa ausencias que NO pagan auxilio de transporte pero NO restan días trabajados.
        Ejemplo: Vacaciones disfrutadas (sub_wd=False, pay_transport_allowance=False)

        Según Decreto 1250/2017, durante las vacaciones no se paga auxilio de transporte.
        """
        for leave in leaves:
            status = leave.holiday_status_id

            # Solo procesar ausencias que:
            # 1. NO restan días trabajados (sub_wd=False) - ya procesados en _find_active_leave
            # 2. NO pagan auxilio de transporte (pay_transport_allowance=False)
            # 3. NO son vacaciones compensadas ni permisos especiales
            if status.sub_wd:
                # Ya procesado en _find_active_leave
                continue

            if status.pay_transport_allowance:
                # Paga auxilio, no restar
                continue

            if status.novelty in ['vco', 'p']:
                # Vacaciones compensadas o permisos especiales
                continue

            # Calcular días de esta ausencia dentro del período de nómina
            leave_start = leave.date_from.date() if hasattr(leave.date_from, 'date') else leave.date_from
            leave_end = leave.date_to.date() if hasattr(leave.date_to, 'date') else leave.date_to

            # Intersección con el período de nómina
            overlap_start = max(leave_start, date_from)
            overlap_end = min(leave_end, date_to)

            if overlap_start > overlap_end:
                # Sin intersección
                continue

            # Calcular días usando método comercial 360
            days_without_aux = self._days360(overlap_start, overlap_end)

            # Acumular días sin auxilio de transporte
            self._result.days_without_aux_transport += days_without_aux

            # Log para debugging
            _logger.debug(
                f"Ausencia sin auxilio transporte: {status.code} "
                f"({overlap_start} - {overlap_end}): {days_without_aux} días"
            )

    def _get_absence_config(self, leave) -> Dict:
        """Obtiene la configuración del tipo de ausencia."""
        status = leave.holiday_status_id
        return {
            'code': status.code,
            'name': status.name,
            'sub_wd': status.sub_wd,
            'pay_transport_allowance': status.pay_transport_allowance,
            'apply_day_31': status.apply_day_31,
            'discount_rest_day': status.discount_rest_day,
            'pagar_festivos': getattr(status, 'evaluates_day_off', False),
        }

    def _process_absence_day(self, day_info: DayInfo, leave):
        """
        Procesa un día con ausencia.

        Lógica:
        1. Si es día 31 y apply_day_31=False: no cuenta en nómina
        2. Si pay_transport_allowance=True: suma a días de auxilio
        3. Obtiene valores de la línea de ausencia si existe
        """
        config = day_info.absence_config

        # Buscar línea de ausencia para este día
        absence_line = None
        for line in leave.line_ids:
            line_date = line.date.date() if hasattr(line.date, 'date') else line.date
            if line_date == day_info.date:
                absence_line = line
                break

        # Día 31 con ausencia
        if day_info.is_day_31:
            if config.get('apply_day_31', False):
                # El día 31 CUENTA en la ausencia
                day_info.days_payslip = 1
                if absence_line:
                    day_info.days_payslip = absence_line.days_payslip
                    day_info.hours = absence_line.hours
                    day_info.amount = absence_line.amount
            else:
                # El día 31 NO cuenta en la ausencia
                day_info.days_payslip = 0
                day_info.hours = 0
                day_info.amount = 0
        else:
            # Día normal (no 31)
            if absence_line:
                day_info.days_payslip = absence_line.days_payslip
                day_info.hours = absence_line.hours
                day_info.amount = absence_line.amount
            else:
                day_info.days_payslip = 1
                day_info.hours = HOURS_PER_DAY

        # Auxilio de transporte
        if config.get('pay_transport_allowance', False):
            # La ausencia paga auxilio
            day_info.days_aux = day_info.days_payslip
            self._result.aux_transport_days += day_info.days_payslip
        else:
            # La ausencia NO paga auxilio
            day_info.days_aux = 0

        # Acumular en resumen de ausencias
        type_id = day_info.absence_type_id
        if type_id not in self._result.absence_summary:
            self._result.absence_summary[type_id] = {
                'code': config.get('code', ''),
                'name': config.get('name', ''),
                'days_payslip': 0,
                'hours': 0,
                'amount': 0,
                'days_aux': 0,
            }
        self._result.absence_summary[type_id]['days_payslip'] += day_info.days_payslip
        self._result.absence_summary[type_id]['hours'] += day_info.hours
        self._result.absence_summary[type_id]['amount'] += day_info.amount
        self._result.absence_summary[type_id]['days_aux'] += day_info.days_aux

    def _process_work_day(self, day_info: DayInfo):
        """
        Procesa un día de trabajo normal (sin ausencia).

        Lógica:
        1. Febrero último día: agregar días virtuales
        2. Día 31: verificar si hay ausencia con apply_day_31
        """
        # Verificar febrero
        if day_info.date.month == 2:
            last_day_feb = calendar.monthrange(day_info.date.year, 2)[1]
            if day_info.day_number == last_day_feb:
                day_info.is_february_last = True
                # Agregar días virtuales
                virtual_days = 2 if last_day_feb == 28 else 1
                self._result.worked_days += virtual_days
                self._result.worked_aux_days += virtual_days
                self._result.adjustments.append(f"(+{virtual_days} D febrero)")

        # Verificar día 31
        elif day_info.is_day_31:
            # Por defecto, día 31 no está en el cálculo base (days360)
            # Solo se resta si hay una ausencia con apply_day_31=True
            self._result.worked_30 = 1  # Para WORK131

    def _add_february_virtual_days(self, year: int, leaves: list):
        """
        Agrega días virtuales de febrero (29 y 30) si hay ausencias al final del mes.
        """
        last_day_feb = calendar.monthrange(year, 2)[1]
        virtual_days_needed = 30 - last_day_feb  # 2 si no bisiesto, 1 si bisiesto

        # Verificar si hay ausencia que cubre el último día de febrero
        feb_last = date(year, 2, last_day_feb)
        active_leave = self._find_active_leave(feb_last, leaves)

        if active_leave:
            config = self._get_absence_config(active_leave)

            for i in range(virtual_days_needed):
                virtual_day_num = last_day_feb + 1 + i
                day_info = DayInfo(
                    date=feb_last,  # Usar última fecha real
                    day_number=virtual_day_num,
                    is_virtual_day=True,
                    virtual_day_number=virtual_day_num,
                    is_absence_day=True,
                    absence_type_id=active_leave.holiday_status_id.id,
                    absence_config=config,
                    days_payslip=1,
                    hours=HOURS_PER_DAY,
                )

                # Auxilio en días virtuales
                if config.get('pay_transport_allowance', False):
                    day_info.days_aux = 1
                    self._result.aux_transport_days += 1

                self._result.day_details.append(day_info)

                # Acumular en resumen
                type_id = day_info.absence_type_id
                if type_id in self._result.absence_summary:
                    self._result.absence_summary[type_id]['days_payslip'] += 1
                    self._result.absence_summary[type_id]['hours'] += HOURS_PER_DAY
                    self._result.absence_summary[type_id]['days_aux'] += day_info.days_aux

    def _days360(self, start_date: date, end_date: date) -> int:
        """
        Calcula dias entre fechas con metodo comercial colombiano 360.
        Todos los meses = 30 dias, febrero 28/29 = dia 30.
        """
        start_day = start_date.day
        end_day = end_date.day

        if start_day == 31 or (start_date.month == 2 and start_day >= 28):
            start_day = 30
        else:
            start_day = min(start_day, 30)

        if end_day == 31 or (end_date.month == 2 and end_day >= 28):
            end_day = 30
        else:
            end_day = min(end_day, 30)

        return (
            (end_date.year - start_date.year) * 360 +
            (end_date.month - start_date.month) * 30 +
            (end_day - start_day) + 1
        )

    def get_work100_line(self, wage_day: float = 0, hours_daily: float = HOURS_PER_DAY) -> Dict:
        """
        Genera la línea WORK100 para worked_days_line_ids.

        Args:
            wage_day: Salario diario
            hours_daily: Horas por día

        Returns:
            Dict con los datos para la línea de trabajo
        """
        worked_days = self._result.worked_days

        # Días para auxilio de transporte:
        # + worked_days: días trabajados base
        # + aux_transport_days: días de ausencias que SÍ pagan auxilio (ej: incapacidades)
        # - days_without_aux_transport: días de ausencias que NO pagan auxilio (ej: vacaciones)
        # Según Decreto 1250/2017: No se paga auxilio durante vacaciones
        worked_aux_days = (
            self._result.worked_days
            + self._result.aux_transport_days
            - self._result.days_without_aux_transport
        )

        # Construir nombre con ajustes
        name = 'Días Trabajados'
        if self._result.adjustments:
            name += ' ' + ' '.join(self._result.adjustments)

        return {
            'name': name,
            'code': 'WORK100',
            'symbol': '+',
            'sequence': 6,
            'number_of_days': worked_days,
            'number_of_hours': worked_days * hours_daily,
            'number_of_days_aux': worked_aux_days,
            'number_of_hours_aux': worked_aux_days * hours_daily,
            'amount': wage_day * worked_days,
        }

    def get_work131_line(self, wage_day: float = 0, hours_daily: float = HOURS_PER_DAY) -> Dict:
        """
        Genera la línea WORK131 (día 31) para worked_days_line_ids.
        """
        return {
            'name': 'Día 31',
            'code': 'WORK131',
            'symbol': '+',
            'sequence': 6,
            'number_of_days': self._result.worked_30,
            'number_of_hours': self._result.worked_30 * hours_daily,
            'number_of_days_aux': self._result.worked_30,
            'number_of_hours_aux': self._result.worked_30 * hours_daily,
            'amount': wage_day * self._result.worked_30,
        }

    def get_absence_lines(self) -> List[Dict]:
        """
        Genera las líneas de ausencia para worked_days_line_ids.

        Returns:
            Lista de dicts con las líneas de ausencia
        """
        lines = []
        for type_id, summary in self._result.absence_summary.items():
            lines.append({
                'name': f"Días {summary['name'].capitalize()}",
                'code': summary['code'] or 'nocode',
                'symbol': '-',
                'sequence': 5,
                'number_of_days': summary['days_payslip'],
                'number_of_hours': summary['hours'],
                'amount': summary['amount'],
            })
        return lines

    def print_summary(self):
        """Imprime un resumen del cálculo para debugging."""
        print("\n" + "=" * 80)
        print(" RESUMEN WORKED DAYS SERVICE")
        print("=" * 80)
        print(f"  WORK100 (días trabajados):    {self._result.worked_days}")
        # Cálculo de días para auxilio: worked_days + aux_transport_days - days_without_aux_transport
        dias_aux = self._result.worked_days + self._result.aux_transport_days - self._result.days_without_aux_transport
        print(f"  Días auxilio transporte:      {dias_aux}")
        print(f"  WORK131 (día 31):             {self._result.worked_30}")
        print(f"  Días fuera de contrato:       {self._result.out_of_contract_days}")
        print(f"  Días ausencia pagan auxilio:  {self._result.aux_transport_days}")
        print(f"  Días sin auxilio (vac, etc):  {self._result.days_without_aux_transport}")
        print(f"  Ajustes:                      {self._result.adjustments}")

        if self._result.absence_summary:
            print("\n  AUSENCIAS:")
            for type_id, summary in self._result.absence_summary.items():
                print(f"    {summary['code']}: {summary['days_payslip']} días, ${summary['amount']:,.0f}")

        print("=" * 80)
