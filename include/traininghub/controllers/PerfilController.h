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
        "/perfis",
        drogon::Get
    );

    ADD_METHOD_TO(
        PerfilController::buscarPorId,
        "/perfis/{id}",
        drogon::Get
    );

    ADD_METHOD_TO(
        PerfilController::criar,
        "/perfis",
        drogon::Post
    );

    ADD_METHOD_TO(
        PerfilController::atualizar,
        "/perfis/{id}",
        drogon::Put
    );

    ADD_METHOD_TO(
        PerfilController::excluir,
        "/perfis/{id}",
        drogon::Delete
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