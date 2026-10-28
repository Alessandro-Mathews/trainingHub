#include "traininghub/controllers/UsuarioController.h"
#include "traininghub/services/UsuarioService.h"

#include <drogon/drogon.h>
#include <charconv>
#include <optional>
#include <string_view>

namespace traininghub::controllers
{
namespace
{
using HttpCallback = std::function<void(const drogon::HttpResponsePtr &)>;

services::UsuarioService service()
{
    const auto db = drogon::app().getDbClient("default");
    return {repositories::UsuarioRepository{db}, repositories::AcademiaRepository{db},
            repositories::PerfilRepository{db}};
}

drogon::HttpResponsePtr message(drogon::HttpStatusCode status, const std::string &text)
{
    Json::Value json;
    json["erro"] = text;
    auto response = drogon::HttpResponse::newHttpJsonResponse(json);
    response->setStatusCode(status);
    return response;
}

services::UsuarioService::ErrorCallback onError(HttpCallback callback)
{
    return [callback](services::UsuarioError error)
    {
        using services::UsuarioError;
        switch (error)
        {
        case UsuarioError::InvalidInput:
            callback(message(drogon::k400BadRequest, "Informe IDs positivos, nome, email e senha validos.")); break;
        case UsuarioError::NotFound:
            callback(message(drogon::k404NotFound, "Usuario nao encontrado na academia.")); break;
        case UsuarioError::AcademiaNotFound:
            callback(message(drogon::k404NotFound, "Academia nao encontrada.")); break;
        case UsuarioError::PerfilNotFound:
            callback(message(drogon::k404NotFound, "Perfil nao encontrado.")); break;
        case UsuarioError::AcademiaInactive:
            callback(message(drogon::k400BadRequest, "Academia inativa.")); break;
        case UsuarioError::PerfilInactive:
            callback(message(drogon::k400BadRequest, "Perfil inativo.")); break;
        case UsuarioError::DuplicateEmail:
            callback(message(drogon::k409Conflict, "Email ja cadastrado nesta academia.")); break;
        case UsuarioError::RelationshipConflict:
            callback(message(drogon::k409Conflict, "Academia ou perfil indisponivel para associacao.")); break;
        case UsuarioError::Internal:
            callback(message(drogon::k500InternalServerError, "Erro interno ao acessar usuarios.")); break;
        }
    };
}

Json::Value toJson(const models::Usuario &usuario)
{
    Json::Value json;
    json["id"] = Json::Int64(usuario.id);
    json["academia_id"] = Json::Int64(usuario.academia_id);
    json["perfil_id"] = Json::Int64(usuario.perfil_id);
    json["nome"] = usuario.nome;
    json["email"] = usuario.email;
    json["ativo"] = usuario.ativo;
    json["criado_em"] = usuario.criado_em;
    return json;
}

bool positiveJsonId(const Json::Value &value)
{
    return (value.type() == Json::intValue || value.type() == Json::uintValue)
        && value.isInt64() && value.asInt64() > 0;
}

std::optional<std::int64_t> positiveId(const std::string &text)
{
    std::int64_t id{};
    const auto [end, error] = std::from_chars(text.data(), text.data() + text.size(), id);
    if (error != std::errc{} || end != text.data() + text.size() || id <= 0)
        return std::nullopt;
    return id;
}

std::optional<std::int64_t> academiaIdFromQuery(const drogon::HttpRequestPtr &req)
{
    // query() excludes the body; getParameter() also parses form body data.
    std::string_view query{req->query()};
    std::optional<std::int64_t> id;
    while (!query.empty())
    {
        const auto separator = query.find('&');
        const auto parameter = query.substr(0, separator);
        const auto equals = parameter.find('=');
        if (equals != std::string_view::npos
            && drogon::utils::urlDecode(parameter.substr(0, equals)) == "academia_id")
            id = positiveId(drogon::utils::urlDecode(parameter.substr(equals + 1)));
        if (separator == std::string_view::npos)
            break;
        query.remove_prefix(separator + 1);
    }
    return id;
}
}

void UsuarioController::criar(const drogon::HttpRequestPtr &req, HttpCallback &&callback)
{
    const auto json = req->getJsonObject();
    if (!json || !json->isObject() || !positiveJsonId((*json)["academia_id"])
        || !positiveJsonId((*json)["perfil_id"]) || !(*json)["nome"].isString()
        || !(*json)["email"].isString() || !(*json)["senha"].isString()
        || json->isMember("senha_hash"))
    {
        callback(message(drogon::k400BadRequest,
                         "Informe objeto JSON com academia_id, perfil_id, nome, email e senha; senha_hash nao e aceito."));
        return;
    }
    services::NovoUsuario input{(*json)["academia_id"].asInt64(), (*json)["perfil_id"].asInt64(),
                                (*json)["nome"].asString(), (*json)["email"].asString(),
                                (*json)["senha"].asString()};
    service().criar(input,
        [callback](const models::Usuario &usuario)
        {
            auto response = drogon::HttpResponse::newHttpJsonResponse(toJson(usuario));
            response->setStatusCode(drogon::k201Created);
            callback(response);
        }, onError(callback));
}

void UsuarioController::listar(const drogon::HttpRequestPtr &req, HttpCallback &&callback)
{
    const auto academiaId = academiaIdFromQuery(req);
    if (!academiaId)
    {
        callback(message(drogon::k400BadRequest, "Informe academia_id positivo de 64 bits na query."));
        return;
    }
    service().listarPorAcademia(*academiaId,
        [callback](const std::vector<models::Usuario> &usuarios)
        {
            Json::Value json(Json::arrayValue);
            for (const auto &usuario : usuarios) json.append(toJson(usuario));
            callback(drogon::HttpResponse::newHttpJsonResponse(json));
        }, onError(callback));
}

void UsuarioController::buscarPorId(const drogon::HttpRequestPtr &req, HttpCallback &&callback,
                                    const std::string &textId)
{
    const auto academiaId = academiaIdFromQuery(req);
    const auto id = positiveId(textId);
    if (!academiaId || !id)
    {
        callback(message(drogon::k400BadRequest, "Informe id e academia_id positivos de 64 bits."));
        return;
    }
    service().buscarPorId(*academiaId, *id,
        [callback](const models::Usuario &usuario)
        {
            callback(drogon::HttpResponse::newHttpJsonResponse(toJson(usuario)));
        }, onError(callback));
}
}
