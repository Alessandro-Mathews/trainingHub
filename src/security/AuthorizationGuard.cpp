#include "traininghub/security/AuthorizationGuard.h"

namespace traininghub::security
{
const ValidatedAuthContext &AuthorizationGuard::context(const drogon::HttpRequestPtr &req)
{
    return req->attributes()->get<ValidatedAuthContext>("traininghub.validatedAuth");
}

drogon::HttpResponsePtr AuthorizationGuard::error(drogon::HttpStatusCode status)
{
    Json::Value json;
    json["message"] = status == drogon::k401Unauthorized ? "Usuario nao autenticado."
        : status == drogon::k403Forbidden ? "Acesso negado." : "Erro interno ao autorizar.";
    auto response = drogon::HttpResponse::newHttpJsonResponse(json);
    response->setStatusCode(status);
    response->addHeader("Cache-Control", "no-store");
    return response;
}

bool AuthorizationGuard::require(const drogon::HttpRequestPtr &req, Operation operation,
    const std::function<void(const drogon::HttpResponsePtr &)> &callback)
{
    const auto &user = context(req);
    if (user.identity.userId <= 0)
    {
        callback(error(drogon::k401Unauthorized));
        return false;
    }
    if (!AuthorizationService::allows(user.role, operation))
    {
        callback(error(drogon::k403Forbidden));
        return false;
    }
    return true;
}

bool AuthorizationGuard::tenant(const drogon::HttpRequestPtr &req, std::int64_t academiaId,
    const std::function<void(const drogon::HttpResponsePtr &)> &callback)
{
    if (academiaId != context(req).identity.academiaId)
    {
        callback(error(drogon::k403Forbidden));
        return false;
    }
    return true;
}
}
