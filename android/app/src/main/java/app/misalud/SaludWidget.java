package app.misalud;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.view.View;
import android.widget.RemoteViews;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.Locale;

/**
 * Widget de pantalla de inicio: lee /api/widget (los cuatro números del día) y
 * los pinta. Guarda la última respuesta, así que al añadirlo o al quedarse sin
 * cobertura enseña lo último que sabía en vez de quedarse en blanco.
 */
public class SaludWidget extends AppWidgetProvider {

    static final String ACTION_REFRESH = "app.misalud.action.REFRESH";
    private static final Locale ES = new Locale("es", "ES");

    @Override
    public void onUpdate(Context context, AppWidgetManager manager, int[] ids) {
        renderAll(context, manager, ids, null);
        fetchAndRender(context, ids);
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
                String body = get(Config.baseUrl(app) + "/api/widget", Config.token(app));
                new JSONObject(body); // valida antes de guardar
                SharedPreferences.Editor e = Config.prefs(app).edit();
                e.putString(Config.KEY_SNAPSHOT, body);
                e.putLong(Config.KEY_SNAPSHOT_AT, System.currentTimeMillis());
                e.apply();
            } catch (Unauthorized ex) {
                // La sesión guardada ya no vale (o nunca hubo): se vuelve a leer
                // de la WebView y, si tampoco, hay que entrar en la app.
                Config.prefs(app).edit().remove(Config.KEY_TOKEN).apply();
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

    private static final class Unauthorized extends Exception {
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

        if (d == null || !d.optBoolean("has_data", false)) {
            v.setTextViewText(R.id.widget_steps, "Sin datos todavía");
            v.setProgressBar(R.id.widget_steps_bar, 100, 0, false);
            v.setTextViewText(R.id.widget_battery, "—");
            v.setTextViewText(R.id.widget_hr, "—");
            v.setTextViewText(R.id.widget_sleep, "—");
            v.setTextViewText(R.id.widget_readiness, "—");
            v.setTextViewText(R.id.widget_form, note != null ? note : "Abre la app y sincroniza");
            v.setTextViewText(R.id.widget_updated, "");
            v.setViewVisibility(R.id.widget_workout_row, View.GONE);
            wireClicks(context, v, widgetId);
            return v;
        }

        int steps = d.optInt("steps", 0);
        int goal = Math.max(1, d.optInt("steps_goal", 10000));
        v.setTextViewText(R.id.widget_steps, String.format(ES, "%,d", steps) + " / "
                + String.format(ES, "%,d", goal) + " pasos");
        v.setProgressBar(R.id.widget_steps_bar, 100, Math.min(100, steps * 100 / goal), false);

        v.setTextViewText(R.id.widget_battery, number(d.optInt("body_battery", 0)));
        v.setTextViewText(R.id.widget_hr, number(d.optInt("resting_hr", 0)));
        v.setTextViewText(R.id.widget_sleep, sleep(d.optString("sleep_text", "")));
        int readiness = d.optInt("readiness", 0);
        v.setTextViewText(R.id.widget_readiness, number(readiness));
        // Mismo semáforo que la app: verde ≥70, ámbar ≥50, rojo por debajo
        v.setTextColor(R.id.widget_readiness, Color.parseColor(
                readiness >= 70 ? "#10B981" : readiness >= 50 ? "#F59E0B" : readiness > 0 ? "#EF4444" : "#64748B"));

        v.setTextViewText(R.id.widget_form, note != null ? note : form(d));
        v.setTextViewText(R.id.widget_updated, ago(at));
        workout(v, d.optJSONObject("workout"));

        wireClicks(context, v, widgetId);
        return v;
    }

    /** "● Umbral" en su color + "Hoy · Series 5x1000 · 50 min". Sin plan, la fila se oculta. */
    private static void workout(RemoteViews v, JSONObject w) {
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
        v.setTextViewText(R.id.widget_workout_kind,
                (done ? "✓" : "●") + (kind.isEmpty() ? "" : " " + kind));
        v.setTextColor(R.id.widget_workout_kind, color);

        if (done) {
            // Hecho hoy: lo que hiciste y lo siguiente que toca
            StringBuilder sb = new StringBuilder("Hecho");
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
            v.setTextColor(R.id.widget_workout, Color.parseColor("#94A3B8"));
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
        v.setTextColor(R.id.widget_workout,
                w.optBoolean("is_today", false) ? Color.parseColor("#F1F5F9") : Color.parseColor("#94A3B8"));
        v.setViewVisibility(R.id.widget_workout_row, View.VISIBLE);
    }

    private static String form(JSONObject d) {
        String emoji = d.optString("form_emoji", "");
        String status = d.optString("form_status", "");
        StringBuilder sb = new StringBuilder();
        if (!emoji.isEmpty()) {
            sb.append(emoji).append(' ');
        }
        if (!status.isEmpty()) {
            sb.append(capitalize(status));
        }
        double ctl = d.optDouble("ctl", 0);
        double tsb = d.optDouble("tsb", 0);
        if (ctl > 0 || tsb != 0) {
            if (sb.length() > 0) {
                sb.append(" · ");
            }
            sb.append(String.format(ES, "Fitness %.0f · Forma %+.0f", ctl, tsb));
        }
        return sb.toString();
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

    private void wireClicks(Context context, RemoteViews v, int widgetId) {
        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            flags |= PendingIntent.FLAG_IMMUTABLE;
        }

        Intent open = new Intent(context, MainActivity.class)
                .setAction(Intent.ACTION_MAIN)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        v.setOnClickPendingIntent(R.id.widget_root,
                PendingIntent.getActivity(context, widgetId, open, flags));

        // La fila del entreno abre directamente la pestaña Coach
        Intent coach = new Intent(context, MainActivity.class)
                .setAction(Intent.ACTION_VIEW)
                .setData(Uri.parse("misalud://coach/" + widgetId))
                .putExtra(MainActivity.EXTRA_TAB, "coach")
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        v.setOnClickPendingIntent(R.id.widget_workout_row,
                PendingIntent.getActivity(context, widgetId + 100000, coach, flags));

        Intent refresh = new Intent(context, SaludWidget.class)
                .setAction(ACTION_REFRESH)
                // Datos distintos por widget: evita que PendingIntent reutilice el mismo intent.
                .setData(Uri.parse("misalud://widget/" + widgetId));
        v.setOnClickPendingIntent(R.id.widget_refresh,
                PendingIntent.getBroadcast(context, widgetId, refresh, flags));
    }
}
