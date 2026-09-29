package com.mehmetcerdik.ownerai;

import android.app.Activity;
import android.app.KeyguardManager;
import android.content.Context;
import android.content.Intent;
import android.graphics.Typeface;
import android.os.Bundle;
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

public final class OwnerFeaturesActivity extends Activity implements View.OnClickListener {
    private static final String WORKER="com.codespaceapps.aichat";
    private static final int REQ_UNLOCK=8101,SAVE=8102,RELOAD=8103,INSPECT=8104,OPEN_WORKER=8105,RETURN=8106;
    private LinearLayout root;
    private TextView status,summary;
    private EditText model,custom,language,voice;
    private Spinner reasoning;
    private CheckBox autoRouting,webSearch,deepResearch,memory,personalization,voiceRealtime,multimodal,ocr,tools,diagnostics;
    private boolean unlocked=false;

    @Override protected void onCreate(Bundle b){
        super.onCreate(b);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
        ScrollView scroll=new ScrollView(this);root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);
        int p=(int)(16*getResources().getDisplayMetrics().density);root.setPadding(p,p,p,p);scroll.addView(root);setContentView(scroll);
        renderLocked();requestUnlock();
    }

    private void renderLocked(){
        root.removeAllViews();
        TextView title=label("MEHMET OWNER — FEATURE PROFILE",22f);title.setTypeface(Typeface.DEFAULT_BOLD);root.addView(title);
        root.addView(label("Public CİHAT 3.2.1 değişmez. Bu ekran yalnız owner cihazındaki istenen profil ve güvenli kontrol niyetini saklar.",13f));
        root.addView(label("Truth-lock: LOCAL_DESIRED_PROFILE_ONLY. Bir anahtarın seçilmesi worker/backend üzerinde uygulandığı anlamına gelmez.",12f));
        status=label("DEVICE_CREDENTIAL_REQUIRED",13f);root.addView(status);add("Cihaz Kilidiyle Aç",REQ_UNLOCK);add("Geri",RETURN);
    }

    private void requestUnlock(){
        KeyguardManager km=(KeyguardManager)getSystemService(Context.KEYGUARD_SERVICE);
        if(km==null||!km.isDeviceSecure()){status.setText("BLOCKED: DEVICE_CREDENTIAL_NOT_CONFIGURED");return;}
        Intent i=km.createConfirmDeviceCredentialIntent("MEHMET OWNER","Owner feature profilini açmak için cihaz kilidini doğrula.");
        if(i==null){status.setText("BLOCKED: DEVICE_CREDENTIAL_INTENT_UNAVAILABLE");return;}startActivityForResult(i,REQ_UNLOCK);
    }

    @Override protected void onActivityResult(int requestCode,int resultCode,Intent data){
        super.onActivityResult(requestCode,resultCode,data);
        if(requestCode==REQ_UNLOCK){if(resultCode==RESULT_OK){unlocked=true;renderEditor();}else status.setText("BLOCKED: DEVICE_CREDENTIAL_CANCELLED_OR_FAILED");}
    }

    private void renderEditor(){
        root.removeAllViews();
        TextView title=label("MEHMET OWNER — FEATURE PROFILE",22f);title.setTypeface(Typeface.DEFAULT_BOLD);root.addView(title);
        root.addView(label("BASELINE: com.codespaceapps.aichat 3.2.1/893 — immutable. PROFILE: encrypted local desired state. APPLY: device adapter not yet verified.",12f));
        status=label("DEVICE_CREDENTIAL_VERIFIED",13f);root.addView(status);
        model=input("Model selector preference (WORKER_DEFAULT veya model etiketi)");
        root.addView(label("Reasoning preference",13f));reasoning=new Spinner(this);
        ArrayAdapter<String> ra=new ArrayAdapter<>(this,android.R.layout.simple_spinner_item,OwnerFeatureProfile.REASONING_MODES);ra.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);reasoning.setAdapter(ra);root.addView(reasoning);
        autoRouting=check("Auto model routing");webSearch=check("Web search");deepResearch=check("Deep research");memory=check("Memory");personalization=check("Personalization");
        custom=input("Custom instructions (encrypted at rest)");custom.setMinLines(3);custom.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        voiceRealtime=check("Voice / realtime");multimodal=check("File / image / audio / video input");ocr=check("OCR");tools=check("Tools / function calling");
        language=input("Language preference (AUTO veya dil etiketi)");voice=input("Voice selection preference (WORKER_DEFAULT veya ses etiketi)");diagnostics=check("Diagnostics");
        add("Profili Şifreli Kaydet",SAVE);add("Profili Yeniden Yükle",RELOAD);add("Worker Kimliğini Bridge Üzerinden İncele",INSPECT);add("CİHAT Worker'ı Aç",OPEN_WORKER);
        summary=label("",12f);root.addView(summary);add("Geri",RETURN);loadProfile();
    }

    private EditText input(String hint){EditText e=new EditText(this);e.setHint(hint);root.addView(e);return e;}
    private CheckBox check(String text){CheckBox c=new CheckBox(this);c.setText(text);root.addView(c);return c;}
    private TextView label(String s,float z){TextView v=new TextView(this);v.setText(s);v.setTextSize(z);v.setPadding(0,8,0,8);return v;}
    private void add(String t,int id){Button b=new Button(this);b.setText(t);b.setId(id);b.setOnClickListener(this);root.addView(b);}

    private OwnerFeatureProfile fromUi(){
        OwnerFeatureProfile p=new OwnerFeatureProfile();p.modelPreference=model.getText().toString();p.reasoning=String.valueOf(reasoning.getSelectedItem());
        p.autoRouting=autoRouting.isChecked();p.webSearch=webSearch.isChecked();p.deepResearch=deepResearch.isChecked();p.memory=memory.isChecked();p.personalization=personalization.isChecked();p.customInstructions=custom.getText().toString();
        p.voiceRealtime=voiceRealtime.isChecked();p.multimodalInput=multimodal.isChecked();p.ocr=ocr.isChecked();p.tools=tools.isChecked();p.language=language.getText().toString();p.voiceSelection=voice.getText().toString();p.diagnostics=diagnostics.isChecked();return p;
    }

    private void toUi(OwnerFeatureProfile p){
        model.setText(p.modelPreference);setSpinner(reasoning,p.reasoning);autoRouting.setChecked(p.autoRouting);webSearch.setChecked(p.webSearch);deepResearch.setChecked(p.deepResearch);
        memory.setChecked(p.memory);personalization.setChecked(p.personalization);custom.setText(p.customInstructions);voiceRealtime.setChecked(p.voiceRealtime);multimodal.setChecked(p.multimodalInput);ocr.setChecked(p.ocr);tools.setChecked(p.tools);
        language.setText(p.language);voice.setText(p.voiceSelection);diagnostics.setChecked(p.diagnostics);summary.setText(p.summary());
    }

    private void setSpinner(Spinner s,String value){for(int i=0;i<s.getCount();i++)if(String.valueOf(s.getItemAtPosition(i)).equals(value)){s.setSelection(i);return;}s.setSelection(0);}
    private void loadProfile(){try{OwnerFeatureProfile p=OwnerFeatureStore.load(this);toUi(p);status.setText(OwnerFeatureStore.hasProfile(this)?"PROFILE_DECRYPTED_LOCAL":"DEFAULT_PROFILE_NOT_YET_SAVED");}catch(Throwable t){status.setText("PROFILE_LOAD_FAILED:"+t.getClass().getSimpleName());}}
    private void saveProfile(){try{OwnerFeatureProfile p=fromUi();OwnerFeatureStore.save(this,p);toUi(p);status.setText("PROFILE_SAVED_ENCRYPTED_LOCAL; WORKER_APPLICATION=NOT_YET_VERIFIED");}catch(Throwable t){status.setText("PROFILE_SAVE_FAILED:"+t.getClass().getSimpleName());}}
    private String bundle(Bundle b){if(b==null)return"NULL";StringBuilder s=new StringBuilder();for(String k:b.keySet())s.append(k).append('=').append(String.valueOf(b.get(k))).append('\n');return s.toString();}

    @Override public void onClick(View v){
        int id=v.getId();if(id==RETURN){finish();return;}if(id==REQ_UNLOCK){requestUnlock();return;}if(!unlocked){status.setText("DEVICE_CREDENTIAL_REQUIRED");return;}
        if(id==SAVE){saveProfile();return;}if(id==RELOAD){loadProfile();return;}if(id==INSPECT){status.setText("WORKER_INSPECT\n"+bundle(BridgeClient.inspectPackage(this,WORKER)));return;}
        if(id==OPEN_WORKER){status.setText("WORKER_LAUNCH\n"+bundle(BridgeClient.launchApp(this,WORKER)));}
    }
}
