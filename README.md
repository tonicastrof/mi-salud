# Mi Salud — Proyecto Completo

## Contenido

```
mi-salud-final/
├── api/                      ← Backend (despliega en Vercel)
│   ├── _lib/
│   │   ├── garmin_client.py  ← Garmin Connect (CORREGIDO con test real)
│   │   ├── strava_client.py  ← Strava API (actividades, streams, zonas)
│   │   ├── metrics.py        ← CTL/ATL/TSB, ACWR, predicciones, readiness
│   │   ├── analytics.py      ← Volumen semanal, calendario, récords, tendencias
│   │   ├── coach_context.py  ← Dossier del atleta para el entrenador IA
│   │   └── cache.py          ← Upstash Redis
│   ├── sync-garmin.py        ← Endpoint: descargar datos Garmin
│   ├── sync-strava.py        ← Endpoint: descargar datos Strava
│   ├── calculate.py          ← Endpoint: calcular métricas
│   ├── dashboard.py          ← Endpoint: leer todo (instantáneo)
│   ├── activity.py           ← Endpoint: detalle + streams de una actividad
│   ├── day.py                ← Endpoint: datos de Garmin de un día concreto
│   └── coach.py              ← Endpoint: entrenador IA (Claude)
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
- Últimas 200 actividades con polylines (mapas GPS)
- Splits por km, mejores esfuerzos
- Perfil: peso, FTP
- Zonas: FC, potencia, ritmo de carrera
- Material: bicis y zapatillas con km

### Calculadas
- Fitness/Fatiga/Forma (CTL/ATL/TSB)
- Ratio Agudo:Crónico (riesgo lesión)
- Predicción carreras (5K, 10K, media, maratón)
- Training Readiness (compuesto)
- Volumen por semana y por mes (16 semanas / 12 meses)
- Calendario de días entrenados (12 semanas), racha y días de descanso
- Reparto por deporte, por día de la semana y por franja horaria
- Tendencias de ritmo (carrera) y velocidad (bici)
- Récords: más larga, más desnivel, sesión más dura, ritmo más rápido

## Pestañas de la app

| Pestaña | Qué tiene |
|---|---|
| **Resumen** | Anillos del día, sueño, FC, estrés, Body Battery, tendencias de la semana |
| **Forma** | CTL/ATL/TSB, predicción de carreras, training readiness, volumen |
| **Entrenos** | Gráficas de volumen, desnivel, reparto por deporte, cuándo entrenas, tendencia de ritmo/velocidad, récords, **calendario de entrenos** e historial |
| **Coach** | **Entrenador IA**: conversa con Claude, que ve todos tus datos |

Al tocar una actividad se abre el detalle con el mapa, la **evolución durante la
sesión** (FC, ritmo, altitud, cadencia, potencia), el **tiempo en cada zona de
FC**, los parciales por km y los mejores esfuerzos. Desde ahí puedes pulsar
«Preguntar al entrenador sobre esta sesión» y el chat arranca con esa actividad
como contexto (parciales y zonas incluidos).

## Entrenador IA (Claude)

`POST /api/coach` monta un dossier con todo lo que hay en caché — perfil, datos
de Garmin de hoy, tendencias de la semana, CTL/ATL/TSB, ACWR, readiness,
volumen, calendario, récords y las últimas 40 actividades — y se lo pasa a
Claude junto con la conversación.

- El dossier va marcado con `cache_control`, así que las preguntas siguientes de
  la misma conversación reutilizan el contexto cacheado (más rápido y barato).
- La conversación se guarda en el navegador (`localStorage`), no en el servidor.
- El modelo se puede cambiar con `COACH_MODEL` (por defecto `claude-sonnet-5`,
  que va sobrado para esto; pon `claude-opus-5` si quieres análisis más finos).
- Puedes preguntarle en general («¿qué carga llevo esta semana?», «¿qué toca
  mañana?», «¿voy bien para bajar de 45' en 10K?») o sobre una sesión concreta.
  El contexto de actividad solo se añade si entras desde el detalle de una, y
  se quita con el botón «✕ quitar» del chip de arriba.

### Proteger el endpoint

La app es privada pero la URL de Vercel es pública. Si defines `APP_SECRET`,
`/api/coach` exige la cabecera `X-App-Secret`; la app te pedirá esa clave la
primera vez y la recordará en el navegador. Es lo recomendado para que nadie
pueda gastar tu cuota de la API.

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
   - `ANTHROPIC_API_KEY` ← para el entrenador IA ([console.anthropic.com](https://console.anthropic.com) → API Keys)
   - `APP_SECRET` (opcional pero recomendado) ← contraseña para `/api/coach`
   - `COACH_MODEL` (opcional) ← por defecto `claude-sonnet-5`
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
