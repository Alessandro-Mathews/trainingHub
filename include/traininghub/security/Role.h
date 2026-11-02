#pragma once

#include <string_view>

namespace traininghub::security
{
enum class Role { UNKNOWN, ADMIN, GESTOR, INSTRUTOR, ALUNO };

inline Role roleFromName(std::string_view name)
{
    if (name == "Administrador") return Role::ADMIN;
    if (name == "Gestor") return Role::GESTOR;
    if (name == "Instrutor") return Role::INSTRUTOR;
    if (name == "Aluno") return Role::ALUNO;
    return Role::UNKNOWN;
}
}
