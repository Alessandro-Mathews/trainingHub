#include "traininghub/services/MatriculaService.h"
#include "traininghub/security/AuthorizationService.h"

#include <utility>

namespace traininghub::services
{
namespace
{
MatriculaComSituacao classificar(const repositories::MatriculaTemporal &value)
{
    return {value.matricula, MatriculaService::determinarSituacao(value.matricula, value.agoraUtc)};
}

auto classificarLista(MatriculaService::ListCallback callback)
{
    return [callback = std::move(callback)](const std::vector<repositories::MatriculaTemporal> &values)
    {
        std::vector<MatriculaComSituacao> classified;
        classified.reserve(values.size());
        for (const auto &value : values) classified.push_back(classificar(value));
        callback(classified);
    };
}

bool authorize(const security::ValidatedAuthContext &actor, security::Operation operation,
    const MatriculaService::ErrorCallback &errorCallback)
{
    if (actor.identity.userId <= 0 || actor.identity.academiaId <= 0 || actor.identity.perfilId <= 0)
    { errorCallback(MatriculaError::Unauthorized); return false; }
    if (!security::AuthorizationService::allows(actor.role, operation))
    { errorCallback(MatriculaError::Forbidden); return false; }
    return true;
}

repositories::MatriculaRepository::ErrorCallback databaseError(MatriculaService::ErrorCallback callback)
{
    return [callback = std::move(callback)](const drogon::orm::DrogonDbException &error)
    {
        if (dynamic_cast<const drogon::orm::ForeignKeyViolation *>(&error))
            callback(MatriculaError::RelationshipConflict);
        else
            callback(MatriculaError::Internal);
    };
}
}

MatriculaService::MatriculaService(repositories::MatriculaRepository repository)
    : repository_(std::move(repository)) {}

SituacaoMatricula MatriculaService::determinarSituacao(const models::Matricula &matricula,
    const std::string &agoraUtc)
{
    if (matricula.canceladoEm) return SituacaoMatricula::Cancelada;
    if (matricula.dataInicio <= agoraUtc && agoraUtc < matricula.dataFim) return SituacaoMatricula::Ativa;
    return SituacaoMatricula::Inativa;
}

void MatriculaService::cancelar(const security::ValidatedAuthContext &actor, std::int64_t id,
    FindCallback callback, ErrorCallback errorCallback) const
{
    if (!authorize(actor, security::Operation::MatriculasManage, errorCallback)) return;
    if (id <= 0) { errorCallback(MatriculaError::InvalidInput); return; }
    const auto academiaId = actor.identity.academiaId;
    repository_.buscarPorId(academiaId, id,
        [repository = repository_, academiaId, id, callback, errorCallback]
        (const std::optional<repositories::MatriculaTemporal> &value)
        {
            if (!value) { errorCallback(MatriculaError::NotFound); return; }
            if (determinarSituacao(value->matricula, value->agoraUtc) != SituacaoMatricula::Ativa)
            { errorCallback(MatriculaError::LifecycleConflict); return; }
            repository.cancelar(academiaId, id,
                [callback, errorCallback](const std::optional<repositories::MatriculaTemporal> &updated)
                {
                    if (updated) callback(classificar(*updated));
                    else errorCallback(MatriculaError::LifecycleConflict);
                }, databaseError(errorCallback));
        }, databaseError(errorCallback));
}

void MatriculaService::criar(const security::ValidatedAuthContext &actor, const NovaMatricula &input,
    FindCallback callback, ErrorCallback errorCallback) const
{
    if (!authorize(actor, security::Operation::MatriculasManage, errorCallback)) return;
    if (input.alunoId <= 0 || input.planoId <= 0) { errorCallback(MatriculaError::InvalidInput); return; }
    const auto academiaId = actor.identity.academiaId;
    repository_.verificarCriacao(academiaId, input.alunoId, input.planoId,
        [repository = repository_, academiaId, input, callback, errorCallback]
        (const repositories::ContextoCriacaoMatricula &context)
        {
            if (!context.alunoExiste || !context.planoExiste)
            { errorCallback(MatriculaError::ResourcesNotFound); return; }
            if (!context.academiaAtiva) { errorCallback(MatriculaError::RelationshipConflict); return; }
            if (!context.usuarioAtivo || !context.perfilAtivo || !context.perfilNome
                || security::roleFromName(*context.perfilNome) != security::Role::ALUNO)
            { errorCallback(MatriculaError::IneligibleAluno); return; }
            if (!context.planoAtivo) { errorCallback(MatriculaError::InactivePlano); return; }
            if (!context.vigenciaValida) { errorCallback(MatriculaError::InvalidValidity); return; }
            repository.criar(academiaId, input.alunoId, input.planoId, *context.perfilNome,
                [callback, errorCallback](const std::optional<repositories::MatriculaTemporal> &value)
                {
                    if (value) callback(classificar(*value));
                    else errorCallback(MatriculaError::RelationshipConflict);
                }, databaseError(errorCallback));
        }, databaseError(errorCallback));
}

void MatriculaService::listarPorAcademia(const security::ValidatedAuthContext &actor,
    ListCallback callback, ErrorCallback errorCallback) const
{
    if (!authorize(actor, security::Operation::MatriculasRead, errorCallback)) return;
    repository_.listarPorAcademia(actor.identity.academiaId, classificarLista(std::move(callback)), databaseError(errorCallback));
}

void MatriculaService::buscarPorId(const security::ValidatedAuthContext &actor, std::int64_t id,
    FindCallback callback, ErrorCallback errorCallback) const
{
    if (!authorize(actor, security::Operation::MatriculasRead, errorCallback)) return;
    if (id <= 0) { errorCallback(MatriculaError::InvalidInput); return; }
    repository_.buscarPorId(actor.identity.academiaId, id,
        [callback, errorCallback](const std::optional<repositories::MatriculaTemporal> &value)
        {
            if (value) callback(classificar(*value));
            else errorCallback(MatriculaError::NotFound);
        }, databaseError(errorCallback));
}

void MatriculaService::listarPorAluno(const security::ValidatedAuthContext &actor, std::int64_t alunoId,
    ListCallback callback, ErrorCallback errorCallback) const
{
    if (!authorize(actor, security::Operation::MatriculasRead, errorCallback)) return;
    if (alunoId <= 0) { errorCallback(MatriculaError::InvalidInput); return; }
    repository_.listarPorAluno(actor.identity.academiaId, alunoId,
        [callback, errorCallback](const std::optional<std::vector<repositories::MatriculaTemporal>> &values)
        {
            if (values) classificarLista(callback)(*values);
            else errorCallback(MatriculaError::AlunoNotFound);
        }, databaseError(errorCallback));
}
}
