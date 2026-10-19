#include "traininghub/security/PasswordHasher.h"

#include <argon2.h>
#include <drogon/utils/Utilities.h>
#include <array>
#include <cstdint>
#include <stdexcept>
#include <vector>

namespace traininghub::security
{
namespace
{
constexpr std::uint32_t iterations{3};
constexpr std::uint32_t memoryKiB{65536};
constexpr std::uint32_t parallelism{1};
constexpr std::uint32_t saltLength{16};
constexpr std::uint32_t hashLength{32};
}

std::string PasswordHasher::hash(const std::string &password)
{
    std::array<unsigned char, saltLength> salt{};
    if (!drogon::utils::secureRandomBytes(salt.data(), salt.size()))
        throw std::runtime_error("Unable to generate password salt.");

    std::vector<char> encoded(argon2_encodedlen(
        iterations, memoryKiB, parallelism, saltLength, hashLength, Argon2_id));
    const auto result = argon2id_hash_encoded(
        iterations, memoryKiB, parallelism,
        password.data(), password.size(), salt.data(), salt.size(), hashLength,
        encoded.data(), encoded.size());
    if (result != ARGON2_OK)
        throw std::runtime_error("Unable to hash password.");

    return std::string(encoded.data());
}

bool PasswordHasher::verify(const std::string &password,
                            const std::string &encodedHash)
{
    if (encodedHash.empty() || encodedHash.find('\0') != std::string::npos)
        return false;

    return argon2id_verify(encodedHash.c_str(), password.data(), password.size())
        == ARGON2_OK;
}

}
