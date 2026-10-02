package com.mehmetcerdik.ownerai;

import android.content.Intent;
import android.os.Bundle;
import android.provider.Settings;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import androidx.appcompat.app.AppCompatActivity;

public final class OwnerControlPlaneActivity extends AppCompatActivity {
    private TextView status;
    private TextView result;

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

    @Override protected void onResume() {
        super.onResume();
        redactUnlessAuthorized();
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
