/* Check whether this process may use the low 4GB on arm64 macOS, as Wine
 * needs to: release the pagezero the way arm64 ntdll's free_pagezero does,
 * then map KUSER_SHARED_DATA at 0x7ffe0000 and the low 64k guest area.
 * Exits 0 only if both maps land where asked.
 *
 *   clang -arch arm64 -o pagezero_probe tests/pagezero_probe.c
 *
 * A plain or ad-hoc signed build fails the maps; one claiming the restricted
 * com.apple.developer.cross-architecture-support entitlement without an
 * Apple-issued profile is killed at exec. Wrap it with make-wine-app.sh to
 * test a provisioning profile before building Wine.
 */
#include <mach-o/dyld.h>
#include <mach-o/loader.h>
#include <mach/mach.h>
#include <mach/mach_vm.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>

static int map_at(const char *what, unsigned long address, size_t size)
{
    void *p = mmap((void *)address, size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON | MAP_FIXED, -1, 0);
    int ok = p == (void *)address;
    printf("map %-20s at %#010lx: %s\n", what, address, ok ? "ok" : "failed");
    if (ok) ((volatile char *)p)[0] = 1;
    return ok;
}

int main(void)
{
    const struct mach_header_64 *header = (const void *)_dyld_get_image_header(0);
    const struct load_command *cmd = (const void *)(header + 1);
    for (unsigned i = 0; i < header->ncmds; i++, cmd = (const void *)((const char *)cmd + cmd->cmdsize))
    {
        const struct segment_command_64 *segment = (const void *)cmd;
        if (cmd->cmd != LC_SEGMENT_64 || strcmp(segment->segname, SEG_PAGEZERO)) continue;
        kern_return_t ret = mach_vm_deallocate(mach_task_self(), segment->vmaddr, segment->vmsize);
        printf("release %#llx byte pagezero: %s\n", segment->vmsize, mach_error_string(ret));
    }
    int ok = map_at("KUSER_SHARED_DATA", 0x7ffe0000, 0x10000);
    ok &= map_at("low 64k guest area", 0x10000, 0x10000);
    printf("%s\n", ok ? "low 4GB usable" : "low 4GB NOT usable");
    return !ok;
}
