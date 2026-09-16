/* Same-PID trampoline that gives a matched Wine game a Game Mode app context. */

#include <errno.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

#include <crt_externs.h>

#ifndef _POSIX_SPAWN_DISABLE_ASLR
#define _POSIX_SPAWN_DISABLE_ASLR 0x0100
#endif

int main(int argc, char **argv)
{
    posix_spawnattr_t attributes;
    char original_pid[32];
    int error;

    if (argc < 2 || !argv[1] || !*argv[1])
    {
        fputs("WHISKY_CHILD_POLICY result=host-failed error=missing-loader\n", stderr);
        return 64;
    }

    unsetenv("WHISKY_GAME_MODE_REQUESTED");
    snprintf(original_pid, sizeof(original_pid), "%d", getpid());
    setenv("WHISKY_GAME_MODE_HOST_PID", original_pid, 1);
    error = posix_spawnattr_init(&attributes);
    if (!error)
    {
        error = posix_spawnattr_setflags(&attributes, POSIX_SPAWN_SETEXEC | _POSIX_SPAWN_DISABLE_ASLR);
        if (!error) error = posix_spawn(NULL, argv[1], NULL, &attributes, argv + 1, *_NSGetEnviron());
        posix_spawnattr_destroy(&attributes);
    }

    fprintf(stderr, "WHISKY_CHILD_POLICY result=host-failed error=%d\n", error ?: errno);
    execv(argv[1], argv + 1);
    return 126;
}
