cmake_minimum_required(VERSION 3.20)
project(TrainingHubSecurityTests LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(Drogon CONFIG REQUIRED)
find_package(unofficial-argon2 CONFIG REQUIRED)

add_executable(security_tests
    security_tests.cpp
    ../src/security/PasswordHasher.cpp
    ../src/security/SessionManager.cpp
)
target_compile_features(security_tests PRIVATE cxx_std_20)
target_include_directories(security_tests PRIVATE ../include)
target_link_libraries(security_tests PRIVATE Drogon::Drogon unofficial::argon2::libargon2)

add_executable(sqlite_foreign_keys_tests
    sqlite_foreign_keys_tests.cpp
    ../src/database/SqliteConfig.cpp
)
target_include_directories(sqlite_foreign_keys_tests PRIVATE ../include)
target_link_libraries(sqlite_foreign_keys_tests PRIVATE Drogon::Drogon SQLite3_lib)

enable_testing()
add_test(NAME security COMMAND security_tests)
add_test(NAME sqlite_foreign_keys COMMAND sqlite_foreign_keys_tests)
