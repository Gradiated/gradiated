#include <archive.h>
#include <archive_entry.h>
#include <curl/curl.h>
#include <openssl/evp.h>
#include <fcntl.h>
#include <sys/file.h>
#include <unistd.h>

#include <array>
#include <cerrno>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;
constexpr size_t max_download = 20ULL * 1024 * 1024 * 1024;
constexpr size_t max_expanded = 40ULL * 1024 * 1024 * 1024;
void require(bool ok, const char* message) {
  if (!ok) throw std::runtime_error(message);
}
std::string read_id(const fs::path& path) {
  std::ifstream file(path);
  std::string value;
  std::getline(file, value);
  require(file.good() || file.eof(), "Cannot read base ID");
  require(!value.empty() && value.size() <= 128, "Invalid base ID");
  return value;
}
struct Download {
  FILE* file;
  size_t bytes = 0;
};
size_t write_download(char* data, size_t size, size_t count, void* context) {
  auto& download = *static_cast<Download*>(context);
  if (size != 0 && count > (max_download - download.bytes) / size) return 0;
  size_t bytes = size * count;
  size_t written = fwrite(data, 1, bytes, download.file);
  download.bytes += written;
  return written;
}
void fetch(const std::string& url, const fs::path& path) {
  require(url.starts_with("https://"), "Bundle URL must use HTTPS");
  auto close_file = [](FILE* file) { fclose(file); };
  std::unique_ptr<FILE, decltype(close_file)> file(fopen(path.c_str(), "wb"), close_file);
  require(bool(file), "Cannot create bundle download");
  std::unique_ptr<CURL, decltype(&curl_easy_cleanup)> curl(curl_easy_init(), curl_easy_cleanup);
  require(bool(curl), "Cannot initialize download");
  Download download{file.get()};
  curl_easy_setopt(curl.get(), CURLOPT_URL, url.c_str());
  curl_easy_setopt(curl.get(), CURLOPT_PROTOCOLS_STR, "https");
  curl_easy_setopt(curl.get(), CURLOPT_REDIR_PROTOCOLS_STR, "https");
  curl_easy_setopt(curl.get(), CURLOPT_FOLLOWLOCATION, 1L);
  curl_easy_setopt(curl.get(), CURLOPT_MAXREDIRS, 3L);
  curl_easy_setopt(curl.get(), CURLOPT_FAILONERROR, 1L);
  curl_easy_setopt(curl.get(), CURLOPT_CONNECTTIMEOUT, 15L);
  curl_easy_setopt(curl.get(), CURLOPT_TIMEOUT, 600L);
  curl_easy_setopt(curl.get(), CURLOPT_WRITEFUNCTION, write_download);
  curl_easy_setopt(curl.get(), CURLOPT_WRITEDATA, &download);
  require(curl_easy_perform(curl.get()) == CURLE_OK, "Bundle download failed");
  require(fflush(file.get()) == 0, "Cannot flush bundle download");
}
std::string digest(const fs::path& path) {
  std::ifstream file(path, std::ios::binary);
  require(bool(file), "Cannot read bundle archive");
  std::unique_ptr<EVP_MD_CTX, decltype(&EVP_MD_CTX_free)> ctx(EVP_MD_CTX_new(), EVP_MD_CTX_free);
  require(ctx && EVP_DigestInit_ex(ctx.get(), EVP_sha256(), nullptr) == 1, "Cannot initialize SHA-256");
  std::array<char, 65536> buffer{};
  while (file.read(buffer.data(), buffer.size()) || file.gcount()) {
    require(EVP_DigestUpdate(ctx.get(), buffer.data(), file.gcount()) == 1, "Cannot hash bundle");
  }
  require(file.eof(), "Bundle read failed");
  std::array<unsigned char, EVP_MAX_MD_SIZE> hash{};
  unsigned int length = 0;
  require(EVP_DigestFinal_ex(ctx.get(), hash.data(), &length) == 1, "Cannot finish SHA-256");
  std::string result;
  constexpr char hex[] = "0123456789abcdef";
  for (unsigned int i = 0; i < length; ++i) {
    result += hex[hash[i] >> 4];
    result += hex[hash[i] & 15];
  }
  return result;
}
void extract(const fs::path& archive_path, const fs::path& destination) {
  std::unique_ptr<archive, decltype(&archive_read_free)> reader(archive_read_new(), archive_read_free);
  archive_read_support_filter_gzip(reader.get());
  archive_read_support_format_tar(reader.get());
  require(archive_read_open_filename(reader.get(), archive_path.c_str(), 65536) == ARCHIVE_OK,
          "Cannot open bundle archive");
  const auto previous = fs::current_path();
  fs::current_path(destination);
  try {
    archive_entry* entry = nullptr;
    size_t total = 0;
    int result;
    while ((result = archive_read_next_header(reader.get(), &entry)) == ARCHIVE_OK) {
      auto size = archive_entry_size(entry);
      require(size >= 0 && static_cast<uint64_t>(size) <= max_expanded - total,
              "Expanded bundle exceeds limit");
      total += size;
      auto type = archive_entry_filetype(entry);
      require(type == AE_IFREG || type == AE_IFDIR || type == AE_IFLNK,
              "Unsupported archive entry type");
      // Do not preserve ownership, setuid bits, ACLs, or extended attributes.
      archive_entry_set_perm(entry, archive_entry_perm(entry) & 0777);
      int flags = ARCHIVE_EXTRACT_SECURE_SYMLINKS | ARCHIVE_EXTRACT_SECURE_NODOTDOT |
                  ARCHIVE_EXTRACT_SECURE_NOABSOLUTEPATHS;
      require(archive_read_extract(reader.get(), entry, flags) == ARCHIVE_OK,
              "Unsafe or invalid bundle archive");
    }
    require(result == ARCHIVE_EOF, "Truncated bundle archive");
  } catch (...) {
    fs::current_path(previous);
    throw;
  }
  fs::current_path(previous);
}
int main(int argc, char** argv) {
  fs::path staging;
  int lock = -1;
  try {
    require(argc >= 7, "Usage: runtime-launch --bundle URL|--archive PATH --sha256 DIGEST --cache PATH [-- ARGS...]");
    std::string source, hash;
    fs::path cache;
    bool local = false;
    int index = 1;
    for (; index < argc && std::string(argv[index]) != "--"; index += 2) {
      require(index + 1 < argc, "Missing option value");
      std::string option = argv[index];
      if (option == "--bundle" || option == "--archive") {
        require(source.empty(), "Specify one bundle source");
        source = argv[index + 1];
        local = option == "--archive";
      } else if (option == "--sha256") hash = argv[index + 1];
      else if (option == "--cache") cache = argv[index + 1];
      else throw std::runtime_error("Unknown option");
    }
    require(!source.empty() && !cache.empty(), "Bundle source and cache are required");
    require(hash.size() == 64 && hash.find_first_not_of("0123456789abcdef") == std::string::npos,
            "Invalid SHA-256 digest");
    const std::string base = read_id("/etc/gradiated/base-id");
    fs::create_directories(cache);
    cache = fs::canonical(cache);
    auto target = cache / hash;
    lock = open((cache / (hash + ".lock")).c_str(), O_CREAT | O_RDWR | O_CLOEXEC | O_NOFOLLOW, 0600);
    require(lock >= 0 && flock(lock, LOCK_EX) == 0, "Cannot lock bundle cache");
    if (!fs::exists(target)) {
      std::string pattern = (cache / (hash + ".partial.XXXXXX")).string();
      require(mkdtemp(pattern.data()) != nullptr, "Cannot create staging directory");
      staging = pattern;
      fs::path archive_path = staging / "bundle.tar.gz";
      if (local) fs::copy_file(source, archive_path);
      else fetch(source, archive_path);
      require(fs::file_size(archive_path) <= max_download, "Bundle archive exceeds limit");
      require(digest(archive_path) == hash, "Bundle checksum mismatch");
      fs::create_directory(staging / "runtime");
      extract(archive_path, staging / "runtime");
      require(read_id(staging / "runtime/base-id") == base, "Bundle base ID mismatch");
      const auto staged_entry = staging / "runtime/entrypoint";
      require(fs::is_regular_file(fs::symlink_status(staged_entry)) && access(staged_entry.c_str(), X_OK) == 0,
              "Bundle entrypoint must be an executable regular file");
      fs::rename(staging / "runtime", target);
      fs::remove_all(staging);
      staging.clear();
    }
    require(read_id(target / "base-id") == base, "Cached bundle base ID mismatch");
    const auto entry = target / "entrypoint";
    require(fs::is_regular_file(fs::symlink_status(entry)) && access(entry.c_str(), X_OK) == 0,
            "Bundle entrypoint must be an executable regular file");
    close(lock);
    lock = -1;
    require(setenv("GRADIATED_RUNTIME_ROOT", target.c_str(), 1) == 0, "Cannot set runtime root");
    std::vector<char*> args{const_cast<char*>(entry.c_str())};
    if (index < argc) for (++index; index < argc; ++index) args.push_back(argv[index]);
    args.push_back(nullptr);
    execv(entry.c_str(), args.data());
    throw std::runtime_error("Cannot execute bundle entrypoint");
  } catch (const std::exception& error) {
    if (lock >= 0) close(lock);
    if (!staging.empty()) { std::error_code ignored; fs::remove_all(staging, ignored); }
    std::cerr << "runtime-launch: " << error.what() << '\n';
    return 1;
  }
}
