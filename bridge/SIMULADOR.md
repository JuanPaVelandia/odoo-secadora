# 🎮 Simulador de Báscula - Guía de Pruebas

## ¿Qué es esto?

Un simulador que **NO requiere báscula física** para probar el sistema completo. Genera pesos aleatorios y los envía a Odoo como si fuera una báscula real.

## ✅ Ideal para:
- ✨ Probar el sistema sin hardware
- 🧪 Hacer demos
- 🎓 Entrenar usuarios
- 🐛 Debugging
- 📊 Desarrollo y testing

---

## 🚀 Inicio Rápido

### 1. Configurar Odoo (primero)

1. Inicia sesión en Odoo
2. Ve a: **Configuración → Ajustes**
3. Busca sección **"Báscula"**
4. Click **"Generar"** para crear API Key
5. **Copia** la API Key
6. **Guarda** cambios

### 2. Configurar el simulador

Abre `bascula_simulador.py` y modifica:

```python
# Tu URL de CloudPepper
ODOO_URL = "https://223ivyj1eb1.cloudpepper.site"

# Pega aquí la API Key que copiaste
API_KEY = "K8hN2pQr5vXzAb9Cd4Ef7Gh1Jk6Lm3Np0Rs8Tu"
```

### 3. Instalar dependencias (solo primera vez)

```cmd
pip install requests
```

### 4. Ejecutar

```cmd
python bascula_simulador.py
```

Verás algo como:
```
======================================================================
🎮 SIMULADOR DE BÁSCULA PROMETÁLICOS → ODOO CLOUDPEPPER
======================================================================
Odoo URL: https://223ivyj1eb1.cloudpepper.site
Modo: ALEATORIO
Rango de peso: 5000 - 35000 kg
Variación: ± 10 kg
Intervalo: 1s
======================================================================

✅ Simulador iniciado correctamente
🔍 Esperando pesajes en Odoo...
💡 Crea un pesaje en Odoo para empezar a ver datos

⏳ Esperando pesaje activo en Odoo...
```

---

## 🎯 Flujo de Prueba Completo

### Paso 1: Inicia el simulador
```cmd
python bascula_simulador.py
```

### Paso 2: En Odoo, crea un nuevo pesaje
1. Ve a **Báscula → Pesajes → Todos los Pesajes**
2. Click **Crear**
3. Llena los datos básicos:
   - **Tipo**: Entrada o Salida
   - **Placa**: ABC123 (o cualquiera)
   - **Tercero**: Selecciona uno
4. **Guarda** (no presiones ningún botón todavía)

### Paso 3: Observa el simulador
Verás:
```
📋 Pesaje activo: ID 5, Placa: ABC123, Tipo: entrada
🔄 Iniciando envío de pesos simulados...

⚖️  Peso simulado: 28,345.67 kg
📈  Peso simulado: 28,352.12 kg
📉  Peso simulado: 28,343.89 kg
➡️  Peso simulado: 28,343.89 kg
```

### Paso 4: Observa Odoo
En el formulario del pesaje verás:

```
┌────────────────────────────────────────┐
│  🟢 PESO ACTUAL DESDE BÁSCULA         │
│                                        │
│         28,345.67 Kg                  │
│                                        │
│  Se actualiza automáticamente         │
│                                        │
│  [✓ Usar Este Peso]                   │
└────────────────────────────────────────┘
```

El peso **se actualiza cada segundo** automáticamente.

### Paso 5: Registra la 1ª Pesada
- Espera a que el peso se "estabilice" (deja de variar mucho)
- Click en **"Usar Este Peso"** (opcional, si quieres asignar manualmente)
- O simplemente click en **"1ª Pesada"**
- El peso se congela

### Paso 6: Simula descarga/carga
El simulador automáticamente cambiará a un peso diferente (simulando que el camión descargó/cargó).

Verás:
```
📉  Peso simulado: 8,120.45 kg
📈  Peso simulado: 8,125.89 kg
```

### Paso 7: Registra la 2ª Pesada
- Click en **"2ª Pesada"**
- El sistema calcula automáticamente el peso neto
- Estado cambia a **"Completado"**

### Paso 8: Imprime el tiquete
- Click en **"Imprimir"**
- Selecciona **"Tiquete de Pesaje"**
- Se genera el PDF con todos los datos

---

## ⚙️ Modos de Simulación

### Modo Aleatorio (por defecto)
Genera pesos entre 5,000 y 35,000 kg con variaciones naturales.

```python
MODO_SIMULACION = "aleatorio"
PESO_BASE_MIN = 5000
PESO_BASE_MAX = 35000
VARIACION_PESO = 10
```

### Modo Fijo
Usa siempre el mismo peso (útil para pruebas específicas).

```python
MODO_SIMULACION = "fijo"
PESO_FIJO = 28345.50
```

---

## 📊 Escenarios de Prueba

### 🚚 Escenario 1: Entrada de Arroz (Compra)

1. Crea pesaje tipo **"Entrada"**
2. El simulador genera ~28,000 kg (camión lleno)
3. Registra **1ª Pesada** (peso bruto)
4. El simulador cambia a ~8,000 kg (camión vacío)
5. Registra **2ª Pesada** (peso tara)
6. Peso neto = 20,000 kg ✅

### 🚛 Escenario 2: Salida de Arroz (Venta)

1. Crea pesaje tipo **"Salida"**
2. El simulador genera ~8,000 kg (camión vacío)
3. Registra **1ª Pesada** (peso tara)
4. El simulador cambia a ~28,000 kg (camión lleno)
5. Registra **2ª Pesada** (peso bruto)
6. Peso neto = 20,000 kg ✅

### 🔄 Escenario 3: Múltiples Pesajes

1. Deja el simulador corriendo
2. Crea pesaje 1 → Complétalo
3. Crea pesaje 2 → El simulador lo detecta automáticamente
4. Crea pesaje 3 → Sin detener el simulador
5. Todos funcionan en secuencia ✅

---

## 🐛 Solución de Problemas

### ❌ "API KEY NO CONFIGURADA"
Edita el script y pega tu API Key de Odoo.

### ❌ "No se puede conectar a Odoo"
- Verifica que el `ODOO_URL` sea correcto
- Verifica conexión a internet
- Verifica que Odoo esté funcionando

### ❌ "No hay pesajes activos"
Crea un pesaje en Odoo primero (estado: borrador o en_transito).

### ❌ El peso no se actualiza en Odoo
- Actualiza la página (F5)
- Verifica que el módulo esté actualizado
- Revisa el log: `bascula_simulador.log`

---

## 🎛️ Comandos Útiles

### Ejecutar normalmente
```cmd
python bascula_simulador.py
```

### Detener el simulador
Presiona `Ctrl + C` en la ventana de CMD

### Ver logs
Abre el archivo `bascula_simulador.log`

### Cambiar intervalo de actualización
```python
INTERVALO_ACTUALIZACION = 2  # Cada 2 segundos
```

### Cambiar rango de pesos
```python
PESO_BASE_MIN = 10000  # 10 toneladas
PESO_BASE_MAX = 40000  # 40 toneladas
```

---

## 🎬 Demo para Clientes

**Escenario perfecto para mostrar el sistema:**

1. **Preparación** (antes de la demo):
   - Inicia el simulador
   - Ten Odoo abierto en pantalla completa

2. **Durante la demo**:
   - "Llega un camión a pesarse..." → Creas el pesaje
   - "El peso se actualiza en tiempo real..." → Muestras el número verde parpadeando
   - "El basculero registra la primera pesada..." → Click en 1ª Pesada
   - "El camión descarga..." → El peso baja automáticamente
   - "Segunda pesada..." → Click en 2ª Pesada
   - "Se genera el tiquete..." → Imprimir PDF

3. **Efecto WOW** 🤩
   - Los clientes ven el peso actualizándose en vivo
   - Proceso rápido y profesional
   - PDF automático al final

---

## 💡 Tips

- ✅ Deja el simulador corriendo todo el día para pruebas continuas
- ✅ Crea varios pesajes seguidos para probar el flujo
- ✅ Prueba los filtros (Entradas, Salidas, En Tránsito)
- ✅ Prueba la vista Kanban
- ✅ Imprime varios tiquetes
- ✅ Crea datos de prueba (vehículos, conductores, lugares)

---

## 🔄 Diferencias con Báscula Real

| Aspecto | Simulador | Báscula Real |
|---------|-----------|--------------|
| Hardware | ❌ No requiere | ✅ Báscula Prometálicos |
| Cable | ❌ No requiere | ✅ RS-232/USB |
| Velocidad | 1 actualización/seg | 2 actualizaciones/seg |
| Peso | Aleatorio/Fijo | Real |
| Uso | Pruebas/Demo | Producción |

---

## 📞 Soporte

¿Problemas con el simulador?
1. Revisa `bascula_simulador.log`
2. Verifica configuración de API Key
3. Verifica conexión a Odoo

---

## 🎓 Próximo Paso

Una vez que todo funcione con el simulador, será **muy fácil** cambiar a la báscula real:

1. Conecta la báscula al PC
2. Usa `bascula_bridge.py` en lugar del simulador
3. Configura el puerto COM
4. ¡Listo! Todo lo demás es igual

---

¡Disfruta probando el sistema! 🚀
