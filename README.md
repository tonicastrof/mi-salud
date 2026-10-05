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
│   │   ├── archive.py        ← Ficha diaria: guarda el día en el histórico
│   │   └── cache.py          ← Upstash Redis
│   ├── sync-garmin.py        ← Endpoint: descargar datos Garmin
│   ├── sync-strava.py        ← Endpoint: descargar datos Strava
│   ├── sync-all.py           ← Endpoint: los tres pasos seguidos (lo llama el cron)
│   ├── calculate.py          ← Endpoint: calcular métricas
│   ├── history.py            ← Endpoint: leer el archivo diario
│   ├── dashboard.py          ← Endpoint: leer todo (instantáneo)
│   ├── widget.py             ← Endpoint: resumen mínimo para el widget de Android
│   ├── activity.py           ← Endpoint: detalle + streams de una actividad
│   ├── day.py                ← Endpoint: datos de Garmin de un día concreto
│   ├── plan.py               ← Endpoint: próximos entrenos de Garmin Coach / calendario
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

  Medias exponenciales del Relative Effort de Strava: CTL a 42 días, ATL a 7,
  TSB = CTL − ATL. La simulación arranca en la actividad más antigua que haya
  (tope 400 días) y siembra ambas con la carga media de las dos primeras
  semanas. Con menos de 42 días de historial el CTL no ha convergido y la app
  lo avisa bajo la gráfica: el Fitness aún se está asentando.

  Forma negativa = la última semana ha cargado más que tu media de 6 semanas.
  Es lo normal entrenando; se busca que suba a positivo antes de competir.
- Ratio Agudo:Crónico (riesgo lesión)

  **Las tres cargas no son la misma cosa y nunca deben compararse entre sí:**

  | Cifra | Ventana | Escala |
  |---|---|---|
  | Carga aguda / crónica (ACWR) | Móvil: hoy-6→hoy y media de 28 días | Relative Effort de Strava |
  | Barra de «Volumen por semana» | Semana natural lun→dom, la última EN CURSO | Relative Effort de Strava |
  | «Carga» del Estado de entreno | Últimos 7 días | Escala propia de Garmin (EPOC) |

  Un viernes con 202 en la barra de la semana y 400 de carga aguda es correcto:
  la barra lleva 5 días (lun→vie) y la aguda lleva 7 (incluye el sábado y el
  domingo anteriores). La app ahora etiqueta ambas con su ventana y marca la
  semana en curso con los días que lleva.

  La media de 4 semanas se calcula solo con semanas **completas**: antes incluía
  la semana a medias, así que la referencia bajaba sola según avanzaba la semana.
- Predicción carreras (5K, 10K, media, maratón)

  El VO₂max que se muestra es el que mide Garmin **corriendo**. Solo si Garmin
  no lo da se recurre a la estimación desde el FTP, que es una fórmula de
  ciclismo y se queda muy corta para correr. Los tiempos en sí se calibran con
  tu mejor ritmo real de 5 km+, así que no dependen del VO₂max.
- Training Readiness (compuesto)
- Volumen por semana y por mes (16 semanas / 12 meses)
- Calendario de días entrenados (12 semanas), racha y días de descanso
- Reparto por deporte, por día de la semana y por franja horaria
- Tendencias de ritmo (carrera) y velocidad (bici)
- Récords: más larga, más desnivel, sesión más dura, ritmo más rápido

## Sincronización automática y archivo diario

### El problema que resuelve

Antes los datos solo se refrescaban cuando abrías la app y pulsabas **Sync**.
Eso dejaba dos agujeros:

- **El widget mentía.** Enseñaba lo último que hubiera en Redis, que era de la
  última vez que abriste la app. Si no la abrías en tres días, el widget
  llevaba tres días de retraso — justo la parte que debería servir para *no*
  tener que abrir nada.
- **No había histórico.** Redis solo guardaba cuatro claves (`garmin`,
  `strava`, `metrics`, `meta`) y cada sync las machacaba. Todo lo que la app
  enseña «del pasado» sale de las ventanas móviles que devuelven Garmin y
  Strava en ese momento: 7 días de sueño, HRV y estrés, 8 semanas de FC en
  reposo, 200 actividades. En cuanto un dato salía de esa ventana,
  desaparecía para siempre.

### El cron

`vercel.json` define un cron diario que llama a `/api/sync-all`:

```json
"crons": [{ "path": "/api/sync-all", "schedule": "10 5 * * *" }]
```

`/api/sync-all` encadena los tres pasos (Garmin → Strava → cálculo) en una
sola llamada, porque un cron de Vercel apunta a una URL y no puede encadenar
tres. El botón Sync de la app sigue llamando a los tres endpoints por separado:
así enseña el progreso paso a paso y cada petición tiene su propio presupuesto
de tiempo.

- **Cada paso guarda en Redis en cuanto acaba**, así que si se agota el tiempo
  a mitad quedan hechos los pasos anteriores en vez de perderse todo.
- La respuesta trae el detalle por paso. **Un 200 no significa que los tres
  fueran bien**: mira `status` (`ok` / `partial` / `error`) y `failed`.
- `?steps=garmin,strava` limita qué pasos corren. Los tres caben de sobra en
  los 60 s del plan Hobby, pero si algún día no cupieran se puede partir en
  varios crons sin tocar código.

**Ojo con el plan de Vercel.** En Hobby cada cron dispara **una vez al día** y
`maxDuration` no puede pasar de 60 s (por eso está en 60 y no más). En Pro
puedes subir la frecuencia a varias veces al día — `0 */6 * * *` para cada seis
horas — y es lo recomendable para que el widget esté siempre al día.

### Proteger el endpoint

`/api/sync-all` dispara un login de Garmin y la descarga de 200 actividades, y
la URL de Vercel es pública. Define `CRON_SECRET` y exigirá
`Authorization: Bearer <secreto>`, que es justo la cabecera que manda Vercel
Cron por su cuenta. Sin esa variable el endpoint queda abierto.

### El archivo diario

Cada cálculo guarda una **ficha compacta del día** en `day:YYYY-MM-DD`, más un
índice en `day:index` con las fechas que hay. Lleva los pasos, calorías,
distancia, FC en reposo/mín/máx, estrés, Body Battery, sueño con sus fases,
HRV, SpO₂, respiración, y además el CTL/ATL/TSB, la readiness con su desglose
y el ACWR de ese día.

Es compacta a propósito: la foto completa lleva la curva de FC del día (248+
mediciones) y no tiene sentido multiplicarla por 365.

Dos cosas que hace y que no son obvias:

- **Rellena los últimos 7 días, no solo hoy.** El cron corre de madrugada,
  cuando «hoy» son 200 pasos y nada más; si solo archivara hoy, el archivo
  sería una colección de días vacíos. Los arrays semanales del snapshot
  (`steps_week`, `hrv_week`, …) traen los 7 últimos días con su fecha, así que
  se aprovechan para completar hacia atrás. De paso tapa los huecos de los días
  que no sincronizaste.
- **Nunca degrada un día ya archivado.** Al fusionar, un valor nuevo a 0 o
  vacío no pisa uno anterior que sí tenía dato: en estas métricas el 0 casi
  siempre significa «no medido». La ficha completa de ayer por la noche no
  pierde su readiness porque el array semanal de esta madrugada no la traiga.

La readiness y el ACWR solo se guardan del día en que se calcularon — no se
inventan hacia atrás. El CTL/ATL/TSB de días pasados sí, porque sale del
timeline que Strava permite recalcular entero.

### Leerlo

```
GET /api/history?days=90                        # fichas completas
GET /api/history?days=180&field=readiness.score # una sola serie, aplanada
GET /api/history?days=90&field=daily.resting_hr
```

Devuelve también `total_archived`, `first` y `last`, para saber cuánto archivo
hay acumulado. Cuanto más tiempo lleve el cron corriendo, más largo es — y a
diferencia del resto de la app, **esto no se puede reconstruir**: si no se
guardó en su día, no está.

## Pestañas de la app

| Pestaña | Qué tiene |
|---|---|
| **Resumen** | Anillos del día, sueño, FC, estrés, Body Battery, tendencias de la semana |
| **Forma** | CTL/ATL/TSB, **carga aguda/crónica con su ventana**, predicción de carreras, training readiness, volumen |
| **Entrenos** | Gráficas de volumen, desnivel, reparto por deporte, cuándo entrenas, tendencia de ritmo/velocidad, récords, **calendario de entrenos** e historial |
| **Coach** | Copia tu informe para pegarlo en la app de Claude, o chatea aquí mismo si activas la API |

Al tocar una actividad se abre el detalle con el mapa, la **evolución durante la
sesión** (FC, ritmo, altitud, cadencia, potencia), el **tiempo en cada zona de
FC**, los parciales por km y los mejores esfuerzos. Desde ahí puedes pulsar
«Preguntar al entrenador sobre esta sesión» y el chat arranca con esa actividad
como contexto (parciales y zonas incluidos).

## Entrenador IA (Claude)

Hay dos formas de usarlo, y no son excluyentes.

### A) Copiar el informe y preguntar en la app de Claude — **gratis**

La pestaña Coach tiene un botón **«Copiar informe»**: genera un texto con las
instrucciones de entrenador + todo tu dossier y lo deja en el portapapeles.
Lo pegas en una conversación nueva de la app de Claude (la de tu suscripción) y
ya te responde como entrenador con tus datos delante.

- `GET /api/coach?dossier=1` es lo que devuelve ese texto. No necesita
  `ANTHROPIC_API_KEY`, así que funciona sin gastar nada de API.
- Si entras desde el detalle de una sesión, el informe incluye además sus
  parciales por km y su tiempo en zonas.
- Ojo: tu suscripción de claude.ai **no** sirve para llamar a la API desde la
  app; son productos con facturación separada. Por eso existe esta opción.

### B) Chat dentro de la app — de pago por uso

Si defines `ANTHROPIC_API_KEY`, la pestaña Coach añade un chat completo.
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
`/api/coach` exige la cabecera `X-App-Secret` tanto para el chat como para el
informe; la app te pedirá esa clave la primera vez y la recordará en el
navegador. Protege tu cuota de API y, sobre todo, tus datos de salud.

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
   - `ANTHROPIC_API_KEY` ← **solo** si quieres el chat dentro de la app ([console.anthropic.com](https://console.anthropic.com) → API Keys). El botón «Copiar informe» funciona sin ella.
   - `APP_SECRET` (opcional pero recomendado) ← contraseña para `/api/coach`
   - `CRON_SECRET` (opcional pero recomendado) ← protege `/api/sync-all`. Vercel
     Cron la manda sola como `Authorization: Bearer …`; sin ella el endpoint es
     público y cualquiera puede dispararte el sync.
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

### 7. Instalar en el móvil

Dos opciones:

**A) PWA (sin compilar nada)**
1. Abre tu dashboard en Chrome/Safari
2. Menú → "Añadir a pantalla de inicio"
3. Se instala como app nativa

**B) APK de Android** — ver la sección siguiente.

## APK de Android

En `android/` hay una app nativa mínima: una WebView a pantalla completa que
abre el despliegue de Vercel. No duplica el frontend, así que cualquier cambio
en `public/index.html` aparece en el móvil sin recompilar la APK.

Qué añade sobre la PWA:

- Icono y entrada propia en el cajón de aplicaciones, sin barra del navegador.
- Botón atrás del móvil = atrás en la app (cierra modales, vuelve de pestañas).
- Puente de portapapeles nativo: el botón «Copiar informe» del Coach funciona
  aunque la WebView no exponga la API asíncrona de portapapeles.
- La barra de estado se tiñe del color de fondo de la web, así que sigue al
  modo claro/oscuro de la app.
- Pantalla de error propia si no hay red, con **Reintentar** y **Cambiar URL**
  (por si cambias de despliegue: la URL nueva se guarda en el móvil).
- Widget para la pantalla de inicio (ver más abajo).

### Widget en la pantalla de inicio

La APK trae un widget redimensionable (4x2 por defecto) que enseña, sin abrir
la app: pasos del día con barra de progreso sobre tu objetivo, Body Battery,
FC en reposo, sueño, readiness y una línea con la forma (fitness y TSB).

- **Para añadirlo**: mantén pulsado el escritorio → Widgets → Mi Salud.
- **Toca el widget** y se abre la app; **toca el ⟳** y se actualiza al momento.
- Se refresca solo cada 30 minutos (el mínimo que permite Android) y también
  cuando abres la app, si lo que enseña tiene más de 10 minutos.
- Guarda la última respuesta, así que sin cobertura sigue enseñando los últimos
  datos conocidos con un «sin conexión» en el pie, en vez de quedarse en blanco.

Lee de `GET /api/widget`, un endpoint nuevo que devuelve solo esos números
(un par de kB). El widget no puede usar `/api/dashboard`: ese devuelve el
volcado completo con 200 actividades y sus polylines, y no tiene sentido
bajárselo cada media hora desde la pantalla de inicio.

`/api/widget` no pide `APP_SECRET`, igual que `/api/dashboard` — el widget es
código nativo y no tiene acceso a la clave que guarda el navegador. Si algún
día proteges la API entera, este endpoint hay que tenerlo en cuenta.

### Compilarla

La compila GitHub Actions — no hace falta Android Studio.

1. Ve a **Actions → Compilar APK** en el repo.
2. La APK se genera sola en cada push que toque `android/`, y también a mano
   con **Run workflow** (ahí puedes escribir otra URL de despliegue).
3. Cuando acabe, el `.apk` queda en dos sitios: como *artifact* del run y como
   **release** (`apk-v1.0.N`), que es la cómoda para el móvil.

### Instalarla

1. Abre la release desde el móvil y descarga el `.apk`.
2. Android pedirá permiso para instalar desde orígenes desconocidos → acéptalo.
3. Instala. Las siguientes versiones se instalan encima sin desinstalar nada,
   porque todas las compilaciones usan la misma clave de firma.

### Cambiar la URL por defecto

Por defecto apunta a `https://mi-salud-nine.vercel.app`. Para otra:

- puntual: **Run workflow** → campo *URL del despliegue*;
- permanente: cambia `appUrl` en `android/app/build.gradle`;
- desde el móvil: pantalla de error → **Cambiar URL**.

### Compilar en local (opcional)

Con el SDK de Android instalado:

```bash
cd android
./gradlew assembleRelease -PappUrl=https://mi-salud-nine.vercel.app
# app/build/outputs/apk/release/app-release.apk
```
