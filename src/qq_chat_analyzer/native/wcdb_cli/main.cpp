// Read-only WCDB query helper for WeChat 4.x databases.
//
// Loads the same WCDB.dll that WeChat uses, opens a database with a raw
// 32-byte key (64 hex chars), and prints one JSON document to stdout:
//
//   {"ok": true, "columns": [...], "rows": [...], "row_count": N, ...}
//   {"ok": false, "error": "...", "stage": "..."}
//
// The key is only kept in memory and is never printed or written to disk.

#include <windows.h>

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <string>
#include <vector>

namespace {

const char* kGetVersionSymbol = "?getVersion@Database@WCDB@@SA?BVStringView@2@XZ";

const char* kUnsafeStringViewCtor = "??0UnsafeStringView@WCDB@@QEAA@PEBD@Z";
const char* kUnsafeStringViewDtor = "??1UnsafeStringView@WCDB@@QEAA@XZ";
const char* kInnerDatabaseCtor = "??0InnerDatabase@WCDB@@QEAA@AEBVUnsafeStringView@1@@Z";
const char* kInnerDatabaseDtor = "??1InnerDatabase@WCDB@@UEAA@XZ";
const char* kSetReadOnly = "?setReadOnly@InnerDatabase@WCDB@@QEAAXXZ";
const char* kCanOpen = "?canOpen@InnerDatabase@WCDB@@QEAA_NXZ";
const char* kUnsafeDataImmutable = "?immutable@UnsafeData@WCDB@@SA?BV12@PEBE_K@Z";
const char* kUnsafeDataDtor = "??1UnsafeData@WCDB@@UEAA@XZ";
const char* kMakeSharedCipherConfig =
    "??$make_shared@VCipherConfig@WCDB@@AEBVUnsafeData@2@AEAHAEAW4CipherVersion@Database@2@@std@@"
    "YA?AV?$shared_ptr@VCipherConfig@WCDB@@@0@AEBVUnsafeData@WCDB@@AEAHAEAW4CipherVersion@Database@3@@Z";
const char* kSharedPtrCipherConfigDtor = "??1?$shared_ptr@VCipherConfig@WCDB@@@std@@QEAA@XZ";
const char* kSetConfig =
    "?setConfig@InnerDatabase@WCDB@@QEAAXAEBVUnsafeStringView@2@AEBV?$shared_ptr@VConfig@WCDB@@@std@@H@Z";
const char* kGetHandle = "?getHandle@InnerDatabase@WCDB@@QEAA?AVRecyclableHandle@2@_N0@Z";
const char* kRecyclableGet = "?get@RecyclableHandle@WCDB@@QEBAPEAVInnerHandle@2@XZ";
const char* kRecyclableDtor = "??1RecyclableHandle@WCDB@@UEAA@XZ";
const char* kPrepare = "?prepare@InnerHandle@WCDB@@QEAA_NAEBVUnsafeStringView@2@@Z";
const char* kStep = "?step@InnerHandle@WCDB@@QEAA_NXZ";
const char* kDone = "?done@InnerHandle@WCDB@@QEAA_NXZ";
const char* kGetInteger = "?getInteger@InnerHandle@WCDB@@QEAA_JH@Z";
const char* kGetDouble = "?getDouble@InnerHandle@WCDB@@QEAANH@Z";
const char* kGetNumberOfColumns = "?getNumberOfColumns@InnerHandle@WCDB@@QEAAHXZ";
const char* kGetText = "?getText@InnerHandle@WCDB@@QEAA?AVUnsafeStringView@2@H@Z";
const char* kGetColumnName = "?getColumnName@InnerHandle@WCDB@@QEAA?BVUnsafeStringView@2@H@Z";
const char* kGetColumnType = "?getColumnType@InnerHandle@WCDB@@QEAA?AW4ColumnType@Syntax@2@H@Z";
const char* kGetBlob = "?getBLOB@InnerHandle@WCDB@@QEAA?AVUnsafeData@2@H@Z";
const char* kSchemaSql = "SELECT name, type, sql FROM sqlite_master ORDER BY type, name";

using UnsafeStringViewCtorFn = void (*)(void*, const char*);
using UnsafeStringViewDtorFn = void (*)(void*);
using InnerDatabaseCtorFn = void (*)(void*, const void*);
using InnerDatabaseDtorFn = void (*)(void*);
using SetReadOnlyFn = void (*)(void*);
using CanOpenFn = bool (*)(void*);
using UnsafeDataImmutableFn = void (*)(void*, const unsigned char*, size_t);
using UnsafeDataDtorFn = void (*)(void*);
using MakeSharedCipherConfigFn = void (*)(void*, const void*, int*, int*);
using SharedPtrDtorFn = void (*)(void*);
using SetConfigFn = void (*)(void*, const void*, const void*, int);
using GetHandleFn = void (*)(void*, void*, bool, bool);
using RecyclableGetFn = void* (*)(void*);
using RecyclableDtorFn = void (*)(void*);
using PrepareFn = bool (*)(void*, const void*);
using StepFn = bool (*)(void*);
using DoneFn = bool (*)(void*);
using GetIntegerFn = int64_t (*)(void*, int);
using GetDoubleFn = double (*)(void*, int);
using GetNumberOfColumnsFn = int (*)(void*);
using GetTextFn = void* (*)(void*, void*, int);
using GetColumnNameFn = void* (*)(void*, void*, int);
using GetColumnTypeFn = int (*)(void*, int);
using GetBlobFn = void* (*)(void*, void*, int);

struct StringViewData {
  const char* data;
  size_t length;
};

struct BlobViewData {
  uintptr_t vtable;
  const unsigned char* data;
  size_t length;
};

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

bool IsReadableRegion(const void* ptr, size_t need) {
  if (ptr == nullptr) {
    return false;
  }
  MEMORY_BASIC_INFORMATION mbi{};
  if (!VirtualQuery(ptr, &mbi, sizeof(mbi))) {
    return false;
  }
  if (mbi.State != MEM_COMMIT) {
    return false;
  }
  const DWORD ok = PAGE_READONLY | PAGE_READWRITE | PAGE_WRITECOPY |
                   PAGE_EXECUTE_READ | PAGE_EXECUTE_READWRITE | PAGE_EXECUTE_WRITECOPY;
  if ((mbi.Protect & ok) == 0) {
    return false;
  }
  const uintptr_t start = reinterpret_cast<uintptr_t>(ptr);
  const uintptr_t region_end =
      reinterpret_cast<uintptr_t>(mbi.BaseAddress) + mbi.RegionSize;
  return start + need <= region_end;
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

class CleanupGuard {
 public:
  void Add(std::function<void()> action) {
    actions_.push_back(std::move(action));
  }

  void RunAll() {
    for (auto it = actions_.rbegin(); it != actions_.rend(); ++it) {
      try {
        (*it)();
      } catch (...) {
        // Destructor cleanup is best effort; the query result is already
        // finalised by the time this runs.
      }
    }
    actions_.clear();
  }

  ~CleanupGuard() {
    RunAll();
  }

 private:
  std::vector<std::function<void()>> actions_;
};

struct NativeSymbols {
  HMODULE module = nullptr;
  UnsafeStringViewCtorFn usv_ctor = nullptr;
  UnsafeStringViewDtorFn usv_dtor = nullptr;
  InnerDatabaseCtorFn db_ctor = nullptr;
  InnerDatabaseDtorFn db_dtor = nullptr;
  SetReadOnlyFn set_read_only = nullptr;
  CanOpenFn can_open = nullptr;
  UnsafeDataImmutableFn data_immutable = nullptr;
  UnsafeDataDtorFn data_dtor = nullptr;
  MakeSharedCipherConfigFn make_shared_config = nullptr;
  SharedPtrDtorFn shared_ptr_dtor = nullptr;
  SetConfigFn set_config = nullptr;
  GetHandleFn get_handle = nullptr;
  RecyclableGetFn recyclable_get = nullptr;
  RecyclableDtorFn recyclable_dtor = nullptr;
  PrepareFn prepare = nullptr;
  StepFn step = nullptr;
  DoneFn done = nullptr;
  GetIntegerFn get_integer = nullptr;
  GetDoubleFn get_double = nullptr;
  GetNumberOfColumnsFn get_number_of_columns = nullptr;
  GetTextFn get_text = nullptr;
  GetColumnNameFn get_column_name = nullptr;
  GetColumnTypeFn get_column_type = nullptr;
  GetBlobFn get_blob = nullptr;
};

FARPROC Resolve(HMODULE module, const char* name) {
  return GetProcAddress(module, name);
}

bool LoadSymbols(NativeSymbols* symbols) {
  auto* s = symbols;
  s->usv_ctor = reinterpret_cast<UnsafeStringViewCtorFn>(Resolve(s->module, kUnsafeStringViewCtor));
  s->usv_dtor = reinterpret_cast<UnsafeStringViewDtorFn>(Resolve(s->module, kUnsafeStringViewDtor));
  s->db_ctor = reinterpret_cast<InnerDatabaseCtorFn>(Resolve(s->module, kInnerDatabaseCtor));
  s->db_dtor = reinterpret_cast<InnerDatabaseDtorFn>(Resolve(s->module, kInnerDatabaseDtor));
  s->set_read_only = reinterpret_cast<SetReadOnlyFn>(Resolve(s->module, kSetReadOnly));
  s->can_open = reinterpret_cast<CanOpenFn>(Resolve(s->module, kCanOpen));
  s->data_immutable = reinterpret_cast<UnsafeDataImmutableFn>(Resolve(s->module, kUnsafeDataImmutable));
  s->data_dtor = reinterpret_cast<UnsafeDataDtorFn>(Resolve(s->module, kUnsafeDataDtor));
  s->make_shared_config =
      reinterpret_cast<MakeSharedCipherConfigFn>(Resolve(s->module, kMakeSharedCipherConfig));
  s->shared_ptr_dtor =
      reinterpret_cast<SharedPtrDtorFn>(Resolve(s->module, kSharedPtrCipherConfigDtor));
  s->set_config = reinterpret_cast<SetConfigFn>(Resolve(s->module, kSetConfig));
  s->get_handle = reinterpret_cast<GetHandleFn>(Resolve(s->module, kGetHandle));
  s->recyclable_get = reinterpret_cast<RecyclableGetFn>(Resolve(s->module, kRecyclableGet));
  s->recyclable_dtor = reinterpret_cast<RecyclableDtorFn>(Resolve(s->module, kRecyclableDtor));
  s->prepare = reinterpret_cast<PrepareFn>(Resolve(s->module, kPrepare));
  s->step = reinterpret_cast<StepFn>(Resolve(s->module, kStep));
  s->done = reinterpret_cast<DoneFn>(Resolve(s->module, kDone));
  s->get_integer = reinterpret_cast<GetIntegerFn>(Resolve(s->module, kGetInteger));
  s->get_double = reinterpret_cast<GetDoubleFn>(Resolve(s->module, kGetDouble));
  s->get_number_of_columns =
      reinterpret_cast<GetNumberOfColumnsFn>(Resolve(s->module, kGetNumberOfColumns));
  s->get_text = reinterpret_cast<GetTextFn>(Resolve(s->module, kGetText));
  s->get_column_name = reinterpret_cast<GetColumnNameFn>(Resolve(s->module, kGetColumnName));
  s->get_column_type = reinterpret_cast<GetColumnTypeFn>(Resolve(s->module, kGetColumnType));
  s->get_blob = reinterpret_cast<GetBlobFn>(Resolve(s->module, kGetBlob));

  return s->usv_ctor && s->usv_dtor && s->db_ctor && s->db_dtor && s->set_read_only &&
         s->can_open && s->data_immutable && s->data_dtor && s->make_shared_config &&
         s->shared_ptr_dtor && s->set_config && s->get_handle && s->recyclable_get &&
         s->recyclable_dtor && s->prepare && s->step && s->done && s->get_integer &&
         s->get_double && s->get_number_of_columns && s->get_text && s->get_column_name &&
         s->get_column_type && s->get_blob;
}

std::string ReadStringView(const unsigned char* buffer) {
  const uint64_t* qwords = reinterpret_cast<const uint64_t*>(buffer);
  const char* data = reinterpret_cast<const char*>(static_cast<uintptr_t>(qwords[0]));
  const size_t length = static_cast<size_t>(qwords[1]);
  if (data == nullptr || length == 0) {
    return "";
  }
  const size_t safe_length = IsReadableRegion(data, length) ? length : 0;
  if (safe_length == 0) {
    return "";
  }
  return std::string(data, safe_length);
}

bool AppendColumnValue(
    std::string* out,
    const NativeSymbols& symbols,
    void* inner_handle,
    int index) {
  const int column_type = symbols.get_column_type(inner_handle, index);
  switch (column_type) {
    case 1: {  // INTEGER
      const int64_t value = symbols.get_integer(inner_handle, index);
      out->append(std::to_string(value));
      return true;
    }
    case 2: {  // FLOAT
      const double value = symbols.get_double(inner_handle, index);
      char buffer[40];
      std::snprintf(buffer, sizeof(buffer), "%.17g", value);
      out->append(buffer);
      return true;
    }
    case 3: {  // TEXT
      alignas(16) unsigned char text_buffer[0x40] = {};
      symbols.get_text(inner_handle, text_buffer, index);
      const std::string text = ReadStringView(text_buffer);
      out->append("\"");
      out->append(JsonEscape(text));
      out->append("\"");
      return true;
    }
    case 4: {  // BLOB
      alignas(16) unsigned char blob_buffer[0x80] = {};
      symbols.get_blob(inner_handle, blob_buffer, index);
      const uint64_t* qwords = reinterpret_cast<const uint64_t*>(blob_buffer);
      const unsigned char* data =
          reinterpret_cast<const unsigned char*>(static_cast<uintptr_t>(qwords[1]));
      const size_t length = static_cast<size_t>(qwords[2]);
      if (data == nullptr || length == 0) {
        out->append("\"\"");
        return true;
      }
      const size_t safe_length = IsReadableRegion(data, length) ? length : 0;
      out->append("\"");
      out->append(HexEncode(data, safe_length));
      out->append("\"");
      return true;
    }
    case 5:  // NULL
    default:
      out->append("null");
      return true;
  }
}

int RunQuery(const QueryOptions& options) {
  DebugPrint(options, "load WCDB.dll");
  std::wstring wcdb_wide = WideFromUtf8(options.wcdb_path);
  NativeSymbols symbols;
  symbols.module = LoadLibraryW(wcdb_wide.c_str());
  if (symbols.module == nullptr) {
    std::printf("{\"ok\":false,\"stage\":\"load\",\"error\":\"LoadLibraryW failed: %lu\"}\n",
                GetLastError());
    return 1;
  }

  CleanupGuard cleanup;
  cleanup.Add([&symbols]() {
    if (symbols.module != nullptr) {
      FreeLibrary(symbols.module);
      symbols.module = nullptr;
    }
  });

  if (!LoadSymbols(&symbols)) {
    std::printf("{\"ok\":false,\"stage\":\"symbols\",\"error\":\"missing WCDB exports\"}\n");
    return 1;
  }
  DebugPrint(options, "symbols loaded");

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

  alignas(16) unsigned char path_buffer[0x40] = {};
  alignas(16) unsigned char db_buffer[0x2000] = {};
  alignas(16) unsigned char data_buffer[0x40] = {};
  alignas(16) unsigned char config_buffer[0x40] = {};
  alignas(16) unsigned char name_buffer[0x40] = {};
  // RecyclableHandle is a by-value return object whose constructor writes up
  // to offset 0x68. Keep a generous slot so getHandle cannot spill into the
  // adjacent SQL string-view buffer.
  alignas(16) unsigned char recyclable_buffer[0x100] = {};
  alignas(16) unsigned char sql_buffer[0x40] = {};

  try {
    DebugPrint(options, "construct path");
    symbols.usv_ctor(path_buffer, options.db_path.c_str());
    cleanup.Add([&]() { symbols.usv_dtor(path_buffer); });

    DebugPrint(options, "construct database");
    symbols.db_ctor(db_buffer, path_buffer);
    cleanup.Add([&]() { symbols.db_dtor(db_buffer); });

    DebugPrint(options, "set read-only");
    symbols.set_read_only(db_buffer);

    if (!options.no_cipher) {
      DebugPrint(options, "build cipher config");
      symbols.data_immutable(data_buffer, key_bytes, sizeof(key_bytes));
      cleanup.Add([&]() { symbols.data_dtor(data_buffer); });

      int page_size = options.page_size;
      int cipher_version = options.cipher_version;
      symbols.make_shared_config(config_buffer, data_buffer, &page_size, &cipher_version);
      cleanup.Add([&]() { symbols.shared_ptr_dtor(config_buffer); });

      symbols.usv_ctor(name_buffer, "com.Tencent.WCDB.Config.Cipher");
      cleanup.Add([&]() { symbols.usv_dtor(name_buffer); });

      DebugPrint(options, "apply cipher config");
      symbols.set_config(db_buffer, name_buffer, config_buffer, 0x80000000);
    }

    DebugPrint(options, "get handle");
    symbols.get_handle(db_buffer, recyclable_buffer, false, false);
    cleanup.Add([&]() { symbols.recyclable_dtor(recyclable_buffer); });

    DebugPrint(options, "recyclable get");
    void* inner_handle = symbols.recyclable_get(recyclable_buffer);
    if (inner_handle == nullptr) {
      std::printf(
          "{\"ok\":false,\"stage\":\"open\",\"error\":\"RecyclableHandle::get returned null\"}\n");
      return 1;
    }

    DebugPrint(options, "construct sql");
    symbols.usv_ctor(sql_buffer, options.sql.c_str());
    cleanup.Add([&]() { symbols.usv_dtor(sql_buffer); });

    DebugPrint(options, "prepare");
    if (!symbols.prepare(inner_handle, sql_buffer)) {
      std::printf("{\"ok\":false,\"stage\":\"prepare\",\"error\":\"prepare failed\"}\n");
      return 1;
    }

    DebugPrint(options, "read columns");
    std::vector<std::string> columns;
    const int column_count = symbols.get_number_of_columns(inner_handle);
    for (int index = 0; index < column_count; ++index) {
      alignas(16) unsigned char column_buffer[0x40] = {};
      symbols.get_column_name(inner_handle, column_buffer, index);
      const std::string name = ReadStringView(column_buffer);
      if (name.empty()) {
        break;
      }
      columns.push_back(name);
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

    DebugPrint(options, "step rows");
    bool first_row = true;
    int row_count = 0;
    int max_rows = options.limit > 0 ? options.limit : 100000;
    while (row_count < max_rows) {
      if (!symbols.step(inner_handle)) {
        break;
      }
      if (symbols.done(inner_handle)) {
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
        if (!AppendColumnValue(&out, symbols, inner_handle, static_cast<int>(i))) {
          out += "null";
        }
      }
      out += "}";
      ++row_count;
    }

    const bool truncated = options.limit > 0 && row_count >= options.limit;
    DebugPrint(options, "done");
    symbols.done(inner_handle);

    out += "],\"row_count\":";
    out += std::to_string(row_count);
    out += truncated ? ",\"truncated\":true" : ",\"truncated\":false";
    out += ",\"db\":\"";
    out += JsonEscape(options.db_path);
    out += "\"}";
    DebugPrint(options, "print result");
    std::printf("%s\n", out.c_str());
  } catch (...) {
    std::printf("{\"ok\":false,\"stage\":\"query\",\"error\":\"unexpected C++ exception\"}\n");
    return 1;
  }

  cleanup.RunAll();
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
