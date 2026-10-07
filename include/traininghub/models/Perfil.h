#pragma once

#include <cstdint>
#include <optional>
#include <string>

namespace traininghub::models
{

struct Perfil
{
    std::int64_t id{};
    std::string nome;
    std::optional<std::string> descricao;
    int ativo{1};
    std::string criado_em;
};

}