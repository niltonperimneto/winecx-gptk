require 'xcodeproj'
require 'fileutils'

repo_root = File.expand_path('../..', __dir__)
project_path = File.join(repo_root, 'WineArm64.xcodeproj')

# Remove existing project if any
FileUtils.rm_rf(project_path) if File.exist?(project_path)

project = Xcodeproj::Project.new(project_path)

# Root level build settings
project.build_configurations.each do |config|
  config.build_settings['ARCHS'] = 'arm64'
  config.build_settings['ONLY_ACTIVE_ARCH'] = config.name == 'Debug' ? 'YES' : 'NO'
  config.build_settings['MACOSX_DEPLOYMENT_TARGET'] = '14.0'
  config.build_settings['SDKROOT'] = 'macosx'
  config.build_settings['DEVELOPMENT_TEAM'] = '4ULPH24442'
  config.build_settings['CODE_SIGN_STYLE'] = 'Automatic'
  config.build_settings['CODE_SIGN_IDENTITY'] = 'Apple Development'
  config.build_settings['ENABLE_HARDENED_RUNTIME'] = 'NO'
  config.build_settings['GCC_C_LANGUAGE_STANDARD'] = 'gnu11'
  config.build_settings['CLANG_ENABLE_OBJC_ARC'] = 'YES'
  config.build_settings['CLANG_ENABLE_MODULES'] = 'YES'
  config.build_settings['ALWAYS_SEARCH_USER_PATHS'] = 'NO'
end

# Groups
main_group = project.main_group

pagezero_group = main_group.new_group('PagezeroProbe', 'Xcode/PagezeroProbe')
probe_entitlements_ref = pagezero_group.new_file('PagezeroProbe.entitlements')
probe_plist_ref = pagezero_group.new_file('Info.plist')

tests_group = main_group.new_group('Tests', 'tests')
pagezero_source_ref = tests_group.new_file('pagezero_probe.c')

wineapp_group = main_group.new_group('WineApp', 'Xcode/WineApp')
wineapp_main_ref = wineapp_group.new_file('main.c')
wineapp_entitlements_ref = wineapp_group.new_file('WineApp.entitlements')
wineapp_plist_ref = wineapp_group.new_file('Info.plist')
wineapp_post_build_ref = wineapp_group.new_file('post_build.sh')

scripts_group = main_group.new_group('Scripts', 'Xcode/Scripts')
sign_runtime_ref = scripts_group.new_file('sign_runtime.sh')

# Target 1: PagezeroProbe
probe_target = project.new_target(:application, 'PagezeroProbe', :osx)
probe_target.source_build_phase.add_file_reference(pagezero_source_ref)

probe_target.build_configurations.each do |config|
  config.build_settings['PRODUCT_NAME'] = 'PagezeroProbe'
  config.build_settings['PRODUCT_BUNDLE_IDENTIFIER'] = 'com.niltonperimneto.pagezero-probe'
  config.build_settings['INFOPLIST_FILE'] = 'Xcode/PagezeroProbe/Info.plist'
  config.build_settings['CODE_SIGN_ENTITLEMENTS'] = 'Xcode/PagezeroProbe/PagezeroProbe.entitlements'
  config.build_settings['DEVELOPMENT_TEAM'] = '4ULPH24442'
  config.build_settings['CODE_SIGN_STYLE'] = 'Automatic'
  config.build_settings['CODE_SIGN_IDENTITY'] = 'Apple Development'
  config.build_settings['ENABLE_HARDENED_RUNTIME'] = 'NO'
  config.build_settings['ARCHS'] = 'arm64'
end

# Target 2: WineApp
wine_target = project.new_target(:application, 'WineApp', :osx)
wine_target.source_build_phase.add_file_reference(wineapp_main_ref)

# Add Run Script phase to WineApp to run post_build.sh before codesign
post_build_phase = wine_target.new_shell_script_build_phase('Stage Wine Loader & Symlinks')
post_build_phase.shell_script = 'bash "${PROJECT_DIR}/Xcode/WineApp/post_build.sh"'
post_build_phase.always_out_of_date = '1'

wine_target.build_configurations.each do |config|
  config.build_settings['PRODUCT_NAME'] = 'wine'
  config.build_settings['WRAPPER_EXTENSION'] = 'app'
  config.build_settings['PRODUCT_BUNDLE_IDENTIFIER'] = 'com.niltonperimneto.wine'
  config.build_settings['INFOPLIST_FILE'] = 'Xcode/WineApp/Info.plist'
  config.build_settings['CODE_SIGN_ENTITLEMENTS'] = 'Xcode/WineApp/WineApp.entitlements'
  config.build_settings['DEVELOPMENT_TEAM'] = '4ULPH24442'
  config.build_settings['CODE_SIGN_STYLE'] = 'Automatic'
  config.build_settings['CODE_SIGN_IDENTITY'] = 'Apple Development'
  config.build_settings['ENABLE_HARDENED_RUNTIME'] = 'NO'
  config.build_settings['ARCHS'] = 'arm64'
end

# Target 3: SignRuntime (Aggregate Target)
sign_target = project.new_aggregate_target('SignRuntime')
sign_phase = sign_target.new_shell_script_build_phase('Sign Runtime Helper')
sign_phase.shell_script = <<'SCRIPT'
echo "== SignRuntime Scheme =="
echo "To sign a custom Wine executable or directory with make-wine-app.sh:"
echo "bash ${PROJECT_DIR}/Xcode/Scripts/sign_runtime.sh <EXECUTABLE> <APP_DIRECTORY> <PROFILE> [IDENTITY]"
SCRIPT
sign_phase.always_out_of_date = '1'

project.save

# Generate shared schemes
shared_data_dir = File.join(project_path, 'xcshareddata', 'xcschemes')
FileUtils.mkdir_p(shared_data_dir)

# Scheme for PagezeroProbe
scheme_probe = Xcodeproj::XCScheme.new
scheme_probe.add_build_target(probe_target)
scheme_probe.set_launch_target(probe_target)
scheme_probe.save_as(project_path, 'PagezeroProbe', true)

# Scheme for WineApp
scheme_wine = Xcodeproj::XCScheme.new
scheme_wine.add_build_target(wine_target)
scheme_wine.set_launch_target(wine_target)
scheme_wine.save_as(project_path, 'WineApp', true)

# Scheme for SignRuntime
scheme_sign = Xcodeproj::XCScheme.new
scheme_sign.add_build_target(sign_target)
scheme_sign.save_as(project_path, 'SignRuntime', true)

puts "Successfully regenerated #{project_path}"
