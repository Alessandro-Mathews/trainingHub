#include "traininghub/controllers/PlanoController.h"
#include "traininghub/services/PlanoService.h"
#include "traininghub/security/AuthorizationGuard.h"

#include <drogon/drogon.h>
#include <charconv>
#include <memory>
#include <utility>

namespace traininghub::controllers
{
namespace
{
using HttpCallback = std::function<void(const drogon::HttpResponsePtr &)>;

services::PlanoService service()
{
    return services::PlanoService{repositories::PlanoRepository{drogon::app().getDbClient("default")}};
}

drogon::HttpResponsePtr message(drogon::HttpStatusCode status, const std::string &text)
{
    Json::Value json;
    json["erro"] = text;
    auto response = drogon::HttpResponse::newHttpJsonResponse(json);
    response->setStatusCode(status);
    return response;
}

HttpCallback noStore(HttpCallback callback)
{
    return [callback = std::move(callback)](const drogon::HttpResponsePtr &response)
    {
        response->addHeader("Cache-Control", "no-store");
        callback(response);
    };
}

services::PlanoService::ErrorCallback onError(HttpCallback callback)
{
    return [callback](services::PlanoError error)
    {
        using services::PlanoError;
        switch (error)
        {
        case PlanoError::InvalidInput:
            callback(message(drogon::k400BadRequest, "Informe nome nao vazio, valor em centavos nao negativo e duracao positiva em dias.")); break;
        case PlanoError::Unauthorized:
            callback(security::AuthorizationGuard::error(drogon::k401Unauthorized)); break;
        case PlanoError::Forbidden:
            callback(security::AuthorizationGuard::error(drogon::k403Forbidden)); break;
        case PlanoError::NotFound:
            callback(message(drogon::k404NotFound, "Plano nao encontrado na academia.")); break;
        case PlanoError::DuplicateName:
            callback(message(drogon::k409Conflict, "Nome de plano ja cadastrado nesta academia.")); break;
        case PlanoError::RelationshipConflict:
            callback(message(drogon::k409Conflict, "Academia indisponivel para associacao.")); break;
        case PlanoError::Internal:
            callback(message(drogon::k500InternalServerError, "Erro interno ao acessar planos.")); break;
        }
    };
}

Json::Value toJson(const models::Plano &plano)
{
    Json::Value json;
    json["id"] = Json::Int64(plano.id);
    json["academia_id"] = Json::Int64(plano.academiaId);
    json["nome"] = plano.nome;
    json["descricao"] = plano.descricao ? Json::Value(*plano.descricao) : Json::Value(Json::nullValue);
    json["valor_centavos"] = Json::Int64(plano.valorCentavos);
    json["duracao_dias"] = Json::Int64(plano.duracaoDias);
    json["ativo"] = plano.ativo;
    json["criado_em"] = plano.criadoEm;
    return json;
}

std::optional<std::int64_t> positiveId(const std::string &text)
{
    std::int64_t id{};
    const auto [end, error] = std::from_chars(text.data(), text.data() + text.size(), id);
    if (error != std::errc{} || end != text.data() + text.size() || id <= 0) return std::nullopt;
    return id;
}

std::optional<Json::Value> strictJson(const drogon::HttpRequestPtr &req)
{
    if (req->contentType() != drogon::CT_APPLICATION_JSON || req->body().empty()) return std::nullopt;
    Json::CharReaderBuilder builder;
    Json::CharReaderBuilder::ecma404Mode(&builder.settings_);
    builder["collectComments"] = false;
    builder["stackLimit"] = static_cast<Json::UInt>(drogon::app().getJsonParserStackLimit());
    const std::unique_ptr<Json::CharReader> reader(builder.newCharReader());
    Json::Value json;
    Json::String errors;
    const auto body = req->body();
    try
    {
        if (!reader->parse(body.data(), body.data() + body.size(), &json, &errors)) return std::nullopt;
    }
    catch (const Json::Exception &)
    {
        return std::nullopt;
    }
    return json;
}

bool integer(const Json::Value &value)
{
    return (value.type() == Json::intValue || value.type() == Json::uintValue) && value.isInt64();
}

std::optional<services::DadosPlano> readDados(const drogon::HttpRequestPtr &req)
{
    const auto json = strictJson(req);
    if (!req->query().empty() || !json || !json->isObject()
        || json->size() != (json->isMember("descricao") ? 4U : 3U)
        || !json->isMember("nome") || !(*json)["nome"].isString()
        || !json->isMember("valor_centavos") || !integer((*json)["valor_centavos"])
        || !json->isMember("duracao_dias") || !integer((*json)["duracao_dias"])
        || (json->isMember("descricao") && !(*json)["descricao"].isNull() && !(*json)["descricao"].isString()))
        return std::nullopt;
    services::DadosPlano dados;
    dados.nome = (*json)["nome"].asString();
    if (json->isMember("descricao") && !(*json)["descricao"].isNull())
        dados.descricao = (*json)["descricao"].asString();
    dados.valorCentavos = (*json)["valor_centavos"].asInt64();
    dados.duracaoDias = (*json)["duracao_dias"].asInt64();
    return dados;
}

bool readContract(const drogon::HttpRequestPtr &req, const HttpCallback &callback)
{
    if (!req->query().empty() || !req->body().empty())
    {
        callback(message(drogon::k400BadRequest, "Consulta nao aceita query ou body."));
        return false;
    }
    return true;
}
}

void PlanoController::criar(const drogon::HttpRequestPtr &req, HttpCallback &&callback)
{
    callback = noStore(std::move(callback));
    if (!security::AuthorizationGuard::require(req, security::Operation::PlanosManage, callback)) return;
    const auto dados = readDados(req);
    if (!dados) { callback(message(drogon::k400BadRequest, "Informe somente os campos editaveis do plano em JSON, sem query.")); return; }
    service().criar(security::AuthorizationGuard::context(req), *dados,
        [callback](const models::Plano &plano)
        {
            auto response = drogon::HttpResponse::newHttpJsonResponse(toJson(plano));
            response->setStatusCode(drogon::k201Created);
            callback(response);
        }, onError(callback));
}

void PlanoController::listar(const drogon::HttpRequestPtr &req, HttpCallback &&callback)
{
    callback = noStore(std::move(callback));
    if (!security::AuthorizationGuard::require(req, security::Operation::PlanosRead, callback)) return;
    if (!readContract(req, callback)) return;
    service().listarPorAcademia(security::AuthorizationGuard::context(req),
        [callback](const std::vector<models::Plano> &planos)
        {
            Json::Value json(Json::arrayValue);
            for (const auto &plano : planos) json.append(toJson(plano));
            callback(drogon::HttpResponse::newHttpJsonResponse(json));
        }, onError(callback));
}

void PlanoController::buscarPorId(const drogon::HttpRequestPtr &req, HttpCallback &&callback,
    const std::string &textId)
{
    callback = noStore(std::move(callback));
    if (!security::AuthorizationGuard::require(req, security::Operation::PlanosRead, callback)) return;
    if (!readContract(req, callback)) return;
    const auto id = positiveId(textId);
    if (!id) { callback(message(drogon::k400BadRequest, "Informe id positivo de 64 bits.")); return; }
    service().buscarPorId(security::AuthorizationGuard::context(req), *id,
        [callback](const models::Plano &plano) { callback(drogon::HttpResponse::newHttpJsonResponse(toJson(plano))); }, onError(callback));
}

void PlanoController::atualizar(const drogon::HttpRequestPtr &req, HttpCallback &&callback,
    const std::string &textId)
{
    callback = noStore(std::move(callback));
    if (!security::AuthorizationGuard::require(req, security::Operation::PlanosManage, callback)) return;
    const auto id = positiveId(textId);
    const auto dados = readDados(req);
    if (!id || !dados) { callback(message(drogon::k400BadRequest, "Informe id e campos editaveis validos em JSON, sem query.")); return; }
    service().atualizar(security::AuthorizationGuard::context(req), *id, *dados,
        [callback](const models::Plano &plano) { callback(drogon::HttpResponse::newHttpJsonResponse(toJson(plano))); }, onError(callback));
}

void PlanoController::atualizarStatus(const drogon::HttpRequestPtr &req, HttpCallback &&callback,
    const std::string &textId)
{
    callback = noStore(std::move(callback));
    if (!security::AuthorizationGuard::require(req, security::Operation::PlanosManage, callback)) return;
    const auto id = positiveId(textId);
    const auto json = strictJson(req);
    if (!id || !req->query().empty() || !json || !json->isObject() || json->size() != 1
        || !json->isMember("ativo") || !(*json)["ativo"].isBool())
    { callback(message(drogon::k400BadRequest, "Informe id positivo e somente ativo boolean em JSON, sem query.")); return; }
    service().atualizarStatus(security::AuthorizationGuard::context(req), *id, (*json)["ativo"].asBool(),
        [callback](const models::Plano &plano) { callback(drogon::HttpResponse::newHttpJsonResponse(toJson(plano))); }, onError(callback));
}
}
