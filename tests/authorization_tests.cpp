#include "traininghub/security/AuthorizationService.h"

#include <array>
#include <iostream>
#include <stdexcept>

int main()
{
    using namespace traininghub::security;
    try
    {
        const std::array roles{Role::UNKNOWN, Role::ADMIN, Role::GESTOR, Role::INSTRUTOR, Role::ALUNO};
        const std::array operations{Operation::ContextRead, Operation::AcademiasRead,
            Operation::PerfisRead, Operation::PerfisManage, Operation::UsuariosRead, Operation::UsuariosCreate};
        const bool access[5][6] = {
            {false, false, false, false, false, false},
            {true, true, true, true, true, true},
            {true, false, true, false, true, true},
            {true, false, false, false, false, false},
            {true, false, false, false, false, false}
        };
        const bool assignments[5][5] = {
            {false, false, false, false, false},
            {false, false, true, true, true},
            {false, false, false, true, true},
            {false, false, false, false, false},
            {false, false, false, false, false}
        };
        for (std::size_t actor = 0; actor < roles.size(); ++actor)
        {
            for (std::size_t operation = 0; operation < operations.size(); ++operation)
                if (AuthorizationService::allows(roles[actor], operations[operation]) != access[actor][operation])
                    throw std::runtime_error("Access matrix mismatch");
            for (std::size_t target = 0; target < roles.size(); ++target)
                if (AuthorizationService::canAssign(roles[actor], roles[target]) != assignments[actor][target])
                    throw std::runtime_error("Assignment matrix mismatch");
        }
        const std::array names{"Administrador", "Gestor", "Instrutor", "Aluno"};
        for (std::size_t index = 0; index < names.size(); ++index)
            if (roleFromName(names[index]) != roles[index + 1])
                throw std::runtime_error("Canonical name mismatch");
        for (const auto *name : {"", "Admin", "ADMIN", "admin", "administrador", "Administrador ", " Aluno", "aluno"})
            if (roleFromName(name) != Role::UNKNOWN)
                throw std::runtime_error("Noncanonical name received privileges");
        if (AuthorizationService::allows(Role::ADMIN, static_cast<Operation>(999)))
            throw std::runtime_error("Unknown operation allowed");
        std::cout << "Authorization role, access and assignment matrices passed.\n";
        return 0;
    }
    catch (const std::exception &error)
    {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
