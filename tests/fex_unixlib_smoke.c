/* Load the FEX Unix helpers natively, without Wine, and call the handlers
 * whose macOS behaviour the port defines.
 *
 *   clang -arch arm64 -o fex_unixlib_smoke tests/fex_unixlib_smoke.c
 *   ./fex_unixlib_smoke BUNDLE/aarch64-unix/libarm64ecfex.so BUNDLE/aarch64-unix/libwow64fex.so
 */
#include <dlfcn.h>
#include <fcntl.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

typedef int32_t NTSTATUS;
typedef NTSTATUS (*unixlib_entry_t)(void *);

/* FEXUnixLibFunctions and argument layouts from Source/Windows/UnixLib/FEXUnixLib.h. */
enum { SetHardwareTSOControl, SetKernelUnalignedAtomicControl, Madvise, SetVMAName,
       GetSHMStatsVMA, DeleteSHMStatsFile, MapFile };
struct tso_args { bool Enable; };
struct unaligned_args { uint64_t Flags; };
struct madvise_args { const void *Addr; size_t Size; int32_t Advise; uint32_t pad; };
struct vma_args { const void *Addr; size_t Size; const char *Name; };
struct shm_args { void *SHMBase; uint32_t MapSize; uint32_t MaxSize; };
struct map_args { int32_t FD; uint64_t MapSize; void *Result; };

#define STATUS_SUCCESS 0
#define STATUS_NOT_SUPPORTED ((NTSTATUS)0xC00000BB)

static int failures;

static void expect(const char *library, const char *what, NTSTATUS got, NTSTATUS want)
{
    printf("%s: %-28s %#010x %s\n", library, what, (uint32_t)got, got == want ? "ok" : "FAIL");
    if (got != want) failures++;
}

static void check(const char *path)
{
    const char *name = strrchr(path, '/') ? strrchr(path, '/') + 1 : path;
    void *handle = dlopen(path, RTLD_NOW | RTLD_LOCAL);
    if (!handle) { printf("%s: dlopen failed: %s\n", name, dlerror()); failures++; return; }
    const unixlib_entry_t *funcs = dlsym(handle, "__wine_unix_call_funcs");
    if (!funcs) { printf("%s: no __wine_unix_call_funcs\n", name); failures++; return; }

    struct tso_args tso_on = { true }, tso_off = { false };
    expect(name, "TSO enable (unsupported)", funcs[SetHardwareTSOControl](&tso_on), STATUS_NOT_SUPPORTED);
    expect(name, "TSO disable", funcs[SetHardwareTSOControl](&tso_off), STATUS_SUCCESS);
    struct unaligned_args unaligned = { 1 };
    expect(name, "unaligned atomics", funcs[SetKernelUnalignedAtomicControl](&unaligned), STATUS_NOT_SUPPORTED);

    size_t page = (size_t)getpagesize();
    void *region = mmap(NULL, page, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    struct madvise_args hugepage = { region, page, 14 /* Linux MADV_HUGEPAGE */, 0 };
    expect(name, "madvise hugepage (dropped)", funcs[Madvise](&hugepage), STATUS_SUCCESS);
    struct madvise_args willneed = { region, page, 3 /* Linux MADV_WILLNEED */, 0 };
    expect(name, "madvise willneed", funcs[Madvise](&willneed), STATUS_SUCCESS);
    struct vma_args vma = { region, page, "FEXMem_Misc" };
    expect(name, "VMA name (noop)", funcs[SetVMAName](&vma), STATUS_SUCCESS);
    struct shm_args shm = { NULL, (uint32_t)page, (uint32_t)page * 4 };
    expect(name, "SHM stats (unsupported)", funcs[GetSHMStatsVMA](&shm), STATUS_NOT_SUPPORTED);
    expect(name, "SHM stats delete", funcs[DeleteSHMStatsFile](NULL), STATUS_SUCCESS);
    munmap(region, page);

    /* MapFile maps a file read-only and closes the descriptor it is given. */
    char file[] = "/tmp/fex-unixlib-smoke-XXXXXX";
    int fd = mkstemp(file);
    const char text[] = "FEX MapFile on macOS";
    if (fd < 0 || write(fd, text, sizeof(text)) != (ssize_t)sizeof(text)) { perror("temp file"); exit(1); }
    struct map_args map = { fd, sizeof(text), NULL };
    expect(name, "MapFile", funcs[MapFile](&map), STATUS_SUCCESS);
    bool same = map.Result && memcmp(map.Result, text, sizeof(text)) == 0;
    bool closed = fcntl(fd, F_GETFD) == -1;
    printf("%s: %-28s %s\n", name, "MapFile contents and close", same && closed ? "ok" : "FAIL");
    if (!same || !closed) failures++;
    if (map.Result) munmap(map.Result, sizeof(text));
    unlink(file);
}

int main(int argc, char **argv)
{
    if (argc < 2) { fprintf(stderr, "usage: %s LIBRARY.so...\n", argv[0]); return 2; }
    for (int i = 1; i < argc; i++) check(argv[i]);
    printf("%s\n", failures ? "FAILED" : "all checks passed");
    return failures != 0;
}
