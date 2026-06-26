# -*- coding: utf-8 -*-
"""
SQL Query Builder
=================

Builder con soporte para:
- CTEs (WITH clauses)
- ARRAY_AGG y otras agregaciones
- UNION / EXCEPT
- Subqueries
- Parametros seguros con psycopg2.sql
"""
from psycopg2 import sql
from typing import List, Dict, Any, Optional, Tuple, Union
from dataclasses import dataclass, field
from datetime import date
from .field_sets import TABLE_ALIASES, VALID_PAYSLIP_STATES, VALID_LEAVE_STATES


@dataclass
class CTEDefinition:
    """Definicion de un CTE (Common Table Expression)."""
    name: str
    query: str
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class JoinDefinition:
    """Definicion de un JOIN."""
    table: str
    alias: str
    condition: str
    join_type: str = 'INNER'  # INNER, LEFT, RIGHT, FULL


class SQLQueryBuilder:
    """
    Builder avanzado para consultas SQL.

    Uso basico:
        builder = SQLQueryBuilder()
        builder.select('HPL.id', 'HPL.total', 'HSR.code AS rule_code')
        builder.from_table('hr_payslip_line', 'HPL')
        builder.join('hr_salary_rule', 'HSR', 'HSR.id = HPL.salary_rule_id')
        builder.where('HPL.total > %(min_total)s', min_total=0)
        query, params = builder.build()

    Con CTE:
        builder = SQLQueryBuilder()
        builder.with_cte('payslips', '''
            SELECT id, contract_id FROM hr_payslip
            WHERE state IN %(states)s
        ''', states=('done', 'paid'))
        builder.select('p.id', 'p.contract_id')
        builder.from_table('payslips', 'p')
        query, params = builder.build()
    """

    def __init__(self):
        self.reset()

    def reset(self) -> 'SQLQueryBuilder':
        """Resetea el builder para nueva consulta."""
        self._ctes: List[CTEDefinition] = []
        self._select_fields: List[str] = []
        self._from_table: Optional[Tuple[str, str]] = None
        self._joins: List[JoinDefinition] = []
        self._where_conditions: List[str] = []
        self._group_by: List[str] = []
        self._having: List[str] = []
        self._order_by: List[str] = []
        self._limit: Optional[int] = None
        self._offset: Optional[int] = None
        self._params: Dict[str, Any] = {}
        self._param_counter: int = 0
        return self

    # =========================================================================
    # CTE (WITH) METHODS
    # =========================================================================

    def with_cte(self, name: str, query: str, **params) -> 'SQLQueryBuilder':
        """
        Agrega un CTE (Common Table Expression).

        Args:
            name: Nombre del CTE
            query: Query SQL del CTE
            **params: Parametros para el CTE

        Ejemplo:
            builder.with_cte('active_payslips', '''
                SELECT id, contract_id FROM hr_payslip
                WHERE state IN %(states)s AND date_from >= %(date_from)s
            ''', states=('done', 'paid'), date_from=date(2024, 1, 1))
        """
        self._ctes.append(CTEDefinition(name=name, query=query, params=params))
        self._params.update(params)
        return self

    # =========================================================================
    # SELECT METHODS
    # =========================================================================

    def select(self, *fields: str) -> 'SQLQueryBuilder':
        """
        Agrega campos al SELECT.

        Args:
            *fields: Campos a seleccionar (pueden incluir alias)

        Ejemplo:
            builder.select('HPL.id', 'HPL.total', 'HSR.code AS rule_code')
        """
        self._select_fields.extend(fields)
        return self

    def select_aggregate(self, func: str, field: str, alias: str) -> 'SQLQueryBuilder':
        """
        Agrega una funcion de agregacion.

        Args:
            func: Funcion (SUM, COUNT, AVG, MAX, MIN)
            field: Campo a agregar
            alias: Alias para el resultado

        Ejemplo:
            builder.select_aggregate('SUM', 'HPL.total', 'total_amount')
        """
        self._select_fields.append(f"{func}({field}) AS {alias}")
        return self

    def select_array_agg(self, field: str, alias: str,
                         order_by: Optional[str] = None,
                         distinct: bool = False) -> 'SQLQueryBuilder':
        """
        Agrega ARRAY_AGG para agrupar IDs u otros valores.

        Args:
            field: Campo a agregar
            alias: Alias para el array
            order_by: Ordenamiento opcional dentro del array
            distinct: Si usar DISTINCT

        Ejemplo:
            builder.select_array_agg('HPL.id', 'line_ids', order_by='HPL.id')
        """
        distinct_str = 'DISTINCT ' if distinct else ''
        order_str = f' ORDER BY {order_by}' if order_by else ''
        self._select_fields.append(f"ARRAY_AGG({distinct_str}{field}{order_str}) AS {alias}")
        return self

    def select_coalesce(self, field: str, default: Any, alias: str) -> 'SQLQueryBuilder':
        """
        Agrega COALESCE para valores por defecto.

        Ejemplo:
            builder.select_coalesce('HPL.amount', 0, 'amount')
        """
        param_name = self._generate_param_name('coalesce')
        self._params[param_name] = default
        self._select_fields.append(f"COALESCE({field}, %({param_name})s) AS {alias}")
        return self

    # =========================================================================
    # FROM & JOIN METHODS
    # =========================================================================

    def from_table(self, table: str, alias: Optional[str] = None) -> 'SQLQueryBuilder':
        """
        Define la tabla principal.

        Args:
            table: Nombre de la tabla
            alias: Alias opcional (usa TABLE_ALIASES si no se proporciona)
        """
        if alias is None:
            alias = TABLE_ALIASES.get(table, table[:3].upper())
        self._from_table = (table, alias)
        return self

    def join(self, table: str, alias: Optional[str], condition: str,
             join_type: str = 'INNER') -> 'SQLQueryBuilder':
        """
        Agrega un JOIN.

        Args:
            table: Tabla a unir
            alias: Alias para la tabla
            condition: Condicion de union
            join_type: Tipo de JOIN (INNER, LEFT, RIGHT)
        """
        if alias is None:
            alias = TABLE_ALIASES.get(table, table[:3].upper())
        self._joins.append(JoinDefinition(
            table=table, alias=alias, condition=condition, join_type=join_type
        ))
        return self

    def left_join(self, table: str, alias: Optional[str], condition: str) -> 'SQLQueryBuilder':
        """Shortcut para LEFT JOIN."""
        return self.join(table, alias, condition, 'LEFT')

    # =========================================================================
    # WHERE METHODS
    # =========================================================================

    def where(self, condition: str, **params) -> 'SQLQueryBuilder':
        """
        Agrega condicion WHERE.

        Args:
            condition: Condicion SQL (puede usar %(param)s)
            **params: Parametros para la condicion

        Ejemplo:
            builder.where('HPL.total > %(min_total)s', min_total=0)
        """
        self._where_conditions.append(condition)
        self._params.update(params)
        return self

    def where_in(self, field: str, values: Union[List, Tuple],
                 param_name: Optional[str] = None) -> 'SQLQueryBuilder':
        """
        Agrega condicion IN.

        Ejemplo:
            builder.where_in('HP.state', ['done', 'paid'])
        """
        if not values:
            # Lista vacia - condicion siempre falsa
            self._where_conditions.append('FALSE')
            return self

        if param_name is None:
            param_name = self._generate_param_name('in')

        self._where_conditions.append(f"{field} IN %({param_name})s")
        self._params[param_name] = tuple(values)
        return self

    def where_not_in(self, field: str, values: Union[List, Tuple],
                     param_name: Optional[str] = None) -> 'SQLQueryBuilder':
        """Agrega condicion NOT IN."""
        if not values:
            return self  # Lista vacia - no afecta

        if param_name is None:
            param_name = self._generate_param_name('not_in')

        self._where_conditions.append(f"{field} NOT IN %({param_name})s")
        self._params[param_name] = tuple(values)
        return self

    def where_date_range(self, field: str, date_from: date, date_to: date,
                         param_prefix: str = 'date') -> 'SQLQueryBuilder':
        """
        Agrega filtro de rango de fechas.

        Ejemplo:
            builder.where_date_range('HP.date_from', date(2024,1,1), date(2024,12,31))
        """
        from_param = f"{param_prefix}_from"
        to_param = f"{param_prefix}_to"
        self._where_conditions.append(f"{field} >= %({from_param})s")
        self._where_conditions.append(f"{field} <= %({to_param})s")
        self._params[from_param] = date_from
        self._params[to_param] = date_to
        return self

    def where_between(self, field: str, date_from: date, date_to: date) -> 'SQLQueryBuilder':
        """
        Agrega filtro BETWEEN para fechas.

        Ejemplo:
            builder.where_between('HLL.date', date(2024,1,1), date(2024,1,31))
        """
        param_from = self._generate_param_name('between_from')
        param_to = self._generate_param_name('between_to')
        self._where_conditions.append(f"{field} BETWEEN %({param_from})s AND %({param_to})s")
        self._params[param_from] = date_from
        self._params[param_to] = date_to
        return self

    def where_contract(self, contract_id: int, field: str = 'contract_id',
                       table_alias: Optional[str] = None) -> 'SQLQueryBuilder':
        """Filtro por contrato."""
        full_field = f"{table_alias}.{field}" if table_alias else field
        return self.where(f"{full_field} = %(contract_id)s", contract_id=contract_id)

    def where_contracts(self, contract_ids: List[int], field: str = 'contract_id',
                        table_alias: Optional[str] = None) -> 'SQLQueryBuilder':
        """Filtro por multiples contratos."""
        full_field = f"{table_alias}.{field}" if table_alias else field
        return self.where_in(full_field, contract_ids, 'contract_ids')

    def where_payslip_states(self, states: Tuple[str, ...] = VALID_PAYSLIP_STATES,
                             table_alias: str = 'HP') -> 'SQLQueryBuilder':
        """Filtro por estados de nomina."""
        return self.where_in(f"{table_alias}.state", states, 'payslip_states')

    def where_leave_states(self, states: Tuple[str, ...] = VALID_LEAVE_STATES,
                           table_alias: str = 'HLL') -> 'SQLQueryBuilder':
        """Filtro por estados de ausencia."""
        return self.where_in(f"{table_alias}.state", states, 'leave_states')

    def where_exclude_payslips(self, payslip_ids: List[int],
                               table_alias: str = 'HP') -> 'SQLQueryBuilder':
        """Excluir nominas especificas."""
        if payslip_ids:
            return self.where_not_in(f"{table_alias}.id", payslip_ids, 'exclude_payslip_ids')
        return self

    # =========================================================================
    # GROUP BY, HAVING, ORDER BY
    # =========================================================================

    def group_by(self, *fields: str) -> 'SQLQueryBuilder':
        """Agrega campos al GROUP BY."""
        self._group_by.extend(fields)
        return self

    def having(self, condition: str, **params) -> 'SQLQueryBuilder':
        """Agrega condicion HAVING."""
        self._having.append(condition)
        self._params.update(params)
        return self

    def order_by(self, *fields: str) -> 'SQLQueryBuilder':
        """Agrega campos al ORDER BY."""
        self._order_by.extend(fields)
        return self

    def limit(self, limit: int) -> 'SQLQueryBuilder':
        """Establece LIMIT."""
        self._limit = limit
        return self

    def offset(self, offset: int) -> 'SQLQueryBuilder':
        """Establece OFFSET."""
        self._offset = offset
        return self

    # =========================================================================
    # BUILD METHOD
    # =========================================================================

    def build(self) -> Tuple[str, Dict[str, Any]]:
        """
        Construye la query final.

        Returns:
            Tuple de (query_string, params_dict)
        """
        parts = []

        # CTEs
        if self._ctes:
            cte_parts = []
            for cte in self._ctes:
                cte_parts.append(f"{cte.name} AS (\n{cte.query}\n)")
            parts.append("WITH\n" + ",\n".join(cte_parts))

        # SELECT
        if not self._select_fields:
            raise ValueError("No se han definido campos SELECT")
        parts.append("SELECT\n    " + ",\n    ".join(self._select_fields))

        # FROM
        if not self._from_table:
            raise ValueError("No se ha definido tabla FROM")
        table, alias = self._from_table
        parts.append(f"FROM {table} AS {alias}")

        # JOINs
        for join in self._joins:
            parts.append(f"{join.join_type} JOIN {join.table} AS {join.alias} ON {join.condition}")

        # WHERE
        if self._where_conditions:
            parts.append("WHERE " + "\n  AND ".join(self._where_conditions))

        # GROUP BY
        if self._group_by:
            parts.append("GROUP BY " + ", ".join(self._group_by))

        # HAVING
        if self._having:
            parts.append("HAVING " + " AND ".join(self._having))

        # ORDER BY
        if self._order_by:
            parts.append("ORDER BY " + ", ".join(self._order_by))

        # LIMIT / OFFSET
        if self._limit is not None:
            parts.append(f"LIMIT {self._limit}")
        if self._offset is not None:
            parts.append(f"OFFSET {self._offset}")

        query = "\n".join(parts)
        return query, self._params.copy()

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def _generate_param_name(self, prefix: str) -> str:
        """Genera nombre unico para parametro."""
        self._param_counter += 1
        return f"{prefix}_{self._param_counter}"

    def clone(self) -> 'SQLQueryBuilder':
        """Crea una copia del builder."""
        new_builder = SQLQueryBuilder()
        new_builder._ctes = self._ctes.copy()
        new_builder._select_fields = self._select_fields.copy()
        new_builder._from_table = self._from_table
        new_builder._joins = self._joins.copy()
        new_builder._where_conditions = self._where_conditions.copy()
        new_builder._group_by = self._group_by.copy()
        new_builder._having = self._having.copy()
        new_builder._order_by = self._order_by.copy()
        new_builder._limit = self._limit
        new_builder._offset = self._offset
        new_builder._params = self._params.copy()
        new_builder._param_counter = self._param_counter
        return new_builder

    def debug(self) -> str:
        """Retorna la query formateada para debug."""
        query, params = self.build()
        return f"Query:\n{query}\n\nParams:\n{params}"

    # =========================================================================
    # JSONB TRANSLATABLE FIELD HELPERS (Odoo 17+)
    # =========================================================================

    @staticmethod
    def translatable_field(
        table_alias: str,
        field_name: str,
        alias: Optional[str] = None,
        default: Optional[str] = None,
        lang: str = 'es_CO',
        fallback_lang: str = 'en_US'
    ) -> str:
        """
        Genera SQL para extraer texto de un campo JSONB traducible (Odoo 17+).

        En Odoo 17, los campos traducibles se almacenan como JSONB:
        {"es_CO": "Departamento", "en_US": "Department"}

        Args:
            table_alias: Alias de la tabla (ej: 'dep', 'hlt', 'cat')
            field_name: Nombre del campo (ej: 'name')
            alias: Alias para el resultado (ej: 'department_name')
            default: Valor por defecto si es NULL (ej: 'Sin Departamento')
            lang: Idioma principal a extraer (default: 'es_CO')
            fallback_lang: Idioma de respaldo (default: 'en_US')

        Returns:
            SQL string para el campo

        Ejemplo:
            >>> SQLQueryBuilder.translatable_field('dep', 'name', 'department_name', 'Sin Departamento')
            "COALESCE(dep.name->>'es_CO', dep.name->>'en_US', 'Sin Departamento') AS department_name"

            >>> SQLQueryBuilder.translatable_field('hlt', 'name', 'type_name')
            "COALESCE(hlt.name->>'es_CO', hlt.name->>'en_US') AS type_name"
        """
        field_ref = f"{table_alias}.{field_name}"

        if default:
            expr = f"COALESCE({field_ref}->>'{lang}', {field_ref}->>'{fallback_lang}', '{default}')"
        else:
            expr = f"COALESCE({field_ref}->>'{lang}', {field_ref}->>'{fallback_lang}')"

        if alias:
            return f"{expr} AS {alias}"
        return expr

    @staticmethod
    def translatable_coalesce(
        *field_refs: Tuple[str, str],
        alias: Optional[str] = None,
        default: Optional[str] = None,
        lang: str = 'es_CO',
        fallback_lang: str = 'en_US'
    ) -> str:
        """
        Genera SQL para COALESCE de múltiples campos JSONB traducibles.

        Útil cuando se necesita tomar el primer valor no nulo de varios campos,
        como COALESCE(parent_category.name, category.name).

        Args:
            *field_refs: Tuplas de (table_alias, field_name)
            alias: Alias para el resultado
            default: Valor por defecto si todos son NULL
            lang: Idioma principal
            fallback_lang: Idioma de respaldo

        Ejemplo:
            >>> SQLQueryBuilder.translatable_coalesce(
            ...     ('cat_parent', 'name'), ('cat', 'name'),
            ...     alias='category_name'
            ... )
            "COALESCE(cat_parent.name->>'es_CO', cat_parent.name->>'en_US', cat.name->>'es_CO', cat.name->>'en_US') AS category_name"
        """
        parts = []
        for table_alias, field_name in field_refs:
            field_ref = f"{table_alias}.{field_name}"
            parts.append(f"{field_ref}->>'{lang}'")
            parts.append(f"{field_ref}->>'{fallback_lang}'")

        if default:
            parts.append(f"'{default}'")

        expr = f"COALESCE({', '.join(parts)})"

        if alias:
            return f"{expr} AS {alias}"
        return expr
