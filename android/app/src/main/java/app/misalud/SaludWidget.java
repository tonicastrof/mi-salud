package app.misalud;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Build;
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
                String body = get(Config.baseUrl(app) + "/api/widget");
                new JSONObject(body); // valida antes de guardar
                SharedPreferences.Editor e = Config.prefs(app).edit();
                e.putString(Config.KEY_SNAPSHOT, body);
                e.putLong(Config.KEY_SNAPSHOT_AT, System.currentTimeMillis());
                e.apply();
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

    private static String get(String url) throws Exception {
        HttpURLConnection conn = (HttpURLConnection) new URL(url).openConnection();
        try {
            conn.setRequestMethod("GET");
            conn.setConnectTimeout(5000);
            conn.setReadTimeout(6000);
            conn.setRequestProperty("Accept", "application/json");
            conn.setRequestProperty("User-Agent", "MiSaludWidget/" + BuildConfig.VERSION_NAME);
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
        v.setTextViewText(R.id.widget_readiness, number(d.optInt("readiness", 0)));

        v.setTextViewText(R.id.widget_form, note != null ? note : form(d));
        v.setTextViewText(R.id.widget_updated, ago(at));

        wireClicks(context, v, widgetId);
        return v;
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

        Intent refresh = new Intent(context, SaludWidget.class)
                .setAction(ACTION_REFRESH)
                // Datos distintos por widget: evita que PendingIntent reutilice el mismo intent.
                .setData(Uri.parse("misalud://widget/" + widgetId));
        v.setOnClickPendingIntent(R.id.widget_refresh,
                PendingIntent.getBroadcast(context, widgetId, refresh, flags));
    }
}
