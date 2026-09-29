#import <Metal/Metal.h>
#include <stdio.h>

int main(void) {
    @autoreleasepool {
        id<MTLDevice> device = MTLCreateSystemDefaultDevice();
        if (device == nil) {
            puts("Metal device unavailable on this runner");
            return 2;
        }
        NSString *name = [device name];
        printf("Metal device: %s\n", [name UTF8String]);
        if ([name rangeOfString:@"Paravirtual" options:NSCaseInsensitiveSearch].location != NSNotFound) {
            puts("Virtual Metal device cannot validate KosmicKrisp on Apple hardware");
            return 2;
        }
        return 0;
    }
}
