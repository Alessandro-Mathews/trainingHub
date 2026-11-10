#pragma once

#include <drogon/HttpController.h>

namespace traininghub::controllers
{
class AlunoController : public drogon::HttpController<AlunoController>
{
public:
    METHOD_LIST_BEGIN
    ADD_METHOD_TO(AlunoController::criar, "/api/alunos", drogon::Post, "traininghub::security::AuthenticationFilter");
    ADD_METHOD_TO(AlunoController::listar, "/api/alunos", drogon::Get, "traininghub::security::AuthenticationFilter");
    ADD_METHOD_TO(AlunoController::buscarPorId, "/api/alunos/{id}", drogon::Get, "traininghub::security::AuthenticationFilter");
    ADD_METHOD_TO(AlunoController::buscarInstrutor, "/api/alunos/{alunoId}/instrutor", drogon::Get, "traininghub::security::AuthenticationFilter");
    ADD_METHOD_TO(AlunoController::definirInstrutor, "/api/alunos/{alunoId}/instrutor", drogon::Put, "traininghub::security::AuthenticationFilter");
    METHOD_LIST_END

    void criar(const drogon::HttpRequestPtr &req,
               std::function<void(const drogon::HttpResponsePtr &)> &&callback);
    void listar(const drogon::HttpRequestPtr &req,
                std::function<void(const drogon::HttpResponsePtr &)> &&callback);
    void buscarPorId(const drogon::HttpRequestPtr &req,
                     std::function<void(const drogon::HttpResponsePtr &)> &&callback,
                     const std::string &id);
    void buscarInstrutor(const drogon::HttpRequestPtr &req,
                         std::function<void(const drogon::HttpResponsePtr &)> &&callback,
                         const std::string &alunoId);
    void definirInstrutor(const drogon::HttpRequestPtr &req,
                         std::function<void(const drogon::HttpResponsePtr &)> &&callback,
                         const std::string &alunoId);
};
}
