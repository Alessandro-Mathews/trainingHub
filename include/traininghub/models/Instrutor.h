#pragma once

#include <cstdint>
#include <string>

namespace traininghub::models
{
struct Instrutor
{
    std::int64_t id{};
    std::int64_t usuario_id{};
    std::string criado_em;
};
}
