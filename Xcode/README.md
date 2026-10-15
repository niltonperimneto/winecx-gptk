# WineArm64 Xcode Project

This Xcode project provides an IDE environment to configure signing identities, provisioning profiles, and entitlements for arm64 Wine on macOS Apple Silicon.

## Targets & Schemes

### 1. `PagezeroProbe`
- **Source**: `tests/pagezero_probe.c`
- **Output**: `PagezeroProbe.app`
- **Entitlements**: `com.apple.developer.cross-architecture-support = YES`
- **Purpose**: Rapidly verifies whether macOS permits dropping the 4GB `PAGEZERO` and mapping the low 64k guest area (`0x10000`) and `KUSER_SHARED_DATA` (`0x7ffe0000`).
- **Usage**: Select `PagezeroProbe` in the scheme selector and hit **Cmd+R**. If the provisioning profile is valid, it prints `low 4GB usable` and exits 0.

### 2. `WineApp`
- **Output**: `wine.app`
- **Entitlements**: `com.apple.developer.cross-architecture-support = YES`
- **Build Phases**:
  - Compiles the launcher runner / trampoline.
  - Runs `Xcode/WineApp/post_build.sh`:
    - If `WINE_LOADER` is provided, copies that binary into `wine.app/Contents/MacOS/wine`.
    - Creates the required relative symlink `wine.app/Contents/MacOS/ntdll.so -> ../../../ntdll.so`.
    - If `WINE_PROVISIONING_PROFILE` is specified, embeds it into `Contents/embedded.provisionprofile`.
  - Xcode native code signing automatically signs the bundle with the designated identity, entitlements, and profile.

### 3. `SignRuntime`
- **Purpose**: Helper aggregate target to invoke `Xcode/Scripts/sign_runtime.sh` or `arm64/make-wine-app.sh` directly.

## Signing Setup in Xcode

1. Open `WineArm64.xcodeproj` in Xcode:
   ```sh
   open WineArm64.xcodeproj
   ```
2. In the Project Navigator, select **WineArm64** and navigate to the **Signing & Capabilities** tab.
3. For each target (`PagezeroProbe` and `WineApp`):
   - **Team**: Select your Apple Developer Team (`4ULPH24442` / `niltomperimneto@gmail.com`).
   - **Bundle Identifier**: Set your registered App ID prefix (default `com.niltonperimneto.*`).
   - **Provisioning Profile**:
     - **Automatic**: If your Apple Developer account has the `cross-architecture-support` capability enabled by Apple, Xcode will generate and download the profile automatically.
     - **Manual**: If Apple issued a custom `.provisionprofile` file, uncheck "Automatically manage signing" and select / import the profile.

## Maintenance & Regeneration

The project structure is generated using the Ruby script:
```sh
ruby Xcode/Scripts/generate_project.rb
```
