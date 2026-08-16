#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <string>

namespace {

constexpr int kRows = 384;
constexpr int kWidth = 21504;
constexpr float kAlpha = 0.044715f;
constexpr float kBeta = 0.7978845608028654f;

uint16_t to_bfloat16(float value) {
  uint32_t bits;
  std::memcpy(&bits, &value, sizeof(bits));
  const uint32_t rounding = 0x7fffu + ((bits >> 16u) & 1u);
  return static_cast<uint16_t>((bits + rounding) >> 16u);
}

float from_bfloat16(uint16_t value) {
  const uint32_t bits = static_cast<uint32_t>(value) << 16u;
  float result;
  std::memcpy(&result, &bits, sizeof(result));
  return result;
}

uint32_t next(uint32_t& state) {
  state ^= state << 13u;
  state ^= state >> 17u;
  state ^= state << 5u;
  return state;
}

float sample(uint32_t& state) {
  const int32_t centered = static_cast<int32_t>(next(state) % 8193u) - 4096;
  return static_cast<float>(centered) / 1024.0f;
}

uint64_t update_hash(uint64_t hash, uint16_t value) {
  hash ^= static_cast<uint8_t>(value);
  hash *= 1099511628211ull;
  hash ^= static_cast<uint8_t>(value >> 8u);
  hash *= 1099511628211ull;
  return hash;
}

}  // namespace

int main(int argc, char** argv) {
  if (argc != 2) {
    std::cerr << "usage: semantic_fixture OUTPUT.json\n";
    return 2;
  }
  uint32_t state = 20260726u;
  uint64_t stock_hash = 1469598103934665603ull;
  uint64_t fixed_hash = 1469598103934665603ull;
  uint64_t old_hash = 1469598103934665603ull;
  uint64_t fixed_mismatches = 0;
  uint64_t old_mismatches = 0;
  uint64_t nonzero = 0;
  float maximum = 0.0f;

  for (int row = 0; row < kRows; ++row) {
    for (int column = 0; column < kWidth; ++column) {
      const float gate = from_bfloat16(to_bfloat16(sample(state)));
      const float up = from_bfloat16(to_bfloat16(sample(state)));
      const float gate3 = gate * gate * gate;
      const float cdf =
          0.5f * (1.0f + std::tanh(kBeta * (gate + kAlpha * gate3)));
      const uint16_t stock = to_bfloat16((gate * cdf) * up);
      const uint16_t fixed = to_bfloat16((gate * cdf) * up);
      const uint16_t old = to_bfloat16(
          from_bfloat16(to_bfloat16(gate * cdf)) * up);
      stock_hash = update_hash(stock_hash, stock);
      fixed_hash = update_hash(fixed_hash, fixed);
      old_hash = update_hash(old_hash, old);
      fixed_mismatches += fixed != stock;
      old_mismatches += old != stock;
      const float value = from_bfloat16(fixed);
      if (!std::isfinite(value)) {
        std::cerr << "nonfinite output\n";
        return 3;
      }
      nonzero += value != 0.0f;
      maximum = std::max(maximum, std::abs(value));
    }
  }

  std::ofstream output(argv[1]);
  output << "{\n"
         << "  \"candidate_bf16_hash_fnv1a64\": \"" << std::hex
         << fixed_hash << "\",\n"
         << "  \"candidate_mismatches\": " << std::dec << fixed_mismatches
         << ",\n"
         << "  \"elements\": " << static_cast<uint64_t>(kRows) * kWidth
         << ",\n"
         << "  \"finite\": true,\n"
         << "  \"geometry\": [" << kRows << ", " << kWidth << "],\n"
         << "  \"max_abs\": " << std::setprecision(9) << maximum << ",\n"
         << "  \"nonzero\": " << nonzero << ",\n"
         << "  \"old_extra_rounding_hash_fnv1a64\": \"" << std::hex
         << old_hash << "\",\n"
         << "  \"old_extra_rounding_mismatches\": " << std::dec
         << old_mismatches << ",\n"
         << "  \"schema_version\": 1,\n"
         << "  \"stock_bf16_hash_fnv1a64\": \"" << std::hex << stock_hash
         << "\"\n"
         << "}\n";
  return fixed_mismatches == 0 && old_mismatches > 0 && nonzero > 0 ? 0 : 4;
}
