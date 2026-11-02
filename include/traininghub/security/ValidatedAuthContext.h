#pragma once

#include "traininghub/security/AuthSession.h"
#include "traininghub/security/Role.h"

namespace traininghub::security
{
struct ValidatedAuthContext
{
    AuthSession identity;
    Role role{Role::UNKNOWN};
};
}
