# Lavish: Nómina Electrónica DIAN

**Versión:** 19.0.1.0  
**Autor:** Lavish S.A.S — https://lavishsoft.co  
**Licencia:** OPL-1  
**Dependencias:** `hr`, `hr_holidays`, `hr_work_entry_holidays`, `hr_payroll`, `lavish_hr_employee`, `lavish_hr_payroll`

---

## ¿Qué hace este módulo?

Implementa el ciclo completo de **Nómina Electrónica DIAN** para Colombia (Resolución 000013 de 2021) dentro de Odoo 19. Toma las nóminas procesadas normalmente en Odoo (`hr.payslip`) y genera, firma digitalmente y transmite a la DIAN los documentos XML `NominaIndividual` y `NominaIndividualDeAjuste`.

Cubre:

- Generación del XML según anexo técnico DIAN
- Firma digital XAdES-EPES con certificado PKCS12
- Comunicación SOAP con el proveedor tecnológico / DIAN
- Gestión del ciclo de vida del documento (borrador → confirmado → enviado → validado)
- Notas de ajuste tipo Reemplazar y Eliminar
- Procesamiento en lotes masivos
- Consulta y reintento de estado DIAN
- Notificaciones por correo al empleado
- Glosario de códigos de rechazo DIAN con soluciones

---

## Estructura del menú

El módulo agrega el menú **Nómina Electrónica** dentro de **Nómina**:

```
Nómina
└── Nómina Electrónica
    ├── Lotes Masivos          (hr.payslip.edi.run)
    ├── Por Empleado           (hr.payslip.edi)
    └── Configuración
        ├── Métodos de Pago    (hr.payment.method.dian)
        ├── Formas de Pago     (hr.way.pay)
        ├── Tipos de Nota      (hr.type.note)
        ├── Reglas Devengado   (hr.accrued.rule)
        ├── Reglas Deducción   (hr.deduct.rule)
        └── Glosario Reglas DIAN (dian.rejection.glossary)
```

La configuración de la empresa está en:  
**Ajustes → Usuarios y Empresas → Empresas → [empresa] → pestaña "Nómina Electrónica DIAN"**

---

## Configuración inicial

### 1. Datos de la empresa

En la pestaña **Nómina Electrónica DIAN** de la empresa configurar:

| Campo | Descripción |
|---|---|
| Ambiente Producción | Desactivado = pruebas, Activado = producción |
| Password Ambiente | Contraseña del ambiente DIAN |
| Software ID | Código del software registrado en DIAN |
| PIN Software | PIN del software |
| ID Set Pruebas | TestSetId otorgado por DIAN para habilitación |
| Repositorio Documentos | Ruta local donde se guardan XML y ZIP (por defecto `/tmp/nomina_electronica`) |
| Secuencia Nómina Electrónica | Secuencia para numerar documentos (prefijo ALFABÉTICO en MAYÚSCULAS, ej: `NOMI`) |
| Secuencia Nota Ajuste | Secuencia para notas de ajuste (ej: `NOJA`) |

### 2. Certificado digital

En la misma pestaña:

1. Subir el archivo `.p12` en **Certificado Digital (.p12)**
2. Ingresar la contraseña en **Clave Certificado**
3. Hacer clic en **Extraer Certificado** — el sistema extrae automáticamente el serial, el PEM y la fecha de vencimiento

### 3. Asociar reglas salariales con conceptos DIAN

Botón **Asociar Conceptos DIAN** en la pestaña de la empresa. Mapea automáticamente las reglas salariales del módulo `lavish_hr_payroll` a los conceptos del anexo técnico DIAN (devengados y deducciones).

Para auditar reglas que tienen cuenta contable pero no tienen concepto DIAN asignado: botón **Auditar Reglas DIAN**.

### 4. Verificar catálogos

Ir a **Nómina → Nómina Electrónica → Configuración → Reglas Devengado** y **Reglas Deducción** — deben tener registros cargados (BASIC, PRIMA, CESANTIAS, Salud, FondoPension, etc.). Se cargan automáticamente al instalar el módulo.

---

## Flujo de trabajo estándar

### Documento individual (Por Empleado)

```
Nuevo → [Confirmar] → verify → [Hecho] → done → [Enviar a DIAN] → exitoso/rechazado
```

**Paso a paso:**

1. **Nómina → Nómina Electrónica → Por Empleado → Nuevo**
2. Seleccionar **Empleado**, **Periodo** (Desde / Hasta), **Fecha de Pago**
3. Configurar **Modo Provisiones**:
   - *Incluir*: reporta provisiones junto con devengados (recomendado cuando la empresa contabiliza por causación)
   - *Excluir*: omite provisiones (reportar solo al pagar la prestación real)
   - *Solo Provisiones*: genera un documento únicamente con provisiones
4. Guardar
5. Botón **Confirmar** → el sistema busca las nóminas del periodo del empleado, consolida líneas de devengados y deducciones, y pasa a estado **En Espera**
6. Revisar las pestañas **Devengados**, **Deducciones**, **Días Trabajados** y los totales
7. Botón **Vista Previa XML** (opcional) — genera el XML sin firma para revisar la estructura antes de enviar
8. Botón **Hecho** → estado **Hecho** (listo para envío)
9. Botón **Enviar a DIAN** → genera XML firmado, lo empaqueta en ZIP, lo envía por SOAP y registra la respuesta

**Estados del documento:**

| Estado | Descripción |
|---|---|
| Borrador | Recién creado, editable |
| En Espera | Confirmado, líneas consolidadas |
| Hecho | Listo para enviar a DIAN |
| Cancelado | Anulado internamente |

**Estados DIAN:**

| Estado DIAN | Descripción |
|---|---|
| Por Notificar | Aún no enviado |
| Por Validar | Enviado, pendiente de respuesta DIAN |
| Exitoso | Validado y aceptado por DIAN |
| Rechazado | Rechazado por DIAN (ver logs para causa) |
| Error | Error técnico en el envío |

---

### Lotes masivos

Para procesar grupos de empleados en un mismo periodo:

1. **Nómina → Nómina Electrónica → Lotes Masivos → Nuevo**
2. Configurar periodo, modo de provisiones y lote de nómina origen
3. Botón **Generar Por Empleados** (wizard) → seleccionar empleados → genera los EDIs individuales
4. Botón **Consolidar Todo** → ejecuta la consolidación en todos los documentos del lote
5. Botón **Confirmar Todo** → pasa todos a estado Hecho
6. Botón **Validar DIAN** → envía todos a DIAN con validación previa de datos faltantes

Si hay datos incompletos, aparece el wizard de advertencias con el detalle antes de continuar.

---

## Notas de ajuste

Se usan para corregir un documento ya validado por DIAN (`exitoso`).

### Tipo Reemplazar (type_note = '1')

Reemplaza el documento original completo con valores corregidos. El documento de ajuste lleva todos los conceptos, no solo los que cambiaron.

Desde el formulario de un documento **Exitoso**:  
→ Botón **Crear Ajuste** — genera una copia en borrador con `previous_cune` del original, lista para editar y enviar

### Tipo Eliminar (type_note = '2')

Elimina completamente el documento original. El XML se envía con valores en cero.

### Cadena de ajustes

Cada ajuste mantiene:
- `origin_edi_id` — apunta siempre al documento raíz de la cadena
- `parent_edi_id` — apunta al documento inmediatamente anterior
- El smart button **Cadena de Ajustes** muestra todos los documentos relacionados

---

## Consulta y reintento

Si un documento quedó en estado **Por Validar** o fue rechazado:

- **Consultar Estado DIAN** — consulta directamente en DIAN usando el `ZipKey` (requiere que el documento haya sido enviado)
- **Reintentar Envío** — muestra el wizard con comparación de valores antes de reenviar
- **Recuperar Nómina** — resetea el estado DIAN a *Por Notificar* para permitir correcciones y reenvío

---

## Logs

Cada documento mantiene un historial completo en la pestaña **Logs** (o botón smart **Logs**):

| Tipo de log | Cuándo se genera |
|---|---|
| Validación | Errores de datos antes del envío |
| Envío DIAN | Cada intento de envío |
| Respuesta DIAN | Respuesta del proveedor / DIAN |
| Consulta Estado | Cada consulta de estado |
| Advertencia | Alertas de provisiones negativas, etc. |

El **Glosario Reglas DIAN** (`Configuración → Glosario Reglas DIAN`) contiene los códigos de rechazo más comunes con su causa y solución. También se consulta automáticamente al registrar una respuesta de rechazo.

---

## Modelos principales

| Modelo | Descripción |
|---|---|
| `hr.payslip.edi` | Documento de nómina electrónica individual |
| `hr.payslip.edi.run` | Lote de documentos para procesamiento masivo |
| `hr.payslip.edi.line` | Líneas de devengados y deducciones del documento |
| `hr.payslip.edi.worked_days` | Días trabajados del documento |
| `hr.payslip.edi.log` | Historial de eventos y respuestas DIAN |
| `hr.accrued.rule` | Catálogo de conceptos devengados DIAN |
| `hr.deduct.rule` | Catálogo de conceptos deducción DIAN |
| `hr.payment.method.dian` | Métodos de pago DIAN |
| `hr.way.pay` | Formas de pago DIAN |
| `hr.type.note` | Tipos de nota de ajuste (Reemplazar / Eliminar) |
| `dian.rejection.glossary` | Glosario de reglas de rechazo DIAN |
| `nomina.xml.generator` | Generador de XML, firma y comunicación SOAP (abstracto) |

---

## Dependencias Python

```
cryptography      # Manejo de certificados P12 / firma XAdES-EPES
lxml              # Generación y parseo de XML
requests          # Comunicación HTTP con proveedor
pyqrcode          # Generación de código QR (opcional)
xmltodict         # Parseo de XML en comparación de valores (opcional)
```

Instalar con:

```bash
pip install cryptography lxml requests pyqrcode xmltodict
```

---

## Pruebas unitarias

El módulo incluye pruebas en `tests/`:

```bash
python odoo-bin -c odoo.conf -d <base> \
  --test-enable -u lavish_hr_payroll_edi \
  --stop-after-init --http-port 8099
```

Cobertura: estados del documento, consolidación de líneas, notas de ajuste, mapeo de códigos DIAN, logs, restricciones de campos.

---

## Migración desde v18

El módulo incluye scripts de migración en `migrations/`. El `pre_init_hook` en `hooks.py` adopta registros existentes de `hr.accrued.rule` y `hr.deduct.rule` para evitar conflictos de constraint al reinstalar.
