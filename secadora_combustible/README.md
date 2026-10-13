# Combustible (ACPM)

Módulo para Odoo 19 que lleva el ACPM comprado por **finca y campaña**, a
partir de las facturas de proveedor, sin tocar su contabilidad.

## Dos tipos de ACPM

- **Finca**: costo del cultivo. Cuenta *Diversos* (1425.06.01), finca
  (punto operativo) y campaña.
- **Logística**: combustible de un vehículo (camioneta). Se asigna el equipo
  de Mantenimiento marcado como **Vehículo** en su ficha.

## Cómo funciona

1. **Combustible → Compras de ACPM (facturas)**. Muestra las líneas de
   factura de proveedor; abre filtrado por las que parecen combustible
   (ACPM, diésel, gasolina) y las ya marcadas. Se activa **ACPM** en la línea
   (o se seleccionan varias y se usa *Marcar como ACPM de finca* o *de
   logística*), se revisan los **galones** (se proponen de la cantidad de la
   línea) y se escribe la **finca** o el **vehículo** según el tipo. La
   **campaña** se propone sola: la de Labores de Finca que contiene la fecha
   de la factura.
2. Al asignar la finca se corrige la **distribución analítica** de la línea:
   se pone la cuenta de la finca en el plan *Punto operativo* y se conserva lo
   demás (Cultivo de arroz, cosecha...). Si se borra la finca de la línea,
   también se quita de la analítica. En logística se quita la finca de la
   analítica si la había. Al marcar una línea que ya traía finca en la
   analítica, esa finca se propone sola. La columna *Analítica* indica si quedó. No se
   corrige cuando la finca no tiene cuenta analítica para la compañía de la
   factura o la fecha está bloqueada; en ese caso queda en falso para
   revisarla. El filtro *Finca con cuenta distinta de Diversos* señala las
   líneas de finca que contabilidad debería revisar.
3. **Combustible → Resumen por finca y campaña**: pivote de galones y valor
   (negativos en notas crédito), con gráfico y lista. Por defecto solo cuenta
   facturas publicadas. En la lista (y en *Compras registradas*) se cambian
   el tipo, la finca, la campaña, el vehículo y los galones directamente en
   la fila; seleccionando varias filas el cambio se aplica a todas (edición
   en bloque). Escribir un vehículo pone el tipo en logística y limpia la
   finca; escribir una finca pone el tipo en finca y limpia el vehículo.

Las mismas columnas (ACPM, Galones, Finca, Campaña) están disponibles como
columnas opcionales en las líneas del formulario de la factura.

## Lo que NO hace

- No cambia la cuenta contable ni el producto de la línea.
- No lleva inventario de tanque ni consumo por hora de máquina.

## Permisos

- Grupo **Combustible**: ve el menú y el resumen.
- Marcar y asignar líneas requiere además el rol de **Facturación**
  (se escribe sobre las líneas de la factura). Para ver facturas de varias
  empresas, activarlas todas en el selector de compañías.

## Dependencias

`account`, `maintenance` (vehículos), `bascula` (lugares/fincas con su cuenta
analítica) y `finca_labores` (campañas).
