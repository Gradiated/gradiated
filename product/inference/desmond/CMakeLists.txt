find_package(CURL REQUIRED)

set(DESMOND_WARNINGS -Wall -Wextra -Wpedantic -Wconversion -Wshadow)

add_library(desmond_core
  src/child_process.cpp
  src/config.cpp
  src/control_api.cpp
  src/deployment_status.cpp
  src/gpu_metrics.cpp
  src/http.cpp
  src/http_client.cpp
  src/json.cpp
  src/profiling.cpp
  src/profiling_events.cpp
  src/runtime_health.cpp
  src/runtime_launch.cpp
  src/runtime_metrics.cpp
  src/status_reporter.cpp
  src/supervisor_metrics.cpp
  src/trace.cpp
)
target_include_directories(desmond_core PUBLIC include)
target_compile_options(desmond_core PRIVATE ${DESMOND_WARNINGS})
target_link_libraries(desmond_core PUBLIC dl pthread CURL::libcurl)

if(DESMOND_ENABLE_SANITIZERS)
  target_compile_options(desmond_core PUBLIC -fsanitize=address,undefined -fno-omit-frame-pointer)
  target_link_options(desmond_core PUBLIC -fsanitize=address,undefined)
endif()

add_executable(desmondd src/main.cpp)
target_link_libraries(desmondd PRIVATE desmond_core)
target_compile_options(desmondd PRIVATE ${DESMOND_WARNINGS})
install(TARGETS desmondd RUNTIME DESTINATION bin)

if(BUILD_TESTING)
  add_executable(desmond_tests
    tests/child_process_tests.cpp
    tests/config_tests.cpp
    tests/control_api_tests.cpp
    tests/deployment_status_tests.cpp
    tests/gpu_metrics_tests.cpp
    tests/http_client_tests.cpp
    tests/http_server_tests.cpp
    tests/json_tests.cpp
    tests/profiling_events_tests.cpp
    tests/profiling_uploader_tests.cpp
    tests/runtime_health_tests.cpp
    tests/runtime_launch_tests.cpp
    tests/runtime_metrics_tests.cpp
    tests/status_reporter_tests.cpp
    tests/supervisor_metrics_tests.cpp
    tests/trace_ring_tests.cpp
    tests/support/test_support.cpp
  )
  target_include_directories(desmond_tests PRIVATE tests/support)
  target_link_libraries(desmond_tests PRIVATE desmond_core)
  target_compile_options(desmond_tests PRIVATE ${DESMOND_WARNINGS})
  add_test(NAME desmond_tests COMMAND desmond_tests)

  find_package(Python3 COMPONENTS Interpreter REQUIRED)
  add_test(NAME desmond_observer COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/observer.py $<TARGET_FILE:desmondd>)
  set_tests_properties(desmond_observer PROPERTIES TIMEOUT 60)
endif()
