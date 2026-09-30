#pragma once

#include <drogon/HttpController.h>

namespace traininghub::controllers
{

class HealthController : public drogon::HttpController<HealthController>
{
public:
    METHOD_LIST_BEGIN
    ADD_METHOD_TO(
        HealthController::health,
        "/api/health",
        drogon::Get
    );

    ADD_METHOD_TO(
    HealthController::databaseHealth,
    "/api/health/database",
    drogon::Get
    );
    
    METHOD_LIST_END

    void health(
        const drogon::HttpRequestPtr &req,
        std::function<void(const drogon::HttpResponsePtr &)> &&callback
    ) const;

    void databaseHealth(
    const drogon::HttpRequestPtr &req,
    std::function<void(const drogon::HttpResponsePtr &)> &&callback
    ) const;
};

}
