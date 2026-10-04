#ifndef WINE_D3D11_PADDING_TEST_H
#define WINE_D3D11_PADDING_TEST_H

#include <stdlib.h>
#include <string.h>
#include <stdio.h>

/* Phase 3: Dirty Memory Injection for Padding Traps */

/* Allocates memory filled with 0xCC to detect implicit padding */
static inline void *malloc_dirty(size_t size)
{
    void *ptr = malloc(size);
    if (ptr)
        memset(ptr, 0xCC, size);
    return ptr;
}

/* Scans memory for 0xCC bytes to check if implicit padding leaked */
static inline int check_uninitialized_padding(const char *name, const void *ptr, size_t size)
{
    const unsigned char *bytes = (const unsigned char *)ptr;
    size_t i;
    int leaks = 0;
    
    for (i = 0; i < size; ++i)
    {
        if (bytes[i] == 0xCC)
        {
            printf("[fail] Uninitialized padding byte found in %s at offset %lu\n", name, (unsigned long)i);
            leaks++;
        }
    }
    
    if (leaks == 0)
    {
        printf("[ ok ] %s has no uninitialized padding bytes\n", name);
    }
    return leaks;
}

#endif
