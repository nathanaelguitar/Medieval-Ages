cmake_minimum_required(VERSION 3.24)
project(OpenEmpire VERSION 1.0.0 LANGUAGES C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)
option(OE_BUILD_TESTS "Build portable tests without fetching the game or SDL" OFF)

if(OE_BUILD_TESTS)
    enable_testing()
    add_executable(oe_portable_tests portable/OETouch.c portable/OEClock.c portable/OEAssets.c tests/test_portable.c)
    target_include_directories(oe_portable_tests PRIVATE portable)
    if(NOT MSVC)
        target_compile_options(oe_portable_tests PRIVATE -Wall -Wextra -Wpedantic -Werror -UNDEBUG)
        target_link_libraries(oe_portable_tests PRIVATE m)
    endif()
    add_test(NAME portable_input_clock_assets COMMAND oe_portable_tests)
    find_package(Python3 COMPONENTS Interpreter REQUIRED)
    add_test(NAME patch_preparation COMMAND "${Python3_EXECUTABLE}" "${CMAKE_SOURCE_DIR}/tests/test_prepare.py")
    # Checks the selected 0 A.D. art resolves and that the baked manifest still describes sprites
    # that exist on disk. Needs only the standard library -- the bake itself requires Pillow and
    # assimp, but the committed output and the actor graph can be validated without either.
    add_test(NAME zeroad_art_sources COMMAND "${Python3_EXECUTABLE}" "${CMAKE_SOURCE_DIR}/tests/test_zeroad_art.py")
    return()
endif()

if(NOT CMAKE_SYSTEM_NAME STREQUAL "iOS")
    message(FATAL_ERROR "Use ./open-xcode.command on a Mac, or -DOE_BUILD_TESTS=ON for portable tests.")
endif()
enable_language(OBJC)
find_package(Python3 COMPONENTS Interpreter REQUIRED)
include(FetchContent)
# SDL2's compatibility range predates CMake 4. This permits the known old policies.
set(CMAKE_POLICY_VERSION_MINIMUM 3.5 CACHE STRING "Dependency policy compatibility")
set(BUILD_SHARED_LIBS OFF CACHE BOOL "Static app dependencies" FORCE)
set(SDL_SHARED OFF CACHE BOOL "" FORCE)
set(SDL_STATIC ON CACHE BOOL "" FORCE)
set(SDL_TEST OFF CACHE BOOL "" FORCE)
set(SDL_TESTS OFF CACHE BOOL "" FORCE)
set(SDL_HIDAPI OFF CACHE BOOL "" FORCE)
set(SDL_RENDER_METAL ON CACHE BOOL "" FORCE)
set(SDL2NET_SAMPLES OFF CACHE BOOL "" FORCE)
set(SDL2NET_INSTALL OFF CACHE BOOL "" FORCE)
FetchContent_Declare(sdl2
    URL https://github.com/libsdl-org/SDL/archive/2359383fc187386204c3bb22de89655a494cd128.tar.gz
    DOWNLOAD_EXTRACT_TIMESTAMP TRUE)
FetchContent_MakeAvailable(sdl2)
FetchContent_Declare(sdl2net
    URL https://github.com/libsdl-org/SDL_net/archive/669e75b84632e2c6cc5c65974ec9e28052cb7a4e.tar.gz
    DOWNLOAD_EXTRACT_TIMESTAMP TRUE)
FetchContent_MakeAvailable(sdl2net)
FetchContent_Declare(openempire
    URL https://github.com/glouw/openempire/archive/466fc251f1bcad69c917c31c94ffa4c069700cc2.tar.gz
    DOWNLOAD_EXTRACT_TIMESTAMP TRUE)
FetchContent_MakeAvailable(openempire)
set(ENGINE "${CMAKE_BINARY_DIR}/engine")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
    "${CMAKE_SOURCE_DIR}/scripts/prepare_engine.py" "${CMAKE_SOURCE_DIR}/ios/Text.h")
execute_process(
    COMMAND "${Python3_EXECUTABLE}" "${CMAKE_SOURCE_DIR}/scripts/prepare_engine.py"
        --source "${openempire_SOURCE_DIR}" --destination "${ENGINE}" --port "${CMAKE_SOURCE_DIR}"
    COMMAND_ERROR_IS_FATAL ANY)
file(GLOB ENGINE_SOURCES CONFIGURE_DEPENDS "${ENGINE}/*.c")
list(REMOVE_ITEM ENGINE_SOURCES "${ENGINE}/main.c" "${ENGINE}/Input.c" "${ENGINE}/Text.c")

# The selected 0 A.D. art is bundled as native SceneKit resources. Collada
# files in the upstream snapshot use constructs SceneKit does not import on
# current iOS, so the checked-in Assimp OBJ conversions and PNGs are included
# alongside the original attribution and material metadata.
set(OE_ART_ROOT "${CMAKE_SOURCE_DIR}/ios/ZeroADArt")
file(GLOB_RECURSE OE_ART_FILES CONFIGURE_DEPENDS
    "${OE_ART_ROOT}/*.obj"
    "${OE_ART_ROOT}/*.mtl"
    "${OE_ART_ROOT}/*.png"
    "${OE_ART_ROOT}/*.xml"
    "${OE_ART_ROOT}/*.txt")
foreach(OE_ART_FILE IN LISTS OE_ART_FILES)
    file(RELATIVE_PATH OE_ART_REL "${OE_ART_ROOT}" "${OE_ART_FILE}")
    get_filename_component(OE_ART_DIR "${OE_ART_REL}" DIRECTORY)
    if(OE_ART_DIR STREQUAL "")
        set(OE_ART_RESOURCE_DIR "Resources/ZeroADArt")
    else()
        set(OE_ART_RESOURCE_DIR "Resources/ZeroADArt/${OE_ART_DIR}")
    endif()
    set_source_files_properties("${OE_ART_FILE}" PROPERTIES
        MACOSX_PACKAGE_LOCATION "${OE_ART_RESOURCE_DIR}")
endforeach()

# The bundled browser game is a self-contained canvas build. Keep it in a
# subdirectory so WKWebView can grant local read access to the game root.
set(OE_WEB_ROOT "${CMAKE_SOURCE_DIR}/ios/WebGame")
file(GLOB_RECURSE OE_WEB_FILES CONFIGURE_DEPENDS
    "${OE_WEB_ROOT}/*")
foreach(OE_WEB_FILE IN LISTS OE_WEB_FILES)
    file(RELATIVE_PATH OE_WEB_REL "${OE_WEB_ROOT}" "${OE_WEB_FILE}")
    get_filename_component(OE_WEB_DIR "${OE_WEB_REL}" DIRECTORY)
    if(OE_WEB_DIR STREQUAL "")
        set(OE_WEB_RESOURCE_DIR "Resources/open-empire-mobile")
    else()
        set(OE_WEB_RESOURCE_DIR "Resources/open-empire-mobile/${OE_WEB_DIR}")
    endif()
    set_source_files_properties("${OE_WEB_FILE}" PROPERTIES
        MACOSX_PACKAGE_LOCATION "${OE_WEB_RESOURCE_DIR}")
endforeach()

set(NATIVE_SOURCES ios/main.m ios/OEPlatform.m ios/OEText.m ios/OEArtDemo.m ios/OEWebGame.m)
add_executable(OpenEmpire MACOSX_BUNDLE ${ENGINE_SOURCES} ${NATIVE_SOURCES}
    ios/OEInput.c ios/OERuntime.c portable/OETouch.c portable/OEClock.c portable/OEAssets.c
    ios/Assets.xcassets ios/PrivacyInfo.xcprivacy ${OE_ART_FILES} ${OE_WEB_FILES})
target_include_directories(OpenEmpire PRIVATE "${ENGINE}" ios portable)
target_link_libraries(OpenEmpire PRIVATE SDL2::SDL2-static SDL2_net::SDL2_net-static
    "-framework UIKit" "-framework Foundation" "-framework QuartzCore"
    "-framework Metal" "-framework SceneKit" "-framework CoreGraphics"
    "-framework UniformTypeIdentifiers" "-framework WebKit")
target_compile_definitions(OpenEmpire PRIVATE SANITIZE_ADDRESS=0 SANITIZE_THREAD=0 SANITIZE_UNDEFINED=0)
target_compile_options(OpenEmpire PRIVATE -Wall -Wextra -Wno-unused-function -UNDEBUG)
set_source_files_properties(${NATIVE_SOURCES} PROPERTIES COMPILE_OPTIONS "-fobjc-arc")
set_source_files_properties(ios/Assets.xcassets ios/PrivacyInfo.xcprivacy PROPERTIES MACOSX_PACKAGE_LOCATION Resources)
set(OE_BUNDLE_ID "org.openempire.ios" CACHE STRING "Unique bundle ID for your signing team")
set(OE_DEVELOPMENT_TEAM "" CACHE STRING "Optional Apple Development Team ID")
set_target_properties(OpenEmpire PROPERTIES
    MACOSX_BUNDLE_INFO_PLIST "${CMAKE_SOURCE_DIR}/ios/Info.plist.in"
    MACOSX_BUNDLE_GUI_IDENTIFIER "${OE_BUNDLE_ID}"
    MACOSX_BUNDLE_BUNDLE_NAME "OpenEmpire"
    MACOSX_BUNDLE_SHORT_VERSION_STRING "1.0"
    MACOSX_BUNDLE_BUNDLE_VERSION "1"
    XCODE_GENERATE_SCHEME TRUE
    XCODE_ATTRIBUTE_PRODUCT_BUNDLE_IDENTIFIER "${OE_BUNDLE_ID}"
    XCODE_ATTRIBUTE_TARGETED_DEVICE_FAMILY "1,2"
    XCODE_ATTRIBUTE_IPHONEOS_DEPLOYMENT_TARGET "15.0"
    XCODE_ATTRIBUTE_CODE_SIGN_STYLE "Automatic"
    XCODE_ATTRIBUTE_ENABLE_BITCODE "NO"
    XCODE_ATTRIBUTE_CLANG_ENABLE_OBJC_ARC "YES"
    XCODE_ATTRIBUTE_ASSETCATALOG_COMPILER_APPICON_NAME "AppIcon"
    XCODE_ATTRIBUTE_SUPPORTS_MACCATALYST "NO"
    XCODE_ATTRIBUTE_SUPPORTS_MAC_DESIGNED_FOR_IPHONE_IPAD "NO")
if(OE_DEVELOPMENT_TEAM)
    set_target_properties(OpenEmpire PROPERTIES XCODE_ATTRIBUTE_DEVELOPMENT_TEAM "${OE_DEVELOPMENT_TEAM}")
endif()
