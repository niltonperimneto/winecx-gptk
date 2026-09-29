#import <Metal/Metal.h>
#include <stdio.h>

int main(void) {
    @autoreleasepool {
        id<MTLDevice> device = MTLCreateSystemDefaultDevice();
        if (device == nil) {
            puts("Metal device unavailable on this runner");
            return 2;
        }
        printf("Metal device: %s\n", [[device name] UTF8String]);
        return 0;
    }
}
