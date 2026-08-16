#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstring>

#ifdef _OPENMP
#include <omp.h>
#endif

namespace {

constexpr std::size_t kRows = 32;
constexpr std::size_t kColumns = 128;
constexpr std::size_t kTileBytes = kRows * kColumns;
constexpr std::size_t kTileAlignment = 16;

std::size_t align_up(std::size_t value) {
  return (value + kTileAlignment - 1) & ~(kTileAlignment - 1);
}

std::size_t encoded_row_bytes(const std::uint8_t* row,
                              const std::uint8_t* lengths) {
  std::size_t bits = 0;
  for (std::size_t column = 0; column < kColumns; ++column) {
    bits += lengths[row[column]];
  }
  return (bits + 7) / 8;
}

}  // namespace

extern "C" int huffman_plan(const std::uint8_t* input,
                            std::size_t tile_count,
                            const std::uint8_t* lengths,
                            std::uint32_t* tile_offsets,
                            std::uint64_t* totals) {
  if (input == nullptr || lengths == nullptr || tile_offsets == nullptr ||
      totals == nullptr) {
    return 1;
  }
  auto* tile_sizes = new std::uint32_t[tile_count];
  std::uint64_t payload_bits = 0;
  std::uint64_t row_bytes = 0;
  std::uint64_t tile_padding = 0;
  int invalid = 0;

#pragma omp parallel for reduction(+ : payload_bits, row_bytes, tile_padding, invalid) schedule(static)
  for (std::size_t tile = 0; tile < tile_count; ++tile) {
    const std::uint8_t* source = input + tile * kTileBytes;
    std::size_t bytes = kRows;
    for (std::size_t row = 0; row < kRows; ++row) {
      std::size_t bits = 0;
      const std::uint8_t* row_source = source + row * kColumns;
      for (std::size_t column = 0; column < kColumns; ++column) {
        const std::uint8_t length = lengths[row_source[column]];
        invalid += length == 0 || length > 12;
        bits += length;
      }
      const std::size_t encoded_bytes = (bits + 7) / 8;
      invalid += encoded_bytes > 255;
      payload_bits += bits;
      row_bytes += encoded_bytes;
      bytes += encoded_bytes;
    }
    const std::size_t aligned = align_up(bytes);
    tile_padding += aligned - bytes;
    tile_sizes[tile] = static_cast<std::uint32_t>(aligned);
  }

  std::uint64_t offset = 0;
  tile_offsets[0] = 0;
  for (std::size_t tile = 0; tile < tile_count; ++tile) {
    offset += tile_sizes[tile];
    if (offset > UINT32_MAX) {
      delete[] tile_sizes;
      return 2;
    }
    tile_offsets[tile + 1] = static_cast<std::uint32_t>(offset);
  }
  delete[] tile_sizes;
  totals[0] = payload_bits;
  totals[1] = row_bytes;
  totals[2] = tile_padding;
  totals[3] = offset;
  totals[4] = invalid;
  return invalid == 0 ? 0 : 3;
}

extern "C" int huffman_encode_decode(
    const std::uint8_t* input,
    std::size_t tile_count,
    const std::uint16_t* reversed_codes,
    const std::uint8_t* lengths,
    const std::uint16_t* decode_table,
    const std::uint32_t* tile_offsets,
    std::uint8_t* encoded,
    std::size_t encoded_capacity,
    std::uint64_t* mismatch_count) {
  if (input == nullptr || reversed_codes == nullptr || lengths == nullptr ||
      decode_table == nullptr || tile_offsets == nullptr ||
      encoded == nullptr || mismatch_count == nullptr) {
    return 1;
  }
  if (tile_offsets[tile_count] > encoded_capacity) {
    return 2;
  }
  std::uint64_t mismatches = 0;
  int invalid = 0;

#pragma omp parallel for reduction(+ : mismatches, invalid) schedule(static)
  for (std::size_t tile = 0; tile < tile_count; ++tile) {
    const std::uint8_t* source = input + tile * kTileBytes;
    std::uint8_t* tile_output = encoded + tile_offsets[tile];
    const std::size_t tile_size =
        tile_offsets[tile + 1] - tile_offsets[tile];
    std::memset(tile_output, 0, tile_size);
    std::size_t row_offsets[kRows + 1];
    row_offsets[0] = kRows;
    for (std::size_t row = 0; row < kRows; ++row) {
      const std::size_t bytes =
          encoded_row_bytes(source + row * kColumns, lengths);
      invalid += bytes > 255;
      tile_output[row] = static_cast<std::uint8_t>(bytes);
      row_offsets[row + 1] = row_offsets[row] + bytes;
    }
    invalid += row_offsets[kRows] > tile_size;

    for (std::size_t row = 0; row < kRows; ++row) {
      const std::uint8_t* row_source = source + row * kColumns;
      std::uint8_t* destination = tile_output + row_offsets[row];
      const std::uint8_t* destination_end =
          tile_output + row_offsets[row + 1];
      std::uint64_t accumulator = 0;
      unsigned accumulator_bits = 0;
      for (std::size_t column = 0; column < kColumns; ++column) {
        const std::uint8_t symbol = row_source[column];
        accumulator |=
            static_cast<std::uint64_t>(reversed_codes[symbol])
            << accumulator_bits;
        accumulator_bits += lengths[symbol];
        while (accumulator_bits >= 8) {
          *destination++ = static_cast<std::uint8_t>(accumulator);
          accumulator >>= 8;
          accumulator_bits -= 8;
        }
      }
      if (accumulator_bits != 0) {
        *destination++ = static_cast<std::uint8_t>(accumulator);
      }
      invalid += destination != destination_end;

      const std::uint8_t* cursor = tile_output + row_offsets[row];
      const std::uint8_t* end = tile_output + row_offsets[row + 1];
      accumulator = 0;
      accumulator_bits = 0;
      for (std::size_t column = 0; column < kColumns; ++column) {
        while (accumulator_bits < 12 && cursor != end) {
          accumulator |= static_cast<std::uint64_t>(*cursor++)
                         << accumulator_bits;
          accumulator_bits += 8;
        }
        const std::uint16_t entry = decode_table[accumulator & 4095u];
        const std::uint8_t symbol = static_cast<std::uint8_t>(entry);
        const unsigned length = entry >> 8;
        if (length == 0 || length > accumulator_bits) {
          ++invalid;
          break;
        }
        mismatches += symbol != row_source[column];
        accumulator >>= length;
        accumulator_bits -= length;
      }
    }
  }
  *mismatch_count = mismatches;
  return invalid == 0 ? 0 : 3;
}
