#include "traininghub/services/AuthService.h"
#include "traininghub/security/PasswordHasher.h"

#include <exception>
#include <utility>

namespace traininghub::services
{

AuthService::AuthService(repositories::UsuarioRepository repository)
    : repository_(std::move(repository))
{
}

void AuthService::authenticate(
    std::int64_t academiaId, const std::string &email, const std::string &password,
    AuthCallback callback, ErrorCallback errorCallback) const
{
    repository_.findByAcademiaAndEmail(
        academiaId, email,
        [password, callback, errorCallback](const std::optional<models::Usuario> &user)
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

            callback(security::AuthSession{
                user->id, user->academia_id, user->perfil_id});
        },
        [errorCallback](const drogon::orm::DrogonDbException &)
        {
            errorCallback();
        }
    );
}

}
