cmake_minimum_required(VERSION 3.22)
project(harr_codex_scheduler VERSION 0.2.0 LANGUAGES CXX)

if(CMAKE_INSTALL_PREFIX_INITIALIZED_TO_DEFAULT)
    set(CMAKE_INSTALL_PREFIX "/usr" CACHE PATH "Install prefix" FORCE)
endif()

if(NOT DEFINED SCHEDULER_VERSION)
    file(STRINGS "${CMAKE_CURRENT_SOURCE_DIR}/VERSION" SCHEDULER_VERSION LIMIT_COUNT 1)
endif()
if(NOT SCHEDULER_VERSION MATCHES "^[0-9]+\\.[0-9]+\\.[0-9]+([.+~-][A-Za-z0-9.+~-]+)?$")
    message(FATAL_ERROR "Invalid SCHEDULER_VERSION: ${SCHEDULER_VERSION}")
endif()
set(SCHEDULER_VERSION "${SCHEDULER_VERSION}" CACHE STRING "Scheduler package version" FORCE)

if(NOT CMAKE_CONFIGURATION_TYPES AND NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Debug CACHE STRING "Build type" FORCE)
endif()

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_AUTOMOC ON)

find_package(Qt6 6.4 REQUIRED COMPONENTS Core Gui Widgets)

option(SCHEDULER_ENABLE_SANITIZERS "Enable AddressSanitizer and UndefinedBehaviorSanitizer" OFF)

set(SCHEDULER_SOURCES
    src/main.cpp
    src/Common.cpp
    src/TaskStore.cpp
    src/CodexService.cpp
    src/ScheduleCore.cpp
    src/JobRunner.cpp
    src/Widgets.cpp
    src/TaskPage.cpp
    src/QuickSchedule.cpp
    src/MainWindow.cpp
)

add_executable(harr-codex-scheduler
    ${SCHEDULER_SOURCES}
)

set_target_properties(harr-codex-scheduler PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}"
)

target_include_directories(harr-codex-scheduler PRIVATE src)

target_link_libraries(harr-codex-scheduler PRIVATE
    Qt6::Core
    Qt6::Gui
    Qt6::Widgets
)

target_compile_options(harr-codex-scheduler PRIVATE
    -Wall
    -Wextra
    -Wpedantic
)

if(SCHEDULER_ENABLE_SANITIZERS)
    target_compile_options(harr-codex-scheduler PRIVATE
        -fsanitize=address,undefined
        -fno-omit-frame-pointer
    )
    target_link_options(harr-codex-scheduler PRIVATE -fsanitize=address,undefined)
endif()

include(GNUInstallDirs)

set(SCHEDULER_BIN_FILES
    codex-schedule
    codex-scheduler-ui
    sol
    terra
    luna
)
set(SCHEDULER_BIN_PATHS)
foreach(BIN_FILE IN LISTS SCHEDULER_BIN_FILES)
    list(APPEND SCHEDULER_BIN_PATHS "${CMAKE_CURRENT_SOURCE_DIR}/bin/${BIN_FILE}")
endforeach()
set(SCHEDULER_DESKTOP_EXECUTABLE "/usr/bin/harr-codex-scheduler")

configure_file(
    "${CMAKE_CURRENT_SOURCE_DIR}/desktop/harr-codex-scheduler.desktop.in"
    "${CMAKE_CURRENT_BINARY_DIR}/harr-codex-scheduler.desktop"
    @ONLY
)

install(TARGETS harr-codex-scheduler RUNTIME DESTINATION "${CMAKE_INSTALL_BINDIR}")
install(PROGRAMS
    ${SCHEDULER_BIN_PATHS}
    DESTINATION "${CMAKE_INSTALL_BINDIR}"
)
install(FILES
    "${CMAKE_CURRENT_BINARY_DIR}/harr-codex-scheduler.desktop"
    DESTINATION "${CMAKE_INSTALL_DATADIR}/applications"
)
install(FILES
    "${CMAKE_CURRENT_SOURCE_DIR}/README.md"
    DESTINATION "${CMAKE_INSTALL_DOCDIR}/harr-codex-scheduler"
)

set(SCHEDULER_PACKAGE_OUTPUT_DIR "${CMAKE_SOURCE_DIR}/dist" CACHE PATH
    "Directory for generated Debian and portable packages")

execute_process(
    COMMAND dpkg --print-architecture
    OUTPUT_VARIABLE SCHEDULER_ARCH
    OUTPUT_STRIP_TRAILING_WHITESPACE
    ERROR_QUIET
)
if(NOT SCHEDULER_ARCH)
    set(SCHEDULER_ARCH "${CMAKE_SYSTEM_PROCESSOR}")
    if(SCHEDULER_ARCH STREQUAL "x86_64")
        set(SCHEDULER_ARCH amd64)
    elseif(SCHEDULER_ARCH STREQUAL "aarch64")
        set(SCHEDULER_ARCH arm64)
    endif()
endif()

set(SCHEDULER_POSTINST "${CMAKE_CURRENT_BINARY_DIR}/packaging/postinst")
file(MAKE_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/packaging")
configure_file(
    "${CMAKE_CURRENT_SOURCE_DIR}/packaging/postinst.in"
    "${SCHEDULER_POSTINST}"
    @ONLY
)
file(CHMOD "${SCHEDULER_POSTINST}"
    PERMISSIONS
        OWNER_READ OWNER_WRITE OWNER_EXECUTE
        GROUP_READ GROUP_EXECUTE
        WORLD_READ WORLD_EXECUTE
)

set(CPACK_GENERATOR "DEB")
set(CPACK_PACKAGE_NAME "harr-codex-scheduler")
set(CPACK_PACKAGE_VENDOR "Harr Codex Scheduler contributors")
set(CPACK_PACKAGE_VERSION "${SCHEDULER_VERSION}")
set(CPACK_PACKAGE_DESCRIPTION_SUMMARY "Native Qt scheduler for existing OpenAI Codex CLI sessions")
set(CPACK_PACKAGE_CONTACT "Harr Codex Scheduler contributors")
set(CPACK_PACKAGE_INSTALL_DIRECTORY "harr-codex-scheduler")
set(CPACK_OUTPUT_FILE_PREFIX "${SCHEDULER_PACKAGE_OUTPUT_DIR}")
set(CPACK_PACKAGING_INSTALL_PREFIX "/usr")
set(CPACK_DEBIAN_PACKAGE_ARCHITECTURE "${SCHEDULER_ARCH}")
set(CPACK_DEBIAN_FILE_NAME
    "harr-codex-scheduler_${SCHEDULER_VERSION}_${SCHEDULER_ARCH}.deb")
set(CPACK_DEBIAN_PACKAGE_SECTION "utils")
set(CPACK_DEBIAN_PACKAGE_PRIORITY "optional")
set(CPACK_DEBIAN_PACKAGE_DEPENDS
    "at, git, bash, util-linux, libqt6core6t64, libqt6gui6t64, libqt6widgets6t64"
)
set(CPACK_DEBIAN_PACKAGE_SHLIBDEPS OFF)
set(CPACK_DEBIAN_PACKAGE_CONTROL_EXTRA "${SCHEDULER_POSTINST}")

include(CPack)

add_custom_target(package-deb
    COMMAND "${CMAKE_CPACK_COMMAND}" --config "${CMAKE_BINARY_DIR}/CPackConfig.cmake" -G DEB
    DEPENDS harr-codex-scheduler
    USES_TERMINAL
)

add_custom_target(package-portable
    COMMAND "${CMAKE_COMMAND}"
        "-DPORTABLE_SOURCE_DIR=${CMAKE_CURRENT_SOURCE_DIR}"
        "-DPORTABLE_BINARY=${CMAKE_BINARY_DIR}/harr-codex-scheduler"
        "-DPORTABLE_VERSION=${SCHEDULER_VERSION}"
        "-DPORTABLE_ARCH=${SCHEDULER_ARCH}"
        "-DPORTABLE_OUTPUT_DIR=${SCHEDULER_PACKAGE_OUTPUT_DIR}"
        -P "${CMAKE_CURRENT_SOURCE_DIR}/packaging/package-portable.cmake"
    DEPENDS harr-codex-scheduler
    USES_TERMINAL
)

add_custom_target(package-release DEPENDS package-deb package-portable)
