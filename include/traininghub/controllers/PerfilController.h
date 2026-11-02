#pragma once

#include <cstdint>
#include <functional>

#include <drogon/HttpController.h>

namespace traininghub::controllers
{

class PerfilController
    : public drogon::HttpController<PerfilController>
{
public:

    METHOD_LIST_BEGIN

    ADD_METHOD_TO(
        PerfilController::listar,
        "/api/perfis",
        drogon::Get,
        "traininghub::security::AuthenticationFilter"
    );

    ADD_METHOD_TO(
        PerfilController::buscarPorId,
        "/api/perfis/{id}",
        drogon::Get,
        "traininghub::security::AuthenticationFilter"
    );

    ADD_METHOD_TO(
        PerfilController::criar,
        "/api/perfis",
        drogon::Post,
        "traininghub::security::AuthenticationFilter"
    );

    ADD_METHOD_TO(
        PerfilController::atualizar,
        "/api/perfis/{id}",
        drogon::Put,
        "traininghub::security::AuthenticationFilter"
    );

    ADD_METHOD_TO(
        PerfilController::excluir,
        "/api/perfis/{id}",
        drogon::Delete,
        "traininghub::security::AuthenticationFilter"
    );

    METHOD_LIST_END

    void listar(
        const drogon::HttpRequestPtr& req,
        std::function<void(const drogon::HttpResponsePtr&)>&& callback
    );

    void buscarPorId(
        const drogon::HttpRequestPtr& req,
        std::function<void(const drogon::HttpResponsePtr&)>&& callback,
        std::int64_t id
    );

    void criar(
        const drogon::HttpRequestPtr& req,
        std::function<void(const drogon::HttpResponsePtr&)>&& callback
    );

    void atualizar(
        const drogon::HttpRequestPtr& req,
        std::function<void(const drogon::HttpResponsePtr&)>&& callback,
        std::int64_t id
    );

    void excluir(
        const drogon::HttpRequestPtr& req,
        std::function<void(const drogon::HttpResponsePtr&)>&& callback,
        std::int64_t id
    );
};

}