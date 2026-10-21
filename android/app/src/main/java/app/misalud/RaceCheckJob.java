package app.misalud;

import android.app.job.JobInfo;
import android.app.job.JobParameters;
import android.app.job.JobScheduler;
import android.app.job.JobService;
import android.content.ComponentName;
import android.content.Context;

/**
 * Comprobación periódica (cada ~3 h, con red): baja /api/widget, avisa si hay
 * pruebas nuevas en Carreiras Galegas y repinta el widget. Va aparte del
 * widget para que la notificación llegue aunque no lo tengas en la pantalla.
 * Android decide el momento exacto para ahorrar batería.
 */
public class RaceCheckJob extends JobService {

    private static final int JOB_ID = 1001;
    private static final long PERIOD_MS = 3 * 60 * 60 * 1000L;

    /** Programa la comprobación si aún no lo está (se puede llamar a menudo). */
    static void schedule(Context context) {
        JobScheduler js = context.getSystemService(JobScheduler.class);
        if (js == null || js.getPendingJob(JOB_ID) != null) {
            return;
        }
        js.schedule(new JobInfo.Builder(JOB_ID, new ComponentName(context, RaceCheckJob.class))
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                .setPeriodic(PERIOD_MS)
                .setPersisted(true)
                .build());
    }

    @Override
    public boolean onStartJob(JobParameters params) {
        final Context app = getApplicationContext();
        new Thread(() -> {
            boolean retry = false;
            try {
                SaludWidget.notifyNewRaces(app, SaludWidget.fetchSnapshot(app));
                SaludWidget.refreshAllWidgets(app);
            } catch (SaludWidget.Unauthorized e) {
                // Sin sesión no hay nada que hacer hasta que entres en la app
            } catch (Exception e) {
                retry = true;
            }
            jobFinished(params, retry);
        }).start();
        return true;
    }

    @Override
    public boolean onStopJob(JobParameters params) {
        return true;
    }
}
