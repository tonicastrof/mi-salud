package app.misalud;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.text.InputType;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

/**
 * Envoltorio nativo del dashboard web de Mi Salud: una WebView a pantalla
 * completa apuntando al despliegue de Vercel, con puente de portapapeles,
 * color de barras de sistema sincronizado con el tema de la web y pantalla
 * de error propia cuando no hay conexión.
 */
public class MainActivity extends Activity {

    private static final String BRIDGE = "MiSaludNative";
    private static final long WIDGET_MAX_AGE_MS = 10 * 60 * 1000;

    private FrameLayout root;
    private WebView web;
    private View errorView;
    private String baseUrl;
    private boolean pageFailed;
    private int bgColor;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        SharedPreferences prefs = Config.prefs(this);
        baseUrl = Config.baseUrl(this);
        bgColor = prefs.getInt(Config.KEY_BG, 0xFF0A0A0F);

        root = new FrameLayout(this);
        root.setBackgroundColor(bgColor);

        web = new WebView(this);
        configureWebView(web);
        root.addView(web, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT));

        setContentView(root);
        applyInsets();
        applyBarAppearance(bgColor);

        if (savedInstanceState != null) {
            web.restoreState(savedInstanceState);
        } else {
            web.loadUrl(baseUrl);
        }
    }

    // ─── WebView ───────────────────────────────────────────────────────────

    private void configureWebView(WebView w) {
        WebSettings s = w.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        s.setBuiltInZoomControls(false);
        s.setSupportZoom(false);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);
        s.setUserAgentString(s.getUserAgentString() + " MiSaludApp/" + BuildConfig.VERSION_NAME);

        w.setBackgroundColor(bgColor);
        w.setOverScrollMode(View.OVER_SCROLL_NEVER);
        w.addJavascriptInterface(new Bridge(), BRIDGE);

        w.setDownloadListener((url, ua, disposition, mime, size) -> openExternally(Uri.parse(url)));

        w.setWebChromeClient(new WebChromeClient());
        w.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                if (isInternal(uri)) {
                    return false;
                }
                openExternally(uri);
                return true;
            }

            @Override
            public void onPageStarted(WebView view, String url, android.graphics.Bitmap favicon) {
                pageFailed = false;
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                if (pageFailed) {
                    return;
                }
                hideError();
                if (isInternal(Uri.parse(url))) {
                    view.evaluateJavascript(bridgeScript(), null);
                }
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) {
                    pageFailed = true;
                    showError(error.getDescription() == null ? "" : error.getDescription().toString());
                }
            }
        });
    }

    /** Script inyectado en la página: portapapeles nativo y color de fondo. */
    private String bridgeScript() {
        return "(function(){"
                + "if(window.__misalud)return;window.__misalud=1;"
                + "try{var w=function(t){" + BRIDGE + ".copy(String(t));return Promise.resolve()};"
                + "if(!navigator.clipboard){Object.defineProperty(navigator,'clipboard',{value:{}})}"
                + "navigator.clipboard.writeText=w}catch(e){}"
                + "var last='';setInterval(function(){try{"
                + "var c=getComputedStyle(document.body).backgroundColor;"
                + "if(c&&c!==last){last=c;" + BRIDGE + ".setBackground(c)}"
                + "}catch(e){}},600);"
                + "})();";
    }

    public class Bridge {
        @JavascriptInterface
        public void copy(String text) {
            runOnUiThread(() -> {
                ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
                if (cm == null) {
                    return;
                }
                cm.setPrimaryClip(ClipData.newPlainText("Mi Salud", text));
                // Android 13+ ya enseña su propio aviso al copiar.
                if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) {
                    Toast.makeText(MainActivity.this, "Copiado", Toast.LENGTH_SHORT).show();
                }
            });
        }

        @JavascriptInterface
        public void setBackground(String css) {
            Integer color = parseCssColor(css);
            if (color == null) {
                return;
            }
            runOnUiThread(() -> {
                bgColor = color;
                root.setBackgroundColor(bgColor);
                web.setBackgroundColor(bgColor);
                applyBarAppearance(bgColor);
                Config.prefs(MainActivity.this).edit().putInt(Config.KEY_BG, bgColor).apply();
            });
        }
    }

    // ─── Barras de sistema ─────────────────────────────────────────────────

    private void applyInsets() {
        root.setOnApplyWindowInsetsListener((v, insets) -> {
            int top, bottom, left, right;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                android.graphics.Insets bars = insets.getInsets(
                        WindowInsets.Type.systemBars() | WindowInsets.Type.ime()
                                | WindowInsets.Type.displayCutout());
                top = bars.top;
                bottom = bars.bottom;
                left = bars.left;
                right = bars.right;
            } else {
                top = insets.getSystemWindowInsetTop();
                bottom = insets.getSystemWindowInsetBottom();
                left = insets.getSystemWindowInsetLeft();
                right = insets.getSystemWindowInsetRight();
            }
            v.setPadding(left, top, right, bottom);
            return insets;
        });
    }

    /** Iconos de la barra de estado claros u oscuros según el fondo de la web. */
    private void applyBarAppearance(int color) {
        boolean lightBackground = luminance(color) > 0.55;
        View decor = getWindow().getDecorView();
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            WindowInsetsController c = decor.getWindowInsetsController();
            if (c != null) {
                int mask = WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS
                        | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS;
                c.setSystemBarsAppearance(lightBackground ? mask : 0, mask);
            }
        } else {
            int flags = decor.getSystemUiVisibility();
            int mask = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
            decor.setSystemUiVisibility(lightBackground ? (flags | mask) : (flags & ~mask));
        }
    }

    private static double luminance(int color) {
        return (0.299 * Color.red(color) + 0.587 * Color.green(color) + 0.114 * Color.blue(color)) / 255.0;
    }

    /** Acepta "rgb(r,g,b)", "rgba(r,g,b,a)" y "#rrggbb". */
    static Integer parseCssColor(String css) {
        if (css == null) {
            return null;
        }
        String v = css.trim();
        try {
            if (v.startsWith("#")) {
                return Color.parseColor(v);
            }
            if (v.startsWith("rgb")) {
                String inner = v.substring(v.indexOf('(') + 1, v.lastIndexOf(')'));
                String[] parts = inner.split("[,/ ]+");
                if (parts.length < 3) {
                    return null;
                }
                int r = clamp(Math.round(Float.parseFloat(parts[0])));
                int g = clamp(Math.round(Float.parseFloat(parts[1])));
                int b = clamp(Math.round(Float.parseFloat(parts[2])));
                return Color.rgb(r, g, b);
            }
        } catch (RuntimeException e) {
            return null;
        }
        return null;
    }

    private static int clamp(int v) {
        return v < 0 ? 0 : (v > 255 ? 255 : v);
    }

    // ─── Pantalla de error ─────────────────────────────────────────────────

    private void showError(String detail) {
        if (errorView == null) {
            errorView = buildErrorView();
            root.addView(errorView, new FrameLayout.LayoutParams(
                    FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT));
        }
        TextView msg = errorView.findViewWithTag("detail");
        msg.setText(baseUrl + (detail.isEmpty() ? "" : "\n" + detail));
        errorView.setVisibility(View.VISIBLE);
        web.setVisibility(View.GONE);
    }

    private void hideError() {
        if (errorView != null) {
            errorView.setVisibility(View.GONE);
        }
        web.setVisibility(View.VISIBLE);
    }

    private View buildErrorView() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setGravity(Gravity.CENTER);
        box.setBackgroundColor(0xFF0A0A0F);
        int pad = dp(24);
        box.setPadding(pad, pad, pad, pad);

        TextView title = new TextView(this);
        title.setText("No se pudo cargar Mi Salud");
        title.setTextColor(0xFFF1F5F9);
        title.setTextSize(TypedValue.COMPLEX_UNIT_SP, 18);
        title.setGravity(Gravity.CENTER);

        TextView detail = new TextView(this);
        detail.setTag("detail");
        detail.setTextColor(0xFF94A3B8);
        detail.setTextSize(TypedValue.COMPLEX_UNIT_SP, 13);
        detail.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams dlp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        dlp.topMargin = dp(10);
        detail.setLayoutParams(dlp);

        Button retry = new Button(this);
        retry.setText("Reintentar");
        retry.setOnClickListener(v -> {
            hideError();
            web.loadUrl(baseUrl);
        });

        Button change = new Button(this);
        change.setText("Cambiar URL");
        change.setOnClickListener(v -> askForUrl());

        box.addView(title);
        box.addView(detail);
        box.addView(retry);
        box.addView(change);
        return box;
    }

    private void askForUrl() {
        EditText input = new EditText(this);
        input.setInputType(InputType.TYPE_TEXT_VARIATION_URI);
        input.setText(baseUrl);
        input.setSelectAllOnFocus(true);

        new AlertDialog.Builder(this)
                .setTitle("URL del despliegue")
                .setView(input)
                .setPositiveButton("Guardar", (d, which) -> {
                    String url = Config.normalize(input.getText().toString());
                    if (url.isEmpty()) {
                        return;
                    }
                    baseUrl = url;
                    Config.prefs(this).edit().putString(Config.KEY_URL, url).apply();
                    hideError();
                    web.loadUrl(baseUrl);
                })
                .setNegativeButton("Cancelar", null)
                .show();
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    // ─── Navegación y ciclo de vida ────────────────────────────────────────

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) {
            web.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        web.saveState(outState);
    }

    @Override
    protected void onPause() {
        web.onPause();
        super.onPause();
    }

    @Override
    protected void onResume() {
        super.onResume();
        web.onResume();
        refreshWidgetIfStale();
    }

    /** Si el widget enseña datos viejos, aprovecha que abres la app para actualizarlo. */
    private void refreshWidgetIfStale() {
        long at = Config.prefs(this).getLong(Config.KEY_SNAPSHOT_AT, 0);
        if (System.currentTimeMillis() - at < WIDGET_MAX_AGE_MS) {
            return;
        }
        sendBroadcast(new Intent(this, SaludWidget.class).setAction(SaludWidget.ACTION_REFRESH));
    }

    @Override
    protected void onDestroy() {
        root.removeView(web);
        web.destroy();
        super.onDestroy();
    }

    // ─── Utilidades ────────────────────────────────────────────────────────

    private boolean isInternal(Uri uri) {
        String host = uri.getHost();
        Uri base = Uri.parse(baseUrl);
        return host != null && host.equalsIgnoreCase(base.getHost());
    }

    private void openExternally(Uri uri) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, uri).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        } catch (ActivityNotFoundException e) {
            Toast.makeText(this, "No hay ninguna app para abrir ese enlace", Toast.LENGTH_SHORT).show();
        }
    }
}
