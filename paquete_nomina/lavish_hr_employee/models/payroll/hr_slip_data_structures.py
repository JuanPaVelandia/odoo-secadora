# -*- coding: utf-8 -*-
"""


- LineDetail: Almacena información detallada de líneas con fechas
- add_value()/delete_value(): Modificación con recomputo automático
- Tracking de dependencias entre reglas
- Historial de cambios
- Métodos para generación de reportes

Este módulo define clases que encapsulan datos de categorías y reglas durante
el cálculo de nómina, garantizando tipos
BENEFICIOS:
- Tipos garantizados desde la creación
- Acceso directo a propiedades sin .get()
- Métodos de filtrado integrados
- Recomputo automático al modificar valores
- Detalles de líneas para reportes
"""

from typing import List, Dict, Optional, Callable, Set, Tuple
from decimal import Decimal
from datetime import date, datetime
from collections import defaultdict


class LineDetail:
    """
    Encapsula detalles de una línea de nómina para reportes.

    Contiene información completa incluyendo fechas, empleado, contrato, etc.

    Uso:
        detail = LineDetail(
            line_id=1001,
            date_from=date(2025, 1, 1),
            date_to=date(2025, 1, 31),
            employee_id=50,
            employee_name='Juan Pérez',
            amount=100000
        )

        # Para reportes
        print(f"{detail.employee_name}: {detail.amount} ({detail.date_from})")
    """

    __slots__ = (
        'line_id', 'date_from', 'date_to', 'employee_id', 'employee_name',
        'contract_id', 'amount', 'quantity', 'rate', 'total',
        'rule_code', 'rule_name', 'category_code', 'category_name',
        'slip_id', 'slip_number', 'metadata'
    )

    def __init__(
        self,
        line_id: int = 0,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        employee_id: int = 0,
        employee_name: str = '',
        contract_id: int = 0,
        amount: float = 0.0,
        quantity: float = 1.0,
        rate: float = 100.0,
        total: float = 0.0,
        rule_code: str = '',
        rule_name: str = '',
        category_code: str = '',
        category_name: str = '',
        slip_id: int = 0,
        slip_number: str = '',
        metadata: Optional[Dict] = None
    ):
        self.line_id = int(line_id)
        self.date_from = date_from
        self.date_to = date_to
        self.employee_id = int(employee_id)
        self.employee_name = str(employee_name)
        self.contract_id = int(contract_id)
        self.amount = float(amount)
        self.quantity = float(quantity)
        self.rate = float(rate)
        self.total = float(total)
        self.rule_code = str(rule_code)
        self.rule_name = str(rule_name)
        self.category_code = str(category_code)
        self.category_name = str(category_name)
        self.slip_id = int(slip_id)
        self.slip_number = str(slip_number)
        self.metadata = metadata if metadata is not None else {}

    def to_dict(self) -> dict:
        """Convierte a diccionario para serialización."""
        return {
            'line_id': self.line_id,
            'date_from': self.date_from.isoformat() if self.date_from else None,
            'date_to': self.date_to.isoformat() if self.date_to else None,
            'employee_id': self.employee_id,
            'employee_name': self.employee_name,
            'contract_id': self.contract_id,
            'amount': self.amount,
            'quantity': self.quantity,
            'rate': self.rate,
            'total': self.total,
            'rule_code': self.rule_code,
            'rule_name': self.rule_name,
            'category_code': self.category_code,
            'category_name': self.category_name,
            'slip_id': self.slip_id,
            'slip_number': self.slip_number,
            'metadata': self.metadata,
        }

    def __repr__(self):
        return f"LineDetail(id={self.line_id}, employee='{self.employee_name}', total={self.total})"


class ChangeRecord:
    """
    Registra un cambio en RuleData o CategoryData.

    Útil para auditoría y debugging.

    Uso:
        record = ChangeRecord(
            operation='add_value',
            amount=50000,
            previous_total=300000,
            new_total=350000
        )
    """

    __slots__ = ('timestamp', 'operation', 'amount', 'previous_total', 'new_total', 'metadata')

    def __init__(
        self,
        operation: str,
        amount: float = 0.0,
        previous_total: float = 0.0,
        new_total: float = 0.0,
        metadata: Optional[Dict] = None
    ):
        self.timestamp = datetime.now()
        self.operation = str(operation)
        self.amount = float(amount)
        self.previous_total = float(previous_total)
        self.new_total = float(new_total)
        self.metadata = metadata if metadata is not None else {}

    def __repr__(self):
        return f"ChangeRecord({self.operation}: {self.previous_total} → {self.new_total})"


class RuleData:
    """
    Encapsula datos de una regla salarial calculada con funcionalidades avanzadas.

    NUEVAS FUNCIONALIDADES v2.0:
    - line_details: Lista de LineDetail con información completa
    - dependent_rules: Tracking de reglas que dependen de esta
    - change_history: Historial de cambios
    - add_value()/delete_value(): Modificación con recomputo
    - get_line_details(): Detalles para reportes

    Uso:
        rule_data = RuleData(
            code='HEYREC_D',
            total=300000,
            rule=rule_obj
        )

        # Acceso directo
        total = rule_data.total
        is_prima = rule_data.rule.base_prima

        # Agregar valor
        rule_data.add_value(amount=50000, recompute_callback=lambda: recalc())

        # Obtener detalles
        details = rule_data.get_line_details(env)
    """

    __slots__ = (
        'code', 'total', 'amount', 'quantity', 'rate',
        'category_id', 'category_code', 'rule_id', 'rule',
        'has_leave', 'payslip_id', 'line_ids', 'line_details',
        'dependent_rules', 'change_history', '_track_changes',
        'leave_id', 'leave_novelty', 'leave_liquidacion_value',
        'extra_data'
    )

    def __init__(
        self,
        code: str,
        total: float = 0.0,
        amount: float = 0.0,
        quantity: float = 1.0,
        rate: float = 100.0,
        category_id: int = 0,
        category_code: str = '',
        rule_id: int = 0,
        rule=None,
        has_leave: bool = False,
        payslip_id: int = 0,
        line_ids: Optional[List[int]] = None,
        line_details: Optional[List[LineDetail]] = None,
        dependent_rules: Optional[Set[str]] = None,
        track_changes: bool = False,
        leave_id: int = 0,
        leave_novelty: str = '',
        leave_liquidacion_value: str = '',
        extra_data: Optional[Dict] = None
    ):
        self.code = code
        self.total = float(total)
        self.amount = float(amount)
        self.quantity = float(quantity)
        self.rate = float(rate)
        self.category_id = int(category_id)
        self.category_code = str(category_code)
        self.rule_id = int(rule_id)
        self.rule = rule
        self.has_leave = bool(has_leave)
        self.payslip_id = int(payslip_id)
        self.line_ids = line_ids if line_ids is not None else []
        self.line_details = line_details if line_details is not None else []
        self.dependent_rules = dependent_rules if dependent_rules is not None else set()
        self.change_history = []
        self._track_changes = bool(track_changes)
        self.leave_id = int(leave_id)
        self.leave_novelty = str(leave_novelty)
        self.leave_liquidacion_value = str(leave_liquidacion_value)
        self.extra_data = extra_data if extra_data is not None else {}

    def add_value(
        self,
        amount: float,
        quantity: float = 1.0,
        rate: float = 100.0,
        line_detail: Optional[LineDetail] = None,
        recompute_callback: Optional[Callable] = None
    ):
        """
        Agrega un valor y opcionalmente recomputa reglas dependientes.

        Uso:
            # Simple
            rule_data.add_value(amount=50000)

            # Con detalle de línea
            detail = LineDetail(line_id=1001, amount=50000, ...)
            rule_data.add_value(amount=50000, line_detail=detail)

            # Con recomputo de dependientes
            rule_data.add_value(
                amount=50000,
                recompute_callback=lambda: recompute_dependent_rules()
            )

        Args:
            amount: Monto a agregar
            quantity: Cantidad (opcional)
            rate: Tasa (opcional)
            line_detail: Detalle de línea para reportes (opcional)
            recompute_callback: Función a ejecutar para recomputar dependientes
        """
        previous_total = self.total

        self.total += float(amount)
        self.amount += float(amount)
        self.quantity += float(quantity)
        self.rate = float(rate)

        if line_detail:
            self.line_details.append(line_detail)

        if self._track_changes:
            change = ChangeRecord(
                operation='add_value',
                amount=amount,
                previous_total=previous_total,
                new_total=self.total,
                metadata={'quantity': quantity, 'rate': rate}
            )
            self.change_history.append(change)

        if recompute_callback and callable(recompute_callback):
            recompute_callback()

    def delete_value(
        self,
        amount: float,
        quantity: float = 1.0,
        line_id: Optional[int] = None,
        recompute_callback: Optional[Callable] = None
    ):
        """
        Elimina un valor y opcionalmente recomputa reglas dependientes.

        Uso:
            # Simple
            rule_data.delete_value(amount=50000)

            # Eliminando detalle de línea específica
            rule_data.delete_value(amount=50000, line_id=1001)

            # Con recomputo
            rule_data.delete_value(
                amount=50000,
                recompute_callback=lambda: recompute_dependent_rules()
            )

        Args:
            amount: Monto a restar
            quantity: Cantidad a restar (opcional)
            line_id: ID de línea a eliminar de detalles (opcional)
            recompute_callback: Función a ejecutar para recomputar dependientes
        """
        previous_total = self.total

        self.total -= float(amount)
        self.amount -= float(amount)
        self.quantity -= float(quantity)

        if line_id:
            self.line_details = [
                detail for detail in self.line_details
                if detail.line_id != line_id
            ]
            self.line_ids = [lid for lid in self.line_ids if lid != line_id]

        if self._track_changes:
            change = ChangeRecord(
                operation='delete_value',
                amount=-amount,
                previous_total=previous_total,
                new_total=self.total,
                metadata={'quantity': quantity, 'line_id': line_id}
            )
            self.change_history.append(change)

        if recompute_callback and callable(recompute_callback):
            recompute_callback()

    def accumulate(self, amount: float, quantity: float = 1.0, rate: float = 100.0):
        """
        Acumula valores a la regla (alias de add_value sin callbacks).

        Uso:
            rule_data.accumulate(amount=50000, quantity=2)
        """
        self.add_value(amount=amount, quantity=quantity, rate=rate)

    def matches_filter(self, **filters) -> bool:
        """
        Verifica si la regla cumple los filtros especificados.

        Uso:
            if rule_data.matches_filter(base_prima=True, category_code='HEYREC'):
                base_prima += rule_data.total

        Filtros disponibles:
            - base_prima, base_cesantias, base_vacaciones, etc.
            - category_code, category_codes (lista)
            - min_total, max_total
            - custom (función lambda)
        """
        if 'base_prima' in filters and filters['base_prima']:
            if not (self.rule and self.rule.base_prima):
                return False

        if 'base_cesantias' in filters and filters['base_cesantias']:
            if not (self.rule and self.rule.base_cesantias):
                return False

        if 'base_vacaciones' in filters and filters['base_vacaciones']:
            if not (self.rule and self.rule.base_vacaciones):
                return False

        if 'base_seguridad_social' in filters and filters['base_seguridad_social']:
            if not (self.rule and self.rule.base_seguridad_social):
                return False

        if 'category_code' in filters:
            if self.category_code != filters['category_code']:
                return False

        if 'category_codes' in filters:
            if self.category_code not in filters['category_codes']:
                return False

        if 'min_total' in filters:
            if self.total < filters['min_total']:
                return False

        if 'max_total' in filters:
            if self.total > filters['max_total']:
                return False

        if 'custom' in filters and callable(filters['custom']):
            if not filters['custom'](self):
                return False

        return True

    def add_dependent_rule(self, rule_code: str):
        """
        Registra una regla que depende de esta.

        Uso:
            # BASIC depende de SALARY_BASE
            salary_base.add_dependent_rule('BASIC')
            salary_base.add_dependent_rule('TOTAL_EARNINGS')

        Args:
            rule_code: Código de la regla dependiente
        """
        self.dependent_rules.add(str(rule_code))

    def has_dependents(self) -> bool:
        """
        Verifica si hay reglas que dependen de esta.

        Uso:
            if rule_data.has_dependents():
                recompute_dependents()

        Returns:
            True si hay dependientes
        """
        return len(self.dependent_rules) > 0

    def get_line_details(self, env=None, fetch_from_db: bool = False) -> List[LineDetail]:
        """
        Obtiene detalles completos de líneas para reportes.

        Uso:
            # Usar detalles en memoria
            details = rule_data.get_line_details()

            # O fetch desde base de datos
            details = rule_data.get_line_details(env, fetch_from_db=True)

            for detail in details:
                print(f"{detail.date_from} - {detail.employee_name}: {detail.total}")

        Args:
            env: Environment de Odoo (requerido si fetch_from_db=True)
            fetch_from_db: Si True, consulta hr.payslip.line en BD

        Returns:
            Lista de LineDetail con información completa
        """
        if not fetch_from_db or not self.line_details:
            return self.line_details

        if not env or not self.line_ids:
            return self.line_details

        lines = env['hr.payslip.line'].browse(self.line_ids)
        details = []

        for line in lines:
            detail = LineDetail(
                line_id=line.id,
                date_from=line.slip_id.date_from if line.slip_id else None,
                date_to=line.slip_id.date_to if line.slip_id else None,
                employee_id=line.employee_id.id if line.employee_id else 0,
                employee_name=line.employee_id.name if line.employee_id else '',
                contract_id=line.contract_id.id if line.contract_id else 0,
                amount=line.amount,
                quantity=line.quantity,
                rate=line.rate,
                total=line.total,
                rule_code=line.salary_rule_id.code if line.salary_rule_id else '',
                rule_name=line.salary_rule_id.name if line.salary_rule_id else '',
                category_code=line.category_id.code if line.category_id else '',
                category_name=line.category_id.name if line.category_id else '',
                slip_id=line.slip_id.id if line.slip_id else 0,
                slip_number=line.slip_id.number if line.slip_id else '',
            )
            details.append(detail)

        return details

    def get_details_by_period(self, start_date: date, end_date: date, env=None) -> List[LineDetail]:
        """
        Filtra detalles de líneas por período de fechas.

        Uso:
            details = rule_data.get_details_by_period(
                date(2025, 1, 1),
                date(2025, 3, 31),
                env
            )

        Args:
            start_date: Fecha inicial
            end_date: Fecha final
            env: Environment de Odoo (opcional)

        Returns:
            Lista de LineDetail dentro del período
        """
        details = self.get_line_details(env, fetch_from_db=True)

        filtered = [
            detail for detail in details
            if detail.date_from and start_date <= detail.date_from <= end_date
        ]

        return filtered

    def get_change_history(self) -> List[ChangeRecord]:
        """
        Obtiene historial de cambios si tracking está activo.

        Uso:
            history = rule_data.get_change_history()
            for change in history:
                print(f"{change.timestamp}: {change.operation} = {change.amount}")

        Returns:
            Lista de ChangeRecord
        """
        return self.change_history

    def to_dict(self, include_details: bool = False) -> dict:
        """
        Convierte a diccionario (compatibilidad con código legacy).

        Uso:
            # Básico
            legacy_dict = rule_data.to_dict()

            # Con detalles completos
            full_dict = rule_data.to_dict(include_details=True)

        Args:
            include_details: Si True, incluye line_details y change_history

        Returns:
            Diccionario con datos de la regla
        """
        result = {
            'code': self.code,
            'total': self.total,
            'amount': self.amount,
            'quantity': self.quantity,
            'rate': self.rate,
            'category_id': self.category_id,
            'category_code': self.category_code,
            'rule_id': self.rule_id,
            'rule': self.rule,
            'has_leave': self.has_leave,
            'payslip_id': self.payslip_id,
            'line_ids': self.line_ids,
        }

        if include_details:
            result['line_details'] = [d.to_dict() for d in self.line_details]
            result['dependent_rules'] = list(self.dependent_rules)
            result['change_history'] = [
                {
                    'timestamp': ch.timestamp.isoformat(),
                    'operation': ch.operation,
                    'amount': ch.amount,
                    'previous_total': ch.previous_total,
                    'new_total': ch.new_total,
                }
                for ch in self.change_history
            ]

        return result

    def __repr__(self):
        deps = f", deps={len(self.dependent_rules)}" if self.dependent_rules else ""
        return f"RuleData(code='{self.code}', total={self.total}, category='{self.category_code}'{deps})"


class CategoryData:
    """
    Encapsula datos de una categoría salarial.

    Garantiza tipos y proporciona métodos de agregación/filtrado.

    Uso:
        cat_data = CategoryData(code='HEYREC')
        cat_data.add_rule(rule_data)

        # Acceso directo
        total = cat_data.total

        # Filtrado por reglas
        prima_rules = cat_data.filter_rules(base_prima=True)
        total_prima = sum(r.total for r in prima_rules)
    """

    __slots__ = ('code', 'total', 'quantity', 'rule_codes', 'rules', 'line_ids')

    def __init__(
        self,
        code: str,
        total: float = 0.0,
        quantity: float = 0.0,
        rule_codes: Optional[List[str]] = None,
        rules: Optional[List[RuleData]] = None,
        line_ids: Optional[List[int]] = None
    ):
        self.code = str(code)
        self.total = float(total)
        self.quantity = float(quantity)
        self.rule_codes = rule_codes if rule_codes is not None else []
        self.rules = rules if rules is not None else []
        self.line_ids = line_ids if line_ids is not None else []

    def add_rule(self, rule_data: RuleData):
        """
        Agrega una regla a la categoría y acumula sus valores.

        Uso:
            category.add_rule(rule_data)
        """
        self.total += rule_data.total
        self.quantity += rule_data.quantity

        if rule_data.code not in self.rule_codes:
            self.rule_codes.append(rule_data.code)

        self.rules.append(rule_data)
        self.line_ids.extend(rule_data.line_ids)

    def filter_rules(self, **filters) -> List[RuleData]:
        """
        Filtra reglas de esta categoría según criterios.

        Uso:
            # Solo reglas con base_prima=True
            prima_rules = category.filter_rules(base_prima=True)

            # Solo reglas con total > 100000
            high_rules = category.filter_rules(min_total=100000)

            # Filtro custom
            custom_rules = category.filter_rules(
                custom=lambda r: r.rule.code.startswith('HEY')
            )

        Returns:
            Lista de RuleData que cumplen los filtros
        """
        return [rule for rule in self.rules if rule.matches_filter(**filters)]

    def get_filtered_total(self, **filters) -> float:
        """
        Obtiene total de reglas filtradas.

        Uso:
            # Total de reglas con base_prima=True en esta categoría
            total_prima = category.get_filtered_total(base_prima=True)

        Returns:
            Suma de totales de reglas que cumplen los filtros
        """
        filtered = self.filter_rules(**filters)
        return sum(rule.total for rule in filtered)

    def has_rule(self, rule_code: str) -> bool:
        """
        Verifica si la categoría contiene una regla específica.

        Uso:
            if category.has_rule('HEYREC_D'):
                ...
        """
        return rule_code in self.rule_codes

    def add_value(
        self,
        amount: float,
        rule_code: Optional[str] = None,
        recompute_callback: Optional[Callable] = None
    ):
        """
        Agrega un valor a la categoría. Si rule_code se proporciona,
        busca la regla y le agrega el valor.

        Uso:
            # Agregar a total de categoría
            category.add_value(amount=50000)

            # Agregar a regla específica
            category.add_value(amount=50000, rule_code='HEYREC_D')

        Args:
            amount: Monto a agregar
            rule_code: Código de regla específica (opcional)
            recompute_callback: Función de recomputo (opcional)
        """
        self.total += float(amount)

        if rule_code:
            for rule in self.rules:
                if rule.code == rule_code:
                    rule.add_value(amount=amount, recompute_callback=recompute_callback)
                    break

    def delete_value(
        self,
        amount: float,
        rule_code: Optional[str] = None,
        recompute_callback: Optional[Callable] = None
    ):
        """
        Elimina un valor de la categoría. Si rule_code se proporciona,
        busca la regla y le elimina el valor.

        Uso:
            # Eliminar de total de categoría
            category.delete_value(amount=50000)

            # Eliminar de regla específica
            category.delete_value(amount=50000, rule_code='HEYREC_D')

        Args:
            amount: Monto a restar
            rule_code: Código de regla específica (opcional)
            recompute_callback: Función de recomputo (opcional)
        """
        self.total -= float(amount)

        if rule_code:
            for rule in self.rules:
                if rule.code == rule_code:
                    rule.delete_value(amount=amount, recompute_callback=recompute_callback)
                    break

    def get_all_line_details(self, env=None, fetch_from_db: bool = False) -> List[LineDetail]:
        """
        Obtiene detalles de líneas de TODAS las reglas en esta categoría.

        Uso:
            # Todas las líneas de la categoría HEYREC
            details = heyrec_category.get_all_line_details(env, fetch_from_db=True)

            for detail in details:
                print(f"{detail.rule_code}: {detail.total}")

        Args:
            env: Environment de Odoo (requerido si fetch_from_db=True)
            fetch_from_db: Si True, consulta desde BD

        Returns:
            Lista consolidada de LineDetail de todas las reglas
        """
        all_details = []
        for rule in self.rules:
            details = rule.get_line_details(env, fetch_from_db)
            all_details.extend(details)
        return all_details

    def get_details_by_period(
        self,
        start_date: date,
        end_date: date,
        env=None
    ) -> Dict[str, List[LineDetail]]:
        """
        Obtiene detalles por período agrupados por regla.

        Uso:
            details_by_rule = category.get_details_by_period(
                date(2025, 1, 1),
                date(2025, 3, 31),
                env
            )

            for rule_code, details in details_by_rule.items():
                print(f"{rule_code}: {len(details)} líneas")

        Args:
            start_date: Fecha inicial
            end_date: Fecha final
            env: Environment de Odoo (opcional)

        Returns:
            Diccionario {rule_code: [LineDetail, ...]}
        """
        result = {}
        for rule in self.rules:
            details = rule.get_details_by_period(start_date, end_date, env)
            if details:
                result[rule.code] = details
        return result

    def filter_by_leave_novelty(self, novelty: str) -> List[RuleData]:
        """
        Filtra reglas por tipo de ausencia (novelty).

        Tipos de ausencia disponibles:
        - 'sln': Suspensión temporal del contrato
        - 'ige': Incapacidad EPS
        - 'irl': Incapacidad por accidente de trabajo
        - 'lma': Licencia de Maternidad
        - 'lpa': Licencia de Paternidad
        - 'vco': Vacaciones Compensadas (Dinero)
        - 'vdi': Vacaciones Disfrutadas
        - 'vre': Vacaciones por Retiro
        - 'lr': Licencia remunerada
        - 'lnr': Licencia no Remunerada
        - 'lt': Licencia de Luto
        - 'p': Permisos no remunerados

        Uso:
            # Obtener solo incapacidades EPS
            incapacidades_eps = category.filter_by_leave_novelty('ige')

            # Obtener vacaciones disfrutadas
            vacaciones = category.filter_by_leave_novelty('vdi')

        Args:
            novelty: Código del tipo de ausencia

        Returns:
            Lista de RuleData con el tipo de ausencia especificado
        """
        return [rule for rule in self.rules if rule.leave_novelty == novelty]

    def get_leave_rules(self) -> List[RuleData]:
        """
        Obtiene solo las reglas que tienen ausencias asociadas.

        Uso:
            # Todas las reglas con ausencias
            leave_rules = category.get_leave_rules()

        Returns:
            Lista de RuleData que tienen leave_id > 0
        """
        return [rule for rule in self.rules if rule.has_leave]

    def get_non_leave_rules(self) -> List[RuleData]:
        """
        Obtiene solo las reglas que NO tienen ausencias asociadas.

        Uso:
            # Reglas sin ausencias
            normal_rules = category.get_non_leave_rules()

        Returns:
            Lista de RuleData que no tienen ausencias
        """
        return [rule for rule in self.rules if not rule.has_leave]

    def get_leave_totals_by_novelty(self) -> Dict[str, Dict[str, float]]:
        """
        Obtiene totales agrupados por tipo de ausencia.

        Retorna un diccionario con:
        - 'novelty_code': {'total': X, 'count': Y, 'rule_codes': [...]}

        Uso:
            totals_by_type = category.get_leave_totals_by_novelty()

            # Ejemplo de resultado:
            # {
            #     'ige': {'total': 500000, 'count': 3, 'rule_codes': ['INCAP001', ...]},
            #     'vdi': {'total': 300000, 'count': 1, 'rule_codes': ['VAC001']}
            # }

            for novelty, data in totals_by_type.items():
                print(f"{novelty}: {data['total']} ({data['count']} reglas)")

        Returns:
            Diccionario con totales por tipo de ausencia
        """
        result = {}
        for rule in self.rules:
            if rule.has_leave and rule.leave_novelty:
                novelty = rule.leave_novelty
                if novelty not in result:
                    result[novelty] = {'total': 0.0, 'count': 0, 'rule_codes': []}

                result[novelty]['total'] += rule.total
                result[novelty]['count'] += 1
                result[novelty]['rule_codes'].append(rule.code)

        return result

    def to_dict(self) -> dict:
        """
        Convierte a diccionario (compatibilidad con código legacy).

        Uso:
            legacy_dict = category.to_dict()
        """
        return {
            'code': self.code,
            'total': self.total,
            'quantity': self.quantity,
            'rule_codes': self.rule_codes,
            'line_ids': self.line_ids,
        }

    def __repr__(self):
        return f"CategoryData(code='{self.code}', total={self.total}, rules={len(self.rules)})"


class CategoryCollection:
    """
    Colección de categorías con métodos de consulta y filtrado.

    Se comporta como un objeto ORM de Odoo pero para datos en memoria.

    Uso:
        categories = CategoryCollection()
        categories.add_category(cat_data)

        # Acceso directo por código
        heyrec = categories['HEYREC']
        total = heyrec.total

        # Filtrado
        prima_total = categories.get_total(
            category_codes=['HEYREC', 'COMISIONES'],
            base_prima=True
        )

        # Iterar
        for category in categories:
            print(category.code, category.total)
    """

    def __init__(self):
        self._categories: Dict[str, CategoryData] = {}

    def add_category(self, category: CategoryData):
        """
        Agrega o actualiza una categoría.

        Uso:
            collection.add_category(CategoryData(code='HEYREC'))
        """
        self._categories[category.code] = category

    def get(self, code: str, default: Optional[CategoryData] = None) -> Optional[CategoryData]:
        """
        Obtiene una categoría por código.

        Uso:
            heyrec = categories.get('HEYREC')
            if heyrec:
                total = heyrec.total
        """
        return self._categories.get(code, default)

    def __getitem__(self, code: str) -> CategoryData:
        """
        Acceso directo por código (lanza KeyError si no existe).

        Uso:
            heyrec = categories['HEYREC']
        """
        return self._categories[code]

    def __contains__(self, code: str) -> bool:
        """
        Verifica existencia de categoría.

        Uso:
            if 'HEYREC' in categories:
                ...
        """
        return code in self._categories

    def __getattr__(self, code: str) -> float:
        """
        Compatibilidad con reglas Python legacy: categories.CODE -> total.
        Retorna 0.0 si no existe la categoría.
        """
        category = self._categories.get(code)
        if category:
            return category.total
        return 0.0

    def __iter__(self):
        """
        Permite iterar sobre categorías.

        Uso:
            for category in categories:
                print(category.code)
        """
        return iter(self._categories.values())

    def keys(self):
        """Retorna códigos de categorías."""
        return self._categories.keys()

    def values(self):
        """Retorna objetos CategoryData."""
        return self._categories.values()

    def items(self):
        """Retorna tuplas (code, CategoryData)."""
        return self._categories.items()

    def get_total(self, category_codes: Optional[List[str]] = None, **filters) -> float:
        """
        Obtiene total de categorías opcionalmente filtrado por reglas.

        Uso:
            # Total de TODAS las categorías
            total_all = categories.get_total()

            # Total de categorías específicas
            total_variable = categories.get_total(
                category_codes=['HEYREC', 'COMISIONES', 'BONIFICACIONES']
            )

            # Total filtrado por base_prima
            total_prima = categories.get_total(
                category_codes=['HEYREC', 'COMISIONES'],
                base_prima=True
            )

        Args:
            category_codes: Lista de códigos de categorías (None = todas)
            **filters: Filtros a aplicar a reglas (base_prima, etc.)

        Returns:
            Suma de totales
        """
        total = 0.0

        categories_to_sum = (
            [self._categories[code] for code in category_codes if code in self._categories]
            if category_codes
            else self._categories.values()
        )

        if filters:
            for category in categories_to_sum:
                total += category.get_filtered_total(**filters)
        else:
            total = sum(cat.total for cat in categories_to_sum)

        return total

    def filter_categories(self, **filters) -> List[CategoryData]:
        """
        Filtra categorías según criterios.

        Uso:
            # Categorías con total > 0
            active = categories.filter_categories(min_total=0.01)

            # Categorías que contienen reglas con base_prima
            prima_cats = categories.filter_categories(
                custom=lambda cat: any(r.rule.base_prima for r in cat.rules if r.rule)
            )

        Returns:
            Lista de CategoryData que cumplen los filtros
        """
        result = []

        for category in self._categories.values():
            if 'min_total' in filters and category.total < filters['min_total']:
                continue

            if 'max_total' in filters and category.total > filters['max_total']:
                continue

            if 'has_rule' in filters and not category.has_rule(filters['has_rule']):
                continue

            if 'custom' in filters and callable(filters['custom']):
                if not filters['custom'](category):
                    continue

            result.append(category)

        return result

    def to_dict(self) -> Dict[str, dict]:
        """
        Convierte a diccionario (compatibilidad con código legacy).

        Uso:
            legacy_dict = categories.to_dict()
            # Retorna: {'HEYREC': {'total': 500000, ...}, ...}
        """
        return {code: cat.to_dict() for code, cat in self._categories.items()}

    def __repr__(self):
        return f"CategoryCollection(categories={len(self._categories)})"


def ensure_category_data(data) -> CategoryData:
    """
    Convierte dict legacy a CategoryData si es necesario.

    Uso en código de transición:
        cat_data = ensure_category_data(some_dict_or_object)
        total = cat_data.total  # Garantizado CategoryData
    """
    if isinstance(data, CategoryData):
        return data

    if isinstance(data, dict):
        return CategoryData(
            code=data.get('code', ''),
            total=data.get('total', 0.0),
            quantity=data.get('quantity', 0.0),
            rule_codes=data.get('rule_codes', []),
            line_ids=data.get('line_ids', [])
        )

    return CategoryData(code='UNKNOWN')


def ensure_rule_data(data) -> RuleData:
    """
    Convierte dict legacy a RuleData si es necesario.

    Uso en código de transición:
        rule_data = ensure_rule_data(some_dict_or_object)
        total = rule_data.total  # Garantizado RuleData
    """
    if isinstance(data, RuleData):
        return data

    if isinstance(data, dict):
        return RuleData(
            code=data.get('code', ''),
            total=data.get('total', 0.0),
            amount=data.get('amount', 0.0),
            quantity=data.get('quantity', 1.0),
            rate=data.get('rate', 100.0),
            category_id=data.get('category_id', 0),
            category_code=data.get('category_code', ''),
            rule_id=data.get('rule_id', 0),
            rule=data.get('rule'),
            has_leave=data.get('has_leave', False),
            payslip_id=data.get('payslip_id', 0),
            line_ids=data.get('line_ids', [])
        )

    return RuleData(code='UNKNOWN')


class RulesCollection:
    """
    Colección tipo-segura de reglas salariales con acceso ORM-like.

    Maneja localdict['rules'] como un objeto con métodos de filtrado integrados.
    Elimina la necesidad de trabajar con diccionarios anidados.

    ESTRUCTURA DE DATOS:
    - Internamente almacena RuleData objects
    - Acceso directo por código: collection.get('BASIC')
    - Iteración: for rule in collection
    - Filtrado: collection.filter_rules(base_prima=True)

    Uso:
        # Crear colección
        rules = RulesCollection()

        # Agregar reglas
        rules.add_rule(rule_data)

        # Acceso directo
        basic = rules.get('BASIC')
        if basic:
            total = basic.total

        # Filtrado
        prima_rules = rules.filter_rules(base_prima=True)
        total_prima = sum(r.total for r in prima_rules)

        # Iteración
        for rule in rules:
            print(f"{rule.code}: {rule.total}")

    VENTAJAS:
    - Tipo-seguro (0 isinstance checks)
    - Acceso directo a propiedades
    - Filtrado integrado
    - Métodos de agregación
    - Comportamiento similar a recordset de Odoo
    """

    __slots__ = ('_rules_by_code', '_rules_list')

    def __init__(self, rules: Optional[List[RuleData]] = None):
        """
        Inicializa colección de reglas.

        Args:
            rules: Lista opcional de RuleData
        """
        self._rules_by_code = {}
        self._rules_list = []

        if rules:
            for rule in rules:
                self.add_rule(rule)

    def add_rule(self, rule_data: RuleData):
        """
        Agrega una regla a la colección.

        Uso:
            rules.add_rule(rule_data)

        Args:
            rule_data: RuleData a agregar
        """
        if rule_data.code in self._rules_by_code:
            # Si ya existe, actualizar valores
            existing = self._rules_by_code[rule_data.code]
            existing.total += rule_data.total
            existing.amount += rule_data.amount
            existing.quantity += rule_data.quantity
            existing.line_ids.extend(rule_data.line_ids)
        else:
            self._rules_by_code[rule_data.code] = rule_data
            self._rules_list.append(rule_data)

    def get(self, code: str, default: Optional[RuleData] = None) -> Optional[RuleData]:
        """
        Obtiene regla por código.

        Uso:
            basic = rules.get('BASIC')
            if basic:
                total = basic.total

        Args:
            code: Código de la regla
            default: Valor por defecto si no existe

        Returns:
            RuleData o None/default
        """
        return self._rules_by_code.get(code, default)

    def __getitem__(self, code: str) -> RuleData:
        """
        Acceso tipo diccionario con excepción si no existe.

        Uso:
            basic = rules['BASIC']  # Lanza KeyError si no existe
        """
        if code not in self._rules_by_code:
            raise KeyError(f"Regla '{code}' no encontrada")
        return self._rules_by_code[code]

    def __contains__(self, code: str) -> bool:
        """
        Verifica si existe una regla.

        Uso:
            if 'BASIC' in rules:
                ...
        """
        return code in self._rules_by_code

    def __iter__(self):
        """
        Itera sobre todas las reglas.

        Uso:
            for rule in rules:
                print(rule.code)
        """
        return iter(self._rules_list)

    def __len__(self):
        """Cantidad de reglas."""
        return len(self._rules_list)

    def keys(self):
        """
        Retorna códigos de reglas.

        Uso:
            for code in rules.keys():
                print(code)
        """
        return self._rules_by_code.keys()

    def values(self):
        """
        Retorna objetos RuleData.

        Uso:
            for rule_data in rules.values():
                print(rule_data.total)
        """
        return self._rules_list

    def items(self):
        """
        Retorna tuplas (code, RuleData).

        Uso:
            for code, rule_data in rules.items():
                print(f"{code}: {rule_data.total}")
        """
        return self._rules_by_code.items()

    def filter_rules(self, **filters) -> List[RuleData]:
        """
        Filtra reglas según criterios.

        Uso:
            # Por campo de base
            prima_rules = rules.filter_rules(base_prima=True)

            # Por total mínimo
            high_rules = rules.filter_rules(min_total=100000)

            # Por categoría
            heyrec_rules = rules.filter_rules(category_code='HEYREC')

            # Filtro custom
            custom = rules.filter_rules(
                custom=lambda r: r.code.startswith('HEY')
            )

        Args:
            **filters: Criterios de filtrado

        Returns:
            Lista de RuleData que cumplen filtros
        """
        return [rule for rule in self._rules_list if rule.matches_filter(**filters)]

    def filter_by_category(self, category_code: str) -> List[RuleData]:
        """
        Filtra reglas por categoría.

        Uso:
            heyrec_rules = rules.filter_by_category('HEYREC')

        Args:
            category_code: Código de categoría

        Returns:
            Lista de RuleData de esa categoría
        """
        return [r for r in self._rules_list if r.category_code == category_code]

    def filter_by_leave_novelty(self, novelty: str) -> List[RuleData]:
        """
        Filtra reglas por tipo de ausencia.

        Uso:
            incapacidades = rules.filter_by_leave_novelty('ige')

        Args:
            novelty: Tipo de ausencia (ige, irl, vdi, etc.)

        Returns:
            Lista de RuleData con ese tipo de ausencia
        """
        return [r for r in self._rules_list if r.leave_novelty == novelty]

    def get_leave_rules(self) -> List[RuleData]:
        """
        Obtiene solo reglas con ausencias.

        Uso:
            leave_rules = rules.get_leave_rules()

        Returns:
            Lista de RuleData que tienen ausencias
        """
        return [r for r in self._rules_list if r.has_leave]

    def get_non_leave_rules(self) -> List[RuleData]:
        """
        Obtiene reglas sin ausencias.

        Uso:
            normal_rules = rules.get_non_leave_rules()

        Returns:
            Lista de RuleData sin ausencias
        """
        return [r for r in self._rules_list if not r.has_leave]

    def get_total(self, **filters) -> float:
        """
        Obtiene total de reglas filtradas.

        Uso:
            # Total de todas las reglas
            total = rules.get_total()

            # Total de reglas con base_prima=True
            total_prima = rules.get_total(base_prima=True)

            # Total de categoría específica
            total_heyrec = rules.get_total(category_code='HEYREC')

        Args:
            **filters: Criterios opcionales de filtrado

        Returns:
            Suma de totales
        """
        if filters:
            filtered = self.filter_rules(**filters)
            return sum(r.total for r in filtered)
        else:
            return sum(r.total for r in self._rules_list)

    def get_codes(self) -> List[str]:
        """
        Obtiene lista de códigos de reglas.

        Uso:
            codes = rules.get_codes()
            # ['BASIC', 'HEYREC_D', 'HEYREC_N', ...]

        Returns:
            Lista de códigos
        """
        return list(self._rules_by_code.keys())

    def to_dict(self) -> Dict[str, dict]:
        """
        Convierte a diccionario (compatibilidad legacy).

        Uso:
            legacy_dict = rules.to_dict()

        Returns:
            Diccionario {code: {total, amount, ...}}
        """
        result = {}
        for rule in self._rules_list:
            result[rule.code] = {
                'code': rule.code,
                'total': rule.total,
                'amount': rule.amount,
                'quantity': rule.quantity,
                'rate': rule.rate,
                'category_code': rule.category_code,
                'rule_id': rule.rule_id,
                'rule': rule.rule,
                'has_leave': rule.has_leave,
                'line_ids': rule.line_ids,
                'leave_id': rule.leave_id,
                'leave_novelty': rule.leave_novelty,
            }
        return result

    def __repr__(self):
        return f"RulesCollection({len(self._rules_list)} rules)"
