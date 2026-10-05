package com.mehmetcerdik.ownerai;

import android.content.ComponentName;
import android.content.Intent;
import android.content.ServiceConnection;
import android.content.pm.PackageManager;
import android.os.Bundle;
import android.os.IBinder;
import android.os.RemoteException;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.security.MessageDigest;
import java.util.Locale;
import android.provider.Settings;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import androidx.appcompat.app.AppCompatActivity;

import rikka.shizuku.Shizuku;

public final class OwnerControlPlaneActivity extends AppCompatActivity {
    private static final int SHIZUKU_PERMISSION_REQUEST = 5101;
    private static final String EMBEDDED_BRIDGE_ASSET = "MEHMET_OWNER_BRIDGE_1.2.1_VC4_GEN2_SIGNED.apk";
    private static final String EMBEDDED_BRIDGE_SHA256 = "b3d950746e92bf09fdb9730cbe1a7d770e7363a104852182cc3b1d80542b33b4";
    private static final int MAX_EMBEDDED_BRIDGE_BYTES = 2 * 1024 * 1024;

    private TextView status;
    private TextView result;

    private Shizuku.OnRequestPermissionResultListener shizukuPermissionListener;
    private Shizuku.UserServiceArgs shizukuServiceArgs;
    private boolean shizukuListenerRegistered;

    private final ServiceConnection shizukuServiceConnection = new ServiceConnection() {
        @Override
        public void onServiceConnected(ComponentName name, IBinder binder) {
            if (binder == null || !binder.pingBinder()) {
                result.setText("SHIZUKU_USER_SERVICE_INVALID_BINDER");
                return;
            }
            IShizukuShellService service = IShizukuShellService.Stub.asInterface(binder);
            try {
                byte[] bridgeApk = readAndVerifyEmbeddedBridge();
                String evidence = service.bootstrapBridge(bridgeApk);
                result.setText(evidence);
            } catch (Throwable e) {
                result.setText("ONE_TAP_BOOTSTRAP_ERROR:" + e.getClass().getSimpleName()
                        + ":" + (e.getMessage() == null ? "" : e.getMessage()));
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
        shizukuUnlock.setText("TEK DOKUNUŞ KURULUM: Bridge 1.2.1 + İzinler");
        shizukuUnlock.setOnClickListener(v -> OwnerAuth.requireFresh(
                this,
                this::bootstrapBridgeWithShizuku,
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
        if (shizukuListenerRegistered && shizukuPermissionResultListenerReady()) {
            try {
                Shizuku.removeRequestPermissionResultListener(shizukuPermissionListener);
            } catch (Throwable ignored) {
            }
        }
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

    private void bootstrapBridgeWithShizuku() {
        try {
            ensureShizukuObjects();
            if (!Shizuku.pingBinder()) {
                try {
                    Intent launch = getPackageManager().getLaunchIntentForPackage("moe.shizuku.privileged.api");
                    if (launch != null) startActivity(launch);
                } catch (Throwable ignored) {
                }
                result.setText("SHIZUKU_NOT_RUNNING_OPENED_IF_AVAILABLE");
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

    private byte[] readAndVerifyEmbeddedBridge() throws Exception {
        try (InputStream in = getAssets().open(EMBEDDED_BRIDGE_ASSET);
             ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8192];
            int total = 0;
            for (int n; (n = in.read(buffer)) > 0; ) {
                total += n;
                if (total > MAX_EMBEDDED_BRIDGE_BYTES) {
                    throw new SecurityException("EMBEDDED_BRIDGE_TOO_LARGE");
                }
                out.write(buffer, 0, n);
            }
            byte[] bytes = out.toByteArray();
            String actual = sha256(bytes);
            if (!EMBEDDED_BRIDGE_SHA256.equals(actual)) {
                throw new SecurityException("EMBEDDED_BRIDGE_HASH_MISMATCH");
            }
            return bytes;
        }
    }

    private static String sha256(byte[] bytes) throws Exception {
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(bytes);
        StringBuilder out = new StringBuilder();
        for (byte b : digest) out.append(String.format(Locale.ROOT, "%02x", b & 0xff));
        return out.toString();
    }

    private void bindShizukuUnlockService() {
        try {
            ensureShizukuObjects();
            result.setText("SHIZUKU_UNLOCK_RUNNING");
            Shizuku.bindUserService(shizukuServiceArgs, shizukuServiceConnection);
        } catch (Throwable t) {
            result.setText("SHIZUKU_BIND_FAILED: " + t.getClass().getSimpleName());
        }
    }

    private void ensureShizukuObjects() {
        if (shizukuServiceArgs == null) {
            shizukuServiceArgs = new Shizuku.UserServiceArgs(
                    new ComponentName(
                            getPackageName(),
                            ShizukuShellService.class.getName()))
                    .daemon(false)
                    .processNameSuffix("restricted_settings_unlock")
                    .debuggable(false)
                    .version(1);
        }
        if (shizukuPermissionListener == null) {
            shizukuPermissionListener = this::onShizukuPermissionResult;
        }
        if (!shizukuListenerRegistered) {
            Shizuku.addRequestPermissionResultListener(shizukuPermissionListener);
            shizukuListenerRegistered = true;
        }
    }

    private boolean shizukuPermissionResultListenerReady() {
        return shizukuPermissionListener != null;
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
        try {
            show(BridgeClient.status(this));
        } catch (Throwable t) {
            status.setText("CONTROL_PLANE_STATUS_ERROR");
            result.setText("CONTROL_PLANE_STATUS_ERROR:" + t.getClass().getSimpleName());
        }
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
