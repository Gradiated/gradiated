#include "desmond/json.h"
#include "desmond/prometheus.h"

#include "test_support.h"

#include <cstdint>
#include <optional>
#include <string>

namespace {

DESMOND_TEST(json_string_escapes_quote_backslash_and_named_controls) {
  CHECK(desmond::json_string("a\"b\\c\n\t\r\b\f") == "\"a\\\"b\\\\c\\n\\t\\r\\b\\f\"");
}

DESMOND_TEST(json_string_escapes_every_other_control_byte_as_unicode) {
  for (int byte = 0; byte < 0x20; ++byte) {
    const std::string input(1, static_cast<char>(byte));
    const auto output = desmond::json_string(input);

    const bool named = byte == '\b' || byte == '\t' || byte == '\n' || byte == '\f' || byte == '\r';
    CHECK(named ? output.size() == 4 : output.size() == 8);
    CHECK(output.find(static_cast<char>(byte)) == std::string::npos);
  }

  CHECK(desmond::json_string(std::string(1, '\x01')) == "\"\\u0001\"");
  CHECK(desmond::json_string(std::string(1, '\x1f')) == "\"\\u001f\"");
}

DESMOND_TEST(json_string_passes_utf8_through) {
  CHECK(desmond::json_string("caf\xc3\xa9 \xe2\x9c\x93") == "\"caf\xc3\xa9 \xe2\x9c\x93\"");
}

DESMOND_TEST(json_object_writer_renders_mixed_fields_in_order) {
  const auto json = desmond::JsonObjectWriter()
                        .field("unsigned", std::uint64_t{18446744073709551615ULL})
                        .field("signed", std::int64_t{-7})
                        .field("flag", false)
                        .field("text", "a\"b")
                        .raw_field("nested", "{\"x\":null}")
                        .str();

  CHECK(json == "{\"unsigned\":18446744073709551615,\"signed\":-7,\"flag\":false,"
                "\"text\":\"a\\\"b\",\"nested\":{\"x\":null}}");
}

DESMOND_TEST(json_object_writer_skips_empty_optional_fields) {
  const auto json = desmond::JsonObjectWriter()
                        .field("present", std::optional<std::string>("x"))
                        .field("absent", std::optional<std::string>())
                        .field("count", std::optional<unsigned int>(3))
                        .str();

  CHECK(json == "{\"present\":\"x\",\"count\":3}");
}

DESMOND_TEST(json_object_writer_without_fields_is_an_empty_object) {
  CHECK(desmond::JsonObjectWriter().str() == "{}");
}

DESMOND_TEST(prometheus_label_value_escapes_backslash_quote_and_newline) {
  CHECK(desmond::prometheus::label_value("a\\b\"c\nd") == "a\\\\b\\\"c\\nd");
  CHECK(desmond::prometheus::label_value("plain") == "plain");
}

} // namespace
