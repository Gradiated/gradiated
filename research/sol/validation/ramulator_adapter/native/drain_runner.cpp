#include <cstdint>
#include <fstream>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "ramulator/base/config.h"
#include "ramulator/base/config_node.h"
#include "ramulator/base/factory.h"
#include "ramulator/base/request.h"
#include "ramulator/frontend/i_frontend.h"
#include "ramulator/memory_system/i_memory_system.h"

namespace {

using Ramulator::ConfigNode;
using Ramulator::Request;

struct TraceEntry {
  int type;
  Ramulator::AddrVec_t address;
};

std::string escape_json(const std::string& value) {
  std::string escaped;
  for (const char character : value) {
    switch (character) {
      case '"':
        escaped += "\\\"";
        break;
      case '\\':
        escaped += "\\\\";
        break;
      case '\n':
        escaped += "\\n";
        break;
      case '\r':
        escaped += "\\r";
        break;
      case '\t':
        escaped += "\\t";
        break;
      default:
        escaped += character;
    }
  }
  return escaped;
}

void write_node(std::ostream& output, const ConfigNode& node) {
  if (node.is_null()) {
    output << "null";
    return;
  }
  if (node.is_scalar()) {
    output << '"' << escape_json(node.scalar()) << '"';
    return;
  }
  if (node.is_sequence()) {
    output << '[';
    bool first = true;
    for (const auto& child : node.seq()) {
      if (!first) {
        output << ',';
      }
      first = false;
      write_node(output, child);
    }
    output << ']';
    return;
  }
  output << '{';
  bool first = true;
  for (const auto& [key, child] : node.map()) {
    if (!first) {
      output << ',';
    }
    first = false;
    output << '"' << escape_json(key) << "\":";
    write_node(output, child);
  }
  output << '}';
}

std::vector<TraceEntry> read_trace(const std::string& path) {
  std::ifstream input(path);
  if (!input) {
    throw std::runtime_error("cannot open trace: " + path);
  }
  std::vector<TraceEntry> trace;
  std::string line;
  while (std::getline(input, line)) {
    if (line.empty()) {
      continue;
    }
    std::istringstream line_stream(line);
    char operation;
    std::string address_text;
    if (!(line_stream >> operation >> address_text)) {
      throw std::runtime_error("invalid trace line");
    }
    const int type = operation == 'R' ? Request::Type::Read : operation == 'W' ? Request::Type::Write : -1;
    if (type < 0) {
      throw std::runtime_error("invalid trace operation");
    }
    Ramulator::AddrVec_t address;
    std::istringstream address_stream(address_text);
    std::string level;
    while (std::getline(address_stream, level, ',')) {
      address.push_back(std::stoi(level));
    }
    if (address.size() != 7) {
      throw std::runtime_error("HBM3 trace address must have seven levels");
    }
    trace.push_back({type, std::move(address)});
  }
  if (trace.empty()) {
    throw std::runtime_error("trace is empty");
  }
  return trace;
}

int run(const std::string& config_path, const std::string& trace_path, const std::string& output_path) {
  const ConfigNode config = Ramulator::Config::parse_config_file(config_path);
  std::unique_ptr<Ramulator::IFrontEnd> frontend(Ramulator::Factory::create_frontend(config));
  std::unique_ptr<Ramulator::IMemorySystem> memory(Ramulator::Factory::create_memory_system(config));
  frontend->connect_memory_system(memory.get());
  memory->connect_frontend(frontend.get());
  if (frontend->get_clock_ratio() != 1 || memory->get_clock_ratio() != 1) {
    throw std::runtime_error("expected unit frontend and memory clock ratios");
  }
  if (memory->get_tx_bytes() != 32) {
    throw std::runtime_error("expected a 32-byte HBM3 transaction");
  }

  const auto trace = read_trace(trace_path);
  std::uint64_t accepted = 0;
  std::uint64_t completed = 0;
  std::uint64_t callback_latency_sum = 0;
  std::uint64_t tick_count = 0;
  constexpr std::uint64_t tick_limit = 1'000'000'000;

  while (completed < trace.size()) {
    if (accepted < trace.size()) {
      const auto& entry = trace[accepted];
      Request request(entry.address, entry.type);
      request.size_bytes = memory->get_tx_bytes();
      request.source_id = 0;
      request.callback = [&](Request& completed_request) {
        completed++;
        if (completed_request.depart >= completed_request.arrive) {
          callback_latency_sum += static_cast<std::uint64_t>(completed_request.depart - completed_request.arrive);
        }
      };
      if (memory->send(request)) {
        accepted++;
      }
    }
    memory->tick();
    tick_count++;
    if (tick_count >= tick_limit) {
      throw std::runtime_error("drain tick limit exceeded");
    }
  }

  frontend->finalize();
  memory->finalize();
  std::ofstream output(output_path);
  if (!output) {
    throw std::runtime_error("cannot open output: " + output_path);
  }
  output << "{\"frontend\":";
  write_node(output, frontend->collect_stats());
  output << ",\"memory_system\":";
  write_node(output, memory->collect_stats());
  output << ",\"driver\":{"
         << "\"accepted_request_count\":" << accepted << ',' << "\"completed_request_count\":" << completed << ','
         << "\"tick_count\":" << tick_count << ',' << "\"callback_latency_sum\":" << callback_latency_sum << "}}\n";
  return 0;
}

}

int main(int argc, char** argv) {
  if (argc != 4) {
    std::cerr << "usage: drain_runner CONFIG TRACE OUTPUT\n";
    return 2;
  }
  try {
    return run(argv[1], argv[2], argv[3]);
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
