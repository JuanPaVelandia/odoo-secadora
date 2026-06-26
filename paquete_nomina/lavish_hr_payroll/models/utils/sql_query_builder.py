# -*- coding: utf-8 -*-
"""
Utilidad para construir queries SQL base con filtros esenciales usando psycopg2.sql
Sigue mejores prácticas Odoo 19: SQL seguro con parámetros
"""

from psycopg2 import sql
from typing import Dict, List, Optional, Tuple, Any
from datetime import date
import logging

_logger = logging.getLogger(__name__)


class SQLQueryBuilder:
    """
    Builder para construir queries SQL de forma segura usando psycopg2.sql.
    
    Proporciona métodos para construir queries base con filtros esenciales
    (company_id, employee_id, contract_id, date_from, date_to, states).
    """
    
    def __init__(self, cr):
        """
        Args:
            cr: Cursor de Odoo (self.env.cr)
        """
        self.cr = cr
        self._params = {}
        self._where_clauses = []
        self._joins = []
        self._select_fields = []
        self._group_by = []
        self._order_by = []
    
    def add_base_filters(
        self,
        company_id: Optional[int] = None,
        employee_id: Optional[int] = None,
        contract_id: Optional[int] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        states: Optional[List[str]] = None,
        exclude_payslip_id: Optional[int] = None,
        table_alias: str = 'HP'
    ) -> 'SQLQueryBuilder':
        """
        Agrega filtros base esenciales a la query.
        
        Args:
            company_id: ID de compañía (multi-compañía)
            employee_id: ID de empleado
            contract_id: ID de contrato
            date_from: Fecha inicial
            date_to: Fecha final
            states: Estados de nómina (default: ['done', 'paid'])
            exclude_payslip_id: ID de nómina a excluir
            table_alias: Alias de la tabla principal (default: 'HP')
        
        Returns:
            self para method chaining
        """
        if company_id:
            param_key = 'company_id'
            self._where_clauses.append(
                sql.SQL("{} = %({})s").format(
                    sql.Identifier(table_alias, 'company_id'),
                    sql.Identifier(param_key)
                )
            )
            self._params[param_key] = company_id
        
        if employee_id:
            param_key = 'employee_id'
            self._where_clauses.append(
                sql.SQL("{} = %({})s").format(
                    sql.Identifier(table_alias, 'employee_id'),
                    sql.Identifier(param_key)
                )
            )
            self._params[param_key] = employee_id
        
        if contract_id:
            param_key = 'contract_id'
            self._where_clauses.append(
                sql.SQL("{} = %({})s").format(
                    sql.Identifier(table_alias, 'contract_id'),
                    sql.Identifier(param_key)
                )
            )
            self._params[param_key] = contract_id
        
        if date_from:
            param_key = 'date_from'
            self._where_clauses.append(
                sql.SQL("{} >= %({})s").format(
                    sql.Identifier(table_alias, 'date_from'),
                    sql.Identifier(param_key)
                )
            )
            self._params[param_key] = date_from
        
        if date_to:
            param_key = 'date_to'
            self._where_clauses.append(
                sql.SQL("{} <= %({})s").format(
                    sql.Identifier(table_alias, 'date_to'),
                    sql.Identifier(param_key)
                )
            )
            self._params[param_key] = date_to
        
        if states:
            states_tuple = tuple(states) if isinstance(states, (list, tuple)) else (states,)
            param_key = 'states'
            self._where_clauses.append(
                sql.SQL("{} IN %({})s").format(
                    sql.Identifier(table_alias, 'state'),
                    sql.Identifier(param_key)
                )
            )
            self._params[param_key] = states_tuple
        else:
            # Default states
            param_key = 'states'
            self._where_clauses.append(
                sql.SQL("{} IN %({})s").format(
                    sql.Identifier(table_alias, 'state'),
                    sql.Identifier(param_key)
                )
            )
            self._params[param_key] = ('done', 'paid')
        
        if exclude_payslip_id:
            param_key = 'exclude_payslip_id'
            self._where_clauses.append(
                sql.SQL("{} != %({})s").format(
                    sql.Identifier(table_alias, 'id'),
                    sql.Identifier(param_key)
                )
            )
            self._params[param_key] = exclude_payslip_id
        
        return self
    
    def add_date_range_filter(
        self,
        date_field: str,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        table_alias: str = ''
    ) -> 'SQLQueryBuilder':
        """
        Agrega filtro de rango de fechas a un campo específico.
        
        Args:
            date_field: Nombre del campo de fecha (ej: 'date', 'date_from')
            date_from: Fecha inicial
            date_to: Fecha final
            table_alias: Alias de la tabla (opcional)
        
        Returns:
            self para method chaining
        """
        if date_from:
            param_key = f'{date_field}_from'
            if table_alias:
                self._where_clauses.append(
                    sql.SQL("{} >= %({})s").format(
                        sql.Identifier(table_alias, date_field),
                        sql.Identifier(param_key)
                    )
                )
            else:
                self._where_clauses.append(
                    sql.SQL("{} >= %({})s").format(
                        sql.Identifier(date_field),
                        sql.Identifier(param_key)
                    )
                )
            self._params[param_key] = date_from
        
        if date_to:
            param_key = f'{date_field}_to'
            if table_alias:
                self._where_clauses.append(
                    sql.SQL("{} <= %({})s").format(
                        sql.Identifier(table_alias, date_field),
                        sql.Identifier(param_key)
                    )
                )
            else:
                self._where_clauses.append(
                    sql.SQL("{} <= %({})s").format(
                        sql.Identifier(date_field),
                        sql.Identifier(param_key)
                    )
                )
            self._params[param_key] = date_to
        
        return self
    
    def add_join(
        self,
        join_type: str,
        table: str,
        alias: str,
        condition: str
    ) -> 'SQLQueryBuilder':
        """
        Agrega un JOIN a la query.
        
        Args:
            join_type: Tipo de join ('INNER', 'LEFT', 'RIGHT', 'FULL')
            table: Nombre de la tabla
            alias: Alias de la tabla
            condition: Condición del JOIN (ej: 'ON T1.id = T2.parent_id')
        
        Returns:
            self para method chaining
        """
        join_sql = sql.SQL("{} JOIN {} AS {} {}").format(
            sql.SQL(join_type),
            sql.Identifier(table),
            sql.Identifier(alias),
            sql.SQL(condition)
        )
        self._joins.append(join_sql)
        return self
    
    def add_where(self, condition: str, value: Any = None) -> 'SQLQueryBuilder':
        """
        Agrega una condición WHERE personalizada.
        
        Args:
            condition: Condición SQL (puede incluir %s para parámetros)
            value: Valor del parámetro (opcional)
        
        Returns:
            self para method chaining
        """
        if value is not None:
            # Si hay valor, usar parámetro nombrado
            param_key = f'custom_{len(self._params)}'
            self._params[param_key] = value
            # Reemplazar %s con %(param_key)s
            condition = condition.replace('%s', f'%({param_key})s')
            self._where_clauses.append(sql.SQL(condition))
        else:
            # Sin valor, usar condición tal cual
            self._where_clauses.append(sql.SQL(condition))
        
        return self
    
    def add_group_by(self, *fields: str) -> 'SQLQueryBuilder':
        """
        Agrega campos para GROUP BY.
        
        Args:
            *fields: Nombres de campos o expresiones SQL (pueden incluir punto, ej: 'HSRC.code')
        
        Returns:
            self para method chaining
        """
        for field in fields:
            # Si tiene punto, dividir en partes
            if '.' in field:
                parts = field.split('.')
                self._group_by.append(sql.Identifier(*parts))
            else:
                self._group_by.append(sql.Identifier(field))
        return self
    
    def add_order_by(self, *fields: str, desc: bool = False) -> 'SQLQueryBuilder':
        """
        Agrega campos para ORDER BY.
        
        Args:
            *fields: Nombres de campos (pueden incluir punto, ej: 'HSRC.code')
            desc: Si True, ordena descendente
        
        Returns:
            self para method chaining
        """
        for field in fields:
            # Si tiene punto, dividir en partes
            if '.' in field:
                parts = field.split('.')
                field_ident = sql.Identifier(*parts)
            else:
                field_ident = sql.Identifier(field)
            
            order = sql.SQL("{} DESC").format(field_ident) if desc else field_ident
            self._order_by.append(order)
        return self
    
    def build_select(
        self,
        select_fields: List[str],
        from_table: str,
        from_alias: str = ''
    ) -> Tuple[sql.SQL, Dict[str, Any]]:
        """
        Construye la query SELECT completa.
        
        Args:
            select_fields: Lista de campos a seleccionar
            from_table: Tabla principal
            from_alias: Alias de la tabla principal
        
        Returns:
            Tuple (query SQL compilada, parámetros)
        """
        # SELECT
        select_parts = [sql.SQL("SELECT")]
        # Manejar campos con alias (ej: "HLT.code AS leave_type_code")
        select_fields_sql = []
        for field in select_fields:
            if ' AS ' in field.upper():
                # Campo con alias: dividir y construir correctamente
                parts = field.split(' AS ', 1)
                field_expr = sql.SQL(parts[0].strip())
                alias = sql.Identifier(parts[1].strip())
                select_fields_sql.append(sql.SQL("{} AS {}").format(field_expr, alias))
            else:
                # Campo simple: usar tal cual
                select_fields_sql.append(sql.SQL(field))
        
        select_parts.append(sql.SQL(", ").join(select_fields_sql))
        
        # FROM
        if from_alias:
            from_part = sql.SQL("FROM {} AS {}").format(
                sql.Identifier(from_table),
                sql.Identifier(from_alias)
            )
        else:
            from_part = sql.SQL("FROM {}").format(sql.Identifier(from_table))
        
        # JOINs
        query_parts = [select_parts[0], select_parts[1], from_part]
        if self._joins:
            query_parts.extend(self._joins)
        
        # WHERE
        if self._where_clauses:
            where_part = sql.SQL("WHERE {}").format(
                sql.SQL(" AND ").join(self._where_clauses)
            )
            query_parts.append(where_part)
        
        # GROUP BY
        if self._group_by:
            group_by_part = sql.SQL("GROUP BY {}").format(
                sql.SQL(", ").join(self._group_by)
            )
            query_parts.append(group_by_part)
        
        # ORDER BY
        if self._order_by:
            order_by_part = sql.SQL("ORDER BY {}").format(
                sql.SQL(", ").join(self._order_by)
            )
            query_parts.append(order_by_part)
        
        # Compilar query
        final_query = sql.SQL(" ").join(query_parts)
        
        # Convertir parámetros a formato compatible con psycopg2
        # psycopg2 acepta dict directamente cuando se usa con sql.SQL
        return final_query, self._params
    
    def reset(self) -> 'SQLQueryBuilder':
        """Resetea el builder para construir una nueva query."""
        self._params = {}
        self._where_clauses = []
        self._joins = []
        self._select_fields = []
        self._group_by = []
        self._order_by = []
        return self
    
    def get_params(self) -> Dict[str, Any]:
        """Retorna los parámetros acumulados."""
        return self._params.copy()


def build_base_payslip_query(
    cr,
    company_id: Optional[int] = None,
    employee_id: Optional[int] = None,
    contract_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    states: Optional[List[str]] = None,
    exclude_payslip_id: Optional[int] = None
) -> SQLQueryBuilder:
    """
    Función helper para construir query base de nóminas.
    
    Returns:
        SQLQueryBuilder configurado con filtros base
    """
    builder = SQLQueryBuilder(cr)
    builder.add_base_filters(
        company_id=company_id,
        employee_id=employee_id,
        contract_id=contract_id,
        date_from=date_from,
        date_to=date_to,
        states=states,
        exclude_payslip_id=exclude_payslip_id,
        table_alias='HP'
    )
    return builder


def build_base_leave_query(
    cr,
    employee_id: Optional[int] = None,
    contract_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    leave_type_codes: Optional[List[str]] = None,
    states: Optional[List[str]] = None,
    exclude_payslip_id: Optional[int] = None
) -> SQLQueryBuilder:
    """
    Función helper para construir query base de ausencias.
    
    Returns:
        SQLQueryBuilder configurado con filtros base para ausencias
    """
    builder = SQLQueryBuilder(cr)
    
    # JOINs base para ausencias
    builder.add_join(
        'INNER',
        'hr_leave',
        'HL',
        'ON HL.id = HLL.leave_id'
    )
    builder.add_join(
        'INNER',
        'hr_leave_type',
        'HLT',
        'ON HLT.id = HL.holiday_status_id'
    )
    
    # Filtros base
    if contract_id:
        builder.add_where('HL.contract_id = %s', contract_id)
    
    if employee_id:
        builder.add_where('HL.employee_id = %s', employee_id)
    
    if date_from or date_to:
        builder.add_date_range_filter('date', date_from, date_to, 'HLL')
    
    if states:
        states_tuple = tuple(states) if isinstance(states, (list, tuple)) else (states,)
        builder.add_where('HLL.state IN %s', states_tuple)
    else:
        builder.add_where("HLL.state IN ('paid', 'validate', 'validated')")
    
    if leave_type_codes:
        codes_tuple = tuple(leave_type_codes)
        builder.add_where('HLT.code IN %s', codes_tuple)
    
    if exclude_payslip_id:
        builder.add_where('HLL.payslip_id IS NULL OR HLL.payslip_id = %s', exclude_payslip_id)
    
    return builder
