# -*- coding: utf-8 -*-
"""
Tipos de resultado para consultas SQL
=====================================

Dataclasses tipadas para resultados de consultas.
Esto proporciona autocompletado y validacion de tipos.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import date


@dataclass
class PayslipLineResult:
    """Resultado de una linea de nomina."""
    id: int
    slip_id: int
    total: float
    amount: float = 0.0
    quantity: float = 1.0
    rate: float = 100.0
    category_id: int = 0
    category_code: str = ''
    salary_rule_id: int = 0
    rule_code: str = ''
    rule_name: str = ''
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    leave_id: Optional[int] = None
    computation: Optional[Dict[str, Any]] = None

    @classmethod
    def from_row(cls, row: tuple, columns: List[str]) -> 'PayslipLineResult':
        """Crea instancia desde fila de cursor."""
        data = dict(zip(columns, row))
        return cls(
            id=data.get('id', 0),
            slip_id=data.get('slip_id', 0),
            total=float(data.get('total', 0) or 0),
            amount=float(data.get('amount', 0) or 0),
            quantity=float(data.get('quantity', 1) or 1),
            rate=float(data.get('rate', 100) or 100),
            category_id=data.get('category_id', 0),
            category_code=data.get('category_code', ''),
            salary_rule_id=data.get('salary_rule_id', 0),
            rule_code=data.get('rule_code', ''),
            rule_name=data.get('rule_name', ''),
            date_from=data.get('date_from'),
            date_to=data.get('date_to'),
            leave_id=data.get('leave_id'),
            computation=data.get('computation'),
        )


@dataclass
class LeaveLineResult:
    """Resultado de una linea de ausencia."""
    id: int
    leave_id: int
    date: date
    amount: float = 0.0
    state: str = ''
    days_payslip: float = 1.0
    leave_type_code: str = ''
    leave_type_novelty: str = ''
    contract_id: int = 0

    @classmethod
    def from_row(cls, row: tuple, columns: List[str]) -> 'LeaveLineResult':
        """Crea instancia desde fila de cursor."""
        data = dict(zip(columns, row))
        return cls(
            id=data.get('id', 0),
            leave_id=data.get('leave_id', 0),
            date=data.get('date'),
            amount=float(data.get('amount', 0) or 0),
            state=data.get('state', ''),
            days_payslip=float(data.get('days_payslip', 1) or 1),
            leave_type_code=data.get('leave_type_code', ''),
            leave_type_novelty=data.get('leave_type_novelty', ''),
            contract_id=data.get('contract_id', 0),
        )


@dataclass
class LeaveAccumulatedResult:
    """Resultado de acumulacion de ausencias por tipo."""
    leave_type_code: str
    days_count: int = 0
    total_amount: float = 0.0
    line_ids: List[int] = field(default_factory=list)
    novelty: Optional[str] = None
    unpaid: bool = False

    @classmethod
    def from_row(cls, row: tuple, columns: List[str]) -> 'LeaveAccumulatedResult':
        """Crea instancia desde fila de cursor."""
        data = dict(zip(columns, row))
        return cls(
            leave_type_code=data.get('leave_type_code', ''),
            days_count=int(data.get('days_count', 0) or 0),
            total_amount=float(data.get('total_amount', 0) or 0),
            line_ids=list(data.get('line_ids', []) or []),
            novelty=data.get('novelty'),
            unpaid=bool(data.get('unpaid', False)),
        )


@dataclass
class AccumulatedResult:
    """Resultado de acumulacion generica."""
    code: str
    total_amount: float = 0.0
    count: int = 0
    quantity: float = 0.0
    avg_rate: float = 100.0
    line_ids: List[int] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_row(cls, row: tuple, columns: List[str]) -> 'AccumulatedResult':
        """Crea instancia desde fila de cursor."""
        data = dict(zip(columns, row))
        return cls(
            code=data.get('code', data.get('rule_code', data.get('category_code', ''))),
            total_amount=float(data.get('total_amount', data.get('total', 0)) or 0),
            count=int(data.get('count', data.get('days_count', 0)) or 0),
            quantity=float(data.get('quantity', data.get('sum_quantity', 0)) or 0),
            avg_rate=float(data.get('avg_rate', 100) or 100),
            line_ids=list(data.get('line_ids', []) or []),
            metadata={k: v for k, v in data.items() if k not in [
                'code', 'rule_code', 'category_code', 'total_amount', 'total',
                'count', 'days_count', 'quantity', 'sum_quantity', 'avg_rate', 'line_ids'
            ]},
        )


@dataclass
class CategoryAccumulatedResult:
    """Resultado de acumulacion por categoria."""
    contract_id: int
    category_code: str
    rule_code: str
    rule_id: int = 0
    total_amount: float = 0.0
    amount: float = 0.0
    quantity: float = 0.0
    rate: float = 100.0
    line_ids: List[int] = field(default_factory=list)
    leave_id: Optional[int] = None
    leave_novelty: Optional[str] = None
    leave_liquidacion_value: Optional[str] = None

    @classmethod
    def from_row(cls, row: tuple, columns: List[str]) -> 'CategoryAccumulatedResult':
        """Crea instancia desde fila de cursor."""
        data = dict(zip(columns, row))
        return cls(
            contract_id=data.get('contract_id', 0),
            category_code=data.get('category_code', ''),
            rule_code=data.get('rule_code', ''),
            rule_id=data.get('rule_id', 0),
            total_amount=float(data.get('total_amount', 0) or 0),
            amount=float(data.get('amount', 0) or 0),
            quantity=float(data.get('quantity', 0) or 0),
            rate=float(data.get('rate', 100) or 100),
            line_ids=list(data.get('line_ids', []) or []),
            leave_id=data.get('leave_id'),
            leave_novelty=data.get('leave_novelty'),
            leave_liquidacion_value=data.get('leave_liquidacion_value'),
        )


