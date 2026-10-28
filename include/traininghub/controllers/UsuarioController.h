#pragma once

#include <drogon/HttpController.h>

namespace traininghub::controllers
{
class UsuarioController : public drogon::HttpController<UsuarioController>
{
public:
    METHOD_LIST_BEGIN
    ADD_METHOD_TO(UsuarioController::criar, "/api/usuarios", drogon::Post);
    ADD_METHOD_TO(UsuarioController::listar, "/api/usuarios", drogon::Get);
    ADD_METHOD_TO(UsuarioController::buscarPorId, "/api/usuarios/{id}", drogon::Get);
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
