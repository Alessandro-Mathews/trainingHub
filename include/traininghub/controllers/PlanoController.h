#pragma once

#include <drogon/HttpController.h>

namespace traininghub::controllers
{
class PlanoController : public drogon::HttpController<PlanoController>
{
public:
    METHOD_LIST_BEGIN
    ADD_METHOD_TO(PlanoController::criar, "/api/planos", drogon::Post, "traininghub::security::AuthenticationFilter");
    ADD_METHOD_TO(PlanoController::listar, "/api/planos", drogon::Get, "traininghub::security::AuthenticationFilter");
    ADD_METHOD_TO(PlanoController::buscarPorId, "/api/planos/{id}", drogon::Get, "traininghub::security::AuthenticationFilter");
    ADD_METHOD_TO(PlanoController::atualizar, "/api/planos/{id}", drogon::Put, "traininghub::security::AuthenticationFilter");
    ADD_METHOD_TO(PlanoController::atualizarStatus, "/api/planos/{id}/status", drogon::Put, "traininghub::security::AuthenticationFilter");
    METHOD_LIST_END

    void criar(const drogon::HttpRequestPtr &req,
        std::function<void(const drogon::HttpResponsePtr &)> &&callback);
    void listar(const drogon::HttpRequestPtr &req,
        std::function<void(const drogon::HttpResponsePtr &)> &&callback);
    void buscarPorId(const drogon::HttpRequestPtr &req,
        std::function<void(const drogon::HttpResponsePtr &)> &&callback, const std::string &id);
    void atualizar(const drogon::HttpRequestPtr &req,
        std::function<void(const drogon::HttpResponsePtr &)> &&callback, const std::string &id);
    void atualizarStatus(const drogon::HttpRequestPtr &req,
        std::function<void(const drogon::HttpResponsePtr &)> &&callback, const std::string &id);
};
}
