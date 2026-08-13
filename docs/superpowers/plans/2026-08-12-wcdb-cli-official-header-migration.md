# wcdb_cli 迁移设计：GetProcAddress 私有 C++ ABI → 官方 WCDB v2.1.15 header 直接链接

- 日期：2026-08-12
- 状态：设计定稿（未实现、未 build）
- 范围：仅 `src/qq_chat_analyzer/native/wcdb_cli/main.cpp` + `CMakeLists.txt` + 新增 third_party/include/lib
- 不动：Python Provider、GUI、Analyzer、Key 获取、cipher 参数语义、SQL、JSON 契约、命令参数

---

## 1. 当前 main.cpp 使用的 WCDB 内部 API（已对照 DLL 导出验证）

现状：`GetProcAddress` + 手写函数指针 + 栈上猜测 buffer 镜像 C++ 对象。
`main.cpp` 中共 25 个符号常量；`LoadSymbols` 实际解析 24 个（`kGetVersionSymbol` 为死常量，未解析）。

已用 `dumpbin /exports`（`build\wcdb_exports.txt`，26701 行）逐一核对：**24/24 全部存在于 `runtime\wechat\WCDB.dll` 导出表**。

| 手写声明 | 真实导出（mangled） | 说明 |
|---|---|---|
| `UnsafeStringView ctor(const char*)` | `??0UnsafeStringView@WCDB@@QEAA@PEBD@Z` | 按值/引用传参 |
| `InnerDatabase ctor(const UnsafeStringView&)` | `??0InnerDatabase@WCDB@@QEAA@AEBVUnsafeStringView@1@@Z` | 对象 buffer 8KB 猜测 |
| `setReadOnly()` | `?setReadOnly@InnerDatabase@WCDB@@QEAAXXZ` | |
| `canOpen()` | `?canOpen@InnerDatabase@WCDB@@QEAA_NXZ` | |
| `setConfig(name, shared_ptr<Config>, prio)` | `?setConfig@InnerDatabase@WCDB@@QEAAXAEBVUnsafeStringView@2@AEBV?$shared_ptr@VConfig@WCDB@@@std@@H@Z` | shared_ptr 跨边界 |
| `getHandle(bool,bool) → RecyclableHandle` | `?getHandle@InnerDatabase@WCDB@@QEAA?AVRecyclableHandle@2@_N0@Z` | **按值返回** |
| `RecyclableHandle::get() → InnerHandle*` | `?get@RecyclableHandle@WCDB@@QEBAPEAVInnerHandle@2@XZ` | |
| `UnsafeData::immutable(const uint8_t*, size_t)` | `?immutable@UnsafeData@WCDB@@SA?BV12@PEBE_K@Z` | 静态，按值返回 |
| `make_shared<CipherConfig>(UnsafeData, int&, CipherVersion&)` | `??$make_shared@VCipherConfig@WCDB@@AEBVUnsafeData@2@AEAHAEAW4CipherVersion@Database@2@@std@@...` | 模板实例导出 |
| `InnerHandle::prepare(UnsafeStringView)` | `?prepare@InnerHandle@WCDB@@QEAA_NAEBVUnsafeStringView@2@@Z` | 另有 `AEBVStatement@2` 重载也导出 |
| `step/done` | `?step@InnerHandle@WCDB@@QEAA_NXZ` / `?done@...` | |
| `getInteger(int) → int64_t` | `?getInteger@InnerHandle@WCDB@@QEAA_JH@Z` | 标量，安全 |
| `getDouble(int) → double` | `?getDouble@InnerHandle@WCDB@@QEAANH@Z` | 标量，安全 |
| `getNumberOfColumns() → int` | `?getNumberOfColumns@InnerHandle@WCDB@@QEAAHXZ` | |
| `getText(int) → UnsafeStringView` | `?getText@InnerHandle@WCDB@@QEAA?AVUnsafeStringView@2@H@Z` | **按值返回（非 const）** |
| `getColumnName(int) → UnsafeStringView` | `?getColumnName@InnerHandle@WCDB@@QEAA?BVUnsafeStringView@2@H@Z` | **按值返回（const）→ mangled 不同** |
| `getColumnType(int) → int` | `?getColumnType@InnerHandle@WCDB@@QEAA?AW4ColumnType@Syntax@2@H@Z` | **返回 WCDB::Syntax::ColumnType 枚举** |
| `getBLOB(int) → UnsafeData` | `?getBLOB@InnerHandle@WCDB@@QEAA?AVUnsafeData@2@H@Z` | **按值返回** |

关键 ABI 风险（已确认）：
- 手写镜像：`StringViewData {const char*, size_t}` 16B、`BlobViewData {vtable, ptr, size}` 24B —— 均为猜测布局。
- 猜测 buffer：`db_buffer[0x2000]`(8KB)、`recyclable_buffer[0x100]`、`path/sql/name/data/config/column/text_buffer[0x40]`、`blob_buffer[0x80]`。
- MSVC 对类/枚举按值返回会把返回类型编进 mangled 名：`?AV`（非 const 按值）vs `?BV`（const 按值）vs `?AW4...@Syntax@2`（嵌套枚举）——**官方 header 声明必须与 DLL 导出逐字节一致，否则链接失败**。

---

## 2. 官方 v2.1.15 中的真实 C++ API（对应表）

| 现状（手写） | 官方 v2.1.15 头文件 |
|---|---|
| `InnerDatabase ctor(UnsafeStringView)` | `src/common/core/InnerDatabase.hpp`（同签名） |
| `setReadOnly/canOpen/setConfig/getHandle` | 同上；`getHandle() → RecyclableHandle` |
| `prepare/step/done/getInteger/getDouble/getNumberOfColumns/getText/getColumnName/getColumnType/getBLOB` | `src/common/core/InnerHandle.hpp`（Text/BLOB = `ColumnTypeInfo<...>::UnderlyingType`） |
| `CipherConfig` 手工 shared_ptr | `src/common/core/config/CipherConfig.hpp`：`CipherConfig(const UnsafeData&, int pageSize, int cipherVersion)` |
| 配置名 `"com.Tencent.WCDB.Config.Cipher"` | `src/common/core/CoreConst.h` `CipherConfigName` 常量 |
| `UnsafeStringView / UnsafeData / RecyclableHandle` | `SyntaxCommonConst.hpp`、`src/common/base/UnsafeData.hpp`、`src/common/core/RecyclableHandle.hpp` |
| （公共替代，后续演进） | `src/cpp/core/Database.hpp`：`Database(path, readOnly)`、`setCipherKey(UnsafeData, 4096, CipherVersion)`、`getHandle() → Handle` |

注意：官方 v2.1.15 源码**尚未放入本仓库**（`native/wcdb_cli/third_party` 不存在），需按第 4 节获取。DLL 中 `?prepare@...AEBVStatement@2@@Z` 亦存在，说明 winq 语法树路径可链接，但最小迁移仍走 `UnsafeStringView` 重载，与现状完全一致。

---

## 3. 最小迁移方式（推荐：内部 API + 官方 header 直接链接）

- 保留：命令行参数（`--wcdb/--db/--key/--sql/--limit/--page-size/--cipher-version/--no-cipher/--schema/--debug`）、stdout JSON 契约、`[wcdb-debug]` 阶段日志、SEH、主机信息。
- 删除：全部 `GetProcAddress`、手写 `struct`/`typedef`/函数指针、猜测 buffer、`IsReadableRegion`/`ReadStringView`/`ReadBlobView` 镜像逻辑。
- 替换为直接 include 官方 header、真实类型 RAII：
  - `UnsafeStringView path_view(db_path.c_str()); InnerDatabase db(path_view); db.setReadOnly();`
  - `UnsafeData key = UnsafeData::immutable(key_bytes, 32); auto config = std::make_shared<CipherConfig>(key, page_size, static_cast<CipherVersion>(cipher_version)); db.setConfig(CipherConfigName, config, 0x80000000);`
  - `RecyclableHandle handle = db.getHandle(false, false); InnerHandle* h = handle.get();`
  - `h->prepare(UnsafeStringView(sql)); while (h->step()) { h->getInteger(i); h->getText(i); h->getBLOB(i); ... } h->done();`
- 编译链接 `WCDB.lib`（import lib），由链接器保证符号/签名一致；对象布局、析构、生命周期全部交给编译器，不再跨边界手拼。

备选（不推荐本阶段做）：改公共 `WCDB::Database` + `setCipherKey` + `Handle`——`Handle::prepare` 接受 `Statement` 语法对象，任意 `--sql` 需 winq 解析入口，增加不确定面，留作后续演进。

---

## 4. 需要新增

**include（第三方源码树）**
- `src/qq_chat_analyzer/native/wcdb_cli/third_party/wcdb-2.1.15/`：官方 v2.1.15 整棵 `src` 树（`src/common`、`src/cpp`、`src/bridge/include`、winq），避免缺失传递 include。
- sqlcipher 子模块的 `sqlite3.h`（WCDB header 依赖）。
- CMake include 目录指向上述路径。

**lib**
- 仓库现无 `WCDB.lib`。从 `runtime/wechat/WCDB.dll` 生成：
  `dumpbin /exports WCDB.dll` → 整理 `.def` → `lib /machine:x64 /def:WCDB.def /out:WCDB.lib`（DLL 导出 26682+ 符号，含全部所需类方法）。
- CMake 用 `add_library(WCDB SHARED IMPORTED)` + `IMPORTED_IMPLIB` / `IMPORTED_LOCATION`（指向 `runtime/wechat/WCDB.dll`），或直接链接生成的 `WCDB.lib`。

**CMake 配置（`native/wcdb_cli/CMakeLists.txt`）**
- 增加 include 目录、链接 `WCDB.lib`。
- 保留 `/W4 /EHsc`，增加 `/utf-8`（源文件含非 ASCII 注释/字符串安全）。
- `wmain` 入口需 `target_link_options(wcdb_cli PRIVATE /SUBSYSTEM:CONSOLE)`。

**runtime 文件**
- **无新增**。`wechat\wcdb_cli.exe`、`wechat\WCDB.dll` 已在 `scripts/build_windows_exe.ps1` 的 `RequiredRuntimePaths`；构建后覆盖 `runtime/wechat/wcdb_cli.exe` 即可，打包结构不变。

---

## 5. 是否可以继续使用当前 CipherTalk 的 WCDB.dll

**可以，先用它验证。** 依据：
- 当前 main.cpp 用到的 24 个符号在 DLL 导出表中 24/24 存在（第 1 节逐项核对）。
- 该 DLL 与官方 v2.1.15 同源码线（SQLCipher 4.1.0 / SQLite 3.27.2 / OpenSSL 1.1.1l、`CMAKE_WINDOWS_EXPORT_ALL_SYMBOLS`、`WCDB_IDENTIFIER` 一致，前序指纹分析结论）。

前置校验（编译后必做）：
1. 链接成功即符号级校验；再对关键符号（`prepare@InnerHandle`、`getText/getBLOB/getColumnName/getColumnType`、`setConfig`、`getHandle`）比对编译产物与 DLL 导出。
2. 保留启动时一次性的关键符号 `GetProcAddress` 校验（仅诊断用途，不影响主流程）。
3. 先跑 `SELECT count(*) FROM sqlite_master` 冒烟，再跑真实 session_list。

风险与兜底：
- 该 DLL 是 "Custom build"（无版本号），可能有官方之外 patch；MSVC 工具链版本差异影响 `std::shared_ptr<CipherConfig>` 等跨边界布局。
- 若冒烟即崩溃或符号不符 → 兜底：用官方 v2.1.15 源码按官方 CMake（`BUILD_SHARED_LIBS=ON`）重建 `WCDB.dll` 替换 runtime（与微信库兼容性已由指纹确认）。

---

## 6. 迁移步骤与风险

**步骤**
1. 拉取官方 v2.1.15 源码（含 sqlcipher 子模块）到 `native/wcdb_cli/third_party/wcdb-2.1.15`。
2. 从 `runtime/wechat/WCDB.dll` 生成 `WCDB.lib`。
3. 改写 `main.cpp`：删除 GetProcAddress/手写布局，替换为官方类型直接调用；保留参数、JSON 契约、`[wcdb-debug]` 阶段日志、SEH、主机信息。
4. 更新 `CMakeLists.txt`（include/lib/subsystem/utf-8）。
5. 编译 → 符号比对校验 → `count(*)` 冒烟 → 真实库验证。
6. 覆盖 `runtime/wechat/wcdb_cli.exe`，按既有流程打包（`scripts\build_windows_exe.ps1`）。

**风险**
- 高：官方 header 与私有 DLL 的 ABI 不完全一致（patch/MSVC 版本）→ 链接错或运行崩溃；缓解：步骤 5 符号校验 + 冒烟 + 重建 DLL 兜底。
- 中：`std::shared_ptr<CipherConfig>` 跨 DLL 边界（现状同样存在，`count(*)` 已证明该路径可行）；缓解：保持同工具链编译，或改用公共 `Database::setCipherKey` 路径。
- 中：WCDB header 依赖链复杂（winq/sqlcipher/bridge）；缓解：拷贝完整 src 树 + sqlcipher 头。
- 低：行为等价性（cipher_version/page_size 语义不变，配置名用 `CipherConfigName` 常量）。
- 低：`wmain` 入口与 CMake 默认 entry 差异；缓解：显式 `/SUBSYSTEM:CONSOLE`。

---

## 结论

- 最小迁移 = 保留现有流程骨架，把 GetProcAddress + 手写布局整体替换为官方 v2.1.15 header 直接链接；参数/JSON/日志/SEH 全部保留。
- 先继续使用 CipherTalk 的 `WCDB.dll` 验证（24/24 符号已核对存在），符号不符或冒烟崩溃时用官方源码重建 DLL 兜底。
- 改动面：`main.cpp` + `CMakeLists.txt` + 新增 third_party（官方源码 + `WCDB.lib`）；无 runtime 新增、无 Python/GUI 改动。
