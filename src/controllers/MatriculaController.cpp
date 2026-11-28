#include "traininghub/controllers/MatriculaController.h"
#include "traininghub/services/MatriculaService.h"
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

services::MatriculaService service()
{
    return services::MatriculaService{repositories::MatriculaRepository{drogon::app().getDbClient("default")}};
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

services::MatriculaService::ErrorCallback onError(HttpCallback callback)
{
    return [callback](services::MatriculaError error)
    {
        using services::MatriculaError;
        switch (error)
        {
        case MatriculaError::InvalidInput:
            callback(message(drogon::k400BadRequest, "Informe IDs inteiros positivos de 64 bits.")); break;
        case MatriculaError::Unauthorized:
            callback(security::AuthorizationGuard::error(drogon::k401Unauthorized)); break;
        case MatriculaError::Forbidden:
            callback(security::AuthorizationGuard::error(drogon::k403Forbidden)); break;
        case MatriculaError::ResourcesNotFound:
            callback(message(drogon::k404NotFound, "Aluno ou plano nao encontrado na academia.")); break;
        case MatriculaError::NotFound:
            callback(message(drogon::k404NotFound, "Matricula nao encontrada na academia.")); break;
        case MatriculaError::AlunoNotFound:
            callback(message(drogon::k404NotFound, "Aluno nao encontrado na academia.")); break;
        case MatriculaError::IneligibleAluno:
            callback(message(drogon::k400BadRequest, "Aluno deve possuir Usuario ativo e Perfil Aluno ativo.")); break;
        case MatriculaError::InactivePlano:
            callback(message(drogon::k400BadRequest, "Plano deve estar ativo para nova matricula.")); break;
        case MatriculaError::InvalidValidity:
            callback(message(drogon::k400BadRequest, "Duracao do plano nao permite calcular vigencia valida.")); break;
        case MatriculaError::RelationshipConflict:
            callback(message(drogon::k409Conflict, "Relacionamento indisponivel para criar matricula.")); break;
        case MatriculaError::LifecycleConflict:
            callback(message(drogon::k409Conflict, "Matricula deve estar ativa para cancelamento.")); break;
        case MatriculaError::Internal:
            callback(message(drogon::k500InternalServerError, "Erro interno ao acessar matriculas.")); break;
        }
    };
}

Json::Value toJson(const services::MatriculaComSituacao &result)
{
    const auto &value = result.matricula;
    Json::Value json;
    json["id"] = Json::Int64(value.id);
    json["academia_id"] = Json::Int64(value.academiaId);
    json["aluno_id"] = Json::Int64(value.alunoId);
    json["plano_id"] = Json::Int64(value.planoId);
    json["nome_plano_contratado"] = value.nomePlanoContratado;
    json["valor_contratado_centavos"] = Json::Int64(value.valorContratadoCentavos);
    json["duracao_contratada_dias"] = Json::Int64(value.duracaoContratadaDias);
    json["data_inicio"] = value.dataInicio;
    json["data_fim"] = value.dataFim;
    json["criado_em"] = value.criadoEm;
    json["cancelado_em"] = value.canceladoEm ? Json::Value(*value.canceladoEm) : Json::Value(Json::nullValue);
    switch (result.situacao)
    {
    case services::SituacaoMatricula::Ativa: json["situacao"] = "ATIVA"; break;
    case services::SituacaoMatricula::Inativa: json["situacao"] = "INATIVA"; break;
    case services::SituacaoMatricula::Cancelada: json["situacao"] = "CANCELADA"; break;
    }
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
    builder["rejectDupKeys"] = true;
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

bool positiveInteger(const Json::Value &value)
{
    return (value.type() == Json::intValue || value.type() == Json::uintValue)
        && value.isInt64() && value.asInt64() > 0;
}

bool readContract(const drogon::HttpRequestPtr &req, const HttpCallback &callback)
{
    if (!req->query().empty() || !req->body().empty())
    { callback(message(drogon::k400BadRequest, "Consulta nao aceita query ou body.")); return false; }
    return true;
}

auto listResponse(HttpCallback callback)
{
    return [callback](const std::vector<services::MatriculaComSituacao> &values)
    {
        Json::Value json(Json::arrayValue);
        for (const auto &value : values) json.append(toJson(value));
        callback(drogon::HttpResponse::newHttpJsonResponse(json));
    };
}
}

void MatriculaController::criar(const drogon::HttpRequestPtr &req, HttpCallback &&callback)
{
    callback = noStore(std::move(callback));
    if (!security::AuthorizationGuard::require(req, security::Operation::MatriculasManage, callback)) return;
    const auto json = strictJson(req);
    if (!req->query().empty() || !json || !json->isObject() || json->size() != 2
        || !json->isMember("aluno_id") || !json->isMember("plano_id")
        || !positiveInteger((*json)["aluno_id"]) || !positiveInteger((*json)["plano_id"]))
    { callback(message(drogon::k400BadRequest, "Informe somente aluno_id e plano_id inteiros positivos em JSON, sem query.")); return; }
    service().criar(security::AuthorizationGuard::context(req),
        {(*json)["aluno_id"].asInt64(), (*json)["plano_id"].asInt64()},
        [callback](const services::MatriculaComSituacao &value)
        {
            auto response = drogon::HttpResponse::newHttpJsonResponse(toJson(value));
            response->setStatusCode(drogon::k201Created);
            callback(response);
        }, onError(callback));
}

void MatriculaController::listar(const drogon::HttpRequestPtr &req, HttpCallback &&callback)
{
    callback = noStore(std::move(callback));
    if (!security::AuthorizationGuard::require(req, security::Operation::MatriculasRead, callback)) return;
    if (!readContract(req, callback)) return;
    service().listarPorAcademia(security::AuthorizationGuard::context(req), listResponse(callback), onError(callback));
}

void MatriculaController::buscarPorId(const drogon::HttpRequestPtr &req, HttpCallback &&callback,
    const std::string &textId)
{
    callback = noStore(std::move(callback));
    if (!security::AuthorizationGuard::require(req, security::Operation::MatriculasRead, callback)) return;
    if (!readContract(req, callback)) return;
    const auto id = positiveId(textId);
    if (!id) { callback(message(drogon::k400BadRequest, "Informe id positivo de 64 bits.")); return; }
    service().buscarPorId(security::AuthorizationGuard::context(req), *id,
        [callback](const services::MatriculaComSituacao &value) { callback(drogon::HttpResponse::newHttpJsonResponse(toJson(value))); }, onError(callback));
}

void MatriculaController::cancelar(const drogon::HttpRequestPtr &req, HttpCallback &&callback,
    const std::string &textId)
{
    callback = noStore(std::move(callback));
    if (!security::AuthorizationGuard::require(req, security::Operation::MatriculasManage, callback)) return;
    if (!req->query().empty() || !req->body().empty())
    { callback(message(drogon::k400BadRequest, "Cancelamento nao aceita query ou body.")); return; }
    const auto id = positiveId(textId);
    if (!id) { callback(message(drogon::k400BadRequest, "Informe id positivo de 64 bits.")); return; }
    service().cancelar(security::AuthorizationGuard::context(req), *id,
        [callback](const services::MatriculaComSituacao &value)
        { callback(drogon::HttpResponse::newHttpJsonResponse(toJson(value))); }, onError(callback));
}

void MatriculaController::listarPorAluno(const drogon::HttpRequestPtr &req, HttpCallback &&callback,
    const std::string &textId)
{
    callback = noStore(std::move(callback));
    if (!security::AuthorizationGuard::require(req, security::Operation::MatriculasRead, callback)) return;
    if (!readContract(req, callback)) return;
    const auto id = positiveId(textId);
    if (!id) { callback(message(drogon::k400BadRequest, "Informe aluno_id positivo de 64 bits.")); return; }
    service().listarPorAluno(security::AuthorizationGuard::context(req), *id, listResponse(callback), onError(callback));
}
}
