cmake_minimum_required(VERSION 3.25)

project(gradiated_inference LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(DESMOND_ENABLE_SANITIZERS "Build Desmond with address and undefined behavior sanitizers" OFF)
option(GRADIATED_ENGINE_ENABLE_CUDA "Build the native Gemma 4 CUDA execution backend" OFF)

find_package(CURL REQUIRED)

include(CTest)
add_subdirectory(desmond)

add_library(gradiated_engine_model
  engine/src/json.cpp
  engine/src/gemma4_config.cpp
  engine/src/gemma4_model.cpp
  engine/src/safetensors.cpp
  engine/src/weight_plan.cpp
)
target_include_directories(gradiated_engine_model PUBLIC engine/include)
target_compile_options(gradiated_engine_model PRIVATE -Wall -Wextra -Wpedantic -Wconversion -Wshadow)

add_library(gradiated_engine_runtime
  engine/src/runtime/completion_request.cpp
  engine/src/runtime/completion_response.cpp
  engine/src/runtime/metrics.cpp
  engine/src/runtime/settings.cpp
  engine/src/runtime/slot_policy.cpp
  engine/src/runtime/speculation.cpp
)
target_include_directories(gradiated_engine_runtime PUBLIC engine/src)
target_link_libraries(gradiated_engine_runtime PRIVATE gradiated_engine_model)
target_compile_options(gradiated_engine_runtime PRIVATE -Wall -Wextra -Wpedantic -Wconversion -Wshadow)

add_executable(gradiated-engine-inspect engine/src/inspect_main.cpp)
target_link_libraries(gradiated-engine-inspect PRIVATE gradiated_engine_model)
target_compile_options(gradiated-engine-inspect PRIVATE -Wall -Wextra -Wpedantic -Wconversion -Wshadow)

if(GRADIATED_ENGINE_ENABLE_CUDA)
  enable_language(CUDA)
  find_package(CUDAToolkit REQUIRED)
  include(FetchContent)
  set(CUDNN_FRONTEND_BUILD_SAMPLES OFF CACHE BOOL "" FORCE)
  set(CUDNN_FRONTEND_BUILD_TESTS OFF CACHE BOOL "" FORCE)
  set(CUDNN_FRONTEND_BUILD_PYTHON_BINDINGS OFF CACHE BOOL "" FORCE)
  FetchContent_Declare(
    cudnn_frontend
    GIT_REPOSITORY https://github.com/NVIDIA/cudnn-frontend.git
    GIT_TAG b372d39879d44c91a8d5b342022e74802b6a8da2
    GIT_SHALLOW FALSE
  )
  FetchContent_MakeAvailable(cudnn_frontend)
  FetchContent_Declare(
    cutlass
    GIT_REPOSITORY https://github.com/NVIDIA/cutlass.git
    GIT_TAG 6c65a175668952f09bcbf66cb97a8de1b734b4a0
    GIT_SHALLOW TRUE
    SOURCE_SUBDIR _gradiated_header_only
  )
  FetchContent_MakeAvailable(cutlass)
  find_library(CUDNN_LIBRARY NAMES cudnn REQUIRED)
  add_library(gradiated_engine_cuda
    engine/cuda/attention.cu
    engine/cuda/assistant_runner.cu
    engine/cuda/batch_model_runner.cu
    engine/cuda/gemm_attention.cu
    engine/cuda/hopper_attention.cu
    engine/cuda/prefill_gemm_attention.cu
    engine/cuda/ops.cu
    engine/cuda/prefill_attention.cu
    engine/cuda/device_weights.cu
    engine/cuda/int4_bf16_linear.cu
    engine/cuda/int4_linear.cu
    engine/cuda/linear.cu
    engine/cuda/layer_runner.cu
    engine/cuda/model_runner.cu
    engine/cuda/qkv.cu
  )
  target_include_directories(gradiated_engine_cuda PUBLIC engine/include PRIVATE
    ${cutlass_SOURCE_DIR}/include
    ${cutlass_SOURCE_DIR}/tools/util/include)
  target_link_libraries(gradiated_engine_cuda PUBLIC gradiated_engine_model CUDA::cudart CUDA::cublas
    CUDA::cublasLt cudnn_frontend ${CUDNN_LIBRARY})
  set_target_properties(gradiated_engine_cuda PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
    CUDA_ARCHITECTURES 90a
  )
  if(BUILD_TESTING)
    add_executable(gradiated_engine_cuda_tests engine/tests/cuda_ops_tests.cu)
    target_link_libraries(gradiated_engine_cuda_tests PRIVATE gradiated_engine_cuda CUDA::cudart)
    set_target_properties(gradiated_engine_cuda_tests PROPERTIES
      CUDA_STANDARD 20
      CUDA_STANDARD_REQUIRED ON
      CUDA_ARCHITECTURES 90
    )
    add_test(NAME gradiated_engine_cuda_tests COMMAND gradiated_engine_cuda_tests)
  endif()
  add_executable(gradiated-engine-load engine/src/load_main.cpp)
  target_link_libraries(gradiated-engine-load PRIVATE gradiated_engine_cuda)
  add_executable(gradiated-engine-linear-benchmark engine/src/linear_benchmark.cu)
  target_link_libraries(gradiated-engine-linear-benchmark PRIVATE gradiated_engine_cuda)
  set_target_properties(gradiated-engine-linear-benchmark PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
    CUDA_ARCHITECTURES 90
  )
  add_executable(gradiated-engine-fp8-linear-benchmark engine/src/fp8_linear_benchmark.cu)
  target_link_libraries(gradiated-engine-fp8-linear-benchmark PRIVATE gradiated_engine_cuda)
  set_target_properties(gradiated-engine-fp8-linear-benchmark PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
    CUDA_ARCHITECTURES 90
  )
  add_executable(gradiated-engine-fp8-model-parity engine/src/fp8_model_parity.cu)
  target_link_libraries(gradiated-engine-fp8-model-parity PRIVATE gradiated_engine_cuda)
  set_target_properties(gradiated-engine-fp8-model-parity PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
    CUDA_ARCHITECTURES 90
  )
  add_executable(gradiated-engine-fp8-quality-eval engine/src/fp8_quality_eval.cu)
  target_link_libraries(gradiated-engine-fp8-quality-eval PRIVATE gradiated_engine_cuda)
  set_target_properties(gradiated-engine-fp8-quality-eval PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
    CUDA_ARCHITECTURES 90
  )
  add_executable(gradiated-engine-attention-benchmark engine/src/attention_benchmark.cu)
  target_link_libraries(gradiated-engine-attention-benchmark PRIVATE gradiated_engine_cuda)
  set_target_properties(gradiated-engine-attention-benchmark PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
    CUDA_ARCHITECTURES 90
  )
  add_executable(gradiated-engine-fp8-attention-benchmark engine/src/fp8_attention_benchmark.cu)
  target_link_libraries(gradiated-engine-fp8-attention-benchmark PRIVATE CUDA::cublas CUDA::cudart)
  set_target_properties(gradiated-engine-fp8-attention-benchmark PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
    CUDA_ARCHITECTURES 90
  )
  add_executable(gradiated-engine-prefill-attention-benchmark engine/src/prefill_attention_benchmark.cu)
  target_link_libraries(gradiated-engine-prefill-attention-benchmark PRIVATE gradiated_engine_cuda)
  set_target_properties(gradiated-engine-prefill-attention-benchmark PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
    CUDA_ARCHITECTURES 90
  )
  add_executable(gradiated-engine-layer-parity engine/src/layer_parity.cu)
  target_link_libraries(gradiated-engine-layer-parity PRIVATE gradiated_engine_cuda)
  set_target_properties(gradiated-engine-layer-parity PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
    CUDA_ARCHITECTURES 90
  )
  add_executable(gradiated-engine-model-parity engine/src/model_parity.cu)
  target_link_libraries(gradiated-engine-model-parity PRIVATE gradiated_engine_cuda)
  set_target_properties(gradiated-engine-model-parity PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
    CUDA_ARCHITECTURES 90
  )
  add_executable(gradiated-engine-prefill-model-parity engine/src/prefill_model_parity.cu)
  target_link_libraries(gradiated-engine-prefill-model-parity PRIVATE gradiated_engine_cuda)
  set_target_properties(gradiated-engine-prefill-model-parity PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
    CUDA_ARCHITECTURES 90
  )
  add_executable(gradiated-engine-prefill-benchmark engine/src/prefill_benchmark.cu)
  target_link_libraries(gradiated-engine-prefill-benchmark PRIVATE gradiated_engine_cuda)
  set_target_properties(gradiated-engine-prefill-benchmark PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
    CUDA_ARCHITECTURES 90
  )
  add_executable(gradiated-engine-runtime engine/src/native_runtime_main.cpp)
  target_link_libraries(gradiated-engine-runtime PRIVATE gradiated_engine_cuda gradiated_engine_runtime
    desmond_core)
  target_compile_options(gradiated-engine-runtime PRIVATE -Wall -Wextra -Wpedantic -Wconversion -Wshadow)
  install(TARGETS gradiated-engine-runtime RUNTIME DESTINATION bin)
  add_executable(gradiated-engine-batch-benchmark engine/src/batch_benchmark.cu)
  target_link_libraries(gradiated-engine-batch-benchmark PRIVATE gradiated_engine_cuda)
  set_target_properties(gradiated-engine-batch-benchmark PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
    CUDA_ARCHITECTURES 90
  )
  add_executable(gradiated-engine-ragged-batch-parity engine/src/ragged_batch_parity.cu)
  target_link_libraries(gradiated-engine-ragged-batch-parity PRIVATE gradiated_engine_cuda)
  set_target_properties(gradiated-engine-ragged-batch-parity PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
    CUDA_ARCHITECTURES 90
  )
endif()

if(BUILD_TESTING)
  set(GRADIATED_ENGINE_WARNINGS -Wall -Wextra -Wpedantic -Wconversion -Wshadow)

  add_library(gradiated_engine_test_support STATIC engine/tests/support/test_support.cpp)
  target_include_directories(gradiated_engine_test_support PUBLIC engine/tests)
  target_compile_options(gradiated_engine_test_support PRIVATE ${GRADIATED_ENGINE_WARNINGS})

  add_library(gradiated_engine_model_fixtures STATIC engine/tests/support/model_fixtures.cpp)
  target_include_directories(gradiated_engine_model_fixtures PUBLIC engine/tests)
  target_compile_options(gradiated_engine_model_fixtures PRIVATE ${GRADIATED_ENGINE_WARNINGS})

  add_executable(gradiated_engine_model_tests
    engine/tests/json_tests.cpp
    engine/tests/safetensors_tests.cpp
    engine/tests/gemma4_config_tests.cpp
    engine/tests/weight_plan_tests.cpp
  )
  target_link_libraries(gradiated_engine_model_tests PRIVATE gradiated_engine_model
    gradiated_engine_model_fixtures gradiated_engine_test_support)
  target_compile_options(gradiated_engine_model_tests PRIVATE ${GRADIATED_ENGINE_WARNINGS})
  add_test(NAME gradiated_engine_model_tests COMMAND gradiated_engine_model_tests)

  add_executable(gradiated_engine_runtime_tests
    engine/tests/completion_request_tests.cpp
    engine/tests/completion_response_tests.cpp
    engine/tests/runtime_metrics_tests.cpp
    engine/tests/runtime_settings_tests.cpp
    engine/tests/slot_policy_tests.cpp
    engine/tests/speculation_tests.cpp
  )
  target_link_libraries(gradiated_engine_runtime_tests PRIVATE gradiated_engine_runtime
    gradiated_engine_test_support)
  target_compile_options(gradiated_engine_runtime_tests PRIVATE ${GRADIATED_ENGINE_WARNINGS})
  add_test(NAME gradiated_engine_runtime_tests COMMAND gradiated_engine_runtime_tests)

  add_executable(gradiated_engine_model_fixtures_writer engine/tests/support/write_model_fixtures_main.cpp)
  target_link_libraries(gradiated_engine_model_fixtures_writer PRIVATE gradiated_engine_model_fixtures)
  target_compile_options(gradiated_engine_model_fixtures_writer PRIVATE ${GRADIATED_ENGINE_WARNINGS})
  add_test(NAME gradiated_engine_inspect_cli COMMAND ${CMAKE_COMMAND}
    -DFIXTURES=$<TARGET_FILE:gradiated_engine_model_fixtures_writer>
    -DINSPECT=$<TARGET_FILE:gradiated-engine-inspect>
    -DWORK_DIRECTORY=${CMAKE_CURRENT_BINARY_DIR}/engine-inspect-cli
    -P ${CMAKE_CURRENT_SOURCE_DIR}/engine/tests/inspect_cli_test.cmake)

  if(NOT GRADIATED_ENGINE_ENABLE_CUDA)
    # The CUDA build links the runtime; host builds still compile it against the CUDA-free headers.
    add_library(gradiated_engine_runtime_host_compile OBJECT engine/src/native_runtime_main.cpp)
    target_link_libraries(gradiated_engine_runtime_host_compile PRIVATE gradiated_engine_model
      gradiated_engine_runtime desmond_core)
    target_compile_options(gradiated_engine_runtime_host_compile PRIVATE ${GRADIATED_ENGINE_WARNINGS})
  endif()
endif()

install(TARGETS gradiated-engine-inspect RUNTIME DESTINATION bin)
