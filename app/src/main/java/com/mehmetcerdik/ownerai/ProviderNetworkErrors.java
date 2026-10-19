package com.mehmetcerdik.ownerai;

import java.net.ConnectException;
import java.net.SocketTimeoutException;
import java.net.UnknownHostException;
import javax.net.ssl.SSLException;

/** Fixed, non-sensitive error codes for provider transport failures. */
public final class ProviderNetworkErrors {
    private ProviderNetworkErrors() {}

    public static String code(Throwable failure) {
        // Never return the exception message (it may include a URL, query or secret).
        for (Throwable current = failure; current != null; current = current.getCause()) {
            if (current instanceof UnknownHostException) return "PROVIDER_DNS_UNAVAILABLE";
            if (current instanceof SocketTimeoutException) return "PROVIDER_NETWORK_TIMEOUT";
            if (current instanceof ConnectException) return "PROVIDER_CONNECT_FAILED";
            if (current instanceof SSLException) return "PROVIDER_TLS_FAILURE";
        }
        return "PROVIDER_NETWORK_FAILURE";
    }
}
