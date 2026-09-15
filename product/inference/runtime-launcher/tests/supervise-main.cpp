// Test adapter for the same supervisor used by runtime-launch.
#include "supervise.h"
#include <exception>
#include <iostream>
int main(int argc, char** argv) {
  if (argc < 2) return 2;
  try { return supervise(argv + 1); }
  catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
