#include "traininghub/security/PasswordHasher.h"
#include "traininghub/security/SessionManager.h"

#include <iostream>
#include <stdexcept>
#include <string>

namespace
{
void require(bool condition, const char *message)
{
    if (!condition)
        throw std::runtime_error(message);
}
}

int main(int argc, char **argv)
{
    using traininghub::security::PasswordHasher;
    using traininghub::security::SessionManager;
    try
    {
        if (argc == 2 && std::string(argv[1]) == "--fixture-hash")
        {
            std::cout << PasswordHasher::hash("TH24-test-password") << '\n';
            return 0;
        }

        const std::string password{"test\0password", 13};
        const auto first = PasswordHasher::hash(password);
        const auto second = PasswordHasher::hash(password);
        require(first != second, "Salts must differ");
        require(first.starts_with("$argon2id$v=19$m=65536,t=3,p=1$"),
                "Unexpected Argon2 parameters");
        require(PasswordHasher::verify(password, first), "Valid password rejected");
        require(!PasswordHasher::verify("test", first), "Password was truncated");
        require(!PasswordHasher::verify("incorrect", first), "Wrong password accepted");
        require(!PasswordHasher::verify(password, ""), "Empty hash accepted");
        require(!PasswordHasher::verify(password, "invalid"), "Invalid hash accepted");
        require(!PasswordHasher::verify(password, first + std::string(1, '\0')),
                "Hash with embedded NUL accepted");
        require(PasswordHasher::verify("", PasswordHasher::hash("")),
                "Hasher must preserve empty input (HTTP validation is separate)");

        require(!SessionManager::authenticate(nullptr, {}), "Null session accepted");
        require(!SessionManager::getAuthenticatedUser(nullptr), "Null session has user");
        require(!SessionManager::isAuthenticated(nullptr), "Null session authenticated");
        SessionManager::logout(nullptr);
        std::cout << "PasswordHasher and null-session tests passed.\n";
        return 0;
    }
    catch (const std::exception &error)
    {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
