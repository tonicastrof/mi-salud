# Mi Salud — Proyecto Completo

## Contenido

```
mi-salud-final/
├── api/                      ← Backend (despliega en Vercel)
│   ├── _lib/
│   │   ├── garmin_client.py  ← Garmin Connect (CORREGIDO con test real)
│   │   ├── strava_client.py  ← Strava API
│   │   ├── metrics.py        ← CTL/ATL/TSB, ACWR, predicciones, readiness
│   │   └── cache.py          ← Upstash Redis
│   ├── sync-garmin.py        ← Endpoint: descargar datos Garmin
│   ├── sync-strava.py        ← Endpoint: descargar datos Strava
│   ├── calculate.py          ← Endpoint: calcular métricas
│   ├── dashboard.py          ← Endpoint: leer todo (instantáneo)
│   └── activity.py           ← Endpoint: detalle de actividad
├── public/index.html         ← Landing del API
├── dashboard.jsx             ← Frontend React (dark/light mode + Sync)
├── vercel.json
├── requirements.txt
└── README.md
```

## Datos que se descargan

### Garmin — HOY
- Pasos, calorías, distancia, minutos activos, pisos
- FC reposo, mínima, máxima + timeline por hora (248+ mediciones)
- Sueño: fases (profundo, ligero, REM, despierto), score, horarios
- Estrés: nivel medio, máximo + timeline por hora
- Body Battery: máximo, mínimo + curva del día
- HRV: media semanal, última noche, estado
- SpO₂: media, mínimo (si el reloj lo soporta)
- Respiración: media, máxima, mínima

### Garmin — SEMANAL
- Pasos diarios (7 días)
- HRV + FC reposo diarios (7 días)
- Sueño: horas + score por noche (7 días)
- Estrés medio diario (7 días)
- Body Battery máx/mín diario (7 días)
- FC reposo tendencia (8 semanas)

### Strava
- Últimas 30 actividades con polylines (mapas GPS)
- Splits por km, mejores esfuerzos
- Perfil: peso, FTP
- Zonas: FC, potencia, ritmo de carrera
- Material: bicis y zapatillas con km

### Calculadas
- Fitness/Fatiga/Forma (CTL/ATL/TSB)
- Ratio Agudo:Crónico (riesgo lesión)
- Predicción carreras (5K, 10K, media, maratón)
- Training Readiness (compuesto)

## Despliegue — Paso a paso

### 1. Crear Upstash Redis (1 min, gratis)
- [console.upstash.com](https://console.upstash.com) → crear DB Redis → copiar URL + Token

### 2. Preparar Strava (5 min, una sola vez)
```bash
# Crear app en https://www.strava.com/settings/api
# Autorizar:
open "https://www.strava.com/oauth/authorize?client_id=TU_ID&response_type=code&redirect_uri=http://localhost&scope=read_all,activity:read_all,profile:read_all"
# Cambiar code por tokens:
curl -X POST https://www.strava.com/oauth/token \
  -d client_id=TU_ID -d client_secret=TU_SECRET \
  -d code=EL_CODE -d grant_type=authorization_code
```

### 3. Probar Garmin localmente (2 min)
```bash
pip install garminconnect
python test_garmin.py  # (el script de test que ya tienes)
```

### 4. Subir a GitHub
```bash
cd mi-salud-final
git init && git add . && git commit -m "Mi Salud v1"
git remote add origin https://github.com/TU_USER/mi-salud.git
git push -u origin main
```

### 5. Deploy en Vercel
1. [vercel.com](https://vercel.com) → New Project → importar repo
2. Variables de entorno:
   - `GARMIN_EMAIL` / `GARMIN_PASSWORD`
   - `STRAVA_CLIENT_ID` / `STRAVA_CLIENT_SECRET` / `STRAVA_REFRESH_TOKEN`
   - `UPSTASH_REDIS_URL` / `UPSTASH_REDIS_TOKEN`
3. Deploy

### 6. Desplegar el Dashboard
El archivo `dashboard.jsx` es el frontend React. Para desplegarlo:

```bash
npx create-react-app mi-salud-pwa
# Reemplaza src/App.jsx con el contenido de dashboard.jsx
# Cambia la línea API_URL al principio:
#   const API_URL = "https://tu-proyecto.vercel.app";
npm run build
# Despliega en Vercel como segundo proyecto, o en GitHub Pages
```

### 7. Instalar como PWA en el móvil
1. Abre tu dashboard en Chrome/Safari
2. Menú → "Añadir a pantalla de inicio"
3. Se instala como app nativa
