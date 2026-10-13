# Combustible (ACPM)

Módulo para Odoo 19 que lleva el ACPM comprado por **finca y campaña**, a
partir de las facturas de proveedor, sin tocar su contabilidad.

## Cómo funciona

1. **Combustible → Compras de ACPM (facturas)**. Muestra las líneas de
   factura de proveedor; abre filtrado por las que parecen combustible
   (ACPM, diésel, gasolina) y las ya marcadas. Se activa **ACPM** en la línea
   (o se seleccionan varias y se usa *Marcar como ACPM*), se revisan los
   **galones** (se proponen de la cantidad de la línea) y se escribe la
   **finca**. La **campaña** se propone sola: la de Labores de Finca que
   contiene la fecha de la factura.
2. Al asignar la finca se corrige la **distribución analítica** de la línea:
   se pone la cuenta de la finca en el plan *Punto operativo* y se conserva lo
   demás (Cultivo de arroz, cosecha...). La columna *Analítica* indica si
   quedó. No se corrige cuando la finca no tiene cuenta analítica para la
   compañía de la factura o la fecha está bloqueada; en ese caso queda en falso
   para revisarla.
3. **Combustible → Resumen por finca y campaña**: pivote de galones y valor
   (negativos en notas crédito), con gráfico y lista. Por defecto solo cuenta
   facturas publicadas. En la lista (y en *Compras registradas*) se cambian
   la finca, la campaña y los galones directamente en la fila; seleccionando
   varias filas el cambio se aplica a todas (edición en bloque).

Las mismas columnas (ACPM, Galones, Finca, Campaña) están disponibles como
columnas opcionales en las líneas del formulario de la factura.

## Lo que NO hace

- No cambia la cuenta contable ni el producto de la línea.
- No lleva inventario de tanque ni consumo por máquina.

## Permisos

- Grupo **Combustible**: ve el menú y el resumen.
- Marcar y asignar líneas requiere además el rol de **Facturación**
  (se escribe sobre las líneas de la factura). Para ver facturas de varias
  empresas, activarlas todas en el selector de compañías.

## Dependencias

`account`, `bascula` (lugares/fincas con su cuenta analítica) y
`finca_labores` (campañas).
