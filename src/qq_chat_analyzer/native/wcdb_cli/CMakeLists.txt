cmake_minimum_required(VERSION 3.20)
project(wcdb_cli LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_executable(wcdb_cli main.cpp)
target_compile_options(wcdb_cli PRIVATE /W4 /EHsc)
target_compile_definitions(wcdb_cli PRIVATE _CRT_SECURE_NO_WARNINGS)
