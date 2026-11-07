#include "traininghub/controllers/AlunoController.h"
#include "traininghub/services/AlunoService.h"
#include "traininghub/security/AuthorizationGuard.h"

#include <drogon/drogon.h>
#include <charconv>
#include <memory>
#include <optional>

namespace traininghub::controllers
{
namespace
{
using HttpCallback = std::function<void(const drogon::HttpResponsePtr &)>;

services::AlunoService service()
{
    return services::AlunoService{repositories::AlunoRepository{drogon::app().getDbClient("default")}};
}

drogon::HttpResponsePtr message(drogon::HttpStatusCode status, const std::string &text)
{
    Json::Value json;
    json["erro"] = text;
    auto response = drogon::HttpResponse::newHttpJsonResponse(json);
    response->setStatusCode(status);
    return response;
}

services::AlunoService::ErrorCallback onError(HttpCallback callback)
{
    return [callback](services::AlunoError error)
    {
        using services::AlunoError;
        switch (error)
        {
        case AlunoError::InvalidInput:
            callback(message(drogon::k400BadRequest, "Informe id positivo de 64 bits.")); break;
        case AlunoError::Unauthorized:
            callback(security::AuthorizationGuard::error(drogon::k401Unauthorized)); break;
        case AlunoError::Forbidden:
            callback(security::AuthorizationGuard::error(drogon::k403Forbidden)); break;
        case AlunoError::UsuarioNotFound:
            callback(message(drogon::k404NotFound, "Usuario nao encontrado na academia.")); break;
        case AlunoError::IneligibleUsuario:
            callback(message(drogon::k400BadRequest, "Usuario deve estar ativo e possuir perfil Aluno ativo.")); break;
        case AlunoError::NotFound:
            callback(message(drogon::k404NotFound, "Aluno nao encontrado na academia.")); break;
        case AlunoError::AlreadyExists:
            callback(message(drogon::k409Conflict, "Usuario ja possui Aluno.")); break;
        case AlunoError::RelationshipConflict:
            callback(message(drogon::k409Conflict, "Relacionamento indisponivel para criar Aluno.")); break;
        case AlunoError::Internal:
            callback(message(drogon::k500InternalServerError, "Erro interno ao acessar alunos.")); break;
        }
    };
}

Json::Value toJson(const models::Aluno &aluno)
{
    Json::Value json;
    json["id"] = Json::Int64(aluno.id);
    json["usuario_id"] = Json::Int64(aluno.usuario_id);
    json["criado_em"] = aluno.criado_em;
    return json;
}

std::optional<std::int64_t> positiveId(const std::string &text)
{
    std::int64_t id{};
    const auto [end, error] = std::from_chars(text.data(), text.data() + text.size(), id);
    if (error != std::errc{} || end != text.data() + text.size() || id <= 0)
        return std::nullopt;
    return id;
}

std::optional<Json::Value> strictJson(const drogon::HttpRequestPtr &req)
{
    if (req->contentType() != drogon::CT_APPLICATION_JSON
        && req->getHeader("content-type").find("application/json") == std::string::npos)
        return std::nullopt;
    const auto body = req->body();
    if (body.empty()) return std::nullopt;

    Json::CharReaderBuilder builder;
    Json::CharReaderBuilder::ecma404Mode(&builder.settings_);
    builder["collectComments"] = false;
    builder["stackLimit"] = static_cast<Json::UInt>(drogon::app().getJsonParserStackLimit());
    const std::unique_ptr<Json::CharReader> reader(builder.newCharReader());
    Json::Value json;
    Json::String errors;
    try
    {
        if (!reader->parse(body.data(), body.data() + body.size(), &json, &errors))
            return std::nullopt;
    }
    catch (const Json::Exception &)
    {
        return std::nullopt;
    }
    return json;
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

void AlunoController::criar(const drogon::HttpRequestPtr &req, HttpCallback &&callback)
{
    if (!security::AuthorizationGuard::require(req, security::Operation::AlunosCreate, callback)) return;
    const auto json = strictJson(req);
    if (!req->query().empty() || !json || !json->isObject() || json->size() != 1
        || !json->isMember("usuario_id"))
    {
        callback(message(drogon::k400BadRequest, "Informe somente usuario_id no objeto JSON, sem query."));
        return;
    }
    const auto &id = (*json)["usuario_id"];
    if ((id.type() != Json::intValue && id.type() != Json::uintValue)
        || !id.isInt64() || id.asInt64() <= 0)
    {
        callback(message(drogon::k400BadRequest, "Informe usuario_id inteiro positivo de 64 bits."));
        return;
    }
    service().criar(security::AuthorizationGuard::context(req), id.asInt64(),
        [callback](const models::Aluno &aluno)
        {
            auto response = drogon::HttpResponse::newHttpJsonResponse(toJson(aluno));
            response->setStatusCode(drogon::k201Created);
            callback(response);
        }, onError(callback));
}

void AlunoController::listar(const drogon::HttpRequestPtr &req, HttpCallback &&callback)
{
    if (!security::AuthorizationGuard::require(req, security::Operation::AlunosRead, callback)) return;
    if (!readContract(req, callback)) return;
    service().listarPorAcademia(security::AuthorizationGuard::context(req),
        [callback](const std::vector<models::Aluno> &alunos)
        {
            Json::Value json(Json::arrayValue);
            for (const auto &aluno : alunos) json.append(toJson(aluno));
            callback(drogon::HttpResponse::newHttpJsonResponse(json));
        }, onError(callback));
}

void AlunoController::buscarPorId(const drogon::HttpRequestPtr &req, HttpCallback &&callback,
    const std::string &textId)
{
    if (!security::AuthorizationGuard::require(req, security::Operation::AlunosRead, callback)) return;
    if (!readContract(req, callback)) return;
    const auto id = positiveId(textId);
    if (!id) { callback(message(drogon::k400BadRequest, "Informe id positivo de 64 bits.")); return; }
    service().buscarPorId(security::AuthorizationGuard::context(req), *id,
        [callback](const models::Aluno &aluno)
        {
            callback(drogon::HttpResponse::newHttpJsonResponse(toJson(aluno)));
        }, onError(callback));
}
}
