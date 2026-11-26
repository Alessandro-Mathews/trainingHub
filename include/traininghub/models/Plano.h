#pragma once

#include <cstdint>
#include <optional>
#include <string>

namespace traininghub::models
{
struct Plano
{
    std::int64_t id{};
    std::int64_t academiaId{};
    std::string nome;
    std::optional<std::string> descricao;
    std::int64_t valorCentavos{};
    std::int64_t duracaoDias{};
    bool ativo{true};
    std::string criadoEm;
};
}
