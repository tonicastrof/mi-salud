package app.misalud;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.text.SpannableString;
import android.text.SpannableStringBuilder;
import android.text.Spanned;
import android.text.style.ForegroundColorSpan;
import android.view.View;
import android.widget.RemoteViews;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.Locale;

/**
 * Widget de pantalla de inicio: lee /api/widget (los números del día, la
 * carrera de la semana y las pruebas nuevas) y los pinta. Guarda la última
 * respuesta, así que al añadirlo o al quedarse sin cobertura enseña lo último
 * que sabía en vez de quedarse en blanco.
 *
 * También avisa con una notificación cuando aparecen pruebas nuevas en
 * Carreiras Galegas (una vez por cada tanda; ver {@link #notifyNewRaces}).
 */
public class SaludWidget extends AppWidgetProvider {

    static final String ACTION_REFRESH = "app.misalud.action.REFRESH";
    private static final String CHANNEL_RACES = "carreras";
    private static final int NOTIF_RACES = 42;
    private static final Locale ES = new Locale("es", "ES");

    @Override
    public void onUpdate(Context context, AppWidgetManager manager, int[] ids) {
        renderAll(context, manager, ids, null);
        fetchAndRender(context, ids);
        RaceCheckJob.schedule(context);
    }

    @Override
    public void onReceive(Context context, Intent intent) {
        super.onReceive(context, intent);
        if (!ACTION_REFRESH.equals(intent.getAction())) {
            return;
        }
        AppWidgetManager manager = AppWidgetManager.getInstance(context);
        int[] ids = manager.getAppWidgetIds(new ComponentName(context, SaludWidget.class));
        renderAll(context, manager, ids, "actualizando…");
        fetchAndRender(context, ids);
    }

    /** Descarga en segundo plano y repinta; el broadcast se mantiene vivo mientras tanto. */
    private void fetchAndRender(Context context, final int[] ids) {
        final Context app = context.getApplicationContext();
        final PendingResult pending = goAsync();
        new Thread(() -> {
            String error = null;
            try {
                notifyNewRaces(app, fetchSnapshot(app));
            } catch (Unauthorized ex) {
                error = "abre la app para iniciar sesión";
            } catch (Exception ex) {
                error = "sin conexión";
            }
            try {
                renderAll(app, AppWidgetManager.getInstance(app), ids, error);
            } finally {
                pending.finish();
            }
        }).start();
    }

    /**
     * Pide /api/widget y guarda la respuesta. La usan el widget y la
     * comprobación periódica ({@link RaceCheckJob}). Llamar fuera del hilo principal.
     */
    static JSONObject fetchSnapshot(Context app) throws Exception {
        try {
            String body = get(Config.baseUrl(app) + "/api/widget", Config.token(app));
            JSONObject d = new JSONObject(body); // valida antes de guardar
            SharedPreferences.Editor e = Config.prefs(app).edit();
            e.putString(Config.KEY_SNAPSHOT, body);
            e.putLong(Config.KEY_SNAPSHOT_AT, System.currentTimeMillis());
            e.apply();
            return d;
        } catch (Unauthorized ex) {
            // La sesión guardada ya no vale (o nunca hubo): se vuelve a leer
            // de la WebView y, si tampoco, hay que entrar en la app.
            Config.prefs(app).edit().remove(Config.KEY_TOKEN).apply();
            throw ex;
        }
    }

    /** Repinta todos los widgets que haya con lo último guardado. */
    static void refreshAllWidgets(Context app) {
        AppWidgetManager manager = AppWidgetManager.getInstance(app);
        int[] ids = manager.getAppWidgetIds(new ComponentName(app, SaludWidget.class));
        new SaludWidget().renderAll(app, manager, ids, null);
    }

    static final class Unauthorized extends Exception {
    }

    private static String get(String url, String token) throws Exception {
        HttpURLConnection conn = (HttpURLConnection) new URL(url).openConnection();
        try {
            conn.setRequestMethod("GET");
            conn.setConnectTimeout(5000);
            conn.setReadTimeout(6000);
            conn.setRequestProperty("Accept", "application/json");
            conn.setRequestProperty("User-Agent", "MiSaludWidget/" + BuildConfig.VERSION_NAME);
            if (token != null && !token.isEmpty()) {
                conn.setRequestProperty("X-App-Token", token);
            }
            if (conn.getResponseCode() == 401) {
                throw new Unauthorized();
            }
            if (conn.getResponseCode() != 200) {
                throw new IllegalStateException("HTTP " + conn.getResponseCode());
            }
            StringBuilder sb = new StringBuilder();
            try (BufferedReader r = new BufferedReader(new InputStreamReader(conn.getInputStream(), "UTF-8"))) {
                String line;
                while ((line = r.readLine()) != null) {
                    sb.append(line);
                }
            }
            return sb.toString();
        } finally {
            conn.disconnect();
        }
    }

    // ─── Notificación de pruebas nuevas ────────────────────────────────────

    /**
     * Avisa una sola vez por cada tanda de pruebas nuevas: el servidor manda
     * una clave que cambia cuando aparecen más, y aquí se recuerda la última
     * avisada. Si das las pruebas por vistas en la app, el contador vuelve a 0.
     */
    static void notifyNewRaces(Context app, JSONObject d) {
        JSONObject n = d == null ? null : d.optJSONObject("races_new");
        if (n == null) {
            return;
        }
        int count = n.optInt("count", 0);
        String key = n.optString("key", "");
        SharedPreferences prefs = Config.prefs(app);
        if (count <= 0 || key.isEmpty() || key.equals(prefs.getString(Config.KEY_RACES_NOTIFIED, ""))) {
            return;
        }
        prefs.edit().putString(Config.KEY_RACES_NOTIFIED, key).apply();
        if (Build.VERSION.SDK_INT >= 33
                && app.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            return;
        }
        NotificationManager nm = app.getSystemService(NotificationManager.class);
        if (nm == null) {
            return;
        }
        NotificationChannel ch = new NotificationChannel(CHANNEL_RACES,
                app.getString(R.string.channel_races), NotificationManager.IMPORTANCE_DEFAULT);
        ch.setDescription(app.getString(R.string.channel_races_desc));
        nm.createNotificationChannel(ch);

        StringBuilder text = new StringBuilder();
        JSONArray names = n.optJSONArray("names");
        if (names != null) {
            for (int i = 0; i < names.length(); i++) {
                if (text.length() > 0) {
                    text.append(i == names.length() - 1 && count <= names.length() ? " y " : ", ");
                }
                text.append(names.optString(i));
            }
            if (count > names.length()) {
                text.append(" y ").append(count - names.length()).append(" más");
            }
        }
        String title = count == 1 ? "1 prueba nueva en Carreiras Galegas"
                : count + " pruebas nuevas en Carreiras Galegas";

        int flags = PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE;
        PendingIntent open = PendingIntent.getActivity(app, NOTIF_RACES, openTab(app, "carreras", 0), flags);
        Notification notif = new Notification.Builder(app, CHANNEL_RACES)
                .setSmallIcon(R.drawable.ic_notif_flag)
                .setColor(0xFF2F5BD3)
                .setContentTitle(title)
                .setContentText(text)
                .setStyle(new Notification.BigTextStyle().bigText(text))
                .setContentIntent(open)
                .setAutoCancel(true)
                .build();
        nm.notify(NOTIF_RACES, notif);
    }

    // ─── Pintado ───────────────────────────────────────────────────────────

    private void renderAll(Context context, AppWidgetManager manager, int[] ids, String note) {
        if (ids == null) {
            return;
        }
        for (int id : ids) {
            manager.updateAppWidget(id, build(context, id, note));
        }
    }

    private RemoteViews build(Context context, int widgetId, String note) {
        RemoteViews v = new RemoteViews(context.getPackageName(), R.layout.widget_salud);

        SharedPreferences prefs = Config.prefs(context);
        String raw = prefs.getString(Config.KEY_SNAPSHOT, null);
        long at = prefs.getLong(Config.KEY_SNAPSHOT_AT, 0);

        JSONObject d = null;
        if (raw != null) {
            try {
                d = new JSONObject(raw);
            } catch (Exception ignored) {
                // snapshot corrupto: se trata como si no hubiera nada
            }
        }

        v.setTextViewText(R.id.widget_battery_label, dotLabel("Batería", context.getColor(R.color.w_bat)));
        v.setTextViewText(R.id.widget_hr_label, dotLabel("FC reposo", context.getColor(R.color.w_hr)));
        v.setTextViewText(R.id.widget_sleep_label, dotLabel("Sueño", context.getColor(R.color.w_sleep)));

        if (d == null || !d.optBoolean("has_data", false)) {
            v.setTextViewText(R.id.widget_readiness, "—");
            v.setTextViewText(R.id.widget_readiness_status, "");
            v.setTextColor(R.id.widget_readiness, context.getColor(R.color.w_sub));
            v.setTextViewText(R.id.widget_steps, note != null ? note : "Abre la app y sincroniza");
            v.setProgressBar(R.id.widget_steps_bar, 100, 0, false);
            v.setTextViewText(R.id.widget_battery, "—");
            v.setTextViewText(R.id.widget_hr, "—");
            v.setTextViewText(R.id.widget_sleep, "—");
            v.setTextViewText(R.id.widget_form, "");
            v.setTextViewText(R.id.widget_updated, "");
            v.setViewVisibility(R.id.widget_workout_row, View.GONE);
            v.setViewVisibility(R.id.widget_race_row, View.GONE);
            wireClicks(context, v, widgetId);
            return v;
        }

        // Readiness con el mismo semáforo que la app: verde ≥70, ámbar ≥50, rojo por debajo
        int readiness = d.optInt("readiness", 0);
        int rc = readiness >= 70 ? Color.parseColor("#10B981") : readiness >= 50 ? Color.parseColor("#F59E0B")
                : readiness > 0 ? Color.parseColor("#EF4444") : context.getColor(R.color.w_sub);
        v.setTextViewText(R.id.widget_readiness, number(readiness));
        v.setTextColor(R.id.widget_readiness, rc);
        v.setTextViewText(R.id.widget_readiness_status, capitalize(d.optString("readiness_status", "")));
        v.setTextColor(R.id.widget_readiness_status, rc);

        v.setTextViewText(R.id.widget_battery, d.optInt("body_battery", 0) > 0 ? d.optInt("body_battery") + " %" : "—");
        v.setTextViewText(R.id.widget_hr, number(d.optInt("resting_hr", 0)));
        v.setTextViewText(R.id.widget_sleep, sleep(d.optString("sleep_text", "")));

        int steps = d.optInt("steps", 0);
        int goal = Math.max(1, d.optInt("steps_goal", 10000));
        v.setTextViewText(R.id.widget_steps, note != null ? note
                : String.format(ES, "%,d", steps) + " / " + String.format(ES, "%,d", goal) + " pasos");
        v.setProgressBar(R.id.widget_steps_bar, 100, Math.min(100, steps * 100 / goal), false);
        v.setTextViewText(R.id.widget_form, form(d));
        v.setTextViewText(R.id.widget_updated, ago(at));

        race(v, d.optJSONObject("race"));
        workout(context, v, d.optJSONObject("workout"));

        wireClicks(context, v, widgetId);
        return v;
    }

    /** «● Batería» con el punto del color de la métrica, como en la app. */
    private static CharSequence dotLabel(String label, int color) {
        SpannableString s = new SpannableString("● " + label);
        s.setSpan(new ForegroundColorSpan(color), 0, 1, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        return s;
    }

    /** «En 4 días» + «Rianxo · sáb 31 · 17:30 · 10K». Sin carrera apuntada esta semana, se oculta. */
    private static void race(RemoteViews v, JSONObject r) {
        if (r == null) {
            v.setViewVisibility(R.id.widget_race_row, View.GONE);
            return;
        }
        int days = r.optInt("days", 0);
        v.setTextViewText(R.id.widget_race_when, days <= 0 ? "Carrera hoy" : days == 1 ? "Carrera mañana" : "Carrera en " + days + " días");
        StringBuilder sb = new StringBuilder(r.optString("name", ""));
        for (String k : new String[]{"when", "time", "dist"}) {
            String x = r.optString(k, "");
            if (!x.isEmpty()) {
                sb.append(" · ").append(x);
            }
        }
        v.setTextViewText(R.id.widget_race, sb.toString());
        v.setViewVisibility(R.id.widget_race_row, View.VISIBLE);
    }

    /** «Base» en su color + «Hoy · Rodaje suave · 45 min». Sin plan, la fila se oculta. */
    private static void workout(Context context, RemoteViews v, JSONObject w) {
        if (w == null) {
            v.setViewVisibility(R.id.widget_workout_row, View.GONE);
            return;
        }
        int color;
        try {
            color = Color.parseColor(w.optString("color", "#94A3B8"));
        } catch (IllegalArgumentException e) {
            color = Color.parseColor("#94A3B8");
        }
        String kind = w.optString("kind", "");
        boolean done = w.optBoolean("done", false);
        v.setInt(R.id.widget_workout_bar, "setBackgroundColor", color);
        v.setTextViewText(R.id.widget_workout_kind, (done ? "✓ " : "") + (kind.isEmpty() ? "Entreno" : kind));
        v.setTextColor(R.id.widget_workout_kind, color);

        if (done) {
            // Hecho hoy: lo que hiciste y lo siguiente que toca
            StringBuilder sb = new StringBuilder("Hecho");
            // Nota frente al plan, si ya se calculó al abrir la app
            int score = w.optInt("score", -1);
            if (score >= 0) {
                sb.append(' ').append(score).append("/100");
            }
            String doneText = w.optString("done_text", "");
            if (!doneText.isEmpty()) {
                sb.append(" · ").append(doneText);
            }
            JSONObject next = w.optJSONObject("next");
            if (next != null) {
                String nk = next.optString("kind", "");
                sb.append("  →  ").append(next.optString("when", "")).append(' ')
                        .append(nk.isEmpty() ? next.optString("title", "") : nk);
            }
            v.setTextViewText(R.id.widget_workout, sb.toString());
            v.setTextColor(R.id.widget_workout, context.getColor(R.color.w_sub));
            v.setViewVisibility(R.id.widget_workout_row, View.VISIBLE);
            return;
        }

        StringBuilder sb = new StringBuilder(w.optString("when", ""));
        String title = w.optString("title", "");
        // Si el título es solo el tipo ("Base"), no repetirlo
        if (!title.isEmpty() && !title.equalsIgnoreCase(kind)) {
            sb.append(" · ").append(title);
        }
        int min = w.optInt("minutes", 0);
        double km = w.optDouble("distance_km", 0);
        if (min > 0) {
            sb.append(" · ").append(min).append(" min");
        } else if (km > 0) {
            sb.append(String.format(ES, " · %.1f km", km));
        }
        v.setTextViewText(R.id.widget_workout, sb.toString());
        v.setTextColor(R.id.widget_workout, context.getColor(
                w.optBoolean("is_today", false) ? R.color.w_text : R.color.w_sub));
        v.setViewVisibility(R.id.widget_workout_row, View.VISIBLE);
    }

    /** «Cargando · Forma −7» con el estado en su color (los mismos que la pestaña Forma). */
    private static CharSequence form(JSONObject d) {
        String status = d.optString("form_status", "");
        double tsb = d.optDouble("tsb", 0);
        SpannableStringBuilder sb = new SpannableStringBuilder();
        if (!status.isEmpty()) {
            sb.append(capitalize(status));
            String c;
            switch (status) {
                case "desentrenado": c = "#3B82F6"; break;
                case "descansado": c = "#10B981"; break;
                case "equilibrado": c = "#F59E0B"; break;
                case "cargando": c = "#F97316"; break;
                case "fatigado": c = "#EF4444"; break;
                default: c = null;
            }
            if (c != null) {
                sb.setSpan(new ForegroundColorSpan(Color.parseColor(c)), 0, sb.length(), Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
            }
        }
        if (d.optDouble("ctl", 0) > 0 || tsb != 0) {
            if (sb.length() > 0) {
                sb.append(" · ");
            }
            sb.append(String.format(ES, "Forma %+.0f", tsb).replace('-', '−'));
        }
        return sb;
    }

    private static String capitalize(String s) {
        return s.isEmpty() ? s : Character.toUpperCase(s.charAt(0)) + s.substring(1);
    }

    private static String number(int value) {
        return value > 0 ? String.valueOf(value) : "—";
    }

    /** "7h 20m" ocupa demasiado en el widget: "7h20". */
    private static String sleep(String formatted) {
        if (formatted == null || formatted.isEmpty()) {
            return "—";
        }
        return formatted.replace(" ", "").replace("m", "");
    }

    private static String ago(long timestamp) {
        if (timestamp <= 0) {
            return "";
        }
        long min = (System.currentTimeMillis() - timestamp) / 60000;
        if (min < 1) {
            return "ahora";
        }
        if (min < 60) {
            return "hace " + min + " min";
        }
        long hours = min / 60;
        if (hours < 24) {
            return "hace " + hours + " h";
        }
        return "hace " + (hours / 24) + " d";
    }

    /** Abre la app en una pestaña concreta (con la app ya abierta llega por onNewIntent). */
    static Intent openTab(Context context, String tab, int id) {
        return new Intent(context, MainActivity.class)
                .setAction(Intent.ACTION_VIEW)
                .setData(Uri.parse("misalud://" + tab + "/" + id))
                .putExtra(MainActivity.EXTRA_TAB, tab)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
    }

    private void wireClicks(Context context, RemoteViews v, int widgetId) {
        int flags = PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE;

        Intent open = new Intent(context, MainActivity.class)
                .setAction(Intent.ACTION_MAIN)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        v.setOnClickPendingIntent(R.id.widget_root,
                PendingIntent.getActivity(context, widgetId, open, flags));

        // La fila del entreno abre la pestaña Coach; la de la carrera, Carreras
        v.setOnClickPendingIntent(R.id.widget_workout_row,
                PendingIntent.getActivity(context, widgetId + 100000, openTab(context, "coach", widgetId), flags));
        v.setOnClickPendingIntent(R.id.widget_race_row,
                PendingIntent.getActivity(context, widgetId + 200000, openTab(context, "carreras", widgetId), flags));

        Intent refresh = new Intent(context, SaludWidget.class)
                .setAction(ACTION_REFRESH)
                // Datos distintos por widget: evita que PendingIntent reutilice el mismo intent.
                .setData(Uri.parse("misalud://widget/" + widgetId));
        v.setOnClickPendingIntent(R.id.widget_refresh,
                PendingIntent.getBroadcast(context, widgetId, refresh, flags));
    }
}
