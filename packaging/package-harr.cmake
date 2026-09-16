cmake_minimum_required(VERSION 3.22)

if(NOT DEFINED HARR_SOURCE_DIR)
    get_filename_component(HARR_SOURCE_DIR "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE)
endif()
if(NOT DEFINED HARR_VERSION OR NOT DEFINED HARR_ARCH OR NOT DEFINED HARR_OUTPUT_DIR)
    message(FATAL_ERROR "HARR_VERSION, HARR_ARCH and HARR_OUTPUT_DIR are required")
endif()
if(NOT HARR_VERSION MATCHES "^[0-9]+\\.[0-9]+\\.[0-9]+([.+~-][A-Za-z0-9.+~-]+)?$")
    message(FATAL_ERROR "Invalid HARR_VERSION: ${HARR_VERSION}")
endif()
if(NOT IS_DIRECTORY "${HARR_SOURCE_DIR}")
    message(FATAL_ERROR "HARR_SOURCE_DIR does not exist: ${HARR_SOURCE_DIR}")
endif()

set(NAME "harr-${HARR_VERSION}-linux-${HARR_ARCH}")
if(NOT DEFINED HARR_TEMP_DIR OR HARR_TEMP_DIR STREQUAL "")
    set(HARR_TEMP_DIR "/tmp")
endif()
set(STAGE_PARENT "${HARR_TEMP_DIR}/harr-package-${HARR_VERSION}-${HARR_ARCH}")
set(STAGE_ROOT "${STAGE_PARENT}/${NAME}")
set(OUTPUT_DEB "${HARR_OUTPUT_DIR}/harr_${HARR_VERSION}_${HARR_ARCH}.deb")
set(OUTPUT_TAR "${HARR_OUTPUT_DIR}/${NAME}.tar.gz")
set(DEB_ROOT "${STAGE_PARENT}/deb-root")

file(REMOVE_RECURSE "${STAGE_PARENT}")
file(REMOVE "${OUTPUT_DEB}" "${OUTPUT_TAR}")
file(MAKE_DIRECTORY "${STAGE_ROOT}" "${HARR_OUTPUT_DIR}")

# Release builds use git archive to package exactly the checked-out commit.
# Local invocations default to the worktree so uncommitted packaging changes
# can be tested before the release commit exists.
if(DEFINED HARR_ARCHIVE_REF AND NOT HARR_ARCHIVE_REF STREQUAL "")
    set(SOURCE_ARCHIVE "${STAGE_PARENT}/harr-source.tar")
    execute_process(
        COMMAND git -C "${HARR_SOURCE_DIR}" archive --format=tar
                "--prefix=${NAME}/" "${HARR_ARCHIVE_REF}"
        OUTPUT_FILE "${SOURCE_ARCHIVE}"
        RESULT_VARIABLE ARCHIVE_RESULT
    )
    if(NOT ARCHIVE_RESULT EQUAL 0)
        message(FATAL_ERROR "Could not archive Harr source at ${HARR_ARCHIVE_REF}")
    endif()
    execute_process(
        COMMAND "${CMAKE_COMMAND}" -E tar xf "${SOURCE_ARCHIVE}"
        WORKING_DIRECTORY "${STAGE_PARENT}"
        RESULT_VARIABLE EXTRACT_RESULT
    )
    if(NOT EXTRACT_RESULT EQUAL 0)
        message(FATAL_ERROR "Could not extract Harr source archive")
    endif()
else()
    file(GLOB HARR_ENTRIES RELATIVE "${HARR_SOURCE_DIR}"
         "${HARR_SOURCE_DIR}/*" "${HARR_SOURCE_DIR}/.*")
    foreach(ENTRY IN LISTS HARR_ENTRIES)
        if(NOT ENTRY STREQUAL "." AND NOT ENTRY STREQUAL ".." AND
           NOT ENTRY STREQUAL ".git" AND NOT ENTRY STREQUAL ".idea" AND
           NOT ENTRY STREQUAL ".codegraph" AND NOT ENTRY STREQUAL "harr-package")
            file(COPY "${HARR_SOURCE_DIR}/${ENTRY}" DESTINATION "${STAGE_ROOT}"
                 PATTERN ".git" EXCLUDE
                 PATTERN ".idea" EXCLUDE
                 PATTERN ".codegraph" EXCLUDE
                 PATTERN "build" EXCLUDE
                 PATTERN "build-*" EXCLUDE
                 PATTERN "dist" EXCLUDE)
        endif()
    endforeach()
endif()

if(NOT EXISTS "${STAGE_ROOT}/install.sh" OR
   NOT EXISTS "${STAGE_ROOT}/linux/install.sh" OR
   NOT EXISTS "${STAGE_ROOT}/common/mcp/registry.json")
    message(FATAL_ERROR "Harr source archive is incomplete")
endif()

execute_process(
    COMMAND "${CMAKE_COMMAND}" -E tar czf "${OUTPUT_TAR}" --format=gnutar "${NAME}"
    WORKING_DIRECTORY "${STAGE_PARENT}"
    RESULT_VARIABLE TAR_RESULT
)
if(NOT TAR_RESULT EQUAL 0)
    message(FATAL_ERROR "Could not create Harr portable archive: ${OUTPUT_TAR}")
endif()

file(MAKE_DIRECTORY
    "${DEB_ROOT}/DEBIAN"
    "${DEB_ROOT}/usr/bin"
    "${DEB_ROOT}/usr/lib"
    "${DEB_ROOT}/usr/share/doc/harr"
)
file(COPY "${STAGE_ROOT}" DESTINATION "${DEB_ROOT}/usr/lib")
file(RENAME "${DEB_ROOT}/usr/lib/${NAME}" "${DEB_ROOT}/usr/lib/harr")
file(CREATE_LINK "/usr/lib/harr/linux/harr" "${DEB_ROOT}/usr/bin/harr" SYMBOLIC)
file(CREATE_LINK "/usr/lib/harr/install.sh" "${DEB_ROOT}/usr/bin/harr-install" SYMBOLIC)

file(WRITE "${DEB_ROOT}/usr/share/doc/harr/INSTALL.md" [=[# Harr after package installation

The Debian package installs Harr itself but does not silently alter the user's
global agent configuration or select optional MCPs.

Run as the normal user:

    harr-install --clean

The first interactive run opens the optional MCP checklist. For automation use
`harr-install --clean --all` or `harr-install --clean --mcp none` (or a comma-
separated list such as `--mcp gitlab,grafana`). Later updates reuse the saved
selection; change it with `harr mcp configure`.
]=])
file(COPY "${STAGE_ROOT}/README.md" DESTINATION "${DEB_ROOT}/usr/share/doc/harr")

file(WRITE "${DEB_ROOT}/DEBIAN/control"
"Package: harr\n"
"Version: ${HARR_VERSION}\n"
"Section: admin\n"
"Priority: optional\n"
"Architecture: ${HARR_ARCH}\n"
"Depends: bash, python3, git, coreutils, util-linux, systemd | systemd-sysv\n"
"Maintainer: Harr contributors\n"
"Description: Harr global harness for token-efficient MCP infrastructure\n"
" Harr installs and manages LeanCTX, CodeGraph and selectable MCP services.\n"
" The package itself only installs the files; user-level configuration is\n"
" performed explicitly by harr-install.\n")

execute_process(
    COMMAND dpkg-deb --root-owner-group --build "${DEB_ROOT}" "${OUTPUT_DEB}"
    RESULT_VARIABLE DEB_RESULT
    OUTPUT_VARIABLE DEB_OUTPUT
    ERROR_VARIABLE DEB_ERROR
)
if(NOT DEB_RESULT EQUAL 0)
    message(FATAL_ERROR "Could not create Harr Debian package:\n${DEB_OUTPUT}\n${DEB_ERROR}")
endif()

message(STATUS "Built Harr Debian package: ${OUTPUT_DEB}")
message(STATUS "Built Harr portable archive: ${OUTPUT_TAR}")
