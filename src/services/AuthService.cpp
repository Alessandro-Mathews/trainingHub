#include "traininghub/services/AuthService.h"
#include "traininghub/security/PasswordHasher.h"
#include "traininghub/security/AuthorizationService.h"

#include <exception>
#include <utility>

namespace traininghub::services
{

AuthService::AuthService(repositories::UsuarioRepository repository,
                         repositories::AuthContextRepository authContext)
    : repository_(std::move(repository)), authContext_(std::move(authContext))
{
}

void AuthService::authenticate(
    std::int64_t academiaId, const std::string &email, const std::string &password,
    AuthCallback callback, ErrorCallback errorCallback) const
{
    repository_.findByAcademiaAndEmail(
        academiaId, email,
        [password, callback, errorCallback, authContext = authContext_](const std::optional<models::Usuario> &user)
        {
            bool validPassword{};
            try
            {
                // Missing users still incur an Argon2 verification.
                static const auto dummyHash =
                    security::PasswordHasher::hash("traininghub-dummy-credential");
                validPassword = security::PasswordHasher::verify(
                    password, user ? user->senha_hash : dummyHash);
            }
            catch (const std::exception &)
            {
                errorCallback();
                return;
            }

            if (!user || !user->ativo || !validPassword)
            {
                callback(std::nullopt);
                return;
            }

            security::AuthorizationService{authContext}.validate(
                {user->id, user->academia_id, user->perfil_id},
                [callback](const security::ValidatedAuthContext &context) { callback(context.identity); },
                [callback, errorCallback](security::AuthError error)
                {
                    if (error == security::AuthError::Internal) errorCallback();
                    else callback(std::nullopt);
                });
        },
        [errorCallback](const drogon::orm::DrogonDbException &)
        {
            errorCallback();
        }
    );
}

}
