#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>
#include <mswsock.h>
#include <stdio.h>
#include <string.h>

static int failures;

static void fail(const char *message)
{
    fprintf(stderr, "FAIL: %s (WSA %d)\n", message, WSAGetLastError());
    failures++;
}

static LPFN_WSARECVMSG recvmsg_function(SOCKET socket)
{
    GUID guid = WSAID_WSARECVMSG;
    LPFN_WSARECVMSG function = NULL;
    DWORD bytes = 0;
    if (WSAIoctl(socket, SIO_GET_EXTENSION_FUNCTION_POINTER, &guid, sizeof(guid),
                 &function, sizeof(function), &bytes, NULL, NULL))
        fail("WSAIoctl(WSAID_WSARECVMSG)");
    return function;
}

static int has_int_control(WSAMSG *message, int level, int type, int expected)
{
    WSACMSGHDR *header;
    for (header = WSA_CMSG_FIRSTHDR(message); header; header = WSA_CMSG_NXTHDR(message, header))
        if (header->cmsg_level == level && header->cmsg_type == type &&
            header->cmsg_len >= WSA_CMSG_LEN(sizeof(int)) &&
            *(int *)WSA_CMSG_DATA(header) == expected)
            return 1;
    return 0;
}

static void probe_ipv4(int overlapped)
{
    SOCKET receiver = INVALID_SOCKET, sender = INVALID_SOCKET;
    struct sockaddr_in address = {0};
    int address_length = sizeof(address), enabled = 1, tos = 0x28;
    char payload[] = "whisky", received[16], control[128];
    WSABUF buffer = {sizeof(received), received};
    WSAMSG message = {0};
    LPFN_WSARECVMSG function;
    DWORD bytes = 0;
    WSAOVERLAPPED operation = {0};

    receiver = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    sender = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (receiver == INVALID_SOCKET || sender == INVALID_SOCKET) { fail("IPv4 socket"); goto done; }
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (bind(receiver, (struct sockaddr *)&address, sizeof(address)) ||
        getsockname(receiver, (struct sockaddr *)&address, &address_length)) { fail("IPv4 bind"); goto done; }
    if (setsockopt(receiver, IPPROTO_IP, IP_RECVTOS, (char *)&enabled, sizeof(enabled)) ||
        setsockopt(sender, IPPROTO_IP, IP_TOS, (char *)&tos, sizeof(tos))) { fail("IPv4 TOS options"); goto done; }
    function = recvmsg_function(receiver);
    if (!function) goto done;
    message.lpBuffers = &buffer; message.dwBufferCount = 1;
    message.Control.buf = control; message.Control.len = sizeof(control);
    if (overlapped) {
        operation.hEvent = WSACreateEvent();
        if (function(receiver, &message, NULL, &operation, NULL) != SOCKET_ERROR ||
            WSAGetLastError() != WSA_IO_PENDING) { fail("overlapped WSARecvMsg did not pend"); goto done; }
    }
    if (sendto(sender, payload, sizeof(payload), 0, (struct sockaddr *)&address, sizeof(address)) < 0) {
        fail("IPv4 sendto"); goto done;
    }
    if (overlapped) {
        if (!WSAGetOverlappedResult(receiver, &operation, &bytes, TRUE, &message.dwFlags)) {
            fail("overlapped WSARecvMsg completion"); goto done;
        }
    } else if (function(receiver, &message, &bytes, NULL, NULL)) {
        fail("synchronous WSARecvMsg"); goto done;
    }
    if (!has_int_control(&message, IPPROTO_IP, IP_TOS, tos)) fail("IPv4 TOS control data missing");
done:
    if (operation.hEvent) WSACloseEvent(operation.hEvent);
    if (receiver != INVALID_SOCKET) closesocket(receiver);
    if (sender != INVALID_SOCKET) closesocket(sender);
}

static void probe_ipv6(void)
{
    SOCKET receiver = INVALID_SOCKET, sender = INVALID_SOCKET;
    struct sockaddr_in6 address = {0};
    int address_length = sizeof(address), enabled = 1, traffic_class = 0;
    char payload[] = "whisky", received[16], control[128];
    WSABUF buffer = {sizeof(received), received};
    WSAMSG message = {0}; LPFN_WSARECVMSG function; DWORD bytes = 0;
    receiver = socket(AF_INET6, SOCK_DGRAM, IPPROTO_UDP);
    sender = socket(AF_INET6, SOCK_DGRAM, IPPROTO_UDP);
    if (receiver == INVALID_SOCKET || sender == INVALID_SOCKET) { fail("IPv6 socket"); goto done; }
    address.sin6_family = AF_INET6; address.sin6_addr = in6addr_loopback;
    if (bind(receiver, (struct sockaddr *)&address, sizeof(address)) ||
        getsockname(receiver, (struct sockaddr *)&address, &address_length)) { fail("IPv6 bind"); goto done; }
    if (setsockopt(receiver, IPPROTO_IPV6, IPV6_RECVTCLASS, (char *)&enabled, sizeof(enabled))) {
        fail("IPv6 receive-traffic-class option"); goto done;
    }
    function = recvmsg_function(receiver); if (!function) goto done;
    message.lpBuffers = &buffer; message.dwBufferCount = 1;
    message.Control.buf = control; message.Control.len = sizeof(control);
    if (sendto(sender, payload, sizeof(payload), 0, (struct sockaddr *)&address, sizeof(address)) < 0 ||
        function(receiver, &message, &bytes, NULL, NULL)) { fail("IPv6 WSARecvMsg"); goto done; }
    if (!has_int_control(&message, IPPROTO_IPV6, IPV6_TCLASS, traffic_class))
        fail("IPv6 traffic-class control data missing");
done:
    if (receiver != INVALID_SOCKET) closesocket(receiver);
    if (sender != INVALID_SOCKET) closesocket(sender);
}

int main(void)
{
    WSADATA data;
    if (WSAStartup(MAKEWORD(2, 2), &data)) return 2;
    probe_ipv4(0);
    probe_ipv4(1);
    probe_ipv6();
    WSACleanup();
    if (failures) return 1;
    puts("RESULT: WSARecvMsg IPv4 TOS, IPv6 traffic class, and overlapped receive verified");
    return 0;
}
