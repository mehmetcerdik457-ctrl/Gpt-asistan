package com.mehmetcerdik.ownerai;

import java.io.IOException;
import java.net.ConnectException;
import java.net.SocketTimeoutException;
import java.net.UnknownHostException;
import javax.net.ssl.SSLException;

public final class ProviderNetworkErrorsTest {
    private static int count = 0;
    private static void check(Throwable t, String expected) {
        String actual = ProviderNetworkErrors.code(t);
        if (!expected.equals(actual)) throw new AssertionError(expected + " != " + actual);
        if (actual.contains("private.example") || actual.contains("SENTINEL_SECRET"))
            throw new AssertionError("Exception message leaked");
        count++;
    }
    public static void main(String[] ignored) {
        check(new UnknownHostException("private.example SENTINEL_SECRET"), "PROVIDER_DNS_UNAVAILABLE");
        check(new SocketTimeoutException("SENTINEL_SECRET"), "PROVIDER_NETWORK_TIMEOUT");
        check(new ConnectException("SENTINEL_SECRET"), "PROVIDER_CONNECT_FAILED");
        check(new SSLException("SENTINEL_SECRET"), "PROVIDER_TLS_FAILURE");
        check(new IOException("SENTINEL_SECRET"), "PROVIDER_NETWORK_FAILURE");
        check(new IOException("outer", new UnknownHostException("private.example")), "PROVIDER_DNS_UNAVAILABLE");
        System.out.println("PASS " + count + " provider network classification assertions");
    }
}
