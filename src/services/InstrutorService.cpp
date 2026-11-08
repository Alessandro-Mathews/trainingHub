#include "traininghub/services/InstrutorService.h"
#include "traininghub/security/AuthorizationService.h"

#include <utility>

namespace traininghub::services
{
namespace
{
bool authorize(const security::ValidatedAuthContext &actor, security::Operation operation,
               const InstrutorService::ErrorCallback &errorCallback)
{
    if (actor.identity.userId <= 0 || actor.identity.academiaId <= 0 || actor.identity.perfilId <= 0)
    {
        errorCallback(InstrutorError::Unauthorized);
        return false;
    }
    if (!security::AuthorizationService::allows(actor.role, operation))
    {
        errorCallback(InstrutorError::Forbidden);
        return false;
    }
    return true;
}

repositories::InstrutorRepository::ErrorCallback databaseError(InstrutorService::ErrorCallback callback)
{
    return [callback = std::move(callback)](const drogon::orm::DrogonDbException &error)
    {
        if (dynamic_cast<const drogon::orm::UniqueViolation *>(&error))
            callback(InstrutorError::AlreadyExists);
        else if (dynamic_cast<const drogon::orm::ForeignKeyViolation *>(&error))
            callback(InstrutorError::RelationshipConflict);
        else
            callback(InstrutorError::Internal);
    };
}
}

InstrutorService::InstrutorService(repositories::InstrutorRepository repository) : repository_(std::move(repository)) {}

void InstrutorService::criar(const security::ValidatedAuthContext &actor, std::int64_t usuarioId,
    FindCallback callback, ErrorCallback errorCallback) const
{
    if (!authorize(actor, security::Operation::InstrutoresCreate, errorCallback)) return;
    if (usuarioId <= 0) { errorCallback(InstrutorError::InvalidInput); return; }
    repository_.buscarUsuarioParaCriacao(actor.identity.academiaId, usuarioId,
        [actor, usuarioId, callback, errorCallback, repository = repository_]
        (const std::optional<repositories::UsuarioParaInstrutor> &usuario)
        {
            if (!usuario) { errorCallback(InstrutorError::UsuarioNotFound); return; }
            if (!usuario->academiaAtiva) { errorCallback(InstrutorError::RelationshipConflict); return; }
            if (!usuario->usuarioAtivo || !usuario->perfilAtivo || !usuario->perfilNome
                || security::roleFromName(*usuario->perfilNome) != security::Role::INSTRUTOR)
            {
                errorCallback(InstrutorError::IneligibleUsuario);
                return;
            }
            if (usuario->possuiInstrutor) { errorCallback(InstrutorError::AlreadyExists); return; }
            repository.criar(actor.identity.academiaId, usuarioId, *usuario->perfilNome,
                [callback, errorCallback](const std::optional<models::Instrutor> &saved)
                {
                    if (saved) callback(*saved);
                    else errorCallback(InstrutorError::RelationshipConflict);
                }, databaseError(errorCallback));
        }, databaseError(errorCallback));
}

void InstrutorService::buscarPorId(const security::ValidatedAuthContext &actor, std::int64_t id,
    FindCallback callback, ErrorCallback errorCallback) const
{
    if (!authorize(actor, security::Operation::InstrutoresRead, errorCallback)) return;
    if (id <= 0) { errorCallback(InstrutorError::InvalidInput); return; }
    repository_.buscarPorId(actor.identity.academiaId, id,
        [callback, errorCallback](const std::optional<models::Instrutor> &instrutor)
        {
            if (instrutor) callback(*instrutor);
            else errorCallback(InstrutorError::NotFound);
        }, databaseError(errorCallback));
}

void InstrutorService::listarPorAcademia(const security::ValidatedAuthContext &actor,
    ListCallback callback, ErrorCallback errorCallback) const
{
    if (!authorize(actor, security::Operation::InstrutoresRead, errorCallback)) return;
    repository_.listarPorAcademia(actor.identity.academiaId, std::move(callback), databaseError(errorCallback));
}
}
