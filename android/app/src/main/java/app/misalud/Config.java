package app.misalud;

import android.content.Context;
import android.content.SharedPreferences;

/** URL del despliegue, compartida entre la app y el widget. */
final class Config {

    static final String PREFS = "mi_salud";
    static final String KEY_URL = "base_url";
    static final String KEY_BG = "bg_color";
    static final String KEY_SNAPSHOT = "widget_snapshot";
    static final String KEY_SNAPSHOT_AT = "widget_snapshot_at";

    private Config() {
    }

    static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    static String baseUrl(Context context) {
        return normalize(prefs(context).getString(KEY_URL, BuildConfig.APP_URL));
    }

    /** Añade el esquema si falta y quita las barras finales. */
    static String normalize(String url) {
        String v = url == null ? "" : url.trim();
        if (v.isEmpty()) {
            return v;
        }
        if (!v.startsWith("http://") && !v.startsWith("https://")) {
            v = "https://" + v;
        }
        while (v.endsWith("/")) {
            v = v.substring(0, v.length() - 1);
        }
        return v;
    }
}
