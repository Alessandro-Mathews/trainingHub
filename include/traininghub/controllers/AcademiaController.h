#pragma once

#include <drogon/HttpController.h>
#include <functional>

namespace traininghub::controllers
{

class AcademiaController : public drogon::HttpController<AcademiaController>
{
public:
    METHOD_LIST_BEGIN
    ADD_METHOD_TO(AcademiaController::listAll, "/api/academias", drogon::Get);
    METHOD_LIST_END

    void listAll(
        const drogon::HttpRequestPtr &req,
        std::function<void(const drogon::HttpResponsePtr &)> &&callback
    ) const;
};

}
