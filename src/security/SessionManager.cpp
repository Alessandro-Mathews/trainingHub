#include "traininghub/security/SessionManager.h"

namespace traininghub::security
{
namespace
{
const std::string authKey{"traininghub.auth"};
}

bool SessionManager::authenticate(const drogon::SessionPtr &session,
                                  const AuthSession &user)
{
    if (!session)
        return false;

    session->modify([&user](drogon::Session::SessionMap &values)
    {
        values.insert_or_assign(authKey, user);
    });
    session->changeSessionIdToClient();
    return true;
}

std::optional<AuthSession> SessionManager::getAuthenticatedUser(
    const drogon::SessionPtr &session)
{
    return session ? session->getOptional<AuthSession>(authKey) : std::nullopt;
}

bool SessionManager::isAuthenticated(const drogon::SessionPtr &session)
{
    return getAuthenticatedUser(session).has_value();
}

void SessionManager::logout(const drogon::SessionPtr &session)
{
    if (!session)
        return;

    session->erase(authKey);
    session->changeSessionIdToClient();
}

}
