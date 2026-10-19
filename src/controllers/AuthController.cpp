#include "traininghub/controllers/AuthController.h"
#include "traininghub/security/SessionManager.h"
#include "traininghub/services/AuthService.h"

#include <drogon/drogon.h>

namespace traininghub::controllers
{
namespace
{
drogon::HttpResponsePtr messageResponse(drogon::HttpStatusCode status,
                                       const std::string &message)
{
    Json::Value json;
    json["message"] = message;
    auto response = drogon::HttpResponse::newHttpJsonResponse(json);
    response->setStatusCode(status);
    response->addHeader("Cache-Control", "no-store");
    return response;
}

drogon::HttpResponsePtr contextResponse(const security::AuthSession &user)
{
    Json::Value json;
    json["userId"] = Json::Int64(user.userId);
    json["academiaId"] = Json::Int64(user.academiaId);
    json["perfilId"] = Json::Int64(user.perfilId);
    auto response = drogon::HttpResponse::newHttpJsonResponse(json);
    response->addHeader("Cache-Control", "no-store");
    return response;
}
}

void AuthController::login(
    const drogon::HttpRequestPtr &req,
    std::function<void(const drogon::HttpResponsePtr &)> &&callback) const
{
    const auto json = req->getJsonObject();
    if (!json || !json->isObject()
        || ((*json)["academia_id"].type() != Json::intValue
            && (*json)["academia_id"].type() != Json::uintValue)
        || !(*json)["academia_id"].isInt64()
        || (*json)["academia_id"].asInt64() <= 0
        || !(*json)["email"].isString() || (*json)["email"].asString().empty()
        || !(*json)["senha"].isString() || (*json)["senha"].asString().empty())
    {
        callback(messageResponse(drogon::k400BadRequest,
                                 "Informe academia_id, email e senha validos."));
        return;
    }

    const auto session = req->session();
    if (!session)
    {
        callback(messageResponse(drogon::k500InternalServerError,
                                 "Nao foi possivel autenticar."));
        return;
    }

    services::AuthService service{
        repositories::UsuarioRepository{drogon::app().getDbClient("default")}};
    service.authenticate(
        (*json)["academia_id"].asInt64(), (*json)["email"].asString(),
        (*json)["senha"].asString(),
        [session, callback](const std::optional<security::AuthSession> &user)
        {
            if (!user)
            {
                callback(messageResponse(drogon::k401Unauthorized,
                                         "Credenciais invalidas."));
                return;
            }

            if (!security::SessionManager::authenticate(session, *user))
            {
                callback(messageResponse(drogon::k500InternalServerError,
                                         "Nao foi possivel autenticar."));
                return;
            }
            callback(contextResponse(*user));
        },
        [callback]
        {
            LOG_ERROR << "Falha interna ao autenticar usuario.";
            callback(messageResponse(drogon::k500InternalServerError,
                                     "Nao foi possivel autenticar."));
        }
    );
}

void AuthController::me(
    const drogon::HttpRequestPtr &req,
    std::function<void(const drogon::HttpResponsePtr &)> &&callback) const
{
    const auto user = security::SessionManager::getAuthenticatedUser(req->session());
    if (!user)
    {
        callback(messageResponse(drogon::k401Unauthorized,
                                 "Usuario nao autenticado."));
        return;
    }
    callback(contextResponse(*user));
}

void AuthController::logout(
    const drogon::HttpRequestPtr &req,
    std::function<void(const drogon::HttpResponsePtr &)> &&callback) const
{
    security::SessionManager::logout(req->session());
    callback(messageResponse(drogon::k200OK, "Sessao encerrada."));
}

}
