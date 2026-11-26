#include "traininghub/services/PlanoService.h"
#include "traininghub/security/AuthorizationService.h"

#include <utility>

namespace traininghub::services
{
namespace
{
bool authorize(const security::ValidatedAuthContext &actor, security::Operation operation,
    const PlanoService::ErrorCallback &errorCallback)
{
    if (actor.identity.userId <= 0 || actor.identity.academiaId <= 0 || actor.identity.perfilId <= 0)
    { errorCallback(PlanoError::Unauthorized); return false; }
    if (!security::AuthorizationService::allows(actor.role, operation))
    { errorCallback(PlanoError::Forbidden); return false; }
    return true;
}

bool valid(const DadosPlano &dados)
{
    return dados.nome.find_first_not_of(" \t\r\n\f\v") != std::string::npos
        && dados.valorCentavos >= 0 && dados.duracaoDias > 0;
}

repositories::PlanoRepository::ErrorCallback databaseError(PlanoService::ErrorCallback callback)
{
    return [callback = std::move(callback)](const drogon::orm::DrogonDbException &error)
    {
        if (dynamic_cast<const drogon::orm::UniqueViolation *>(&error))
            callback(PlanoError::DuplicateName);
        else if (dynamic_cast<const drogon::orm::ForeignKeyViolation *>(&error))
            callback(PlanoError::RelationshipConflict);
        else
            callback(PlanoError::Internal);
    };
}

auto found(PlanoService::FindCallback callback, PlanoService::ErrorCallback errorCallback)
{
    return [callback = std::move(callback), errorCallback](const std::optional<models::Plano> &plano)
    {
        if (plano) callback(*plano);
        else errorCallback(PlanoError::NotFound);
    };
}
}

PlanoService::PlanoService(repositories::PlanoRepository repository) : repository_(std::move(repository)) {}

void PlanoService::criar(const security::ValidatedAuthContext &actor, const DadosPlano &dados,
    FindCallback callback, ErrorCallback errorCallback) const
{
    if (!authorize(actor, security::Operation::PlanosManage, errorCallback)) return;
    if (!valid(dados)) { errorCallback(PlanoError::InvalidInput); return; }
    repository_.criar(actor.identity.academiaId, dados.nome, dados.descricao, dados.valorCentavos,
        dados.duracaoDias,
        [callback, errorCallback](const std::optional<models::Plano> &plano)
        {
            if (plano) callback(*plano);
            else errorCallback(PlanoError::Internal);
        }, databaseError(errorCallback));
}

void PlanoService::listarPorAcademia(const security::ValidatedAuthContext &actor,
    ListCallback callback, ErrorCallback errorCallback) const
{
    if (!authorize(actor, security::Operation::PlanosRead, errorCallback)) return;
    repository_.listarPorAcademia(actor.identity.academiaId, std::move(callback), databaseError(errorCallback));
}

void PlanoService::buscarPorId(const security::ValidatedAuthContext &actor, std::int64_t id,
    FindCallback callback, ErrorCallback errorCallback) const
{
    if (!authorize(actor, security::Operation::PlanosRead, errorCallback)) return;
    if (id <= 0) { errorCallback(PlanoError::InvalidInput); return; }
    repository_.buscarPorId(actor.identity.academiaId, id, found(std::move(callback), errorCallback),
        databaseError(errorCallback));
}

void PlanoService::atualizar(const security::ValidatedAuthContext &actor, std::int64_t id,
    const DadosPlano &dados, FindCallback callback, ErrorCallback errorCallback) const
{
    if (!authorize(actor, security::Operation::PlanosManage, errorCallback)) return;
    if (id <= 0 || !valid(dados)) { errorCallback(PlanoError::InvalidInput); return; }
    repository_.atualizar(actor.identity.academiaId, id, dados.nome, dados.descricao, dados.valorCentavos,
        dados.duracaoDias, found(std::move(callback), errorCallback), databaseError(errorCallback));
}

void PlanoService::atualizarStatus(const security::ValidatedAuthContext &actor, std::int64_t id,
    bool ativo, FindCallback callback, ErrorCallback errorCallback) const
{
    if (!authorize(actor, security::Operation::PlanosManage, errorCallback)) return;
    if (id <= 0) { errorCallback(PlanoError::InvalidInput); return; }
    repository_.atualizarStatus(actor.identity.academiaId, id, ativo,
        found(std::move(callback), errorCallback), databaseError(errorCallback));
}
}
