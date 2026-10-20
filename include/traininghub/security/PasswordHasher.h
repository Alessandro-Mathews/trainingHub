#pragma once

#include <string>

namespace traininghub::security
{

class PasswordHasher
{
public:
    static std::string hash(const std::string &password);
    static bool verify(const std::string &password,
                       const std::string &encodedHash);
};

}
