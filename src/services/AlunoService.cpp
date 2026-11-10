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

AlunoService::AlunoService(repositories::AlunoRepository repository,
    repositories::InstrutorRepository instrutores)
    : repository_(std::move(repository)), instrutores_(std::move(instrutores)) {}

void AlunoService::buscarInstrutor(const security::ValidatedAuthContext &actor, std::int64_t alunoId,
    ResponsavelCallback callback, ErrorCallback errorCallback) const
{
    if (!authorize(actor, security::Operation::AlunosInstrutorRead, errorCallback)) return;
    if (alunoId <= 0) { errorCallback(AlunoError::InvalidInput); return; }
    repository_.buscarInstrutor(actor.identity.academiaId, alunoId,
        [callback, errorCallback](const std::optional<repositories::InstrutorResponsavel> &responsavel)
        {
            if (!responsavel) errorCallback(AlunoError::NotFound);
            else if (!responsavel->consistente) errorCallback(AlunoError::InstrutorNotFound);
            else callback(responsavel->instrutorId);
        }, databaseError(errorCallback));
}

void AlunoService::definirInstrutor(const security::ValidatedAuthContext &actor, std::int64_t alunoId,
    std::int64_t instrutorId, ResponsavelCallback callback, ErrorCallback errorCallback) const
{
    if (!authorize(actor, security::Operation::AlunosInstrutorManage, errorCallback)) return;
    if (alunoId <= 0 || instrutorId <= 0) { errorCallback(AlunoError::InvalidInput); return; }
    const auto academiaId = actor.identity.academiaId;
    repository_.buscarPorId(academiaId, alunoId,
        [academiaId, alunoId, instrutorId, callback, errorCallback,
         repository = repository_, instrutores = instrutores_](const std::optional<models::Aluno> &aluno)
        {
            if (!aluno) { errorCallback(AlunoError::NotFound); return; }
            repository.buscarUsuarioParaCriacao(academiaId, aluno->usuario_id,
                [academiaId, alunoId, instrutorId, callback, errorCallback, repository, instrutores]
                (const std::optional<repositories::UsuarioParaAluno> &usuario)
                {
                    if (!usuario) { errorCallback(AlunoError::NotFound); return; }
                    if (!usuario->academiaAtiva) { errorCallback(AlunoError::RelationshipConflict); return; }
                    if (!usuario->usuarioAtivo || !usuario->perfilAtivo || !usuario->perfilNome
                        || security::roleFromName(*usuario->perfilNome) != security::Role::ALUNO)
                    { errorCallback(AlunoError::IneligibleUsuario); return; }
                    instrutores.buscarPorId(academiaId, instrutorId,
                        [academiaId, alunoId, instrutorId, callback, errorCallback, repository,
                         instrutores, perfilAluno = *usuario->perfilNome]
                        (const std::optional<models::Instrutor> &instrutor)
                        {
                            if (!instrutor) { errorCallback(AlunoError::InstrutorNotFound); return; }
                            instrutores.buscarUsuarioParaCriacao(academiaId, instrutor->usuario_id,
                                [academiaId, alunoId, instrutorId, callback, errorCallback, repository, perfilAluno]
                                (const std::optional<repositories::UsuarioParaInstrutor> &usuarioInstrutor)
                                {
                                    if (!usuarioInstrutor) { errorCallback(AlunoError::InstrutorNotFound); return; }
                                    if (!usuarioInstrutor->academiaAtiva)
                                    { errorCallback(AlunoError::RelationshipConflict); return; }
                                    if (!usuarioInstrutor->usuarioAtivo || !usuarioInstrutor->perfilAtivo
                                        || !usuarioInstrutor->perfilNome
                                        || security::roleFromName(*usuarioInstrutor->perfilNome) != security::Role::INSTRUTOR)
                                    { errorCallback(AlunoError::IneligibleInstrutor); return; }
                                    repository.definirInstrutor(academiaId, alunoId, instrutorId,
                                        perfilAluno, *usuarioInstrutor->perfilNome,
                                        [callback, errorCallback]
                                        (const std::optional<repositories::InstrutorResponsavel> &saved)
                                        {
                                            if (saved) callback(saved->instrutorId);
                                            else errorCallback(AlunoError::RelationshipConflict);
                                        }, databaseError(errorCallback));
                                }, databaseError(errorCallback));
                        }, databaseError(errorCallback));
                }, databaseError(errorCallback));
        }, databaseError(errorCallback));
}

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
