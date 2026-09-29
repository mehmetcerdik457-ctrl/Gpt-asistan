package com.mehmetcerdik.ownerai;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.util.Locale;
import java.util.Properties;

public final class OwnerFeatureProfile {
    public static final String APPLY_STATUS = "LOCAL_DESIRED_PROFILE_ONLY";
    public static final String SAFETY_POLICY = "NO_BACKEND_MUTATION|NO_ENTITLEMENT_BYPASS|PUBLIC_WORKER_IMMUTABLE";
    public static final String[] REASONING_MODES = {"AUTO","FAST","BALANCED","DEEP"};

    public String modelPreference = "WORKER_DEFAULT";
    public String reasoning = "AUTO";
    public boolean autoRouting = true;
    public boolean webSearch = true;
    public boolean deepResearch = true;
    public boolean memory = true;
    public boolean personalization = true;
    public String customInstructions = "";
    public boolean voiceRealtime = true;
    public boolean multimodalInput = true;
    public boolean ocr = true;
    public boolean tools = true;
    public String language = "AUTO";
    public String voiceSelection = "WORKER_DEFAULT";
    public boolean diagnostics = true;

    public static OwnerFeatureProfile defaults(){ return new OwnerFeatureProfile(); }

    public byte[] encode() throws Exception {
        Properties p=new Properties();
        p.setProperty("model_selector",clean(modelPreference,120));
        p.setProperty("reasoning",normalizeReasoning(reasoning));
        p.setProperty("auto_routing",Boolean.toString(autoRouting));
        p.setProperty("web_search",Boolean.toString(webSearch));
        p.setProperty("deep_research",Boolean.toString(deepResearch));
        p.setProperty("memory",Boolean.toString(memory));
        p.setProperty("personalization",Boolean.toString(personalization));
        p.setProperty("custom_instructions",clean(customInstructions,8000));
        p.setProperty("voice_realtime",Boolean.toString(voiceRealtime));
        p.setProperty("multimodal_input",Boolean.toString(multimodalInput));
        p.setProperty("ocr",Boolean.toString(ocr));
        p.setProperty("tools",Boolean.toString(tools));
        p.setProperty("language",clean(language,80));
        p.setProperty("voice_selection",clean(voiceSelection,120));
        p.setProperty("diagnostics",Boolean.toString(diagnostics));
        ByteArrayOutputStream out=new ByteArrayOutputStream();
        p.store(out,"MEHMET OWNER feature profile");
        return out.toByteArray();
    }

    public static OwnerFeatureProfile decode(byte[] data) throws Exception {
        OwnerFeatureProfile o=defaults();
        Properties p=new Properties();
        p.load(new ByteArrayInputStream(data));
        o.modelPreference=clean(p.getProperty("model_selector",o.modelPreference),120);
        o.reasoning=normalizeReasoning(p.getProperty("reasoning",o.reasoning));
        o.autoRouting=b(p,"auto_routing",o.autoRouting);
        o.webSearch=b(p,"web_search",o.webSearch);
        o.deepResearch=b(p,"deep_research",o.deepResearch);
        o.memory=b(p,"memory",o.memory);
        o.personalization=b(p,"personalization",o.personalization);
        o.customInstructions=clean(p.getProperty("custom_instructions",""),8000);
        o.voiceRealtime=b(p,"voice_realtime",o.voiceRealtime);
        o.multimodalInput=b(p,"multimodal_input",o.multimodalInput);
        o.ocr=b(p,"ocr",o.ocr);
        o.tools=b(p,"tools",o.tools);
        o.language=clean(p.getProperty("language",o.language),80);
        o.voiceSelection=clean(p.getProperty("voice_selection",o.voiceSelection),120);
        o.diagnostics=b(p,"diagnostics",o.diagnostics);
        return o;
    }

    private static boolean b(Properties p,String key,boolean d){return Boolean.parseBoolean(p.getProperty(key,Boolean.toString(d)));}
    private static String clean(String s,int max){if(s==null)return "";s=s.replace("\u0000","").trim();return s.length()<=max?s:s.substring(0,max);}
    private static String normalizeReasoning(String s){String v=clean(s,20).toUpperCase(Locale.ROOT);for(String m:REASONING_MODES)if(m.equals(v))return v;return "AUTO";}

    public String summary(){
        return "APPLY_STATUS="+APPLY_STATUS+
                "\nSAFETY_POLICY="+SAFETY_POLICY+
                "\nMODEL_SELECTOR="+modelPreference+
                "\nREASONING="+reasoning+
                "\nAUTO_ROUTING="+autoRouting+
                "\nWEB_SEARCH="+webSearch+
                "\nDEEP_RESEARCH="+deepResearch+
                "\nMEMORY="+memory+
                "\nPERSONALIZATION="+personalization+
                "\nCUSTOM_INSTRUCTIONS="+(customInstructions.isEmpty()?"EMPTY":"SET_ENCRYPTED")+
                "\nVOICE_REALTIME="+voiceRealtime+
                "\nMULTIMODAL_INPUT="+multimodalInput+
                "\nOCR="+ocr+
                "\nTOOLS="+tools+
                "\nLANGUAGE="+language+
                "\nVOICE_SELECTION="+voiceSelection+
                "\nDIAGNOSTICS="+diagnostics+
                "\nWORKER_APPLICATION=NOT_YET_VERIFIED_DEVICE_ADAPTER_REQUIRED";
    }
}
