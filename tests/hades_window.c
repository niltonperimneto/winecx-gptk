/* Send menu keys only to a Hades window in this Wine prefix. No global input. */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static HWND target;
static BOOL CALLBACK find_window(HWND window, LPARAM unused) {
    char title[256];
    GetWindowTextA(window, title, sizeof(title));
    if (IsWindowVisible(window) && !strcmp(title, "Hades")) target = window;
    return TRUE;
}
int main(int argc, char **argv) {
    EnumWindows(find_window, 0);
    if (!target) return 2;
    if (argc == 2 && !strcmp(argv[1], "close")) {
        return PostMessageA(target, WM_CLOSE, 0, 0) ? 0 : 3;
    }
    unsigned key = argc == 2 ? strtoul(argv[1], NULL, 0) : VK_RETURN;
    unsigned scan = MapVirtualKeyA(key, MAPVK_VK_TO_VSC);
    PostMessageA(target, WM_KEYDOWN, key, 1 | (scan << 16));
    Sleep(80);
    PostMessageA(target, WM_KEYUP, key, 1 | (scan << 16) | 0xc0000000);
    return 0;
}
