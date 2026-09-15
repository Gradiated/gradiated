cmake_minimum_required(VERSION 3.20)
project(runtime_launcher LANGUAGES CXX)
add_executable(runtime-launch main.cpp supervise.cpp)
target_compile_features(runtime-launch PRIVATE cxx_std_20)
target_compile_options(runtime-launch PRIVATE -Wall -Wextra -Werror)
install(TARGETS runtime-launch RUNTIME DESTINATION bin)

include(CTest)
if(BUILD_TESTING)
  add_executable(process-tree-fixture tests/process-tree.cpp)
  target_compile_features(process-tree-fixture PRIVATE cxx_std_20)
  target_compile_options(process-tree-fixture PRIVATE -Wall -Wextra -Werror)

  foreach(case arguments wrong-base missing-base non-executable
               symlink-entrypoint missing-directory invalid-arguments)
    add_test(NAME launcher.${case}
      COMMAND bash ${CMAKE_CURRENT_SOURCE_DIR}/tests/launcher.sh
              ${case} $<TARGET_FILE:runtime-launch>)
    set_tests_properties(launcher.${case} PROPERTIES TIMEOUT 10)
  endforeach()

  foreach(mode stop exit crash stubborn)
    add_test(NAME cleanup.${mode}
      COMMAND bash ${CMAKE_CURRENT_SOURCE_DIR}/tests/process-cleanup.sh
              ${mode} $<TARGET_FILE:runtime-launch> $<TARGET_FILE:process-tree-fixture>)
    set_tests_properties(cleanup.${mode} PROPERTIES TIMEOUT 40)
  endforeach()

  add_test(NAME nomad.artifact
    COMMAND bash ${CMAKE_CURRENT_SOURCE_DIR}/tests/nomad-artifact.sh
            $<TARGET_FILE:runtime-launch>)
  set_tests_properties(nomad.artifact PROPERTIES TIMEOUT 60)
endif()
