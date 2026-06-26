# Manual de Usuario — Nómina Electrónica DIAN
**Módulo:** Lavish: Nómina Electrónica DIAN  
**Versión Odoo:** 19.0

---

## Tabla de contenido

1. [¿Qué es la Nómina Electrónica?](#1-qué-es-la-nómina-electrónica)
2. [Cómo acceder al módulo](#2-cómo-acceder-al-módulo)
3. [Configuración inicial de la empresa](#3-configuración-inicial-de-la-empresa)
4. [Proceso documento individual (Por Empleado)](#4-proceso-documento-individual-por-empleado)
5. [Proceso en lote (Lotes Masivos)](#5-proceso-en-lote-lotes-masivos)
6. [Notas de ajuste](#6-notas-de-ajuste)
7. [Qué hacer cuando DIAN rechaza o da error](#7-qué-hacer-cuando-dian-rechaza-o-da-error)
8. [Enviar correo al empleado](#8-enviar-correo-al-empleado)
9. [Alertas y mensajes del sistema](#9-alertas-y-mensajes-del-sistema)
10. [Catálogos de configuración](#10-catálogos-de-configuración)

---

## 1. ¿Qué es la Nómina Electrónica?

La Nómina Electrónica es el documento que las empresas colombianas deben enviar a la DIAN cada vez que pagan a sus empleados, según la Resolución 000013 de 2021. Reemplaza los comprobantes de nómina en papel y queda registrado en la plataforma de la DIAN.

Este módulo toma las nóminas que ya procesó en Odoo, genera el archivo XML requerido por la DIAN, lo firma digitalmente y lo transmite. Usted solo necesita seguir los pasos del sistema.

---

## 2. Cómo acceder al módulo

En la barra superior de Odoo vaya a **Nómina**. Allí encontrará el menú **Nómina Electrónica** con tres opciones:

| Opción de menú | Para qué sirve |
|---|---|
| **Lotes Masivos** | Procesar todos los empleados de un periodo en conjunto |
| **Por Empleado** | Crear o consultar el documento de un empleado específico |
| **Configuración** | Catálogos DIAN (solo administradores) |

---

## 3. Configuración inicial de la empresa

> Esta sección la realiza el administrador del sistema una sola vez antes de comenzar a transmitir.

Vaya a **Ajustes → Usuarios y Empresas → Empresas**, abra su empresa y haga clic en la pestaña **Nómina Electrónica DIAN**.

### 3.1 Ambiente

| Campo | Qué poner |
|---|---|
| **Ambiente Producción** | Desactivado mientras está en pruebas con DIAN. Activar solo cuando DIAN haya habilitado la empresa para producción. |
| **Password Ambiente** | Contraseña del ambiente entregada por el proveedor tecnológico. |
| **Software ID** | Código del software registrado en DIAN. Lo entrega el proveedor. |
| **PIN Software** | PIN del software. Lo entrega el proveedor. |
| **ID Set Pruebas** | El `TestSetId` que la DIAN asigna para el proceso de habilitación. Solo aplica en ambiente de pruebas. |

### 3.2 Certificado digital

El certificado digital es el archivo `.p12` que firma los documentos antes de enviarlos a DIAN. Sin él no es posible enviar nada.

**Pasos:**
1. En el campo **Certificado Digital (.p12)** suba el archivo `.p12` que le entregó la entidad certificadora.
2. En **Clave Certificado** escriba la contraseña de ese archivo.
3. Haga clic en el botón **Extraer Certificado**.

El sistema extrae automáticamente el número serial, la fecha de vencimiento y el certificado público. Guarde el registro.

> **Importante:** Cuando el certificado esté a menos de 30 días de vencer, el sistema mostrará una alerta roja en cada documento. Renueve el certificado con anticipación.

### 3.3 Secuencias (numeración)

La DIAN exige que cada documento tenga un número con prefijo alfabético en mayúsculas (ejemplo: `NOMI0001`, `NOJA0001`).

En los campos **Secuencia Nómina Electrónica** y **Secuencia Nota Ajuste** seleccione las secuencias configuradas. Si no existen, pídale al administrador que las cree en **Ajustes → Técnico → Secuencias** con prefijo de 4 letras mayúsculas.

### 3.4 Repositorio de documentos

El campo **Repositorio Documentos** indica la carpeta del servidor donde se guardan los archivos XML y ZIP generados. Por defecto es `/tmp/nomina_electronica`. No cambie este valor a menos que el administrador del servidor lo indique.

### 3.5 Asociar reglas salariales con conceptos DIAN

> Haga esto una sola vez después de instalar el módulo.

En la misma pestaña **Nómina Electrónica DIAN** de la empresa, haga clic en **Asociar Conceptos DIAN**. El sistema mapea automáticamente las reglas salariales de Odoo con los conceptos del anexo técnico DIAN (sueldo, prima, cesantías, salud, pensión, etc.).

Si quiere revisar qué reglas quedaron sin concepto DIAN asignado, use el botón **Auditar Reglas DIAN**.

---

## 4. Proceso documento individual (Por Empleado)

Use esta opción cuando necesite generar el documento de un solo empleado o consultar/corregir un documento existente.

Vaya a **Nómina → Nómina Electrónica → Por Empleado**.

### 4.1 Crear un nuevo documento

Haga clic en **Nuevo**.

**Campos obligatorios:**

| Campo | Qué poner |
|---|---|
| **Empleado** | El empleado para quien se genera el documento. |
| **Período (Desde / Hasta)** | El rango de fechas del periodo de nómina (ej: 01/01/2025 – 31/01/2025). |
| **Versión Contrato** | El contrato activo del empleado en ese periodo. Se completa automáticamente si el empleado tiene nóminas procesadas. |
| **Fecha de Pago** | La fecha en que se pagó la nómina. |
| **Modo Provisiones** | Ver sección 4.2. |

Guarde el registro con el botón **Guardar** (ícono de nube).

### 4.2 Modo de provisiones

Este campo controla cómo se incluyen las provisiones de prestaciones sociales (prima, cesantías, intereses, vacaciones):

| Opción | Cuándo usarla |
|---|---|
| **Incluir Provisiones** | La empresa contabiliza mensualmente las prestaciones (régimen de causación). Las provisiones se reportan junto con los demás devengados. |
| **Excluir Provisiones** | La empresa solo reporta al momento del pago real de la prestación. No se incluyen provisiones en el XML. |
| **Solo Provisiones** | Genera un documento únicamente con las provisiones, sin otros devengados ni deducciones. |

> Si no está seguro, consulte con su contador. La opción más común es **Incluir Provisiones**.

### 4.3 Consolidar las líneas

Después de guardar, haga clic en **Computar** (o **Confirmar**).

El sistema busca todas las nóminas del empleado en el periodo indicado, extrae los conceptos (devengados y deducciones) y los consolida en las pestañas del documento.

Revise que aparezcan las pestañas con datos:

- **Nóminas y Conceptos** → muestra Devengos, Deducciones, Seguridad Social, Provisiones
- **Días Trabajados** → días laborados en el periodo
- Los totales en la parte superior: **Total Devengados**, **Total Deducciones**, **Total Comprobante**

> Si el empleado tiene una liquidación de contrato en el periodo, el sistema lo detecta automáticamente y muestra un aviso azul en la parte superior del formulario.

### 4.4 Probar el XML antes de enviar (opcional pero recomendado)

Antes de enviar a DIAN, haga clic en **Test XML**. Se abre una ventana con el XML generado para ese documento. Esto le permite revisar la estructura y detectar errores sin enviar nada a la DIAN.

### 4.5 Confirmar el documento

Haga clic en **Confirmar**. El estado pasa a **En Espera** (amarillo en la barra de estado).

Revise los datos una vez más. Si necesita corregir algo, use el botón **Cancelar** y luego **Volver a Borrador**.

Cuando todo esté correcto, haga clic en **Marcar Hecho**. El estado pasa a **Hecho** (verde).

### 4.6 Enviar a DIAN

Con el documento en estado **Hecho**, haga clic en **Enviar a DIAN**.

El sistema:
1. Genera el XML definitivo con todos los datos
2. Lo firma digitalmente con el certificado de la empresa
3. Lo empaqueta en un archivo ZIP
4. Lo envía al proveedor tecnológico / DIAN
5. Registra la respuesta en la pestaña **DIAN** y en los **Logs**

El banner superior cambia según la respuesta:

| Banner | Qué significa |
|---|---|
| Azul: *"Documento pendiente de envío a DIAN"* | Aún no se ha enviado |
| Amarillo: *"Documento enviado. Pendiente validación DIAN"* | Enviado, esperando respuesta |
| Verde: *"Documento validado exitosamente por DIAN. CUNE: ..."* | Aprobado. El CUNE es el número único de identificación |
| Rojo: *"Error DIAN: ..."* | Rechazado o error. Ver sección 7 |

### 4.7 Barra de estado y estados DIAN

La barra superior del documento muestra el **Estado** del documento en Odoo:

```
Borrador → En Espera → Hecho
```

El campo **Estado DIAN** (en la ficha derecha) muestra el estado ante la DIAN:

| Estado DIAN | Color | Significado |
|---|---|---|
| Por Notificar | Gris | No enviado aún |
| Por Validar | Amarillo | Enviado, esperando respuesta de DIAN |
| Exitoso | Verde | Aceptado por DIAN |
| Rechazado | Rojo | Rechazado por DIAN |
| Error | Rojo | Error técnico en el envío |

### 4.8 Pestaña DIAN

En la pestaña **DIAN** del formulario encontrará:

- **CUNE**: código único del documento validado
- **Consultar en DIAN**: enlace directo al portal DIAN para verificar el documento
- **ZipKey**: identificador del paquete enviado
- **Respuesta DIAN**: mensaje de respuesta del proveedor/DIAN
- **Descargar XML**: botones para descargar el XML enviado, el XML de respuesta y el ZIP

### 4.9 Smart buttons (botones en la esquina superior)

| Botón | Para qué sirve |
|---|---|
| **Nóminas** (número) | Ver las nóminas de Odoo que se usaron para consolidar este documento |
| **Ajustes** (número) | Ver las notas de ajuste creadas a partir de este documento |
| **Logs** (número) | Ver el historial completo de envíos, respuestas y errores |

---

## 5. Proceso en lote (Lotes Masivos)

Use esta opción al final de cada periodo para procesar todos los empleados de la empresa al mismo tiempo.

Vaya a **Nómina → Nómina Electrónica → Lotes Masivos → Nuevo**.

### 5.1 Crear el lote

Llene los campos:

| Campo | Qué poner |
|---|---|
| **Nombre** | Nombre descriptivo del lote (ej: "Nómina Enero 2025") |
| **Desde / Hasta** | Fechas del periodo |
| **Modo Provisiones** | Igual que en documento individual (ver sección 4.2) |

Guarde el registro.

### 5.2 Los 4 pasos del lote

La pantalla del lote muestra un **indicador de 4 pasos** con su estado (gris = pendiente, amarillo = en proceso, verde = completado):

---

**Paso 1 — Generar Nóminas**

Haga clic en **Generar Nóminas**. Se abre un asistente donde puede:
- Seleccionar empleados específicos, o
- Generar para todos los empleados de la empresa en el periodo

El sistema crea un documento EDI individual por cada empleado seleccionado.

---

**Paso 2 — Consolidar Líneas**

Haga clic en **Consolidar Líneas**. El sistema recorre todos los documentos del lote y consolida los conceptos de cada empleado desde sus nóminas del periodo.

Al terminar, el indicador del paso 2 se vuelve verde.

---

**Paso 3 — Confirmar Todas**

Haga clic en **Confirmar Todas**. Todos los documentos pasan a estado **Hecho** y quedan listos para envío.

---

**Paso 4 — Validar DIAN**

Haga clic en **Validar DIAN**.

Antes de enviar, el sistema revisa que todos los documentos tengan los datos mínimos requeridos (NIT empresa, documento empleado, dirección, contrato, sueldo). Si encuentra datos faltantes, muestra un aviso con el listado de problemas.

Puede:
- **Corregir los datos** faltantes y volver a intentar, o
- **Forzar Envío** si los datos faltantes no son críticos

Para enviar solo algunos documentos del lote (no todos), use el botón **Envío Selectivo**.

---

**Cerrar Lote**

Una vez que todos los documentos estén enviados, haga clic en **Cerrar Lote** para marcar el lote como completado.

---

**Reiniciar Lote**

Si necesita empezar de cero (por ejemplo, si el periodo cambió o hubo un error masivo), use **Reiniciar Lote**. Esto elimina todos los documentos del lote. El sistema pide confirmación antes de hacerlo.

---

## 6. Notas de ajuste

Una nota de ajuste corrige un documento que ya fue **validado por DIAN** (estado DIAN: Exitoso). Hay dos tipos:

| Tipo | Cuándo usarlo |
|---|---|
| **Reemplazar** | Corrección de valores (montos, conceptos). El documento de ajuste debe contener TODOS los conceptos, no solo los que cambiaron. |
| **Eliminar** | Anulación completa del documento. Los valores van en cero. |

### 6.1 Crear nota de ajuste tipo Reemplazar

1. Abra el documento original (estado DIAN: **Exitoso**)
2. Haga clic en **Crear Nota de Ajuste**

El sistema crea automáticamente una copia del documento en borrador con:
- **Nota de Ajuste** activado
- **Tipo de Nota**: Reemplazar
- **CUNE Anterior**: el CUNE del documento original (requerido por DIAN)

3. Edite los valores que necesita corregir en las líneas de devengados o deducciones
4. Siga el mismo proceso normal: **Confirmar → Marcar Hecho → Enviar a DIAN**

### 6.2 Ajuste solo de datos del empleado

Si el empleado cambió de nombre, documento o datos bancarios y necesita reportarlo sin cambiar los valores financieros:

1. Abra el documento original (estado DIAN: **Exitoso**)
2. Haga clic en **Ajuste Datos Empleado**

Genera una nota de ajuste con los mismos montos del original, pero con los datos actualizados del empleado.

### 6.3 Ajuste parcial

Si solo necesita cambiar algunos conceptos específicos:

1. Abra el documento original (estado DIAN: **Exitoso**)
2. Haga clic en **Ajuste Parcial**

Se abre un asistente donde puede seleccionar exactamente qué conceptos modificar y con qué valores.

### 6.4 Ver la cadena de ajustes

El smart button **Ajustes** en la esquina superior muestra todos los ajustes relacionados con un documento. La pestaña **Historial de Ajustes** también lista las notas de ajuste creadas a partir del documento actual.

> **Regla DIAN:** El documento original debe estar **Exitoso** en DIAN antes de poder crear una nota de ajuste. La DIAN no acepta ajustes sobre documentos que no haya validado.

---

## 7. Qué hacer cuando DIAN rechaza o da error

Cuando el estado DIAN es **Rechazado** o **Error**, aparece un banner rojo con el mensaje de la DIAN y tres botones:

### Botón "Reintentar con Comparación"

Abre un asistente que muestra una comparación entre los valores actuales del documento y los valores enviados anteriormente. Útil para identificar qué cambió antes de reenviar. Si el documento ya tiene un ZipKey, también consulta el estado directamente en DIAN.

### Botón "Consultar Estado DIAN"

Consulta directamente en la DIAN el estado del documento usando el ZipKey. Aparece solo si el documento fue enviado (tiene ZipKey). Úselo para confirmar si DIAN tiene el documento aunque la respuesta automática haya fallado.

### Botón "Recuperar y Limpiar"

Resetea el estado DIAN a **Por Notificar** y marca el documento como autorizado para reenvío. Úselo cuando:
- Quiere corregir los datos del documento y enviarlo de nuevo
- El rechazo fue por un problema de datos que ya corrigió

**Después de usar Recuperar:** corrija el problema, vuelva a confirmar el documento (**Computar** si necesita reconsolidar, luego **Marcar Hecho**) y envíe nuevamente.

### Entender el mensaje de rechazo

La DIAN devuelve códigos de rechazo como `NIE024`, `NIE069`, `92`, etc. El sistema busca automáticamente en el **Glosario de Reglas DIAN** la explicación y solución para cada código. Puede consultarlo manualmente en:

**Nómina → Nómina Electrónica → Configuración → Glosario Reglas DIAN**

Busque el código en la lista y lea la columna **Solución**.

Los rechazos más comunes y su causa:

| Código | Causa frecuente | Solución |
|---|---|---|
| `92` | La empresa no está habilitada en DIAN | Completar el proceso de habilitación en el portal DIAN |
| `NIE024` | Error en el cálculo del CUNE | Los totales tienen más de 2 decimales. Revisar montos |
| `NIE033` | NIT con guiones o dígito de verificación | Configurar el NIT sin guiones ni DV en la empresa |
| `NIE069` | Faltan días trabajados | El documento no tiene línea de días laborados |
| `NIE070` | Falta el sueldo básico | El documento no tiene línea de sueldo básico (BASIC) |
| `NIE161/163` | Porcentaje o valor de salud incorrecto | Verificar que la deducción de salud sea el 4% del devengado |
| `NIE164/166` | Porcentaje o valor de pensión incorrecto | Verificar que la deducción de pensión sea el 4% del devengado |
| `NIAE191a` | Documento a reemplazar no encontrado en DIAN | El documento original aún no está Exitoso en DIAN |
| `NIAE010` | Prefijo de la secuencia inválido | La secuencia debe tener prefijo de 4 letras mayúsculas |

---

## 8. Enviar correo al empleado

Cuando el documento está en estado DIAN **Exitoso**, puede enviarle al empleado su comprobante de nómina electrónica por correo.

Haga clic en el botón **Enviar Correo** (ícono de sobre). El sistema envía el correo usando la plantilla configurada y deja registro en el chatter del documento.

---

## 9. Alertas y mensajes del sistema

El formulario puede mostrar avisos en la parte superior según la situación:

| Aviso | Qué significa |
|---|---|
| **Rojo: "CERTIFICADO VENCIDO"** | El certificado digital de la empresa está vencido. No se puede enviar hasta renovarlo. |
| **Rojo: "El certificado digital vence en X días"** | El certificado vence pronto. Renuévelo antes de esa fecha. |
| **Amarillo: "Alerta Provisiones"** | Una o más líneas de devengados tienen valor negativo. DIAN no acepta valores negativos. Revise el modo de provisiones. |
| **Azul: "Liquidación de contrato"** | El contrato del empleado termina dentro del periodo. El documento se trata como liquidación. |

---

## 10. Catálogos de configuración

Accesibles desde **Nómina → Nómina Electrónica → Configuración**. Son tablas de referencia que carga el módulo automáticamente. No necesita modificarlos a menos que la DIAN actualice su anexo técnico.

| Catálogo | Contenido |
|---|---|
| **Reglas Devengado** | Conceptos de devengados reconocidos por DIAN (Sueldo, Prima, Cesantías, Horas Extra, etc.) |
| **Reglas Deducción** | Conceptos de deducciones reconocidos por DIAN (Salud, Pensión, Retención en la Fuente, etc.) |
| **Métodos de Pago** | Formas en que se realiza el pago (transferencia, efectivo, cheque, etc.) |
| **Formas de Pago** | Clasificación DIAN del tipo de pago |
| **Tipos de Nota** | Tipos de nota de ajuste: 1 = Reemplazar, 2 = Eliminar |
| **Glosario Reglas DIAN** | Códigos de rechazo DIAN con su descripción y solución sugerida |

---

## Preguntas frecuentes

**¿Puedo enviar el documento si la nómina del empleado no está cerrada?**  
No. El sistema solo toma nóminas en estado **Hecho** o **Pagado**. Cierre la nómina primero.

**¿Qué pasa si el empleado tiene varias nóminas en el mismo periodo?**  
El sistema las consolida todas automáticamente en un solo documento EDI.

**¿Puedo modificar las líneas de devengados manualmente?**  
Solo en estado Borrador o En Espera, y únicamente en líneas informativas. Las líneas normales se generan desde la nómina. Si los valores están mal, corrija la nómina original y vuelva a computar.

**¿Puedo reenviar un documento ya Exitoso?**  
Sí, pero solo activando el campo **Autorizar Reenvío** en la pestaña DIAN. Sin embargo, en producción esto puede generar duplicados. Consulte con DIAN antes de reenviar un documento Exitoso.

**El lote quedó a mitad de proceso. ¿Puedo continuarlo?**  
Sí. Los pasos del lote guardan su progreso. Puede retomar desde donde quedó: si el paso 2 ya está verde, solo falta continuar desde el paso 3.

**¿Por qué aparece "Documento enviado. Pendiente validación DIAN" durante mucho tiempo?**  
La DIAN puede tardar minutos o incluso horas en procesar dependiendo de la carga del sistema. Use el botón **Consultar Estado** para verificar manualmente. Si pasaron más de 24 horas, use **Consultar Estado DIAN** con el ZipKey.
