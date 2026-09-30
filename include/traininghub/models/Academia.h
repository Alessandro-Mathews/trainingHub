#pragma once

#include <cstdint>
#include <optional>
#include <string>

namespace traininghub::models
{

struct Academia
{
    std::int64_t id{};
    std::string nome;
    std::optional<std::string> cnpj;
    std::optional<std::string> email;
    std::optional<std::string> telefone;
    bool ativo{true};
    std::string criado_em;
};

}
