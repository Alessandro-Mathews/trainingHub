#pragma once

#include <drogon/HttpController.h>

namespace traininghub::controllers
{
class MatriculaController : public drogon::HttpController<MatriculaController>
{
public:
    METHOD_LIST_BEGIN
    ADD_METHOD_TO(MatriculaController::criar, "/api/matriculas", drogon::Post, "traininghub::security::AuthenticationFilter");
    ADD_METHOD_TO(MatriculaController::listar, "/api/matriculas", drogon::Get, "traininghub::security::AuthenticationFilter");
    ADD_METHOD_TO(MatriculaController::buscarPorId, "/api/matriculas/{id}", drogon::Get, "traininghub::security::AuthenticationFilter");
    ADD_METHOD_TO(MatriculaController::listarPorAluno, "/api/alunos/{alunoId}/matriculas", drogon::Get, "traininghub::security::AuthenticationFilter");
    METHOD_LIST_END

    void criar(const drogon::HttpRequestPtr &req,
        std::function<void(const drogon::HttpResponsePtr &)> &&callback);
    void listar(const drogon::HttpRequestPtr &req,
        std::function<void(const drogon::HttpResponsePtr &)> &&callback);
    void buscarPorId(const drogon::HttpRequestPtr &req,
        std::function<void(const drogon::HttpResponsePtr &)> &&callback, const std::string &id);
    void listarPorAluno(const drogon::HttpRequestPtr &req,
        std::function<void(const drogon::HttpResponsePtr &)> &&callback, const std::string &alunoId);
};
}
