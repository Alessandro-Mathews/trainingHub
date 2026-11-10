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
    const auto db = drogon::app().getDbClient("default");
    return services::AlunoService{repositories::AlunoRepository{db}, repositories::InstrutorRepository{db}};
}

drogon::HttpResponsePtr message(drogon::HttpStatusCode status, const std::string &text)
{
    Json::Value json;
    json["erro"] = text;
    auto response = drogon::HttpResponse::newHttpJsonResponse(json);
    response->setStatusCode(status);
    return response;
}

services::AlunoService::ErrorCallback onError(HttpCallback callback, bool vinculo = false)
{
    return [callback, vinculo](services::AlunoError error)
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
            callback(message(drogon::k409Conflict, vinculo ? "Relacionamento indisponivel para definir instrutor."
                : "Relacionamento indisponivel para criar Aluno.")); break;
        case AlunoError::Internal:
            callback(message(drogon::k500InternalServerError, "Erro interno ao acessar alunos.")); break;
        case AlunoError::InstrutorNotFound:
            callback(message(drogon::k404NotFound, "Instrutor nao encontrado na academia.")); break;
        case AlunoError::IneligibleInstrutor:
            callback(message(drogon::k400BadRequest, "Usuario deve estar ativo e possuir perfil Instrutor ativo.")); break;
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

HttpCallback noStore(HttpCallback callback)
{
    return [callback = std::move(callback)](const drogon::HttpResponsePtr &response)
    {
        response->addHeader("Cache-Control", "no-store");
        callback(response);
    };
}

drogon::HttpResponsePtr responsavelJson(const std::optional<std::int64_t> &instrutorId)
{
    Json::Value json;
    json["instrutor_id"] = instrutorId ? Json::Value(Json::Int64(*instrutorId)) : Json::Value(Json::nullValue);
    return drogon::HttpResponse::newHttpJsonResponse(json);
}
}

void AlunoController::buscarInstrutor(const drogon::HttpRequestPtr &req, HttpCallback &&callback,
    const std::string &textId)
{
    callback = noStore(std::move(callback));
    if (!security::AuthorizationGuard::require(req, security::Operation::AlunosInstrutorRead, callback)) return;
    if (!readContract(req, callback)) return;
    const auto id = positiveId(textId);
    if (!id) { callback(message(drogon::k400BadRequest, "Informe id positivo de 64 bits.")); return; }
    service().buscarInstrutor(security::AuthorizationGuard::context(req), *id,
        [callback](const std::optional<std::int64_t> &instrutorId) { callback(responsavelJson(instrutorId)); },
        onError(callback, true));
}

void AlunoController::definirInstrutor(const drogon::HttpRequestPtr &req, HttpCallback &&callback,
    const std::string &textId)
{
    callback = noStore(std::move(callback));
    if (!security::AuthorizationGuard::require(req, security::Operation::AlunosInstrutorManage, callback)) return;
    const auto id = positiveId(textId);
    const auto json = strictJson(req);
    if (!id || !req->query().empty() || !json || !json->isObject() || json->size() != 1
        || !json->isMember("instrutor_id"))
    {
        callback(message(drogon::k400BadRequest, "Informe id positivo e somente instrutor_id no objeto JSON, sem query."));
        return;
    }
    const auto &instrutorId = (*json)["instrutor_id"];
    if ((instrutorId.type() != Json::intValue && instrutorId.type() != Json::uintValue)
        || !instrutorId.isInt64() || instrutorId.asInt64() <= 0)
    {
        callback(message(drogon::k400BadRequest, "Informe instrutor_id inteiro positivo de 64 bits."));
        return;
    }
    service().definirInstrutor(security::AuthorizationGuard::context(req), *id, instrutorId.asInt64(),
        [callback](const std::optional<std::int64_t> &saved) { callback(responsavelJson(saved)); },
        onError(callback, true));
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
