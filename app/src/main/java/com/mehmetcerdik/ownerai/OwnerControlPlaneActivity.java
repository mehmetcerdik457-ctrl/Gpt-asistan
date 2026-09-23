package com.mehmetcerdik.ownerai;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Typeface;
import android.os.Bundle;
import android.provider.Settings;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

public final class OwnerControlPlaneActivity extends Activity implements View.OnClickListener {
    private static final String WORKER = "com.codespaceapps.aichat";
    private TextView status;
    private TextView result;
    private EditText selector;
    private EditText text;

    private static final int REFRESH=1001, ACCESS=1002, ARM=1003, STOP=1004, APPROVE_WORKER=1005,
        SCREEN=1006, LAUNCH_WORKER=1007, CLICK=1008, TYPE=1009, SCROLL_DOWN=1010,
        SCROLL_UP=1011, SWIPE_UP=1012, SWIPE_DOWN=1013, BACK=1014, HOME=1015, RECENTS=1016;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        ScrollView scroll = new ScrollView(this);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int p=(int)(16*getResources().getDisplayMetrics().density);
        root.setPadding(p,p,p,p);
        scroll.addView(root);

        TextView title=label("MEHMET OWNER — CONTROL PLANE",22f);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        root.addView(title);
        root.addView(label("Mevcut Owner Core IPC korunmuştur. Phone Agent yerel runtime ayrı yüzeydir.",13f));

        status=label("Durum",14f); root.addView(status);
        result=label("Sonuç",13f); root.addView(result);
        selector=new EditText(this); selector.setHint("Hedef metin / alan etiketi"); root.addView(selector);
        text=new EditText(this); text.setHint("Yazılacak metin"); root.addView(text);

        add(root,"Yenile",REFRESH);
        add(root,"Accessibility Ayarlarını Aç",ACCESS);
        add(root,"5 Dakika OWNER Oturumu Yetkilendir",ARM);
        add(root,"ACİL DURDUR",STOP);
        add(root,"Chatbot AI Paketini Onayla",APPROVE_WORKER);
        add(root,"Aktif Ekranı Oku",SCREEN);
        add(root,"Chatbot AI Aç",LAUNCH_WORKER);
        add(root,"Hedef Metne Tıkla",CLICK);
        add(root,"Tek/Seçili Alana Metni Yaz",TYPE);
        add(root,"Kaydır İleri",SCROLL_DOWN);
        add(root,"Kaydır Geri",SCROLL_UP);
        add(root,"Jest: Yukarı Kaydır",SWIPE_UP);
        add(root,"Jest: Aşağı Kaydır",SWIPE_DOWN);
        add(root,"GERİ",BACK);
        add(root,"ANA EKRAN",HOME);
        add(root,"SON UYGULAMALAR",RECENTS);

        setContentView(scroll);
        refresh();
    }

    @Override protected void onResume(){ super.onResume(); refresh(); }

    private TextView label(String s,float size){
        TextView v=new TextView(this); v.setText(s); v.setTextSize(size); v.setPadding(0,8,0,8); return v;
    }

    private void add(LinearLayout root,String label,int id){
        Button b=new Button(this); b.setText(label); b.setId(id); b.setOnClickListener(this); root.addView(b);
    }

    private void refresh(){ show(BridgeClient.status(this)); }

    private void show(Bundle b){
        if(b==null){ result.setText("NULL"); return; }
        status.setText(
            "bridgeSigner="+BridgeClient.getBridgeSigner(this)+
            "\nbridgeSignerMatch="+BridgeClient.verifyBridge(this)+
            "\nok="+b.getBoolean("ok",false)+
            "\nservice="+b.getBoolean("service_connected",false)+
            "\narmed="+b.getBoolean("armed",false)+
            "\nemergency="+b.getBoolean("emergency_stop",true)+
            "\nactivePackage="+b.getString("active_package","")+
            "\nstatus="+b.getString("status","")+
            "\nfailure="+b.getString("failure","")+
            "\nlastAction="+b.getString("last_action","")
        );
        String snapshot=b.getString("snapshot","");
        if(snapshot.length()>12000) snapshot=snapshot.substring(0,12000)+"\n…[kısaltıldı]";
        result.setText(snapshot.isEmpty()?b.toString():snapshot);
    }

    @Override public void onClick(View v){
        int id=v.getId();
        Bundle out;
        if(id==REFRESH){ refresh(); return; }
        if(id==ACCESS){ startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)); return; }
        if(id==ARM) out=BridgeClient.arm(this,5*60*1000L);
        else if(id==STOP) out=BridgeClient.stop(this);
        else if(id==APPROVE_WORKER) out=BridgeClient.approvePackage(this,WORKER);
        else if(id==SCREEN) out=BridgeClient.screenRead(this);
        else if(id==LAUNCH_WORKER) out=BridgeClient.launchApp(this,WORKER);
        else if(id==CLICK) out=BridgeClient.clickText(this,selector.getText().toString());
        else if(id==TYPE) out=BridgeClient.typeText(this,selector.getText().toString(),text.getText().toString());
        else if(id==SCROLL_DOWN) out=BridgeClient.scroll(this,true);
        else if(id==SCROLL_UP) out=BridgeClient.scroll(this,false);
        else if(id==SWIPE_UP) out=BridgeClient.swipe(this,0.5f,0.78f,0.5f,0.28f,420L);
        else if(id==SWIPE_DOWN) out=BridgeClient.swipe(this,0.5f,0.28f,0.5f,0.78f,420L);
        else if(id==BACK) out=BridgeClient.globalAction(this,"BACK");
        else if(id==HOME) out=BridgeClient.globalAction(this,"HOME");
        else if(id==RECENTS) out=BridgeClient.globalAction(this,"RECENTS");
        else return;
        show(out);
    }
}
