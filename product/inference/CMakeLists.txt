cmake_minimum_required(VERSION 3.25)

project(gradiated_inference LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(DESMOND_ENABLE_SANITIZERS "Build Desmond with address and undefined behavior sanitizers" OFF)
option(GRADIATED_ENGINE_ENABLE_CUDA "Build the native Gemma 4 CUDA execution backend" OFF)

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

add_library(gradiated_engine_model
  engine/src/json.cpp
  engine/src/gemma4_config.cpp
  engine/src/safetensors.cpp
  engine/src/weight_plan.cpp
)
target_include_directories(gradiated_engine_model PUBLIC engine/include)
target_compile_options(gradiated_engine_model PRIVATE -Wall -Wextra -Wpedantic -Wconversion -Wshadow)

add_executable(gradiated-engine-inspect engine/src/inspect_main.cpp)
target_link_libraries(gradiated-engine-inspect PRIVATE gradiated_engine_model)
target_compile_options(gradiated-engine-inspect PRIVATE -Wall -Wextra -Wpedantic -Wconversion -Wshadow)

if(GRADIATED_ENGINE_ENABLE_CUDA)
  enable_language(CUDA)
  find_package(CUDAToolkit REQUIRED)
  add_library(gradiated_engine_cuda
    engine/cuda/attention.cu
    engine/cuda/batch_model_runner.cu
    engine/cuda/gemm_attention.cu
    engine/cuda/ops.cu
    engine/cuda/device_weights.cu
    engine/cuda/linear.cu
    engine/cuda/layer_runner.cu
    engine/cuda/model_runner.cu
    engine/cuda/qkv.cu
  )
  target_include_directories(gradiated_engine_cuda PUBLIC engine/include)
  target_link_libraries(gradiated_engine_cuda PUBLIC gradiated_engine_model CUDA::cudart CUDA::cublas CUDA::cublasLt)
  set_target_properties(gradiated_engine_cuda PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
    CUDA_ARCHITECTURES 90
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
  add_executable(gradiated-engine-attention-benchmark engine/src/attention_benchmark.cu)
  target_link_libraries(gradiated-engine-attention-benchmark PRIVATE gradiated_engine_cuda)
  set_target_properties(gradiated-engine-attention-benchmark PROPERTIES
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
  add_executable(gradiated-engine-batch-benchmark engine/src/batch_benchmark.cu)
  target_link_libraries(gradiated-engine-batch-benchmark PRIVATE gradiated_engine_cuda)
  set_target_properties(gradiated-engine-batch-benchmark PROPERTIES
    CUDA_STANDARD 20
    CUDA_STANDARD_REQUIRED ON
    CUDA_ARCHITECTURES 90
  )
endif()

if(BUILD_TESTING)
  add_executable(gradiated_engine_model_tests engine/tests/model_tests.cpp)
  target_link_libraries(gradiated_engine_model_tests PRIVATE gradiated_engine_model)
  target_compile_options(gradiated_engine_model_tests PRIVATE -Wall -Wextra -Wpedantic -Wconversion -Wshadow)
  add_test(NAME gradiated_engine_model_tests COMMAND gradiated_engine_model_tests)
endif()

install(TARGETS gradiated-engine-inspect RUNTIME DESTINATION bin)
