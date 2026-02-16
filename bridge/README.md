# Bridge Báscula Prometálicos → Odoo CloudPepper

## 📋 Descripción

Este script conecta tu báscula Prometálicos (conectada por RS-232/USB) con tu instancia de Odoo en CloudPepper, permitiendo actualizar el peso en tiempo real durante los pesajes.

## 🔧 Requisitos

### Hardware:
- ✅ Báscula Prometálicos con salida RS-232/USB
- ✅ Cable RS-232 a USB (si tu PC no tiene puerto serial)
- ✅ PC Windows conectado a internet
- ✅ La báscula debe estar encendida y configurada para transmitir datos

### Software:
- ✅ Windows 7 o superior
- ✅ Python 3.7 o superior
- ✅ Driver USB-Serial instalado (si usas cable USB)

---

## 📦 Instalación

### Paso 1: Instalar Python

1. Descarga Python desde: https://www.python.org/downloads/
2. Durante la instalación, marca: **"Add Python to PATH"**
3. Verifica la instalación abriendo CMD y ejecutando:
   ```cmd
   python --version
   ```

### Paso 2: Instalar dependencias

Abre CMD en esta carpeta y ejecuta:

```cmd
pip install pyserial requests
```

### Paso 3: Identificar el puerto COM de la báscula

1. Conecta el cable de la báscula al PC
2. Abre **Administrador de Dispositivos** (Win + X → Administrador de dispositivos)
3. Busca en **Puertos (COM y LPT)**
4. Verás algo como: `USB Serial Port (COM3)`
5. Anota el número del puerto (ej: COM3)

### Paso 4: Configurar Odoo

1. Inicia sesión en tu Odoo CloudPepper
2. Ve a: **Configuración → Ajustes**
3. Busca la sección **"Báscula"**
4. Click en **"Generar API Key Aleatoria"**
5. Copia la API Key generada
6. Guarda los cambios

### Paso 5: Configurar el script

1. Abre `bascula_bridge.py` con un editor de texto (Notepad++, VS Code, etc.)
2. Modifica las siguientes líneas:

```python
# Cambia esto:
ODOO_URL = "https://tu-instancia.cloudpepper.site"

# Por tu URL real (ejemplo):
ODOO_URL = "https://223ivyj1eb1.cloudpepper.site"

# Cambia esto:
API_KEY = "TU_API_KEY_AQUI"

# Por la API Key que generaste en Odoo (ejemplo):
API_KEY = "K8hN2pQr5vXzAb9Cd4Ef7Gh1Jk6Lm3Np0Rs8Tu"

# Cambia el puerto COM si es necesario:
PUERTO_SERIAL = "COM3"  # Usa el que identificaste en el Paso 3
```

3. Guarda el archivo

---

## 🚀 Uso

### Ejecutar manualmente (para pruebas):

1. Abre CMD en esta carpeta
2. Ejecuta:
   ```cmd
   python bascula_bridge.py
   ```
3. Deberías ver:
   ```
   ============================================================
   🔌 BRIDGE BÁSCULA PROMETÁLICOS → ODOO CLOUDPEPPER
   ============================================================
   Odoo URL: https://tu-instancia.cloudpepper.site
   Puerto Serial: COM3
   Intervalo: 0.5s
   ============================================================
   ✅ Conectado a báscula Prometálicos
   ✅ Bridge iniciado correctamente
   🔍 Esperando pesajes en Odoo...
   ```

4. En Odoo, crea un nuevo pesaje
5. Pon peso en la báscula
6. Verás en el CMD:
   ```
   🎯 Nuevo pesaje activo: 5
   ⚖️  Peso leído: 28345.50 kg
   ✅ Peso enviado a Odoo
   ```

7. En Odoo verás el peso actualizándose automáticamente

### Para detener:
- Presiona `Ctrl + C` en la ventana de CMD

---

## 🔄 Instalar como servicio de Windows (ejecución automática)

Para que el bridge se ejecute automáticamente al iniciar Windows:

### Método 1: Tarea Programada (Recomendado)

1. Crea un archivo `iniciar_bridge.bat` con:
   ```batch
   @echo off
   cd /d C:\ruta\a\bridge
   python bascula_bridge.py
   pause
   ```

2. Abre **Programador de tareas** (Task Scheduler)
3. Click en **"Crear tarea básica"**
4. Nombre: `Bridge Báscula`
5. Desencadenador: **"Al iniciar el equipo"**
6. Acción: **"Iniciar un programa"**
7. Programa: Ruta al archivo `.bat`
8. Finalizar

### Método 2: NSSM (Avanzado)

1. Descarga NSSM: https://nssm.cc/download
2. Abre CMD como Administrador
3. Ejecuta:
   ```cmd
   nssm install BasculaBridge "C:\Python\python.exe" "C:\ruta\a\bridge\bascula_bridge.py"
   nssm set BasculaBridge Description "Bridge Báscula Prometálicos → Odoo"
   nssm set BasculaBridge Start SERVICE_AUTO_START
   nssm start BasculaBridge
   ```

---

## 📊 Logs

El script genera un archivo `bascula_bridge.log` con todos los eventos:
- Conexiones exitosas/fallidas
- Pesos leídos
- Errores

Revisa este archivo si hay problemas.

---

## 🐛 Solución de problemas

### ❌ "No se puede conectar a báscula"
- Verifica que el puerto COM sea correcto
- Verifica que la báscula esté encendida
- Verifica que el cable esté bien conectado
- Prueba con otro puerto COM (COM1, COM2, COM4, etc.)

### ❌ "No se puede conectar a Odoo"
- Verifica que el ODOO_URL sea correcto
- Verifica que tengas conexión a internet
- Verifica que la API Key sea correcta

### ❌ "Error parseando peso"
- La báscula puede estar enviando un formato diferente
- Contacta soporte para ajustar el regex de parseo

### ❌ Peso no se actualiza en Odoo
- Verifica que haya un pesaje activo en Odoo (estado: borrador o en_transito)
- Revisa el archivo `bascula_bridge.log`
- Verifica que el peso esté dentro del rango válido (0 - 100,000 kg)

---

## 📞 Soporte

Para soporte técnico, contacta:
- Secadora La Gran Colombia S.A.S
- Incluye el archivo `bascula_bridge.log` en tu consulta

---

## 🔒 Seguridad

- ⚠️ **Nunca compartas tu API Key**
- ⚠️ La API Key es como una contraseña
- ⚠️ Si crees que tu API Key fue comprometida, genera una nueva en Odoo

---

## 📝 Licencia

© 2026 Secadora La Gran Colombia S.A.S
