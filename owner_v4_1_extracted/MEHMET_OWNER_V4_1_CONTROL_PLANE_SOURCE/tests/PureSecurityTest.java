package com.mehmetcerdik.ownerbridge;

public final class PureSecurityTest {
    private static void req(boolean v,String m){if(!v)throw new AssertionError(m);}
    public static void main(String[] args){
        String prev=AuditChain.GENESIS;
        String[] lines=new String[8];
        for(int i=0;i<8;i++){lines[i]=AuditChain.buildLine(i+1,0,"session",123,9,100+i,1000+i,"A"+i,"OBSERVED","r"+i,"",prev);prev=lines[i].substring(lines[i].lastIndexOf("|entry_hash=")+12);}
        req(AuditChain.verify(lines,1,AuditChain.GENESIS,8,prev).ok,"valid chain rejected");
        String original=lines[3]; lines[3]=original.replace("action=A3","action=TAMPERED"); req(!AuditChain.verify(lines,1,AuditChain.GENESIS,8,prev).ok,"content tamper not detected"); lines[3]=original;
        String[] deleted={lines[0],lines[1],lines[2],lines[4],lines[5],lines[6],lines[7]}; req(!AuditChain.verify(deleted,1,AuditChain.GENESIS,8,prev).ok,"deletion not detected");
        String tmp=lines[2];lines[2]=lines[3];lines[3]=tmp;req(!AuditChain.verify(lines,1,AuditChain.GENESIS,8,prev).ok,"reorder not detected");lines[3]=lines[2];lines[2]=tmp; // restore below
        // rebuild to avoid accidental restore ambiguity
        prev=AuditChain.GENESIS;for(int i=0;i<8;i++){lines[i]=AuditChain.buildLine(i+1,0,"session",123,9,100+i,1000+i,"A"+i,"OBSERVED","r"+i,"",prev);prev=lines[i].substring(lines[i].lastIndexOf("|entry_hash=")+12);}
        String p=lines[4];lines[4]=p.replaceFirst("prev_hash=[0-9a-f]+","prev_hash=deadbeef");req(!AuditChain.verify(lines,1,AuditChain.GENESIS,8,prev).ok,"previous hash tamper not detected");lines[4]=p;
        String[] truncated=new String[7];System.arraycopy(lines,0,truncated,0,7);req(!AuditChain.verify(truncated,1,AuditChain.GENESIS,8,prev).ok,"truncation not detected");
        p=lines[5];lines[5]=p.replace("process_session=session","process_session=other");req(!AuditChain.verify(lines,1,AuditChain.GENESIS,8,prev).ok,"process/session field tamper not detected");lines[5]=p;
        p=lines[5];lines[5]=p.replace("boot_count=9","boot_count=10");req(!AuditChain.verify(lines,1,AuditChain.GENESIS,8,prev).ok,"boot field tamper not detected");lines[5]=p;
        p=lines[5];lines[5]=p.replace("segment=0","segment=7");req(!AuditChain.verify(lines,1,AuditChain.GENESIS,8,prev).ok,"segment field tamper not detected");lines[5]=p;
        req(SecretClassifier.isSensitiveMetadata("","","password","id"),"password missed");
        req(SecretClassifier.isSensitiveMetadata("","","PIN","id"),"PIN missed");
        req(SecretClassifier.isSensitiveMetadata("","","OTP code","id"),"OTP missed");
        req(SecretClassifier.isSensitiveMetadata("","","CVV","id"),"CVV missed");
        req(SecretClassifier.isSensitiveMetadata("","","API key","id"),"API key missed");
        req(SecretClassifier.isSensitiveMetadata("","","access token","id"),"token missed");
        req(SecretClassifier.isSensitiveMetadata("","","recovery code","id"),"recovery code missed");
        req(SecretClassifier.isSensitiveMetadata("","","seed phrase","id"),"seed missed");
        req(!SecretClassifier.isSensitiveMetadata("hello","send","message","id"),"ordinary/ambiguous field false positive");
        System.out.println("PURE_JAVA_SECURITY_TEST=PASS");
        System.out.println("AUDIT_CORRUPTION_NEGATIVE_TEST=PASS_MODEL");
        System.out.println("SECRET_CLASSIFIER_NEGATIVE_TEST=PASS_MODEL");
    }
}
