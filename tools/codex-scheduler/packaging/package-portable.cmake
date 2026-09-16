if(NOT DEFINED PORTABLE_SOURCE_DIR OR NOT DEFINED PORTABLE_BINARY OR
   NOT DEFINED PORTABLE_VERSION OR NOT DEFINED PORTABLE_ARCH OR
   NOT DEFINED PORTABLE_OUTPUT_DIR)
    message(FATAL_ERROR "Portable package variables are required")
endif()

set(NAME "harr-codex-scheduler-${PORTABLE_VERSION}-linux-${PORTABLE_ARCH}")
set(STAGE_PARENT "${CMAKE_CURRENT_BINARY_DIR}/portable")
set(STAGE_ROOT "${STAGE_PARENT}/${NAME}")
set(OUTPUT "${PORTABLE_OUTPUT_DIR}/${NAME}.tar.gz")

if(NOT EXISTS "${PORTABLE_BINARY}")
    message(FATAL_ERROR "Scheduler binary was not produced: ${PORTABLE_BINARY}")
endif()

file(REMOVE_RECURSE "${STAGE_ROOT}")
file(REMOVE "${OUTPUT}")
file(MAKE_DIRECTORY "${STAGE_ROOT}/bin" "${PORTABLE_OUTPUT_DIR}")

file(INSTALL DESTINATION "${STAGE_ROOT}" TYPE PROGRAM FILES "${PORTABLE_BINARY}")
foreach(BIN_FILE codex-schedule codex-scheduler-ui sol terra luna)
    file(INSTALL DESTINATION "${STAGE_ROOT}/bin" TYPE PROGRAM
         FILES "${PORTABLE_SOURCE_DIR}/bin/${BIN_FILE}")
endforeach()
file(INSTALL DESTINATION "${STAGE_ROOT}" TYPE FILE
     FILES "${PORTABLE_SOURCE_DIR}/README.md" "${PORTABLE_SOURCE_DIR}/VERSION")
file(WRITE "${STAGE_ROOT}/INSTALL.txt" [=[Harr Codex Scheduler portable C++ bundle

Runtime requirements on Ubuntu/Debian:
  sudo apt install at git libqt6core6t64 libqt6gui6t64 libqt6widgets6t64
  sudo systemctl enable --now atd

OpenAI Codex CLI must be installed and available as `codex` in PATH.

Run without installing:
  ./harr-codex-scheduler

CLI selectors:
  ./bin/sol
  ./bin/terra
  ./bin/luna
]=])

execute_process(
    COMMAND "${CMAKE_COMMAND}" -E tar "czf" "${OUTPUT}" --format=gnutar "${NAME}"
    WORKING_DIRECTORY "${STAGE_PARENT}"
    RESULT_VARIABLE TAR_RESULT
)
if(NOT TAR_RESULT EQUAL 0)
    message(FATAL_ERROR "Could not create portable archive: ${OUTPUT}")
endif()
message(STATUS "Built portable package: ${OUTPUT}")
