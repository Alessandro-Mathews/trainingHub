#include "traininghub/controllers/PerfilController.h"

#include "traininghub/services/PerfilService.h"

namespace traininghub::controllers
{

void PerfilController::listar(
    const drogon::HttpRequestPtr& req,
    std::function<void(const drogon::HttpResponsePtr&)>&& callback)
{
    services::PerfilService service;

    auto perfis = service.listar();

    Json::Value resposta(Json::arrayValue);

    for (const auto& perfil : perfis)
    {
        Json::Value item;

        item["id"] = static_cast<Json::Int64>(perfil.id);
        item["nome"] = perfil.nome;
        item["ativo"] = perfil.ativo;
        item["criado_em"] = perfil.criado_em;

        if (perfil.descricao)
        {
            item["descricao"] = *perfil.descricao;
        }
        else
        {
            item["descricao"] = Json::nullValue;
        }

        resposta.append(item);
    }

    auto response =
        drogon::HttpResponse::newHttpJsonResponse(resposta);

    callback(response);
}


void PerfilController::buscarPorId(
    const drogon::HttpRequestPtr& req,
    std::function<void(const drogon::HttpResponsePtr&)>&& callback,
    std::int64_t id)
{
    services::PerfilService service;

    auto perfil = service.buscarPorId(id);

    if (!perfil)
    {
        Json::Value resposta;

        resposta["erro"] = "Perfil não encontrado";

        auto response =
            drogon::HttpResponse::newHttpJsonResponse(resposta);

        response->setStatusCode(drogon::k404NotFound);

        callback(response);

        return;
    }

    Json::Value resposta;

    resposta["id"] =
        static_cast<Json::Int64>(perfil->id);

    resposta["nome"] =
        perfil->nome;

    resposta["ativo"] =
        perfil->ativo;

    resposta["criado_em"] =
        perfil->criado_em;

    if (perfil->descricao)
    {
        resposta["descricao"] =
            *perfil->descricao;
    }
    else
    {
        resposta["descricao"] =
            Json::nullValue;
    }

    auto response =
        drogon::HttpResponse::newHttpJsonResponse(resposta);

    callback(response);
}


void PerfilController::criar(
    const drogon::HttpRequestPtr& req,
    std::function<void(const drogon::HttpResponsePtr&)>&& callback)
{
    auto json = req->getJsonObject();

    if (!json)
    {
        Json::Value resposta;
        resposta["erro"] = "JSON inválido";

        auto response =
            drogon::HttpResponse::newHttpJsonResponse(resposta);

        response->setStatusCode(drogon::k400BadRequest);

        callback(response);
        return;
    }

    if (!json->isMember("nome"))
    {
        Json::Value resposta;
        resposta["erro"] = "O campo nome é obrigatório";

        auto response =
            drogon::HttpResponse::newHttpJsonResponse(resposta);

        response->setStatusCode(drogon::k400BadRequest);

        callback(response);
        return;
    }

    models::Perfil perfil;

    perfil.nome = (*json)["nome"].asString();

    if (json->isMember("descricao"))
    {
        perfil.descricao = (*json)["descricao"].asString();
    }

    if (json->isMember("ativo"))
    {
        perfil.ativo = (*json)["ativo"].asInt();
    }

    services::PerfilService service;

    auto id = service.criar(perfil);

    Json::Value resposta;

    resposta["mensagem"] = "Perfil criado com sucesso";
    resposta["id"] = static_cast<Json::Int64>(id);

    auto response =
        drogon::HttpResponse::newHttpJsonResponse(resposta);

    response->setStatusCode(drogon::k201Created);

    callback(response);
}


void PerfilController::atualizar(
    const drogon::HttpRequestPtr& req,
    std::function<void(const drogon::HttpResponsePtr&)>&& callback,
    std::int64_t id)
{
    auto json = req->getJsonObject();

    if (!json)
    {
        Json::Value resposta;

        resposta["erro"] =
            "JSON inválido";

        auto response =
            drogon::HttpResponse::newHttpJsonResponse(resposta);

        response->setStatusCode(drogon::k400BadRequest);

        callback(response);

        return;
    }

    if (!json->isMember("nome"))
    {
        Json::Value resposta;

        resposta["erro"] =
            "O campo nome é obrigatório";

        auto response =
            drogon::HttpResponse::newHttpJsonResponse(resposta);

        response->setStatusCode(drogon::k400BadRequest);

        callback(response);

        return;
    }

    models::Perfil perfil;

    perfil.nome =
        (*json)["nome"].asString();

    perfil.ativo =
        json->get("ativo", 1).asInt();

    if (json->isMember("descricao") &&
        !(*json)["descricao"].isNull())
    {
        perfil.descricao =
            (*json)["descricao"].asString();
    }

    services::PerfilService service;

    bool atualizado =
        service.atualizar(id, perfil);

    if (!atualizado)
    {
        Json::Value resposta;

        resposta["erro"] =
            "Perfil não encontrado";

        auto response =
            drogon::HttpResponse::newHttpJsonResponse(resposta);

        response->setStatusCode(drogon::k404NotFound);

        callback(response);

        return;
    }

    Json::Value resposta;

    resposta["mensagem"] =
        "Perfil atualizado com sucesso";

    resposta["id"] =
        static_cast<Json::Int64>(id);

    auto response =
        drogon::HttpResponse::newHttpJsonResponse(resposta);

    callback(response);
}


void PerfilController::excluir(
    const drogon::HttpRequestPtr& req,
    std::function<void(const drogon::HttpResponsePtr&)>&& callback,
    std::int64_t id)
{
    services::PerfilService service;

    bool excluido =
        service.excluir(id);

    if (!excluido)
    {
        Json::Value resposta;

        resposta["erro"] =
            "Perfil não encontrado";

        auto response =
            drogon::HttpResponse::newHttpJsonResponse(resposta);

        response->setStatusCode(drogon::k404NotFound);

        callback(response);

        return;
    }

    Json::Value resposta;

    resposta["mensagem"] =
        "Perfil excluído com sucesso";

    resposta["id"] =
        static_cast<Json::Int64>(id);

    auto response =
        drogon::HttpResponse::newHttpJsonResponse(resposta);

    callback(response);
}

}