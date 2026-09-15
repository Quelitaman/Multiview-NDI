# Despliegue en Windows — NDI Multiview

> **Importante**: NDI descubre fuentes por **mDNS multicast (UDP 5353)** en la subred local.
> Para que la app detecte tus fuentes reales, el backend **debe correr en un equipo Windows
> conectado a la misma red que las fuentes NDI** (o llegar a ellas vía NDI Discovery Server).
> El preview en la nube nunca verá fuentes de tu LAN — solo mostrará las 6 fuentes DEMO.

---

## 1. Requisitos

- Windows 10 / 11 o Windows Server 2019+
- **NDI 5/6 Runtime** instalado — <https://ndi.video/tools/> → *NDI Tools* (incluye el runtime).
- Python 3.11 (64-bit) — <https://www.python.org/downloads/windows/>
- Node.js 20 + Yarn (`npm i -g yarn`)
- MongoDB Community — <https://www.mongodb.com/try/download/community> (o usa un Mongo remoto/Atlas)

## 2. Clonar / copiar el proyecto

```powershell
git clone <tu-repo-o-copia-el-zip>
cd nombre-del-proyecto
```

## 3. Backend (FastAPI + cyndilib)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
pip install cyndilib pillow
```

Crear/editar `backend\.env`:

```
MONGO_URL=mongodb://localhost:27017
DB_NAME=ndi_multiview
CORS_ORIGINS=*
```

Levantar el servicio:

```powershell
uvicorn server:app --host 0.0.0.0 --port 8001
```

Comprobar el descubrimiento (debe listar tus fuentes reales, no las DEMO):

```powershell
curl http://localhost:8001/api/sources
```

## 4. Frontend (React)

```powershell
cd frontend
yarn install
```

Editar `frontend\.env`:

```
REACT_APP_BACKEND_URL=http://IP-DEL-SERVIDOR:8001
```

> Si el navegador y el backend están en el **mismo** equipo puedes usar `http://localhost:8001`.

```powershell
yarn build
# o para pruebas rápidas:
yarn start
```

Sirve el `build/` con cualquier servidor estático (IIS, `serve`, nginx-win, etc.).

## 5. Firewall

Abrir en el firewall de Windows:

- **TCP 8001** — backend FastAPI
- **TCP 3000** (si usas `yarn start` en desarrollo)
- **UDP 5353** — mDNS, entrada/salida (imprescindible para NDI)
- **UDP 5960 – 5990** — NDI streams
- **TCP 5960 – 5990** — NDI streams

## 6. Verificación

- `GET /api/config` → `{"ndi_available":true,"mode":"ndi"}`
- `GET /api/sources` → lista con tus cámaras / PCs NDI reales (además de las 6 DEMO).
- Si sólo ves las DEMO: revisa que las fuentes estén en la **misma subred**, que el firewall
  no bloquee mDNS/UDP 5353 y que **NDI Studio Monitor** (de NDI Tools) sí las vea desde
  ese mismo equipo. Si Studio Monitor tampoco las ve → problema de red, no de la app.

## 7. (Opcional) Ejecutar como servicio de Windows

Usar [NSSM](https://nssm.cc/):

```powershell
nssm install NdiMultiviewBackend ^
    "C:\ruta\backend\.venv\Scripts\python.exe" ^
    "-m" "uvicorn" "server:app" "--host" "0.0.0.0" "--port" "8001"
nssm set NdiMultiviewBackend AppDirectory "C:\ruta\backend"
nssm start NdiMultiviewBackend
```

## 8. Subredes distintas / Discovery Server

Si tus fuentes viven en otra VLAN, ejecuta **NDI Discovery Server** (NDI Tools) en un equipo
alcanzable por ambos lados y configúralo en el servidor con:

```powershell
setx NDI_DISCOVERY_SERVER "IP.DEL.DISCOVERY.SERVER"
```

Reinicia el backend.
