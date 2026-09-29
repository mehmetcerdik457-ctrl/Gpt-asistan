package com.mehmetcerdik.ownerai;

import org.junit.Test;
import static org.junit.Assert.*;

public final class ProviderEndpointPolicyTest {
    @Test public void canonicalEndpointIsAllowed() {
        assertTrue(ProviderEndpointPolicy.isAllowed("https://api.openai.com/v1/responses"));
        assertTrue(ProviderEndpointPolicy.isAllowed("https://api.openai.com:443/v1/responses"));
        assertEquals(ProviderEndpointPolicy.CANONICAL,
                ProviderEndpointPolicy.canonicalForStorage("https://api.openai.com:443/v1/responses"));
    }

    @Test public void exfiltrationAndLookalikesAreDenied() {
        String[] denied = {
                "http://api.openai.com/v1/responses",
                "https://api.openai.com.evil.example/v1/responses",
                "https://api.openai.com@evil.example/v1/responses",
                "https://evil.example@api.openai.com/v1/responses",
                "https://api.openai.com:444/v1/responses",
                "https://api.openai.com/v1/responses?next=https://evil.example",
                "https://api.openai.com/v1/responses#fragment",
                "https://api.openai.com/v1/chat/completions",
                "https://API.OPENAI.COM.evil.example/v1/responses"
        };
        for (String value : denied) assertFalse(value, ProviderEndpointPolicy.isAllowed(value));
    }
}
