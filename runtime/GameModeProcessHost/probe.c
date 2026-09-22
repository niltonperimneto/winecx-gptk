#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

int main(void)
{
    const char *host_pid = getenv("WHISKY_GAME_MODE_HOST_PID");
    if (!host_pid || (pid_t)strtol(host_pid, NULL, 10) != getpid()) return 70;
    puts("same-pid");
    return 37;
}
