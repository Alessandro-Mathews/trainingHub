cmake_minimum_required(VERSION 3.20)

project(TrainingHub
    VERSION 0.1.0
    LANGUAGES CXX
)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(Drogon CONFIG REQUIRED)

add_executable(traininghub
    src/main.cpp
    src/controllers/HealthController.cpp
    src/controllers/AcademiaController.cpp
    src/repositories/AcademiaRepository.cpp
    src/services/AcademiaService.cpp
)

target_include_directories(traininghub
    PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_link_libraries(traininghub
    PRIVATE
        Drogon::Drogon
)
