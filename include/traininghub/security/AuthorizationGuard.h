#pragma once

#include "traininghub/security/AuthorizationService.h"
#include <drogon/HttpRequest.h>
#include <drogon/HttpResponse.h>

namespace traininghub::security
{
class AuthorizationGuard
{
public:
    static const ValidatedAuthContext &context(const drogon::HttpRequestPtr &req);
    static bool require(const drogon::HttpRequestPtr &req, Operation operation,
                        const std::function<void(const drogon::HttpResponsePtr &)> &callback);
    static bool tenant(const drogon::HttpRequestPtr &req, std::int64_t academiaId,
                       const std::function<void(const drogon::HttpResponsePtr &)> &callback);
    static drogon::HttpResponsePtr error(drogon::HttpStatusCode status);
};
}
