# Labores de Finca

Reemplaza las hojas de Google de la carpeta *Semilla / 2025-2026* (una hoja por
finca, la hoja de Maquinaria y el *Consolidado*). Es **control operativo**: no
genera asientos. Los pagos se siguen registrando en contabilidad y aquí solo se
descuentan del saldo.

## De la hoja a Odoo

| Hoja | Odoo |
|---|---|
| Consolidado › Parámetros: fincas, lotes, dueños | Configuración › Fincas y dueños / Lotes (`secadora.lugar`, `secadora.lote` de `bascula`) |
| Consolidado › Parámetros: trabajo por contrato y valor unitario | Configuración › Labores y tarifas (`finca.labor`, precargadas) |
| Consolidado › Parámetros: mtto maquinaria y valor unitario | Configuración › Topes de maquinaria (campo en la categoría de equipo) |
| Finca › Por contrato (bloques lote / trabajo / has / entre cuántos) | Registro › Labores por contrato (`finca.contrato`): una labor por lote, con sus operadores |
| Finca › Por jornales, Liquidador_jornales | Registro › Jornales (`finca.jornal`) |
| Maquinaria › Maquinaria | Registro › Trabajos de maquinaria (`finca.maquinaria.trabajo`); al confirmar crea un costo "Recursos Humanos" en el equipo |
| Maquinaria › Verificación | Aviso "supera el tope" en el trabajo y en la lista |
| Consolidado › Anticipos (JotForm) | Pagos de contabilidad (`account.payment`) con campaña de labores |
| Consolidado › Resumen total | Saldos › Saldos por dueño y operador (pivote) |
| Consolidado › Reporte | Saldos › Estado de cuenta (PDF) |

## Puesta en marcha

1. Instalar el módulo y dar el grupo *Usuario Labores* o *Administrador Labores*
   (Ajustes › Usuarios › Labores de Finca).
2. Configuración › Campañas: crear la campaña (ej. 2026-2027) con sus fechas.
   Las campañas no pueden solaparse: los pagos se asignan por fecha.
3. Configuración › Fincas y dueños: poner el **dueño** de cada finca (un
   contacto; ej. Lotes Luis → Luis Cubides, La Alianza → Finca La Alianza).
4. Configuración › Lotes: revisar que estén los lotes con sus hectáreas.
5. Revisar las tarifas precargadas y llenar los topes de maquinaria
   (Rastra 250.000, Encaladora 500.000, Fumigadora 350.000, Voleadora 250.000,
   Zorro 200.000, Sembradora 1.250.000, Tolvo 270.000, Cosechadora pequeña
   1.800.000 en 2025-2026).

## Cómo se arma el saldo

- **Trabajos**: labores por contrato, jornales y trabajos de maquinaria
  *confirmados*. El dueño se toma de la finca (o de la compañía del equipo) y se
  puede cambiar en cada registro.
- **Pagos**: pagos publicados (`in_process` o `paid`) con *Campaña de labores*.
  Al pagar a un contacto marcado como operador, el pago toma solo la campaña
  por su fecha y, si la compañía del pago es dueña de una finca, también el
  dueño. Ambos campos se pueden corregir en el pago (grupo "Labores de finca").
  Si el pago no es por labores, se borra la campaña.
- Un contacto queda marcado como operador al confirmar su primera labor. En ese
  momento sus pagos de la campaña ya registrados entran al saldo.
- **Saldo** = Trabajos − Pagos. Positivo: se le debe al operador.

Revisar en Saldos › Pagos a operadores el filtro *Labores sin dueño*: esos pagos
quedan en el saldo pero fuera de cualquier dueño.
