#include "traininghub/controllers/HealthController.h"

namespace traininghub::controllers
{

void HealthController::health(
    const drogon::HttpRequestPtr &req,
    std::function<void(const drogon::HttpResponsePtr &)> &&callback
) const
{
    Json::Value response;
    response["status"] = "ok";
    response["application"] = "TrainingHub";

    callback(drogon::HttpResponse::newHttpJsonResponse(response));
}

void HealthController::databaseHealth(
    const drogon::HttpRequestPtr &req,
    std::function<void(const drogon::HttpResponsePtr &)> &&callback
) const
{
    auto db = drogon::app().getDbClient("default");

    db->execSqlAsync(
        "SELECT 1;",
        [callback](const drogon::orm::Result &result) mutable
        {
            Json::Value response;
            response["status"] = "ok";
            response["database"] = "connected";

            callback(drogon::HttpResponse::newHttpJsonResponse(response));
        },
        [callback](const drogon::orm::DrogonDbException &error) mutable
        {
            Json::Value response;
            response["status"] = "error";
            response["database"] = "disconnected";
            LOG_ERROR << "Falha ao verificar conexao com o banco: " << error.base().what();
            response["message"] = "Erro interno ao verificar banco.";

            auto httpResponse =
                drogon::HttpResponse::newHttpJsonResponse(response);

            httpResponse->setStatusCode(drogon::k500InternalServerError);
            callback(httpResponse);
        }
    );
}

}
