cmake_minimum_required(VERSION 3.25)

project(gradiated_inference LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(DESMOND_ENABLE_SANITIZERS "Build Desmond with address and undefined behavior sanitizers" OFF)

add_library(desmond_core
  desmond/src/gpu_metrics.cpp
  desmond/src/http.cpp
  desmond/src/profiling.cpp
  desmond/src/supervisor.cpp
  desmond/src/trace.cpp
)
target_include_directories(desmond_core PUBLIC desmond/include)
target_compile_options(desmond_core PRIVATE -Wall -Wextra -Wpedantic -Wconversion -Wshadow)
target_link_libraries(desmond_core PUBLIC dl pthread)

if(DESMOND_ENABLE_SANITIZERS)
  target_compile_options(desmond_core PUBLIC -fsanitize=address,undefined -fno-omit-frame-pointer)
  target_link_options(desmond_core PUBLIC -fsanitize=address,undefined)
endif()

add_executable(desmondd desmond/src/main.cpp)
target_link_libraries(desmondd PRIVATE desmond_core)
target_compile_options(desmondd PRIVATE -Wall -Wextra -Wpedantic -Wconversion -Wshadow)

include(CTest)
if(BUILD_TESTING)
  add_executable(desmond_tests desmond/tests/desmond_tests.cpp)
  target_link_libraries(desmond_tests PRIVATE desmond_core)
  target_compile_options(desmond_tests PRIVATE -Wall -Wextra -Wpedantic -Wconversion -Wshadow)
  add_test(NAME desmond_tests COMMAND desmond_tests)
endif()

install(TARGETS desmondd RUNTIME DESTINATION bin)
