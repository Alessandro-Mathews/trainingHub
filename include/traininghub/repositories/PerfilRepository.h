#pragma once

#include "traininghub/models/Perfil.h"

#include <cstdint>
#include <optional>
#include <vector>

namespace traininghub::repositories
{

class PerfilRepository
{
public:

    std::vector<models::Perfil> listar();

    std::optional<models::Perfil> buscarPorId(
        std::int64_t id
    );

    std::int64_t criar(
        const models::Perfil& perfil
    );

    bool atualizar(
        std::int64_t id,
        const models::Perfil& perfil
    );

    bool excluir(
        std::int64_t id
    );
};

}