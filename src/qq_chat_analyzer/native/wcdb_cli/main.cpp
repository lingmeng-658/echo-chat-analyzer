// Read-only WCDB query helper for WeChat 4.x databases.
//
// This build links against the official Tencent WCDB v2.1.15 headers and the
// WCDB.dll import library, so no WCDB C++ object layout is hand-mirrored.
//
// Migration note:
// - The previous implementation resolved WCDB's private C++ ABI through
//   GetProcAddress and hand-mirrored layouts (UnsafeStringView, UnsafeData,
//   RecyclableHandle, std::shared_ptr) with guessed stack buffers, which can
//   crash with 0xC0000005 during real session reads.
// - Database construction, cipher configuration, the open check and handle
//   acquisition now use the public WCDB::Database / WCDB::Handle API. The
//   InnerDatabase object is created inside WCDB.dll (never on the caller
//   stack), so no private layout is assumed.
// - The public API has no raw-SQL entry in v2.1.15: StatementOperation::
//   prepare() only accepts winq Statement objects and no SQL-text parser is
//   exposed, while wcdb_cli must run arbitrary --sql text supplied by Python.
//   The shared InnerHandle is therefore reached through the public core API
//   (CommonCore::getOrCreateDatabase) solely to prepare the raw SQL text.
//
// stdout contract (unchanged):
//   {"ok":true,"columns":[...],"rows":[...],"row_count":N,"truncated":bool,"db":"..."}
//   {"ok":false,"stage":"...","error":"..."}
//
// The key is only kept in memory and is never printed or written to disk.

#ifndef NOMINMAX
#define NOMINMAX
#endif
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <string>
#include <vector>

#include "CoreConst.h"
#include "CommonCore.hpp"
#include "Database.hpp"
#include "Handle.hpp"
#include "InnerDatabase.hpp"
#include "InnerHandle.hpp"
#include "Path.hpp"
#include "RecyclableHandle.hpp"
#include "StringView.hpp"
#include "UnsafeData.hpp"

namespace {

const char* g_stage = "startup";

void SetStage(const char* stage) {
  g_stage = stage;
  std::fprintf(stderr, "[wcdb-debug] %s\n", stage);
  std::fflush(stderr);
}

void PrintHostInfo() {
  struct OsVersionInfo {
    DWORD size;
    DWORD major;
    DWORD minor;
    DWORD build;
    DWORD platform;
    WCHAR csd[128];
  };
  using RtlGetVersionFn = LONG(WINAPI*)(OsVersionInfo*);
  std::string windows = "unknown";
  HMODULE ntdll = GetModuleHandleW(L"ntdll.dll");
  if (ntdll != nullptr) {
    auto fn = reinterpret_cast<RtlGetVersionFn>(GetProcAddress(ntdll, "RtlGetVersion"));
    if (fn != nullptr) {
      OsVersionInfo info = {};
      info.size = sizeof(info);
      if (fn(&info) == 0) {
        char buffer[64];
        std::snprintf(buffer, sizeof(buffer), "%lu.%lu.%lu", info.major, info.minor, info.build);
        windows = buffer;
      }
    }
  }
  SYSTEM_INFO si = {};
  GetNativeSystemInfo(&si);
  const char* host_arch = "unknown";
  switch (si.wProcessorArchitecture) {
    case PROCESSOR_ARCHITECTURE_AMD64:
      host_arch = "x64";
      break;
    case PROCESSOR_ARCHITECTURE_INTEL:
      host_arch = "x86";
      break;
    case PROCESSOR_ARCHITECTURE_ARM64:
      host_arch = "arm64";
      break;
    default:
      break;
  }
  const char* process_arch = sizeof(void*) == 8 ? "x64" : "x86";
  std::fprintf(stderr,
               "[wcdb-debug] host windows=%s host_arch=%s process_arch=%s pointer_bits=%zu\n",
               windows.c_str(), host_arch, process_arch, sizeof(void*) * 8);
  std::fflush(stderr);
}

LONG WINAPI NativeExceptionFilter(EXCEPTION_POINTERS* info) {
  const DWORD code = info != nullptr && info->ExceptionRecord != nullptr
                         ? info->ExceptionRecord->ExceptionCode
                         : 0;
  const void* address =
      info != nullptr && info->ExceptionRecord != nullptr
          ? info->ExceptionRecord->ExceptionAddress
          : nullptr;
  std::fprintf(stderr, "[wcdb-debug] native exception code=0x%08lX address=0x%p stage=%s\n",
               code, address, g_stage);
  std::fflush(stderr);
  std::printf(
      "{\"ok\":false,\"stage\":\"%s\",\"error\":\"native exception\","
      "\"exception_code\":\"0x%08lX\",\"exception_address\":\"0x%p\",\"crashed\":true}\n",
      g_stage, code, address);
  std::fflush(stdout);
  return EXCEPTION_EXECUTE_HANDLER;
}

const char* kSchemaSql = "SELECT name, type, sql FROM sqlite_master ORDER BY type, name";

struct QueryOptions {
  std::string wcdb_path;
  std::string db_path;
  std::string key_hex;
  std::string sql;
  int limit = 0;
  int page_size = 4096;
  int cipher_version = 0;
  bool no_cipher = false;
  bool debug = false;
};

void DebugPrint(const QueryOptions& options, const std::string& message) {
  if (options.debug) {
    std::fprintf(stderr, "[wcdb_cli] %s\n", message.c_str());
    std::fflush(stderr);
  }
}

bool ParseHexKey(const std::string& hex, unsigned char out[32]) {
  if (hex.size() != 64) {
    return false;
  }
  auto nibble = [](char c) -> int {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
  };
  for (int i = 0; i < 32; ++i) {
    const int high = nibble(hex[static_cast<size_t>(i) * 2]);
    const int low = nibble(hex[static_cast<size_t>(i) * 2 + 1]);
    if (high < 0 || low < 0) {
      return false;
    }
    out[i] = static_cast<unsigned char>((high << 4) | low);
  }
  return true;
}

std::string JsonEscape(const std::string& input) {
  std::string out;
  out.reserve(input.size() + 8);
  for (const unsigned char c : input) {
    switch (c) {
      case '"':
        out += "\\\"";
        break;
      case '\\':
        out += "\\\\";
        break;
      case '\b':
        out += "\\b";
        break;
      case '\f':
        out += "\\f";
        break;
      case '\n':
        out += "\\n";
        break;
      case '\r':
        out += "\\r";
        break;
      case '\t':
        out += "\\t";
        break;
      default:
        if (c < 0x20) {
          char buffer[8];
          std::snprintf(buffer, sizeof(buffer), "\\u%04x", c);
          out += buffer;
        } else {
          out += static_cast<char>(c);
        }
    }
  }
  return out;
}

std::string HexEncode(const unsigned char* data, size_t length) {
  static const char* digits = "0123456789abcdef";
  std::string out;
  out.reserve(length * 2);
  for (size_t i = 0; i < length; ++i) {
    out += digits[data[i] >> 4];
    out += digits[data[i] & 0x0f];
  }
  return out;
}

std::string Utf8FromWide(const wchar_t* wide) {
  if (wide == nullptr) {
    return "";
  }
  const int size = WideCharToMultiByte(CP_UTF8, 0, wide, -1, nullptr, 0, nullptr, nullptr);
  if (size <= 1) {
    return "";
  }
  std::string out(static_cast<size_t>(size - 1), '\0');
  WideCharToMultiByte(CP_UTF8, 0, wide, -1, out.data(), size, nullptr, nullptr);
  return out;
}

std::wstring WideFromUtf8(const std::string& utf8) {
  const int size = MultiByteToWideChar(CP_UTF8, 0, utf8.c_str(), -1, nullptr, 0);
  if (size <= 1) {
    return L"";
  }
  std::wstring out(static_cast<size_t>(size - 1), L'\0');
  MultiByteToWideChar(CP_UTF8, 0, utf8.c_str(), -1, out.data(), size);
  return out;
}

// Appends the JSON value of one result column to |out|. Column types follow
// WCDB::Syntax::ColumnType: Null=0, Integer=1, Float=2, Text=3, BLOB=4.
bool AppendColumnValue(std::string* out, WCDB::Handle* handle, int index) {
  const int column_type = static_cast<int>(handle->getType(index));
  switch (column_type) {
    case 1: {  // INTEGER
      const int64_t value = handle->getInteger(index);
      out->append(std::to_string(value));
      return true;
    }
    case 2: {  // FLOAT
      const double value = handle->getDouble(index);
      char buffer[40];
      std::snprintf(buffer, sizeof(buffer), "%.17g", value);
      out->append(buffer);
      return true;
    }
    case 3: {  // TEXT
      const WCDB::UnsafeStringView text = handle->getText(index);
      // Copy immediately: the view is only valid until the next step.
      const std::string value(text.data(), text.length());
      out->append("\"");
      out->append(JsonEscape(value));
      out->append("\"");
      return true;
    }
    case 4: {  // BLOB
      const WCDB::UnsafeData blob = handle->getBLOB(index);
      out->append("\"");
      out->append(HexEncode(blob.buffer(), blob.size()));
      out->append("\"");
      return true;
    }
    default:  // NULL or unknown
      out->append("null");
      return true;
  }
}

int RunQuery(const QueryOptions& options) {
  SetStage("loading dll");
  DebugPrint(options, "load WCDB.dll");
  std::wstring wcdb_wide = WideFromUtf8(options.wcdb_path);
  HMODULE module = LoadLibraryW(wcdb_wide.c_str());
  if (module == nullptr) {
    std::fprintf(stderr, "[wcdb-debug] load dll failed error=%lu stage=%s\n", GetLastError(),
                 g_stage);
    std::fflush(stderr);
    std::printf("{\"ok\":false,\"stage\":\"load\",\"error\":\"LoadLibraryW failed: %lu\"}\n",
                GetLastError());
    return 1;
  }
  std::fprintf(stderr, "[wcdb-debug] dll loaded path=%s\n", options.wcdb_path.c_str());
  std::fflush(stderr);
  struct ModuleGuard {
    HMODULE* module;
    ~ModuleGuard() {
      if (*module != nullptr) {
        FreeLibrary(*module);
        *module = nullptr;
      }
    }
  } module_guard{&module};

  SetStage("symbols loaded");
  DebugPrint(options, "import-lib symbols available");

  unsigned char key_bytes[32] = {};
  if (!options.no_cipher) {
    if (!ParseHexKey(options.key_hex, key_bytes)) {
      std::printf("{\"ok\":false,\"stage\":\"key\",\"error\":\"key must be exactly 64 hex chars\"}\n");
      return 1;
    }
  }
  if (options.sql.empty()) {
    std::printf("{\"ok\":false,\"stage\":\"sql\",\"error\":\"missing --sql\"}\n");
    return 1;
  }

  try {
    SetStage("create database object");
    DebugPrint(options, "construct database");
    // Public API: the InnerDatabase object is created inside WCDB.dll and is
    // never constructed on the caller stack, removing the private-layout hazard
    // of the previous direct `WCDB::InnerDatabase db(...)` construction.
    WCDB::Database db(WCDB::UnsafeStringView(options.db_path.c_str()), /*readOnly=*/true);

    SetStage("configure cipher");
    if (!options.no_cipher) {
      DebugPrint(options, "set cipher key");
      const WCDB::UnsafeData key =
          WCDB::UnsafeData::immutable(key_bytes, sizeof(key_bytes));
      db.setCipherKey(key, options.page_size,
                      static_cast<WCDB::Database::CipherVersion>(options.cipher_version));
    }

    SetStage("open database");
    DebugPrint(options, "open database");
    if (!db.canOpen()) {
      std::printf("{\"ok\":false,\"stage\":\"open\",\"error\":\"canOpen failed\"}\n");
      return 1;
    }

    DebugPrint(options, "get handle");
    WCDB::Handle handle = db.getHandle();

    // Raw SQL prepare is not exposed on the public Handle (StatementOperation::
    // prepare() only accepts winq Statement objects and no SQL-text parser is
    // provided in v2.1.15), so the shared InnerHandle is reached through the
    // public core API solely to prepare the arbitrary SQL text supplied by
    // Python. getOrCreateDatabase returns the same InnerDatabase instance that
    // `db` wraps (same normalized path); no database object is constructed on
    // the caller stack here.
    SetStage("prepare statement");
    DebugPrint(options, "prepare");
    WCDB::RecyclableDatabase database_holder = WCDB::CommonCore::shared().getOrCreateDatabase(
        WCDB::Path::normalize(WCDB::UnsafeStringView(options.db_path.c_str())));
    WCDB::RecyclableHandle recyclable = database_holder.get()->getHandle(false, false);
    WCDB::InnerHandle* inner_handle = recyclable.get();
    if (inner_handle == nullptr) {
      std::printf(
          "{\"ok\":false,\"stage\":\"prepare\",\"error\":\"inner handle is null\"}\n");
      return 1;
    }
    if (!inner_handle->prepare(WCDB::UnsafeStringView(options.sql.c_str()))) {
      std::printf("{\"ok\":false,\"stage\":\"prepare\",\"error\":\"prepare failed\"}\n");
      return 1;
    }
    SetStage("bind arguments");
    DebugPrint(options, "no bind arguments (literal SQL)");

    DebugPrint(options, "read columns");
    std::vector<std::string> columns;
    const int column_count = handle.getNumberOfColumns();
    for (int index = 0; index < column_count; ++index) {
      const WCDB::UnsafeStringView name = handle.getColumnName(index);
      const std::string name_copy(name.data(), name.length());
      if (name_copy.empty()) {
        break;
      }
      columns.push_back(name_copy);
    }

    std::string out = "{\"ok\":true,\"columns\":[";
    for (size_t i = 0; i < columns.size(); ++i) {
      if (i > 0) {
        out += ",";
      }
      out += "\"";
      out += JsonEscape(columns[i]);
      out += "\"";
    }
    out += "],\"rows\":[";

    SetStage("execute step");
    DebugPrint(options, "step rows");
    bool first_row = true;
    int row_count = 0;
    int max_rows = options.limit > 0 ? options.limit : 100000;
    while (row_count < max_rows) {
      if (!handle.step()) {
        break;
      }
      if (handle.done()) {
        break;
      }
      if (options.debug && row_count < 5) {
        std::fprintf(stderr, "[wcdb_cli] row %d\n", row_count + 1);
        std::fflush(stderr);
      }
      if (!first_row) {
        out += ",";
      }
      first_row = false;
      out += "{";
      for (size_t i = 0; i < columns.size(); ++i) {
        if (i > 0) {
          out += ",";
        }
        out += "\"";
        out += JsonEscape(columns[i]);
        out += "\":";
        if (options.debug && row_count < 2) {
          std::fprintf(stderr, "[wcdb_cli]   column %zu\n", i);
          std::fflush(stderr);
        }
        if (!AppendColumnValue(&out, &handle, static_cast<int>(i))) {
          out += "null";
        }
      }
      out += "}";
      ++row_count;
    }

    const bool truncated = options.limit > 0 && row_count >= options.limit;
    SetStage("finalize");
    DebugPrint(options, "done");
    handle.invalidate();

    out += "],\"row_count\":";
    out += std::to_string(row_count);
    out += truncated ? ",\"truncated\":true" : ",\"truncated\":false";
    out += ",\"db\":\"";
    out += JsonEscape(options.db_path);
    out += "\"}";
    SetStage("export result");
    DebugPrint(options, "print result");
    std::printf("%s\n", out.c_str());
  } catch (...) {
    std::fprintf(stderr, "[wcdb-debug] unexpected C++ exception stage=%s\n", g_stage);
    std::fflush(stderr);
    std::printf("{\"ok\":false,\"stage\":\"%s\",\"error\":\"unexpected C++ exception\"}\n",
                g_stage);
    return 1;
  }

  return 0;
}

std::string OptionValue(
    const std::vector<std::string>& args,
    const std::string& name,
    const std::string& fallback = "") {
  for (size_t i = 0; i + 1 < args.size(); ++i) {
    if (args[i] == name) {
      return args[i + 1];
    }
  }
  return fallback;
}

int ParsePositiveInt(const std::string& value, int fallback) {
  if (value.empty()) {
    return fallback;
  }
  try {
    const long parsed = std::strtol(value.c_str(), nullptr, 10);
    return parsed > 0 ? static_cast<int>(parsed) : fallback;
  } catch (...) {
    return fallback;
  }
}

}  // namespace

int wmain(int argc, wchar_t** wargv) {
  SetUnhandledExceptionFilter(NativeExceptionFilter);
  SetStage("startup");
  PrintHostInfo();

  std::vector<std::string> args;
  args.reserve(static_cast<size_t>(argc));
  for (int i = 0; i < argc; ++i) {
    args.push_back(Utf8FromWide(wargv[i]));
  }

  QueryOptions options;
  options.wcdb_path = OptionValue(args, "--wcdb");
  options.db_path = OptionValue(args, "--db");
  options.key_hex = OptionValue(args, "--key");
  options.sql = OptionValue(args, "--sql");
  options.limit = ParsePositiveInt(OptionValue(args, "--limit"), 0);
  options.page_size = ParsePositiveInt(OptionValue(args, "--page-size"), 4096);
  options.cipher_version = ParsePositiveInt(OptionValue(args, "--cipher-version"), 0);
  for (const std::string& arg : args) {
    if (arg == "--no-cipher") {
      options.no_cipher = true;
    } else if (arg == "--debug") {
      options.debug = true;
    } else if (arg == "--schema" && options.sql.empty()) {
      options.sql = kSchemaSql;
    }
  }

  if (options.key_hex.empty() && !options.no_cipher) {
    const char* env_key = std::getenv("WX_DB_KEY");
    if (env_key != nullptr) {
      options.key_hex = env_key;
    }
  }

  if (options.wcdb_path.empty()) {
    std::printf("{\"ok\":false,\"stage\":\"args\",\"error\":\"missing --wcdb\"}\n");
    return 2;
  }
  if (options.db_path.empty()) {
    std::printf("{\"ok\":false,\"stage\":\"args\",\"error\":\"missing --db\"}\n");
    return 2;
  }
  if (options.key_hex.empty() && !options.no_cipher) {
    std::printf("{\"ok\":false,\"stage\":\"args\",\"error\":\"missing --key or WX_DB_KEY\"}\n");
    return 2;
  }
  if (options.sql.empty()) {
    std::printf("{\"ok\":false,\"stage\":\"args\",\"error\":\"missing --sql\"}\n");
    return 2;
  }

  return RunQuery(options);
}
