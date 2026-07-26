#include <cmath>
#include <cstddef>
#include <cstdint>

extern "C" int fp8_block_stats(const std::uint8_t* data,
                                std::size_t block_count,
                                const std::uint8_t* code_index,
                                float* entropy_bits,
                                std::uint16_t* escape_counts) {
  if (data == nullptr || code_index == nullptr || entropy_bits == nullptr ||
      escape_counts == nullptr) {
    return 1;
  }

#pragma omp parallel for schedule(static)
  for (std::size_t block = 0; block < block_count; ++block) {
    std::uint16_t histogram[256] = {};
    std::uint16_t escapes = 0;
    const std::uint8_t* input = data + block * 4096;
    for (std::size_t i = 0; i < 4096; ++i) {
      const std::uint8_t value = input[i];
      ++histogram[value];
      escapes += static_cast<std::uint16_t>(code_index[value] == 31);
    }
    double entropy = 0.0;
    for (std::uint16_t count : histogram) {
      if (count != 0) {
        const double probability = static_cast<double>(count) / 4096.0;
        entropy -= probability * std::log2(probability);
      }
    }
    entropy_bits[block] = static_cast<float>(entropy);
    escape_counts[block] = escapes;
  }
  return 0;
}
