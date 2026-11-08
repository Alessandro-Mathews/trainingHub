#pragma once

#include <drogon/HttpController.h>

namespace traininghub::controllers
{
class InstrutorController : public drogon::HttpController<InstrutorController>
{
public:
    METHOD_LIST_BEGIN
    ADD_METHOD_TO(InstrutorController::criar, "/api/instrutores", drogon::Post, "traininghub::security::AuthenticationFilter");
    ADD_METHOD_TO(InstrutorController::listar, "/api/instrutores", drogon::Get, "traininghub::security::AuthenticationFilter");
    ADD_METHOD_TO(InstrutorController::buscarPorId, "/api/instrutores/{id}", drogon::Get, "traininghub::security::AuthenticationFilter");
    METHOD_LIST_END

    void criar(const drogon::HttpRequestPtr &req,
               std::function<void(const drogon::HttpResponsePtr &)> &&callback);
    void listar(const drogon::HttpRequestPtr &req,
                std::function<void(const drogon::HttpResponsePtr &)> &&callback);
    void buscarPorId(const drogon::HttpRequestPtr &req,
                     std::function<void(const drogon::HttpResponsePtr &)> &&callback,
                     const std::string &id);
};
}
