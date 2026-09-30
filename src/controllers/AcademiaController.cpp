#include "traininghub/controllers/AcademiaController.h"
#include "traininghub/services/AcademiaService.h"

#include <drogon/drogon.h>
#include <utility>
#include <vector>

namespace traininghub::controllers
{

void AcademiaController::listAll(
    const drogon::HttpRequestPtr &,
    std::function<void(const drogon::HttpResponsePtr &)> &&callback
) const
{
    services::AcademiaService service{
        repositories::AcademiaRepository{drogon::app().getDbClient("default")}
    };

    service.listAll(
        [callback](const std::vector<models::Academia> &academias)
        {
            Json::Value response(Json::arrayValue);
            for (const auto &academia : academias)
            {
                Json::Value item(Json::objectValue);
                item["id"] = Json::Int64(academia.id);
                item["nome"] = academia.nome;
                item["cnpj"] = academia.cnpj ? Json::Value(*academia.cnpj)
                                             : Json::Value(Json::nullValue);
                item["email"] = academia.email ? Json::Value(*academia.email)
                                               : Json::Value(Json::nullValue);
                item["telefone"] = academia.telefone ? Json::Value(*academia.telefone)
                                                     : Json::Value(Json::nullValue);
                item["ativo"] = academia.ativo;
                item["criado_em"] = academia.criado_em;
                response.append(std::move(item));
            }
            callback(drogon::HttpResponse::newHttpJsonResponse(response));
        },
        [callback](const drogon::orm::DrogonDbException &error)
        {
            LOG_ERROR << "Falha ao listar academias: " << error.base().what();
            Json::Value response(Json::objectValue);
            response["message"] = "Erro ao listar academias.";
            auto httpResponse = drogon::HttpResponse::newHttpJsonResponse(response);
            httpResponse->setStatusCode(drogon::k500InternalServerError);
            callback(httpResponse);
        }
    );
}

}
