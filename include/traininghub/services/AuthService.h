#pragma once

#include "traininghub/repositories/UsuarioRepository.h"
#include "traininghub/repositories/AuthContextRepository.h"
#include "traininghub/security/AuthSession.h"

#include <functional>
#include <optional>

namespace traininghub::services
{

class AuthService
{
public:
    using AuthCallback =
        std::function<void(const std::optional<security::AuthSession> &)>;
    using ErrorCallback = std::function<void()>;

    AuthService(repositories::UsuarioRepository repository,
                repositories::AuthContextRepository authContext);

    void authenticate(std::int64_t academiaId, const std::string &email,
                      const std::string &password, AuthCallback callback,
                      ErrorCallback errorCallback) const;

private:
    repositories::UsuarioRepository repository_;
    repositories::AuthContextRepository authContext_;
};

}
