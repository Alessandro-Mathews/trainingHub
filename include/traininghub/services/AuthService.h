#pragma once

#include "traininghub/repositories/UsuarioRepository.h"
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

    explicit AuthService(repositories::UsuarioRepository repository);

    void authenticate(std::int64_t academiaId, const std::string &email,
                      const std::string &password, AuthCallback callback,
                      ErrorCallback errorCallback) const;

private:
    repositories::UsuarioRepository repository_;
};

}
