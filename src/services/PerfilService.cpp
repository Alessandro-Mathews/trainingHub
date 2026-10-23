#include "traininghub/services/PerfilService.h"

#include <drogon/drogon.h>
#include <utility>

namespace traininghub::services
{
namespace
{
bool valid(const models::Perfil &perfil)
{
    return perfil.nome.find_first_not_of(" \t\r\n\f\v") != std::string::npos
        && (perfil.ativo == 0 || perfil.ativo == 1);
}

repositories::PerfilRepository::ErrorCallback databaseError(
    PerfilService::ErrorCallback callback)
{
    return [callback = std::move(callback)](const drogon::orm::DrogonDbException &error)
    {
        if (dynamic_cast<const drogon::orm::UniqueViolation *>(&error))
            callback(PerfilError::DuplicateName);
        else if (dynamic_cast<const drogon::orm::ForeignKeyViolation *>(&error))
            callback(PerfilError::InUse);
        else
        {
            LOG_ERROR << "Falha no banco do modulo Perfil: " << error.base().what();
            callback(PerfilError::Database);
        }
    };
}
}

PerfilService::PerfilService(repositories::PerfilRepository repository)
    : repository_(std::move(repository))
{
}

void PerfilService::listar(ListCallback callback, ErrorCallback errorCallback) const
{
    repository_.listar(std::move(callback), databaseError(std::move(errorCallback)));
}

void PerfilService::buscarPorId(std::int64_t id, FindCallback callback,
                               ErrorCallback errorCallback) const
{
    if (id <= 0)
    {
        errorCallback(PerfilError::InvalidInput);
        return;
    }
    repository_.buscarPorId(id,
        [callback, errorCallback](const std::optional<models::Perfil> &perfil)
        {
            if (!perfil)
                errorCallback(PerfilError::NotFound);
            else
                callback(*perfil);
        }, databaseError(errorCallback));
}

void PerfilService::criar(const models::Perfil &perfil, CreateCallback callback,
                         ErrorCallback errorCallback) const
{
    if (!valid(perfil))
    {
        errorCallback(PerfilError::InvalidInput);
        return;
    }
    repository_.criar(perfil, std::move(callback), databaseError(std::move(errorCallback)));
}

void PerfilService::atualizar(std::int64_t id, const models::Perfil &perfil,
                             SuccessCallback callback, ErrorCallback errorCallback) const
{
    if (id <= 0 || !valid(perfil))
    {
        errorCallback(PerfilError::InvalidInput);
        return;
    }
    repository_.atualizar(id, perfil,
        [callback, errorCallback](bool changed)
        {
            if (!changed)
                errorCallback(PerfilError::NotFound);
            else
                callback();
        }, databaseError(errorCallback));
}

void PerfilService::excluir(std::int64_t id, SuccessCallback callback,
                           ErrorCallback errorCallback) const
{
    if (id <= 0)
    {
        errorCallback(PerfilError::InvalidInput);
        return;
    }
    // The FK is the final guard, including concurrent Usuario inserts.
    repository_.excluir(id,
        [callback, errorCallback](bool changed)
        {
            if (!changed)
                errorCallback(PerfilError::NotFound);
            else
                callback();
        }, databaseError(errorCallback));
}

}
