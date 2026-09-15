cmake_minimum_required(VERSION 3.22)
project(harr_codex_scheduler VERSION 0.2.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(Qt6 6.4 REQUIRED COMPONENTS Core Gui Widgets)

add_executable(harr-codex-scheduler
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

install(TARGETS harr-codex-scheduler RUNTIME DESTINATION bin)
