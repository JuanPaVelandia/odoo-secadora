# Libros Contables Colombia

Este módulo implementa los libros contables requeridos por la normativa colombiana para Odoo.

## Descripción

El módulo `account_reports_colombia` extiende las funcionalidades del módulo base `account_reports` para implementar los siguientes libros contables según la normativa colombiana:

1. **Libro de Inventario**: Refleja de manera anual un detalle del inventario de bienes, derechos y obligaciones, correspondiente a un Balance General de manera detallada.

2. **Libro Diario**: Registra cronológicamente los movimientos diarios de cada una de las cuentas afectadas.

3. **Libro Mayor**: Resume por mes el saldo inicial, el movimiento y el saldo final de las cuentas.

4. **Diferencia en el Capital**: Muestra los cambios en el patrimonio, incluyendo las variaciones en el capital.

5. **Libro Auxiliar**: Detalla cronológicamente los hechos económicos registrados en los comprobantes de contabilidad.

## Requisitos

- Odoo 17.0
- Módulo `account_reports`

## Instalación

1. Copie el módulo `account_reports_colombia` en la carpeta de addons de Odoo.
2. Actualice la lista de módulos en Odoo.
3. Instale el módulo `account_reports_colombia`.

## Uso

Una vez instalado el módulo, podrá acceder a los libros contables colombianos desde el menú **Contabilidad > Informes > Libros Contables Colombia**.

### Libro de Inventario

El Libro de Inventario muestra un detalle del inventario de bienes, derechos y obligaciones de la empresa. Puede filtrar por fecha y ver el detalle de cada cuenta.

### Libro Diario

El Libro Diario registra cronológicamente los movimientos diarios de cada una de las cuentas afectadas. Puede filtrar por período y diarios.

### Libro Mayor

El Libro Mayor resume por mes el saldo inicial, el movimiento y el saldo final de las cuentas. Puede filtrar por período y diarios.

### Diferencia en el Capital

El reporte de Diferencia en el Capital muestra los cambios en el patrimonio, incluyendo las variaciones en el capital. Puede filtrar por período y ver el detalle de cada variación.

### Libro Auxiliar

El Libro Auxiliar detalla cronológicamente los hechos económicos registrados en los comprobantes de contabilidad. Puede filtrar por cuenta, período y diarios.

## Características Técnicas

El módulo implementa los siguientes modelos:

- `account.inventory.book.handler`: Implementa el Libro de Inventario.
- `account.journal.book.colombia.handler`: Implementa el Libro Diario.
- `account.ledger.book.colombia.handler`: Implementa el Libro Mayor.
- `account.capital.difference.handler`: Implementa el reporte de Diferencia en el Capital.
- `account.auxiliary.book.handler`: Implementa el Libro Auxiliar.

Todos estos modelos extienden la clase `account.report.custom.handler` para implementar las funcionalidades específicas de cada libro contable según la normativa colombiana.

## Cumplimiento Normativo

Este módulo ha sido desarrollado para cumplir con los requisitos establecidos en:

- Código de Comercio (artículos 50, 52 y 53)
- Decreto 2649 de 1993 (artículo 125)
- Estatuto Tributario
- Constitución Nacional (artículo 5)

## Soporte

Para cualquier consulta o soporte, por favor contacte al equipo de desarrollo.

## Licencia

Este módulo está licenciado bajo OPL-1.

---

Desarrollado por [Su Empresa] - 2025

