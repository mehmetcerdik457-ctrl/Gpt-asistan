package com.mehmetcerdik.ownerai;

import android.app.Activity;
import android.app.KeyguardManager;
import android.content.Context;
import android.content.Intent;
import android.graphics.Typeface;
import android.os.Bundle;
import android.provider.Settings;
import android.text.InputType;
import android.view.View;
import android.view.WindowManager;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.TextView;

import java.util.ArrayList;

public final class MainActivity extends Activity implements View.OnClickListener {
    private static final String WORKER="com.codespaceapps.aichat";
    private static final int REQ_DEVICE_CREDENTIAL=7001;
    private TextView status,result,packagePreview;
    private EditText selector,text;
    private CheckBox secretMode;
    private Spinner packageSpinner;
    private final ArrayList<String> packageWires=new ArrayList<>();
    private final ArrayList<String> packageDisplays=new ArrayList<>();

    private static final int REFRESH=1001,ACCESS=1002,ARM=1003,STOP=1004,SCREEN=1006,CLICK=1008,TYPE=1009,SCROLL_DOWN=1010,SCROLL_UP=1011,SWIPE_UP=1012,SWIPE_DOWN=1013,BACK=1014,HOME=1015,RECENTS=1016,NOTIFICATIONS=1017,LOAD_PACKAGES=1018,APPROVE_SELECTED=1019,REVOKE_SELECTED=1020,REVOKE_ALL=1021,LIST_APPROVED=1022,LAUNCH_SELECTED=1023,VERIFY_AUDIT=1024,VERIFY_PKG=1025,VERIFY_TEXT_PRESENT=1026,VERIFY_TEXT_ABSENT=1027,LAUNCH_WORKER=1028;

    @Override protected void onCreate(Bundle state){
        super.onCreate(state); ScrollView scroll=new ScrollView(this); LinearLayout root=new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL); int p=(int)(16*getResources().getDisplayMetrics().density); root.setPadding(p,p,p,p); scroll.addView(root);
        TextView title=label("MEHMET OWNER — V4.1 CONTROL PLANE",22f);title.setTypeface(Typeface.DEFAULT_BOLD);root.addView(title);
        root.addView(label("GÖR → AÇ → DOKUN → KAYDIR → YAZ → HEDEF KOŞULU DOĞRULA",14f));
        root.addView(label("AI karar/ToolBus döngüsü bu adayda henüz bağlı değildir. Bu arayüz owner-controlled action surface'tir.",12f));
        status=label("Durum",13f);root.addView(status);result=label("Sonuç",12f);root.addView(result);
        selector=new EditText(this);selector.setHint("Hedef metin / alan etiketi / postcondition değeri");root.addView(selector);
        text=new EditText(this);text.setHint("Yazılacak metin");root.addView(text);
        secretMode=new CheckBox(this);secretMode.setText("Gizli giriş modu (maskeli + ekran görüntüsü engeli + işlem sonrası temizle)");secretMode.setOnCheckedChangeListener((buttonView,isChecked)->applySecretMode(isChecked));root.addView(secretMode);
        add(root,"Yenile",REFRESH);add(root,"Accessibility Ayarlarını Aç",ACCESS);add(root,"5 Dakika Cihaz Kilidi Doğrulamalı Oturum",ARM);add(root,"ACİL DURDUR",STOP);
        packagePreview=label("Uygulama seçimi: önce oturumu aç, sonra listeyi yükle.",12f);root.addView(packagePreview);packageSpinner=new Spinner(this);root.addView(packageSpinner);packageSpinner.setOnItemSelectedListener(new android.widget.AdapterView.OnItemSelectedListener(){public void onItemSelected(android.widget.AdapterView<?> p,View v,int pos,long id){preview(pos);}public void onNothingSelected(android.widget.AdapterView<?> p){}});
        add(root,"Uygulama Listesini Yenile",LOAD_PACKAGES);add(root,"Seçili Paketi Onayla",APPROVE_SELECTED);add(root,"Seçili Paketin Onayını Kaldır",REVOKE_SELECTED);add(root,"Worker Hariç Tüm Onayları Kaldır",REVOKE_ALL);add(root,"Onaylı Paketleri Listele",LIST_APPROVED);add(root,"Seçili Uygulamayı Aç",LAUNCH_SELECTED);add(root,"Chatbot AI Aç",LAUNCH_WORKER);
        add(root,"Aktif Ekranı Oku",SCREEN);add(root,"Hedef Metne Tıkla",CLICK);add(root,"Tek/Seçili Alana Metni Yaz",TYPE);add(root,"Kaydır İleri",SCROLL_DOWN);add(root,"Kaydır Geri",SCROLL_UP);add(root,"Jest: Yukarı Kaydır",SWIPE_UP);add(root,"Jest: Aşağı Kaydır",SWIPE_DOWN);add(root,"GERİ",BACK);add(root,"ANA EKRAN",HOME);add(root,"SON UYGULAMALAR",RECENTS);add(root,"BİLDİRİMLER",NOTIFICATIONS);
        add(root,"Postcondition: Aktif Paket Eşit",VERIFY_PKG);add(root,"Postcondition: Metin Var",VERIFY_TEXT_PRESENT);add(root,"Postcondition: Metin Yok",VERIFY_TEXT_ABSENT);add(root,"Audit Zincirini Doğrula",VERIFY_AUDIT);
        setContentView(scroll);refresh();
    }

    @Override protected void onResume(){super.onResume();refresh();}
    private void applySecretMode(boolean enabled){if(enabled){text.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);}else{text.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_NORMAL);getWindow().clearFlags(WindowManager.LayoutParams.FLAG_SECURE);}}
    private TextView label(String s,float size){TextView v=new TextView(this);v.setText(s);v.setTextSize(size);v.setPadding(0,8,0,8);return v;} private void add(LinearLayout root,String t,int id){Button b=new Button(this);b.setText(t);b.setId(id);b.setOnClickListener(this);root.addView(b);}
    private void refresh(){show(BridgeClient.status(this));}
    private void show(Bundle b){if(b==null){result.setText("NULL");return;}String s="bridgeSigner="+BridgeClient.getBridgeSigner(this)+"\nok="+b.getBoolean("ok",false)+"\nservice="+b.getBoolean("service_connected",false)+"\narmed="+b.getBoolean("armed",false)+"\nremainingMs="+b.getLong("armed_remaining_ms",0L)+"\nemergency="+b.getBoolean("emergency_stop",true)+"\nsessionClass="+b.getString("session_class","")+"\nactivePackage="+b.getString("active_package","")+"\nauditIntegrity="+b.getBoolean("audit_integrity",false)+"\nstatus="+b.getString("status","")+"\nfailure="+b.getString("failure","")+"\nlastAction="+b.getString("last_action","");status.setText(s);String snapshot=b.getString("snapshot","");if(snapshot.length()>12000)snapshot=snapshot.substring(0,12000)+"\n…[kısaltıldı]";result.setText(snapshot.isEmpty()?bundleSummary(b):snapshot);}
    private String bundleSummary(Bundle b){StringBuilder sb=new StringBuilder();for(String k:b.keySet()){Object v=b.get(k);if(v instanceof String[])sb.append(k).append('=').append(java.util.Arrays.toString((String[])v)).append('\n');else if(v instanceof ArrayList)sb.append(k).append('=').append(v).append('\n');else sb.append(k).append('=').append(String.valueOf(v)).append('\n');}return sb.toString();}

    private void requestArm(){KeyguardManager km=(KeyguardManager)getSystemService(Context.KEYGUARD_SERVICE);if(km==null||!km.isDeviceSecure()){showFail("DEVICE_CREDENTIAL_NOT_CONFIGURED");return;}Intent i=km.createConfirmDeviceCredentialIntent("MEHMET OWNER","5 dakikalık kontrol oturumunu açmak için cihaz kilidini doğrula.");if(i==null){showFail("DEVICE_CREDENTIAL_INTENT_UNAVAILABLE");return;}startActivityForResult(i,REQ_DEVICE_CREDENTIAL);}
    @Override protected void onActivityResult(int requestCode,int resultCode,Intent data){super.onActivityResult(requestCode,resultCode,data);if(requestCode==REQ_DEVICE_CREDENTIAL){if(resultCode==RESULT_OK)show(BridgeClient.arm(this,5*60*1000L));else showFail("DEVICE_CREDENTIAL_CANCELLED_OR_FAILED");}}
    private void showFail(String reason){Bundle b=new Bundle();b.putBoolean("ok",false);b.putString("status","FAILED");b.putString("failure",reason);show(b);}

    private void loadPackages(){Bundle b=BridgeClient.listPackages(this);ArrayList<String> wires=BridgeClient.packageList(b);packageWires.clear();packageDisplays.clear();if(wires!=null)for(String wire:wires){String[] p=parsePackageWire(wire);if(p==null)continue;packageWires.add(wire);packageDisplays.add(p[0]+" — "+p[1]);}ArrayAdapter<String>a=new ArrayAdapter<>(this,android.R.layout.simple_spinner_item,packageDisplays);a.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);packageSpinner.setAdapter(a);show(b);}
    private String[] parsePackageWire(String wire){if(wire==null)return null;String[] p=wire.split("\\t",-1);if(p.length!=4)return null;if(!p[1].matches("[A-Za-z][A-Za-z0-9_]*(\\.[A-Za-z0-9_]+)+"))return null;if(!p[2].matches("[0-9a-fA-F]{64}"))return null;if(!("true".equals(p[3])||"false".equals(p[3])))return null;return p;}
    private String selectedPackage(){int pos=packageSpinner.getSelectedItemPosition();if(pos<0||pos>=packageWires.size())return null;String[] p=parsePackageWire(packageWires.get(pos));return p==null?null:p[1];}
    private void preview(int pos){if(pos<0||pos>=packageWires.size())return;String[] p=parsePackageWire(packageWires.get(pos));if(p!=null)packagePreview.setText("APP LABEL: "+p[0]+"\nPACKAGE: "+p[1]+"\nSIGNER SHA256: "+p[2]+"\nLAUNCHABLE: "+p[3]);else packagePreview.setText("Geçersiz paket kaydı reddedildi.");}

    @Override public void onClick(View v){int id=v.getId();Bundle out;if(id==REFRESH){refresh();return;}if(id==ACCESS){startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS));return;}if(id==ARM){requestArm();return;}if(id==STOP)out=BridgeClient.stop(this);else if(id==LOAD_PACKAGES){loadPackages();return;}else if(id==APPROVE_SELECTED){String p=selectedPackage();if(p==null){showFail("NO_PACKAGE_SELECTED");return;}out=BridgeClient.approvePackage(this,p);}else if(id==REVOKE_SELECTED){String p=selectedPackage();if(p==null){showFail("NO_PACKAGE_SELECTED");return;}out=BridgeClient.revokePackage(this,p);}else if(id==REVOKE_ALL)out=BridgeClient.revokeAllNonDefaultPackages(this);else if(id==LIST_APPROVED)out=BridgeClient.listApprovedPackages(this);else if(id==LAUNCH_SELECTED){String p=selectedPackage();if(p==null){showFail("NO_PACKAGE_SELECTED");return;}out=BridgeClient.launchApp(this,p);}else if(id==LAUNCH_WORKER)out=BridgeClient.launchApp(this,WORKER);else if(id==SCREEN)out=BridgeClient.screenRead(this);else if(id==CLICK)out=BridgeClient.clickText(this,selector.getText().toString());else if(id==TYPE){boolean secret=secretMode.isChecked();out=BridgeClient.typeText(this,selector.getText().toString(),text.getText().toString(),secret);if(secret)text.setText("");}else if(id==SCROLL_DOWN)out=BridgeClient.scroll(this,true);else if(id==SCROLL_UP)out=BridgeClient.scroll(this,false);else if(id==SWIPE_UP)out=BridgeClient.swipe(this,.5f,.78f,.5f,.28f,420L);else if(id==SWIPE_DOWN)out=BridgeClient.swipe(this,.5f,.28f,.5f,.78f,420L);else if(id==BACK)out=BridgeClient.globalAction(this,"BACK");else if(id==HOME)out=BridgeClient.globalAction(this,"HOME");else if(id==RECENTS)out=BridgeClient.globalAction(this,"RECENTS");else if(id==NOTIFICATIONS)out=BridgeClient.globalAction(this,"NOTIFICATIONS");else if(id==VERIFY_PKG)out=BridgeClient.verifyPostcondition(this,"activePackageEquals",selector.getText().toString());else if(id==VERIFY_TEXT_PRESENT)out=BridgeClient.verifyPostcondition(this,"textPresent",selector.getText().toString());else if(id==VERIFY_TEXT_ABSENT)out=BridgeClient.verifyPostcondition(this,"textAbsent",selector.getText().toString());else if(id==VERIFY_AUDIT)out=BridgeClient.verifyAudit(this);else return;show(out);}
}
