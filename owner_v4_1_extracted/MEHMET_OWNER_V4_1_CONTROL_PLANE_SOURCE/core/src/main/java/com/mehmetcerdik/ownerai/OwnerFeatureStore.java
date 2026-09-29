package com.mehmetcerdik.ownerai;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;

import java.security.KeyStore;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class OwnerFeatureStore {
    private static final String PREFS="mehm_owner_feature_store";
    private static final String KEY_ALIAS="mehmet_owner_feature_profile_v1";
    private static final String K_IV="profile_iv";
    private static final String K_CT="profile_ciphertext";
    private OwnerFeatureStore(){}

    public static boolean hasProfile(Context c){
        SharedPreferences p=c.getSharedPreferences(PREFS,Context.MODE_PRIVATE);
        return p.contains(K_IV)&&p.contains(K_CT);
    }

    public static void save(Context c,OwnerFeatureProfile profile) throws Exception {
        SecretKey key=getOrCreateKey();
        Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE,key);
        byte[] ct=cipher.doFinal(profile.encode());
        boolean ok=c.getSharedPreferences(PREFS,Context.MODE_PRIVATE).edit()
                .putString(K_IV,Base64.encodeToString(cipher.getIV(),Base64.NO_WRAP))
                .putString(K_CT,Base64.encodeToString(ct,Base64.NO_WRAP))
                .commit();
        if(!ok)throw new IllegalStateException("PROFILE_COMMIT_FAILED");
    }

    public static OwnerFeatureProfile load(Context c) throws Exception {
        SharedPreferences p=c.getSharedPreferences(PREFS,Context.MODE_PRIVATE);
        String iv=p.getString(K_IV,null),ct=p.getString(K_CT,null);
        if(iv==null||ct==null)return OwnerFeatureProfile.defaults();
        SecretKey key=getOrCreateKey();
        Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE,key,new GCMParameterSpec(128,Base64.decode(iv,Base64.NO_WRAP)));
        return OwnerFeatureProfile.decode(cipher.doFinal(Base64.decode(ct,Base64.NO_WRAP)));
    }

    private static SecretKey getOrCreateKey() throws Exception {
        KeyStore ks=KeyStore.getInstance("AndroidKeyStore");ks.load(null);
        java.security.Key existing=ks.getKey(KEY_ALIAS,null);
        if(existing instanceof SecretKey)return (SecretKey)existing;
        KeyGenerator kg=KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore");
        KeyGenParameterSpec spec=new KeyGenParameterSpec.Builder(KEY_ALIAS,KeyProperties.PURPOSE_ENCRYPT|KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .setUserAuthenticationRequired(true)
                .setUserAuthenticationValidityDurationSeconds(300)
                .build();
        kg.init(spec);return kg.generateKey();
    }
}
