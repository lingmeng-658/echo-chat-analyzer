cmake_minimum_required(VERSION 3.20)
project(wcdb_cli LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# WCDB source tree and import library are explicit inputs, provided by
# scripts/bootstrap_wechat_native.ps1 (or passed manually on the command line).
# No machine-local third_party checkout or build directory is assumed.
set(WCDB_SOURCE_DIR "" CACHE PATH
    "Root of the official Tencent WCDB v2.1.15 source tree (contains src/common and src/cpp)")
set(WCDB_LIBRARY "" CACHE FILEPATH
    "WCDB.lib import library built from the official WCDB source (Release x64)")

if(NOT WCDB_SOURCE_DIR)
  message(FATAL_ERROR "WCDB_SOURCE_DIR is required. "
                      "Run scripts/bootstrap_wechat_native.ps1 or pass -DWCDB_SOURCE_DIR=<wcdb-src>")
endif()
if(NOT WCDB_LIBRARY)
  message(FATAL_ERROR "WCDB_LIBRARY is required. "
                      "Run scripts/bootstrap_wechat_native.ps1 or pass -DWCDB_LIBRARY=<path-to-WCDB.lib>")
endif()
if(NOT EXISTS "${WCDB_SOURCE_DIR}/src/common")
  message(FATAL_ERROR "WCDB_SOURCE_DIR does not contain src/common: ${WCDB_SOURCE_DIR}")
endif()
if(NOT EXISTS "${WCDB_LIBRARY}")
  message(FATAL_ERROR "WCDB_LIBRARY does not exist: ${WCDB_LIBRARY}")
endif()

set(WCDB_ROOT ${WCDB_SOURCE_DIR})
file(GLOB_RECURSE WCDB_COMMON_DIRS LIST_DIRECTORIES true "${WCDB_ROOT}/src/common/*")
file(GLOB_RECURSE WCDB_CPP_DIRS LIST_DIRECTORIES true "${WCDB_ROOT}/src/cpp/*")
set(WCDB_INCLUDE_DIRS "${WCDB_ROOT}/src/common")
foreach(_dir IN LISTS WCDB_COMMON_DIRS)
  if(IS_DIRECTORY "${_dir}")
    list(APPEND WCDB_INCLUDE_DIRS "${_dir}")
  endif()
endforeach()
foreach(_dir IN LISTS WCDB_CPP_DIRS)
  if(IS_DIRECTORY "${_dir}")
    list(APPEND WCDB_INCLUDE_DIRS "${_dir}")
  endif()
endforeach()

add_executable(wcdb_cli main.cpp)
target_compile_options(wcdb_cli PRIVATE /W4 /EHsc /utf-8)
target_compile_definitions(wcdb_cli PRIVATE _CRT_SECURE_NO_WARNINGS WCDB_DLL)
target_include_directories(wcdb_cli PRIVATE ${WCDB_INCLUDE_DIRS})
target_link_libraries(wcdb_cli PRIVATE "${WCDB_LIBRARY}")
target_link_options(wcdb_cli PRIVATE /SUBSYSTEM:CONSOLE)
