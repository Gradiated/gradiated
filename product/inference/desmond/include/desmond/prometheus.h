#pragma once

#include <ostream>
#include <string>
#include <string_view>

namespace desmond::prometheus {

enum class MetricType { gauge, counter };

[[nodiscard]] inline std::string label_value(const std::string_view value) {
  std::string escaped;
  escaped.reserve(value.size());
  for (const char character : value) {
    switch (character) {
    case '\\':
      escaped += "\\\\";
      break;
    case '"':
      escaped += "\\\"";
      break;
    case '\n':
      escaped += "\\n";
      break;
    default:
      escaped += character;
    }
  }

  return escaped;
}

inline void write_type(std::ostream &output, const std::string_view name, const MetricType type) {
  output << "# TYPE " << name << ' ' << (type == MetricType::counter ? "counter" : "gauge") << '\n';
}

template <typename Value>
void write_metric(std::ostream &output, const std::string_view name, const MetricType type,
                  const Value &value) {
  write_type(output, name, type);
  output << name << ' ' << value << '\n';
}

} // namespace desmond::prometheus
