#pragma once

#include <cstdint>
#include <string>

namespace traininghub::models
{

struct Usuario
{
    std::int64_t id{};
    std::int64_t academia_id{};
    std::int64_t perfil_id{};
    std::string nome;
    std::string email;
    std::string senha_hash;
    bool ativo{true};
    std::string criado_em;
};

}
