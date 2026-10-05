package app.misalud;

import android.content.Context;
import android.content.SharedPreferences;
import android.webkit.CookieManager;

/** URL del despliegue, compartida entre la app y el widget. */
final class Config {

    static final String PREFS = "mi_salud";
    static final String KEY_URL = "base_url";
    static final String KEY_BG = "bg_color";
    static final String KEY_SNAPSHOT = "widget_snapshot";
    static final String KEY_SNAPSHOT_AT = "widget_snapshot_at";
    static final String KEY_TOKEN = "auth_token";
    static final String AUTH_COOKIE = "ms_auth";

    private Config() {
    }

    static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    static String baseUrl(Context context) {
        return normalize(prefs(context).getString(KEY_URL, BuildConfig.APP_URL));
    }

    /**
     * Sesión de la API: la cookie que pone /api/login al entrar en la app.
     * Se copia a las preferencias para que el widget no dependa de la WebView.
     */
    static String token(Context context) {
        String t = prefs(context).getString(KEY_TOKEN, "");
        if (t.isEmpty()) {
            t = syncToken(context);
        }
        return t;
    }

    /** Lee la cookie de sesión de la WebView y la guarda; devuelve la que haya. */
    static String syncToken(Context context) {
        String found = "";
        try {
            String cookies = CookieManager.getInstance().getCookie(baseUrl(context));
            if (cookies != null) {
                for (String part : cookies.split(";")) {
                    String c = part.trim();
                    if (c.startsWith(AUTH_COOKIE + "=")) {
                        found = c.substring(AUTH_COOKIE.length() + 1);
                    }
                }
            }
        } catch (Exception ignored) {
            // Sin WebView disponible: nos quedamos con lo guardado
        }
        if (!found.isEmpty()) {
            prefs(context).edit().putString(KEY_TOKEN, found).apply();
        }
        return found;
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
