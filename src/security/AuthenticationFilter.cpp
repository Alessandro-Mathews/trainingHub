#include "traininghub/security/AuthenticationFilter.h"
#include "traininghub/security/AuthorizationGuard.h"
#include "traininghub/security/SessionManager.h"
#include <drogon/drogon.h>

namespace traininghub::security
{
void AuthenticationFilter::doFilter(const drogon::HttpRequestPtr &req,
    drogon::FilterCallback &&reject, drogon::FilterChainCallback &&next)
{
    const auto identity = SessionManager::getAuthenticatedUser(req->session());
    if (!identity)
    {
        reject(AuthorizationGuard::error(drogon::k401Unauthorized));
        return;
    }
    AuthorizationService service{repositories::AuthContextRepository{drogon::app().getDbClient("default")}};
    service.validate(*identity,
        [req, next = std::move(next)](const ValidatedAuthContext &context)
        {
            req->attributes()->insert("traininghub.validatedAuth", context);
            next();
        },
        [req, reject = std::move(reject)](AuthError error)
        {
            if (error == AuthError::Unauthorized)
                SessionManager::logout(req->session());
            const auto status = error == AuthError::Unauthorized ? drogon::k401Unauthorized
                : error == AuthError::Forbidden ? drogon::k403Forbidden : drogon::k500InternalServerError;
            reject(AuthorizationGuard::error(status));
        });
}
}
