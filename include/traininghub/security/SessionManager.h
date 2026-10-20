#pragma once

#include "traininghub/security/AuthSession.h"

#include <drogon/Session.h>
#include <optional>

namespace traininghub::security
{

class SessionManager
{
public:
    static bool authenticate(const drogon::SessionPtr &session,
                             const AuthSession &user);
    static std::optional<AuthSession> getAuthenticatedUser(
        const drogon::SessionPtr &session);
    static bool isAuthenticated(const drogon::SessionPtr &session);
    static void logout(const drogon::SessionPtr &session);
};

}
