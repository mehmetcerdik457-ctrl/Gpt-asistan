package com.mehmetcerdik.ownerai;

import android.content.ComponentName;
import android.content.Intent;
import android.content.ServiceConnection;
import android.content.pm.PackageManager;
import android.os.Bundle;
import android.os.IBinder;
import android.os.RemoteException;
import android.provider.Settings;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import androidx.appcompat.app.AppCompatActivity;

import rikka.shizuku.Shizuku;

public final class OwnerControlPlaneActivity extends AppCompatActivity {
    private static final int SHIZUKU_PERMISSION_REQUEST = 5101;

    private TextView status;
    private TextView result;

    private final Shizuku.OnRequestPermissionResultListener shizukuPermissionListener =
            this::onShizukuPermissionResult;

    private final Shizuku.UserServiceArgs shizukuServiceArgs =
            new Shizuku.UserServiceArgs(
                    new ComponentName(
                            "com.mehmetcerdik.ownerai",
                            ShizukuShellService.class.getName()))
                    .daemon(false)
                    .processNameSuffix("restricted_settings_unlock")
                    .debuggable(false)
                    .version(1);

    private final ServiceConnection shizukuServiceConnection = new ServiceConnection() {
        @Override
        public void onServiceConnected(ComponentName name, IBinder binder) {
            if (binder == null || !binder.pingBinder()) {
                result.setText("SHIZUKU_USER_SERVICE_INVALID_BINDER");
                return;
            }
            IShizukuShellService service = IShizukuShellService.Stub.asInterface(binder);
            try {
                String evidence = service.unlockBridgeAccessibility();
                result.setText(evidence);
            } catch (RemoteException e) {
                result.setText("SHIZUKU_REMOTE_ERROR: " + e.getClass().getSimpleName());
            } finally {
                try {
                    Shizuku.unbindUserService(
                            shizukuServiceArgs,
                            shizukuServiceConnection,
                            true);
                } catch (Throwable ignored) {
                }
            }
            status.postDelayed(() -> OwnerControlPlaneActivity.this.refresh(), 1000L);
        }

        @Override
        public void onServiceDisconnected(ComponentName name) {
        }
    };

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        Shizuku.addRequestPermissionResultListener(shizukuPermissionListener);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int p = (int)(16 * getResources().getDisplayMetrics().density);
        root.setPadding(p, p, p, p);

        TextView title = new TextView(this);
        title.setText("MEHMET OWNER — HARDENED CONTROL PLANE");
        title.setTextSize(22f);
        root.addView(title);

        TextView note = new TextView(this);
        note.setText("Production privileged actions run only through Owner Brain → Policy → signer-pinned Bridge → postcondition. Direct click/type/swipe bypass controls are disabled.");
        root.addView(note);

        status = new TextView(this);
        result = new TextView(this);
        result.setTextIsSelectable(true);
        root.addView(status);
        root.addView(result);

        Button refresh = new Button(this);
        refresh.setText("Bridge Durumunu Yenile");
        refresh.setOnClickListener(v -> OwnerAuth.require(this, this::refresh, s -> result.setText(s)));
        root.addView(refresh);

        Button access = new Button(this);
        access.setText("Bridge Accessibility Ayarlarını Aç");
        access.setOnClickListener(v -> OwnerAuth.requireFresh(this,
                () -> startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)),
                s -> result.setText(s)));
        root.addView(access);

        Button shizukuUnlock = new Button(this);
        shizukuUnlock.setText("Shizuku ile Bridge Kilidini Aç ve Accessibility'yi Etkinleştir");
        shizukuUnlock.setOnClickListener(v -> OwnerAuth.requireFresh(
                this,
                this::unlockBridgeAccessibilityWithShizuku,
                s -> result.setText(s)));
        root.addView(shizukuUnlock);

        Button arm = new Button(this);
        arm.setText("Secure Session ile Bridge'i Kısa Süreli Arm Et");
        arm.setOnClickListener(v -> OwnerAuth.requireFresh(this, () -> {
            long ttl = Math.min(Math.max(1_000L, OwnerSession.remainingMs()), 120_000L);
            show(BridgeClient.arm(this, ttl));
        }, s -> result.setText(s)));
        root.addView(arm);

        Button stop = new Button(this);
        stop.setText("ACİL DURDUR");
        stop.setOnClickListener(v -> OwnerAuth.require(this, () -> {
            show(BridgeClient.stop(this));
            OwnerSession.clear();
        }, s -> result.setText(s)));
        root.addView(stop);

        Button brain = new Button(this);
        brain.setText("MEHMET Owner Brain");
        brain.setOnClickListener(v -> OwnerAuth.require(this,
                () -> startActivity(new Intent(this, OwnerBrainActivity.class)),
                s -> result.setText(s)));
        root.addView(brain);

        ScrollView scroll = new ScrollView(this);
        scroll.addView(root);
        setContentView(scroll);
        redactUnlessAuthorized();
    }

    @Override protected void onDestroy() {
        Shizuku.removeRequestPermissionResultListener(shizukuPermissionListener);
        super.onDestroy();
    }

    @Override protected void onResume() {
        super.onResume();
        redactUnlessAuthorized();
    }

    private void onShizukuPermissionResult(int requestCode, int grantResult) {
        if (requestCode != SHIZUKU_PERMISSION_REQUEST) return;
        if (grantResult == PackageManager.PERMISSION_GRANTED) {
            bindShizukuUnlockService();
        } else {
            result.setText("SHIZUKU_PERMISSION_DENIED");
        }
    }

    private void unlockBridgeAccessibilityWithShizuku() {
        try {
            if (!Shizuku.pingBinder()) {
                result.setText("SHIZUKU_NOT_RUNNING");
                return;
            }
            if (Shizuku.isPreV11()) {
                result.setText("SHIZUKU_PRE_V11_UNSUPPORTED");
                return;
            }
            if (Shizuku.checkSelfPermission() == PackageManager.PERMISSION_GRANTED) {
                bindShizukuUnlockService();
                return;
            }
            if (Shizuku.shouldShowRequestPermissionRationale()) {
                result.setText("SHIZUKU_PERMISSION_DENIED_DONT_ASK");
                return;
            }
            Shizuku.requestPermission(SHIZUKU_PERMISSION_REQUEST);
        } catch (Throwable t) {
            result.setText("SHIZUKU_UNAVAILABLE: " + t.getClass().getSimpleName());
        }
    }

    private void bindShizukuUnlockService() {
        try {
            result.setText("SHIZUKU_UNLOCK_RUNNING");
            Shizuku.bindUserService(shizukuServiceArgs, shizukuServiceConnection);
        } catch (Throwable t) {
            result.setText("SHIZUKU_BIND_FAILED: " + t.getClass().getSimpleName());
        }
    }

    private void redactUnlessAuthorized() {
        if (status == null || result == null) return;
        if (!OwnerSession.isAuthorized(this)) {
            status.setText("OWNER_AUTH_REQUIRED");
            result.setText("OWNER_AUTH_REQUIRED");
            return;
        }
        refresh();
    }

    private void refresh() {
        show(BridgeClient.status(this));
    }

    private void show(Bundle b) {
        if (b == null) {
            result.setText("NULL");
            return;
        }
        status.setText(
                "bridgeSignerMatch=" + BridgeClient.verifyBridge(this)
                        + "\nownerSession=" + OwnerSession.classification()
                        + "\nownerSessionRemainingMs=" + OwnerSession.remainingMs()
                        + "\nservice=" + b.getBoolean("service_connected", false)
                        + "\narmed=" + b.getBoolean("armed", false)
                        + "\nemergency=" + b.getBoolean("emergency_stop", true)
                        + "\nworkerInstalled=" + b.getBoolean("worker_installed", false)
                        + "\nworkerSignerMatch=" + b.getBoolean("worker_signer_match", false)
                        + "\nworkerExpectedSigner=" + b.getString("worker_expected_signer", "")
                        + "\nworkerObservedSigners=" + b.getString("worker_observed_signers", "")
                        + "\nactivePackage=" + b.getString("active_package", "")
                        + "\nstatus=" + b.getString("status", "")
                        + "\nfailure=" + b.getString("failure", "")
        );
        String snapshot = b.getString("snapshot", "");
        if (snapshot.length() > 12000) snapshot = snapshot.substring(0, 12000) + "\n…[kısaltıldı]";
        result.setText(snapshot.isEmpty() ? b.toString() : snapshot);
    }
}
