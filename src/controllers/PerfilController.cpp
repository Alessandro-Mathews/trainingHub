#include "traininghub/controllers/PerfilController.h"

#include "traininghub/services/PerfilService.h"

#include <drogon/drogon.h>
#include <utility>

namespace traininghub::controllers
{
namespace
{
using HttpCallback = std::function<void(const drogon::HttpResponsePtr &)>;

services::PerfilService service()
{
    return services::PerfilService{
        repositories::PerfilRepository{drogon::app().getDbClient("default")}};
}

drogon::HttpResponsePtr message(drogon::HttpStatusCode status,
                                const std::string &text)
{
    Json::Value json;
    json["erro"] = text;
    auto response = drogon::HttpResponse::newHttpJsonResponse(json);
    response->setStatusCode(status);
    return response;
}

services::PerfilService::ErrorCallback onError(HttpCallback callback)
{
    return [callback = std::move(callback)](services::PerfilError error)
    {
        using services::PerfilError;
        switch (error)
        {
        case PerfilError::InvalidInput:
            callback(message(drogon::k400BadRequest,
                             "Informe id positivo, nome não vazio e ativo igual a 0 ou 1."));
            break;
        case PerfilError::NotFound:
            callback(message(drogon::k404NotFound, "Perfil não encontrado"));
            break;
        case PerfilError::DuplicateName:
            callback(message(drogon::k409Conflict, "Já existe um perfil com esse nome"));
            break;
        case PerfilError::InUse:
            callback(message(drogon::k409Conflict, "Perfil associado a usuário não pode ser excluído"));
            break;
        case PerfilError::Database:
            callback(message(drogon::k500InternalServerError, "Erro interno ao acessar perfis"));
            break;
        }
    };
}

Json::Value toJson(const models::Perfil &perfil)
{
    Json::Value json;
    json["id"] = Json::Int64(perfil.id);
    json["nome"] = perfil.nome;
    json["descricao"] = perfil.descricao ? Json::Value(*perfil.descricao)
                                          : Json::Value(Json::nullValue);
    json["ativo"] = perfil.ativo;
    json["criado_em"] = perfil.criado_em;
    return json;
}

std::optional<models::Perfil> readPerfil(const drogon::HttpRequestPtr &req,
                                        bool fullUpdate)
{
    const auto json = req->getJsonObject();
    if (!json || !json->isObject() || !(*json)["nome"].isString())
        return std::nullopt;
    // PUT replaces every editable field; omission is rejected, never defaulted.
    if (fullUpdate && (!json->isMember("ativo") || !json->isMember("descricao")))
        return std::nullopt;
    if (json->isMember("descricao") && !(*json)["descricao"].isNull()
        && !(*json)["descricao"].isString())
        return std::nullopt;
    if (json->isMember("ativo")
        && (((*json)["ativo"].type() != Json::intValue
             && (*json)["ativo"].type() != Json::uintValue)
            || !(*json)["ativo"].isInt()))
        return std::nullopt;

    models::Perfil perfil;
    perfil.nome = (*json)["nome"].asString();
    if (json->isMember("descricao") && !(*json)["descricao"].isNull())
        perfil.descricao = (*json)["descricao"].asString();
    if (json->isMember("ativo"))
        perfil.ativo = (*json)["ativo"].asInt();
    return perfil;
}

drogon::HttpResponsePtr changed(drogon::HttpStatusCode status,
                                const std::string &text, std::int64_t id)
{
    Json::Value json;
    json["mensagem"] = text;
    json["id"] = Json::Int64(id);
    auto response = drogon::HttpResponse::newHttpJsonResponse(json);
    response->setStatusCode(status);
    return response;
}
}

void PerfilController::listar(
    const drogon::HttpRequestPtr &,
    std::function<void(const drogon::HttpResponsePtr &)> &&callback)
{
    service().listar(
        [callback](const std::vector<models::Perfil> &perfis)
        {
            Json::Value json(Json::arrayValue);
            for (const auto &perfil : perfis)
                json.append(toJson(perfil));
            callback(drogon::HttpResponse::newHttpJsonResponse(json));
        }, onError(callback));
}

void PerfilController::buscarPorId(
    const drogon::HttpRequestPtr &,
    std::function<void(const drogon::HttpResponsePtr &)> &&callback,
    std::int64_t id)
{
    service().buscarPorId(id,
        [callback](const models::Perfil &perfil)
        {
            callback(drogon::HttpResponse::newHttpJsonResponse(toJson(perfil)));
        }, onError(callback));
}

void PerfilController::criar(
    const drogon::HttpRequestPtr &req,
    std::function<void(const drogon::HttpResponsePtr &)> &&callback)
{
    const auto perfil = readPerfil(req, false);
    if (!perfil)
    {
        callback(message(drogon::k400BadRequest,
                         "Informe objeto JSON com nome string, descricao string/null e ativo inteiro."));
        return;
    }
    service().criar(*perfil,
        [callback](std::int64_t id)
        {
            callback(changed(drogon::k201Created, "Perfil criado com sucesso", id));
        }, onError(callback));
}

void PerfilController::atualizar(
    const drogon::HttpRequestPtr &req,
    std::function<void(const drogon::HttpResponsePtr &)> &&callback,
    std::int64_t id)
{
    const auto perfil = readPerfil(req, true);
    if (!perfil)
    {
        callback(message(drogon::k400BadRequest,
                         "PUT exige nome string, descricao string/null e ativo inteiro."));
        return;
    }
    service().atualizar(id, *perfil,
        [callback, id]
        {
            callback(changed(drogon::k200OK, "Perfil atualizado com sucesso", id));
        }, onError(callback));
}

void PerfilController::excluir(
    const drogon::HttpRequestPtr &,
    std::function<void(const drogon::HttpResponsePtr &)> &&callback,
    std::int64_t id)
{
    service().excluir(id,
        [callback, id]
        {
            callback(changed(drogon::k200OK, "Perfil excluído com sucesso", id));
        }, onError(callback));
}

}
