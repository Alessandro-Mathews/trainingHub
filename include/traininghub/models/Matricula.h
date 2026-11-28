#pragma once

#include <cstdint>
#include <optional>
#include <string>

namespace traininghub::models
{
struct Matricula
{
    std::int64_t id{};
    std::int64_t academiaId{};
    std::int64_t alunoId{};
    std::int64_t planoId{};
    std::string nomePlanoContratado;
    std::int64_t valorContratadoCentavos{};
    std::int64_t duracaoContratadaDias{};
    std::string dataInicio;
    std::string dataFim;
    std::string criadoEm;
    std::optional<std::string> canceladoEm;
};
}
