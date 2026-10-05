cmake_minimum_required(VERSION 3.20)
project(runtime_launcher LANGUAGES CXX)

if(NOT CMAKE_SYSTEM_NAME STREQUAL "Linux")
  message(FATAL_ERROR "runtime-launch requires Linux (PR_SET_CHILD_SUBREAPER and /proc child lists)")
endif()

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
add_compile_options(-Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror)

add_library(runtime_supervisor STATIC supervise.cpp)
target_include_directories(runtime_supervisor PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})

add_executable(runtime-launch main.cpp)
target_link_libraries(runtime-launch PRIVATE runtime_supervisor)
install(TARGETS runtime-launch RUNTIME DESTINATION bin)

include(CTest)
if(BUILD_TESTING)
  add_executable(process-tree-fixture tests/process-tree.cpp)
  add_executable(supervise-adapter tests/supervise-main.cpp)
  target_link_libraries(supervise-adapter PRIVATE runtime_supervisor)

  foreach(case arguments canonical-root wrong-base missing-base oversized-base
               blank-base non-executable symlink-entrypoint bad-interpreter
               missing-directory invalid-arguments)
    add_test(NAME launcher.${case}
      COMMAND bash ${CMAKE_CURRENT_SOURCE_DIR}/tests/launcher.sh
              ${case} $<TARGET_FILE:runtime-launch>)
    set_tests_properties(launcher.${case} PROPERTIES TIMEOUT 10)
  endforeach()

  foreach(mode stop interrupt hangup exit crash ignored-stop ignored-exit blocked-stop launcher-killed launcher-killed-during-stop launcher-group-killed)
    add_test(NAME cleanup.${mode}
      COMMAND bash ${CMAKE_CURRENT_SOURCE_DIR}/tests/process-cleanup.sh
              ${mode} $<TARGET_FILE:runtime-launch> $<TARGET_FILE:process-tree-fixture>)
    set_tests_properties(cleanup.${mode} PROPERTIES TIMEOUT 15)
  endforeach()

  add_test(NAME cleanup.stubborn
    COMMAND bash ${CMAKE_CURRENT_SOURCE_DIR}/tests/process-cleanup.sh
            stubborn $<TARGET_FILE:supervise-adapter> $<TARGET_FILE:process-tree-fixture>)
  set_tests_properties(cleanup.stubborn PROPERTIES TIMEOUT 15)

  add_test(NAME nomad.artifact
    COMMAND bash ${CMAKE_CURRENT_SOURCE_DIR}/tests/nomad-artifact.sh
            $<TARGET_FILE:runtime-launch> $<TARGET_FILE:process-tree-fixture>)
  set_tests_properties(nomad.artifact PROPERTIES TIMEOUT 60)
endif()
