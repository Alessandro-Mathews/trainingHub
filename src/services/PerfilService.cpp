#include "traininghub/services/PerfilService.h"

#include "traininghub/repositories/PerfilRepository.h"

namespace traininghub::services
{

std::vector<models::Perfil>
PerfilService::listar()
{
    repositories::PerfilRepository repository;

    return repository.listar();
}


std::optional<models::Perfil>
PerfilService::buscarPorId(std::int64_t id)
{
    repositories::PerfilRepository repository;

    return repository.buscarPorId(id);
}

std::int64_t PerfilService::criar(
    const models::Perfil& perfil)
{
    repositories::PerfilRepository repository;

    return repository.criar(perfil);
}


bool PerfilService::atualizar(
    std::int64_t id,
    const models::Perfil& perfil)
{
    repositories::PerfilRepository repository;

    return repository.atualizar(id, perfil);
}


bool PerfilService::excluir(
    std::int64_t id)
{
    repositories::PerfilRepository repository;

    return repository.excluir(id);
}

}