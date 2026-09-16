# NDI Multiview — Ejecutable para Windows

> Para ver **fuentes NDI reales**, el `.exe` debe correr **dentro de la LAN** donde
> están las fuentes (mDNS/UDP 5353). El preview en la nube nunca las verá.

## Contenido

- `build_windows.ps1` — script que compila el `.exe`
- `backend/launcher.py` — punto de entrada del ejecutable
- `backend/NdiMultiview.spec` — configuración PyInstaller
- `backend/requirements-exe.txt` — dependencias mínimas de runtime
- `backend/layout_store.py` — almacenamiento de layouts en JSON local
  (`%APPDATA%\NdiMultiview\layouts.json`) — **sin MongoDB**

---

## Uso rápido (VM Windows)

### 1. Requisitos (una sola vez en la VM que compila)

- **Python 3.11 x64** — <https://www.python.org/downloads/windows/> (marca *Add to PATH*)
- **Node.js 20** + Yarn (`npm i -g yarn`)
- **NDI 6 Runtime** — <https://ndi.video/tools> (instala *NDI Tools*)
  Aporta `Processing.NDI.Lib.x64.dll` en el PATH, necesario en tiempo de ejecución.

### 2. Compilar el ejecutable

Desde la raíz del proyecto en PowerShell:

```powershell
.\build_windows.ps1
```

Al terminar tendrás:

```
backend\dist\NdiMultiview.exe    (~ 60–90 MB)
```

### 3. Desplegar en la VM final

En cualquier VM Windows con **NDI Runtime** instalado:

1. Copia `NdiMultiview.exe` a una carpeta (por ejemplo `C:\NDI\`).
2. Doble clic. Se abrirá una consola con:

   ```
   ============================================================
    NDI MULTIVIEW
   ============================================================
     URL      : http://localhost:8001
     API      : http://localhost:8001/api
     Data dir : C:\Users\...\AppData\Roaming\NdiMultiview
   ============================================================
   ```

3. El navegador predeterminado se abrirá solo. Otros equipos de la LAN pueden acceder a
   `http://IP-DE-LA-VM:8001`.

### 4. Opciones de línea de comandos

```powershell
NdiMultiview.exe --port 9000          # cambiar puerto
NdiMultiview.exe --host 127.0.0.1     # solo escuchar en localhost
NdiMultiview.exe --no-browser         # no abrir navegador (uso desatendido)
```

Variables de entorno reconocidas:

- `NDI_PORT` — puerto por defecto (8001)
- `NDI_HOST` — host de escucha (0.0.0.0)
- `NDI_MULTIVIEW_DATA_DIR` — carpeta donde guardar `layouts.json`

### 5. Firewall

Abre las reglas de firewall de Windows:

- **TCP 8001** (o el puerto elegido) — HTTP de la app
- **UDP 5353** — mDNS (imprescindible para descubrir NDI)
- **UDP + TCP 5960 – 5990** — streams NDI (recepción **y** envío del Program Out)

### 5b. Publicar el multiview como fuente NDI (Program Out)

La app puede **enviar** el multiview compuesto como una fuente NDI en la red para que
vMix / OBS-NDI / TriCaster / Studio Monitor la consuman:

1. Coloca las tiles como quieras en el canvas.
2. Toolbar → **Program Out** → elige nombre (`NdiMultiview`), resolución (720p–2160p),
   frame rate (25/30/50/60) y pulsa **Go On Air**.
3. El toolbar muestra **ON AIR · <fps>** en rojo mientras esté activo.
4. En el resto de la red aparecerá una fuente NDI llamada `HOSTNAME (NdiMultiview)`.

El sender se compone en el servidor (RGB → BGRA) y respeta el frame rate elegido.
Cualquier cambio de layout mientras está ON AIR se envía automáticamente.

### 6. Instalar como servicio (opcional)

Con [NSSM](https://nssm.cc/):

```powershell
nssm install NdiMultiview "C:\NDI\NdiMultiview.exe" "--no-browser"
nssm set NdiMultiview AppDirectory "C:\NDI"
nssm set NdiMultiview AppStdout "C:\NDI\log\out.log"
nssm set NdiMultiview AppStderr "C:\NDI\log\err.log"
nssm start NdiMultiview
```

### 7. Discovery Server (VLANs distintas)

Si las fuentes viven en otra subred, ejecuta **NDI Discovery Server** en algún equipo
alcanzable por ambos lados y en la VM haz:

```powershell
setx NDI_DISCOVERY_SERVER "IP.DEL.DISCOVERY.SERVER"
```

Reinicia el `.exe`.

### 8. Verificación

- Abre `http://localhost:8001/api/config`  →  `{"ndi_available":true,"mode":"ndi", ...}`
- Abre `http://localhost:8001/api/sources` →  debe listar tus fuentes NDI reales.
  Si solo aparecen las 6 DEMO, comprueba con **NDI Studio Monitor** que ese equipo sí
  las ve. Si Studio Monitor tampoco las ve → problema de red o firewall, no del `.exe`.

---

## Troubleshooting

| Síntoma | Causa habitual |
|---|---|
| Solo aparecen fuentes DEMO | La VM no está en la misma subred que las fuentes, o firewall bloquea UDP 5353 |
| `ImportError: cyndilib` al arrancar | Falta el NDI Runtime — instala NDI Tools |
| El `.exe` se cierra al doble-clic | Lánzalo desde una consola para ver el error |
| Layouts no persisten | Revisa permisos de escritura en `%APPDATA%\NdiMultiview` |
