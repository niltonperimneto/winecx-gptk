/* WineApp Trampoline / Runner
 * When WINE_LOADER is supplied at build time, Xcode embeds the actual arm64 wine binary.
 * When built standalone, this executable acts as a launcher and diagnostic probe verifying
 * low 4GB memory access under com.apple.developer.cross-architecture-support.
 */
#include <mach-o/dyld.h>
#include <mach-o/loader.h>
#include <mach/mach.h>
#include <mach/mach_vm.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

static int map_at(const char *what, unsigned long address, size_t size)
{
    void *p = mmap((void *)address, size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON | MAP_FIXED, -1, 0);
    int ok = (p == (void *)address);
    printf("[WineApp] map %-20s at %#010lx: %s\n", what, address, ok ? "ok" : "failed");
    if (ok) ((volatile char *)p)[0] = 1;
    return ok;
}

static int verify_low_4gb(void)
{
    const struct mach_header_64 *header = (const void *)_dyld_get_image_header(0);
    const struct load_command *cmd = (const void *)(header + 1);
    for (unsigned i = 0; i < header->ncmds; i++, cmd = (const void *)((const char *)cmd + cmd->cmdsize))
    {
        const struct segment_command_64 *segment = (const void *)cmd;
        if (cmd->cmd != LC_SEGMENT_64 || strcmp(segment->segname, SEG_PAGEZERO)) continue;
        kern_return_t ret = mach_vm_deallocate(mach_task_self(), segment->vmaddr, segment->vmsize);
        printf("[WineApp] release %#llx byte pagezero: %s\n", segment->vmsize, mach_error_string(ret));
    }
    int ok = map_at("KUSER_SHARED_DATA", 0x7ffe0000, 0x10000);
    ok &= map_at("low 64k guest area", 0x10000, 0x10000);
    printf("[WineApp] %s\n", ok ? "low 4GB usable (entitlement active)" : "low 4GB NOT usable (entitlement/profile missing)");
    return ok;
}

int main(int argc, char *argv[])
{
    char exec_path[1024];
    uint32_t size = sizeof(exec_path);
    if (_NSGetExecutablePath(exec_path, &size) == 0) {
        printf("[WineApp] Executable: %s\n", exec_path);
    }
    
    int ok = verify_low_4gb();
    if (!ok) {
        fprintf(stderr, "[WineApp] Note: com.apple.developer.cross-architecture-support requires an Apple-provisioned profile.\n");
    }
    return ok ? 0 : 1;
}
