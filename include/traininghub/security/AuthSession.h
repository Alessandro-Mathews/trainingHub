#pragma once

#include <cstdint>

namespace traininghub::security
{

struct AuthSession
{
    std::int64_t userId{};
    std::int64_t academiaId{};
    std::int64_t perfilId{};
};

}
