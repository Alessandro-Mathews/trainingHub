#include "traininghub/services/AlunoService.h"
#include "traininghub/security/AuthorizationService.h"

#include <utility>

namespace traininghub::services
{
namespace
{
bool authorize(const security::ValidatedAuthContext &actor, security::Operation operation,
               const AlunoService::ErrorCallback &errorCallback)
{
    if (actor.identity.userId <= 0 || actor.identity.academiaId <= 0 || actor.identity.perfilId <= 0)
    {
        errorCallback(AlunoError::Unauthorized);
        return false;
    }
    if (!security::AuthorizationService::allows(actor.role, operation))
    {
        errorCallback(AlunoError::Forbidden);
        return false;
    }
    return true;
}

repositories::AlunoRepository::ErrorCallback databaseError(AlunoService::ErrorCallback callback)
{
    return [callback = std::move(callback)](const drogon::orm::DrogonDbException &error)
    {
        if (dynamic_cast<const drogon::orm::UniqueViolation *>(&error))
            callback(AlunoError::AlreadyExists);
        else if (dynamic_cast<const drogon::orm::ForeignKeyViolation *>(&error))
            callback(AlunoError::RelationshipConflict);
        else
            callback(AlunoError::Internal);
    };
}
}

AlunoService::AlunoService(repositories::AlunoRepository repository) : repository_(std::move(repository)) {}

void AlunoService::criar(const security::ValidatedAuthContext &actor, std::int64_t usuarioId,
    FindCallback callback, ErrorCallback errorCallback) const
{
    if (!authorize(actor, security::Operation::AlunosCreate, errorCallback)) return;
    if (usuarioId <= 0) { errorCallback(AlunoError::InvalidInput); return; }
    repository_.buscarUsuarioParaCriacao(actor.identity.academiaId, usuarioId,
        [actor, usuarioId, callback, errorCallback, repository = repository_]
        (const std::optional<repositories::UsuarioParaAluno> &usuario)
        {
            if (!usuario) { errorCallback(AlunoError::UsuarioNotFound); return; }
            if (!usuario->academiaAtiva) { errorCallback(AlunoError::RelationshipConflict); return; }
            if (!usuario->usuarioAtivo || !usuario->perfilAtivo || !usuario->perfilNome
                || security::roleFromName(*usuario->perfilNome) != security::Role::ALUNO)
            {
                errorCallback(AlunoError::IneligibleUsuario);
                return;
            }
            if (usuario->possuiAluno) { errorCallback(AlunoError::AlreadyExists); return; }
            repository.criar(actor.identity.academiaId, usuarioId, *usuario->perfilNome,
                [callback, errorCallback](const std::optional<models::Aluno> &saved)
                {
                    if (saved) callback(*saved);
                    else errorCallback(AlunoError::RelationshipConflict);
                }, databaseError(errorCallback));
        }, databaseError(errorCallback));
}

void AlunoService::buscarPorId(const security::ValidatedAuthContext &actor, std::int64_t id,
    FindCallback callback, ErrorCallback errorCallback) const
{
    if (!authorize(actor, security::Operation::AlunosRead, errorCallback)) return;
    if (id <= 0) { errorCallback(AlunoError::InvalidInput); return; }
    repository_.buscarPorId(actor.identity.academiaId, id,
        [callback, errorCallback](const std::optional<models::Aluno> &aluno)
        {
            if (aluno) callback(*aluno);
            else errorCallback(AlunoError::NotFound);
        }, databaseError(errorCallback));
}

void AlunoService::listarPorAcademia(const security::ValidatedAuthContext &actor,
    ListCallback callback, ErrorCallback errorCallback) const
{
    if (!authorize(actor, security::Operation::AlunosRead, errorCallback)) return;
    repository_.listarPorAcademia(actor.identity.academiaId, std::move(callback), databaseError(errorCallback));
}
}
